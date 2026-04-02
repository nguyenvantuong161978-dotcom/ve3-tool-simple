#!/usr/bin/env python3
"""
ProxyXoayProvider - Proxy provider dung proxyxoay.shop API.
============================================================

ProxyXoay.shop: Dich vu proxy xoay Viet Nam
- Lay proxy qua API: GET /api/get.php?key=...
- Tra ve SOCKS5 hoac HTTP proxy
- Proxy tu dong doi sau ~1777s (TTL)
- Rotate = goi lai API de lay proxy moi

Flow:
  Chrome → socks5://IP:PORT (direct, khong can bridge)
    → Target website

Config (1 key):
    proxyxoay:
        api_key: "key1"
        proxy_type: "socks5"

Config (nhieu key - moi worker 1 key rieng):
    proxyxoay:
        api_keys:
            - "key1"
            - "key2"
            - "key3"
        proxy_type: "socks5"
"""

import time
import requests
from typing import Optional, Callable
from modules.proxy_providers.base_provider import ProxyProvider


class ProxyXoayProvider(ProxyProvider):
    """
    Proxy provider dung proxyxoay.shop API.

    Config (1 key):
        proxyxoay:
            api_key: "key1"
            proxy_type: "socks5"

    Config (nhieu key - moi worker 1 key):
        proxyxoay:
            api_keys:
                - "key1"
                - "key2"
            proxy_type: "socks5"
    """

    API_URL = "https://proxyxoay.shop/api/get.php"

    def __init__(self, config: dict = None, log_func: Callable = print):
        super().__init__(config, log_func)
        px_cfg = (config or {}).get('proxyxoay', {})

        # Ho tro ca api_key (1 key) va api_keys (danh sach)
        self._api_keys = px_cfg.get('api_keys', [])
        single_key = px_cfg.get('api_key', '')
        if single_key and not self._api_keys:
            self._api_keys = [single_key]

        self.api_key = ''  # Se duoc gan trong setup() theo worker_id
        self.proxy_type = px_cfg.get('proxy_type', 'socks5')  # socks5 or http

        self._current_ip = ''
        self._current_port = 0
        self._proxy_expire_time = 0  # timestamp khi proxy het han
        self._last_api_message = ''  # Luu message cuoi tu API (de parse cooldown)

    def setup(self, worker_id: int = 0, port: int = 0) -> bool:
        """
        Khoi tao ProxyXoay - lay proxy dau tien tu API.

        Args:
            worker_id: ID cua Chrome worker
            port: Khong dung (proxy direct, khong can local port)
        """
        self.worker_id = worker_id

        if not self._api_keys:
            self.log("[PROXY-PX] Thieu API key!")
            return False

        # Chon key theo worker_id (round-robin neu worker nhieu hon key)
        key_index = worker_id % len(self._api_keys)
        self.api_key = self._api_keys[key_index]

        self.log(f"[PROXY-PX] Setup worker {worker_id}: proxyxoay.shop (key {key_index+1}/{len(self._api_keys)})")
        self.log(f"[PROXY-PX] Type: {self.proxy_type}")

        # Lay proxy dau tien (retry neu dang cooldown)
        max_retries = 3
        for attempt in range(max_retries):
            ok = self._fetch_proxy()
            if ok:
                self._ready = True
                return True

            # Check cooldown
            if self._last_api_message:
                import re
                m = re.search(r'(\d+)s', self._last_api_message)
                if m and attempt < max_retries - 1:
                    wait_secs = int(m.group(1)) + 2
                    self.log(f"[PROXY-PX] Cooldown {wait_secs}s, doi... ({attempt+1}/{max_retries})")
                    time.sleep(wait_secs)
                    continue

            break

        self.log("[PROXY-PX] [x] Khong lay duoc proxy!")
        return False

    def rotate(self, reason: str = "403") -> bool:
        """
        Doi IP bang cach goi API lay proxy moi.
        API co cooldown ~60s giua moi lan doi → retry voi backoff.
        """
        self.log(f"[PROXY-PX] Rotate ({reason})...")

        max_retries = 5
        for attempt in range(max_retries):
            ok = self._fetch_proxy()
            if ok:
                self.log(f"[PROXY-PX] [v] Proxy moi: {self._current_ip}:{self._current_port}")
                return True

            # Parse cooldown tu error message (vd: "Con 59s moi co the doi proxy")
            if self._last_api_message:
                import re
                m = re.search(r'(\d+)s', self._last_api_message)
                if m:
                    wait_secs = int(m.group(1)) + 2  # +2s buffer
                    self.log(f"[PROXY-PX] Cooldown {wait_secs}s, doi... ({attempt+1}/{max_retries})")
                    time.sleep(wait_secs)
                    continue

            # Khong phai cooldown → loi khac
            self.log(f"[PROXY-PX] [x] Rotate that bai!")
            return False

        self.log(f"[PROXY-PX] [x] Rotate that bai sau {max_retries} lan!")
        return False

    def get_chrome_arg(self) -> str:
        """Tra ve proxy URL cho Chrome (direct connection, khong can bridge)."""
        if not self._current_ip:
            return ""
        if self.proxy_type == 'socks5':
            return f"socks5://{self._current_ip}:{self._current_port}"
        else:
            return f"http://{self._current_ip}:{self._current_port}"

    def get_current_ip(self) -> str:
        """Tra ve IP proxy hien tai."""
        if self._current_ip:
            ttl = max(0, int(self._proxy_expire_time - time.time()))
            return f"{self._current_ip} (TTL:{ttl}s)"
        return "unknown"

    def has_ttl(self) -> bool:
        """ProxyXoay co TTL - proxy het han sau ~1777s."""
        return True

    def get_ttl(self) -> int:
        """Tra ve so giay con lai cua proxy hien tai."""
        if self._proxy_expire_time > 0:
            return max(0, int(self._proxy_expire_time - time.time()))
        return 0

    def stop(self):
        """Khong can cleanup gi (khong co local bridge)."""
        self._ready = False
        self._current_ip = ''
        self._current_port = 0
        self.log("[PROXY-PX] Stopped")

    def get_type(self) -> str:
        return "proxyxoay"

    def test_connectivity(self) -> bool:
        """Test ket noi qua ProxyXoay proxy."""
        if not self._current_ip:
            # Thu lay proxy truoc
            if not self._fetch_proxy():
                return False

        try:
            proxy_url = self.get_chrome_arg()
            proxies = {"http": proxy_url, "https": proxy_url}
            resp = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=15)
            if resp.status_code == 200:
                ip = resp.json().get('origin', 'unknown')
                self.log(f"[PROXY-PX] [v] Test OK: IP = {ip}")
                return True
            self.log(f"[PROXY-PX] [x] Test failed: HTTP {resp.status_code}")
            return False
        except Exception as e:
            self.log(f"[PROXY-PX] [x] Test failed: {e}")
            return False

    def _fetch_proxy(self) -> bool:
        """
        Goi API proxyxoay.shop de lay proxy moi.

        API: GET /api/get.php?key={key}&nhamang=random&tinhthanh=0&whitelist=
        Response: {"status":100,"proxyhttp":"IP:PORT::","proxysocks5":"IP:PORT::","message":"proxy nay se die sau 1777s"}
        """
        try:
            params = {
                'key': self.api_key,
                'nhamang': 'random',
                'tinhthanh': 0,
                'whitelist': '',
            }
            resp = requests.get(self.API_URL, params=params, timeout=15)
            data = resp.json()

            if data.get('status') != 100:
                msg = data.get('message', 'Unknown error')
                self._last_api_message = msg
                self.log(f"[PROXY-PX] API error: {msg}")
                return False

            self._last_api_message = ''

            # Parse proxy string "IP:PORT::" hoac "IP:PORT"
            if self.proxy_type == 'socks5':
                proxy_str = data.get('proxysocks5', '')
            else:
                proxy_str = data.get('proxyhttp', '')

            if not proxy_str:
                self.log("[PROXY-PX] API khong tra ve proxy!")
                return False

            # Clean up trailing colons: "IP:PORT::" → "IP:PORT"
            proxy_str = proxy_str.rstrip(':')
            parts = proxy_str.split(':')
            if len(parts) < 2:
                self.log(f"[PROXY-PX] Proxy format sai: {proxy_str}")
                return False

            self._current_ip = parts[0]
            self._current_port = int(parts[1])

            # Parse TTL tu message (vd: "proxy nay se die sau 1777s")
            msg = data.get('message', '')
            ttl = 1777  # default
            import re
            m = re.search(r'(\d+)s', msg)
            if m:
                ttl = int(m.group(1))
            self._proxy_expire_time = time.time() + ttl

            self.log(f"[PROXY-PX] Got proxy: {self._current_ip}:{self._current_port} (TTL:{ttl}s)")
            return True

        except Exception as e:
            self.log(f"[PROXY-PX] API call failed: {e}")
            return False
