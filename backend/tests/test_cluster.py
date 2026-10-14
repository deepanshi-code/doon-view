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


def _rated(pid, aspects, stars, platform="google"):
    return {**_review(pid, "2025-03", aspects), "rating": str(stars), "platform": platform}


def test_star_costs_recover_the_true_effects_and_hold_platform_apart():
    # Built so stars = 4.8 - 1.5*(wifi complaint) - 0.5*(food complaint), with Booking.com a flat 0.4 lower.
    # Every combination appears, so the fit must recover 1.5 and 0.5 exactly (and not blame the platform gap on food).
    reviews = []
    for i in range(240):
        wifi, food, booking = i % 2 == 0, i % 3 == 0, i % 5 == 0
        aspects = {"wifi": "negative" if wifi else "positive", "food": "negative" if food else "positive"}
        stars = 4.8 - 1.5 * wifi - 0.5 * food - 0.4 * booking
        reviews.append(_rated("h", aspects, stars, "booking" if booking else "google"))
    c = C.Cluster("t", "T", "hotels", "", {"h": "H"}, tuple(
        C.Review(r["property_id"], r["month"], "positive", r["aspects"], "", None, r["platform"], C._rating(r["rating"]))
        for r in reviews), aspects=("wifi", "food"))
    costs = C.star_costs(c)
    assert costs["wifi"]["cost"] == pytest.approx(1.5, abs=1e-6)
    assert costs["food"]["cost"] == pytest.approx(0.5, abs=1e-6)
    assert C._rating("4.5") == 4.5 and C._rating("") is None and C._rating("9") is None and C._rating(None) is None


def test_impact_ranks_only_aspects_where_the_property_complains_more(tmp_path, monkeypatch):
    monkeypatch.setenv("CLUSTER_DIR", str(tmp_path))
    reviews = []
    for pid, wifi_bad, food_bad in (("worse", 30, 10), ("a", 6, 10), ("b", 6, 10)):
        for i in range(60):
            aspects = {"wifi": "negative" if i < wifi_bad else "positive", "food": "negative" if i < food_bad else "positive"}
            reviews.append(_rated(pid, aspects, 4.8 - 1.0 * (i < wifi_bad) - 0.3 * (i < food_bad) - 0.01 * (i % 7)))
    (tmp_path / "t.json").write_text(json.dumps({"slug": "t", "name": "T", "source": "unit test",
                                                 "properties": {"worse": "W", "a": "A", "b": "B"}, "reviews": reviews}))
    C._load.cache_clear()
    out = client.get("/api/clusters/t/properties/worse?since=").json()["impact"]
    assert [r["aspect"] for r in out["aspects"]] == ["wifi"]          # food: no more complaints than the market
    wifi = out["aspects"][0]
    gap = 30 / 60 - 6 / 60
    assert wifi["gain"] == pytest.approx(gap * wifi["stars_per_complaint"], abs=1e-3)
    assert wifi["stars_per_complaint"] == pytest.approx(1.0, abs=0.02)
    assert out["rating"] < out["market_rating"]
    assert client.get("/api/clusters/t/properties/a?since=").json()["impact"]["aspects"] == []


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


def test_market_grid_ranks_properties_and_matches_the_benchmark(cluster_dir):
    grid = client.get("/api/clusters/town/grid").json()
    names = [p["id"] for p in grid["properties"]]
    assert names[0] == "good" and names.index("bad") > names.index("mid")   # most led-minus-lagged first
    assert grid["shared_issues"] == ["location"]
    good = next(p for p in grid["properties"] if p["id"] == "good")
    bench = client.get("/api/clusters/town/properties/good").json()
    assert good["cells"]["food"]["verdict"] == "leads" == next(a for a in bench["aspects"] if a["aspect"] == "food")["verdict"]
    assert good["sources"] == {} and bench["property"]["sources"] == {}       # the fixture has no platforms
    assert client.get("/api/clusters/nowhere/grid").status_code == 404


def test_only_aspects_the_labeller_covers_are_shown(cluster_dir):
    """Regression: a model without the booking aspect showed a 0-mention Booking row with a 0-100% range."""
    shown = lambda body: {a["aspect"] for a in body["aspects"]}  # noqa: E731
    assert shown(client.get("/api/clusters/town").json()) == {"food", "location"}
    assert shown(client.get("/api/clusters/town/properties/good").json()) == {"food", "location"}
    # an empty window keeps the cluster's aspects (with zeros), it doesn't drop them
    assert shown(client.get("/api/clusters/town?since=2030-01").json()) == {"food", "location"}
    assert client.get("/api/clusters/town").json()["label_sources"] == {}


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
