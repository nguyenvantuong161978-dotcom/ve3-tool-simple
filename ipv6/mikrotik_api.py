#!/usr/bin/env python3
"""
MikroTik REST API Client - Quan ly IPv6 addresses qua Router API.
==================================================================

VNPT Fiber Xtra 2: Prefix /56 → 256 subnet /64 (3000 → 30ff)
Subnet rotate: 3052 → 30ff (174 subnets kha dung)

MikroTik RouterOS 7+ REST API:
    GET    /rest/ipv6/address        → List all IPv6 addresses
    PUT    /rest/ipv6/address        → Add new address
    DELETE /rest/ipv6/address/{id}   → Remove address

Flow:
    Pool can IP → add_ipv6(subnet_hex) → MikroTik add vao interface
    IP bi 403   → remove_ipv6(address_id) → MikroTik xoa khoi interface
    Lay IP moi  → pick subnet chua dung → add_ipv6() → IP moi san sang
"""

import requests
import urllib3
import time
from typing import Optional, List, Dict, Tuple

# Tat SSL warning (MikroTik dung self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MikroTikAPI:
    """
    Client giao tiep voi MikroTik RouterOS REST API.

    Args:
        host: IP cua router (mac dinh 192.168.88.1)
        username: Tai khoan admin
        password: Mat khau
        interface: Ten interface IPv6 (mac dinh ether1)
        prefix: IPv6 prefix /56 (vd: 2001:ee0:4f89:3000)
        subnet_start: Subnet bat dau rotate (hex, vd: 0x52 = 3052)
        subnet_end: Subnet ket thuc rotate (hex, vd: 0xff = 30ff)
    """

    def __init__(
        self,
        host: str = "192.168.88.1",
        username: str = "admin",
        password: str = "",
        interface: str = "ether1",
        prefix: str = "",
        subnet_start: int = 0x52,
        subnet_end: int = 0xFF,
        log_func=print,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.interface = interface
        self.prefix = prefix.rstrip(":")  # "2001:ee0:4f89:30" (bo ":" cuoi)
        self.subnet_start = subnet_start
        self.subnet_end = subnet_end
        self.log = log_func

        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.verify = False  # MikroTik self-signed cert
        self.session.headers.update({"Content-Type": "application/json"})

        # v1.0.554: Auto-detect HTTPS vs HTTP
        self.base_url = self._detect_base_url()

    def _detect_base_url(self) -> str:
        """Thu HTTPS truoc, neu fail thu HTTP."""
        for scheme in ["https", "http"]:
            try:
                url = f"{scheme}://{self.host}/rest/system/identity"
                resp = self.session.get(url, timeout=5)
                if resp.status_code in (200, 401):
                    self.log(f"[MikroTik] Using {scheme.upper()}://{self.host}")
                    return f"{scheme}://{self.host}/rest"
            except Exception:
                pass
        # Fallback HTTPS
        return f"https://{self.host}/rest"

    # =========================================================================
    # CORE API METHODS
    # =========================================================================

    def list_ipv6_addresses(self) -> List[Dict]:
        """
        Lay danh sach tat ca IPv6 addresses tren router.

        Returns:
            List of dicts: [{".id": "*1", "address": "2001:...:1/64", "interface": "ether1", ...}]
        """
        try:
            resp = self.session.get(f"{self.base_url}/ipv6/address", timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            self.log(f"[MikroTik] List IPv6 failed: {e}")
            return []

    def add_ipv6_address(self, address: str, interface: str = None) -> Optional[str]:
        """
        Them IPv6 address vao interface.

        Args:
            address: IPv6 address voi prefix length (vd: "2001:ee0:4f89:3052::1/64")
            interface: Interface name (mac dinh dung self.interface)

        Returns:
            Address ID (vd: "*A") neu thanh cong, None neu that bai
        """
        iface = interface or self.interface
        data = {
            "address": address,
            "interface": iface,
            "advertise": "false",  # Khong quang ba ra mang
        }

        try:
            resp = self.session.put(f"{self.base_url}/ipv6/address", json=data, timeout=10)
            if resp.status_code in (200, 201):
                result = resp.json()
                addr_id = result.get(".id", "")
                self.log(f"[MikroTik] Added: {address} on {iface} → ID={addr_id}")
                return addr_id
            else:
                self.log(f"[MikroTik] Add failed ({resp.status_code}): {resp.text}")
                return None
        except Exception as e:
            self.log(f"[MikroTik] Add IPv6 error: {e}")
            return None

    def remove_ipv6_address(self, address_id: str) -> bool:
        """
        Xoa IPv6 address theo ID.

        Args:
            address_id: MikroTik address ID (vd: "*A", "*1B")

        Returns:
            True neu thanh cong
        """
        try:
            resp = self.session.delete(
                f"{self.base_url}/ipv6/address/{address_id}", timeout=10
            )
            if resp.status_code in (200, 204):
                self.log(f"[MikroTik] Removed: ID={address_id}")
                return True
            else:
                self.log(f"[MikroTik] Remove failed ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            self.log(f"[MikroTik] Remove IPv6 error: {e}")
            return False

    def remove_ipv6_by_address(self, address: str) -> bool:
        """
        Xoa IPv6 theo address string (tim ID roi xoa).

        Args:
            address: IPv6 address (vd: "2001:ee0:4f89:3052::1/64")
        """
        all_addrs = self.list_ipv6_addresses()
        for entry in all_addrs:
            if entry.get("address", "").startswith(address.split("/")[0]):
                return self.remove_ipv6_address(entry[".id"])
        self.log(f"[MikroTik] Address not found: {address}")
        return False

    # =========================================================================
    # SUBNET HELPERS
    # =========================================================================

    def build_ipv6_address(self, subnet_hex: int, host_id: int = 1) -> str:
        """
        Tao IPv6 address tu subnet hex.

        Args:
            subnet_hex: Subnet number (vd: 0x52 → 3052)
            host_id: Host part (mac dinh ::1)

        Returns:
            Full IPv6 address voi /128 (vd: "2001:ee0:4f89:3052::1/128")

        Note: Dung /128 de chi assign 1 IP duy nhat (khong phai ca subnet)
        """
        # prefix = "2001:ee0:4f89:30" → "2001:ee0:4f89:30{52}"
        subnet_str = f"{subnet_hex:02x}"

        # Prefix da chua phan dau (vd: "2001:ee0:4f89:30")
        # Them subnet hex vao cuoi
        full_prefix = f"{self.prefix}{subnet_str}"
        return f"{full_prefix}::{host_id}/128"

    def get_available_subnets(self) -> List[int]:
        """
        Tra ve danh sach subnet hex kha dung (chua dung).

        Returns:
            List subnet hex numbers (vd: [0x52, 0x53, ..., 0xff])
        """
        return list(range(self.subnet_start, self.subnet_end + 1))

    def get_used_subnets(self) -> List[int]:
        """
        Lay cac subnet dang duoc su dung tren router.

        Returns:
            List subnet hex numbers dang active
        """
        all_addrs = self.list_ipv6_addresses()
        used = []

        for entry in all_addrs:
            addr = entry.get("address", "")
            # Parse subnet tu address
            subnet = self._extract_subnet(addr)
            if subnet is not None and self.subnet_start <= subnet <= self.subnet_end:
                used.append(subnet)

        return used

    def _extract_subnet(self, address: str) -> Optional[int]:
        """
        Extract subnet hex tu IPv6 address.

        "2001:ee0:4f89:3052::1/128" → 0x52
        """
        try:
            # Bo /prefix
            addr_part = address.split("/")[0]
            # Split groups
            groups = addr_part.split(":")
            # Tim group chua subnet (group thu 4, 0-indexed = 3)
            if len(groups) >= 4:
                subnet_group = groups[3]  # "3052"
                # Lay 2 ky tu cuoi
                if len(subnet_group) >= 2:
                    subnet_hex = subnet_group[-2:]
                    return int(subnet_hex, 16)
        except (ValueError, IndexError):
            pass
        return None

    # =========================================================================
    # CONNECTIVITY TEST
    # =========================================================================

    def test_connection(self) -> bool:
        """Test ket noi toi MikroTik REST API."""
        try:
            resp = self.session.get(
                f"{self.base_url}/system/identity", timeout=5
            )
            if resp.status_code == 200:
                identity = resp.json()
                name = identity.get("name", "unknown")
                self.log(f"[MikroTik] Connected: {name} ({self.host})")
                return True
            elif resp.status_code == 401:
                self.log(f"[MikroTik] Auth failed! Check username/password")
                return False
            else:
                self.log(f"[MikroTik] HTTP {resp.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            self.log(f"[MikroTik] Cannot connect to {self.host}")
            return False
        except Exception as e:
            self.log(f"[MikroTik] Connection error: {e}")
            return False

    def test_ipv6_connectivity(self, address: str) -> bool:
        """
        Test xem IPv6 address co bind duoc khong (ping tu may local).

        Args:
            address: IPv6 address (khong co /prefix)
        """
        import subprocess

        try:
            # Ping Google DNS qua IPv6 address nay
            cmd = f"ping -6 -n 1 -w 3000 -S {address} 2001:4860:4860::8888"
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and "Reply from" in result.stdout:
                self.log(f"[MikroTik] IPv6 OK: {address}")
                return True
            else:
                self.log(f"[MikroTik] IPv6 FAIL: {address}")
                return False
        except Exception as e:
            self.log(f"[MikroTik] IPv6 test error: {e}")
            return False
