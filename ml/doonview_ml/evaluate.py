"""Compare every candidate on the same 1,657 Mussoorie reviews, each scored on reviews it never trained on.

    python -m doonview_ml.evaluate --teacher data/processed/teacher/X.jsonl --cv runs/cv-* \
        [--compare-model path/to/current-model-dir] --out runs/report

Candidates:
  keyword rules          the app's last-resort fallback (no training)
  tf-idf                 logistic regression on word n-grams, same 5 folds
  teacher                the LLM's own sentiment, against the stars
  cv-<backbone>          out-of-fold predictions of each fine-tuned backbone
  current model          the general model the app uses now (trained on other hotels), if --compare-model is given

Sentiment is scored against the guests' stars, with a 95% bootstrap interval: with ~190 negative and ~90 neutral
reviews, differences under a few points are noise. Aspects are scored against the teacher (agreement, not accuracy)
and, for rooms, staff and location, against the guests' own Google sub-ratings (independent of every model).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, f1_score, precision_recall_fscore_support

from .labels import ASPECT_VALUES, ASPECTS, SENTIMENTS, rating_to_polarity
from .teacher import read_labels

BOOTSTRAP = 1000


def sentiment_report(gold: np.ndarray, pred: np.ndarray, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    f1 = f1_score(gold, pred, labels=list(SENTIMENTS), average="macro", zero_division=0)
    boots = []
    for _ in range(BOOTSTRAP):
        i = rng.integers(0, len(gold), len(gold))
        boots.append(f1_score(gold[i], pred[i], labels=list(SENTIMENTS), average="macro", zero_division=0))
    p, r, f, s = precision_recall_fscore_support(gold, pred, labels=list(SENTIMENTS), zero_division=0)
    return {"n": int(len(gold)), "macro_f1": float(f1), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "accuracy": float((gold == pred).mean()),
            "per_class": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(s[i])}
                          for i, c in enumerate(SENTIMENTS)},
            "confusion": confusion_matrix(gold, pred, labels=list(SENTIMENTS)).tolist()}


def aspect_report(df: pd.DataFrame, pred_aspects: dict[str, list[str]], teacher: dict) -> dict:
    """pred_aspects: aspect -> per-review value. Agreement with the teacher, and polarity vs the guest's sub-rating."""
    out = {"vs_teacher": {}, "negative_recall_vs_teacher": {}, "negative_f1_vs_teacher": {}, "vs_subratings": {}}
    for a, preds in pred_aspects.items():
        gold = [teacher.get(r, {}).get("aspects", {}).get(a, "not_mentioned") if r in teacher else None
                for r in df["review_id"]]
        pairs = [(g, p) for g, p in zip(gold, preds) if g is not None and p is not None]
        if pairs:
            g, p = zip(*pairs)
            out["vs_teacher"][a] = float(f1_score(g, p, labels=list(ASPECT_VALUES), average="macro", zero_division=0))
            neg = [pp == "negative" for gg, pp in pairs if gg == "negative"]
            out["negative_recall_vs_teacher"][a] = {"recall": float(np.mean(neg)) if neg else None, "support": len(neg)}
            # recall alone rewards flagging everything; F1 of the complaint class also counts false alarms
            out["negative_f1_vs_teacher"][a] = (float(f1_score(g, p, labels=["negative"], average="macro",
                                                               zero_division=0)) if neg else None)
        col = f"sub_{a}"
        if col in df:
            pol = df[col].map(rating_to_polarity)
            # isinstance, not truthiness: pandas turns "no polarity" into NaN, and NaN is truthy
            judged = [(want, got) for want, got in zip(pol, preds)
                      if isinstance(want, str) and got in ("positive", "negative")]
            if judged:
                out["vs_subratings"][a] = {"polarity_accuracy": float(np.mean([w == g for w, g in judged])),
                                           "n": len(judged)}
    scores = list(out["vs_teacher"].values())
    out["vs_teacher_mean"] = float(np.mean(scores)) if scores else None
    return out


def tfidf_oof(df: pd.DataFrame) -> np.ndarray:
    pred = np.empty(len(df), dtype=object)
    for k in sorted(df["fold"].unique()):
        test = df["fold"] == k
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        clf = LogisticRegression(max_iter=2000, class_weight="balanced")
        clf.fit(vec.fit_transform(df.loc[~test, "text"]), df.loc[~test, "sentiment"])
        pred[test.to_numpy()] = clf.predict(vec.transform(df.loc[test, "text"]))
    return pred


def keyword_rules(df: pd.DataFrame) -> np.ndarray:
    from app.labelling import _heuristic
    return np.array([_heuristic(t, "").sentiment for t in df["text"]])


