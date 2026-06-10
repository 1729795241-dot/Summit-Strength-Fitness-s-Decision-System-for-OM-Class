from __future__ import annotations

import csv
import json
import mimetypes
import os
import socket
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote

import summit_inventory_system as system


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_BASE_URL = "https://api.deepseek.com"


def read_csv(name: str) -> list[dict[str, str]]:
    path = DATA_DIR / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def read_json(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def response_payload() -> dict:
    ai_review = read_json("ai_decision_review.json")
    return {
        "ok": bool(ai_review),
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ai_review": ai_review,
        "transfers": read_csv("transfer_recommendations.csv"),
        "kpis": read_csv("kpi_summary.csv"),
        "production": read_csv("production_plan.csv"),
        "policy": read_csv("inventory_policy_outputs.csv"),
        "central_allocation": read_csv("central_allocation.csv"),
        "files": {
            "ai_json": "/outputs/data/ai_decision_review.json",
            "ai_csv": "/outputs/data/ai_decision_review.csv",
            "system_report": "/outputs/reports/simulation_data_and_system_results.md",
        },
    }


def run_system_with_key(api_key: str, model: str, base_url: str) -> dict:
    if not api_key.strip():
        raise RuntimeError("Enter a DeepSeek key before running a fresh review.")

    previous = {
        "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY"),
        "DEEPSEEK_MODEL": os.environ.get("DEEPSEEK_MODEL"),
        "DEEPSEEK_BASE_URL": os.environ.get("DEEPSEEK_BASE_URL"),
    }
    os.environ["DEEPSEEK_API_KEY"] = api_key.strip()
    os.environ["DEEPSEEK_MODEL"] = model.strip() or DEFAULT_MODEL
    os.environ["DEEPSEEK_BASE_URL"] = base_url.strip() or DEFAULT_BASE_URL
    try:
        system.main()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return response_payload()


def json_bytes(payload: dict, status: int = 200) -> tuple[int, bytes, str]:
    return status, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8"


def safe_path(base: Path, relative: str) -> Path | None:
    requested = (base / relative).resolve()
    try:
        requested.relative_to(base.resolve())
    except ValueError:
        return None
    return requested


class Handler(BaseHTTPRequestHandler):
    server_version = "SummitDecisionSystem/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def send_payload(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path == "/":
            self.serve_file(STATIC_DIR / "index.html")
        elif path == "/api/current":
            self.send_payload(*json_bytes(response_payload()))
        elif path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            target = safe_path(STATIC_DIR, rel)
            self.serve_file(target)
        elif path.startswith("/outputs/data/"):
            rel = path.removeprefix("/outputs/data/")
            target = safe_path(DATA_DIR, rel)
            self.serve_file(target)
        elif path.startswith("/outputs/reports/"):
            rel = path.removeprefix("/outputs/reports/")
            target = safe_path(REPORT_DIR, rel)
            self.serve_file(target)
        else:
            self.send_payload(*json_bytes({"ok": False, "error": "Not found"}, 404))

    def do_POST(self) -> None:
        if self.path != "/api/run":
            self.send_payload(*json_bytes({"ok": False, "error": "Not found"}, 404))
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(body)
            result = run_system_with_key(
                payload.get("apiKey", ""),
                payload.get("model", DEFAULT_MODEL),
                payload.get("baseUrl", DEFAULT_BASE_URL),
            )
            self.send_payload(*json_bytes({"ok": True, "data": result}))
        except Exception as exc:
            self.send_payload(*json_bytes({"ok": False, "error": str(exc)}, 400))

    def serve_file(self, path: Path | None) -> None:
        if path is None or not path.exists() or not path.is_file():
            self.send_payload(*json_bytes({"ok": False, "error": "File not found"}, 404))
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix.lower() in {".html", ".css", ".js", ".md", ".json", ".csv"}:
            content_type += "; charset=utf-8"
        self.send_payload(200, path.read_bytes(), content_type)


def find_port(preferred: int = 8765) -> int:
    for port in range(preferred, preferred + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No available local port found.")


def main() -> None:
    port = find_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    print("Summit inventory review is running.")
    print(f"Open: {url}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
