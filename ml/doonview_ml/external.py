"""Outside training data for the mixed model: a sample of TripAdvisor hotel reviews, labelled by the same teacher.

    python -m doonview_ml.external --out data/external [--rows 15000] [--source local.parquet]

Why: the Mussoorie-only models missed most WiFi, location and food complaints because the town has only 17-76 of
each to learn from. Hotel reviews from elsewhere teach what a complaint about each aspect looks like; the Mussoorie
reviews (repeated in training) keep the model on local wording.

Rules:
  * fold = -1: these reviews are only ever trained on, never scored, so every reported number is still measured on
    Mussoorie reviews only
  * complaints are over-represented (MIX), because complaints are what the Mussoorie data lacks
  * one review per author, no duplicate texts, 30-400 words (long reviews would not fit the teacher's context)
  * sentiment from the guest's own stars, as for the Mussoorie reviews

Licence: jniimi/tripadvisor-review-rating is scraped TripAdvisor text with no upstream licence. Academic and
non-commercial use only: never commit or publish the data, and keep any model trained on it private, as the current
app model already is.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from .labels import rating_to_sentiment

DATASET = "jniimi/tripadvisor-review-rating"
DATASET_FILE = "data/train-00000-of-00001.parquet"  # parquet only: the repo's .pkl copies are never loaded
MIX = {"negative": 0.30, "neutral": 0.20, "positive": 0.50}
MIN_CHARS, MAX_WORDS = 30, 400
COLUMNS = ["review_id", "text", "sentiment", "rating_5", "group", "fold", "source"]


def build(raw: pd.DataFrame, rows: int, seed: int, keep: pd.DataFrame | None = None) -> pd.DataFrame:
    """raw: the dataset's own columns (review, overall, hotel_id = a per-review id, user_id).
    keep: an earlier sample; its rows are kept first (their teacher labels already exist) and topped up."""
    text = raw["review"].fillna("").astype(str).str.split().str.join(" ")
    df = pd.DataFrame({"review_id": "ta-" + raw["hotel_id"].astype(str), "text": text,
                       "rating_5": pd.to_numeric(raw["overall"], errors="coerce"),
                       "group": "ta-author-" + raw["user_id"].astype(str)})
    words = df["text"].str.split().str.len()
    df = df[df["text"].str.len().ge(MIN_CHARS) & words.le(MAX_WORDS) & df["rating_5"].between(1, 5)]
    df = df[~df["text"].str.lower().duplicated()].drop_duplicates("group")
    df["sentiment"] = df["rating_5"].map(rating_to_sentiment)
    kept = set(keep["review_id"]) if keep is not None else set()
    parts = []
    for s, g in df.groupby("sentiment"):
        if s not in MIX:
            continue
        quota = round(rows * MIX[s])
        old = g[g["review_id"].isin(kept)].head(quota)
        new = g[~g["review_id"].isin(kept)]
        parts += [old, new.sample(min(len(new), quota - len(old)), random_state=seed)]
    out = pd.concat(parts).sample(frac=1, random_state=seed)
    out["fold"], out["source"] = -1, "tripadvisor"
    return out[COLUMNS].reset_index(drop=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", type=Path, default=Path("data/external"))
    p.add_argument("--rows", type=int, default=15000)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--source", type=Path, help="a local parquet of the dataset instead of downloading it")
    args = p.parse_args()
    if args.source:
        raw = pd.read_parquet(args.source)
    else:
        from huggingface_hub import hf_hub_download
        raw = pd.read_parquet(hf_hub_download(DATASET, DATASET_FILE, repo_type="dataset"))
    earlier = args.out / "reviews.parquet"
    keep = pd.read_parquet(earlier) if earlier.is_file() else None
    df = build(raw, args.rows, args.seed, keep)
    if keep is not None:
        print(f"kept {df['review_id'].isin(keep['review_id']).sum()} of the earlier {len(keep)} (already labelled)")
    args.out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out / "reviews.parquet", index=False)
    manifest = {"dataset": DATASET, "rows": len(df), "seed": args.seed, "mix": MIX,
                "sentiment": df["sentiment"].value_counts().to_dict(),
                "median_words": int(df["text"].str.split().str.len().median()),
                "ids_sha256": hashlib.sha256("\n".join(sorted(df["review_id"])).encode()).hexdigest()}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
