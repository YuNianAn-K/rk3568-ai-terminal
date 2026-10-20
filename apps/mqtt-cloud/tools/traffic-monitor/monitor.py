"""On-demand read-only dashboard with opt-in Windows encrypted credentials."""
import argparse
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import webbrowser

from model import month_key, quota_view

ROOT = Path(__file__).resolve().parents[4]
LOCAL = ROOT / "local/ecs-monitor"
WEB = Path(__file__).with_name("web")


class Monitor:
    def __init__(self, config, credential_store=None):
        self.config = config
        self.credential_store = credential_store
        self.reader = None
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.last_touch = time.monotonic()
        self.generation = 0
        self.state = {"connected": False, "message": "尚未接入只读凭据，实时数据未知",
                      "metrics": None, "metrics_at": None, "bill": None, "bill_at": None,
                      "bill_error": "尚未查询", "guard_enabled": False,
                      "credential_saved": bool(credential_store and credential_store.exists()),
                      "credential_notice": ""}

    def connect(self, data, *, restoring=False):
        from provider import CloudReader
        allowed = {"access_id", "secret", "token", "remember"}
        if not isinstance(data, dict) or set(data) - allowed or type(data.get("remember", False)) is not bool:
            raise ValueError("invalid credentials")
        credentials = {key: data.get(key, "") for key in ("access_id", "secret", "token")}
        if not all(isinstance(v, str) for v in credentials.values()):
            raise ValueError("invalid credentials")
        reader = CloudReader(self.config, credentials["access_id"], credentials["secret"], credentials["token"])
        with self.lock:
            if not restoring:
                if data.get("remember"):
                    if not self.credential_store:
                        raise ValueError("credential storage unavailable")
                    self.credential_store.save(credentials)
                elif self.credential_store:
                    # A one-time connection must not restore a different old key on restart.
                    self.credential_store.forget()
            self.generation += 1
            self.reader = reader
            self.state.update(connected=True, message="凭据已载入内存，正在核验权限与数据",
                              metrics=None, metrics_at=None, bill=None, bill_at=None, bill_error="正在查询",
                              credential_saved=bool(self.credential_store and self.credential_store.exists()),
                              credential_notice="")
        self.wake.set()

    def restore_saved(self):
        if not self.credential_store or not self.credential_store.exists():
            return
        try:
            self.connect(self.credential_store.load(), restoring=True)
        except Exception:
            self.state["credential_notice"] = "已保存凭据无法载入，请重新接入或忘记凭据；不会改用明文保存。"

    def disconnect(self):
        with self.lock:
            self.generation += 1
            self.reader = None
            self.state.update(connected=False, message="已停止当前连接；旧值仅供参考")

    def forget_credentials(self):
        with self.lock:
            if self.credential_store:
                self.credential_store.forget()
            self.disconnect()
            self.state.update(credential_saved=False, credential_notice="已忘记本机凭据并断开连接，下次需重新接入。")

    def snapshot(self):
        now = time.time()
        with self.lock:
            result = json.loads(json.dumps(self.state))
        result.update(month=month_key(now), public_ip=self.config["public_ip"], region="华南1（深圳）",
                      quota_gb=20, alerts_gb=[10, 15, 18], billing_delay_hours=24)
        metrics = result.get("metrics")
        if metrics and result.get("metrics_month") != result["month"]:
            result["metrics"] = metrics = None
        if result.get("bill_month") != result["month"]:
            result["bill"] = None
        if metrics:
            for values in metrics.values():
                if not result["connected"] or not values["latest_at"] or now - values["latest_at"] > 180:
                    values["bps"] = None
        # Static verified observation is visibly separate from API results.
        observed = self.config.get("observation")
        result["observation"] = observed if observed and observed.get("month") == result["month"] else None
        used = metrics["out"]["month_gb"] if metrics else None
        result["quota_estimate"] = quota_view(used)
        result["quota_estimate"]["scope"] = "仅此实例已观测流量；未核实账号其他资源，不是准确剩余额度"
        result["metrics_stale"] = not metrics or not result["connected"] or now - (result["metrics_at"] or 0) > 180
        return result

    def run(self):
        next_metric, next_bill, previous = 0, 0, -1
        while not self.stop.is_set():
            if time.monotonic() - self.last_touch > 120:
                self.stop.set()
                break
            with self.lock:
                reader, generation = self.reader, self.generation
            if generation != previous:
                next_metric, next_bill, previous = 0, 0, generation
            now = time.time()
            if reader and now >= next_metric:
                try:
                    values = reader.metrics(now)
                    with self.lock:
                        if generation == self.generation:
                            self.state.update(metrics=values, metrics_at=time.time(), metrics_month=month_key(now),
                                              message="云监控已更新；缺失区间不补零，非计费计量")
                except Exception:
                    # Never log SDK exceptions: they can contain signed URLs/IDs.
                    with self.lock:
                        if generation == self.generation:
                            self.state["message"] = "监控查询失败：请核对只读权限、凭据有效期或网络；旧值不代表当前状态"
                next_metric = time.time() + 60
            if reader and now >= next_bill and not self.stop.is_set():
                try:
                    bill = reader.bills(now)
                    with self.lock:
                        if generation == self.generation:
                            self.state.update(bill=bill, bill_at=time.time(), bill_month=month_key(now), bill_error="")
                except Exception:
                    with self.lock:
                        if generation == self.generation:
                            self.state["bill_error"] = "账单查询失败：旧费用仅供参考，请检查CDT只读账单权限"
                next_bill = time.time() + 900
            self.wake.wait(1)
            self.wake.clear()


