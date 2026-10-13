"""
RevLens dataset pipeline: raw Apify JSON  ->  clean review tables.

Usage
    python clean_reviews.py                       # default folders below
    REVIEWER_HASH_SALT=<secret> python clean_reviews.py

Inputs
    data/raw/google_all_properties_20261013.json
    data/raw/makemytrip_all_properties_20261013.json
    data/raw/tripadvisor_all_properties_20261013.json
    data/current/hotels.csv      (maintained by hand: one row per hotel, platform IDs, in_cluster)

Outputs (data/current/)
    reviews.csv, sub_ratings.csv, tripadvisor_hotel_scores.csv

Design rules (lessons from v1):
    * No silent defaults: a missing rating stays missing and is reported; it is never set to 5.
    * No silent skips: every stage prints counts, and unexpected input stops the run.
    * Deduplicate only true duplicates (same platform, hotel, date, rating, text).
"""
import argparse
import hashlib
import json
import os
import re
import sys

import pandas as pd

RAW_FILES = {
    "google": "google_all_properties_20261013.json",
    "makemytrip": "makemytrip_all_properties_20261013.json",
    "tripadvisor": "tripadvisor_all_properties_20261013.json",
}
SCRAPED_AT = "2026-10-13"

# Reviews flagged by hand after reading them, keyed by platform review ID.
MANUAL_FLAGS = {
    "ChdDSUhNMG9nS0VONzcxWlBGNVp6UGlBRRAB": "off_topic_other_place",  # describes a restaurant in Jodhpur
}

COLUMNS = [
    "review_id", "hotel_id", "canonical_name", "platform", "review_origin", "platform_review_id",
    "platform_property_id", "platform_property_name", "rating_raw", "rating_scale", "rating_5",
    "review_date", "date_precision", "stay_month", "title", "text", "has_text", "language",
    "hindi_marker_count", "travel_group", "trip_purpose", "room_name", "owner_reply", "owner_reply_date",
    "reviewer_hash", "reviewer_id_type", "reviewer_review_count", "reviewer_is_local_guide",
    "helpful_count", "image_count", "original_language_platform", "text_translated_platform",
    "platform_context_json", "cross_post_group", "text_hash", "source_url", "scraped_at",
    "quality_flag", "review_edited_likely",
]


def log(msg):
    print(f"[clean] {msg}")


# ----------------------------------------------------------------------------- helpers
SALT = os.environ.get("REVIEWER_HASH_SALT", "")


def reviewer_hash(value):
    """Pseudonymous reviewer ID. Set REVIEWER_HASH_SALT (kept secret) so names cannot be re-identified by guessing."""
    if not value:
        return None
    return hashlib.sha256((SALT + str(value)).encode("utf-8")).hexdigest()[:16]


def text_hash(text):
    if not isinstance(text, str) or not text.strip():
        return None
    return hashlib.sha256(re.sub(r"\s+", "", text.lower()).encode("utf-8")).hexdigest()


EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?0?[6-9]\d{4}[\s-]?\d{5}(?!\d)")        # 98765 43210, +91-9876543210
LANDLINE = re.compile(r"(?<!\d)0\d{2,4}[\s-]?\d{3}[\s-]?\d{4}(?!\d)")              # 0135 263 6959


def mask(text):
    if not isinstance(text, str) or not text:
        return None
    text = EMAIL.sub("[EMAIL_REDACTED]", text)
    text = MOBILE.sub("[PHONE_REDACTED]", text)
    return LANDLINE.sub("[PHONE_REDACTED]", text)


# Romanised Hindi words that are NOT also common English words.
# Excluded on purpose: the, to, me, main, hi, is, par, so, he, use, bus, more, jab  ("the" caused the v1 bug).
HINDI = set("""
tha thi thay hai hain haiin hei hey nahi nahin nai nhi bahut bahot bohot bhot bhut bht
accha acha achha achchha achhi achi acchi badiya badhiya badia bekar bakwas bakwaas ghatiya kharab ganda gandi
bilkul lekin magar aur bhi wala wali wale kaafi kafi thoda thodi zyada jyada jada ekdum mast
khana khane kamra kamre paisa paise paison hua hui huye hue raha rahi rahe diya diye kiya kiye
hota hoti hote karna karne karte kar ke ki ka ko se mein mai mujhe humein hume humko hamara hamari
yaha yahan waha wahan kuch sab sabhi bas aap apna apni koi kisi kyunki kyuki matlab sahi galat
milta milti mila mili paani pani garam thanda thandi saaf safai dikkat pareshani samay waqt
log logon jagah mera meri mere gya gaya gayi gaye liya lia achhe acche wo woh ye yeh unka unki unke inka
hamesha dobara phir fir
""".split())
DEVA = re.compile(r"[\u0900-\u097F]")
LATIN = re.compile(r"[A-Za-z]")
TOKEN = re.compile(r"[a-z]+")


