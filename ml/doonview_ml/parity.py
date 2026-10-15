"""Aspect check for the int8 export: the compressed model must still find the complaints its fp32 model finds.

export.py used to accept an int8 recipe on sentiment agreement alone. The deberta-v3-base export passed that check
and then flagged about a third as many aspect complaints as the app's model on the same reviews, so complaints are
now checked too. Pure Python, so it is tested without the training environment.
"""
MIN_COMPLAINT_RECALL = 0.90   # share of fp32 complaints the int8 model must keep, per aspect
MIN_COMPLAINTS = 20           # aspects with fewer fp32 complaints in the parity texts are reported, not judged


def complaint_recall(ref: list[dict], got: list[dict], aspects: list[str]) -> dict[str, dict]:
    """Per aspect: how many reviews fp32 labels "negative", and the share of those int8 also labels "negative"."""
    out = {}
    for a in aspects:
        idx = [i for i, r in enumerate(ref) if r.get(a) == "negative"]
        kept = sum(1 for i in idx if got[i].get(a) == "negative")
        out[a] = {"fp32_complaints": len(idx), "recall": round(kept / len(idx), 4) if idx else None}
    return out


def failing(recalls: dict[str, dict]) -> list[str]:
    """Aspects with enough complaints to judge whose recall is under the bar."""
    return [a for a, r in recalls.items()
            if r["fp32_complaints"] >= MIN_COMPLAINTS and r["recall"] < MIN_COMPLAINT_RECALL]
