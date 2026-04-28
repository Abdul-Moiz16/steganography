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
import queue
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

# Force UTF-8 console output on Windows (avoids UnicodeEncodeError on
# restrictive codepages such as cp1253).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).parent.resolve()
PUBLIC_DIR = PROJECT_ROOT / "public"
RUNS_DIR = PROJECT_ROOT / "runs"
RUNNING_JOBS: dict[str, dict] = {}  # job_id -> {'proc': Popen, 'run_id': str}
_JOBS_LOCK = threading.Lock()
_SERVER_PORT: int = 0  # set after bind; used to make run IDs unique per instance

# ── Cross-instance sync via filesystem polling ─────────────────────────────
_SSE_CLIENTS: list = []          # list of queue.Queue, one per connected browser
_SSE_LOCK = threading.Lock()


def _runs_mtime() -> float:
    """Return the latest mtime across RUNS_DIR and its immediate children."""
    try:
        t = RUNS_DIR.stat().st_mtime
        for child in RUNS_DIR.iterdir():
            if child.is_dir():
                t = max(t, child.stat().st_mtime)
        return t
    except OSError:
        return 0.0


def _broadcast(event: str, data: str) -> None:
    with _SSE_LOCK:
        dead = []
        for q in _SSE_CLIENTS:
            try:
                q.put_nowait((event, data))
            except Exception:
                dead.append(q)
        for q in dead:
            _SSE_CLIENTS.remove(q)


def _watch_runs_dir() -> None:
    """Background thread: poll RUNS_DIR every 2 s; broadcast 'refresh' on change."""
    last = _runs_mtime()
    while True:
        threading.Event().wait(2)
        now = _runs_mtime()
        if now != last:
            last = now
            _broadcast("refresh", "runs")

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
        # .meta.json written at launch — provides profile/engine before config.json exists
        meta = _read_json(d / ".meta.json")
        if meta and not config.get("profile"):
            config.setdefault("profile", meta.get("profile"))
        if meta:
            for key in ("payload_mode", "hardcoded_payload_bytes", "hardcoded_payload_max_bytes"):
                if key in meta:
                    config.setdefault(key, meta.get(key))
        # Last resort: parse profile from run ID (format: {profile}_{timestamp}_p{port})
        if not config.get("profile"):
            for known in ("prototype", "full_design"):
                if d.name.startswith(known):
                    config["profile"] = known
                    break
        det_metrics = _read_csv(d / "metrics" / "detector_metrics.csv")
        has_results = bool(det_metrics)
        best_auc = None
        if has_results:
            aucs = [float(r["roc_auc"]) for r in det_metrics if r.get("roc_auc")]
            if aucs:
                best_auc = max(aucs)
        # Source effect delta (ML avg AUC - Real avg AUC)
        source_delta = None
        src_metrics = _read_csv(d / "metrics" / "source_metrics.csv")
        if src_metrics:
            real_aucs = [float(r["roc_auc"]) for r in src_metrics if r.get("source") == "real" and r.get("roc_auc")]
            ml_aucs = [float(r["roc_auc"]) for r in src_metrics if r.get("source") != "real" and r.get("roc_auc")]
            if real_aucs and ml_aucs:
                source_delta = sum(ml_aucs) / len(ml_aucs) - sum(real_aucs) / len(real_aucs)
        # .running marker written at launch, removed on completion/kill — visible to all instances
        is_active = (d / ".running").exists()
        is_killed = (d / ".killed").exists()
        runs.append({
            "id": d.name,
            "config": config,
            "has_results": has_results,
            "best_auc": best_auc,
            "source_delta": source_delta,
            "n_detectors": len({r["detector"] for r in det_metrics}),
            "is_active": is_active,
            "is_killed": is_killed,
        })
    return runs


def _get_predictions(run_id: str) -> list:
    run_dir = RUNS_DIR / run_id
    pred_path = run_dir / "predictions" / "predictions.csv"
    if not pred_path.exists():
        return []
    return _read_csv(pred_path)


def _get_run_detail(run_id: str) -> dict:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        return {}
    config = _read_json(run_dir / "config.json")
    # Merge .meta.json fallback (profile/engine written at launch before config.json exists)
    meta = _read_json(run_dir / ".meta.json")
    if meta and not config.get("profile"):
        config.setdefault("profile", meta.get("profile"))
    if meta:
        for key in ("payload_mode", "hardcoded_payload_bytes", "hardcoded_payload_max_bytes"):
            if key in meta:
                config.setdefault(key, meta.get(key))
    # Last resort: parse profile from run ID (format: {profile}_{timestamp}_p{port})
    if not config.get("profile"):
        for known in ("prototype", "full_design"):
            if run_id.startswith(known):
                config["profile"] = known
                break
    det_metrics = _read_csv(run_dir / "metrics" / "detector_metrics.csv")
    src_metrics = _read_csv(run_dir / "metrics" / "source_metrics.csv")
    cond_metrics = _read_csv(run_dir / "metrics" / "condition_metrics.csv")
    quality_metrics = _read_csv(run_dir / "metrics" / "quality_metrics.csv")
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
        "metrics": {"detector": det_metrics, "source": src_metrics, "condition": cond_metrics, "quality": quality_metrics},
        "covers": covers,
        "has_results": bool(det_metrics),
        "is_killed": (run_dir / ".killed").exists(),
        "is_active": (run_dir / ".running").exists(),
    }