def current_model(df: pd.DataFrame, model_dir: Path) -> tuple[np.ndarray, dict, str]:
    from app.classifier import OnnxClassifier  # backend is on sys.path (labels.py)
    model = OnnxClassifier(model_dir)
    results = model.predict(df["text"].tolist())
    aspects = {a: [r["aspects_all"].get(a) for r in results] for a in model.config["aspects"]}
    return np.array([r["sentiment"] for r in results]), aspects, model.name


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", type=Path, default=Path("data/processed"))
    p.add_argument("--teacher", type=Path, required=True)
    p.add_argument("--cv", type=Path, nargs="*", default=[], help="cv run directories (oof.npz + cv.json)")
    p.add_argument("--compare-model", type=Path, help="exported model dir of the current app model")
    p.add_argument("--out", type=Path, default=Path("runs/report"))
    args = p.parse_args()
    df = pd.read_parquet(args.data / "reviews.parquet")
    teacher = read_labels(args.teacher)
    gold = df["sentiment"].to_numpy()
    rows: dict[str, dict] = {}

    rows["keyword rules"] = {"sentiment": sentiment_report(gold, keyword_rules(df))}
    rows["tf-idf"] = {"sentiment": sentiment_report(gold, tfidf_oof(df))}
    labelled = df["review_id"].isin(teacher).to_numpy()
    t_sent = np.array([teacher[r]["sentiment"] for r in df.loc[labelled, "review_id"]])
    rows[f"teacher ({args.teacher.stem})"] = {"sentiment": sentiment_report(gold[labelled], t_sent),
                                              "note": f"{int(labelled.sum())} of {len(df)} reviews labelled"}
    for run in args.cv:
        oof = np.load(run / "oof.npz", allow_pickle=True)
        cv = json.loads((run / "cv.json").read_text())
        missing = set(df["review_id"]) - set(oof["review_id"])
        if missing:  # every candidate must be scored on the same reviews
            raise SystemExit(f"{run} has predictions for {len(oof['review_id'])} of {len(df)} reviews "
                             f"(a --limit smoke run?): re-run it on all reviews")
        order = pd.Series(range(len(oof["review_id"])), index=oof["review_id"])[df["review_id"]].to_numpy()
        sent = np.array(SENTIMENTS)[oof["sentiment"][order].argmax(-1)]
        asp = {a: list(np.array(ASPECT_VALUES)[oof["aspects"][order, j].argmax(-1)]) for j, a in enumerate(ASPECTS)}
        rows[f"cv {run.name}"] = {"sentiment": sentiment_report(gold, sent), "aspects": aspect_report(df, asp, teacher),
                                  "epochs": cv["best_epochs"]}
    if args.compare_model:
        sent, asp, name = current_model(df, args.compare_model)
        rows[f"current model ({name})"] = {"sentiment": sentiment_report(gold, sent),
                                           "aspects": aspect_report(df, asp, teacher),
                                           "note": "trained on other hotels' reviews; never saw these"}

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "metrics.json").write_text(json.dumps(rows, indent=2))
    lines = ["# Doon View model comparison (Mussoorie reviews, out-of-sample)", "",
             f"{len(df)} reviews; sentiment vs the guests' stars, 95% bootstrap interval in brackets.", "",
             "| Candidate | Sentiment macro-F1 | Negative recall | Neutral F1 | Aspects vs teacher | Rooms/staff/location vs sub-ratings |",
             "|---|---|---|---|---|---|"]
    for name, r in rows.items():
        s, a = r["sentiment"], r.get("aspects") or {}
        teacher_txt = f"{a['vs_teacher_mean']:.3f}" if a.get("vs_teacher_mean") is not None else "-"
        sub_txt = ", ".join(f"{k} {v['polarity_accuracy']:.2f}" for k, v in (a.get("vs_subratings") or {}).items()) or "-"
        lines.append(f"| {name} | {s['macro_f1']:.3f} [{s['ci95'][0]:.3f}, {s['ci95'][1]:.3f}] | "
                     f"{s['per_class']['negative']['recall']:.2f} | {s['per_class']['neutral']['f1']:.2f} | "
                     f"{teacher_txt} | {sub_txt} |")
    lines += ["", "Aspects vs teacher is agreement with the LLM that labelled the training data, not accuracy. "
              "The sub-rating column is independent: the guest's own 1-5 rating for that aspect."]
    # Every ahead/behind verdict in the app counts complaints, so this table decides which model ships
    support = next((r["aspects"]["negative_recall_vs_teacher"] for r in rows.values() if r.get("aspects")), {})
    if support:
        lines += ["", "## Complaints caught per aspect (share of the teacher's negative labels the model also finds)", "",
                  "| Candidate | " + " | ".join(f"{a} (n={s['support']})" for a, s in support.items()) + " |",
                  "|---|" + "---|" * len(support)]
        for name, r in rows.items():
            recall = (r.get("aspects") or {}).get("negative_recall_vs_teacher")
            if recall:
                cells = [f"{recall[a]['recall']:.2f}" if recall.get(a, {}).get("recall") is not None else "-"
                         for a in support]
                lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines += ["", "## Complaint F1 per aspect (counts false alarms too: the score used to pick a model)", "",
                  "| Candidate | " + " | ".join(support) + " |", "|---|" + "---|" * len(support)]
        for name, r in rows.items():
            f1s = (r.get("aspects") or {}).get("negative_f1_vs_teacher")
            if f1s:
                lines.append(f"| {name} | " + " | ".join(f"{f1s[a]:.2f}" if f1s.get(a) is not None else "-"
                                                        for a in support) + " |")
    (args.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
