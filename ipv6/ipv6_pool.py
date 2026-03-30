#!/usr/bin/env python3
"""
IPv6 Pool Manager - Quan ly pool IPv6 dong qua MikroTik.
=========================================================

v1.0.555: Existing IPs mode - dung IP da co san tren router.
Router da co 255 IP (subnet 01-ff), pool chi QUAN LY, KHONG add/remove.

Pool states:
    available  → IP san sang dung (co tren router)
    in_use     → Dang duoc worker su dung
    burned     → Bi 403 (khong dung lai, nhung VAN GIU tren router)
    cooldown   → Tam nghi, se kha dung lai sau cooldown_time

Pool file: ipv6/pool.json (luu trang thai giua cac lan chay)
"""

import json
import time
import random
import threading
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from ipv6.mikrotik_api import MikroTikAPI


class IPv6Pool:
    """
    Quan ly pool IPv6 addresses tu IP da co san tren router.

    Mode: EXISTING IPs - router da co tat ca IP, pool chi track trang thai.
    KHONG add/remove IP tren router.

    Flow:
        1. init() → scan router, lay IP trong allowed range → pool
        2. get_ip() → lay 1 IP available → mark in_use → tra ve
        3. release_ip(ip) → IP van OK → mark available (dung lai duoc)
        4. burn_ip(ip) → IP bi 403 → mark burned (GIU tren router)
        5. refill() → pool it IP → lay them IP tu router (da co san)
    """

    def __init__(
        self,
        mikrotik: MikroTikAPI,
        pool_file: str = None,
        min_pool_size: int = 3,
        max_pool_size: int = 20,
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
        # Tracking: addresses da tung dung (ke ca burned) - de khong dung lai
        self._burned_addresses: set = set()

    # =========================================================================
    # INIT / LOAD / SAVE
    # =========================================================================

    def init(self) -> bool:
        """
        Khoi tao pool:
        1. Load pool.json (neu co)
        2. Scan router, lay IP trong allowed range vao pool
        3. Load TAT CA IP trong range vao pool (day la kho IPv6)
        """
        self.log("[POOL] Initializing IPv6 pool (existing IPs mode)...")

        # Load saved pool
        self._load_pool()

        # Scan router va dong bo
        self._sync_with_router()

        # v1.0.563: Load TAT CA IP trong allowed range vao pool (khong gioi han)
        # Pool la KHO IPv6 → can thay het tat ca IP de quan ly
        self._load_all_from_router()

        available = [p for p in self.pool if p["status"] == "available"]
        in_use = [p for p in self.pool if p["status"] == "in_use"]
        burned = len(self._burned_addresses)
        total_range = self.api.subnet_end - self.api.subnet_start + 1
        self.log(f"[POOL] Ready: {len(available)} available, {len(in_use)} in_use, {burned} burned (range: {total_range})")
        return len(available) > 0

    def _load_pool(self):
        """Load pool tu file."""
        if self.pool_file.exists():
            try:
                with open(self.pool_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.pool = data.get("pool", [])
                self._burned_addresses = set(data.get("burned_addresses", []))
                self.log(f"[POOL] Loaded {len(self.pool)} entries, {len(self._burned_addresses)} burned")
            except Exception as e:
                self.log(f"[POOL] Load error: {e}")
                self.pool = []
                self._burned_addresses = set()
        else:
            self.log("[POOL] No saved pool, starting fresh")

    def _save_pool(self):
        """Save pool ra file."""
        try:
            data = {
                "pool": self.pool,
                "burned_addresses": list(self._burned_addresses),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self.pool_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"[POOL] Save error: {e}")

    # =========================================================================
    # POOL OPERATIONS
    # =========================================================================

    def _get_gateway_for_ip(self, ip: str) -> str:
        """
        v1.0.578: Tinh gateway ::1 cho 1 IPv6 address.
        Gateway = /64 prefix cua IP + ::1

        Args:
            ip: IPv6 address (khong co /prefix)

        Returns:
            Gateway address (vd: "2001:ee0:b004:3065::1")
        """
        import ipaddress
        try:
            addr = ipaddress.IPv6Address(ip)
            full = addr.exploded  # "2001:0ee0:b004:3065:8f2e:41bc:d7a0:3e15"
            groups = full.split(':')
            prefix = ':'.join(groups[:4])  # /64 prefix
            return f"{prefix}::1"
        except Exception:
            return ""

    def get_ip(self) -> Optional[Tuple[str, str]]:
        """
        Lay 1 IPv6 address tu pool.

        Returns:
            Tuple (ip, gateway) hoac None neu het.
            ip: IPv6 address (khong co /prefix)
            gateway: Gateway ::1 cua subnet
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
                    gateway = self._get_gateway_for_ip(ip)
                    self.log(f"[POOL] GET: {ip} gw={gateway} (#{entry['use_count']})")
                    return ip, gateway

            # Het IP available → thu refill
            self.log("[POOL] No available IPs, refilling...")
            added = self._refill(count=self.min_pool_size)
            if added:
                # Lay IP dau tien moi them
                for entry in self.pool:
                    if entry["status"] == "available":
                        entry["status"] = "in_use"
                        entry["used_at"] = time.time()
                        entry["use_count"] = entry.get("use_count", 0) + 1
                        self._save_pool()
                        ip = entry["address"]
                        gateway = self._get_gateway_for_ip(ip)
                        self.log(f"[POOL] GET: {ip} gw={gateway} (#{entry['use_count']})")
                        return ip, gateway

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
        Danh dau IP la burned (bi 403).
        KHONG xoa khoi router - chi danh dau trong pool.

        Args:
            address: IPv6 address
            reason: Ly do burn (vd: "403", "blocked")
        """
        with self._lock:
            for entry in self.pool:
                if entry["address"] == address:
                    entry["status"] = "burned"
                    entry["burned_at"] = time.time()
                    entry["burn_reason"] = reason
                    self._burned_addresses.add(address)
                    self._save_pool()
                    self.log(f"[POOL] BURN: {address} ({reason}) → marked burned (kept on router)")

                    # Refill neu can
                    self._refill_if_needed()
                    return

            self.log(f"[POOL] Burn: {address} not found")

    def rotate_ip(self, current_address: str, reason: str = "403") -> Optional[Tuple[str, str]]:
        """
        Doi IP: burn IP cu → lay IP moi.

        Args:
            current_address: IP dang dung
            reason: Ly do doi

        Returns:
            Tuple (new_ip, gateway) hoac None
        """
        self.log(f"[POOL] ROTATE: {current_address} ({reason})")
        self.burn_ip(current_address, reason)
        result = self.get_ip()
        if result:
            new_ip, gateway = result
            self.log(f"[POOL] ROTATE: {current_address} → {new_ip} gw={gateway}")
            return new_ip, gateway
        else:
            self.log(f"[POOL] ROTATE FAILED: No new IP available!")
            return None

    # =========================================================================
    # POOL MANAGEMENT
    # =========================================================================

    def _load_all_from_router(self):
        """
        v1.0.563: Load TAT CA IP trong allowed range tu router vao pool.
        Khong gioi han max_pool_size - pool la kho IPv6, can thay het.
        """
        router_addrs = self.api.list_ipv6_addresses()
        pool_addresses = {e["address"] for e in self.pool}
        added = 0

        for entry in router_addrs:
            addr_full = entry.get("address", "")
            addr_clean = addr_full.split("/")[0]
            interface = entry.get("interface", "")

            if interface != self.api.interface:
                continue

            subnet = self.api._extract_subnet(addr_full)
            if subnet is None:
                continue
            if subnet < self.api.subnet_start or subnet > self.api.subnet_end:
                continue

            # v1.0.579: Skip gateway addresses (::1/64) - khong phai worker IP
            if addr_clean.endswith("::1") or addr_clean.endswith(":0001"):
                continue

            # Skip neu da co trong pool hoac da burned
            if addr_clean in pool_addresses:
                continue
            if addr_clean in self._burned_addresses:
                continue

            new_entry = {
                "address": addr_clean,
                "full_address": addr_full,
                "subnet": subnet,
                "subnet_hex": f"{subnet:02x}",
                "router_id": entry.get(".id", ""),
                "interface": interface,
                "status": "available",
                "use_count": 0,
                "created_at": time.time(),
                "used_at": None,
            }
            self.pool.append(new_entry)
            pool_addresses.add(addr_clean)
            added += 1

        if added > 0:
            self._save_pool()
            self.log(f"[POOL] Loaded {added} IPs from router (total pool: {len(self.pool)})")

    def _refill_if_needed(self):
        """Them IP tu router neu pool duoi min_pool_size."""
        available = [p for p in self.pool if p["status"] == "available"]
        if len(available) < self.min_pool_size:
            need = self.min_pool_size - len(available)
            self.log(f"[POOL] Refill: {len(available)} available < {self.min_pool_size} min, adding {need}")
            self._refill(count=need)

    def _refill(self, count: int = 1) -> int:
        """
        Them IP tu router vao pool (IP DA CO SAN, khong add moi).
        Chon ngau nhien tu cac IP trong allowed range chua co trong pool.

        Returns:
            So IP da them
        """
        # Lay tat ca IP tren router
        router_addrs = self.api.list_ipv6_addresses()

        # Tim IP trong allowed range chua co trong pool va chua burned
        pool_addresses = {e["address"] for e in self.pool}
        candidates = []

        for entry in router_addrs:
            addr_full = entry.get("address", "")
            addr_clean = addr_full.split("/")[0]
            interface = entry.get("interface", "")

            # Chi lay IP cua interface dung
            if interface != self.api.interface:
                continue

            # Kiem tra subnet co trong allowed range
            subnet = self.api._extract_subnet(addr_full)
            if subnet is None:
                continue
            if subnet < self.api.subnet_start or subnet > self.api.subnet_end:
                continue

            # v1.0.579: Skip gateway addresses (::1/64)
            if addr_clean.endswith("::1") or addr_clean.endswith(":0001"):
                continue

            # Skip neu da co trong pool hoac da burned
            if addr_clean in pool_addresses:
                continue
            if addr_clean in self._burned_addresses:
                continue

            candidates.append({
                "address": addr_clean,
                "full_address": addr_full,
                "subnet": subnet,
                "subnet_hex": f"{subnet:02x}",
                "router_id": entry.get(".id", ""),
                "interface": interface,
            })

        if not candidates:
            self.log("[POOL] No more IPs available in allowed range!")
            return 0

        # Chon ngau nhien de tranh dung cung IP moi lan
        random.shuffle(candidates)

        added = 0
        for cand in candidates:
            if added >= count:
                break

            # Check max pool size (chi dem active entries)
            active_count = len([p for p in self.pool if p["status"] in ("available", "in_use")])
            if active_count >= self.max_pool_size:
                self.log(f"[POOL] Max pool size reached ({self.max_pool_size})")
                break

            entry = {
                "address": cand["address"],
                "full_address": cand["full_address"],
                "subnet": cand["subnet"],
                "subnet_hex": cand["subnet_hex"],
                "router_id": cand["router_id"],
                "status": "available",
                "created_at": time.time(),
                "use_count": 0,
            }
            self.pool.append(entry)
            added += 1
            self.log(f"[POOL] Added from router: {cand['address']} (subnet {cand['subnet_hex']})")

        if added:
            self._save_pool()
        return added

    def rotate_all(self) -> int:
        """
        v1.0.566: Doi TAT CA IP - xoa IP cu, tao IP moi voi SUBNET + host RANDOM.

        /56 prefix = 256 subnet /64 (00-ff). Google block theo /64 nen
        phai doi SUBNET (3065 → 30a3) chu khong chi doi host (::1 → ::abc).

        Flow:
            1. Xoa tat ca IP trong allowed range tren router
            2. Clear pool + burned_addresses
            3. Chon NGAU NHIEN subnet moi tu full range (00-ff), tranh trung subnet cu
            4. Add IP moi: subnet random + host random
            5. Load vao pool

        Returns:
            So IP moi da them
        """
        with self._lock:
            self.log("[POOL] === ROTATE ALL: Doi tat ca IP (subnet + host) ===")

            # 1. Lay tat ca IP trong allowed range tren router
            router_addrs = self.api.list_ipv6_addresses()
            old_ids = []  # router .id de xoa
            old_subnets = set()  # subnet cu de tranh chon lai

            for entry in router_addrs:
                addr_full = entry.get("address", "")
                interface = entry.get("interface", "")
                addr_id = entry.get(".id", "")

                if interface != self.api.interface:
                    continue

                subnet = self.api._extract_subnet(addr_full)
                if subnet is None:
                    continue
                if subnet < self.api.subnet_start or subnet > self.api.subnet_end:
                    continue

                old_ids.append(addr_id)
                old_subnets.add(subnet)

            self.log(f"[POOL] Tim thay {len(old_ids)} IP cu tren router (subnets: {len(old_subnets)})")

            # 2. Xoa tat ca IP cu tren router
            removed = 0
            for addr_id in old_ids:
                if self.api.remove_ipv6_address(addr_id):
                    removed += 1
            self.log(f"[POOL] Da xoa {removed}/{len(old_ids)} IP cu tren router")

            # 3. Clear pool va burned list
            self.pool = []
            self._burned_addresses = set()
            self._save_pool()
            self.log("[POOL] Da clear pool va burned list")

            # 4. Tao IP moi cho TOAN BO subnet trong range (65-ff = 155)
            full_range = list(range(self.api.subnet_start, self.api.subnet_end + 1))
            random.shuffle(full_range)
            selected = full_range

            self.log(f"[POOL] Tao moi {len(selected)} IP cho toan bo range "
                     f"({self.api.subnet_start:02x}-{self.api.subnet_end:02x})")

            # 5. Add IP moi voi random subnet + 64-bit random host (giong Privacy Extension)
            # v1.0.578: Tao gateway ::1/128 rieng cho moi subnet
            added = 0
            for subnet in selected:
                # Tao gateway ::1/64 cho subnet nay (de VM dung lam default route)
                # PHAI la /64 de router biet route ca subnet (khong phai /128)
                subnet_str = f"{subnet:02x}"
                gw_addr = f"{self.api.prefix}{subnet_str}::1/64"
                gw_result = self.api.add_ipv6_address(gw_addr)
                if not gw_result:
                    self.log(f"[POOL] [!] Cannot create gateway for subnet {subnet:02x}, skip")
                    continue

                # Tao IP random cho worker dung
                new_addr = self.api.build_ipv6_address(subnet, full_random=True)
                result = self.api.add_ipv6_address(new_addr)
                if result:
                    added += 1
                else:
                    self.log(f"[POOL] [!] Cannot create IP for subnet {subnet:02x}")

            self.log(f"[POOL] Da them {added}/{len(selected)} IP moi tren router")

            # 6. Load tat ca IP moi vao pool
            self._load_all_from_router()

            available = [p for p in self.pool if p["status"] == "available"]
            self.log(f"[POOL] === ROTATE ALL DONE: {len(available)} IP san sang ===")
            return added

    def _sync_with_router(self):
        """
        Dong bo pool voi trang thai thuc tren router.
        - IP con tren router → giu
        - IP mat khoi router → mark burned
        - Cleanup entries burned cu
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
                    self._burned_addresses.add(entry["address"])

        # Cleanup: xoa entries burned khoi pool list (giu burned_addresses set)
        before = len(self.pool)
        self.pool = [p for p in self.pool if p["status"] != "burned"]
        if before != len(self.pool):
            self.log(f"[POOL] Sync cleanup: removed {before - len(self.pool)} burned entries")

        self._save_pool()

    # =========================================================================
    # STATUS / INFO
    # =========================================================================

    def get_status(self) -> Dict:
        """Tra ve trang thai pool."""
        with self._lock:
            stats = {"available": 0, "in_use": 0, "burned": 0, "total": len(self.pool)}
            for entry in self.pool:
                status = entry.get("status", "unknown")
                if status in stats:
                    stats[status] += 1

            # Tinh IP con lai (trong allowed range, chua burned)
            total_range = self.api.subnet_end - self.api.subnet_start + 1
            stats["burned_total"] = len(self._burned_addresses)
            stats["range_total"] = total_range
            stats["range_remaining"] = total_range - len(self._burned_addresses)
            return stats

    def get_pool_entries(self) -> List[Dict]:
        """Tra ve ban sao cua pool."""
        with self._lock:
            return list(self.pool)

    def cleanup_burned(self):
        """Xoa cac entry burned khoi pool (giu burned_addresses)."""
        with self._lock:
            before = len(self.pool)
            self.pool = [p for p in self.pool if p["status"] != "burned"]
            after = len(self.pool)
            if before != after:
                self._save_pool()
                self.log(f"[POOL] Cleanup: removed {before - after} burned entries")

    def reset_pool(self):
        """
        Reset pool state - KHONG xoa IP khoi router.
        Chi xoa pool tracking data.
        """
        with self._lock:
            self.log("[POOL] RESET: Clearing pool tracking data...")
            self.pool = []
            self._burned_addresses = set()
            self._save_pool()
            self.log("[POOL] RESET complete (IPs unchanged on router)")
