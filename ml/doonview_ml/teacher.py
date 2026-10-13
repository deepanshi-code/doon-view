"""Teacher labels for aspects (and spam): an open LLM labels every review once, with the app's own guide.

    # vLLM server already running:
    python -m doonview_ml.teacher --backend openai --model Qwen/Qwen3-30B-A3B-FP8 --base-url http://localhost:8001/v1
    # no vLLM: the same model through transformers on the GPU (slower)
    python -m doonview_ml.teacher --backend hf --model Qwen/Qwen3-8B

Output: data/processed/teacher/<model>.jsonl, appended as it goes; re-running resumes and retries failures.
Sentiment for training comes from the stars, not from here; the teacher's sentiment is kept only to compare.
"""
import argparse
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

from .labels import ASPECTS, CLASSIFICATION_SCHEMA, build_prompt, parse_classification


def to_json_schema(node: dict) -> dict:
    """Gemini-style schema (type: "OBJECT") -> standard JSON Schema for OpenAI-compatible servers."""
    out = {k: v for k, v in node.items() if k not in ("type", "properties")}
    out["type"] = node["type"].lower()
    if "properties" in node:
        out["properties"] = {k: to_json_schema(v) for k, v in node["properties"].items()}
        out["additionalProperties"] = False
    return out


class OpenAICompatibleTeacher:
    """vLLM (or any OpenAI-compatible server) with JSON-schema constrained output."""

    def __init__(self, base_url: str, model: str):
        self.url, self.model = base_url.rstrip("/") + "/chat/completions", model
        self.schema = to_json_schema(CLASSIFICATION_SCHEMA)

    def label(self, text: str) -> dict:
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "user", "content": build_prompt(text)}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "classification", "schema": self.schema}},
                "chat_template_kwargs": {"enable_thinking": False}}  # Qwen3: no reasoning trace
        res = requests.post(self.url, json=body, timeout=180)
        if not res.ok:
            raise RuntimeError(f"HTTP {res.status_code}: {res.text[:300]}")
        return json.loads(res.json()["choices"][0]["message"]["content"])


class HFTeacher:
    """No vLLM: batched greedy generation with transformers; the JSON is extracted and validated as strictly."""

    def __init__(self, model: str, batch_size: int):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch, self.model, self.batch_size = torch, model, batch_size
        self.tok = AutoTokenizer.from_pretrained(model, padding_side="left")
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        self.lm = AutoModelForCausalLM.from_pretrained(model, dtype=torch.bfloat16, device_map="cuda").eval()
        self.hint = json.dumps(to_json_schema(CLASSIFICATION_SCHEMA))

    def _prompt(self, text: str) -> str:
        content = build_prompt(text) + f"\n\nReply with ONLY a JSON object matching this JSON Schema:\n{self.hint}"
        return self.tok.apply_chat_template([{"role": "user", "content": content}], tokenize=False,
                                            add_generation_prompt=True, enable_thinking=False)

    @staticmethod
    def _extract(reply: str) -> dict | None:
        start, end = reply.find("{"), reply.rfind("}")
        try:
            result = json.loads(reply[start:end + 1]) if 0 <= start < end else None
        except json.JSONDecodeError:
            return None
        if isinstance(result, dict) and isinstance(result.get("aspects"), dict):
            for name in ASPECTS:
                result["aspects"].setdefault(name, "not_mentioned")
        return result

    def label_batch(self, texts: list[str]) -> list[dict | None]:
        enc = self.tok([self._prompt(t) for t in texts], return_tensors="pt", padding=True).to("cuda")
        with self.torch.no_grad():
            out = self.lm.generate(**enc, max_new_tokens=220, do_sample=False, pad_token_id=self.tok.pad_token_id)
        return [self._extract(r) for r in
                self.tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)]


def read_labels(path: Path) -> dict[str, dict]:
    """Teacher JSONL -> {review_id: label}; a line torn by an interrupted write is skipped (and re-labelled)."""
    labels = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                labels[row["review_id"]] = row
            except (json.JSONDecodeError, KeyError):
                continue
    return labels


def run(teacher, rows: pd.DataFrame, out: Path, workers: int) -> tuple[int, int]:
    done = set(read_labels(out))
    if out.is_file() and out.stat().st_size and not out.read_bytes().endswith(b"\n"):
        with out.open("a", encoding="utf-8") as f:
            f.write("\n")
    todo = rows[~rows.review_id.isin(done)]
    print(f"{len(done)} already labelled, {len(todo)} to go -> {out}")
    lock, ok, failed = threading.Lock(), 0, 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        def record(i: int, review_id: str, parsed) -> None:
            nonlocal ok, failed
            with lock:
                if parsed:
                    sentiment, is_spam, aspects = parsed
                    f.write(json.dumps({"review_id": review_id, "sentiment": sentiment, "is_spam": is_spam,
                                        "aspects": aspects, "judged": list(ASPECTS)}) + "\n")
                    f.flush()
                    ok += 1
                else:
                    failed += 1
                if i % 200 == 0:
                    print(f"  {i}/{len(todo)} ({failed} failed)", flush=True)

        if hasattr(teacher, "label_batch"):
            items = list(todo.itertuples())
            for start in range(0, len(items), teacher.batch_size):
                chunk = items[start:start + teacher.batch_size]
                for j, (r, raw) in enumerate(zip(chunk, teacher.label_batch([r.text for r in chunk]))):
                    record(start + j + 1, r.review_id, parse_classification(raw))
        else:
            def work(review_id: str, text: str):
                for attempt in range(3):
                    try:
                        parsed = parse_classification(teacher.label(text))
                        if parsed:
                            return review_id, parsed
                    except Exception as e:  # a hiccup or bad JSON: back off and retry
                        if attempt == 2:
                            print(f"{review_id}: {e}")
                    time.sleep(2 * attempt)
                return review_id, None

            with ThreadPoolExecutor(workers) as pool:
                futures = [pool.submit(work, r.review_id, r.text) for r in todo.itertuples()]
                for i, fut in enumerate(as_completed(futures), 1):
                    record(i, *fut.result())
    return ok, failed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backend", choices=["openai", "hf"], required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", default="http://localhost:8001/v1")
    p.add_argument("--data", type=Path, default=Path("data/processed"))
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--limit", type=int, help="label only this many (spot checks)")
    args = p.parse_args()
    teacher = (OpenAICompatibleTeacher(args.base_url, args.model) if args.backend == "openai"
               else HFTeacher(args.model, args.batch_size))
    rows = pd.read_parquet(args.data / "reviews.parquet")
    if args.limit:
        rows = rows.sample(min(args.limit, len(rows)), random_state=13)
    out = args.data / "teacher" / f"{args.model.split('/')[-1]}.jsonl"
    ok, failed = run(teacher, rows, out, args.workers)
    print(f"done: {ok} labelled, {failed} failed")


if __name__ == "__main__":
    main()