def make_handler(monitor, session):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, data, media="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", media)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def authorized(self):
            supplied = self.headers.get("X-Monitor-Session", "")
            return self.valid_host() and len(supplied) < 256 and secrets.compare_digest(supplied, session)

        def do_GET(self):
            if not self.valid_host():
                self.send(403, {"error": "host_rejected"})
                return
            if self.path == "/api/state":
                if not self.authorized():
                    self.send(403, {"error": "session_required"})
                    return
                monitor.last_touch = time.monotonic()
                self.send(200, monitor.snapshot())
                return
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            entry = files.get(self.path)
            if not entry:
                self.send(404, {"error": "not_found"})
                return
            self.send(200, (WEB / entry[0]).read_bytes(), entry[1])

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.authorized() or self.headers.get("Origin") != origin:
                self.send(403, {"error": "origin_or_session_rejected"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 8192 or self.headers.get("Transfer-Encoding"):
                    raise ValueError()
                data = json.loads(self.rfile.read(length) or b"{}")
                if self.path == "/api/connect":
                    monitor.connect(data)
                elif self.path == "/api/disconnect":
                    monitor.disconnect()
                elif self.path == "/api/forget":
                    monitor.forget_credentials()
                elif self.path == "/api/stop":
                    monitor.disconnect()
                    monitor.stop.set()
                else:
                    self.send(404, {"error": "not_found"})
                    return
                self.send(200, {"ok": True})
            except Exception:
                self.send(400, {"error": "invalid_request_or_credentials"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(LOCAL / "config.json"))
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    session = secrets.token_urlsafe(32)
    from credential_store import CredentialStore
    monitor = Monitor(config, CredentialStore(LOCAL / "credentials.dpapi", config))
    server = ThreadingHTTPServer(("127.0.0.1", config.get("port", 8796)), make_handler(monitor, session))
    server.daemon_threads = True
    server.timeout = 1
    # Capability URL is local-only, short-lived; contains no cloud credentials.
    url = f"http://127.0.0.1:{server.server_port}/#session={session}"
    LOCAL.mkdir(parents=True, exist_ok=True)
    runtime = {"pid": os.getpid(), "url": url, "started_at": time.time()}
    (LOCAL / "session.json").write_text(json.dumps(runtime), encoding="utf-8")
    monitor.restore_saved()
    worker = threading.Thread(target=monitor.run, daemon=True)
    worker.start()
    if not args.no_open:
        edge = config.get("edge")
        if edge and Path(edge).is_file():
            import subprocess
            subprocess.Popen([edge, "--app=" + url], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            webbrowser.open(url)
    try:
        while not monitor.stop.is_set():
            server.handle_request()
    finally:
        monitor.disconnect()
        monitor.stop.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
