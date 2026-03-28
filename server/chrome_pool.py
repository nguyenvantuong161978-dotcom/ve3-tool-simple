"""
Chrome Pool - Quan ly nhieu Chrome instances song song.

Moi Chrome:
- 1 Chrome Portable folder rieng
- 1 Google account rieng (tu sheet SERVER col B)
- 1 IPv6 rieng (tu sheet SERVER col C) [optional]
- 1 debug port rieng (19222, 19223, ...)
- 1 queue worker thread rieng

5 Chrome Portable folders:
1. GoogleChromePortable/
2. GoogleChromePortable - Copy/
3. GoogleChromePortable - Copy (2)/
4. GoogleChromePortable - Copy (3)/
5. GoogleChromePortable - Copy (4)/

Architecture:
- Shared task queue (FIFO)
- N Chrome workers, moi worker co 1 thread pull tu queue chung
- Worker nao ranh se lay task tiep theo
"""
import sys
import time
import threading
import traceback
from pathlib import Path
from typing import List, Dict, Optional, Callable

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent.parent

# Chrome Portable folder names (relative to TOOL_DIR)
CHROME_FOLDERS = [
    "GoogleChromePortable",
    "GoogleChromePortable - Copy",
    "GoogleChromePortable - Copy (2)",
    "GoogleChromePortable - Copy (3)",
    "GoogleChromePortable - Copy (4)",
]

# Base port for Chrome debug
BASE_PORT = 19222


def get_server_config() -> List[Dict]:
    """
    Doc cau hinh server tu Google Sheet "SERVER".
    Moi dong = 1 Chrome instance:
      - Col B: tai khoan (format: email|password|2fa)
      - Col C: IPv6 address

    Returns: [{"account": {"id":..., "password":..., "totp_secret":...}, "ipv6": "..."}, ...]
    """
    try:
        sys.path.insert(0, str(TOOL_DIR))
        from google_login import load_gsheet_client, parse_accounts_cell, col_letter_to_index

        gc, spreadsheet_name = load_gsheet_client()
        if not gc:
            print("[SERVER] Khong load duoc Google Sheet client")
            return []

        ws = gc.open(spreadsheet_name).worksheet("SERVER")
        all_data = ws.get_all_values()

        if not all_data:
            print("[SERVER] Sheet 'SERVER' trong!")
            return []

        col_b = col_letter_to_index("B")  # = 1
        col_c = col_letter_to_index("C")  # = 2

        configs = []
        for row_idx, row in enumerate(all_data, start=1):
            if len(row) <= col_b:
                continue

            # Col B: account
            cell_b = str(row[col_b]).strip()
            if not cell_b:
                continue

            # Parse account (chi lay account dau tien trong cell)
            parsed = parse_accounts_cell(cell_b)
            if not parsed:
                continue

            account = parsed[0]

            # Col C: IPv6
            ipv6 = ""
            if len(row) > col_c:
                ipv6 = str(row[col_c]).strip()

            configs.append({
                "account": account,
                "ipv6": ipv6,
                "row": row_idx,
            })

        if configs:
            print(f"[SERVER] Tim thay {len(configs)} cau hinh tu sheet 'SERVER':")
            for i, cfg in enumerate(configs):
                has_2fa = " [2FA]" if cfg['account'].get('totp_secret') else ""
                ipv6_str = cfg['ipv6'][:30] if cfg['ipv6'] else "no-ipv6"
                print(f"  {i+1}. {cfg['account']['id']}{has_2fa} | {ipv6_str}")

        return configs

    except Exception as e:
        print(f"[SERVER] Loi doc sheet 'SERVER': {e}")
        traceback.print_exc()
        return []


class ChromeWorker:
    """1 Chrome instance voi session, account, IPv6 rieng."""

    def __init__(self, index: int, chrome_path: str, port: int,
                 account: dict = None, ipv6: str = ""):
        self.index = index
        self.chrome_path = chrome_path
        self.port = port
        self.account = account  # {"id": "email", "password": "...", "totp_secret": "..."}
        self.ipv6 = ipv6
        self.session = None  # ChromeSession
        self.ready = False
        self.busy = False
        self.current_task_id: Optional[str] = None
        self.total_completed = 0
        self.total_failed = 0
        self.last_error = ""

    def __repr__(self):
        status = "READY" if self.ready and not self.busy else ("BUSY" if self.busy else "DOWN")
        acc = self.account["id"][:20] if self.account else "?"
        return f"Chrome-{self.index}({status}, {acc}, done={self.total_completed})"


