"""Build the training set from the collected Mussoorie reviews, with 5 cross-validation folds.

    python -m doonview_ml.data --reviews ../data/reviews.csv --sub-ratings ../data/sub_ratings.csv --out data/processed

Rules (see data/DATA_CHANGELOG.md for how the CSVs were made):
  * text reviews only, without a quality flag (off-topic, contentless), with a 1-5 star rating
  * MakeMyTrip titles are part of what the guest wrote: "title. text"
  * sentiment comes from the guest's own stars, never from a model
  * folds are stratified by sentiment and grouped, so a review posted on two platforms (cross_post_group) or two
    reviews by the same Google account never sit on both sides of a split
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from .labels import SUBRATING_ASPECT, rating_to_sentiment


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def build(reviews_csv: Path, sub_csv: Path | None, folds: int, seed: int) -> pd.DataFrame:
    raw = pd.read_csv(reviews_csv, dtype={"title": str, "text": str})
    keep = (_truthy(raw["has_text"]) & raw["quality_flag"].isna() & raw["rating_5"].between(1, 5)
            & raw["text"].fillna("").str.strip().ne(""))
    df = raw[keep].copy()
    print(f"{len(raw)} reviews -> {len(df)} with text, a rating and no quality flag")

    title = df["title"].fillna("").str.strip()
    body = df["text"].str.strip()
    repeated = [b.lower().startswith(t.lower()) for t, b in zip(title, body)]  # some guests restate the title
    df["text"] = np.where(title.ne("") & ~np.array(repeated), title + ". " + body, body)
    df["sentiment"] = df["rating_5"].map(rating_to_sentiment)

    own_account = (df["reviewer_id_type"] == "platform_id") & df["reviewer_hash"].notna()
    df["group"] = np.where(df["cross_post_group"].notna(), df["cross_post_group"],
                           np.where(own_account, "rv-" + df["reviewer_hash"].astype(str), df["review_id"]))

    df["fold"] = -1
    splitter = StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=seed)
    for k, (_, idx) in enumerate(splitter.split(df, df["sentiment"], df["group"])):
        df.iloc[idx, df.columns.get_loc("fold")] = k

    if sub_csv and sub_csv.is_file():
        subs = pd.read_csv(sub_csv)
        subs = subs[subs["platform_category"].isin(SUBRATING_ASPECT)]
        wide = subs.pivot_table(index="review_id", columns="platform_category", values="score", aggfunc="first")
        wide.columns = [f"sub_{SUBRATING_ASPECT[c]}" for c in wide.columns]
        df = df.merge(wide, left_on="review_id", right_index=True, how="left")

    cols = ["review_id", "hotel_id", "canonical_name", "platform", "review_date", "language", "rating_5", "sentiment",
            "text", "group", "fold"] + [c for c in df.columns if c.startswith("sub_")]
    return df[cols].reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--reviews", type=Path, required=True)
    p.add_argument("--sub-ratings", type=Path)
    p.add_argument("--out", type=Path, default=Path("data/processed"))
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=13)
    args = p.parse_args()
    df = build(args.reviews, args.sub_ratings, args.folds, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out / "reviews.parquet", index=False)
    manifest = {
        "rows": len(df), "folds": args.folds, "seed": args.seed,
        "sentiment": df["sentiment"].value_counts().to_dict(),
        "per_fold": {int(k): g["sentiment"].value_counts().to_dict() for k, g in df.groupby("fold")},
        "languages": df["language"].value_counts().to_dict(),
        "source_sha256": hashlib.sha256(args.reviews.read_bytes()).hexdigest(),
        "ids_sha256": hashlib.sha256("\n".join(sorted(df["review_id"])).encode()).hexdigest(),
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
