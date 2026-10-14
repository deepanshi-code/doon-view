"""Fine-tune the multi-task classifier on the Mussoorie reviews, optionally mixed with outside hotel reviews.

    # 5-fold cross-validation: every review is scored by a model that never saw it (out-of-fold predictions)
    python -m doonview_ml.train cv --backbone microsoft/deberta-v3-xsmall --teacher data/processed/teacher/X.jsonl \
        --out runs/cv-deberta-v3-xsmall-s13
    # mixed: outside reviews (doonview_ml.external) in every training set, Mussoorie reviews repeated 3 times
    python -m doonview_ml.train cv ... --external data/external --repeat 3 --out runs/cv-mix-deberta-v3-xsmall-s13
    # the shipped model: all reviews, the epoch count cross-validation chose
    python -m doonview_ml.train final --backbone microsoft/deberta-v3-xsmall --teacher ... --epochs 5 --out runs/final-...

Targets: sentiment from the guests' stars; aspects and spam from the teacher LLM (a review it failed to label has
no aspect target). 1,657 reviews is small and 88% positive, so sentiment uses inverse-frequency class weights and
each aspect its own square-root weights; nothing is tuned on a fold that is then reported. Outside reviews are only
ever trained on: the folds, and so every reported score, are Mussoorie reviews only.
"""
import argparse
import json
import math
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup

from .labels import ASPECT_VALUES, ASPECTS, SENTIMENTS
from .model import MultiTaskModel
from .teacher import read_labels

IGNORE = -100
SPAM_THRESHOLD = 0.5  # too few spam reviews to tune one honestly


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def targets(df: pd.DataFrame, teacher: dict) -> dict:
    sentiment = df["sentiment"].map(SENTIMENTS.index).to_numpy(np.int64)
    spam = np.zeros(len(df), dtype=np.float32)
    aspects = np.full((len(df), len(ASPECTS)), IGNORE, dtype=np.int64)
    for i, rid in enumerate(df["review_id"]):
        label = teacher.get(rid)
        if not label:
            continue
        spam[i] = float(label["is_spam"])
        for j, a in enumerate(ASPECTS):
            if a in label.get("judged", ASPECTS):
                aspects[i, j] = ASPECT_VALUES.index(label["aspects"].get(a, "not_mentioned"))
    return {"sentiment": sentiment, "spam": spam, "aspects": aspects}


class Batches:
    """Tokenised reviews with dynamic padding."""

    def __init__(self, texts: list[str], y: dict, tokenizer, max_len: int):
        enc = tokenizer(texts, truncation=True, max_length=max_len)
        self.items = [{"input_ids": ids, "sentiment": y["sentiment"][i], "spam": y["spam"][i], "aspects": y["aspects"][i]}
                      for i, ids in enumerate(enc["input_ids"])]
        self.pad_id = tokenizer.pad_token_id

    def collate(self, batch: list[dict]) -> dict:
        width = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), width), self.pad_id, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        for i, b in enumerate(batch):
            ids[i, :len(b["input_ids"])] = torch.tensor(b["input_ids"])
            mask[i, :len(b["input_ids"])] = 1
        return {"input_ids": ids, "attention_mask": mask,
                "sentiment": torch.tensor(np.array([b["sentiment"] for b in batch])),
                "spam": torch.tensor(np.array([b["spam"] for b in batch])),
                "aspects": torch.tensor(np.stack([b["aspects"] for b in batch]))}

    def loader(self, batch_size: int, shuffle: bool) -> DataLoader:
        return DataLoader(self.items, batch_size=batch_size, shuffle=shuffle, collate_fn=self.collate)


def predict(model, loader, device: str, amp: bool) -> dict:
    model.eval()
    out = {"sentiment": [], "spam": [], "aspects": []}
    with torch.no_grad(), torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=amp):
        for b in loader:
            s, p, a = model(b["input_ids"].to(device), b["attention_mask"].to(device))
            out["sentiment"].append(s.float().softmax(-1).cpu().numpy())
            out["spam"].append(p.float().sigmoid().cpu().numpy())
            out["aspects"].append(a.float().softmax(-1).cpu().numpy())
    return {k: np.concatenate(v) for k, v in out.items()}


def aspect_weights(y: dict) -> np.ndarray:
    """(aspects, values) loss weights: square-root inverse frequency per aspect, so a rare aspect (booking, wifi)
    is not collapsed into 'not_mentioned'."""
    w = np.ones((len(ASPECTS), len(ASPECT_VALUES)), dtype=np.float32)
    for j in range(len(ASPECTS)):
        col = y["aspects"][:, j]
        counts = np.bincount(col[col != IGNORE], minlength=len(ASPECT_VALUES))
        if counts.sum():
            w[j] = np.sqrt(counts.sum() / (len(ASPECT_VALUES) * np.maximum(counts, 1)))
    return w


