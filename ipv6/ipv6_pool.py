#!/usr/bin/env python3
"""
IPv6 Pool Manager - Quan ly pool IPv6 dong qua MikroTik.
=========================================================

Duy tri pool IPv6 addresses:
- Khi can IP moi → add vao MikroTik → tra ve cho caller
- Khi IP bi 403  → xoa khoi MikroTik → danh dau "burned"
- Tu dong bo sung IP moi khi pool can

Pool states:
    available  → IP da add vao router, san sang dung
    in_use     → Dang duoc worker su dung
    burned     → Bi 403, da xoa khoi router (khong dung lai)
    cooldown   → Tam nghi, se kha dung lai sau cooldown_time

Pool file: ipv6/pool.json (luu trang thai giua cac lan chay)
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from ipv6.mikrotik_api import MikroTikAPI


class IPv6Pool:
    """
    Quan ly pool IPv6 addresses dong.

    Flow:
        1. init() → doc pool.json (neu co) + sync voi router
        2. get_ip() → lay 1 IP available → mark in_use → tra ve
        3. release_ip(ip) → IP van OK → mark available (dung lai duoc)
        4. burn_ip(ip, reason) → IP bi 403 → xoa khoi router → mark burned
        5. refill() → pool it IP → add IP moi tu subnet chua dung
    """

    def __init__(
        self,
        mikrotik: MikroTikAPI,
        pool_file: str = None,
        min_pool_size: int = 3,
        max_pool_size: int = 10,
        cooldown_seconds: int = 3600,
        log_func=print,
    ):
        self.api = mikrotik
        self.pool_file = Path(pool_file) if pool_file else Path(__file__).parent / "pool.json"
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.cooldown_seconds = cooldown_seconds
        self.log = log_func
        self._lock = threading.Lock()

        # Pool data
        self.pool: List[Dict] = []
        # Tracking subnet usage
        self._used_subnets: set = set()  # Tat ca subnet da tung dung (ke ca burned)
        self._next_subnet_idx = 0  # Vi tri tiep theo trong available_subnets

    # =========================================================================
    # INIT / LOAD / SAVE
    # =========================================================================

    def init(self) -> bool:
        """
        Khoi tao pool:
        1. Load pool.json (neu co)
        2. Sync voi router (kiem tra IP nao con active)
        3. Refill neu pool qua it
        """
        self.log("[POOL] Initializing IPv6 pool...")

        # Load saved pool
        self._load_pool()

        # Sync voi router
        self._sync_with_router()

        # Refill neu can
        self._refill_if_needed()

        available = [p for p in self.pool if p["status"] == "available"]
        self.log(f"[POOL] Ready: {len(available)} available, {len(self.pool)} total")
        return len(available) > 0

    def _load_pool(self):
        """Load pool tu file."""
        if self.pool_file.exists():
            try:
                with open(self.pool_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.pool = data.get("pool", [])
                self._used_subnets = set(data.get("used_subnets", []))
                self.log(f"[POOL] Loaded {len(self.pool)} entries from {self.pool_file.name}")
            except Exception as e:
                self.log(f"[POOL] Load error: {e}")
                self.pool = []
                self._used_subnets = set()
        else:
            self.log("[POOL] No saved pool, starting fresh")

    def _save_pool(self):
        """Save pool ra file."""
        try:
            data = {
                "pool": self.pool,
                "used_subnets": list(self._used_subnets),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.pool_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"[POOL] Save error: {e}")

    # =========================================================================
    # POOL OPERATIONS
    # =========================================================================

    def get_ip(self) -> Optional[str]:
        """
        Lay 1 IPv6 address tu pool.

        Returns:
            IPv6 address (khong co /prefix) hoac None neu het
        """
        with self._lock:
            # Tim IP available
            for entry in self.pool:
                if entry["status"] == "available":
                    entry["status"] = "in_use"
                    entry["used_at"] = time.time()
                    entry["use_count"] = entry.get("use_count", 0) + 1
                    self._save_pool()
                    ip = entry["address"]
                    self.log(f"[POOL] GET: {ip} (#{entry['use_count']})")
                    return ip

            # Het IP available → thu refill
            self.log("[POOL] No available IPs, refilling...")
            added = self._refill(count=1)
            if added:
                return self.get_ip()  # Recursive, 1 lan

            self.log("[POOL] [!] POOL EMPTY - No more IPs!")
            return None

    def release_ip(self, address: str):
        """
        Tra IP lai pool (van dung duoc, khong bi 403).

        Args:
            address: IPv6 address
        """
        with self._lock:
            for entry in self.pool:
                if entry["address"] == address and entry["status"] == "in_use":
                    entry["status"] = "available"
                    entry["released_at"] = time.time()
                    self._save_pool()
                    self.log(f"[POOL] RELEASE: {address} → available")
                    return
            self.log(f"[POOL] Release: {address} not found in pool")

    def burn_ip(self, address: str, reason: str = "403"):
        """
        Danh dau IP la burned (bi 403) → xoa khoi router.

        Args:
            address: IPv6 address
            reason: Ly do burn (vd: "403", "blocked")
        """
        with self._lock:
            for entry in self.pool:
                if entry["address"] == address:
                    # Xoa khoi MikroTik
                    if entry.get("router_id"):
                        self.api.remove_ipv6_address(entry["router_id"])
                    else:
                        # Tim theo address
                        self.api.remove_ipv6_by_address(f"{address}/128")

                    entry["status"] = "burned"
                    entry["burned_at"] = time.time()
                    entry["burn_reason"] = reason
                    self._save_pool()
                    self.log(f"[POOL] BURN: {address} ({reason}) → removed from router")

                    # Refill neu can
                    self._refill_if_needed()
                    return

            self.log(f"[POOL] Burn: {address} not found")

    def rotate_ip(self, current_address: str, reason: str = "403") -> Optional[str]:
        """
        Doi IP: burn IP cu → lay IP moi.
        Shortcut cho burn_ip() + get_ip().

        Args:
            current_address: IP dang dung
            reason: Ly do doi

        Returns:
            IP moi hoac None
        """
        self.log(f"[POOL] ROTATE: {current_address} ({reason})")
        self.burn_ip(current_address, reason)
        new_ip = self.get_ip()
        if new_ip:
            self.log(f"[POOL] ROTATE: {current_address} → {new_ip}")
        else:
            self.log(f"[POOL] ROTATE FAILED: No new IP available!")
        return new_ip

    # =========================================================================
    # POOL MANAGEMENT
    # =========================================================================

    def _refill_if_needed(self):
        """Them IP moi neu pool duoi min_pool_size."""
        available = [p for p in self.pool if p["status"] == "available"]
        if len(available) < self.min_pool_size:
            need = self.min_pool_size - len(available)
            self.log(f"[POOL] Refill: {len(available)} available < {self.min_pool_size} min, adding {need}")
            self._refill(count=need)

    def _refill(self, count: int = 1) -> int:
        """
        Them `count` IP moi vao pool tu MikroTik.

        Returns:
            So IP da them thanh cong
        """
        added = 0
        available_subnets = self.api.get_available_subnets()

        for subnet in available_subnets:
            if added >= count:
                break

            # Skip subnet da dung (ke ca burned)
            if subnet in self._used_subnets:
                continue

            # Skip subnet qua pool size
            active_count = len([p for p in self.pool if p["status"] in ("available", "in_use")])
            if active_count >= self.max_pool_size:
                self.log(f"[POOL] Max pool size reached ({self.max_pool_size})")
                break

            # Tao IPv6 address
            ipv6_addr = self.api.build_ipv6_address(subnet)
            router_id = self.api.add_ipv6_address(ipv6_addr, self.api.interface)

            if router_id:
                # Address khong co /prefix
                clean_addr = ipv6_addr.split("/")[0]
                entry = {
                    "address": clean_addr,
                    "full_address": ipv6_addr,
                    "subnet": subnet,
                    "subnet_hex": f"{subnet:02x}",
                    "router_id": router_id,
                    "status": "available",
                    "created_at": time.time(),
                    "use_count": 0,
                }
                self.pool.append(entry)
                self._used_subnets.add(subnet)
                added += 1
                self.log(f"[POOL] Added: {clean_addr} (subnet {subnet:02x})")

                # Doi 1s cho router apply
                time.sleep(1)

        if added:
            self._save_pool()
        return added

    def _sync_with_router(self):
        """
        Dong bo pool voi trang thai thuc tren router.
        IP nao con tren router → giu, IP nao mat → mark burned.
        """
        router_addrs = self.api.list_ipv6_addresses()
        router_set = set()
        for entry in router_addrs:
            addr = entry.get("address", "").split("/")[0]
            router_set.add(addr)

        for entry in self.pool:
            if entry["status"] in ("available", "in_use"):
                if entry["address"] not in router_set:
                    self.log(f"[POOL] Sync: {entry['address']} not on router → burned")
                    entry["status"] = "burned"
                    entry["burn_reason"] = "sync_missing"

        self._save_pool()

    # =========================================================================
    # STATUS / INFO
    # =========================================================================

    def get_status(self) -> Dict:
        """Tra ve trang thai pool."""
        with self._lock:
            stats = {"available": 0, "in_use": 0, "burned": 0, "cooldown": 0, "total": len(self.pool)}
            for entry in self.pool:
                status = entry.get("status", "unknown")
                if status in stats:
                    stats[status] += 1

            # Tinh subnet con lai
            total_subnets = self.api.subnet_end - self.api.subnet_start + 1
            stats["subnets_used"] = len(self._used_subnets)
            stats["subnets_remaining"] = total_subnets - len(self._used_subnets)
            return stats

    def get_pool_entries(self) -> List[Dict]:
        """Tra ve ban sao cua pool."""
        with self._lock:
            return list(self.pool)

    def cleanup_burned(self):
        """Xoa cac entry burned khoi pool (giu used_subnets de khong dung lai)."""
        with self._lock:
            before = len(self.pool)
            self.pool = [p for p in self.pool if p["status"] != "burned"]
            after = len(self.pool)
            if before != after:
                self._save_pool()
                self.log(f"[POOL] Cleanup: removed {before - after} burned entries")

    def reset_pool(self):
        """
        Reset toan bo pool - xoa tat ca IP khoi router.
        CHI DUNG KHI CAN RESET HOAN TOAN.
        """
        with self._lock:
            self.log("[POOL] RESET: Removing all pool IPs from router...")
            for entry in self.pool:
                if entry["status"] in ("available", "in_use") and entry.get("router_id"):
                    self.api.remove_ipv6_address(entry["router_id"])
                    time.sleep(0.5)

            self.pool = []
            self._used_subnets = set()
            self._save_pool()
            self.log("[POOL] RESET complete")