def detect_language(text):
    """Returns (language, distinct_hindi_markers). Tags: en, hinglish, hi, hi_mixed, other, none."""
    if not isinstance(text, str) or not text.strip():
        return "none", 0
    deva, latin = len(DEVA.findall(text)), len(LATIN.findall(text))
    if deva and deva >= latin:
        return ("hi_mixed" if latin > 10 else "hi"), 0
    tokens = TOKEN.findall(text.lower())
    hits = [t for t in tokens if t in HINDI]
    distinct = len(set(hits))
    if deva:
        return "hinglish", distinct
    if distinct >= 3 or (distinct >= 2 and len(hits) / max(len(tokens), 1) >= 0.10):
        return "hinglish", distinct
    if latin == 0:
        return "other", distinct
    return "en", distinct


TRAVEL_GROUP = {"Family": "family", "Couple": "couple", "Friends": "friends_group", "Solo": "solo",
                "FAMILY": "family", "COUPLE": "couple", "GROUP": "friends_group", "SOLO": "solo"}


def to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- loaders
def load_hotels(path):
    h = pd.read_csv(path, dtype=str).fillna("")
    lookup = {}
    for _, r in h.iterrows():
        for platform, col in [("google", "google_place_id"), ("makemytrip", "makemytrip_hotel_id"),
                              ("tripadvisor", "tripadvisor_id")]:
            if r[col]:
                key = (platform, r[col])
                if key in lookup:
                    sys.exit(f"hotels.csv: {platform} id {r[col]} is mapped to two hotels")
                lookup[key] = r.hotel_id
    log(f"hotels.csv: {len(h)} hotels, {(h.in_cluster == 'Y').sum()} in cluster")
    return h, lookup


def parse_google(path, lookup):
    places = json.load(open(path, encoding="utf-8"))
    reviews, subs, n = [], [], 0
    missing_rating = 0
    for place in places:
        pid = place["placeId"]
        if ("google", pid) not in lookup:
            sys.exit(f"Google place {pid} ({place.get('title')}) is not in hotels.csv")
        for r in place.get("reviews") or []:
            n += 1
            rid = f"rev_g_{n:05d}"
            origin = (r.get("reviewOrigin") or "Google").lower()

            # Stars are missing for reviews Google shows from other sites; those carry "x/5" in `rating`.
            rating = r.get("stars")
            if rating in (None, "", 0) and r.get("rating"):
                rating = str(r["rating"]).split("/")[0]
            rating = float(rating) if rating not in (None, "") else None
            missing_rating += rating is None

            ctx = dict(r.get("reviewContext") or {})
            text = mask(r.get("text"))
            reviews.append(dict(
                review_id=rid, hotel_id=lookup[("google", pid)], platform="google", review_origin=origin,
                platform_review_id=r.get("reviewId"), platform_property_id=pid,
                platform_property_name=place.get("title"),
                rating_raw=rating, rating_scale=5, rating_5=rating,
                review_date=(r.get("publishedAtDate") or "")[:10] or None,
                date_precision="exact" if r.get("publishedAtDate") else "missing",
                stay_month=None, title=None, text=text,
                travel_group=TRAVEL_GROUP.get(ctx.pop("Travel group", None), "unknown"),
                trip_purpose={"Vacation": "leisure", "Business": "business"}.get(ctx.pop("Trip type", None), "unknown"),
                room_name=None,
                owner_reply=mask(r.get("responseFromOwnerText")),
                owner_reply_date=(r.get("responseFromOwnerDate") or "")[:10] or None,
                reviewer_hash=reviewer_hash(r.get("reviewerId")),
                reviewer_id_type="platform_id" if r.get("reviewerId") else "none",
                reviewer_review_count=to_int(r.get("reviewerNumberOfReviews")),
                reviewer_is_local_guide=r.get("isLocalGuide"),
                helpful_count=to_int(r.get("likesCount")),
                image_count=len(r.get("reviewImageUrls") or []),
                original_language_platform=r.get("originalLanguage"),
                text_translated_platform=r.get("textTranslated"),
                platform_context_json=json.dumps(ctx, ensure_ascii=False) if ctx else None,
                source_url=r.get("reviewUrl"), scraped_at=SCRAPED_AT,
            ))
            for k, v in (r.get("reviewDetailedRating") or {}).items():
                if v is not None:
                    subs.append(dict(review_id=rid, platform_category=str(k).lower(), score=float(v)))
    log(f"Google: {len(places)} places, {n} reviews, {len(subs)} sub-ratings, {missing_rating} without any rating")
    return reviews, subs


