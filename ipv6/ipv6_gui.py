#!/usr/bin/env python3
"""
IPv6 Pool Manager GUI - Giao dien quan ly IPv6 pool.
=====================================================

Chay:
    python -m ipv6.ipv6_gui

Chuc nang:
    - Ket noi MikroTik router
    - Xem trang thai pool (available/in_use/burned)
    - Doi IPv6 thu cong (1 hoac tat ca)
    - Test IPv6 connectivity
    - Quan ly pool (get/release/burn/rotate)
"""

import sys
import json
import time
import threading
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ipv6.mikrotik_api import MikroTikAPI
from ipv6.ipv6_pool import IPv6Pool
from ipv6.ipv6_server import start_api_server, stop_api_server, is_running as api_is_running
from ipv6 import create_pool

CONFIG_FILE = Path(__file__).parent / "config_test.json"


class IPv6PoolGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("IPv6 Pool Manager")
        self.root.geometry("820x760")
        self.root.resizable(True, True)

        self.pool = None
        self.config = {}
        self.connected = False

        self._build_ui()
        self._load_and_connect()

    # =========================================================================
    # UI BUILDING
    # =========================================================================

    def _build_ui(self):
        # Style
        style = ttk.Style()
        style.configure("Green.TLabel", foreground="green")
        style.configure("Red.TLabel", foreground="red")
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"))

        # ---- TOP: Connection Info ----
        top = ttk.LabelFrame(self.root, text="Router", padding=8)
        top.pack(fill="x", padx=8, pady=(8, 4))

        row0 = ttk.Frame(top)
        row0.pack(fill="x")

        ttk.Label(row0, text="Host:").pack(side="left")
        self.var_host = tk.StringVar(value="192.168.88.1")
        ttk.Entry(row0, textvariable=self.var_host, width=16).pack(side="left", padx=(2, 10))

        ttk.Label(row0, text="User:").pack(side="left")
        self.var_user = tk.StringVar(value="admin")
        ttk.Entry(row0, textvariable=self.var_user, width=10).pack(side="left", padx=(2, 10))

        ttk.Label(row0, text="Pass:").pack(side="left")
        self.var_pass = tk.StringVar(value="")
        ttk.Entry(row0, textvariable=self.var_pass, width=12, show="*").pack(side="left", padx=(2, 10))

        self.btn_connect = ttk.Button(row0, text="Ket noi", command=self._on_connect)
        self.btn_connect.pack(side="left", padx=4)

        self.lbl_status = ttk.Label(row0, text="Chua ket noi", style="Red.TLabel")
        self.lbl_status.pack(side="left", padx=8)

        # ---- STATS ----
        stats_frame = ttk.LabelFrame(self.root, text="Trang thai Pool", padding=8)
        stats_frame.pack(fill="x", padx=8, pady=4)

        self.var_available = tk.StringVar(value="0")
        self.var_in_use = tk.StringVar(value="0")
        self.var_burned = tk.StringVar(value="0")
        self.var_remaining = tk.StringVar(value="0/0")

        stats_row = ttk.Frame(stats_frame)
        stats_row.pack(fill="x")

        for label, var, color in [
            ("San sang:", self.var_available, "green"),
            ("Dang dung:", self.var_in_use, "blue"),
            ("Da chay (burned):", self.var_burned, "red"),
            ("Con lai:", self.var_remaining, "black"),
        ]:
            f = ttk.Frame(stats_row)
            f.pack(side="left", padx=12)
            ttk.Label(f, text=label).pack(side="left")
            l = ttk.Label(f, textvariable=var, font=("Segoe UI", 11, "bold"))
            l.pack(side="left", padx=4)
            l.configure(foreground=color)

        # ---- API SERVER ----
        api_frame = ttk.LabelFrame(self.root, text="API Server (cho VM/Server)", padding=8)
        api_frame.pack(fill="x", padx=8, pady=4)

        api_row = ttk.Frame(api_frame)
        api_row.pack(fill="x")

        ttk.Label(api_row, text="Port:").pack(side="left")
        self.var_port = tk.StringVar(value="8765")
        ttk.Entry(api_row, textvariable=self.var_port, width=6).pack(side="left", padx=(2, 10))

        self.btn_api = ttk.Button(api_row, text="Start API", command=self._on_toggle_api)
        self.btn_api.pack(side="left", padx=4)

        self.lbl_api_status = ttk.Label(api_row, text="API: Chua chay", style="Red.TLabel")
        self.lbl_api_status.pack(side="left", padx=8)

        self.lbl_api_url = ttk.Label(api_row, text="", foreground="gray")
        self.lbl_api_url.pack(side="left", padx=4)

        # ---- IP LIST ----
        list_frame = ttk.LabelFrame(self.root, text="Danh sach IP trong Pool", padding=4)
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Treeview
        cols = ("address", "subnet", "status", "uses", "last_used")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)
        self.tree.heading("address", text="IPv6 Address")
        self.tree.heading("subnet", text="Subnet")
        self.tree.heading("status", text="Trang thai")
        self.tree.heading("uses", text="So lan dung")
        self.tree.heading("last_used", text="Lan cuoi")

        self.tree.column("address", width=300)
        self.tree.column("subnet", width=70, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("uses", width=80, anchor="center")
        self.tree.column("last_used", width=140, anchor="center")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Tag colors
        self.tree.tag_configure("available", background="#d4edda")
        self.tree.tag_configure("in_use", background="#cce5ff")
        self.tree.tag_configure("burned", background="#f8d7da")

        # ---- BUTTONS ----
        btn_frame = ttk.LabelFrame(self.root, text="Thao tac", padding=8)
        btn_frame.pack(fill="x", padx=8, pady=4)

        row1 = ttk.Frame(btn_frame)
        row1.pack(fill="x", pady=2)

        self.btn_get = ttk.Button(row1, text="Lay 1 IP", command=self._on_get_ip, width=14)
        self.btn_get.pack(side="left", padx=4)

        self.btn_release = ttk.Button(row1, text="Tra lai IP", command=self._on_release_ip, width=14)
        self.btn_release.pack(side="left", padx=4)

        self.btn_burn = ttk.Button(row1, text="Burn IP (403)", command=self._on_burn_ip, width=14)
        self.btn_burn.pack(side="left", padx=4)

        self.btn_rotate = ttk.Button(row1, text="Doi IP (Rotate)", command=self._on_rotate_ip, width=14)
        self.btn_rotate.pack(side="left", padx=4)

        self.btn_test = ttk.Button(row1, text="Test IP", command=self._on_test_ip, width=14)
        self.btn_test.pack(side="left", padx=4)

        row2 = ttk.Frame(btn_frame)
        row2.pack(fill="x", pady=2)

        self.btn_rotate_all = ttk.Button(row2, text="Doi TAT CA IP", command=self._on_rotate_all, width=14)
        self.btn_rotate_all.pack(side="left", padx=4)

        self.btn_refill = ttk.Button(row2, text="Them IP vao Pool", command=self._on_refill, width=14)
        self.btn_refill.pack(side="left", padx=4)

        self.btn_refresh = ttk.Button(row2, text="Lam moi", command=self._on_refresh, width=14)
        self.btn_refresh.pack(side="left", padx=4)

        self.btn_reset = ttk.Button(row2, text="Reset Pool", command=self._on_reset, width=14)
        self.btn_reset.pack(side="left", padx=4)

        # ---- LOG ----
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=4)
        log_frame.pack(fill="x", padx=8, pady=(4, 8))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9))
        self.log_text.pack(fill="x")
        self.log_text.configure(state="disabled")

    # =========================================================================
    # CONNECTION
    # =========================================================================

    def _load_and_connect(self):
        """Load config va tu dong ket noi."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                mk = self.config.get("mikrotik", {})
                self.var_host.set(mk.get("host", "192.168.88.1"))
                self.var_user.set(mk.get("username", "admin"))
                self.var_pass.set(mk.get("password", ""))
                self._log(f"Config loaded: {CONFIG_FILE.name}")
                # Auto connect
                self.root.after(500, self._on_connect)
            except Exception as e:
                self._log(f"Config error: {e}")
        else:
            self._log("Chua co config. Nhap thong tin router roi nhan 'Ket noi'")
            self._log(f"Hoac chay: python -m ipv6.test_pool --detect")

    def _on_connect(self):
        """Ket noi MikroTik va khoi tao pool."""
        self.btn_connect.configure(state="disabled")
        self.lbl_status.configure(text="Dang ket noi...", style="")

        def do_connect():
            host = self.var_host.get()
            user = self.var_user.get()
            passwd = self.var_pass.get()

            # Update config
            self.config = {
                "mikrotik": {
                    "host": host,
                    "username": user,
                    "password": passwd,
                    "interface": self.config.get("mikrotik", {}).get("interface", "bridge"),
                    "prefix": self.config.get("mikrotik", {}).get("prefix", ""),
                    "subnet_start": self.config.get("mikrotik", {}).get("subnet_start", 101),
                    "subnet_end": self.config.get("mikrotik", {}).get("subnet_end", 255),
                    "pool_min": self.config.get("mikrotik", {}).get("pool_min", 3),
                    "pool_max": self.config.get("mikrotik", {}).get("pool_max", 20),
                }
            }

            try:
                self.pool = create_pool(self.config, log_func=self._log)
                ok = self.pool.api.test_connection()

                if ok:
                    self.connected = True
                    self.pool.init()
                    self.root.after(0, lambda: self.lbl_status.configure(
                        text=f"OK - {host}", style="Green.TLabel"))
                    self.root.after(0, self._refresh_ui)
                    self._log(f"Ket noi thanh cong: {host}")
                else:
                    self.connected = False
                    self.root.after(0, lambda: self.lbl_status.configure(
                        text="THAT BAI", style="Red.TLabel"))
                    self._log(f"Khong ket noi duoc {host}")
            except Exception as e:
                self.connected = False
                self.root.after(0, lambda: self.lbl_status.configure(
                    text="LOI", style="Red.TLabel"))
                self._log(f"Loi ket noi: {e}")
            finally:
                self.root.after(0, lambda: self.btn_connect.configure(state="normal"))

        threading.Thread(target=do_connect, daemon=True).start()

    # =========================================================================
    # API SERVER
    # =========================================================================

    def _on_toggle_api(self):
        """Start/Stop API server."""
        if api_is_running():
            stop_api_server()
            self.btn_api.configure(text="Start API")
            self.lbl_api_status.configure(text="API: Dung", style="Red.TLabel")
            self.lbl_api_url.configure(text="")
            self._log("API Server dung")
        else:
            if not self._check_connected():
                return
            try:
                port = int(self.var_port.get())
            except ValueError:
                port = 8765

            ok = start_api_server(self.pool, host="0.0.0.0", port=port, log_func=self._log)
            if ok:
                # Tim IP cua may nay de hien thi URL
                import socket
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect(("192.168.88.1", 80))
                    local_ip = s.getsockname()[0]
                    s.close()
                except Exception:
                    local_ip = "localhost"

                self.btn_api.configure(text="Stop API")
                self.lbl_api_status.configure(text="API: Dang chay", style="Green.TLabel")
                self.lbl_api_url.configure(text=f"http://{local_ip}:{port}")
                self._log(f"API Server: http://{local_ip}:{port}")
            else:
                self._log("API Server start that bai!")

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def _on_get_ip(self):
        if not self._check_connected():
            return

        def do():
            ip = self.pool.get_ip()
            if ip:
                self._log(f"Lay IP: {ip}")
            else:
                self._log("Het IP!")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_release_ip(self):
        if not self._check_connected():
            return
        entry = self._get_selected_entry()
        if not entry:
            return
        if entry["status"] != "in_use":
            messagebox.showinfo("Thong bao", "Chi tra lai duoc IP dang 'in_use'")
            return

        def do():
            self.pool.release_ip(entry["address"])
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_burn_ip(self):
        if not self._check_connected():
            return
        entry = self._get_selected_entry()
        if not entry:
            return

        def do():
            self.pool.burn_ip(entry["address"], reason="manual_burn")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_rotate_ip(self):
        if not self._check_connected():
            return
        entry = self._get_selected_entry()
        if not entry:
            return
        if entry["status"] not in ("in_use", "available"):
            messagebox.showinfo("Thong bao", "Chon IP dang 'available' hoac 'in_use' de doi")
            return

        def do():
            new_ip = self.pool.rotate_ip(entry["address"], reason="manual_rotate")
            if new_ip:
                self._log(f"Doi thanh cong: {entry['address']} → {new_ip}")
            else:
                self._log(f"Doi that bai - het IP!")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_rotate_all(self):
        if not self._check_connected():
            return
        active = [e for e in self.pool.pool if e["status"] in ("available", "in_use")]
        if not active:
            messagebox.showinfo("Thong bao", "Pool trong, khong co IP de doi")
            return

        ok = messagebox.askyesno("Xac nhan",
            f"Doi TAT CA {len(active)} IP trong pool?\n"
            f"Tat ca IP hien tai se bi burn va lay IP moi.")
        if not ok:
            return

        def do():
            self._log(f"Dang doi tat ca {len(active)} IP...")
            addresses = [e["address"] for e in active]

            # Burn tat ca TRUOC (khong refill giua chung)
            with self.pool._lock:
                for entry in self.pool.pool:
                    if entry["address"] in addresses:
                        entry["status"] = "burned"
                        entry["burned_at"] = time.time()
                        entry["burn_reason"] = "manual_rotate_all"
                        self.pool._burned_addresses.add(entry["address"])
                self.pool._save_pool()

            self._log(f"Burned {len(addresses)} IP")

            # Sync de xoa burned entries
            self.pool._sync_with_router()

            # Refill dung so luong can
            added = self.pool._refill(count=len(addresses))
            self._log(f"Da doi xong: burn {len(addresses)}, them moi {added}")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_refill(self):
        if not self._check_connected():
            return

        def do():
            added = self.pool._refill(count=5)
            self._log(f"Da them {added} IP vao pool")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_test_ip(self):
        if not self._check_connected():
            return
        entry = self._get_selected_entry()
        if not entry:
            return

        addr = entry["address"]
        self._log(f"Dang test {addr}...")

        def do():
            ok = self.pool.api.test_ipv6_connectivity(addr)
            if ok:
                self._log(f"TEST OK: {addr} - IPv6 hoat dong!")
            else:
                self._log(f"TEST FAIL: {addr} - Khong ket noi duoc")

        threading.Thread(target=do, daemon=True).start()

    def _on_refresh(self):
        if not self._check_connected():
            return

        def do():
            self.pool._sync_with_router()
            self.pool._refill_if_needed()
            self._log("Da lam moi pool")
            self.root.after(0, self._refresh_ui)

        threading.Thread(target=do, daemon=True).start()

    def _on_reset(self):
        if not self._check_connected():
            return
        ok = messagebox.askyesno("Xac nhan",
            "Reset pool?\n"
            "Xoa toan bo tracking data (IP van giu tren router).\n"
            "Pool se bat dau lai tu dau.")
        if not ok:
            return

        self.pool.reset_pool()
        self.pool._refill_if_needed()
        self._refresh_ui()
        self._log("Da reset pool")

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _check_connected(self) -> bool:
        if not self.connected or not self.pool:
            messagebox.showwarning("Chua ket noi", "Hay ket noi MikroTik truoc!")
            return False
        return True

    def _get_selected_entry(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Thong bao", "Chon 1 IP trong danh sach truoc!")
            return None
        item = self.tree.item(sel[0])
        addr = item["values"][0]
        for entry in self.pool.pool:
            if entry["address"] == addr:
                return entry
        return None

    def _refresh_ui(self):
        """Cap nhat giao dien."""
        if not self.pool:
            return

        # Stats
        status = self.pool.get_status()
        self.var_available.set(str(status["available"]))
        self.var_in_use.set(str(status["in_use"]))
        self.var_burned.set(str(status.get("burned_total", 0)))
        remaining = status.get("range_remaining", 0)
        total = status.get("range_total", 0)
        self.var_remaining.set(f"{remaining}/{total}")

        # Tree
        self.tree.delete(*self.tree.get_children())
        for entry in self.pool.pool:
            addr = entry.get("address", "?")
            subnet = entry.get("subnet_hex", "?")
            st = entry.get("status", "?")
            uses = entry.get("use_count", 0)
            last = ""
            if entry.get("used_at"):
                last = time.strftime("%H:%M:%S %d/%m", time.localtime(entry["used_at"]))
            elif entry.get("created_at"):
                last = time.strftime("%H:%M:%S %d/%m", time.localtime(entry["created_at"]))

            # Status display
            st_display = {"available": "San sang", "in_use": "Dang dung", "burned": "Da chay"}.get(st, st)

            tag = st if st in ("available", "in_use", "burned") else ""
            self.tree.insert("", "end", values=(addr, subnet, st_display, uses, last), tags=(tag,))

    def _log(self, msg):
        """Ghi log (thread-safe)."""
        def do():
            self.log_text.configure(state="normal")
            timestamp = time.strftime("%H:%M:%S")
            # Clean log prefix
            clean_msg = msg.replace("[POOL] ", "").replace("[MikroTik] ", "")
            self.log_text.insert("end", f"[{timestamp}] {clean_msg}\n")
            self.log_text.see("end")
            # Giu 200 dong
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 200:
                self.log_text.delete("1.0", f"{lines - 200}.0")
            self.log_text.configure(state="disabled")

        if threading.current_thread() is threading.main_thread():
            do()
        else:
            self.root.after(0, do)


def main():
    root = tk.Tk()
    app = IPv6PoolGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
