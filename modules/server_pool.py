"""
Server Pool - Quan ly nhieu server, load balancing cho VM.

VM co nhieu prompts can tao anh → phan bo qua nhieu server dong thoi.
Moi server co 1 Chrome = 1 anh/lan → N server = N anh song song.

Strategy: Least-queue (chon server it viec nhat)
"""
import time
import threading
import requests
from typing import List, Dict, Optional, Any, Callable


class ServerInfo:
    """Thong tin 1 server."""
    def __init__(self, url: str, name: str = "", enabled: bool = True):
        self.url = url.rstrip('/')
        self.name = name or url
        self.enabled = enabled
        self.queue_size = 0
        self.chrome_ready = False
        self.fail_count = 0
        self.last_check = 0.0
        self.last_fail_time = 0.0
        self.total_completed = 0
        self.total_failed = 0

    def __repr__(self):
        return f"Server({self.name}, q={self.queue_size}, fail={self.fail_count})"


class ServerPool:
    """
    Quan ly pool cac server, load balancing least-queue.

    Usage:
        pool = ServerPool(config)
        pool.refresh_all()

        server = pool.pick_best_server()
        # submit task to server.url
        pool.mark_success(server)
    """

    REFRESH_INTERVAL = 5  # seconds - check server status moi 5s
    FAIL_COOLDOWN = 300   # seconds - server fail bi disable 5 phut
    MAX_FAIL_COUNT = 3    # Sau 3 lan fail lien tiep → disable

    def __init__(self, config: Dict, log_callback: Callable = None):
        self._lock = threading.Lock()
        self._log_fn = log_callback or (lambda msg, level="info": print(f"[ServerPool] {msg}"))
        self.servers: List[ServerInfo] = []

        # Parse config
        self._parse_config(config)

    def _log(self, msg: str, level: str = "info"):
        self._log_fn(msg, level)

    def _parse_config(self, config: Dict):
        """Parse server list tu config. Ho tro ca format cu (single URL) va moi (list)."""
        server_list = config.get('local_server_list', [])

        if server_list:
            # Format moi: list of {url, name, enabled}
            for s in server_list:
                if isinstance(s, str):
                    self.servers.append(ServerInfo(url=s))
                elif isinstance(s, dict):
                    self.servers.append(ServerInfo(
                        url=s.get('url', ''),
                        name=s.get('name', ''),
                        enabled=s.get('enabled', True),
                    ))
        else:
            # Format cu: single URL
            url = config.get('local_server_url', '')
            if url:
                self.servers.append(ServerInfo(url=url, name='default'))

        self._log(f"Loaded {len(self.servers)} servers: {[s.name for s in self.servers]}")

    def available_count(self) -> int:
        """So server kha dung (enabled + khong bi fail qua nhieu)."""
        with self._lock:
            return sum(1 for s in self.servers if self._is_available(s))

    def _is_available(self, server: ServerInfo) -> bool:
        """Check server co kha dung khong (goi trong lock)."""
        if not server.enabled:
            return False
        if server.fail_count >= self.MAX_FAIL_COUNT:
            # Check cooldown
            if time.time() - server.last_fail_time < self.FAIL_COOLDOWN:
                return False
            # Het cooldown → reset fail count, cho thu lai
            server.fail_count = 0
        return True

    def refresh_status(self, server: ServerInfo) -> bool:
        """Check status 1 server. Return True neu OK."""
        try:
            resp = requests.get(f"{server.url}/api/status", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                with self._lock:
                    server.queue_size = data.get('queue_size', 0)
                    server.chrome_ready = data.get('chrome_ready', False)
                    server.last_check = time.time()
                return True
        except Exception:
            pass

        with self._lock:
            server.fail_count += 1
            server.last_fail_time = time.time()
        return False

    def refresh_all(self):
        """Check tat ca servers (song song, nhanh)."""
        threads = []
        for s in self.servers:
            if s.enabled:
                t = threading.Thread(target=self.refresh_status, args=(s,), daemon=True)
                threads.append(t)
                t.start()

        for t in threads:
            t.join(timeout=5)

        # Log
        with self._lock:
            available = [f"{s.name}(q={s.queue_size})" for s in self.servers if self._is_available(s)]
            unavailable = [s.name for s in self.servers if not self._is_available(s)]

        self._log(f"Servers OK: {available}")
        if unavailable:
            self._log(f"Servers DOWN: {unavailable}", "warn")

    def pick_best_server(self) -> Optional[ServerInfo]:
        """
        Chon server tot nhat (queue nho nhat).
        Auto refresh neu data cu (> REFRESH_INTERVAL).
        Return None neu khong co server kha dung.
        """
        now = time.time()

        with self._lock:
            candidates = [s for s in self.servers if self._is_available(s)]

        if not candidates:
            self._log("Khong co server kha dung!", "error")
            return None

        # Refresh neu data cu
        for s in candidates:
            if now - s.last_check > self.REFRESH_INTERVAL:
                self.refresh_status(s)

        # Chon server co queue nho nhat
        with self._lock:
            candidates = [s for s in self.servers if self._is_available(s)]
            if not candidates:
                return None
            # Sort: queue_size ASC, fail_count ASC
            candidates.sort(key=lambda s: (s.queue_size, s.fail_count))
            best = candidates[0]

        return best

    def mark_success(self, server: ServerInfo):
        """Danh dau server thanh cong."""
        with self._lock:
            server.fail_count = 0
            server.total_completed += 1

    def mark_failed(self, server: ServerInfo, error: str = ""):
        """Danh dau server that bai."""
        with self._lock:
            server.fail_count += 1
            server.last_fail_time = time.time()
            server.total_failed += 1
        if server.fail_count >= self.MAX_FAIL_COUNT:
            self._log(f"Server {server.name} disabled ({self.MAX_FAIL_COUNT} fails). Cooldown {self.FAIL_COOLDOWN}s", "warn")

    def get_stats(self) -> Dict[str, Any]:
        """Thong ke tat ca servers."""
        with self._lock:
            return {
                "servers": [
                    {
                        "name": s.name,
                        "url": s.url,
                        "queue_size": s.queue_size,
                        "chrome_ready": s.chrome_ready,
                        "available": self._is_available(s),
                        "fail_count": s.fail_count,
                        "completed": s.total_completed,
                        "failed": s.total_failed,
                    }
                    for s in self.servers
                ],
                "total_available": sum(1 for s in self.servers if self._is_available(s)),
            }
