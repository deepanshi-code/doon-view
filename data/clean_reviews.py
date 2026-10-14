"""
RevLens dataset pipeline: raw Apify JSON  ->  clean review tables.

Usage
    python clean_reviews.py                       # default folders below
    REVIEWER_HASH_SALT=<secret> python clean_reviews.py

Inputs
    data/raw/google_all_properties_20261013.json
    data/raw/makemytrip_all_properties_20261013.json
    data/raw/tripadvisor_all_properties_20261013.json   (hotel-level scores)
    data/raw/tripadvisor_reviews_*.json                  (review-actor output, optional, any number of files)
    data/raw/booking_reviews_*.json                      (Booking.com reviews actor output, optional)
    data/raw/agoda_reviews_*.json                        (Agoda reviews actor output, optional)
    data/current/hotels.csv      (maintained by hand: one row per hotel, platform IDs, in_cluster)

Outputs (data/current/)
    reviews.csv, sub_ratings.csv, tripadvisor_hotel_scores.csv

Design rules (lessons from v1):
    * No silent defaults: a missing rating stays missing and is reported; it is never set to 5.
    * No silent skips: every stage prints counts, and unexpected input stops the run.
    * Deduplicate only true duplicates (same platform, hotel, date, rating, text).
"""
import argparse
import glob
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
TRIPADVISOR_REVIEW_GLOB = "tripadvisor_reviews_*.json"   # one or more review-actor outputs
BOOKING_REVIEW_GLOB = "booking_reviews_*.json"           # Booking.com reviews actor (piotrv1001/booking-reviews-scraper)
AGODA_REVIEW_GLOB = "agoda_reviews_*.json"               # Agoda reviews actor (blackfalcondata/agoda-reviews-scraper)
SCRAPED_AT = "2026-10-13"

# Listings that were scraped but turned out to be a different property. Their reviews are skipped (and logged),
# so the raw files can stay unedited.
IGNORED_LISTINGS = {
    ("agoda", "56389887"): "PerfectStayz Mall Road Mussoorie - a different Perfectstayz property (photo check, 13 Oct 2026)",
}

# Reviews flagged by hand after reading them, keyed by platform review ID.
MANUAL_FLAGS = {
    "ChdDSUhNMG9nS0VONzcxWlBGNVp6UGlBRRAB": "off_topic_other_place",  # describes a restaurant in Jodhpur
}

COLUMNS = [
    "review_id", "hotel_id", "canonical_name", "platform", "review_origin", "platform_review_id",
    "platform_property_id", "platform_property_name", "rating_raw", "rating_scale", "rating_5",
    "review_date", "date_precision", "stay_month", "stay_nights", "stay_status", "title", "text",
    "text_positive", "text_negative", "has_text", "language",
    "hindi_marker_count", "travel_group", "trip_purpose", "room_name", "owner_reply", "owner_reply_date",
    "reviewer_hash", "reviewer_id_type", "reviewer_country", "reviewer_review_count", "reviewer_is_local_guide",
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
    ratio = len(hits) / max(len(tokens), 1)
    # Long English reviews sometimes quote a Hindi phrase ("they said light aati jaati rehti hai");
    # these stay "en" (see hindi_marker_count), so a minimum share of Hindi words is required.
    # Very short reviews ("Bahut shandar", "Mast hotel hai") rarely reach 2 distinct markers.
    if (distinct >= 3 and ratio >= 0.05) or (distinct >= 2 and ratio >= 0.10) or (len(tokens) <= 5 and distinct >= 1 and ratio >= 0.3):
        return "hinglish", distinct
    if latin == 0:
        return "other", distinct
    return "en", distinct


TRAVEL_GROUP = {"Family": "family", "Couple": "couple", "Friends": "friends_group", "Solo": "solo",
                "FAMILY": "family", "COUPLE": "couple", "GROUP": "friends_group", "SOLO": "solo",
                "COUPLES": "couple", "FRIENDS": "friends_group",
                "FAMILIES": "family", "SOLO_TRAVELLERS": "solo", "GROUP_OF_FRIENDS": "friends_group",
                "Family with young children": "family", "Family with teens": "family", "Group": "friends_group",
                "Solo traveler": "solo"}


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
                              ("tripadvisor", "tripadvisor_id"), ("booking", "booking_id"),
                              ("agoda", "agoda_id")]:
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


