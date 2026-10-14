"""Guarantees the reported numbers depend on: honest folds, the right labels, and evaluation that counts correctly."""
import numpy as np
import pandas as pd
import pytest

from doonview_ml import external, pick
from doonview_ml.data import build
from doonview_ml.evaluate import aspect_report, sentiment_report
from doonview_ml.labels import ASPECTS, rating_to_polarity, rating_to_sentiment
from doonview_ml.train import IGNORE, targets, training_set


@pytest.fixture
def csv(tmp_path):
    rows = []
    for i in range(120):
        rows.append({"review_id": f"r{i}", "hotel_id": "MSR01", "canonical_name": "Hotel", "platform": "google",
                     "review_date": "2025-06-01", "language": "en", "rating_5": [5, 4, 3, 2, 1][i % 5],
                     "title": None, "text": f"Review number {i} about the room and the staff.", "has_text": True,
                     "quality_flag": None, "reviewer_id_type": "platform_id", "reviewer_hash": f"u{i // 2}",
                     "cross_post_group": None})
    rows[0]["cross_post_group"] = rows[7]["cross_post_group"] = "CP001"       # the same review on two platforms
    rows[3] |= {"platform": "makemytrip", "title": "Great stay", "text": "Lovely room."}
    rows[4] |= {"title": "Nice", "text": "Nice place to stay."}               # body repeats the title
    rows[5] |= {"quality_flag": "off_topic_other_place"}
    rows[6] |= {"has_text": False, "text": None}
    path = tmp_path / "reviews.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_rating_mappings():
    assert [rating_to_sentiment(s) for s in (1, 2, 3, 4, 5)] == ["negative"] * 2 + ["neutral"] + ["positive"] * 2
    assert [rating_to_polarity(s) for s in (1, 3, 5, None, float("nan"))] == ["negative", None, "positive", None, None]


def test_build_filters_merges_titles_and_never_splits_a_group(csv):
    df = build(csv, None, folds=5, seed=13)
    assert len(df) == 118                                                     # flagged and text-less rows dropped
    text = df.set_index("review_id")["text"]
    assert text["r3"] == "Great stay. Lovely room." and text["r4"] == "Nice place to stay."
    assert df.groupby("group")["fold"].nunique().max() == 1                  # cross-posts and accounts stay together
    assert df.set_index("review_id").loc[["r0", "r7"], "fold"].nunique() == 1
    assert set(df["fold"]) == set(range(5))


def test_targets_mark_unlabelled_aspects_ignored():
    df = pd.DataFrame({"review_id": ["a", "b"], "sentiment": ["positive", "negative"]})
    y = targets(df, {"a": {"is_spam": False, "aspects": {"food": "negative"}, "judged": list(ASPECTS)}})
    assert y["aspects"][0, ASPECTS.index("food")] == 1 and y["aspects"][0, ASPECTS.index("wifi")] == 2
    assert (y["aspects"][1] == IGNORE).all()                                 # no teacher label: no aspect target


def test_subrating_check_ignores_reviews_without_a_subrating():
    """Regression: NaN is truthy, and once counted every review without a sub-rating as a miss."""
    df = pd.DataFrame({"review_id": list("abcd"), "sub_location": [5.0, np.nan, 1.0, 3.0]})
    report = aspect_report(df, {"location": ["positive", "positive", "negative", "positive"]}, {})
    assert report["vs_subratings"]["location"] == {"polarity_accuracy": 1.0, "n": 2}


def _raw_tripadvisor(n_per_star=200):
    rows, i = [], 0
    for stars in (1, 2, 3, 4, 5):
        for _ in range(n_per_star):
            rows.append({"hotel_id": i, "user_id": f"u{i}", "overall": float(stars),
                         "review": f"Review {i}: the room was fine and the staff were helpful during our stay."})
            i += 1
    rows += [{"hotel_id": 9001, "user_id": "short", "overall": 1.0, "review": "Bad."},             # too short
             {"hotel_id": 9002, "user_id": "long", "overall": 1.0, "review": "word " * 401},       # too long
             {"hotel_id": 9003, "user_id": "u0", "overall": 1.0, "review": "Same author again, a whole new review."},
             {"hotel_id": 9004, "user_id": "dup", "overall": 5.0, "review": rows[5]["review"].upper()}]  # duplicate
    return pd.DataFrame(rows)


def test_outside_sample_favours_complaints_and_is_never_scored():
    df = external.build(_raw_tripadvisor(), rows=300, seed=13)
    assert df["sentiment"].value_counts().to_dict() == {"positive": 150, "negative": 90, "neutral": 60}
    assert (df["fold"] == -1).all() and df["review_id"].str.startswith("ta-").all()
    assert not df["review_id"].isin(["ta-9001", "ta-9002", "ta-9003", "ta-9004"]).any()
    assert df["group"].is_unique and df["text"].str.lower().is_unique
    bigger = external.build(_raw_tripadvisor(), rows=500, seed=13, keep=df)   # top-up: labelled rows are kept
    assert set(df["review_id"]) <= set(bigger["review_id"]) and len(bigger) == 500


def test_training_set_repeats_mussoorie_and_adds_outside_rows():
    local = pd.DataFrame({"review_id": ["a", "b"], "text": ["x", "y"], "sentiment": ["positive", "negative"], "fold": [0, 1]})
    outside = pd.DataFrame({"review_id": ["ta-1"], "text": ["z"], "sentiment": ["neutral"], "fold": [-1]})
    mixed = training_set(local, outside, repeat=3)
    assert mixed["review_id"].value_counts().to_dict() == {"a": 3, "b": 3, "ta-1": 1}
    assert list(training_set(local, None, repeat=3)["review_id"]) == ["a", "b"]   # no outside data: no repeats


def _row(sentiment, f1s):
    return {"sentiment": {"macro_f1": sentiment}, "aspects": {"negative_f1_vs_teacher": f1s}}


def test_pick_scores_shared_aspects_and_ships_only_a_model_better_on_both():
    metrics = {
        "cv cv-auto-deberta-v3-xsmall-s13": _row(0.84, {"food": 0.6, "wifi": 0.6, "booking": 0.1}),
        "cv cv-auto-deberta-v3-base-s13": _row(0.85, {"food": 0.8, "wifi": 0.8, "booking": 0.1}),
        "cv cv-deberta-v3-base-s13": _row(0.99, {"food": 0.99, "wifi": 0.99}),        # another run: not competing
        "current model (x)": _row(0.79, {"food": 0.7, "wifi": 0.7}),
    }
    out = pick.choose(metrics, "auto-")
    assert out["aspects"] == ["food", "wifi"]                       # booking: the current model can't be compared
    assert out["best"]["run"] == "cv-auto-deberta-v3-base-s13" and out["ships"] is True
    metrics["current model (x)"] = _row(0.79, {"food": 0.9, "wifi": 0.9})
    assert pick.choose(metrics, "auto-")["ships"] is False          # better sentiment, worse complaints: keep current


def test_sentiment_report_counts_classes_and_interval_contains_the_score():
    gold = np.array(["positive"] * 8 + ["negative"] * 2)
    pred = np.array(["positive"] * 7 + ["negative"] * 3)
    r = sentiment_report(gold, pred)
    assert r["per_class"]["negative"]["recall"] == 1.0 and r["per_class"]["positive"]["recall"] == 7 / 8
    assert r["ci95"][0] <= r["macro_f1"] <= r["ci95"][1]
