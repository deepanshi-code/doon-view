"""Export the final model to int8 ONNX in the format the app loads (backend/app/classifier.py).

    python -m doonview_ml.export --run runs/final-deberta-v3-xsmall --out artifacts/doon-view-xsmall

Writes model.onnx (fp32), model.int8.onnx, tokenizer.json, labels.json and parity.json. The fp32 export must match
PyTorch; the int8 model must agree with PyTorch on >= 95% of sentiments AND keep >= 90% of PyTorch's complaints on
every aspect with enough of them (parity.py; Mussoorie reviews plus fixed examples), trying the smallest recipe first. int8 weights are stored as uint8 (u8u8.py: lossless, and safe on CPUs without
VNNI), and labels.json gets reference answers ("canary") that the app re-checks at start-up.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import onnx
import pandas as pd
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic

from .model import MultiTaskModel
from .parity import MIN_COMPLAINT_RECALL, complaint_recall, failing
from .u8u8 import convert as to_u8u8

PARITY_TEXTS = [
    "Great location on Mall Road and the staff were very helpful, but the WiFi kept dropping.",
    "Terrible. Dirty bathroom, rude staff and far too expensive.",
    "It was okay. Nothing special.",
    "Khana bahut accha tha aur room bhi saaf tha.",
]
CANARY_TEXTS = PARITY_TEXTS + [
    "Breakfast was cold and they charged extra at check-in.",
    "Lovely valley view from the room, clean and quiet.",
    "Overpriced for what you get, and the room smelled damp.",
    "Parking was impossible and the road up to the hotel was steep.",
]
PARITY_SAMPLE = 500
MIN_AGREEMENT = 0.95


def _ffn_down(name: str) -> bool:
    return name.endswith("/output/dense/MatMul") and "/attention/" not in name


def _ffn_up(name: str) -> bool:
    return name.endswith("/intermediate/dense/MatMul")


RECIPES = [  # (name, MatMul nodes kept in fp32), smallest file first
    ("all-int8", lambda name: False),
    ("ffn-down-fp32", _ffn_down),
    ("ffn-fp32", lambda name: _ffn_down(name) or _ffn_up(name)),
]


def classifier(out: Path):
    from app.classifier import OnnxClassifier  # backend on sys.path via labels.py
    return OnnxClassifier(out)


def export(run: Path, out: Path, data: Path | None, opset: int) -> dict:
    model, tok, config = MultiTaskModel.load(run)
    out.mkdir(parents=True, exist_ok=True)
    dummy = tok(["export example"], return_tensors="pt")
    onnx_path, int8_path = out / "model.onnx", out / "model.int8.onnx"
    torch.onnx.export(
        model, (dummy["input_ids"], dummy["attention_mask"]), str(onnx_path),
        input_names=["input_ids", "attention_mask"], output_names=["sentiment", "spam", "aspects"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                      "sentiment": {0: "batch"}, "spam": {0: "batch"}, "aspects": {0: "batch"}},
        opset_version=opset, dynamo=False,
    )
    tok.backend_tokenizer.save(str(out / "tokenizer.json"))
    labels = {"name": f"{run.name}-int8", "backbone": config["backbone"], "onnx_file": int8_path.name,
              "sentiments": config["sentiments"], "aspects": config["aspects"],
              "aspect_values": config["aspect_values"], "max_len": config["max_len"],
              "spam_threshold": config["spam_threshold"], "pad_id": tok.pad_token_id, "pad_token": tok.pad_token,
              "trained_on": config.get("data")}
    (out / "labels.json").write_text(json.dumps(labels, indent=2))

    texts = list(PARITY_TEXTS)
    if data and data.is_file():
        reviews = pd.read_parquet(data)["text"]
        texts += reviews.sample(min(PARITY_SAMPLE, len(reviews)), random_state=0).tolist()
    enc = tok(texts, truncation=True, max_length=config["max_len"], padding=True, return_tensors="pt")
    with torch.no_grad():
        ref = [t.numpy() for t in model(enc["input_ids"], enc["attention_mask"])]
    report = {"texts": len(texts), "fp32_max_abs_logit_diff": fp32_parity(onnx_path, enc, ref), "int8_attempts": []}

    matmuls = [n.name for n in onnx.load(str(onnx_path)).graph.node if n.op_type == "MatMul"]
    ref_labels = [config["sentiments"][i] for i in ref[0].argmax(-1)]
    ref_aspects = [{a: config["aspect_values"][v] for a, v in zip(config["aspects"], row)} for row in ref[2].argmax(-1)]
    for recipe, keep_fp32 in RECIPES:
        quantize_dynamic(str(onnx_path), str(int8_path), weight_type=QuantType.QInt8, per_channel=True,
                         nodes_to_exclude=[m for m in matmuls if keep_fp32(m)])
        to_u8u8(int8_path, int8_path)
        got = classifier(out).predict(texts)
        agree = float(np.mean([w == g["sentiment"] for w, g in zip(ref_labels, got)]))
        recalls = complaint_recall(ref_aspects, [g["aspects_all"] for g in got], config["aspects"])
        weak = failing(recalls)
        attempt = {"recipe": recipe, "sentiment_agreement": agree, "complaint_recall": recalls, "weak_aspects": weak,
                   "size_mb": round(int8_path.stat().st_size / 1e6, 1)}
        report["int8_attempts"].append(attempt)
        print(json.dumps(attempt), flush=True)
        if agree >= MIN_AGREEMENT and not weak:
            report |= {"int8_recipe": recipe, "int8_sentiment_agreement": agree, "int8_complaint_recall": recalls}
            break
    report["sizes_mb"] = {p.name: round(p.stat().st_size / 1e6, 1) for p in (onnx_path, int8_path)}
    (out / "parity.json").write_text(json.dumps(report, indent=2))
    if "int8_recipe" not in report:
        int8_path.unlink()  # never leave a failing int8 model where a deploy would pick it up
        raise SystemExit(f"no int8 recipe kept {MIN_AGREEMENT:.0%} sentiment agreement and {MIN_COMPLAINT_RECALL:.0%} "
                         f"of fp32 complaints per aspect: see {out / 'parity.json'}")
    add_canary(out)
    return report


def add_canary(out: Path) -> None:
    """This machine's answers for CANARY_TEXTS, which the app re-checks at start-up on its own CPU."""
    from app.classifier import cpu_summary
    labels_path = out / "labels.json"
    labels = json.loads(labels_path.read_text())
    results = classifier(out).predict(CANARY_TEXTS)
    labels["canary"] = [{"text": t, "sentiment_probs": [round(p, 4) for p in r["sentiment_probs"]],
                         "aspects_all": r["aspects_all"]} for t, r in zip(CANARY_TEXTS, results)]
    labels["canary_cpu"] = cpu_summary()
    labels_path.write_text(json.dumps(labels, indent=2))


def fp32_parity(onnx_path: Path, enc, ref) -> float:
    import onnxruntime as ort
    got = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"]).run(
        None, {"input_ids": enc["input_ids"].numpy(), "attention_mask": enc["attention_mask"].numpy()})
    diff = max(float(np.abs(a - b).max()) for a, b in zip(ref, got))
    if diff > 1e-3:
        raise SystemExit(f"fp32 ONNX export diverges from PyTorch (max diff {diff:.2e})")
    return diff


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("data/processed/reviews.parquet"))
    p.add_argument("--opset", type=int, default=17)
    args = p.parse_args()
    print(json.dumps(export(args.run, args.out, args.data, args.opset), indent=2))


if __name__ == "__main__":
    main()
