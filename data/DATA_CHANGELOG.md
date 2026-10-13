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
