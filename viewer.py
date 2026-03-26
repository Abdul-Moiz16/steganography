#!/usr/bin/env python3
"""
Stego Explorer — self-contained pipeline run browser and launcher.

Usage
-----
    python viewer.py                  # Opens http://localhost:8765
    python viewer.py --port 9000      # Custom port
    python viewer.py --no-browser     # Don't auto-open browser
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).parent.resolve()
PUBLIC_DIR = PROJECT_ROOT / "public"
RUNS_DIR = PROJECT_ROOT / "runs"
RUNNING_JOBS: dict[str, subprocess.Popen] = {}
_JOBS_LOCK = threading.Lock()

# Mime types for static files
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _list_runs() -> list[dict]:
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        config = _read_json(d / "config.json")
        det_metrics = _read_csv(d / "metrics" / "detector_metrics.csv")
        has_results = bool(det_metrics)
        best_auc = None
        if has_results:
            aucs = [float(r["roc_auc"]) for r in det_metrics if r.get("roc_auc")]
            if aucs:
                best_auc = max(aucs)
        runs.append({
            "id": d.name,
            "config": config,
            "has_results": has_results,
            "best_auc": best_auc,
            "n_detectors": len({r["detector"] for r in det_metrics}),
        })
    return runs


def _get_run_detail(run_id: str) -> dict:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {}
    config = _read_json(run_dir / "config.json")
    det_metrics = _read_csv(run_dir / "metrics" / "detector_metrics.csv")
    src_metrics = _read_csv(run_dir / "metrics" / "source_metrics.csv")
    cond_metrics = _read_csv(run_dir / "metrics" / "condition_metrics.csv")
    covers_rows = _read_csv(run_dir / "manifests" / "covers.csv")

    # Group covers by group_id
    cover_map: dict[str, dict] = {}
    for row in covers_rows:
        gid = row["group_id"]
        if gid not in cover_map:
            cover_map[gid] = {"group_id": gid, "caption": row.get("caption_text", ""), "sources": {}}
        cover_map[gid]["sources"][row["source"]] = row.get("spatial_path", "")

    covers = sorted(cover_map.values(), key=lambda x: int(x["group_id"]))
    return {
        "config": config,
        "metrics": {"detector": det_metrics, "source": src_metrics, "condition": cond_metrics},
        "covers": covers,
        "has_results": bool(det_metrics),
    }


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        p, qs = parsed.path, parse_qs(parsed.query)

        # Serve index.html for root
        if p in ("/", "/index.html"):
            self._serve_static(PUBLIC_DIR / "index.html")
        # Serve static files from /public/
        elif p.startswith("/public/"):
            rel = p[len("/public/"):]
            self._serve_static(PUBLIC_DIR / rel)
        # API routes
        elif p == "/api/runs":
            self._json(_list_runs())
        elif p.startswith("/api/runs/") and p.endswith("/detail"):
            self._json(_get_run_detail(p[10:-7]))
        elif p == "/api/image":
            self._serve_image(qs.get("path", [""])[0])
        elif p.startswith("/api/pipeline/stream/"):
            self._sse_stream(p[len("/api/pipeline/stream/"):])
        else:
            self._err(404, "not found")

    def do_POST(self):
        if self.path == "/api/pipeline/start":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else {}
            self._start_pipeline(body)
        else:
            self._err(404, "not found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        p = parsed.path
        # DELETE /api/runs/<run_id>
        if p.startswith("/api/runs/") and p.count("/") == 3:
            run_id = p[len("/api/runs/"):]
            self._delete_run(run_id)
        else:
            self._err(404, "not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Response helpers ──────────────────────────────────────────────────────

    def _serve_static(self, path: Path):
        safe = path.resolve()
        if not str(safe).startswith(str(PUBLIC_DIR)):
            return self._err(403, "forbidden")
        if not safe.exists() or not safe.is_file():
            return self._err(404, "not found")
        ctype = _MIME.get(safe.suffix.lower(), "application/octet-stream")
        data = safe.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if ctype.startswith("text/") or ctype.startswith("application/javascript"):
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj):
        data = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _err(self, code, msg):
        data = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_image(self, rel_path: str):
        if not rel_path:
            return self._err(400, "missing path")
        safe = (PROJECT_ROOT / rel_path).resolve()
        if not str(safe).startswith(str(PROJECT_ROOT)):
            return self._err(403, "forbidden")
        if not safe.exists():
            return self._err(404, "not found")
        ctype = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
            safe.suffix.lower(), "application/octet-stream"
        )
        data = safe.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _start_pipeline(self, body: dict):
        profile = body.get("profile", "prototype")
        engine = body.get("engine", "stub")
        job_id = uuid.uuid4().hex[:8]
        proc = subprocess.Popen(
            [sys.executable, str(PROJECT_ROOT / "run.py"), profile, "--ml-engine", engine],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(PROJECT_ROOT),
        )
        with _JOBS_LOCK:
            RUNNING_JOBS[job_id] = proc
        self._json({"job_id": job_id})

    def _delete_run(self, run_id: str):
        # Sanitize: only allow alphanumeric, underscore, hyphen
        if not run_id or not all(c.isalnum() or c in "_-" for c in run_id):
            return self._err(400, "invalid run id")
        run_dir = RUNS_DIR / run_id
        if not run_dir.exists() or not run_dir.is_dir():
            return self._err(404, "run not found")
        # Safety: ensure it's actually under RUNS_DIR
        if not str(run_dir.resolve()).startswith(str(RUNS_DIR.resolve())):
            return self._err(403, "forbidden")
        try:
            shutil.rmtree(run_dir)
            self._json({"deleted": run_id})
        except Exception as exc:
            self._err(500, f"failed to delete: {exc}")

    def _sse_stream(self, job_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with _JOBS_LOCK:
            proc = RUNNING_JOBS.get(job_id)
        if not proc:
            try:
                self.wfile.write(b"event: error\ndata: job not found\n\n")
                self.wfile.flush()
            except Exception:
                pass
            return
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                self.wfile.flush()
            proc.wait()
            self.wfile.write(f"event: done\ndata: {proc.returncode}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _JOBS_LOCK:
                RUNNING_JOBS.pop(job_id, None)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Stego Explorer — pipeline run browser")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    server = ThreadedHTTPServer(("", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"\n  ╔══════════════════════════════════════╗")
    print(f"  ║  Stego Explorer  →  {url}  ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"\n  Project root : {PROJECT_ROOT}")
    print(f"  Runs dir     : {RUNS_DIR}")
    print(f"  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
