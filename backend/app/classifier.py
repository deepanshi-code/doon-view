"""Fine-tuned review classifier (DeBERTa-v3-xsmall, int8 ONNX), served on CPU.

Loaded only when MODEL_DIR is set; needs onnxruntime + tokenizers (no torch).
MODEL_DIR holds labels.json, tokenizer.json and the .onnx file named in labels.json (scripts/fetch_model.py).
"""
import json
import os
from pathlib import Path

import numpy as np


def fit_ids(ids: list[int], max_len: int) -> list[int]:
    """Fit an encoded review ([CLS] ... [SEP]) into max_len tokens, keeping its start AND its end.

    Plain truncation keeps only the start, but long reviews often end with the verdict ("As for the downside
    of my stay..."). Keeping the first and last halves raised macro-F1 on reviews over 256 tokens (~19% of
    reviews) from 0.788 to 0.798 on the frozen test split with the same model, chosen on validation first.
    [CLS] and [SEP] stay at the ends."""
    if len(ids) <= max_len:
        return ids
    half = max_len // 2
    return ids[:half] + ids[-(max_len - half):]


def cpu_summary() -> str:
    """CPU model and whether it has VNNI: int8 results can differ on x86 CPUs without it (see self_check)."""
    # Diagnostics only: never let reading it break model loading
    try:
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        name = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("model name")), "?")
        flags = next((ln.split(":", 1)[1].split() for ln in lines if ln.startswith("flags")), [])
        vnni = "yes" if {"avx512_vnni", "avx_vnni"} & set(flags) else "no"
        return f"{name}, {os.cpu_count()} cores, VNNI: {vnni}"
    except Exception:
        import platform
        return f"{platform.processor() or 'unknown CPU'}, {os.cpu_count()} cores, VNNI: unknown"


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class OnnxClassifier:
    def __init__(self, model_dir: str | Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        model_dir = Path(model_dir)
        self.config = json.loads((model_dir / "labels.json").read_text(encoding="utf-8"))
        self.name = self.config.get("name", model_dir.name)
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        # Truncation and padding are done in predict(): see fit_ids()
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        # Small instances (e.g. Render free tier) have little CPU and RAM: keep the thread pool small
        options.intra_op_num_threads = int(os.getenv("MODEL_THREADS", "1"))
        self.session = ort.InferenceSession(
            str(model_dir / self.config["onnx_file"]), options, providers=["CPUExecutionProvider"])

    def self_check(self) -> list[str]:
        """Re-run the reference reviews in labels.json ("canary", written by the export) and list every
        disagreement. An int8 model can compute differently on another CPU: a model verified on VNNI CPUs gave
        wrong labels on a server without VNNI. Empty list = same answers as where the model was verified."""
        canary = self.config.get("canary") or []
        problems = []
        for want, got in zip(canary, self.predict([c["text"] for c in canary])):
            drift = float(np.abs(np.array(want["sentiment_probs"]) - np.array(got["sentiment_probs"])).max())
            if want["aspects_all"] != got["aspects_all"] or drift > 0.05:
                problems.append(f"{want['text'][:40]!r}: expected {want['aspects_all']}, got {got['aspects_all']}, "
                                f"sentiment probability drift {drift:.2f}")
        return problems

    def predict(self, texts: list[str]) -> list[dict]:
        # One review per run, never a padded batch: with the int8 model, batching made a review's label depend
        # on the other reviews in the batch (1.25% of labels changed vs scoring alone), and padding every review
        # to the longest one was ~2.5x slower on one CPU thread. Unpadded runs give one answer per review.
        outputs = []
        for enc in self.tokenizer.encode_batch(texts):
            ids = fit_ids(enc.ids, self.config["max_len"])
            feeds = {"input_ids": np.array([ids], dtype=np.int64), "attention_mask": np.ones((1, len(ids)), dtype=np.int64)}
            outputs.append(self.session.run(None, feeds))
        sentiment_logits, spam_logits, aspect_logits = (np.concatenate(parts) for parts in zip(*outputs))
        sentiment_probs = _softmax(sentiment_logits)
        spam_probs = 1 / (1 + np.exp(-spam_logits))
        aspect_values = self.config["aspect_values"]
        aspect_idx = _softmax(aspect_logits).argmax(-1)

        results = []
        for i in range(len(texts)):
            aspects = {name: aspect_values[aspect_idx[i, j]] for j, name in enumerate(self.config["aspects"])}
            results.append({
                "sentiment": self.config["sentiments"][int(sentiment_probs[i].argmax())],
                "sentiment_probs": sentiment_probs[i].tolist(),
                "confidence": float(sentiment_probs[i].max()),
                "is_spam": bool(spam_probs[i] >= self.config["spam_threshold"]),
                "spam_prob": float(spam_probs[i]),
                "aspects": {k: v for k, v in aspects.items() if v != "not_mentioned"},
                "aspects_all": aspects,
            })
        return results
