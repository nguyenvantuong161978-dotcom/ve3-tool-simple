#!/usr/bin/env python3
"""
IPv6Provider - Proxy provider dung IPv6 rotation.
==================================================

Wrap modules/ipv6_rotator.py + modules/ipv6_proxy.py thanh ProxyProvider interface.
Logic giu nguyen y het, chi thay doi cach goi.

VM Mode: Chrome 1 (worker_id=0) quan ly proxy, Chrome 2+ reuse.
Server Mode: Moi worker co proxy rieng.
"""

import time
from typing import Optional, Callable
from modules.proxy_providers.base_provider import ProxyProvider


class IPv6Provider(ProxyProvider):
    """Proxy provider dung IPv6 SOCKS5 local binding."""

    def __init__(self, config: dict = None, log_func: Callable = print):
        super().__init__(config, log_func)
        self._rotator = None  # IPv6Rotator instance
        self._proxy = None    # IPv6SocksProxy instance
        self._activated = False

    def setup(self, worker_id: int = 0, port: int = 1088) -> bool:
        """
        Khoi tao IPv6 proxy.

        - worker_id=0: Tao SOCKS5 proxy + tim IPv6 hoat dong
        - worker_id>0: Reuse proxy tu worker 0 (VM mode) hoac tao rieng (Server mode)
        """
        self.worker_id = worker_id
        self.port = port

        try:
            from modules.ipv6_rotator import get_ipv6_rotator
            self._rotator = get_ipv6_rotator()

            if not self._rotator or not self._rotator.enabled:
                self.log(f"[PROXY-IPv6] IPv6 khong kha dung (enabled={getattr(self._rotator, 'enabled', False)})")
                return False

            # v1.0.574: Pool mode khong can ipv6_list (lay tu API)
            _is_pool = getattr(self._rotator, '_pool_mode', False)
            if not _is_pool and not self._rotator.ipv6_list:
                self.log(f"[PROXY-IPv6] Khong co IPv6 list va khong co pool!")
                return False

            self._rotator.set_logger(self.log)

            if worker_id == 0:
                # Chrome 1: Tim IPv6 hoat dong + tao SOCKS5 proxy
                working_ipv6 = self._rotator.init_with_working_ipv6()
                if not working_ipv6:
                    self.log("[PROXY-IPv6] Khong tim duoc IPv6 hoat dong!")
                    return False

                from modules.ipv6_proxy import start_ipv6_proxy
                self._proxy = start_ipv6_proxy(
                    ipv6_address=working_ipv6,
                    port=port,
                    log_func=self.log
                )
                if not self._proxy:
                    self.log("[PROXY-IPv6] Khong tao duoc SOCKS5 proxy!")
                    return False

                self._activated = True
                self._ready = True
                self.log(f"[PROXY-IPv6] [v] Worker {worker_id}: IPv6={working_ipv6}, port={port}")
                return True
            else:
                # Worker khac: verify proxy port dang chay
                import socket
                try:
                    _test = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    _test.settimeout(2)
                    _test.connect(('127.0.0.1', port))
                    _test.close()
                    self._ready = True
                    self.log(f"[PROXY-IPv6] [v] Worker {worker_id}: Reuse proxy port {port}")
                    return True
                except Exception:
                    self.log(f"[PROXY-IPv6] Worker {worker_id}: Proxy port {port} chua san sang")
                    return False

        except ImportError as e:
            self.log(f"[PROXY-IPv6] Import error: {e}")
            return False
        except Exception as e:
            self.log(f"[PROXY-IPv6] Setup error: {e}")
            return False

    def setup_dedicated(self, worker_id: int, port: int, ipv6_address: str) -> bool:
        """
        Setup proxy rieng cho 1 worker (Server mode).
        Moi worker co SOCKS5 proxy rieng, IPv6 rieng.
        """
        self.worker_id = worker_id
        self.port = port

        try:
            from modules.ipv6_proxy import IPv6SocksProxy
            self._proxy = IPv6SocksProxy(
                listen_port=port,
                ipv6_address=ipv6_address,
                log_func=self.log
            )
            if self._proxy.start():
                self._activated = True
                self._ready = True
                self.log(f"[PROXY-IPv6] [v] Dedicated worker {worker_id}: IPv6={ipv6_address}, port={port}")
                return True
            return False
        except Exception as e:
            self.log(f"[PROXY-IPv6] Dedicated setup error: {e}")
            return False

    def rotate(self, reason: str = "403") -> bool:
        """Doi sang IPv6 tiep theo trong danh sach."""
        if not self._rotator:
            self.log("[PROXY-IPv6] Rotator chua khoi tao!")
            return False

        # Chi worker 0 rotate (VM mode)
        if self.worker_id != 0 and not self._proxy:
            self.log(f"[PROXY-IPv6] Worker {self.worker_id}: Skip rotate (worker 0 se lam)")
            return True

        new_ip = self._rotator.rotate()
        if new_ip:
            # Cap nhat SOCKS5 proxy voi IP moi
            if self._proxy:
                self._proxy.set_ipv6(new_ip)
            self.log(f"[PROXY-IPv6] [v] Rotated ({reason}): → {new_ip}")
            return True

        self.log(f"[PROXY-IPv6] [x] Rotate failed ({reason})")
        return False

    def rotate_to(self, new_ipv6: str) -> bool:
        """Doi sang 1 IPv6 cu the (Server mode dung)."""
        if self._proxy:
            self._proxy.stop()

        try:
            from modules.ipv6_proxy import IPv6SocksProxy
            self._proxy = IPv6SocksProxy(
                listen_port=self.port,
                ipv6_address=new_ipv6,
                log_func=self.log
            )
            self._proxy.start()
            self.log(f"[PROXY-IPv6] [v] Rotated to: {new_ipv6}")
            return True
        except Exception as e:
            self.log(f"[PROXY-IPv6] Rotate to {new_ipv6} failed: {e}")
            return False

    def get_chrome_arg(self) -> str:
        """Tra ve SOCKS5 proxy URL cho Chrome."""
        return f"socks5://127.0.0.1:{self.port}"

    def get_current_ip(self) -> str:
        """Tra ve IPv6 hien tai."""
        if self._rotator and self._rotator.current_ipv6:
            return self._rotator.current_ipv6
        if self._proxy and self._proxy.ipv6_address:
            return self._proxy.ipv6_address
        return "unknown"

    def stop(self):
        """Dung SOCKS5 proxy."""
        if self._proxy:
            self._proxy.stop()
            self._proxy = None
        self._ready = False
        self.log("[PROXY-IPv6] Stopped")

    def get_type(self) -> str:
        return "ipv6"

    def test_connectivity(self) -> bool:
        """Test IPv6 connectivity qua curl."""
        if self._rotator:
            return self._rotator.test_ipv6_connectivity()
        return False

    def get_rotator(self):
        """Tra ve IPv6Rotator instance (backward compat)."""
        return self._rotator