def parse_makemytrip(path, lookup):
    items = json.load(open(path, encoding="utf-8"))
    reviews = []
    for i, x in enumerate(items, start=1):
        hid = str(x.get("hotelId"))
        if ("makemytrip", hid) not in lookup:
            sys.exit(f"MakeMyTrip hotel {hid} ({x.get('hotelName')}) is not in hotels.csv")
        rating = x.get("overallRating")
        rating = float(rating) if rating not in (None, "") else None
        rv = x.get("reviewer") or {}
        anonymous = rv.get("isAnonymous") or not rv.get("name")
        reply = x.get("ownerResponse") or {}
        tt = x.get("travelType")
        reviews.append(dict(
            review_id=f"rev_mmt_{i:05d}", hotel_id=lookup[("makemytrip", hid)], platform="makemytrip",
            review_origin="makemytrip", platform_review_id=x.get("reviewId"), platform_property_id=hid,
            platform_property_name=x.get("hotelName"),
            rating_raw=rating, rating_scale=5, rating_5=rating,
            review_date=x.get("submittedAt"), date_precision="exact" if x.get("submittedAt") else "missing",
            stay_month=x.get("checkInMonth"), title=x.get("title") or None, text=mask(x.get("reviewText")),
            travel_group=TRAVEL_GROUP.get(tt, "unknown"),
            trip_purpose="business" if tt == "BUSINESS" else "unknown",
            room_name=x.get("roomName"),
            owner_reply=mask(reply.get("text")), owner_reply_date=reply.get("date"),
            # MakeMyTrip gives only a display name: NOT a unique person ID (common names collide).
            reviewer_hash=None if anonymous else reviewer_hash(rv.get("name")),
            reviewer_id_type="none" if anonymous else "name_only",
            reviewer_review_count=to_int(rv.get("reviewsWritten")), reviewer_is_local_guide=None,
            helpful_count=to_int(x.get("usefulCount")), image_count=to_int(x.get("imagesCount")),
            original_language_platform=None, text_translated_platform=None, platform_context_json=None,
            source_url=None, scraped_at=(x.get("extractedAt") or SCRAPED_AT)[:10],
        ))
    log(f"MakeMyTrip: {len(reviews)} reviews")
    return reviews


