#!/usr/bin/env python3
"""
IPv6 Pool HTTP API Server
==========================

API server cho VM/Server lay va doi IPv6 tu dong.

Endpoints:
    GET  /api/get_ip?worker=vm1_chrome1   → Lay 1 IP
    POST /api/rotate_ip                    → Burn IP cu, lay IP moi
    POST /api/release_ip                   → Tra IP ve pool
    POST /api/burn_ip                      → Danh dau burned
    GET  /api/status                       → Trang thai pool

Chay doc lap:
    python -m ipv6.ipv6_server

Hoac tich hop vao GUI (start_api_server()).
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

# Pool instance - set by start_api_server()
_pool = None
_log_func = print


def set_pool(pool, log_func=print):
    """Set pool instance cho API server."""
    global _pool, _log_func
    _pool = pool
    _log_func = log_func


class IPv6APIHandler(BaseHTTPRequestHandler):
    """HTTP request handler cho IPv6 Pool API."""

    def log_message(self, format, *args):
        """Override de dung log_func thay vi stderr."""
        _log_func(f"[API] {args[0]} {args[1]}")

    def _send_json(self, data: dict, status: int = 200):
        """Gui JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _read_body(self) -> dict:
        """Doc JSON body tu request."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = self.rfile.read(length)
                return json.loads(body)
        except Exception:
            pass
        return {}

    # =====================================================================
    # GET endpoints
    # =====================================================================

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/get_ip":
            self._handle_get_ip(params)
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/ping":
            self._send_json({"ok": True, "time": time.strftime("%H:%M:%S")})
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_get_ip(self, params: dict):
        """GET /api/get_ip?worker=xxx → Lay 1 IP tu pool."""
        if not _pool:
            self._send_json({"error": "Pool not initialized"}, 503)
            return

        worker = params.get("worker", ["unknown"])[0]
        ip = _pool.get_ip()

        if ip:
            # Tim entry de lay them thong tin
            entry = None
            for e in _pool.pool:
                if e["address"] == ip:
                    entry = e
                    break

            _log_func(f"[API] GET_IP: {ip} → {worker}")
            self._send_json({
                "success": True,
                "ip": ip,
                "subnet": entry.get("subnet_hex", "") if entry else "",
                "worker": worker,
            })
        else:
            _log_func(f"[API] GET_IP: EMPTY → {worker}")
            self._send_json({"success": False, "error": "No available IPs"}, 200)

    def _handle_status(self):
        """GET /api/status → Trang thai pool."""
        if not _pool:
            self._send_json({"error": "Pool not initialized"}, 503)
            return

        status = _pool.get_status()
        entries = []
        for e in _pool.pool:
            entries.append({
                "ip": e.get("address", ""),
                "subnet": e.get("subnet_hex", ""),
                "status": e.get("status", ""),
                "use_count": e.get("use_count", 0),
            })

        self._send_json({
            "success": True,
            **status,
            "entries": entries,
        })

    # =====================================================================
    # POST endpoints
    # =====================================================================

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        if path == "/api/rotate_ip":
            self._handle_rotate(body)
        elif path == "/api/release_ip":
            self._handle_release(body)
        elif path == "/api/burn_ip":
            self._handle_burn(body)
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_rotate(self, body: dict):
        """POST /api/rotate_ip {ip, reason, worker} → Burn cu, tra IP moi."""
        if not _pool:
            self._send_json({"error": "Pool not initialized"}, 503)
            return

        ip = body.get("ip", "")
        reason = body.get("reason", "403")
        worker = body.get("worker", "unknown")

        if not ip:
            self._send_json({"error": "Missing 'ip' field"}, 400)
            return

        new_ip = _pool.rotate_ip(ip, reason=reason)
        if new_ip:
            _log_func(f"[API] ROTATE: {ip} → {new_ip} ({worker}, {reason})")
            self._send_json({
                "success": True,
                "old_ip": ip,
                "new_ip": new_ip,
                "worker": worker,
            })
        else:
            _log_func(f"[API] ROTATE FAILED: {ip} ({worker})")
            self._send_json({"success": False, "error": "No available IPs"}, 200)

    def _handle_release(self, body: dict):
        """POST /api/release_ip {ip, worker} → Tra IP ve pool."""
        if not _pool:
            self._send_json({"error": "Pool not initialized"}, 503)
            return

        ip = body.get("ip", "")
        worker = body.get("worker", "unknown")

        if not ip:
            self._send_json({"error": "Missing 'ip' field"}, 400)
            return

        _pool.release_ip(ip)
        _log_func(f"[API] RELEASE: {ip} ({worker})")
        self._send_json({"success": True, "ip": ip})

    def _handle_burn(self, body: dict):
        """POST /api/burn_ip {ip, reason, worker} → Danh dau burned."""
        if not _pool:
            self._send_json({"error": "Pool not initialized"}, 503)
            return

        ip = body.get("ip", "")
        reason = body.get("reason", "403")
        worker = body.get("worker", "unknown")

        if not ip:
            self._send_json({"error": "Missing 'ip' field"}, 400)
            return

        _pool.burn_ip(ip, reason=reason)
        _log_func(f"[API] BURN: {ip} ({worker}, {reason})")
        self._send_json({"success": True, "ip": ip})


# =========================================================================
# SERVER START/STOP
# =========================================================================

_server: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None


def start_api_server(pool, host: str = "0.0.0.0", port: int = 8765, log_func=print) -> bool:
    """
    Start HTTP API server trong background thread.

    Args:
        pool: IPv6Pool instance
        host: Bind address (0.0.0.0 = tat ca interface)
        port: Port (default 8765)
        log_func: Ham log

    Returns:
        True neu start thanh cong
    """
    global _server, _server_thread

    if _server:
        log_func("[API] Server da chay roi!")
        return True

    set_pool(pool, log_func)

    try:
        _server = HTTPServer((host, port), IPv6APIHandler)
        _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _server_thread.start()
        log_func(f"[API] Server started: http://{host}:{port}")
        return True
    except OSError as e:
        log_func(f"[API] Start failed: {e}")
        _server = None
        return False


def stop_api_server():
    """Stop API server."""
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server = None
        _server_thread = None
        _log_func("[API] Server stopped")


def is_running() -> bool:
    """Check API server dang chay."""
    return _server is not None


# =========================================================================
# STANDALONE MODE
# =========================================================================

if __name__ == "__main__":
    import sys
    import argparse
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ipv6 import create_pool

    parser = argparse.ArgumentParser(description="IPv6 Pool HTTP API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8765, help="Port")
    args = parser.parse_args()

    # Load config
    config_file = Path(__file__).parent / "config_test.json"
    if not config_file.exists():
        print(f"[!] Chua co config: {config_file}")
        print(f"    Chay truoc: python -m ipv6.test_pool --detect")
        sys.exit(1)

    with open(config_file, "r") as f:
        config = json.load(f)

    pool = create_pool(config)
    pool.init()

    print(f"\nIPv6 Pool API Server")
    print(f"====================")
    print(f"  http://{args.host}:{args.port}")
    print(f"")
    print(f"Endpoints:")
    print(f"  GET  /api/get_ip?worker=xxx")
    print(f"  POST /api/rotate_ip  {{ip, reason, worker}}")
    print(f"  POST /api/release_ip {{ip, worker}}")
    print(f"  POST /api/burn_ip    {{ip, reason, worker}}")
    print(f"  GET  /api/status")
    print(f"  GET  /api/ping")
    print(f"\nCtrl+C de dung")

    start_api_server(pool, args.host, args.port)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDang dung...")
        stop_api_server()
