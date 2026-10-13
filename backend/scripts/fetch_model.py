"""Download the fine-tuned classifier at build time (e.g. Render build command).

    MODEL_URL=<model zip> MODEL_URL_TOKEN=<read token> MODEL_DIR=model python -m scripts.fetch_model

Does nothing when MODEL_URL is unset (labelling then uses Gemini / keyword rules). The zip must contain
labels.json, tokenizer.json and the .onnx file named in labels.json, at its top level.
Keep the zip in private storage: the model is trained on research-only review data that must not be redistributed.

The download streams to disk and survives dropped connections: each retry resumes from the last byte
received (HTTP Range), and the finished file must match the size the server announced before it is unzipped.
"""
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import requests

ATTEMPTS = 5
CHUNK = 1 << 20


def download(url: str, token: str | None, dest: Path) -> None:
    """Stream url to dest, resuming after dropped connections. Raises SystemExit with a clear message."""
    auth = {"Authorization": f"Bearer {token}"} if token else {}  # requests drops it on the redirect to the CDN
    dest.unlink(missing_ok=True)
    total = None
    for attempt in range(1, ATTEMPTS + 1):
        have = dest.stat().st_size if dest.exists() else 0
        headers = {**auth, **({"Range": f"bytes={have}-"} if have else {})}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as res:
                if res.status_code in (401, 403, 404):
                    raise SystemExit(f"{res.status_code} for {url}: check MODEL_URL, and that MODEL_URL_TOKEN can read this repo")
                res.raise_for_status()
                if have and res.status_code != 206:   # server ignored the range: start over
                    have = 0
                if res.status_code == 206:
                    total = int(res.headers["Content-Range"].rsplit("/", 1)[1])
                elif "Content-Length" in res.headers:
                    total = int(res.headers["Content-Length"])
                with open(dest, "ab" if have else "wb") as f:
                    for chunk in res.iter_content(CHUNK):
                        f.write(chunk)
            size = dest.stat().st_size
            if total is None or size == total:
                return
            raise requests.exceptions.ChunkedEncodingError(f"got {size} of {total} bytes")
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as e:
            got = dest.stat().st_size if dest.exists() else 0
            if attempt == ATTEMPTS:
                raise SystemExit(f"Download kept failing after {ATTEMPTS} attempts ({got / 1e6:.0f} MB received): {e}")
            print(f"Connection dropped at {got / 1e6:.0f} MB ({type(e).__name__}); resuming "
                  f"(attempt {attempt + 1} of {ATTEMPTS})...", file=sys.stderr, flush=True)
            time.sleep(min(2 ** attempt, 15))


def main() -> None:
    url, model_dir = os.getenv("MODEL_URL"), Path(os.getenv("MODEL_DIR", "model"))
    if not url:
        print("MODEL_URL not set: skipping model download.")
        return
    model_dir.mkdir(parents=True, exist_ok=True)
    part = model_dir.parent / f"{model_dir.name}.zip.part"
    download(url, os.getenv("MODEL_URL_TOKEN"), part)
    try:
        with zipfile.ZipFile(part) as archive:
            archive.extractall(model_dir)
    except zipfile.BadZipFile:
        raise SystemExit(f"{url} did not return a valid zip (is MODEL_URL the .zip printed by publish_model.sh?)")
    finally:
        part.unlink(missing_ok=True)
    labels = json.loads((model_dir / "labels.json").read_text(encoding="utf-8"))
    onnx_file = model_dir / labels["onnx_file"]
    if not onnx_file.exists() or not (model_dir / "tokenizer.json").exists():
        raise SystemExit(f"Model zip is incomplete: expected {onnx_file.name} and tokenizer.json in {model_dir}")
    print(f"Model '{labels.get('name')}' ready in {model_dir} ({onnx_file.stat().st_size / 1e6:.0f} MB).")


if __name__ == "__main__":
    main()