def parse_tripadvisor_scores(path, hotels):
    items = json.load(open(path, encoding="utf-8"))
    review_like = sum(1 for t in items if t.get("reviews"))
    if review_like:
        log(f"WARNING: TripAdvisor file contains review lists for {review_like} items; this pipeline only "
            f"extracts hotel-level scores. Add a review parser before using them.")
    tmap = {r.tripadvisor_id: r.hotel_id for _, r in hotels.iterrows() if r.tripadvisor_id}
    rows, skipped = [], []
    for t in items:
        hid = tmap.get(str(t.get("id")))
        if not hid:
            skipped.append(t.get("name"))
            continue
        cs = {c["categoryName"].lower().replace(" ", "_"): c["score"] for c in (t.get("categoryReviewScores") or [])}
        hist = t.get("ratingHistogram") or {}
        rows.append(dict(
            hotel_id=hid, tripadvisor_id=t["id"], tripadvisor_name=t.get("name"), overall_rating=t.get("rating"),
            num_reviews=t.get("numberOfReviews"), ranking_position=t.get("rankingPosition"),
            ranking_denominator=t.get("rankingDenominator"), ranking_category=t.get("rankingString"),
            hotel_class=t.get("hotelClass"), price_range_usd=t.get("priceRange"),
            **{f"score_{k}": cs.get(k) for k in ["location", "rooms", "value", "cleanliness", "service", "sleep_quality"]},
            **{f"count_{s}star": hist.get(f"count{s}") for s in range(1, 6)},
            usable_for_benchmark="Y" if (t.get("numberOfReviews") or 0) >= 30 else "N",
            address=t.get("address"), web_url=t.get("webUrl"), scraped_at=SCRAPED_AT,
        ))
    log(f"TripAdvisor: {len(rows)} hotels with scores; not mapped in hotels.csv (skipped): {skipped or 'none'}")
    return pd.DataFrame(rows).sort_values("hotel_id")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--current", default="data/current")
    args = ap.parse_args()

    if not SALT:
        log("WARNING: REVIEWER_HASH_SALT not set; reviewer hashes are unsalted and names could be re-identified.")

    hotels, lookup = load_hotels(os.path.join(args.current, "hotels.csv"))
    g_rev, subs = parse_google(os.path.join(args.raw, RAW_FILES["google"]), lookup)
    m_rev = parse_makemytrip(os.path.join(args.raw, RAW_FILES["makemytrip"]), lookup)
    ta = parse_tripadvisor_scores(os.path.join(args.raw, RAW_FILES["tripadvisor"]), hotels)

    df = pd.DataFrame(g_rev + m_rev)
    df["canonical_name"] = df.hotel_id.map(hotels.set_index("hotel_id").canonical_name)

    # language and text flags
    lang = df.text.apply(detect_language)
    df["language"] = [a for a, _ in lang]
    df["hindi_marker_count"] = [b for _, b in lang]
    df["text_hash"] = df.text.apply(text_hash)
    df["has_text"] = df.text.fillna("").str.strip().ne("")

    df["quality_flag"] = df.platform_review_id.map(MANUAL_FLAGS)
    junk = df.has_text & (df.text.fillna("").str.strip().str.len() <= 3)      # "3", "5", "Wo"
    df.loc[junk, ["has_text", "language", "quality_flag"]] = [False, "none", "no_content"]
    log(f"Text: {int(df.has_text.sum())} with text, {int(junk.sum())} contentless set to rating-only, "
        f"languages {df.language.value_counts().to_dict()}")

    # dedup: only exact duplicates within one platform
    before = len(df)
    dup = df.text_hash.notna() & df.duplicated(["platform", "hotel_id", "review_date", "rating_raw", "text_hash"])
    for _, r in df[dup].iterrows():
        log(f"  duplicate removed: {r.review_id} ({r.platform}, {r.canonical_name}, {r.review_date})")
    df = df[~dup].copy()
    log(f"Dedup: {before} -> {len(df)}")

    # cross-posts: same guest text at the same hotel on two platforms (kept, flagged)
    sub = df[df.text.fillna("").str.len() >= 30]
    n_plat = sub.groupby(["hotel_id", "text_hash"]).platform.nunique()
    cp = n_plat[n_plat > 1].reset_index()[["hotel_id", "text_hash"]]
    cp["cross_post_group"] = [f"CP{i + 1:03d}" for i in range(len(cp))]
    df = df.merge(cp, on=["hotel_id", "text_hash"], how="left")
    log(f"Cross-posts: {len(cp)} groups")

    # owner reply dated before the review -> review edited later; review_date is the edit date
    df["review_edited_likely"] = (pd.to_datetime(df.owner_reply_date, errors="coerce")
                                  < pd.to_datetime(df.review_date, errors="coerce"))
    log(f"Edited-likely reviews: {int(df.review_edited_likely.sum())}")

    # checks: fail loudly rather than write bad data
    assert df.review_id.is_unique, "duplicate review_id"
    assert df.hotel_id.notna().all(), "review without hotel"
    bad = df.rating_5.isna() | ~df.rating_5.between(1, 5)
    if bad.any():
        log(f"WARNING: {int(bad.sum())} reviews with missing/out-of-range rating: {df[bad].review_id.tolist()[:10]}")

    subs = pd.DataFrame(subs)
    subs = subs[subs.review_id.isin(df.review_id)].merge(df[["review_id", "hotel_id"]], on="review_id")
    subs = subs[["review_id", "hotel_id", "platform_category", "score"]]

    df = df.sort_values(["platform", "review_id"])[COLUMNS]
    os.makedirs(args.current, exist_ok=True)
    df.to_csv(os.path.join(args.current, "reviews.csv"), index=False)
    subs.to_csv(os.path.join(args.current, "sub_ratings.csv"), index=False)
    ta.to_csv(os.path.join(args.current, "tripadvisor_hotel_scores.csv"), index=False)
    log(f"Wrote reviews.csv ({len(df)}: {df.platform.value_counts().to_dict()}), "
        f"sub_ratings.csv ({len(subs)}), tripadvisor_hotel_scores.csv ({len(ta)})")


if __name__ == "__main__":
    main()