def aspect_loss(logits, target, weights):
    losses = [nn.functional.cross_entropy(logits[:, j].float(), target[:, j], weight=weights[j], ignore_index=IGNORE)
              for j in range(target.shape[1]) if (target[:, j] != IGNORE).any()]
    return torch.stack(losses).mean() if losses else None


def quick_metrics(pred: dict, y: dict) -> dict:
    """For choosing the epoch count: sentiment vs stars and per-aspect agreement with the teacher, equally."""
    m = {"sentiment_macro_f1": float(f1_score(y["sentiment"], pred["sentiment"].argmax(-1), average="macro"))}
    per = []
    for j in range(len(ASPECTS)):
        mask = y["aspects"][:, j] != IGNORE
        if mask.any():
            per.append(f1_score(y["aspects"][mask, j], pred["aspects"][mask, j].argmax(-1), average="macro",
                                zero_division=0))
    m["aspects_mean_macro_f1"] = float(np.mean(per)) if per else None
    m["score"] = (m["sentiment_macro_f1"] + (m["aspects_mean_macro_f1"] or m["sentiment_macro_f1"])) / 2
    return m


def fit(train_df, eval_df, teacher, args, on_epoch=None):
    """Train on train_df; after each epoch call on_epoch(epoch, eval predictions) when eval_df is given."""
    set_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    amp = device == "cuda" and torch.cuda.is_bf16_supported()
    tok = AutoTokenizer.from_pretrained(args.backbone)
    model = MultiTaskModel(AutoModel.from_pretrained(args.backbone, dtype=torch.float32)).to(device)
    y_train = targets(train_df, teacher)
    train_loader = Batches(train_df["text"].tolist(), y_train, tok, args.max_len).loader(args.batch_size, True)
    eval_loader = (Batches(eval_df["text"].tolist(), targets(eval_df, teacher), tok, args.max_len)
                   .loader(args.batch_size * 2, False) if eval_df is not None else None)

    counts = np.bincount(y_train["sentiment"], minlength=len(SENTIMENTS))
    s_weights = torch.tensor(counts.sum() / (len(SENTIMENTS) * np.maximum(counts, 1)), dtype=torch.float, device=device)
    sentiment_loss = nn.CrossEntropyLoss(weight=s_weights)
    a_weights = torch.tensor(aspect_weights(y_train), device=device)
    spam_loss = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = len(train_loader) * args.epochs
    scheduler = get_linear_schedule_with_warmup(optimizer, math.ceil(0.1 * steps), steps)

    for epoch in range(1, args.epochs + 1):
        model.train()
        start, total = time.time(), 0.0
        for b in train_loader:
            b = {k: v.to(device) for k, v in b.items()}
            with torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=amp):
                s, sp, a = model(b["input_ids"], b["attention_mask"])
            loss = sentiment_loss(s.float(), b["sentiment"]) + spam_loss(sp.float(), b["spam"])
            a_loss = aspect_loss(a, b["aspects"], a_weights)
            if a_loss is not None:
                loss = loss + a_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total += loss.item()
        print(f"  epoch {epoch}: loss {total / len(train_loader):.4f} ({time.time() - start:.0f}s)", flush=True)
        if eval_loader is not None and on_epoch:
            on_epoch(epoch, predict(model, eval_loader, device, amp))
    return model, tok


TRAIN_COLUMNS = ["review_id", "text", "sentiment"]