class ChromePool:
    """
    Pool cua nhieu ChromeWorker, chia se chung 1 task queue.

    Usage:
        pool = ChromePool()
        pool.init_workers(accounts, ipv6_list)
        pool.setup_all()
        pool.start_workers(task_queue, task_queue_lock, tasks, task_lock, stats)
    """

    def __init__(self, log_callback: Callable = None):
        self.workers: List[ChromeWorker] = []
        self._log_fn = log_callback or (lambda msg, level="INFO": print(f"[ChromePool] {msg}"))

    def _log(self, msg: str, level: str = "INFO"):
        self._log_fn(msg, level)

    def discover_chromes(self) -> List[Dict]:
        """Tim cac Chrome Portable folder co san."""
        found = []
        for i, folder in enumerate(CHROME_FOLDERS):
            chrome_dir = TOOL_DIR / folder
            chrome_exe = chrome_dir / "GoogleChromePortable.exe"
            if chrome_exe.exists():
                found.append({
                    "index": i,
                    "path": str(chrome_exe),
                    "folder": folder,
                    "port": BASE_PORT + i,
                })
        return found

    def init_workers(self, server_configs: List[Dict] = None):
        """
        Khoi tao workers tu Chrome Portables + server configs.

        Args:
            server_configs: List tu get_server_config()
                [{"account": {...}, "ipv6": "..."}, ...]
        """
        server_configs = server_configs or []

        chromes = self.discover_chromes()
        if not chromes:
            self._log("Khong tim thay Chrome Portable nao!", "ERROR")
            return

        self._log(f"Tim thay {len(chromes)} Chrome Portables:")
        for c in chromes:
            self._log(f"  [{c['index']}] {c['folder']} (port {c['port']})")

        # Match: chrome[i] <-> config[i]
        for i, chrome_info in enumerate(chromes):
            cfg = server_configs[i] if i < len(server_configs) else {}
            account = cfg.get("account")
            ipv6 = cfg.get("ipv6", "")

            worker = ChromeWorker(
                index=chrome_info["index"],
                chrome_path=chrome_info["path"],
                port=chrome_info["port"],
                account=account,
                ipv6=ipv6,
            )
            self.workers.append(worker)

            acc_str = account["id"] if account else "no-account"
            ipv6_str = ipv6[:30] if ipv6 else "no-ipv6"
            self._log(f"  Worker {i}: {chrome_info['folder']} | {acc_str} | {ipv6_str}")

    def setup_all(self) -> int:
        """
        Setup tat ca Chrome workers (mo Chrome, login, tao project).
        Chay TUAN TU de tranh xung dot port.

        Returns: so workers ready.
        """
        from server.chrome_session import ChromeSession

        for worker in self.workers:
            try:
                self._log(f"[Chrome-{worker.index}] Bat dau setup...")
                self._log(f"  Path: {worker.chrome_path}")
                self._log(f"  Port: {worker.port}")
                if worker.account:
                    self._log(f"  Account: {worker.account['id']}")
                if worker.ipv6:
                    self._log(f"  IPv6: {worker.ipv6}")

                session = ChromeSession(
                    chrome_portable_path=worker.chrome_path,
                    port=worker.port,
                    ipv6=worker.ipv6,
                )

                # Set account de auto-login khi can
                if worker.account:
                    session._account = worker.account

                ok = session.setup()
                if ok:
                    worker.session = session
                    worker.ready = True
                    self._log(f"[Chrome-{worker.index}] READY! Project: {session.project_url}", "OK")
                else:
                    self._log(f"[Chrome-{worker.index}] Setup FAILED!", "ERROR")
            except Exception as e:
                self._log(f"[Chrome-{worker.index}] Setup error: {e}", "ERROR")
                traceback.print_exc()

            # Doi giua cac Chrome de tranh xung dot
            time.sleep(3)

        ready_count = sum(1 for w in self.workers if w.ready)
        self._log(f"Setup hoan tat: {ready_count}/{len(self.workers)} workers ready")
        return ready_count

    def start_workers(self, task_queue: list, queue_lock: threading.Lock,
                      tasks: dict, task_lock: threading.Lock, stats: dict):
        """
        Khoi dong worker threads.
        Moi worker co 1 thread rieng, tat ca pull tu chung 1 queue.

        Args:
            task_queue: Shared task queue (list of task_ids)
            queue_lock: Lock cho task_queue
            tasks: Shared task storage (dict: task_id -> task_data)
            task_lock: Lock cho tasks
            stats: Shared stats dict
        """
        for worker in self.workers:
            if worker.ready:
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(worker, task_queue, queue_lock, tasks, task_lock, stats),
                    daemon=True,
                    name=f"ChromeWorker-{worker.index}",
                )
                t.start()
                self._log(f"[Chrome-{worker.index}] Worker thread started")

    def _worker_loop(self, worker: ChromeWorker, task_queue: list,
                     queue_lock: threading.Lock, tasks: dict,
                     task_lock: threading.Lock, stats: dict):
        """
        Worker loop - pull tasks tu shared queue va xu ly.
        Moi worker chay doc lap, lay task khi ranh.
        """
        worker_name = f"Chrome-{worker.index}"
        self._log(f"[{worker_name}] Worker loop started - doi task...")

        while True:
            # Lay task tiep theo tu queue
            task_id = None
            with queue_lock:
                if task_queue:
                    task_id = task_queue.pop(0)  # FIFO - lay va xoa luon

            if task_id is None:
                time.sleep(0.5)
                continue

            # Lay task data
            with task_lock:
                task = tasks.get(task_id)
            if not task:
                continue

            # Bat dau xu ly
            worker.busy = True
            worker.current_task_id = task_id

            with task_lock:
                tasks[task_id]['status'] = 'processing'
                tasks[task_id]['started_at'] = time.time()
                tasks[task_id]['worker'] = worker.index

            vm_id = task.get('vm_id', '?')
            prompt_preview = task.get('prompt', '')[:50]
            self._log(f"[{worker_name}] Processing: {task_id[:8]}... | VM: {vm_id} | Prompt: {prompt_preview}...")

            try:
                # Check session ready
                if not worker.session or not worker.session.ready:
                    self._log(f"[{worker_name}] Session not ready, re-setup...", "WARN")
                    from server.chrome_session import ChromeSession
                    worker.session = ChromeSession(
                        chrome_portable_path=worker.chrome_path,
                        port=worker.port,
                    )
                    if worker.account:
                        worker.session._account = worker.account
                    if not worker.session.setup():
                        raise RuntimeError("Chrome session setup failed")

                # Tao anh
                result = worker.session.generate_image(
                    client_bearer_token=task['bearer_token'],
                    client_project_id=task['project_id'],
                    client_prompt=task['prompt'],
                    model_name=task.get('model_name', 'GEM_PIX_2'),
                    aspect_ratio=task.get('aspect_ratio', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
                    seed=task.get('seed'),
                )

                with task_lock:
                    if result and 'media' in result:
                        tasks[task_id]['status'] = 'completed'
                        tasks[task_id]['result'] = result
                        tasks[task_id]['completed_at'] = time.time()
                        stats['total_completed'] += 1
                        worker.total_completed += 1
                        worker.last_error = ""
                        duration = time.time() - tasks[task_id].get('started_at', time.time())
                        self._log(f"[{worker_name}] OK: {task_id[:8]}... | VM: {vm_id} | {duration:.1f}s", "OK")
                    elif result and 'error' in result:
                        err_msg = result['error']
                        # error co the la dict ({"code": 403, "message": "..."}) hoac string
                        if isinstance(err_msg, dict):
                            err_str = f"Error {err_msg.get('code', '?')}: {err_msg.get('message', str(err_msg))}"
                        else:
                            err_str = str(err_msg)
                        tasks[task_id]['status'] = 'failed'
                        tasks[task_id]['error'] = err_str
                        stats['total_failed'] += 1
                        worker.total_failed += 1
                        worker.last_error = err_str[:100]
                        self._log(f"[{worker_name}] FAIL: {task_id[:8]}... | {err_str[:80]}", "ERROR")
                    else:
                        tasks[task_id]['status'] = 'failed'
                        tasks[task_id]['error'] = 'No media in response'
                        stats['total_failed'] += 1
                        worker.total_failed += 1
                        worker.last_error = "No media"
                        self._log(f"[{worker_name}] FAIL: {task_id[:8]}... | No media", "ERROR")

            except Exception as e:
                traceback.print_exc()
                with task_lock:
                    tasks[task_id]['status'] = 'failed'
                    tasks[task_id]['error'] = str(e)
                    stats['total_failed'] += 1
                worker.total_failed += 1
                worker.last_error = str(e)[:100]
                self._log(f"[{worker_name}] ERROR: {task_id[:8]}... | {str(e)[:80]}", "ERROR")

            finally:
                worker.busy = False
                worker.current_task_id = None

    # ============================================================
    # Stats & Utilities
    # ============================================================

    def available_count(self) -> int:
        """So workers ranh (ready + khong busy)."""
        return sum(1 for w in self.workers if w.ready and not w.busy)

    def total_ready(self) -> int:
        """So workers da setup xong (ke ca dang busy)."""
        return sum(1 for w in self.workers if w.ready)

    def get_stats(self) -> List[Dict]:
        """Thong ke tung worker."""
        return [
            {
                "index": w.index,
                "ready": w.ready,
                "busy": w.busy,
                "current_task": w.current_task_id[:8] + "..." if w.current_task_id else None,
                "account": w.account["id"] if w.account else None,
                "ipv6": w.ipv6 or None,
                "completed": w.total_completed,
                "failed": w.total_failed,
                "last_error": w.last_error or None,
            }
            for w in self.workers
        ]

    def close_all(self):
        """Dong tat ca Chrome sessions."""
        for w in self.workers:
            try:
                if w.session:
                    w.session.close()
            except Exception:
                pass
            w.ready = False
            w.busy = False
        self._log("All Chrome sessions closed")
