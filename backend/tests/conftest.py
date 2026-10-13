import json as json_lib
import os
import re
import sys
from pathlib import Path

# Before any `app` import: modules read config at import time
os.environ.update({"GEMINI_API_KEY": "", "ALLOWED_ORIGINS": "https://doon-view.example"})
os.environ.pop("MODEL_DIR", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

FAKE_KEY = "AIza-test-key-0000"


class FakeResponse:
    status_code = 200

    def __init__(self, text):
        self._body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class Calls(list):
    """Recorded Gemini requests. `reply` is the text the fake returns; None answers every review in the batch
    as neutral with no aspects."""
    reply = None


@pytest.fixture
def gemini(monkeypatch):
    from app import labelling
    monkeypatch.setattr(labelling, "GEMINI_API_KEY", FAKE_KEY)
    calls = Calls()

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers or {}})
        if calls.reply is not None:
            return FakeResponse(calls.reply)
        prompt = json["contents"][0]["parts"][0]["text"]
        n = int(re.search(r"There are (\d+) reviews", prompt).group(1))
        return FakeResponse(json_lib.dumps([{"index": i, "sentiment": "neutral", "is_spam": False,
                                             "aspects": {a: "not_mentioned" for a in labelling.ASPECT_GUIDE}}
                                            for i in range(n)]))

    monkeypatch.setattr(labelling.requests, "post", fake_post)
    return calls
