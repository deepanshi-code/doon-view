"""Guarantees the reported numbers depend on: honest folds, the right labels, and evaluation that counts correctly."""
import numpy as np
import pandas as pd
import pytest

from doonview_ml.data import build
from doonview_ml.evaluate import aspect_report, sentiment_report
from doonview_ml.labels import ASPECTS, rating_to_polarity, rating_to_sentiment
from doonview_ml.train import IGNORE, targets


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


def test_sentiment_report_counts_classes_and_interval_contains_the_score():
    gold = np.array(["positive"] * 8 + ["negative"] * 2)
    pred = np.array(["positive"] * 7 + ["negative"] * 3)
    r = sentiment_report(gold, pred)
    assert r["per_class"]["negative"]["recall"] == 1.0 and r["per_class"]["positive"]["recall"] == 7 / 8
    assert r["ci95"][0] <= r["macro_f1"] <= r["ci95"][1]
