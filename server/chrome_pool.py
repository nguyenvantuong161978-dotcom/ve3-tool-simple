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
        self._ipv6_list: List[str] = []  # Tat ca IPv6 tu sheet SERVER col C
        self._ipv6_rotate_index = 0  # Vi tri hien tai trong _ipv6_list
        self._all_accounts: List[Dict] = []  # Tat ca tai khoan tu sheet SERVER
        self._account_usage: Dict[str, int] = {}  # email -> so lan da dung

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

        # IPv6 list cho rotation - chi tu GUI (khong lay tu sheet)
        # GUI se truyen qua app.py → chrome_pool._ipv6_list
        self._ipv6_list = []

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

        # Load tat ca tai khoan tu sheet de dung khi doi account (403 lan 5)
        self.load_all_accounts()

    def load_all_accounts(self):
        """Load tat ca tai khoan tu sheet SERVER vao _all_accounts."""
        try:
            from server.chrome_session import get_server_accounts
            accounts = get_server_accounts()
            if accounts:
                self._all_accounts = accounts
                # Track usage: email dang duoc worker nao dung
                for w in self.workers:
                    if w.account:
                        email = w.account['id']
                        self._account_usage[email] = self._account_usage.get(email, 0) + 1
                self._log(f"Loaded {len(accounts)} tai khoan tu sheet SERVER")
            else:
                self._log("Khong tim thay tai khoan nao tu sheet SERVER", "WARN")
        except Exception as e:
            self._log(f"Loi load tai khoan: {e}", "ERROR")

    def get_next_account(self, current_email: str = "") -> Optional[Dict]:
        """
        Lay tai khoan it dung nhat, khac voi current_email.
        Returns: account dict hoac None.
        """
        if not self._all_accounts:
            return None

        # Tim account it dung nhat, khac current
        best = None
        best_usage = float('inf')
        for acc in self._all_accounts:
            email = acc['id']
            if email == current_email:
                continue
            # Khong dung account dang duoc worker khac dung
            in_use = any(
                w.account and w.account['id'] == email
                for w in self.workers
            )
            usage = self._account_usage.get(email, 0)
            # Uu tien: khong dang dung > it dung nhat
            score = usage + (1000 if in_use else 0)
            if score < best_usage:
                best_usage = score
                best = acc

        if best:
            self._account_usage[best['id']] = self._account_usage.get(best['id'], 0) + 1
            self._log(f"Next account: {best['id']} (usage={best_usage})")

        return best

    def get_next_ipv6(self, current_ipv6: str = "") -> str:
        """
        Lay IPv6 tiep theo tu danh sach (sheet SERVER col C).
        Bo qua IPv6 dang dung. Quay vong khi het list.

        Args:
            current_ipv6: IPv6 hien tai cua worker (de bo qua)

        Returns: IPv6 moi, hoac "" neu khong co
        """
        if not self._ipv6_list:
            return ""

        # Tim IPv6 khac voi current, bat dau tu vi tri rotate hien tai
        for _ in range(len(self._ipv6_list)):
            self._ipv6_rotate_index = (self._ipv6_rotate_index + 1) % len(self._ipv6_list)
            candidate = self._ipv6_list[self._ipv6_rotate_index]
            if candidate != current_ipv6:
                return candidate

        # Tat ca deu giong current → tra ve cai dau tien
        return self._ipv6_list[0]

    def _setup_single_worker(self, worker: 'ChromeWorker') -> bool:
        """Setup 1 Chrome worker (co retry). Tra ve True neu thanh cong."""
        from server.chrome_session import ChromeSession
        worker_name = f"Chrome-{worker.index}"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    self._log(f"[{worker_name}] Bat dau setup...")
                    if worker.account:
                        self._log(f"[{worker_name}] Account: {worker.account['id']}")
                    if worker.ipv6:
                        self._log(f"[{worker_name}] IPv6: {worker.ipv6}")
                else:
                    self._log(f"[{worker_name}] Retry setup ({attempt + 1}/{max_retries})...", "WARN")

                session = ChromeSession(
                    chrome_portable_path=worker.chrome_path,
                    port=worker.port,
                    ipv6=worker.ipv6,
                )
                if worker.account:
                    session._account = worker.account

                ok = session.setup()
                if ok:
                    worker.session = session
                    worker.ready = True
                    self._log(f"[{worker_name}] READY!", "OK")
                    return True
                else:
                    self._log(f"[{worker_name}] Setup FAILED (attempt {attempt + 1})", "ERROR")
            except Exception as e:
                self._log(f"[{worker_name}] Setup error: {e}", "ERROR")

            # Doi truoc khi retry
            if attempt < max_retries - 1:
                time.sleep(5)

        self._log(f"[{worker_name}] Setup FAILED sau {max_retries} lan!", "ERROR")
        return False

    def setup_all(self) -> int:
        """
        Setup tat ca Chrome workers SONG SONG.
        Moi worker chay trong thread rieng, khong doi nhau.

        Returns: so workers ready.
        """
        threads = []
        for worker in self.workers:
            t = threading.Thread(
                target=self._setup_single_worker,
                args=(worker,),
                daemon=True,
            )
            t.start()
            threads.append(t)
            time.sleep(1)  # Delay nhe giua cac Chrome

        # Doi tat ca setup xong
        for t in threads:
            t.join(timeout=180)  # Max 3 phut moi worker

        ready_count = sum(1 for w in self.workers if w.ready)
        self._log(f"Setup hoan tat: {ready_count}/{len(self.workers)} workers ready")
        return ready_count

    def start_workers(self, task_queue: list, queue_lock: threading.Lock,
                      tasks: dict, task_lock: threading.Lock, stats: dict):
        """
        Khoi dong worker threads cho TAT CA workers (ke ca chua ready).
        Worker chua ready se tu retry setup trong loop.
        """
        for worker in self.workers:
            t = threading.Thread(
                target=self._worker_loop,
                args=(worker, task_queue, queue_lock, tasks, task_lock, stats),
                daemon=True,
                name=f"ChromeWorker-{worker.index}",
            )
            t.start()
            self._log(f"[Chrome-{worker.index}] Worker thread started" + (" (chua ready, se retry)" if not worker.ready else ""))

    def _worker_loop(self, worker: ChromeWorker, task_queue: list,
                     queue_lock: threading.Lock, tasks: dict,
                     task_lock: threading.Lock, stats: dict):
        """
        Worker loop - pull tasks tu shared queue va xu ly.
        Moi worker chay doc lap, lay task khi ranh.
        Neu chua ready → tu retry setup.
        """
        worker_name = f"Chrome-{worker.index}"

        # Neu chua ready → retry setup trong loop
        if not worker.ready:
            self._log(f"[{worker_name}] Chua ready, retry setup...", "WARN")
            for retry in range(3):
                time.sleep(10)  # Doi 10s giua cac retry
                ok = self._setup_single_worker(worker)
                if ok:
                    break
                self._log(f"[{worker_name}] Retry {retry + 2}/3 setup...", "WARN")
            if not worker.ready:
                self._log(f"[{worker_name}] Setup THAT BAI vinh vien! Worker dung.", "ERROR")
                return

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
                # Check session ready - retry setup neu can
                if not worker.session or not worker.session.ready:
                    self._log(f"[{worker_name}] Session not ready, re-setup...", "WARN")
                    ok = self._setup_single_worker(worker)
                    if not ok:
                        raise RuntimeError("Chrome session setup failed")

                # Tao anh
                result = worker.session.generate_image(
                    client_bearer_token=task['bearer_token'],
                    client_project_id=task['project_id'],
                    client_prompt=task['prompt'],
                    model_name=task.get('model_name', 'GEM_PIX_2'),
                    aspect_ratio=task.get('aspect_ratio', 'IMAGE_ASPECT_RATIO_LANDSCAPE'),
                    seed=task.get('seed'),
                    image_inputs=task.get('image_inputs', []),
                )

                with task_lock:
                    if result and 'media' in result:
                        tasks[task_id]['status'] = 'completed'
                        tasks[task_id]['result'] = result
                        tasks[task_id]['completed_at'] = time.time()
                        stats['total_completed'] += 1
                        worker.total_completed += 1
                        worker.last_error = ""
                        # Reset 403 counter khi thanh cong
                        if worker.session:
                            worker.session._consecutive_403 = 0
                        duration = time.time() - tasks[task_id].get('started_at', time.time())
                        self._log(f"[{worker_name}] OK: {task_id[:8]}... | VM: {vm_id} | {duration:.1f}s", "OK")
                    elif result and 'error' in result:
                        err_msg = result['error']
                        # error co the la dict ({"code": 403, "message": "..."}) hoac string
                        if isinstance(err_msg, dict):
                            err_code = err_msg.get('code', 0)
                            err_str = f"Error {err_code}: {err_msg.get('message', str(err_msg))}"
                        else:
                            err_str = str(err_msg)
                            if '403' in err_str:
                                err_code = 403
                            elif '400' in err_str:
                                err_code = 400
                            else:
                                err_code = 0
                        worker.last_error = err_str[:100]

                        # === 400: Bo qua luon, khong retry ===
                        if err_code == 400:
                            tasks[task_id]['status'] = 'failed'
                            tasks[task_id]['error'] = err_str
                            stats['total_failed'] += 1
                            worker.total_failed += 1
                            self._log(f"[{worker_name}] SKIP (400): {task_id[:8]}... | {err_str[:80]}", "WARN")
                            if worker.session:
                                worker.session._consecutive_403 = 0
                        # === 403: Retry + recovery ===
                        elif err_code == 403:
                            # Track retry count cho task nay (toi da 10 lan = 2 vong x 5 lan)
                            retry_count = tasks[task_id].get('_403_retries', 0)
                            max_retries = 10  # 2 vong x 5 lan
                            if retry_count < max_retries:
                                tasks[task_id]['_403_retries'] = retry_count + 1
                                tasks[task_id]['status'] = 'queued'
                                tasks[task_id]['error'] = ''
                                self._log(f"[{worker_name}] RE-QUEUE (403): {task_id[:8]}... | retry {retry_count + 1}/{max_retries}", "WARN")
                                # Re-queue task de retry sau khi recovery
                                with queue_lock:
                                    task_queue.append(task_id)
                            else:
                                tasks[task_id]['status'] = 'failed'
                                tasks[task_id]['error'] = f"403 x{max_retries} - het retry"
                                stats['total_failed'] += 1
                                worker.total_failed += 1
                                self._log(f"[{worker_name}] FAIL (403 x{max_retries}): {task_id[:8]}... | Het retry!", "ERROR")
                        else:
                            tasks[task_id]['status'] = 'failed'
                            tasks[task_id]['error'] = err_str
                            stats['total_failed'] += 1
                            worker.total_failed += 1
                            self._log(f"[{worker_name}] FAIL: {task_id[:8]}... | {err_str[:80]}", "ERROR")

                        # === 403 RECOVERY ===
                        # Lan 1-3: DOI IPv6 + fingerprint moi (giu data, nhanh)
                        # Lan 4:   CLEAR DATA + DOI IPv6 + login lai (cung account)
                        # Lan 5+:  CLEAR DATA + DOI IPv6 + DOI ACCOUNT MOI + login
                        # Counter chi reset khi TAO ANH THANH CONG hoac doi account
                        if err_code == 403 and worker.session:
                            worker.session._consecutive_403 += 1
                            c403 = worker.session._consecutive_403

                            if c403 <= 3:
                                action = f"DOI IPv6 + fingerprint moi (lan {c403}/3)"
                            elif c403 == 4:
                                action = "CLEAR DATA + DOI IPv6 + LOGIN LAI"
                            else:
                                action = "CLEAR DATA + DOI IPv6 + DOI ACCOUNT MOI"
                            self._log(f"[{worker_name}] [403] Lan thu {c403} → {action}", "WARN")

                            # Cleanup browser data ngay
                            try:
                                from server.chrome_session import JS_CLEANUP
                                worker.session.page.run_js(JS_CLEANUP)
                                self._log(f"[{worker_name}] [403] Cleanup browser data OK")
                            except Exception:
                                pass

                            worker.ready = False
                            try:
                                # Doi IPv6
                                new_ip = self.get_next_ipv6(worker.ipv6)
                                if new_ip and new_ip != worker.ipv6:
                                    self._log(f"[{worker_name}] [403] IPv6: {worker.ipv6} → {new_ip}", "WARN")
                                    worker.session.rotate_ipv6(new_ip)
                                    worker.ipv6 = new_ip
                                else:
                                    self._log(f"[{worker_name}] [403] Khong co IPv6 khac", "WARN")

                                if c403 <= 3:
                                    # Lan 1-3: Restart + fingerprint moi (giu data)
                                    ok = worker.session.restart_with_new_fingerprint(clear_data=False)
                                    worker.ready = ok
                                    if ok:
                                        self._log(f"[{worker_name}] [403] Restart OK - IPv6 moi + fingerprint moi", "OK")
                                    else:
                                        self._log(f"[{worker_name}] [403] Restart FAIL!", "ERROR")

                                elif c403 == 4:
                                    # Lan 4: CLEAR DATA + login lai (cung account)
                                    ok = worker.session.restart_with_new_fingerprint(clear_data=True)
                                    worker.ready = ok
                                    if ok:
                                        self._log(f"[{worker_name}] [403] Clear data + login lai OK", "OK")
                                    else:
                                        self._log(f"[{worker_name}] [403] Clear data + login FAIL!", "ERROR")

                                else:
                                    # Lan 5+: DOI ACCOUNT MOI + clear data + login
                                    old_email = worker.account['id'] if worker.account else "?"
                                    new_account = self.get_next_account(old_email)
                                    if new_account:
                                        self._log(f"[{worker_name}] [403] DOI ACCOUNT: {old_email} → {new_account['id']}", "WARN")
                                        worker.account = new_account
                                        worker.session._account = new_account
                                    else:
                                        self._log(f"[{worker_name}] [403] Khong co account khac, giu {old_email}", "WARN")

                                    ok = worker.session.restart_with_new_fingerprint(clear_data=True)
                                    worker.ready = ok
                                    if ok:
                                        # Reset counter sau khi doi account
                                        worker.session._consecutive_403 = 0
                                        self._log(f"[{worker_name}] [403] Doi account + clear data + login OK → reset counter", "OK")
                                    else:
                                        self._log(f"[{worker_name}] [403] Doi account + login FAIL!", "ERROR")

                            except Exception as re:
                                self._log(f"[{worker_name}] [403] Recovery error: {re}", "ERROR")

                        elif err_code != 403 and worker.session:
                            worker.session._consecutive_403 = 0
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
