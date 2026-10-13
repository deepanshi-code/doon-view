"""The ONNX classifier itself: CPU reporting, long-review fitting, and (with TEST_MODEL_DIR) the real model."""
import os
from pathlib import Path

import pytest


def test_cpu_summary_reports_vnni_from_linux_cpuinfo(monkeypatch):
    from app import classifier
    fake = {"vnni": "model name\t: Intel Xeon\nflags\t\t: fpu avx2 avx512f avx512_vnni\n",
            "plain": "model name\t: AMD EPYC 7763\nflags\t\t: fpu avx2\n"}
    for kind, expected in (("vnni", "Intel Xeon, "), ("plain", "AMD EPYC 7763, ")):
        monkeypatch.setattr(Path, "read_text", lambda self, *a, k=kind, **kw: fake[k])
        summary = classifier.cpu_summary()
        assert summary.startswith(expected) and summary.endswith("VNNI: yes" if kind == "vnni" else "VNNI: no")
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **kw: (_ for _ in ()).throw(OSError("no /proc")))
    assert classifier.cpu_summary().endswith("VNNI: unknown")


def test_fit_ids_keeps_short_reviews_whole_and_long_ones_head_and_tail():
    from app.classifier import fit_ids
    short = [101, 5, 6, 102]
    assert fit_ids(short, 8) is short
    long = [101] + list(range(1, 20)) + [102]
    assert fit_ids(long, 8) == [101, 1, 2, 3, 17, 18, 19, 102]


@pytest.mark.skipif(not os.getenv("TEST_MODEL_DIR"), reason="set TEST_MODEL_DIR to the exported model to run")
def test_real_model_labels_do_not_depend_on_batch_mates():
    from app.classifier import OnnxClassifier
    model = OnnxClassifier(os.environ["TEST_MODEL_DIR"])
    texts = ["Lovely host and spotless room.", "The WiFi kept dropping and breakfast was cold. " * 30,
             "Average stay, nothing special.", "Terrible. Dirty sheets and rude staff."]
    together = model.predict(texts)
    alone = [model.predict([t])[0] for t in texts]
    assert [r["sentiment_probs"] for r in together] == [r["sentiment_probs"] for r in alone]
