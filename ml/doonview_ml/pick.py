"""Pick the model to ship from a cross-validation report, by a rule fixed before the run, and say whether it beats
the current app model.

    python -m doonview_ml.pick --report runs/report-auto/metrics.json --runs runs --tag auto \
        --out runs/selection-auto.json

Score = (sentiment macro-F1 + mean complaint F1 over the aspects the current model also has) / 2. Complaint F1 is the
F1 of the "negative" class per aspect against the teacher: every ahead/behind verdict in the app counts complaints,
and F1 punishes both missed complaints and false alarms.

Ships only if it beats the current model on BOTH sentiment and mean complaint F1, AND catches as many complaints as the
current model where guests rated an aspect 1-2 themselves (Google/TripAdvisor sub-ratings, which no model or teacher
has seen); otherwise the current model stays and the report says why. The teacher-based score alone once picked a
model that copied a cautious teacher and missed real complaints. One seed per candidate, so differences of ~0.01 are noise: stated in the output.
"""
import argparse
import json
from pathlib import Path

import numpy as np


def complaint_f1(row: dict, aspects: list[str]) -> float | None:
    f1s = (row.get("aspects") or {}).get("negative_f1_vs_teacher") or {}
    vals = [f1s[a] for a in aspects if f1s.get(a) is not None]
    return float(np.mean(vals)) if vals else None


GUEST_MIN_LOW_RATED = 30     # aspects with fewer guest 1-2 ratings are reported, not judged
GUEST_CATCH_TOLERANCE = 0.05  # a candidate may catch at most 5 points fewer guest-rated complaints
GUEST_ALARM_TOLERANCE = 0.02  # and raise at most 2 points more false alarms on aspects the guest rated 5


def guest_problems(new: dict | None, cur: dict | None) -> list[str]:
    """Where a candidate misses complaints the guests rated 1-2 (or flags ones they rated 5) clearly more than the
    current model. Empty when either side lacks guest data, so older reports are judged as before."""
    if not new or not cur:
        return []
    out = []
    for a, c in cur.items():
        n = new.get(a) or {}
        if c.get("low_rated", 0) >= GUEST_MIN_LOW_RATED and None not in (c.get("catch"), n.get("catch")) \
                and n["catch"] < c["catch"] - GUEST_CATCH_TOLERANCE:
            out.append(f"{a}: catches {n['catch']:.0%} of guest-rated complaints, current model {c['catch']:.0%}")
        if None not in (c.get("false_alarm"), n.get("false_alarm")) and n["false_alarm"] > c["false_alarm"] + GUEST_ALARM_TOLERANCE:
            out.append(f"{a}: false alarms {n['false_alarm']:.1%}, current model {c['false_alarm']:.1%}")
    return out


def _guests(row: dict | None) -> dict | None:
    return ((row or {}).get("aspects") or {}).get("complaints_vs_guests")


def choose(metrics: dict, prefix: str) -> dict:
    current = next((r for name, r in metrics.items() if name.startswith("current model")), None)
    candidates = {name: r for name, r in metrics.items() if name.startswith(f"cv cv-{prefix}")}
    if not candidates:
        raise SystemExit(f"no cross-validation runs named cv-{prefix}* in the report")
    shared = list(((current or {}).get("aspects") or {}).get("negative_f1_vs_teacher") or
                  next(iter(candidates.values()))["aspects"]["negative_f1_vs_teacher"])
    scored = []
    for name, r in candidates.items():
        c, s = complaint_f1(r, shared), r["sentiment"]["macro_f1"]
        scored.append({"run": name.removeprefix("cv "), "sentiment_f1": s, "complaint_f1": c,
                       "score": (s + (c or 0)) / 2, "guest_problems": guest_problems(_guests(r), _guests(current))})
    # A candidate that misses complaints the guests themselves rated low ranks below every one that doesn't,
    # whatever its score against the teacher (who may be the one missing them)
    scored.sort(key=lambda x: (bool(x["guest_problems"]), -x["score"]))
    best = scored[0]
    out = {"rule": "score = (sentiment F1 + mean complaint F1 on shared aspects) / 2, after the guest sub-rating check",
           "aspects": shared, "candidates": scored, "best": best}
    if current:
        cur = {"sentiment_f1": current["sentiment"]["macro_f1"], "complaint_f1": complaint_f1(current, shared)}
        out["current"] = cur
        better = bool(best["sentiment_f1"] > cur["sentiment_f1"] and best["complaint_f1"] is not None
                      and best["complaint_f1"] > cur["complaint_f1"])
        out["ships"] = better and not best["guest_problems"]
        out["verdict"] = ("ship it: better than the current model on sentiment and complaints, and catches as many "
                          "guest-rated complaints" if out["ships"] else
                          "keep the current model: " + ("; ".join(best["guest_problems"]) if best["guest_problems"] else
                                                        "the best new one is not better on both sentiment and complaints"))
    else:
        out["ships"], out["verdict"] = None, "no current model in the report: compare by hand before shipping"
    out["caveat"] = ("one seed per candidate: score differences under ~0.01 are within seed noise. Before switching "
                     "the app, also run doonview_ml.subrating on the rebuilt cluster (the int8 model, all reviews)")
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--report", type=Path, required=True, help="metrics.json written by doonview_ml.evaluate")
    p.add_argument("--runs", type=Path, default=Path("runs"))
    p.add_argument("--tag", default="", help="RUN_TAG: only cv-<tag>-* runs compete")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    result = choose(json.loads(args.report.read_text()), f"{args.tag}-" if args.tag else "")
    cv = json.loads((args.runs / result["best"]["run"] / "cv.json").read_text())
    result["best"].update({"backbone": cv["backbone"], "seed": cv["seed"], "epochs": cv["best_epochs"]})
    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