def parse_tripadvisor_reviews(paths, lookup):
    reviews, subs, seen = [], [], set()
    translated = 0
    for path in paths:
        items = json.load(open(path, encoding="utf-8"))
        for x in items:
            if not isinstance(x, dict) or "locationId" not in x or "text" not in x:
                sys.exit(f"{path}: item without locationId/text - is this the TripAdvisor REVIEWS actor output?")
            if x["id"] in seen:
                continue                                   # same review in two run files
            seen.add(x["id"])
            loc = str(x["locationId"])
            if ("tripadvisor", loc) not in lookup:
                sys.exit(f"TripAdvisor location {loc} ({(x.get('placeInfo') or {}).get('name')}) is not in hotels.csv")
            rating = float(x["rating"]) if x.get("rating") not in (None, "") else None
            user = x.get("user") or {}
            reply = x.get("ownerResponse") or {}
            if reply and not isinstance(reply, dict):
                sys.exit(f"Unexpected ownerResponse format: {str(reply)[:80]}")
            tt = x.get("tripType")
            machine = bool(x.get("isMachineTranslated"))
            translated += machine
            rid = f"rev_ta_{x['id']}"                      # TripAdvisor review IDs are stable, so use them directly
            reviews.append(dict(
                review_id=rid, hotel_id=lookup[("tripadvisor", loc)], platform="tripadvisor",
                review_origin="tripadvisor", platform_review_id=x["id"], platform_property_id=loc,
                platform_property_name=(x.get("placeInfo") or {}).get("name"),
                rating_raw=rating, rating_scale=5, rating_5=rating,
                review_date=x.get("publishedDate"), date_precision="exact" if x.get("publishedDate") else "missing",
                stay_month=x.get("travelDate"), title=x.get("title") or None,
                # If the actor returned a machine translation, the original text is not available.
                text=None if machine else mask(x.get("text")),
                travel_group=TRAVEL_GROUP.get(tt, "unknown"),
                trip_purpose="business" if tt == "BUSINESS" else ("leisure" if tt else "unknown"),
                room_name=None,
                owner_reply=mask(reply.get("text")),
                owner_reply_date=(reply.get("publishedDate") or "")[:10] or None,
                reviewer_hash=reviewer_hash(user.get("userId")),
                reviewer_id_type="platform_id" if user.get("userId") else "none",
                reviewer_review_count=to_int((user.get("contributions") or {}).get("totalContributions")),
                reviewer_is_local_guide=None,
                helpful_count=to_int(x.get("helpfulVotes")), image_count=len(x.get("photos") or []),
                original_language_platform=x.get("originalLanguage"),
                text_translated_platform=mask(x.get("text")) if machine else None,
                platform_context_json=None, source_url=x.get("url"), scraped_at=SCRAPED_AT,
            ))
            for sr in x.get("subratings") or []:
                if sr.get("value") is not None:
                    subs.append(dict(review_id=rid, platform_category=str(sr["name"]).lower().replace(" ", "_"),
                                     score=float(sr["value"])))
    log(f"TripAdvisor reviews: {len(paths)} file(s), {len(reviews)} reviews, {len(subs)} sub-ratings, "
        f"{translated} machine-translated (original text missing)")
    return reviews, subs


def parse_booking(paths, lookup):
    """Booking.com: score out of 10, separate liked / disliked text, stay dates, stay status, no reviewer ID."""
    reviews, seen = [], set()
    for path in paths:
        for x in json.load(open(path, encoding="utf-8")):
            if not isinstance(x, dict) or "hotelId" not in x or "score" not in x:
                sys.exit(f"{path}: item without hotelId/score - is this the Booking.com REVIEWS actor output?")
            if x["reviewId"] in seen:
                continue
            seen.add(x["reviewId"])
            hid = str(x["hotelId"])
            if ("booking", hid) not in lookup:
                sys.exit(f"Booking hotel {hid} ({x.get('hotelName')}) is not in hotels.csv (column booking_id)")
            score = float(x["score"]) if x.get("score") not in (None, "") else None
            liked = mask((x.get("liked") or "").strip()) or None
            disliked = mask((x.get("disliked") or "").strip()) or None
            # Combined text keeps the guest's own split visible to downstream models.
            parts = [f"Liked: {liked}" if liked else None, f"Disliked: {disliked}" if disliked else None]
            text = "\n".join(p for p in parts if p) or None
            lang = x.get("language")
            reviews.append(dict(
                review_id=f"rev_bk_{x['reviewId']}", hotel_id=lookup[("booking", hid)], platform="booking",
                review_origin="booking", platform_review_id=x["reviewId"], platform_property_id=hid,
                platform_property_name=x.get("hotelName"),
                # Booking scores run 1-10; map linearly onto 1-5 (1 -> 1, 10 -> 5) so rating_5 shares one range.
                rating_raw=score, rating_scale=10, rating_5=round(1 + (score - 1) * 4 / 9, 3) if score is not None else None,
                review_date=(x.get("reviewedAt") or "")[:10] or None,
                date_precision="exact" if x.get("reviewedAt") else "missing",
                stay_month=(x.get("stayCheckin") or "")[:7] or None, stay_nights=to_int(x.get("nights")),
                stay_status=x.get("stayStatus"), title=(x.get("title") or "").strip() or None,
                text=text, text_positive=liked, text_negative=disliked,
                travel_group=TRAVEL_GROUP.get(x.get("travellerType"), "unknown"), trip_purpose="unknown",
                room_name=x.get("roomType"),
                owner_reply=mask(x.get("hotelReply")) if isinstance(x.get("hotelReply"), str) else None,
                owner_reply_date=None,
                reviewer_hash=None, reviewer_id_type="none", reviewer_country=x.get("reviewerCountry"),
                reviewer_review_count=None, reviewer_is_local_guide=None,
                helpful_count=to_int(x.get("helpfulVotes")), image_count=None,
                original_language_platform=None if lang in (None, "xu") else lang,   # "xu" = undetermined
                text_translated_platform=None, platform_context_json=None,
                source_url=x.get("hotelUrl"), scraped_at=SCRAPED_AT,
            ))
    log(f"Booking.com: {len(paths)} file(s), {len(reviews)} reviews, "
        f"{sum(r['text'] is None for r in reviews)} score-only, "
        f"{sum(r['stay_status'] != 'stayed' for r in reviews)} by guests who did not stay")
    return reviews


