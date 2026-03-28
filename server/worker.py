"""
Chrome Worker Process - Chay 1 Chrome instance trong 1 CMD rieng.

Usage:
    python server/worker.py --index 0
    python server/worker.py --index 1
    python server/worker.py --index 2

Moi worker:
1. Lay config tu server (account, ipv6, chrome path, port)
2. Setup Chrome (login, tao project)
3. Dang ky voi server
4. Loop: lay task → xu ly → bao ket qua
"""
import sys
import os
import time
import json
import argparse
import traceback
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOL_DIR))

# Server URL (main server)
SERVER_URL = "http://127.0.0.1:5000"

import requests as http_requests


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "", "OK": "[OK]", "WARN": "[WARN]", "ERROR": "[ERROR]"}
    print(f"  {prefix.get(level, '')} {msg}")


def get_config(index: int) -> dict:
    """Lay config tu server."""
    try:
        r = http_requests.get(f"{SERVER_URL}/internal/worker-config?index={index}", timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            log(f"Config error: {r.status_code} - {r.text}", "ERROR")
            return {}
    except Exception as e:
        log(f"Cannot connect to server: {e}", "ERROR")
        return {}


def register(index: int, account: str, port: int, status: str, **kwargs) -> str:
    """Dang ky worker voi server. Returns worker_id."""
    try:
        data = {
            "index": index,
            "account": account,
            "port": port,
            "status": status,
        }
        data.update(kwargs)
        r = http_requests.post(f"{SERVER_URL}/internal/register", json=data, timeout=10)
        if r.status_code == 200:
            return r.json().get("worker_id", f"chrome-{index}")
        return f"chrome-{index}"
    except Exception as e:
        log(f"Register error: {e}", "WARN")
        return f"chrome-{index}"


def get_next_task(worker_id: str) -> dict:
    """Lay task tiep theo tu server."""
    try:
        r = http_requests.get(f"{SERVER_URL}/internal/next-task?worker_id={worker_id}", timeout=10)
        if r.status_code == 200:
            return r.json().get("task")
        return None
    except Exception:
        return None


def report_done(worker_id: str, task_id: str, success: bool, result=None, error=""):
    """Bao hoan thanh hoac loi."""
    try:
        http_requests.post(f"{SERVER_URL}/internal/task-done", json={
            "worker_id": worker_id,
            "task_id": task_id,
            "success": success,
            "result": result,
            "error": error,
        }, timeout=30)
    except Exception as e:
        log(f"Report error: {e}", "WARN")


def send_heartbeat(worker_id: str, status: str = "ready"):
    """Gui heartbeat ve server."""
    try:
        http_requests.post(f"{SERVER_URL}/internal/heartbeat", json={
            "worker_id": worker_id,
            "status": status,
        }, timeout=5)
    except Exception:
        pass


def main():
    global SERVER_URL

    parser = argparse.ArgumentParser(description="Chrome Worker Process")
    parser.add_argument("--index", type=int, required=True, help="Worker index (0-4)")
    parser.add_argument("--server", type=str, default=SERVER_URL, help="Server URL")
    args = parser.parse_args()

    SERVER_URL = args.server
    index = args.index

    print("=" * 50)
    print(f"  CHROME WORKER {index}")
    print("=" * 50)
    print()

    # 1. Lay config tu server
    log(f"Lay config tu server {SERVER_URL}...")

    # Retry connect to server (server co the chua khoi dong xong)
    config = {}
    for attempt in range(30):
        config = get_config(index)
        if config:
            break
        if attempt < 29:
            log(f"Server chua san sang, thu lai ({attempt + 1}/30)...", "WARN")
            time.sleep(2)

    if not config:
        log("Khong lay duoc config tu server! Thoat.", "ERROR")
        return

    chrome_path = config.get("chrome_path", "")
    port = config.get("port", 19222 + index)
    account = config.get("account")
    ipv6 = config.get("ipv6", "")

    log(f"Chrome: {config.get('chrome_folder', '?')}")
    log(f"Port: {port}")
    log(f"Account: {account['id'] if account else 'no-account'}")
    log(f"IPv6: {ipv6 or 'no-ipv6'}")
    print()

    # 2. Dang ky voi server (status = starting)
    worker_id = register(index, account['id'] if account else '', port, 'starting')
    log(f"Registered as {worker_id}")

    # 3. Setup Chrome
    log("Setup Chrome session...")
    from server.chrome_session import ChromeSession

    session = ChromeSession(
        chrome_portable_path=chrome_path,
        port=port,
    )
    if account:
        session._account = account

    setup_ok = session.setup()

    if not setup_ok:
        log("Chrome setup FAILED!", "ERROR")
        register(index, account['id'] if account else '', port, 'failed')
        return

    log(f"Chrome READY! Project: {session.project_url}", "OK")
    print()

    # 4. Dang ky lai (status = ready)
    worker_id = register(index, account['id'] if account else '', port, 'ready')
    log(f"Worker {worker_id} READY - bat dau xu ly tasks...")
    print()

    # 5. Main loop - lay task → xu ly → bao ket qua
    total_completed = 0
    total_failed = 0
    last_heartbeat = time.time()

    while True:
        # Heartbeat moi 20s
        if time.time() - last_heartbeat > 20:
            send_heartbeat(worker_id, 'ready')
            last_heartbeat = time.time()

        # Lay task
        task = get_next_task(worker_id)

        if not task:
            time.sleep(1)
            continue

        task_id = task.get('task_id', '?')
        prompt = task.get('prompt', '')
        vm_id = task.get('vm_id', '?')

        print(f"\n[TASK] {task_id[:8]}... | VM: {vm_id} | Prompt: {prompt[:50]}...")

        try:
            # Check session
            if not session or not session.ready:
                log("Session not ready, re-setup...", "WARN")
                session = ChromeSession(
                    chrome_portable_path=chrome_path,
                    port=port,
                )
                if account:
                    session._account = account
                if not session.setup():
                    raise RuntimeError("Chrome session setup failed")
                register(index, account['id'] if account else '', port, 'ready')

            # Tao anh
            result = session.generate_image(
                client_bearer_token=task.get('bearer_token', ''),
                client_project_id=task.get('project_id', ''),
                client_prompt=prompt,
                model_name=task.get('model_name', 'GEM_PIX_2'),
                aspect_ratio=task.get('aspect_ratio', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
                seed=task.get('seed'),
            )

            if result and 'media' in result:
                total_completed += 1
                duration = "?"
                log(f"OK: {task_id[:8]}... | Done: {total_completed}", "OK")
                report_done(worker_id, task_id, success=True, result=result)
            elif result and 'error' in result:
                total_failed += 1
                err = str(result.get('error', ''))[:100]
                log(f"FAIL: {task_id[:8]}... | {err}", "ERROR")
                report_done(worker_id, task_id, success=False, error=err)
            else:
                total_failed += 1
                log(f"FAIL: {task_id[:8]}... | No media", "ERROR")
                report_done(worker_id, task_id, success=False, error="No media in response")

        except Exception as e:
            total_failed += 1
            traceback.print_exc()
            log(f"ERROR: {task_id[:8]}... | {str(e)[:80]}", "ERROR")
            report_done(worker_id, task_id, success=False, error=str(e)[:200])

        # Update stats
        register(index, account['id'] if account else '', port, 'ready',
                 total_completed=total_completed, total_failed=total_failed)


if __name__ == '__main__':
    main()
