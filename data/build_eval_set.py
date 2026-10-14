"""
Builds the multilingual evaluation set (English / Hindi / Hinglish) for RevLens.

Usage (from the project root, after clean_reviews.py has run):
    python build_eval_set.py

Inputs
    data/raw/eval/google_hindi_eval_*.json   keyword-filtered Google review runs (any number)
    data/current/reviews.csv                 main dataset (for its Hindi/Hinglish reviews and the English sample)
    data/current/hotels.csv

Output
    data/eval/eval_reviews.csv               one row per review, label columns left empty

The keyword sample is deliberately biased towards Hindi text, so it is kept OUT of the benchmark data.
"""
import glob
import json
import os

import pandas as pd

from clean_reviews import detect_language, mask, log

EVAL_RAW = "data/raw/eval/google_hindi_eval_*.json"
ENGLISH_SAMPLE = 100
SEED = 42
HINDI_TAGS = {"hinglish", "hi", "hi_mixed"}
ASPECTS = ["food", "room", "housekeeping", "staff", "location", "value_for_money", "cleanliness", "booking_experience"]


def rating_of(x):
    if x.get("stars") not in (None, "", 0):
        return float(x["stars"])
    if x.get("rating"):                                   # TripAdvisor reviews shown on Google: "4/5"
        return float(str(x["rating"]).split("/")[0])
    return None


def main():
    hotels = pd.read_csv("data/current/hotels.csv", dtype=str).fillna("")
    by_place = dict(zip(hotels.google_place_id, hotels.hotel_id))
    names = dict(zip(hotels.hotel_id, hotels.canonical_name))
    main_df = pd.read_csv("data/current/reviews.csv")

    # 1) keyword runs: merge, deduplicate by Google review ID, keep Hindi / Hinglish
    paths = sorted(glob.glob(EVAL_RAW))
    seen, raw = {}, 0
    for p in paths:
        for x in json.load(open(p, encoding="utf-8")):
            raw += 1
            seen.setdefault(x["reviewId"], x)
    rows = []
    for rid, x in seen.items():
        lang, markers = detect_language(x.get("text"))
        if lang not in HINDI_TAGS:
            continue
        if x.get("placeId") not in by_place:
            log(f"  skipped review from unmapped place {x.get('placeId')} ({x.get('title')})")
            continue
        rows.append(dict(
            source="keyword_search", platform="google", platform_review_id=rid,
            hotel_id=by_place[x["placeId"]], rating_5=rating_of(x),
            review_date=(x.get("publishedAtDate") or "")[:10] or None,
            language=lang, platform_language=x.get("originalLanguage"),
            text=mask(x.get("text")), text_translated_platform=mask(x.get("textTranslated")),
        ))
    kw = pd.DataFrame(rows)
    log(f"Keyword runs: {len(paths)} files, {raw} results, {len(seen)} unique, {len(kw)} Hindi/Hinglish")

    # 2) Hindi / Hinglish already in the main dataset but not found by the keyword search
    mh = main_df[main_df.language.isin(HINDI_TAGS)]
    extra = mh[~mh.platform_review_id.isin(set(kw.platform_review_id))]
    extra = extra.assign(source="main_dataset", platform_language=extra.original_language_platform)[
        ["source", "platform", "platform_review_id", "hotel_id", "rating_5", "review_date", "language",
         "platform_language", "text", "text_translated_platform"]]
    log(f"Main dataset: {len(mh)} Hindi/Hinglish reviews, {len(extra)} not found by keywords (added)")

    # 3) English comparison sample: cluster hotels, real text, spread across ratings and platforms
    cluster = set(hotels.hotel_id[hotels.in_cluster == "Y"])
    en = main_df[(main_df.language == "en") & main_df.hotel_id.isin(cluster)
                 & main_df.text.fillna("").str.len().between(30, 800)].copy()
    en["band"] = pd.cut(en.rating_5, [0, 2.5, 3.5, 5.1], labels=["negative", "mixed", "positive"])
    # equal thirds by rating band, so negative reviews are not drowned out by 5-star ones
    per_band = ENGLISH_SAMPLE // 3
    en_s = (en.groupby("band", observed=True, group_keys=False)
              .apply(lambda g: g.sample(min(len(g), per_band), random_state=SEED)))
    en_s = en_s.assign(source="english_sample", platform_language=en_s.original_language_platform)[extra.columns]
    log(f"English sample: {len(en_s)} reviews ({per_band} per rating band, seed {SEED})")

    ev = pd.concat([kw, extra, en_s], ignore_index=True)
    ev["in_main_dataset"] = ev.platform_review_id.isin(set(main_df.platform_review_id))
    ev["canonical_name"] = ev.hotel_id.map(names)
    ev = ev.sample(frac=1, random_state=SEED).reset_index(drop=True)      # shuffle so annotators can't guess the group
    ev.insert(0, "eval_id", [f"EV{i + 1:04d}" for i in range(len(ev))])

    # empty label columns
    ev["label_sentiment"] = None
    for a in ASPECTS:
        ev[f"label_{a}"] = None
    ev["annotator"] = None
    ev["notes"] = None

    os.makedirs("data/eval", exist_ok=True)
    ev.to_csv("data/eval/eval_reviews.csv", index=False)
    log(f"Wrote data/eval/eval_reviews.csv: {len(ev)} reviews, languages {ev.language.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
