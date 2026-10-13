"""Cluster benchmarking: the statistics behave, verdicts respect uncertainty, and the endpoints can't be used to
read files outside the cluster folder."""
import json

import pytest
from fastapi.testclient import TestClient

from app import cluster as C
from app.main import app

client = TestClient(app)


def _review(pid, month, aspects, text="The room was clean and the staff were friendly."):
    return {"property_id": pid, "month": month, "sentiment": "positive", "is_spam": False, "aspects": aspects,
            "text": text, "confidence": 0.9}


@pytest.fixture
def cluster_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTER_DIR", str(tmp_path))
    reviews = []
    # "good": food praised 40 times; "bad": food criticised 30 of 40 times; "tiny": 4 food mentions, all bad
    for i in range(40):
        reviews.append(_review("good", f"2025-{i % 12 + 1:02d}", {"food": "positive", "location": "negative"}))
        reviews.append(_review("bad", f"2025-{i % 12 + 1:02d}",
                               {"food": "negative" if i < 30 else "positive", "location": "negative"},
                               text="The breakfast was cold and not fresh at all."))
        reviews.append(_review("mid", f"2025-{i % 12 + 1:02d}", {"food": "positive" if i % 2 else "negative",
                                                                    "location": "negative"}))
    for i in range(4):
        reviews.append(_review("tiny", "2025-06", {"food": "negative"}))
    reviews.append({**_review("good", "2025-01", {"food": "negative"}), "is_spam": True})  # spam never counts
    # Old reviews, outside the default window: "good" used to be bad at food
    reviews += [_review("good", "2019-05", {"food": "negative"}) for _ in range(30)]
    reviews.append(_review("good", None, {"food": "negative"}))  # undated: only counted for all time
    (tmp_path / "town.json").write_text(json.dumps({
        "slug": "town", "name": "Test town", "source": "unit test",
        "properties": {"good": "Good Stay", "bad": "Bad Stay", "mid": "Mid Stay", "tiny": "Tiny Stay"},
        "reviews": reviews}))
    C._load.cache_clear()
    return tmp_path


def test_wilson_interval():
    assert C.wilson(0, 0) == (0.0, 1.0)
    low, high = C.wilson(8, 10)
    assert 0.49 < low < 0.5 and 0.94 < high < 0.95  # textbook values for 8/10
    assert C.wilson(10, 10)[1] == pytest.approx(1.0)


def test_turning_point_found_only_when_real():
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    flat = C.turning_point(months, [2] * 12, [10] * 12)
    assert flat is None
    jump = C.turning_point(months, [1] * 6 + [7] * 6, [10] * 6 + [10] * 6)
    assert jump == {"month": "2025-07", "complaints_before": 0.1, "complaints_after": 0.7, "direction": "worse"}
    assert C.turning_point(months[:4], [0, 0, 5, 5], [5] * 4) is None  # too short to split


def test_benchmark_verdicts_respect_uncertainty(cluster_dir):
    c = C.window(C.load_cluster("town"), "2025-01", None)
    food = lambda pid: next(r for r in C.benchmark(c, pid)["aspects"] if r["aspect"] == "food")  # noqa: E731
    assert food("good")["verdict"] == "leads"
    assert food("bad")["verdict"] == "lags"
    assert food("bad")["complaint_quotes"] == ["The breakfast was cold and not fresh at all."]
    assert food("tiny")["verdict"] == "too_few"  # 4 of 4 bad, but 4 is too few to call
    assert C.benchmark(c, "nobody") is None


def test_shared_issue_is_one_everyone_has(cluster_dir):
    view = C.destination_view(C.window(C.load_cluster("town"), "2025-01", None))
    by = {a["aspect"]: a for a in view["aspects"]}
    assert by["location"]["shared_issue"] is True     # every property gets the same complaint
    assert by["food"]["shared_issue"] is False         # properties clearly differ on food
    assert view["reviews"] == 124                      # the spam review is left out
    assert view["aspects"][0]["aspect"] == "location"  # most complaints first


def test_recent_reviews_by_default_and_any_window_on_request(cluster_dir):
    food = lambda body: next(a for a in body["aspects"] if a["aspect"] == "food")  # noqa: E731
    recent = client.get("/api/clusters/town/properties/good").json()
    assert recent["window"] == {"since": "2025-01", "until": None}
    assert food(recent)["verdict"] == "leads" and food(recent)["mentions"] == 40
    all_time = client.get("/api/clusters/town/properties/good?since=").json()
    assert all_time["window"]["since"] is None and food(all_time)["mentions"] == 71   # 40 + 30 old + 1 undated
    assert client.get("/api/clusters/town?since=2019-01&until=2019-12").json()["reviews"] == 30
    assert client.get("/api/clusters/town?since=2030-01").json()["reviews"] == 0       # empty window still answers
    assert client.get("/api/clusters/town?since=2025-13").status_code == 422
    assert client.get("/api/clusters/town?until=last-year").status_code == 422


def test_demo_data_is_flagged_in_every_view(cluster_dir):
    path = cluster_dir / "town.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "demo": True}))
    C._load.cache_clear()
    assert client.get("/api/clusters").json()[0]["demo"] is True
    assert client.get("/api/clusters/town").json()["demo"] is True
    assert client.get("/api/clusters/town/properties/good").json()["demo"] is True


def test_real_data_is_not_flagged(cluster_dir):
    assert client.get("/api/clusters/town").json()["demo"] is False


def test_endpoints(cluster_dir):
    listed = client.get("/api/clusters").json()
    assert [c["slug"] for c in listed] == ["town"] and listed[0]["properties"] == 4
    assert client.get("/api/clusters/town").json()["name"] == "Test town"
    assert client.get("/api/clusters/town/properties/bad").json()["property"]["name"] == "Bad Stay"
    assert client.get("/api/clusters/nope").status_code == 404
    assert client.get("/api/clusters/town/properties/nope").status_code == 404


@pytest.mark.parametrize("slug", ["..%2F..%2Fapp%2Fdata", "..", "Town", "a" * 80, "%2e%2e"])
def test_slug_cannot_leave_the_cluster_folder(cluster_dir, slug):
    assert client.get(f"/api/clusters/{slug}").status_code == 404
    assert C.load_cluster("../town") is None
