"""scripts.fetch_model survives dropped connections (resuming with HTTP Range) and fails clearly otherwise."""
import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import fetch_model


def model_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("labels.json", json.dumps({"name": "tiny", "onnx_file": "model.onnx"}))
        z.writestr("tokenizer.json", "{}")
        z.writestr("model.onnx", bytes(range(256)) * 400)   # ~100 KB, incompressible-ish
    return buf.getvalue()


class Server:
    """Serves one file. `drops` = how many responses get cut off halfway; `ranges` = honour Range headers."""
    def __init__(self, body: bytes, drops: int = 0, ranges: bool = True, status: int = 200):
        self.body, self.drops, self.ranges, self.status, self.requests = body, drops, ranges, status, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_GET(self):
                rng = self.headers.get("Range")
                outer.requests.append(rng)
                if outer.status != 200:
                    self.send_response(outer.status); self.end_headers(); return
                start = int(rng.split("=")[1].split("-")[0]) if rng and outer.ranges else 0
                part = outer.body[start:]
                if start:
                    self.send_response(206)
                    self.send_header("Content-Range", f"bytes {start}-{len(outer.body) - 1}/{len(outer.body)}")
                else:
                    self.send_response(200)
                self.send_header("Content-Length", str(len(part)))
                self.end_headers()
                if outer.drops:
                    outer.drops -= 1
                    self.wfile.write(part[: len(part) // 2]); self.wfile.flush()
                    self.close_connection = True   # announced more than we sent: client sees IncompleteRead
                    return
                self.wfile.write(part)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/model.zip"

    def close(self):
        self.httpd.shutdown()


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fetch_model.time, "sleep", lambda s: None)
    # Small chunks so partial data reaches disk before a drop, as with the real 69 MB file and 1 MB chunks
    monkeypatch.setattr(fetch_model, "CHUNK", 4096)


def test_dropped_connections_resume_from_the_last_byte(tmp_path):
    body = model_zip()
    srv = Server(body, drops=2)
    try:
        fetch_model.download(srv.url, None, tmp_path / "m.zip")
    finally:
        srv.close()
    assert (tmp_path / "m.zip").read_bytes() == body
    assert srv.requests[0] is None and all(r and r.startswith("bytes=") for r in srv.requests[1:])
    assert len(srv.requests) == 3


def test_server_that_ignores_range_restarts_cleanly(tmp_path):
    body = model_zip()
    srv = Server(body, drops=1, ranges=False)
    try:
        fetch_model.download(srv.url, None, tmp_path / "m.zip")
    finally:
        srv.close()
    assert (tmp_path / "m.zip").read_bytes() == body   # no duplicated bytes from appending a full response


def test_gives_up_with_a_clear_message(tmp_path):
    srv = Server(model_zip(), drops=99)
    try:
        with pytest.raises(SystemExit, match="kept failing after 5 attempts"):
            fetch_model.download(srv.url, None, tmp_path / "m.zip")
    finally:
        srv.close()


def test_missing_or_forbidden_file_is_reported_not_retried(tmp_path):
    srv = Server(b"", status=404)
    try:
        with pytest.raises(SystemExit, match="404 for"):
            fetch_model.download(srv.url, None, tmp_path / "m.zip")
    finally:
        srv.close()
    assert len(srv.requests) == 1


def test_main_downloads_unzips_and_cleans_up(tmp_path, monkeypatch, capsys):
    srv = Server(model_zip(), drops=1)
    monkeypatch.setenv("MODEL_URL", srv.url)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "model"))
    monkeypatch.delenv("MODEL_URL_TOKEN", raising=False)
    try:
        fetch_model.main()
    finally:
        srv.close()
    assert (tmp_path / "model" / "model.onnx").exists()
    assert not (tmp_path / "model.zip.part").exists()
    assert "Model 'tiny' ready" in capsys.readouterr().out