def _payload_launch_config(body: dict, profile: str) -> tuple[dict, list[str], str | None]:
    from src.pipeline.config import PAYLOAD_MODE_HARDCODED, PAYLOAD_MODE_RANDOM, PipelineConfig

    payload_mode = body.get("payload_mode", body.get("payloadMode", PAYLOAD_MODE_RANDOM))
    if payload_mode not in (PAYLOAD_MODE_RANDOM, PAYLOAD_MODE_HARDCODED):
        raise ValueError("invalid payload mode")

    meta = {"payload_mode": payload_mode}
    args = ["--payload-mode", payload_mode]
    if payload_mode == PAYLOAD_MODE_RANDOM:
        return meta, args, None

    payload_text = body.get("hardcoded_payload", body.get("hardcodedPayload", ""))
    config = PipelineConfig.from_profile(PROJECT_ROOT, profile)
    payload_bytes = config.validate_hardcoded_payload_text(payload_text)
    meta.update(
        {
            "hardcoded_payload_bytes": len(payload_bytes),
            "hardcoded_payload_max_bytes": config.min_plaintext_payload_bytes,
        }
    )
    return meta, args, payload_text


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
        elif p.startswith("/api/runs/") and p.endswith("/predictions"):
            run_id = p[len("/api/runs/"):-len("/predictions")]
            self._json(_get_predictions(run_id))
        elif p == "/api/image":
            self._serve_image(qs.get("path", [""])[0])
        elif p == "/api/system/check":
            self._system_check()
        elif p == "/api/events":
            self._sse_events()
        elif p == "/api/proposal-pdf":
            self._serve_proposal_pdf()
        elif p.startswith("/api/pipeline/stream/"):
            self._sse_stream(p[len("/api/pipeline/stream/"):])
        else:
            self._err(404, "not found")

    def do_POST(self):
        if self.path == "/api/pipeline/start":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else {}
            self._start_pipeline(body)
        elif self.path.startswith("/api/pipeline/kill/"):
            job_id = self.path[len("/api/pipeline/kill/"):]
            self._kill_job(job_id)
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

    def _serve_proposal_pdf(self):
        pdf_path = (PROJECT_ROOT / "docs" / "proposals" / "proposal_updated_3.pdf").resolve()
        if not pdf_path.exists():
            return self._err(404, "proposal PDF not found")
        data = pdf_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", "inline; filename=\"proposal.pdf\"")
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def _start_pipeline(self, body: dict):
        import datetime
        profile = body.get("profile", "prototype")
        engine = body.get("engine", "stub")
        try:
            payload_meta, payload_args, payload_text = _payload_launch_config(body, profile)
        except ValueError as exc:
            return self._err(400, str(exc))
        job_id = uuid.uuid4().hex[:8]
        # Embed port in run ID so two viewer instances never collide on the filesystem
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"{profile}_{ts}_p{_SERVER_PORT}"
        # Pre-create the run directory and write lightweight markers so all instances
        # can display correct status/config before config.json is written by run.py
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / ".running").write_text(str(_SERVER_PORT))
        if payload_text is not None:
            payload_file = run_dir / ".hardcoded_payload.txt"
            payload_file.write_text(payload_text, encoding="utf-8")
            payload_args.extend(["--hardcoded-payload-file", str(payload_file)])
        import json as _json
        (run_dir / ".meta.json").write_text(_json.dumps({"profile": profile, "engine": engine, **payload_meta}))
        cmd = [
            sys.executable, str(PROJECT_ROOT / "run.py"), profile,
            "--ml-engine", engine, "--run-id", run_id,
            *payload_args,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(PROJECT_ROOT),
        )
        with _JOBS_LOCK:
            RUNNING_JOBS[job_id] = {"proc": proc, "run_id": run_id}
        self._json({"job_id": job_id, "run_id": run_id})

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
        # Refuse to delete a run that is currently being generated by any instance
        with _JOBS_LOCK:
            active_run_ids = {v["run_id"] for v in RUNNING_JOBS.values()}
        if run_id in active_run_ids:
            return self._err(409, "run is currently active — kill it first")
        try:
            shutil.rmtree(run_dir)
            self._json({"deleted": run_id})
        except Exception as exc:
            self._err(500, f"failed to delete: {exc}")

    def _kill_job(self, job_id: str):
        with _JOBS_LOCK:
            entry = RUNNING_JOBS.get(job_id)
        if not entry:
            return self._err(404, "job not found or already finished")
        try:
            entry["proc"].kill()
            with _JOBS_LOCK:
                RUNNING_JOBS.pop(job_id, None)
            try:
                run_dir = RUNS_DIR / entry["run_id"]
                (run_dir / ".running").unlink(missing_ok=True)
                (run_dir / ".killed").write_text("")
            except Exception:
                pass
            self._json({"killed": job_id})
        except Exception as exc:
            self._err(500, str(exc))

    def _system_check(self):
        import importlib.util
        import importlib.metadata
        import platform
        python_version = platform.python_version()
        python_ok = sys.version_info >= (3, 9)
        checks = [
            ("Pillow",          "pillow",           "PIL",      True),
            ("numpy",           "numpy",            "numpy",    True),
            ("scipy",           "scipy",            "scipy",    True),
            ("scikit-image",    "scikit-image",     "skimage",  True),
            ("scikit-learn",    "scikit-learn",     "sklearn",  True),
            ("torch",           "torch",            "torch",    False),
            ("diffusers",       "diffusers",        "diffusers",False),
            ("transformers",    "transformers",     "transformers",False),
            ("accelerate",      "accelerate",       "accelerate",False),
            ("safetensors",     "safetensors",      "safetensors",False),
            ("huggingface_hub", "huggingface-hub",  "huggingface_hub",False),
            ("tqdm",            "tqdm",             "tqdm",     True),
            ("matplotlib",      "matplotlib",       "matplotlib",True),
            ("cryptography",    "cryptography",     "cryptography",True),
        ]
        packages = []
        for display, pkg_name, import_name, required in checks:
            spec = importlib.util.find_spec(import_name)
            installed = spec is not None
            version = None
            if installed:
                try:
                    version = importlib.metadata.version(pkg_name)
                except Exception:
                    pass
            packages.append({"name": display, "installed": installed, "version": version, "required": required})
        all_core_ok = python_ok and all(p["installed"] for p in packages if p["required"])
        self._json({"python_version": python_version, "python_ok": python_ok, "packages": packages, "all_ok": all_core_ok})

    def _sse_events(self):
        """Long-lived SSE stream for cross-instance sync events (e.g. runs directory changed)."""
        q: queue.Queue = queue.Queue(maxsize=32)
        with _SSE_LOCK:
            _SSE_CLIENTS.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            # Send an initial heartbeat so the browser knows the connection is live
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    event, data = q.get(timeout=25)
                    self.wfile.write(f"event: {event}\ndata: {data}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Keepalive comment every 25 s to prevent proxy timeouts
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _SSE_LOCK:
                try:
                    _SSE_CLIENTS.remove(q)
                except ValueError:
                    pass

    def _sse_stream(self, job_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with _JOBS_LOCK:
            entry = RUNNING_JOBS.get(job_id)
        if not entry:
            try:
                self.wfile.write(b"event: error\ndata: job not found\n\n")
                self.wfile.flush()
            except Exception:
                pass
            return
        proc = entry["proc"]
        run_id = entry["run_id"]
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
            # Remove .running marker so other instances know this run is done
            try:
                (RUNS_DIR / run_id / ".running").unlink(missing_ok=True)
            except Exception:
                pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Stego Explorer — pipeline run browser")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    port = args.port
    server = None
    for attempt in range(16):
        try:
            server = ThreadedHTTPServer(("", port), Handler)
            break
        except OSError:
            if attempt == 0 and port == args.port:
                print(f"  Port {port} in use — scanning for a free port…")
            port += 1
    if server is None:
        print(f"  Error: could not bind to any port in {args.port}–{port - 1}.")
        raise SystemExit(1)

    global _SERVER_PORT
    _SERVER_PORT = port

    # Start background thread that watches RUNS_DIR and pushes refresh events
    watcher = threading.Thread(target=_watch_runs_dir, daemon=True)
    watcher.start()

    url = f"http://localhost:{port}"
    print(f"\n  ╔══════════════════════════════════════╗")
    print(f"  ║  Stego Explorer  →  {url}  ║")
    print(f"  ╚══════════════════════════════════════╝")
    print(f"\n  Project root : {PROJECT_ROOT}")
    print(f"  Runs dir     : {RUNS_DIR}")
    if port != args.port:
        print(f"  Note: default port {args.port} was busy; using {port} instead.")
    print(f"  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()  # url already uses the bound port

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