def load_data(args) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    df = pd.read_parquet(Path(args.data) / "reviews.parquet")
    teacher = read_labels(Path(args.teacher)) if args.teacher else {}
    if args.limit:
        df = df.groupby("fold").head(max(2, args.limit // df["fold"].nunique())).reset_index(drop=True)
    print(f"{len(df)} reviews, {sum(r in teacher for r in df.review_id)} with teacher labels")
    external = None
    if args.external:
        external = pd.read_parquet(Path(args.external) / "reviews.parquet")
        if args.limit:
            external = external.head(args.limit)
        if set(external["review_id"]) & set(df["review_id"]):
            raise SystemExit("outside and Mussoorie review ids overlap: a review would be trained and tested on")
        # the same teacher model labelled both sets: its file has the same name in the outside folder
        ext_labels = read_labels(Path(args.external) / "teacher" / Path(args.teacher).name) if args.teacher else {}
        teacher = {**ext_labels, **teacher}
        print(f"+ {len(external)} outside reviews ({sum(r in ext_labels for r in external.review_id)} with teacher "
              f"labels), Mussoorie reviews repeated x{args.repeat} in training")
    return df, teacher, external


def training_set(mussoorie: pd.DataFrame, external: pd.DataFrame | None, repeat: int) -> pd.DataFrame:
    """Mussoorie rows repeated `repeat` times plus the outside rows, so ~15,000 outside reviews don't drown out
    ~1,300 local ones. Only for training: evaluation always uses the Mussoorie fold alone."""
    parts = [mussoorie[TRAIN_COLUMNS]] * (repeat if external is not None else 1)
    if external is not None:
        parts.append(external[TRAIN_COLUMNS])
    return pd.concat(parts, ignore_index=True)


def run_cv(args) -> None:
    df, teacher, external = load_data(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    folds = sorted(df["fold"].unique())
    # per epoch: out-of-fold predictions assembled across folds, in df order
    oof = {e: {k: None for k in ("sentiment", "spam", "aspects")} for e in range(1, args.epochs + 1)}
    per_fold = []
    for k in folds:
        test_idx = np.where(df["fold"] == k)[0]
        train_df = training_set(df.iloc[np.setdiff1d(np.arange(len(df)), test_idx)], external, args.repeat)
        print(f"fold {k}: train {len(train_df)} rows ({len(df) - len(test_idx)} Mussoorie reviews), "
              f"test {len(test_idx)} Mussoorie reviews", flush=True)
        y_test = targets(df.iloc[test_idx], teacher)

        def on_epoch(epoch, pred, test_idx=test_idx, y_test=y_test, k=k):
            for key, arr in pred.items():
                if oof[epoch][key] is None:
                    oof[epoch][key] = np.zeros((len(df),) + arr.shape[1:], dtype=np.float32)
                oof[epoch][key][test_idx] = arr
            per_fold.append({"fold": int(k), "epoch": epoch, **quick_metrics(pred, y_test)})
            print(f"    fold {k} epoch {epoch}: {json.dumps(per_fold[-1])}", flush=True)

        fit(train_df, df.iloc[test_idx], teacher, args, on_epoch)

    y_all = targets(df, teacher)
    by_epoch = {e: quick_metrics(oof[e], y_all) for e in oof}
    best = max(by_epoch, key=lambda e: by_epoch[e]["score"])
    np.savez_compressed(out / "oof.npz", review_id=df["review_id"].to_numpy(), **oof[best])
    summary = {"backbone": args.backbone, "seed": args.seed, "lr": args.lr, "batch_size": args.batch_size,
               "max_len": args.max_len, "epochs_tried": args.epochs, "best_epochs": best,
               "external": args.external, "external_rows": 0 if external is None else len(external),
               "mussoorie_repeat": args.repeat if external is not None else 1,
               "oof_by_epoch": by_epoch, "per_fold": per_fold, "teacher": args.teacher,
               "note": "best_epochs is chosen on the same out-of-fold scores it reports: slightly optimistic"}
    (out / "cv.json").write_text(json.dumps(summary, indent=2))
    print(f"best epoch count {best}: {json.dumps(by_epoch[best])}")


def run_final(args) -> None:
    df, teacher, external = load_data(args)
    train_df = training_set(df, external, args.repeat)
    model, tok = fit(train_df, None, teacher, args)
    data = ("Mussoorie reviews only (data/reviews.csv)" if external is None else
            f"Mussoorie reviews (x{args.repeat}) + {len(external)} TripAdvisor reviews (jniimi/tripadvisor-review-rating:"
            " academic, non-commercial use; keep this model private)")
    config = {"backbone": args.backbone, "sentiments": list(SENTIMENTS), "aspects": list(ASPECTS),
              "aspect_values": list(ASPECT_VALUES), "max_len": args.max_len, "spam_threshold": SPAM_THRESHOLD,
              "epochs": args.epochs, "lr": args.lr, "seed": args.seed, "train_rows": len(train_df),
              "teacher": args.teacher, "data": data,
              "versions": {"torch": torch.__version__, "transformers": transformers.__version__}}
    model.save(Path(args.out), tok, config)
    print(f"saved {args.out}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mode", choices=["cv", "final"])
    p.add_argument("--backbone", default="microsoft/deberta-v3-xsmall")
    p.add_argument("--data", default="data/processed")
    p.add_argument("--teacher", help="teacher JSONL (aspects and spam)")
    p.add_argument("--out", required=True)
    p.add_argument("--epochs", type=int, default=8)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=3e-5)
    p.add_argument("--max-len", type=int, default=256)
    p.add_argument("--seed", type=int, default=13)
    p.add_argument("--limit", type=int, help="smoke tests: this many reviews in total")
    p.add_argument("--external", help="folder from doonview_ml.external: outside reviews added to every training set")
    p.add_argument("--repeat", type=int, default=3, help="with --external: times each Mussoorie review is trained on")
    args = p.parse_args()
    run_cv(args) if args.mode == "cv" else run_final(args)


if __name__ == "__main__":
    main()