def local_date(ts, fmt="%Y-%m-%d"):
    """Agoda timestamps carry +07:00; convert to India time before taking the date."""
    if not ts:
        return None
    return pd.Timestamp(ts).tz_convert("Asia/Kolkata").strftime(fmt)


def parse_agoda(paths, lookup):
    """Agoda: score out of 10, optional positives/negatives, stay dates. Only Agoda-native reviews are kept;
    Agoda also shows Booking.com / Priceline reviews, which would duplicate other sources."""
    reviews, seen, other_source, translated, ignored = [], set(), 0, 0, {}
    for path in paths:
        for x in json.load(open(path, encoding="utf-8")):
            if not isinstance(x, dict) or "hotelId" not in x or "rating" not in x:
                sys.exit(f"{path}: item without hotelId/rating - is this the Agoda REVIEWS actor output?")
            if (x.get("provider") or "").lower() != "agoda":
                other_source += 1
                continue
            if x["reviewId"] in seen:
                continue
            seen.add(x["reviewId"])
            hid = str(x["hotelId"])
            if ("agoda", hid) in IGNORED_LISTINGS:
                ignored[hid] = ignored.get(hid, 0) + 1
                continue
            if ("agoda", hid) not in lookup:
                sys.exit(f"Agoda hotel {hid} ({x.get('hotelName')}) is not in hotels.csv (column agoda_id)")
            score = float(x["rating"]) if x.get("rating") not in (None, "") else None
            rv = x.get("reviewer") or {}
            src_lang = x.get("translatedFrom")
            # `text` is shown in the site language; if it was translated and no original is given, keep it
            # only as a translation.
            machine = bool(src_lang) and src_lang != (x.get("translatedTo") or "en") and not x.get("originalText")
            translated += machine
            body = (x.get("originalText") or x.get("text") or "").strip()
            group = rv.get("travelerGroup")
            reviews.append(dict(
                review_id=f"rev_ag_{x['reviewId']}", hotel_id=lookup[("agoda", hid)], platform="agoda",
                review_origin="agoda", platform_review_id=x["reviewId"], platform_property_id=hid,
                platform_property_name=x.get("hotelName"),
                rating_raw=score, rating_scale=10, rating_5=round(1 + (score - 1) * 4 / 9, 3) if score is not None else None,
                review_date=local_date(x.get("reviewDate")), date_precision="exact" if x.get("reviewDate") else "missing",
                stay_month=local_date(x.get("checkInDate"), "%Y-%m"), stay_nights=to_int(rv.get("lengthOfStay")),
                stay_status=None, title=((x.get("originalTitle") or x.get("title") or "").strip() or None),
                text=None if machine else (mask(body) or None),
                text_positive=mask((x.get("positives") or "").strip()) or None,
                text_negative=mask((x.get("negatives") or "").strip()) or None,
                travel_group=TRAVEL_GROUP.get(group, "unknown"),
                trip_purpose="business" if group == "Business traveler" else "unknown",
                room_name=rv.get("roomType"),
                owner_reply=mask(x.get("responseText")), owner_reply_date=local_date(x.get("responseDate")),
                reviewer_hash=None, reviewer_id_type="none", reviewer_country=rv.get("country"),
                reviewer_review_count=to_int(rv.get("reviewedCount")), reviewer_is_local_guide=None,
                helpful_count=to_int(x.get("helpfulVotes")), image_count=len(x.get("images") or []),
                original_language_platform=src_lang, text_translated_platform=mask(body) if machine else None,
                platform_context_json=None, source_url=x.get("hotelUrl"), scraped_at=(x.get("scrapedAt") or SCRAPED_AT)[:10],
            ))
    log(f"Agoda: {len(paths)} file(s), {len(reviews)} Agoda-native reviews, {other_source} from other sources skipped, "
        f"{translated} machine-translated (original text missing)")
    for hid, n in ignored.items():
        log(f"  skipped {n} reviews from ignored listing agoda {hid}: {IGNORED_LISTINGS[('agoda', hid)]}")
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
    ta_paths = sorted(glob.glob(os.path.join(args.raw, TRIPADVISOR_REVIEW_GLOB)))
    t_rev, t_subs = parse_tripadvisor_reviews(ta_paths, lookup) if ta_paths else ([], [])
    subs = subs + t_subs

    bk_paths = sorted(glob.glob(os.path.join(args.raw, BOOKING_REVIEW_GLOB)))
    b_rev = parse_booking(bk_paths, lookup) if bk_paths else []

    ag_paths = sorted(glob.glob(os.path.join(args.raw, AGODA_REVIEW_GLOB)))
    a_rev = parse_agoda(ag_paths, lookup) if ag_paths else []

    df = pd.DataFrame(g_rev + m_rev + t_rev + b_rev + a_rev)
    df["canonical_name"] = df.hotel_id.map(hotels.set_index("hotel_id").canonical_name)

    # language and text flags
    lang = df.text.apply(detect_language)
    df["language"] = [a for a, _ in lang]
    df["hindi_marker_count"] = [b for _, b in lang]
    df["text_hash"] = df.text.apply(text_hash)
    df["has_text"] = df.text.fillna("").str.strip().ne("")
    # The tagger only knows en / hi / hinglish. Trust the platform when it reports another language
    # (e.g. a French TripAdvisor review), for texts long enough for its detection to be reliable.
    # Platforms sometimes mislabel English (a TripAdvisor "fr" review reads "Best experience value for money"),
    # so only override when few words are common English ones.
    EN_COMMON = set("the and is was very good for with in of to a we it hotel room rooms staff best nice value "
                    "money great stay experience service food location clean".split())
    en_share = df.text.fillna("").str.lower().apply(lambda t: (lambda w: sum(x in EN_COMMON for x in w) / max(len(w), 1))(TOKEN.findall(t)))
    other = (~df.original_language_platform.isin(["en", "hi", "en-Deva"]) & df.original_language_platform.notna()
             & (df.language == "en") & (df.text.fillna("").str.len() >= 20) & (en_share < 0.2))
    df.loc[other, "language"] = "other"

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

    # Google shows some TripAdvisor reviews (review_origin = tripadvisor). If we also scraped TripAdvisor
    # directly, keep the native record (more fields). Match on hotel + first 60 letters/digits: Google joins
    # TripAdvisor paragraphs with "|" and may truncate, so punctuation and spacing are ignored.
    norm = df.text.fillna("").str.lower().str.replace(r"[^a-z0-9]", "", regex=True).str[:60]
    native = set(zip(df.hotel_id[df.platform == "tripadvisor"], norm[df.platform == "tripadvisor"]))
    syn = (df.platform == "google") & (df.review_origin == "tripadvisor") & (norm.str.len() >= 12)
    copy = syn & pd.Series([(h, t) in native for h, t in zip(df.hotel_id, norm)], index=df.index)
    for _, r in df[copy].iterrows():
        log(f"  Google copy of a scraped TripAdvisor review removed: {r.review_id}")
    df = df[~copy].copy()

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

    df = df.reindex(columns=COLUMNS)                 # platforms without a field get an empty column
    df = df.sort_values(["platform", "review_id"])
    os.makedirs(args.current, exist_ok=True)
    df.to_csv(os.path.join(args.current, "reviews.csv"), index=False)
    subs.to_csv(os.path.join(args.current, "sub_ratings.csv"), index=False)
    ta.to_csv(os.path.join(args.current, "tripadvisor_hotel_scores.csv"), index=False)
    log(f"Wrote reviews.csv ({len(df)}: {df.platform.value_counts().to_dict()}), "
        f"sub_ratings.csv ({len(subs)}), tripadvisor_hotel_scores.csv ({len(ta)})")


if __name__ == "__main__":
    main()
