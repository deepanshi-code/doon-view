"""The two release gates: int8 must keep fp32's complaints, and a new model must catch what guests complained about."""
import csv
import json

from doonview_ml import parity, pick, subrating


def _cand(sentiment, f1, catch, alarm=0.0, low=60):
    return {"sentiment": {"macro_f1": sentiment},
            "aspects": {"negative_f1_vs_teacher": {"amenities": f1},
                        "complaints_vs_guests": {"amenities": {"low_rated": low, "catch": catch,
                                                               "top_rated": 500, "false_alarm": alarm}}}}


def test_pick_never_ships_a_model_that_misses_guest_rated_complaints():
    # The deberta-v3-base case: better against the teacher, far fewer complaints the guests rated 1-2
    metrics = {"cv cv-improve-deberta-v3-base-s13": _cand(0.85, 0.90, catch=0.19),
               "current model (x)": _cand(0.79, 0.70, catch=0.49)}
    out = pick.choose(metrics, "improve-")
    assert out["ships"] is False
    assert out["verdict"].startswith("keep the current model: amenities: catches 19%")


def test_pick_prefers_the_candidate_that_passes_the_guest_check():
    metrics = {"cv cv-improve-deberta-v3-base-s13": _cand(0.86, 0.95, catch=0.20),
               "cv cv-improve-deberta-v3-xsmall-s13": _cand(0.82, 0.75, catch=0.55),
               "current model (x)": _cand(0.79, 0.70, catch=0.49)}
    out = pick.choose(metrics, "improve-")
    assert out["best"]["run"] == "cv-improve-deberta-v3-xsmall-s13" and out["ships"] is True


def test_pick_blocks_more_false_alarms_and_ignores_thin_aspects():
    noisy = {"cv cv-improve-deberta-v3-base-s13": _cand(0.85, 0.9, catch=0.6, alarm=0.05),
             "current model (x)": _cand(0.79, 0.7, catch=0.49, alarm=0.001)}
    assert pick.choose(noisy, "improve-")["ships"] is False
    thin = {"cv cv-improve-deberta-v3-base-s13": _cand(0.85, 0.9, catch=0.0, low=10),
            "current model (x)": _cand(0.79, 0.7, catch=0.49, low=10)}
    assert pick.choose(thin, "improve-")["ships"] is True       # 10 guest ratings are too few to judge


def test_parity_keeps_all_complaints():
    ref = [{"food": "negative"}] * 25
    assert parity.failing(parity.complaint_recall(ref, ref, ["food"])) == []


def test_parity_fails_when_int8_drops_complaints():
    # The base-model failure: fp32 flags 25 food complaints, int8 keeps 10 of them
    ref = [{"food": "negative"}] * 25
    got = [{"food": "negative"}] * 10 + [{"food": "not_mentioned"}] * 15
    recalls = parity.complaint_recall(ref, got, ["food"])
    assert recalls["food"] == {"fp32_complaints": 25, "recall": 0.4}
    assert parity.failing(recalls) == ["food"]


def test_parity_does_not_judge_rare_aspects():
    ref = [{"wifi": "negative"}] * 3
    got = [{"wifi": "positive"}] * 3
    assert parity.failing(parity.complaint_recall(ref, got, ["wifi"])) == []


def _files(tmp_path, low_rated: int, candidate_catches: int):
    """low_rated reviews whose guest rated value 1, and 40 rated value 5; the current model flags every low one."""
    with open(tmp_path / "sub_ratings.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "hotel_id", "platform_category", "score"])
        for i in range(low_rated):
            w.writerow([f"l{i}", "MSR01", "value", 1])
        for i in range(40):
            w.writerow([f"t{i}", "MSR01", "value", 5])
    with open(tmp_path / "reviews.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "text"])
        for i in range(low_rated):
            w.writerow([f"l{i}", f"Way  too expensive {i}"])
        for i in range(40):
            w.writerow([f"t{i}", f"Great value {i}"])
    def cluster(name, catches):
        rows = [{"text": f"way too expensive {i}", "aspects": {"value": "negative" if i < catches else "positive"}}
                for i in range(low_rated)]
        rows += [{"text": f"great value {i}", "aspects": {"value": "positive"}} for i in range(40)]
        (tmp_path / name).write_text(json.dumps({"reviews": rows}), encoding="utf-8")
    cluster("current.json", low_rated)
    cluster("candidate.json", candidate_catches)
    subs = subrating.load_subratings(tmp_path / "sub_ratings.csv", tmp_path / "reviews.csv")
    cur, new = subrating.labels(tmp_path / "current.json"), subrating.labels(tmp_path / "candidate.json")
    keys = [k for k in subs if k in cur and k in new]
    return (subrating.grade(subs, cur, keys), subrating.grade(subs, new, keys),
            subrating.disagreements(subs, cur, new, keys))


def test_subrating_matches_text_despite_spacing_and_case(tmp_path):
    cur, _, _ = _files(tmp_path, 40, 40)
    assert cur["value"]["low_rated"] == 40 and cur["value"]["catch"] == 1.0 and cur["value"]["false_alarm"] == 0.0


def test_subrating_rejects_a_model_that_misses_complaints(tmp_path):
    cur, new, pairs = _files(tmp_path, 40, 20)
    assert pairs["value"] == (20, 0)
    assert subrating.compare(cur, new, pairs) == ["value: catches 50% of low-rated reviews, current model 100% (p=0.000)"]


def test_subrating_accepts_an_equal_model(tmp_path):
    cur, new, pairs = _files(tmp_path, 40, 39)   # within the 5-point tolerance
    assert subrating.compare(cur, new, pairs) == []


def test_subrating_accepts_a_drop_that_could_be_chance(tmp_path):
    cur, new, pairs = _files(tmp_path, 47, 44)   # 6 points fewer, but only 3 reviews: p = 0.125
    assert new["value"]["catch"] < cur["value"]["catch"] - subrating.CATCH_TOLERANCE
    assert subrating.compare(cur, new, pairs) == []


def test_subrating_rejects_a_drop_that_is_not_chance(tmp_path):
    cur, new, pairs = _files(tmp_path, 47, 42)   # 5 current-only catches, none the other way: p = 0.031
    assert subrating.compare(cur, new, pairs) != []


def test_drop_p_is_symmetric_at_a_tie():
    assert subrating.drop_p(0, 0) == 1.0 and subrating.drop_p(2, 2) == 11 / 16


def test_subrating_does_not_judge_thin_aspects(tmp_path):
    cur, new, pairs = _files(tmp_path, 10, 0)    # under MIN_LOW_RATED
    assert subrating.compare(cur, new, pairs) == []
