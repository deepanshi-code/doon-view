# Dataset changelog (Mussoorie Mall Road cluster, scraped 2026-10-13)

## v2 — canonical hotel IDs
- Added `hotels.csv` (MSR01–MSR08) mapping Google / MakeMyTrip / TripAdvisor IDs.
- Added `hotel_id`, `canonical_name`; renamed platform columns to `platform_property_id`, `platform_property_name`.

## v3 — language tagging
- Replaced faulty tagger (English "the" was read as Hindi "थे"; 723 → 24 Hinglish).
- Tags: en, hinglish, hi, hi_mixed, other, none. Added `hindi_marker_count`, `has_text`.
- `text_hash` set to empty for rating-only reviews.

## v4 — restored reviews, context fields, correct dedup
- Restored 46 reviews wrongly removed by global text-hash dedup (short generic texts like
  "Nice" from different guests/hotels, and same-text reviews on different platforms).
- Dedup now removes only exact duplicates within one platform (same hotel, date, rating, text): 1 removed (rev_mmt_01000).
- Cross-platform reposts by the same guest are kept and flagged in `cross_post_group` (4 groups, 8 rows).
- Added: `platform_review_id`, `stay_month` (MakeMyTrip), `room_name` (MakeMyTrip), `travel_group`, `trip_purpose`,
  `reviewer_review_count`, `reviewer_is_local_guide`, `helpful_count`, `image_count`,
  `original_language_platform`, `text_translated_platform` (Google's own translation), `platform_context_json`.
- Removed empty `stay_date` column; filled missing MakeMyTrip `scraped_at`.
- `sub_ratings_v4.csv` rebuilt from raw Google data (3,948 rows; no orphans).
- Known gap: `reviewer_hash` is empty for the 7 restored MakeMyTrip reviews (original hashing method unknown).

Final: 2,835 reviews (Google 1,600, MakeMyTrip 1,235).

## v5 — rating bug, origins, MakeMyTrip fields, cluster decision
- 14 "Google" reviews are TripAdvisor reviews shown on Google (`review_origin = tripadvisor`). They have no star value,
  and the cleaning script defaulted missing stars to 5. Ratings now read from the "x/5" field: 3 corrected (4, 1, 3 stars).
- Filled MakeMyTrip `owner_reply_date` (200 rows) and `reviewer_hash` for restored rows
  (original method: sha256 of the reviewer dict as a string, first 16 chars).
- Google reviewer_hash is empty for the 14 syndicated TripAdvisor reviews (no reviewer ID available).
- Added `quality_flag`; one review describes a restaurant in Jodhpur (`off_topic_other_place`).
- hotels.csv: Rock Stone (MSR06) set `in_cluster = N` (2-star, ~INR 1,100/night, thin recent data);
  its TripAdvisor listing was a different property, so that mapping was removed.
- New `tripadvisor_hotel_scores.csv`: hotel-level TripAdvisor scores for 7 hotels; `usable_for_benchmark = Y` only with 30+ reviews.

## v6 — audit fixes
- MakeMyTrip reviewer_hash is name-based, so different people with the same name share a hash (e.g. 4 reviews by
  "Manoj Kumar" across 2 hotels), and all 7 anonymous reviewers shared one hash. Anonymous hashes cleared; new
  `reviewer_id_type` (platform_id / name_only / none). Use only `platform_id` hashes for same-reviewer or spam analysis.
- New `review_edited_likely`: 9 Google reviews have an owner reply dated before the review, meaning the review was
  edited later and `review_date` is the edit date.
- 5 contentless texts ("3", "5", "Wo", "NYC") set to has_text = False, quality_flag = no_content.
- sub_ratings_v6.csv identical to v5.

## Final — reproducible pipeline (clean_reviews.py)
- `clean_reviews.py` now builds the final files directly from the raw JSON plus `hotels.csv`;
  output is identical to v6 except MakeMyTrip `reviewer_hash`, which is now a hash of the reviewer name only
  (previously the whole reviewer record as text).
- Optional `REVIEWER_HASH_SALT` environment variable salts reviewer hashes; keep the salt secret and share it
  only within the team so everyone gets the same hashes.
- Stable output names in data/current/: reviews.csv, sub_ratings.csv, tripadvisor_hotel_scores.csv (hotels.csv is maintained by hand).

## TripAdvisor reviews added
- New input: data/raw/tripadvisor_reviews_20261013.json (TripAdvisor reviews actor, 7 cluster hotels, max 200 each,
  newest first, all languages; 833 reviews, 0 machine-translated). 1,807 per-review sub-ratings added
  (value, rooms, location, cleanliness, service, sleep_quality).
- Review IDs use TripAdvisor's own IDs (rev_ta_<id>), so they are stable across re-runs.
- 13 TripAdvisor reviews that Google also displays were removed from the Google rows; the native TripAdvisor record is kept.
  Matching ignores punctuation (Google joins paragraphs with "|"). One remains: a Rock Stone review (excluded hotel, no TripAdvisor mapping).
- 3 more cross-posts found (same guest posting on Google and TripAdvisor); kept and flagged.
- Language tagger: Hinglish now also needs at least 5% Hindi words, so long English reviews quoting a Hindi phrase stay "en"
  (4 TripAdvisor reviews). Non-English reviews in other languages are tagged "other" when the platform says so and
  the text has few common English words (1 German Google review). A TripAdvisor review labelled "fr" is actually English and stays "en".

## Booking.com reviews added
- New input: data/raw/booking_reviews_20261013.json (piotrv1001/booking-reviews-scraper; 5 hotels listed on Booking,
  all reviews, newest first, all languages, score-only reviews kept). 577 reviews; Booking only shows the last 36 months.
- Not listed on Booking.com: Sun N Snow, Crystal Palace. Perfectstayz is listed as "Super Hotel by Perfectstayz Mall Road".
- hotels.csv: new column booking_id.
- Scores run 1-10; rating_5 = 1 + (score - 1) * 4/9, so 1 -> 1 and 10 -> 5 (keeps rating_5 in the same 1-5 range as other platforms).
- Liked / disliked text kept as text_positive / text_negative; `text` combines them as "Liked: ... / Disliked: ...".
  Caution: guests sometimes put complaints under "liked" and praise under "disliked", so these are noisy labels.
- New columns: stay_nights, stay_status (45 reviews are from guests who did not stay, e.g. cancelled bookings),
  reviewer_country. Booking provides no reviewer ID, so reviewer_hash is empty.
- 281 reviews (49%) are score-only. Language code "xu" (undetermined) is treated as unknown; 12 reviews in
  French, Italian, Hebrew, Hungarian and German are tagged "other".

## Agoda reviews added
- New input: data/raw/agoda_reviews_20261013.json (blackfalcondata/agoda-reviews-scraper; source = Agoda only,
  most recent first, max 500 per hotel). 372 reviews returned for 7 hotels, fewer than the review counts shown on
  Agoda (see dataset card: likely only reviews with written text are returned; to be confirmed).
- hotels.csv: new column agoda_id.
- Only provider = Agoda is kept (Agoda also shows Booking.com / Priceline reviews, which would duplicate other sources).
- Scores out of 10, mapped like Booking (1 -> 1, 10 -> 5). Agoda timestamps (+07:00) converted to India time before taking dates.
- 2 reviews were machine-translated from French/German with no original text: kept as rating + text_translated_platform only.
- 1 exact duplicate within Agoda removed (same hotel, date, rating and text under two review IDs).
- Correction: Agoda listing 56389887 ("PerfectStayz Mall Road Mussoorie") is a different Perfectstayz property.
  Its 16 reviews are skipped via IGNORED_LISTINGS in clean_reviews.py (raw file left unedited); MSR05 has no Agoda data
  until the correct listing is found. Agoda now: 355 reviews for 6 hotels.
- Decision: the correct Perfectstayz Agoda listing (~80 Agoda reviews) was found but not scraped; Perfectstayz is
  covered by Google, MakeMyTrip, TripAdvisor and Booking.com.

## Multilingual evaluation set
- 15 keyword-filtered Google review runs (hai, nahi, nhi, bahut, bhut, bohot, acha, accha, achha, khana, kharab, bekar,
  होटल, अच्छा + the Vishnu test) in data/raw/eval/: 152 results, 85 unique reviews, 73 Hindi/Hinglish.
- build_eval_set.py merges them with the 21 Hindi/Hinglish reviews from the main dataset that the keywords did not find,
  plus an English sample (33 per rating band: negative / mixed / positive, seed 42) -> data/eval/eval_reviews.csv
  (193 reviews: 99 en, 71 hinglish, 19 hi, 4 hi_mixed). Kept separate from benchmark data (keyword sample is biased).
- Language tagger: very short reviews (<= 5 words) with one clear Hindi word are now Hinglish ("Bahut shandar").
  No change to any main-dataset tag. Tagger vs Google's own language label on the 85 keyword reviews: they agree on
  75; in 7 of the others Google says "en" for clearly code-mixed text (e.g. "Mast hotel hai good food").
