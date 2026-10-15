"""Release check against guests' own per-aspect sub-ratings, the one signal no model or LLM teacher has seen.

    python -m doonview_ml.subrating --data ../data --current ../backend/clusters/mussoorie.json \
        --candidate ../.claude/clusters-new/mussoorie.json

pick.py scores complaint F1 against the LLM teacher, so a model that copies a cautious teacher scores well while
missing real complaints. Google and TripAdvisor guests also rate rooms, service, location, value and cleanliness.
"Catch" is the share of reviews whose guest rated an aspect 1-2 that the model labels as a complaint about it;
"false alarm" is the share rated 5 that it still calls a complaint. Both are proxies (a guest can rate value 2 and
never write about it), so models are compared on the same reviews, never judged on the absolute number.

Exit code 1 when the candidate catches clearly fewer complaints than the current model on any aspect with enough
low-rated reviews, or raises clearly more false alarms. "Clearly" means past the tolerance AND, because both models
label the same reviews, unlikely to be chance on the reviews where they disagree (a one-sided exact McNemar test).
Angry guests often rate every category 1, so most low-rated reviews never mention the aspect: a 3-review swing out
of 47 moves the catch rate 6 points and is noise.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

CATEGORY_TO_ASPECT = {"value": "value", "rooms": "amenities", "location": "location", "cleanliness": "cleanliness",
                      "service": "host"}
MIN_LOW_RATED = 30        # aspects with fewer low-rated reviews are reported, not judged
CATCH_TOLERANCE = 0.05    # the candidate may catch at most 5 points fewer
ALARM_TOLERANCE = 0.02    # and raise at most 2 points more false alarms
ALPHA = 0.05              # a catch drop past the tolerance must also be this unlikely by chance


def norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def load_subratings(sub_ratings_csv: Path, reviews_csv: Path) -> dict[str, dict[str, float]]:
    """Normalised review text -> {aspect: guest score 1-5}."""
    scores = defaultdict(dict)
    with open(sub_ratings_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["platform_category"] in CATEGORY_TO_ASPECT and r["score"]:
                scores[r["review_id"]][CATEGORY_TO_ASPECT[r["platform_category"]]] = float(r["score"])
    out = {}
    with open(reviews_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["review_id"] in scores and r.get("text"):
                out[norm(r["text"])] = scores[r["review_id"]]
    return out


def labels(cluster_json: Path) -> dict[str, dict]:
    with open(cluster_json, encoding="utf-8") as f:
        return {norm(r["text"]): r.get("aspects") or {} for r in json.load(f)["reviews"]}


def grade(subs: dict, model: dict, keys: list[str]) -> dict[str, dict]:
    out = {}
    for aspect in sorted(set(CATEGORY_TO_ASPECT.values())):
        low = [k for k in keys if subs[k].get(aspect, 9) <= 2]
        top = [k for k in keys if subs[k].get(aspect) == 5]
        neg = lambda k: model[k].get(aspect) == "negative"
        out[aspect] = {"low_rated": len(low), "catch": sum(map(neg, low)) / len(low) if low else None,
                       "top_rated": len(top), "false_alarm": sum(map(neg, top)) / len(top) if top else None}
    return out


def disagreements(subs: dict, current: dict, candidate: dict, keys: list[str]) -> dict[str, tuple[int, int]]:
    """Per aspect, among low-rated reviews: (caught only by the current model, caught only by the candidate)."""
    out = {}
    for aspect in sorted(set(CATEGORY_TO_ASPECT.values())):
        low = [k for k in keys if subs[k].get(aspect, 9) <= 2]
        cur = [current[k].get(aspect) == "negative" for k in low]
        new = [candidate[k].get(aspect) == "negative" for k in low]
        out[aspect] = (sum(c and not n for c, n in zip(cur, new)), sum(n and not c for c, n in zip(cur, new)))
    return out


def drop_p(only_current: int, only_candidate: int) -> float:
    """One-sided exact McNemar p: the chance of at least this many current-only catches if both models were equal."""
    n = only_current + only_candidate
    return sum(comb(n, i) for i in range(only_current, n + 1)) / 2 ** n if n else 1.0


def compare(current: dict, candidate: dict, pairs: dict[str, tuple[int, int]]) -> list[str]:
    problems = []
    for aspect, cur in current.items():
        new = candidate[aspect]
        if cur["low_rated"] >= MIN_LOW_RATED and new["catch"] < cur["catch"] - CATCH_TOLERANCE \
                and (p := drop_p(*pairs[aspect])) < ALPHA:
            problems.append(f"{aspect}: catches {new['catch']:.0%} of low-rated reviews, current model "
                            f"{cur['catch']:.0%} (p={p:.3f})")
        if cur["top_rated"] and new["false_alarm"] > cur["false_alarm"] + ALARM_TOLERANCE:
            problems.append(f"{aspect}: false alarms {new['false_alarm']:.1%}, current model {cur['false_alarm']:.1%}")
    return problems


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", type=Path, required=True, help="folder with sub_ratings.csv and reviews.csv")
    p.add_argument("--current", type=Path, required=True, help="cluster JSON labelled by the app's model")
    p.add_argument("--candidate", type=Path, required=True, help="the same reviews labelled by the new model")
    args = p.parse_args()
    subs = load_subratings(args.data / "sub_ratings.csv", args.data / "reviews.csv")
    cur_labels, new_labels = labels(args.current), labels(args.candidate)
    keys = [k for k in subs if k in cur_labels and k in new_labels]
    cur, new = grade(subs, cur_labels, keys), grade(subs, new_labels, keys)
    pairs = disagreements(subs, cur_labels, new_labels, keys)
    print(f"{len(keys)} reviews with guest sub-ratings, labelled by both models")
    print(f"{'aspect':12s} {'low-rated':>9s}  {'catch: current / new':>21s}  {'only current / only new':>24s}  "
          f"{'false alarm: current / new':>27s}")
    for a in cur:
        c, n = cur[a], new[a]
        fmt = lambda v, p=".0%": "n/a" if v is None else format(v, p)
        print(f"{a:12s} {c['low_rated']:9d}  {fmt(c['catch']):>10s} / {fmt(n['catch']):<8s}  "
              f"{pairs[a][0]:>12d} / {pairs[a][1]:<9d}  {fmt(c['false_alarm'], '.1%'):>14s} / {fmt(n['false_alarm'], '.1%')}")
    problems = compare(cur, new, pairs)
    for a, c in cur.items():
        if c["low_rated"] >= MIN_LOW_RATED and new[a]["catch"] < c["catch"] - CATCH_TOLERANCE \
                and not any(x.startswith(f"{a}:") for x in problems):
            print(f"note: {a} catches fewer, but {pairs[a][0]} vs {pairs[a][1]} disagreements is within chance "
                  f"(p={drop_p(*pairs[a]):.2f}); read those reviews before shipping")
    print("\nVERDICT: " + ("keep the current model\n  " + "\n  ".join(problems) if problems else
                           "the candidate catches at least as many complaints, without more false alarms"))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
