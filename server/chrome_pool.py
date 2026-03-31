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
                 account: dict = None, ipv6: str = "", gateway: str = ""):
        self.index = index
        self.chrome_path = chrome_path
        self.port = port
        self.account = account  # {"id": "email", "password": "...", "totp_secret": "..."}
        self.ipv6 = ipv6
        self.gateway = gateway  # v1.0.609: Gateway tu Pool API
        self.session = None  # ChromeSession
        self.ready = False
        self.busy = False
        self.current_task_id: Optional[str] = None
        self.total_completed = 0
        self.total_failed = 0
        self.last_error = ""
        self.proxy_provider = None  # v1.0.545: ProxyProvider instance

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
        self._ipv6_list: List[str] = []  # Tat ca IPv6
        self._ipv6_usage: Dict[str, int] = {}  # ipv6 -> so lan da dung
        self._all_accounts: List[Dict] = []  # Tat ca tai khoan
        self._account_usage: Dict[str, int] = {}  # email -> so lan da dung
        # v1.0.561: IPv6 Pool Client (MikroTik dynamic pool)
        self._pool_client = None  # IPv6PoolClient instance
        self._pool_mode = False  # True = dung pool API thay vi static list

    def _log(self, msg: str, level: str = "INFO"):
        self._log_fn(msg, level)

    def setup_pool_client(self, pool_api_url: str, timeout: int = 5):
        """
        v1.0.561: Setup IPv6 Pool Client cho server.
        Khi co pool client, 403 recovery se lay IPv6 tu pool thay vi static list.

        Args:
            pool_api_url: URL cua Pool API server (vd: "http://192.168.88.1:8765")
            timeout: Timeout cho moi request (giay)
        """
        if not pool_api_url:
            return

        try:
            from modules.ipv6_pool_client import IPv6PoolClient
            client = IPv6PoolClient(
                api_url=pool_api_url,
                timeout=timeout,
                log_func=lambda msg: self._log(msg),
            )
            if client.ping():
                self._pool_client = client
                self._pool_mode = True
                self._log(f"[IPv6 Pool] Connected: {pool_api_url}", "OK")
            else:
                self._log(f"[IPv6 Pool] Not available: {pool_api_url}", "WARN")
        except Exception as e:
            self._log(f"[IPv6 Pool] Init error: {e}", "ERROR")

    def get_pool_ip(self, worker_name: str = "unknown") -> Optional[str]:
        """
        v1.0.561: Lay IPv6 tu Pool API cho 1 worker.

        Args:
            worker_name: Ten worker (vd: "server_chrome0")

        Returns:
            IPv6 address hoac None
        """
        if not self._pool_mode or not self._pool_client:
            return None
        return self._pool_client.get_ip(worker=worker_name)

    def rotate_pool_ip(self, current_ip: str, worker_name: str = "unknown",
                       reason: str = "403") -> Optional[str]:
        """
        v1.0.561: Doi IPv6 qua Pool API (burn cu, lay moi).

        Args:
            current_ip: IPv6 hien tai
            worker_name: Ten worker
            reason: Ly do doi

        Returns:
            IPv6 moi hoac None
        """
        if not self._pool_mode or not self._pool_client:
            return None
        return self._pool_client.rotate_ip(current_ip, reason=reason, worker=worker_name)

    def release_pool_ip(self, ip: str, worker_name: str = "unknown"):
        """v1.0.561: Tra IPv6 ve pool (IP van OK, khong bi 403)."""
        if self._pool_mode and self._pool_client and ip:
            self._pool_client.release_ip(ip, worker=worker_name)

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

            # v1.0.561: Pool mode - lay IPv6 tu pool API thay vi config/sheet
            gateway = ""
            if self._pool_mode and not ipv6:
                worker_name = f"server_chrome{i}"
                pool_result = self.get_pool_ip(worker_name)
                if pool_result:
                    # v1.0.606: Pool API tra ve dict {"ip": "...", "gateway": "..."}
                    if isinstance(pool_result, dict):
                        ipv6 = pool_result.get("ip", "")
                        gateway = pool_result.get("gateway", "")
                    else:
                        ipv6 = pool_result
                    self._log(f"  [IPv6 Pool] Worker {i}: {ipv6} (gw: {gateway[:30]})")

            worker = ChromeWorker(
                index=chrome_info["index"],
                chrome_path=chrome_info["path"],
                port=chrome_info["port"],
                account=account,
                ipv6=ipv6,
                gateway=gateway,
            )
            self.workers.append(worker)

            acc_str = account["id"] if account else "no-account"
            ipv6_str = ipv6[:30] if ipv6 else "no-ipv6"
            self._log(f"  Worker {i}: {chrome_info['folder']} | {acc_str} | {ipv6_str}")

        # _all_accounts se duoc set boi app.py sau init_workers()

    def setup_proxy_providers(self, proxy_config: dict = None):
        """
        v1.0.545: Setup ProxyProvider cho tat ca workers.

        Args:
            proxy_config: Config tu settings.yaml hoac GUI
                { "proxy_provider": { "type": "webshare", "webshare": {...} } }
        """
        if not proxy_config:
            return

        try:
            from modules.proxy_providers import create_provider

            pp_type = proxy_config.get('proxy_provider', {}).get('type', 'none')
            if pp_type == 'none':
                self._log(f"[PROXY] Provider type = none, skip")
                return

            # v1.0.611: Pool mode + IPv6 → cleanup old static IPs truoc
            if pp_type == 'ipv6' and self._pool_mode:
                pool_ips = [w.ipv6 for w in self.workers if w.ipv6]
                if pool_ips:
                    from modules.proxy_providers.ipv6_provider import IPv6Provider
                    _cleaner = IPv6Provider(log_func=lambda msg, lvl="INFO": self._log(msg, lvl))
                    _cleaner.cleanup_old_addresses(keep_ips=pool_ips)

            for worker in self.workers:
                # Moi worker co provider rieng (port rieng)
                proxy_port = worker.port + 200  # 19222 → 19422, 19223 → 19423
                provider = create_provider(
                    config=proxy_config,
                    log_func=lambda msg, lvl="INFO", wn=f"Chrome-{worker.index}": self._log(f"[{wn}] {msg}", lvl),
                )

                if pp_type == 'webshare':
                    # Webshare: setup bridge tren proxy_port
                    if provider.setup(worker_id=worker.index, port=proxy_port):
                        worker.proxy_provider = provider
                        self._log(f"[Chrome-{worker.index}] Proxy ({pp_type}): OK on port {proxy_port}")
                    else:
                        self._log(f"[Chrome-{worker.index}] Proxy ({pp_type}): FAILED", "ERROR")

                elif pp_type == 'ipv6':
                    # IPv6: setup dedicated voi IPv6 cua worker
                    if worker.ipv6:
                        # v1.0.609: Pass gateway de add IPv6 to Windows interface
                        # v1.0.627: Check return value - neu fail (khong co internet) → rotate IPv6
                        setup_ok = provider.setup_dedicated(
                            worker_id=worker.index,
                            port=proxy_port,
                            ipv6_address=worker.ipv6,
                            gateway=getattr(worker, 'gateway', ''),
                        )
                        if setup_ok:
                            worker.proxy_provider = provider
                            self._log(f"[Chrome-{worker.index}] Proxy (ipv6): {worker.ipv6} on port {proxy_port}")
                        else:
                            self._log(f"[Chrome-{worker.index}] Proxy (ipv6): FAILED - {worker.ipv6} khong co internet!", "ERROR")
                            # Rotate sang IPv6 moi tu pool
                            self._try_rotate_worker_ipv6(worker, provider, proxy_port, proxy_config)
                    else:
                        self._log(f"[Chrome-{worker.index}] Proxy (ipv6): skip (no IPv6 assigned)")

        except ImportError as e:
            self._log(f"[PROXY] Import error: {e}", "ERROR")
        except Exception as e:
            self._log(f"[PROXY] Setup error: {e}", "ERROR")

    def _try_rotate_worker_ipv6(self, worker, provider, proxy_port: int, proxy_config: dict,
                                max_retries: int = 3):
        """
        v1.0.627: Khi IPv6 khong co internet, rotate sang IPv6 moi tu pool.
        """
        if not self._pool_client:
            self._log(f"[Chrome-{worker.index}] Khong co pool client de rotate IPv6!", "ERROR")
            return

        for attempt in range(max_retries):
            worker_name = f"server_chrome{worker.index}"
            self._log(f"[Chrome-{worker.index}] Rotate IPv6 (lan {attempt + 1}/{max_retries})...")

            result = self._pool_client.rotate_ip(
                worker.ipv6, reason="no_internet", worker=worker_name
            )
            if not result:
                self._log(f"[Chrome-{worker.index}] Pool rotate failed!", "ERROR")
                break

            new_ip = result.get('ip') or result.get('new_ip', '')
            new_gw = result.get('gateway', '')
            if not new_ip:
                self._log(f"[Chrome-{worker.index}] Pool tra ve IP rong!", "ERROR")
                break

            self._log(f"[Chrome-{worker.index}] Thu IPv6 moi: {new_ip} gw={new_gw}")
            worker.ipv6 = new_ip
            worker.gateway = new_gw

            # Tao provider moi
            from modules.proxy_providers import create_provider
            new_provider = create_provider(
                config=proxy_config,
                log_func=lambda msg, lvl="INFO", wn=f"Chrome-{worker.index}": self._log(f"[{wn}] {msg}", lvl),
            )
            ok = new_provider.setup_dedicated(
                worker_id=worker.index,
                port=proxy_port,
                ipv6_address=new_ip,
                gateway=new_gw,
            )
            if ok:
                worker.proxy_provider = new_provider
                self._log(f"[Chrome-{worker.index}] [v] IPv6 moi OK: {new_ip}")
                return

        self._log(f"[Chrome-{worker.index}] KHONG tim duoc IPv6 co internet sau {max_retries} lan!", "ERROR")

    def get_next_account(self, current_email: str = "") -> Optional[Dict]:
        """
        Lay tai khoan IT DUNG NHAT, khac voi current_email.
        Tranh trung voi account dang duoc worker khac dung.
        Returns: account dict hoac None.
        """
        if not self._all_accounts:
            return None

        best = None
        best_score = float('inf')
        for acc in self._all_accounts:
            email = acc['id']
            if email == current_email:
                continue
            usage = self._account_usage.get(email, 0)
            # Phat diem neu dang duoc worker khac dung (tranh trung)
            in_use = any(
                w.account and w.account['id'] == email
                for w in self.workers
            )
            score = usage + (1000 if in_use else 0)
            if score < best_score:
                best_score = score
                best = acc

        if best:
            self._account_usage[best['id']] = self._account_usage.get(best['id'], 0) + 1
            self._log(f"Next account: {best['id']} (used={self._account_usage[best['id']]}x)")

        return best

    def get_next_ipv6(self, current_ipv6: str = "") -> str:
        """
        Lay IPv6 IT DUNG NHAT, khac voi current_ipv6.
        Tranh trung voi IPv6 dang duoc worker khac dung.

        Returns: IPv6 moi, hoac "" neu khong co
        """
        if not self._ipv6_list:
            return ""

        best = None
        best_score = float('inf')
        for ip in self._ipv6_list:
            if ip == current_ipv6:
                continue
            usage = self._ipv6_usage.get(ip, 0)
            # Phat diem neu dang duoc worker khac dung
            in_use = any(w.ipv6 == ip for w in self.workers)
            score = usage + (1000 if in_use else 0)
            if score < best_score:
                best_score = score
                best = ip

        if best:
            self._ipv6_usage[best] = self._ipv6_usage.get(best, 0) + 1
            return best

        # Tat ca deu giong current → tra ve cai dau tien
        return self._ipv6_list[0]

    def _setup_single_worker(self, worker: 'ChromeWorker') -> bool:
        """Setup 1 Chrome worker (co retry). Tra ve True neu thanh cong."""
        from server.chrome_session import ChromeSession
        worker_name = f"Chrome-{worker.index}"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                # v1.0.633: Close session cu truoc khi tao moi (tranh chiem port)
                if attempt > 0 and worker.session:
                    try:
                        worker.session.close()
                    except Exception:
                        pass
                    worker.session = None

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
                    proxy_provider=getattr(worker, 'proxy_provider', None),
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

        # Neu chua ready → retry setup, rotate IPv6 neu can
        if not worker.ready:
            self._log(f"[{worker_name}] Chua ready, retry setup...", "WARN")
            for retry in range(3):
                # v1.0.633: Kill Chrome cu truoc khi retry (tranh chiem port + IPv6 cu)
                if worker.session:
                    try:
                        self._log(f"[{worker_name}] Kill Chrome cu truoc khi retry...")
                        worker.session.close()
                    except Exception:
                        pass
                    worker.session = None

                time.sleep(5)

                # v1.0.633: Rotate IPv6 TRUOC khi retry setup (khong phai sau)
                if worker.ipv6 and self._pool_client:
                    self._log(f"[{worker_name}] Rotate IPv6 truoc khi retry setup...", "WARN")
                    result = self._pool_client.rotate_ip(
                        worker.ipv6, reason="setup_fail",
                        worker=f"server_chrome{worker.index}"
                    )
                    if result:
                        new_ip = result.get('ip') or result.get('new_ip', '')
                        new_gw = result.get('gateway', '')
                        if new_ip:
                            self._log(f"[{worker_name}] IPv6 moi: {new_ip}")
                            worker.ipv6 = new_ip
                            worker.gateway = new_gw
                            # Re-setup proxy voi IPv6 moi
                            if worker.proxy_provider:
                                try:
                                    from modules.proxy_providers import create_provider
                                    proxy_port = worker.port + 200
                                    new_provider = create_provider(
                                        config={'proxy_type': 'ipv6'},
                                        log_func=lambda msg, lvl="INFO", wn=worker_name: self._log(f"[{wn}] {msg}", lvl),
                                    )
                                    if new_provider.setup_dedicated(worker.index, proxy_port, new_ip, new_gw):
                                        worker.proxy_provider = new_provider
                                        self._log(f"[{worker_name}] Proxy re-setup OK voi IPv6 moi")
                                except Exception as e:
                                    self._log(f"[{worker_name}] Re-setup proxy error: {e}", "ERROR")

                ok = self._setup_single_worker(worker)
                if ok:
                    break

            if not worker.ready:
                self._log(f"[{worker_name}] Setup THAT BAI sau retry + rotate! Worker dung.", "ERROR")
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

                # v1.0.629: Phan biet image vs video task
                task_type = task.get('type', 'image')

                if task_type == 'video':
                    self._log(f"[{worker_name}] VIDEO task: mediaId={task.get('media_id', '')[:40]}...")
                    result = worker.session.generate_video(
                        client_bearer_token=task['bearer_token'],
                        client_project_id=task['project_id'],
                        client_prompt=task['prompt'],
                        media_id=task.get('media_id', ''),
                        video_model=task.get('video_model', 'veo_3_1_r2v_fast_landscape_ultra_relaxed'),
                        aspect_ratio=task.get('aspect_ratio', 'VIDEO_ASPECT_RATIO_LANDSCAPE'),
                        seed=task.get('seed'),
                    )
                else:
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
                    if result and ('media' in result or 'operations' in result):
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
                            if '401' in err_str or 'authentication' in err_str.lower():
                                err_code = 401
                            elif '403' in err_str:
                                err_code = 403
                            elif '429' in err_str or '253' in err_str or 'quota' in err_str.lower():
                                err_code = 429
                            elif '400' in err_str:
                                err_code = 400
                            else:
                                err_code = 0
                        worker.last_error = err_str[:100]

                        # v1.0.635: Check proxy health - neu IPv6 chet thi rotate ngay
                        # thay vi doi 403 (429/400 cung co the do IPv6 chet)
                        _proxy_dead = False
                        if err_code in (429, 400) and worker.proxy_provider:
                            _proxy = getattr(worker.proxy_provider, '_proxy', None)
                            _cf = getattr(_proxy, '_connect_failures', 0) if _proxy else 0
                            if _cf >= 5:
                                self._log(f"[{worker_name}] [IPv6-DEAD] Proxy co {_cf} connect failures → rotate IPv6 thay vi retry!", "WARN")
                                _proxy_dead = True

                        # === 429/QUOTA: Switch model ngay (giong API mode) ===
                        if err_code == 429 and not _proxy_dead:
                            tasks[task_id]['status'] = 'queued'
                            tasks[task_id]['error'] = ''
                            retry_count = tasks[task_id].get('_quota_retries', 0)
                            if retry_count < 3 and worker.session:
                                tasks[task_id]['_quota_retries'] = retry_count + 1
                                # Switch sang model tiep theo
                                old_idx = worker.session._current_model_index
                                worker.session._current_model_index = (old_idx + 1) % 3
                                self._log(f"[{worker_name}] [QUOTA] Model {old_idx} → {worker.session._current_model_index} | retry {retry_count + 1}/3", "WARN")
                                with queue_lock:
                                    task_queue.append(task_id)
                            else:
                                tasks[task_id]['status'] = 'failed'
                                tasks[task_id]['error'] = f"Quota exhausted - all models tried"
                                stats['total_failed'] += 1
                                worker.total_failed += 1
                                self._log(f"[{worker_name}] FAIL (QUOTA): {task_id[:8]}... | Het model!", "ERROR")

                        # === INTERCEPTOR FAIL: Re-queue (khong doi IPv6) ===
                        elif 'interceptor' in err_str.lower():
                            retry_count = tasks[task_id].get('_inject_retries', 0)
                            if retry_count < 3:
                                tasks[task_id]['_inject_retries'] = retry_count + 1
                                tasks[task_id]['status'] = 'queued'
                                tasks[task_id]['error'] = ''
                                self._log(f"[{worker_name}] RE-QUEUE (interceptor): {task_id[:8]}... | retry {retry_count + 1}/3", "WARN")
                                with queue_lock:
                                    task_queue.append(task_id)
                                # Restart Chrome (co the page bi loi)
                                if worker.session:
                                    try:
                                        worker.session.restart_with_new_fingerprint(clear_data=False)
                                    except:
                                        pass
                            else:
                                tasks[task_id]['status'] = 'failed'
                                tasks[task_id]['error'] = 'Interceptor injection failed 3x'
                                stats['total_failed'] += 1
                                worker.total_failed += 1
                                self._log(f"[{worker_name}] FAIL (interceptor): {task_id[:8]}...", "ERROR")

                        # === 401: Token expired - KHONG retry, VM can refresh token ===
                        elif err_code == 401 or '401' in err_str or 'authentication' in err_str.lower():
                            tasks[task_id]['status'] = 'failed'
                            tasks[task_id]['error'] = err_str
                            stats['total_failed'] += 1
                            worker.total_failed += 1
                            self._log(f"[{worker_name}] FAIL (401): {task_id[:8]}... | TOKEN HET HAN - VM can refresh", "ERROR")

                        # === 400: Retry 1 lan, roi POLICY_VIOLATION cho VM skip ===
                        elif err_code == 400 and not _proxy_dead:
                            _400_retries = tasks[task_id].get('_400_retries', 0)
                            if _400_retries < 1:
                                # Retry 1 lan (co the do ref loi, khong phai prompt)
                                tasks[task_id]['_400_retries'] = _400_retries + 1
                                tasks[task_id]['status'] = 'queued'
                                tasks[task_id]['error'] = ''
                                self._log(f"[{worker_name}] 400 RETRY {_400_retries+1}/1: {task_id[:8]}...", "WARN")
                            else:
                                # Da retry roi → POLICY_VIOLATION cho VM skip
                                tasks[task_id]['status'] = 'failed'
                                tasks[task_id]['error'] = f"POLICY_VIOLATION: {err_str}"
                                stats['total_failed'] += 1
                                worker.total_failed += 1
                                self._log(f"[{worker_name}] POLICY_VIOLATION (400x2): {task_id[:8]}... | {err_str[:80]}", "WARN")
                            if worker.session:
                                worker.session._consecutive_403 = 0

                        # === v1.0.635: PROXY DEAD → xu ly nhu 403 (rotate IPv6) ===
                        elif _proxy_dead:
                            # Re-queue task
                            retry_count = tasks[task_id].get('_403_retries', 0)
                            if retry_count < 10:
                                tasks[task_id]['_403_retries'] = retry_count + 1
                                tasks[task_id]['status'] = 'queued'
                                tasks[task_id]['error'] = ''
                                self._log(f"[{worker_name}] RE-QUEUE (proxy-dead): {task_id[:8]}... | retry {retry_count + 1}/10", "WARN")
                                with queue_lock:
                                    task_queue.append(task_id)
                            else:
                                tasks[task_id]['status'] = 'failed'
                                tasks[task_id]['error'] = f"Proxy dead + {err_code} x10"
                                stats['total_failed'] += 1
                                worker.total_failed += 1
                                self._log(f"[{worker_name}] FAIL (proxy-dead): {task_id[:8]}...", "ERROR")
                            # Force 403-like recovery (rotate IPv6 + restart)
                            # Set err_code = 403 de trigger 403 RECOVERY block ben duoi
                            err_code = 403

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
                                # v1.0.609: Pool mode + ProxyProvider → rotate_to() voi IP moi tu pool
                                if self._pool_mode and self._pool_client and worker.proxy_provider:
                                    pool_worker = f"server_chrome{worker.index}"
                                    pool_result = self.rotate_pool_ip(
                                        worker.ipv6, worker_name=pool_worker, reason="403"
                                    )
                                    new_ip = pool_result.get("ip", "") if isinstance(pool_result, dict) else pool_result
                                    new_gw = pool_result.get("gateway", "") if isinstance(pool_result, dict) else ""
                                    if new_ip and new_ip != worker.ipv6:
                                        self._log(f"[{worker_name}] [403] Pool IPv6: {worker.ipv6} → {new_ip}", "WARN")
                                        # Dung rotate_to() de add IP to interface + restart SOCKS5
                                        worker.proxy_provider.rotate_to(new_ip, gateway=new_gw)
                                        worker.ipv6 = new_ip
                                        worker.gateway = new_gw
                                    else:
                                        self._log(f"[{worker_name}] [403] Pool: khong co IPv6 khac", "WARN")

                                elif worker.session._proxy_provider and not self._pool_mode:
                                    # Non-pool mode voi ProxyProvider (webshare, ipv6 static)
                                    ok_rotate = worker.session.rotate_proxy("403")
                                    if ok_rotate:
                                        self._log(f"[{worker_name}] [403] Proxy rotated: → {worker.session._proxy_provider.get_current_ip()}", "WARN")
                                    else:
                                        self._log(f"[{worker_name}] [403] Proxy rotate failed", "WARN")
                                elif self._pool_mode and self._pool_client:
                                    # v1.0.561: Pool mode without ProxyProvider
                                    pool_worker = f"server_chrome{worker.index}"
                                    pool_result = self.rotate_pool_ip(
                                        worker.ipv6, worker_name=pool_worker, reason="403"
                                    )
                                    new_ip = pool_result.get("ip", "") if isinstance(pool_result, dict) else pool_result
                                    if new_ip and new_ip != worker.ipv6:
                                        self._log(f"[{worker_name}] [403] Pool IPv6: {worker.ipv6} → {new_ip}", "WARN")
                                        worker.session.rotate_ipv6(new_ip)
                                        worker.ipv6 = new_ip
                                    else:
                                        self._log(f"[{worker_name}] [403] Pool: khong co IPv6 khac", "WARN")
                                else:
                                    # Backward compat: IPv6 static list
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
            # v1.0.561: Tra IPv6 ve pool khi dong
            if self._pool_mode and w.ipv6:
                try:
                    self.release_pool_ip(w.ipv6, f"server_chrome{w.index}")
                except Exception:
                    pass
            w.ready = False
            w.busy = False
        self._log("All Chrome sessions closed")
