"""
Server GUI - Giao dien cai dat va quan ly Chrome Server.

Chay: python server/server_gui.py
  hoac: START_SERVER.bat

Flow:
1. Hien giao dien cai dat (IPv6, so Chrome)
2. Bam START → khoi dong Flask + Chrome workers
3. Hien trang thai workers, queue, logs
"""
import sys
import os
import json
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(TOOL_DIR))

# Colors (dark theme)
BG = '#0f172a'
BG2 = '#1e293b'
FG = '#e2e8f0'
FG2 = '#94a3b8'
BLUE = '#38bdf8'
GREEN = '#22c55e'
ORANGE = '#f97316'
RED = '#ef4444'
YELLOW = '#eab308'
BORDER = '#334155'


class ServerGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Chrome Server")
        self.geometry("700x850")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._server_started = False
        self._logs = []
        self._workers_info = []
        self._settings_file = TOOL_DIR / "config" / "server_gui.json"

        self._build_setup_page()
        self._load_settings()

    # ============================================================
    # Setup Page
    # ============================================================
    def _build_setup_page(self):
        self.setup_frame = tk.Frame(self, bg=BG)
        self.setup_frame.pack(fill='both', expand=True)

        # Title
        tk.Label(self.setup_frame, text="Chrome Server", font=("Segoe UI", 20, "bold"),
                 bg=BG, fg=BLUE).pack(pady=(15, 3))
        tk.Label(self.setup_frame, text="Cai dat va khoi dong server", font=("Segoe UI", 10),
                 bg=BG, fg=FG2).pack(pady=(0, 15))

        # Settings card
        card = tk.Frame(self.setup_frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        card.pack(padx=80, fill='x')

        # IPv6 toggle
        row1 = tk.Frame(card, bg=BG2)
        row1.pack(fill='x', padx=20, pady=(20, 10))

        tk.Label(row1, text="IPv6 Proxy", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=FG).pack(side='left')

        self.ipv6_var = tk.BooleanVar(value=True)
        self.ipv6_btn = tk.Button(row1, text="BAT", font=("Segoe UI", 11, "bold"),
                                  bg=GREEN, fg='white', width=6, relief='flat',
                                  command=self._toggle_ipv6)
        self.ipv6_btn.pack(side='right')

        tk.Label(card, text="BAT: Moi Chrome dung IPv6 rieng (chong 403).  TAT: Dung IPv4 chung.",
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w')

        # IPv6 list input (optional - bo sung them IPv6 ngoai sheet)
        tk.Label(card, text="IPv6 (moi dong 1 IP):",
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w', pady=(8, 2))

        ipv6_text_frame = tk.Frame(card, bg=BG2)
        ipv6_text_frame.pack(fill='x', padx=20, pady=(0, 2))

        self.ipv6_text = tk.Text(ipv6_text_frame, height=3, width=50,
                                  font=("Consolas", 9), bg='#0f172a', fg=FG,
                                  insertbackground=FG, relief='solid', bd=1,
                                  highlightbackground=BORDER)
        self.ipv6_text.pack(fill='x')

        # IPv6 buttons: THEM VAO MAY + TEST
        ipv6_btn_frame = tk.Frame(card, bg=BG2)
        ipv6_btn_frame.pack(fill='x', padx=20, pady=(2, 5))

        self.ipv6_add_btn = tk.Button(ipv6_btn_frame, text="THEM VAO MAY",
                                       font=("Segoe UI", 9, "bold"),
                                       bg=BLUE, fg='#0f172a', relief='flat', cursor='hand2',
                                       command=self._add_ipv6_to_machine)
        self.ipv6_add_btn.pack(side='left', padx=(0, 8))

        self.ipv6_test_btn = tk.Button(ipv6_btn_frame, text="TEST IPv6",
                                        font=("Segoe UI", 9, "bold"),
                                        bg=ORANGE, fg='#0f172a', relief='flat', cursor='hand2',
                                        command=self._test_ipv6)
        self.ipv6_test_btn.pack(side='left')

        self.ipv6_status_label = tk.Label(ipv6_btn_frame, text="", font=("Segoe UI", 9),
                                           bg=BG2, fg=FG2)
        self.ipv6_status_label.pack(side='left', padx=10)

        # Separator
        tk.Frame(card, bg=BORDER, height=1).pack(fill='x', padx=20, pady=8)

        # === v1.0.545: Proxy Provider (Webshare Rotating Residential) ===
        row_proxy = tk.Frame(card, bg=BG2)
        row_proxy.pack(fill='x', padx=20, pady=(0, 5))

        tk.Label(row_proxy, text="Proxy Provider", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=FG).pack(side='left')

        self.proxy_type_var = tk.StringVar(value="none")
        proxy_options = ["none", "ipv6", "webshare"]
        self.proxy_combo = ttk.Combobox(row_proxy, textvariable=self.proxy_type_var,
                                         values=proxy_options, state='readonly', width=12)
        self.proxy_combo.set("none")
        self.proxy_combo.pack(side='right')
        self.proxy_combo.bind("<<ComboboxSelected>>", self._on_proxy_type_changed)

        tk.Label(card, text="none: Khong proxy | ipv6: IPv6 rotation | webshare: Webshare.io Rotating",
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w')

        # Webshare settings frame (an/hien theo proxy_type)
        self.ws_frame = tk.Frame(card, bg=BG2)
        self.ws_frame.pack(fill='x', padx=20, pady=(5, 5))

        ws_row1 = tk.Frame(self.ws_frame, bg=BG2)
        ws_row1.pack(fill='x', pady=2)
        tk.Label(ws_row1, text="Username:", font=("Segoe UI", 9), bg=BG2, fg=FG2, width=10, anchor='w').pack(side='left')
        self.ws_username_var = tk.StringVar(value="")
        tk.Entry(ws_row1, textvariable=self.ws_username_var, font=("Consolas", 9),
                 bg='#0f172a', fg=FG, insertbackground=FG, relief='solid', bd=1).pack(side='left', fill='x', expand=True)

        ws_row2 = tk.Frame(self.ws_frame, bg=BG2)
        ws_row2.pack(fill='x', pady=2)
        tk.Label(ws_row2, text="Password:", font=("Segoe UI", 9), bg=BG2, fg=FG2, width=10, anchor='w').pack(side='left')
        self.ws_password_var = tk.StringVar(value="")
        tk.Entry(ws_row2, textvariable=self.ws_password_var, font=("Consolas", 9),
                 bg='#0f172a', fg=FG, insertbackground=FG, relief='solid', bd=1).pack(side='left', fill='x', expand=True)

        ws_row3 = tk.Frame(self.ws_frame, bg=BG2)
        ws_row3.pack(fill='x', pady=2)
        tk.Label(ws_row3, text="Machine ID:", font=("Segoe UI", 9), bg=BG2, fg=FG2, width=10, anchor='w').pack(side='left')
        self.ws_machine_var = tk.StringVar(value="1")
        tk.Entry(ws_row3, textvariable=self.ws_machine_var, font=("Consolas", 9),
                 bg='#0f172a', fg=FG, insertbackground=FG, relief='solid', bd=1, width=5).pack(side='left')

        self.ws_test_btn = tk.Button(ws_row3, text="TEST", font=("Segoe UI", 9, "bold"),
                                      bg=ORANGE, fg='#0f172a', relief='flat', cursor='hand2',
                                      command=self._test_webshare)
        self.ws_test_btn.pack(side='right')

        # Mac dinh an webshare settings
        self.ws_frame.pack_forget()

        # Separator
        tk.Frame(card, bg=BORDER, height=1).pack(fill='x', padx=20, pady=8)

        # Chrome count
        row2 = tk.Frame(card, bg=BG2)
        row2.pack(fill='x', padx=20, pady=(0, 10))

        tk.Label(row2, text="So luong Chrome", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=FG).pack(side='left')

        self.chrome_var = tk.StringVar(value="0")
        chrome_options = ["Tat ca", "1", "2", "3", "4", "5"]
        self.chrome_combo = ttk.Combobox(row2, textvariable=self.chrome_var,
                                         values=chrome_options, state='readonly', width=10)
        self.chrome_combo.set("Tat ca")
        self.chrome_combo.pack(side='right')

        tk.Label(card, text="Chon so Chrome workers chay song song.",
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w', pady=(0, 10))

        # Separator
        tk.Frame(card, bg=BORDER, height=1).pack(fill='x', padx=20, pady=5)

        # Accounts input
        tk.Label(card, text="Tai khoan Google", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=FG).pack(padx=20, anchor='w', pady=(10, 0))
        tk.Label(card, text="Moi dong 1 tai khoan: email|password|2fa_secret",
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w', pady=(2, 4))

        acc_text_frame = tk.Frame(card, bg=BG2)
        acc_text_frame.pack(fill='x', padx=20, pady=(0, 20))

        self.accounts_text = tk.Text(acc_text_frame, height=3, width=50,
                                      font=("Consolas", 9), bg='#0f172a', fg=FG,
                                      insertbackground=FG, relief='solid', bd=1,
                                      highlightbackground=BORDER)
        self.accounts_text.pack(fill='x')

        # Buttons row: UPDATE + START
        btn_row = tk.Frame(self.setup_frame, bg=BG)
        btn_row.pack(fill='x', padx=80, pady=15)

        # UPDATE button
        self.update_btn = tk.Button(btn_row, text="UPDATE",
                                     font=("Segoe UI", 12, "bold"),
                                     bg='#0984e3', fg='white', activebackground='#0766b2',
                                     relief='flat', cursor='hand2', width=10,
                                     command=self._run_update)
        self.update_btn.pack(side='left', padx=(0, 10), ipady=8)

        # START button
        self.start_btn = tk.Button(btn_row, text="START SERVER",
                                   font=("Segoe UI", 16, "bold"),
                                   bg=GREEN, fg='#0f172a', activebackground='#16a34a',
                                   relief='flat', cursor='hand2', height=2,
                                   command=self._on_start)
        self.start_btn.pack(side='left', fill='x', expand=True)

        # Version
        version = "?"
        try:
            vf = TOOL_DIR / "VERSION.txt"
            if vf.exists():
                version = vf.read_text(encoding='utf-8').split('\n')[0].strip()
        except:
            pass
        tk.Label(self.setup_frame, text=f"v{version}", font=("Segoe UI", 9),
                 bg=BG, fg=FG2).pack(side='bottom', pady=10)

    def _load_settings(self):
        """Load settings tu file JSON."""
        try:
            if self._settings_file.exists():
                data = json.loads(self._settings_file.read_text(encoding='utf-8'))
                # IPv6 toggle
                if 'use_ipv6' in data:
                    self.ipv6_var.set(data['use_ipv6'])
                    if data['use_ipv6']:
                        self.ipv6_btn.config(text="BAT", bg=GREEN)
                    else:
                        self.ipv6_btn.config(text="TAT", bg='#475569')
                # IPv6 list
                if data.get('ipv6_list'):
                    self.ipv6_text.delete("1.0", "end")
                    self.ipv6_text.insert("1.0", "\n".join(data['ipv6_list']))
                # Chrome count
                if 'chrome_count' in data:
                    val = data['chrome_count']
                    self.chrome_combo.set("Tat ca" if val == 0 else str(val))
                # Accounts
                if data.get('accounts_raw'):
                    self.accounts_text.delete("1.0", "end")
                    self.accounts_text.insert("1.0", "\n".join(data['accounts_raw']))
                # v1.0.545: Proxy Provider
                if data.get('proxy_type'):
                    self.proxy_type_var.set(data['proxy_type'])
                    self._on_proxy_type_changed()
                if data.get('ws_username'):
                    self.ws_username_var.set(data['ws_username'])
                if data.get('ws_password'):
                    self.ws_password_var.set(data['ws_password'])
                if data.get('ws_machine_id'):
                    self.ws_machine_var.set(str(data['ws_machine_id']))
        except Exception:
            pass

    def _save_settings(self):
        """Luu settings ra file JSON."""
        try:
            self._settings_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'use_ipv6': self.ipv6_var.get(),
                'ipv6_list': self._get_ipv6_list(),
                'chrome_count': self._get_chrome_count(),
                'accounts_raw': self._get_accounts_raw(),
                # v1.0.545: Proxy Provider
                'proxy_type': self.proxy_type_var.get(),
                'ws_username': self.ws_username_var.get().strip(),
                'ws_password': self.ws_password_var.get().strip(),
                'ws_machine_id': int(self.ws_machine_var.get().strip() or '1'),
            }
            self._settings_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception:
            pass

    def _on_proxy_type_changed(self, event=None):
        """v1.0.545: Hien/an webshare settings khi doi proxy type."""
        ptype = self.proxy_type_var.get()
        if ptype == "webshare":
            self.ws_frame.pack(fill='x', padx=20, pady=(5, 5))
        else:
            self.ws_frame.pack_forget()

    def _test_webshare(self):
        """v1.0.545: Test ket noi Webshare proxy."""
        import threading
        def _do_test():
            self.ws_test_btn.config(state='disabled', text="Testing...")
            try:
                from modules.proxy_providers.webshare_provider import WebshareProvider
                provider = WebshareProvider(
                    config={'webshare': {
                        'rotating_host': 'p.webshare.io',
                        'rotating_port': 80,
                        'rotating_username': self.ws_username_var.get().strip(),
                        'rotating_password': self.ws_password_var.get().strip(),
                        'machine_id': int(self.ws_machine_var.get().strip() or '1'),
                    }},
                    log_func=lambda msg, lvl="INFO": print(msg),
                )
                ok = provider.test_connectivity()
                if ok:
                    self.ws_test_btn.config(text="OK!", bg=GREEN)
                else:
                    self.ws_test_btn.config(text="FAIL!", bg=RED)
            except Exception as e:
                self.ws_test_btn.config(text=f"ERR", bg=RED)
                print(f"Webshare test error: {e}")
            finally:
                self.ws_test_btn.config(state='normal')
                self.root.after(3000, lambda: self.ws_test_btn.config(text="TEST", bg=ORANGE))
        threading.Thread(target=_do_test, daemon=True).start()

    def _get_proxy_config(self) -> dict:
        """v1.0.545: Lay proxy provider config tu GUI."""
        ptype = self.proxy_type_var.get()
        return {
            'proxy_provider': {
                'type': ptype,
                'webshare': {
                    'rotating_host': 'p.webshare.io',
                    'rotating_port': 80,
                    'rotating_username': self.ws_username_var.get().strip(),
                    'rotating_password': self.ws_password_var.get().strip(),
                    'machine_id': int(self.ws_machine_var.get().strip() or '1'),
                },
            }
        }

    def _toggle_ipv6(self):
        current = self.ipv6_var.get()
        self.ipv6_var.set(not current)
        if not current:
            self.ipv6_btn.config(text="BAT", bg=GREEN)
        else:
            self.ipv6_btn.config(text="TAT", bg='#475569')

    def _get_ipv6_list(self):
        """Lay danh sach IPv6 tu text box."""
        text = self.ipv6_text.get("1.0", "end").strip()
        return [
            line.strip() for line in text.split('\n')
            if line.strip() and ':' in line.strip()
        ]

    def _get_accounts_raw(self):
        """Lay danh sach dong tai khoan (chua parse)."""
        text = self.accounts_text.get("1.0", "end").strip()
        return [
            line.strip() for line in text.split('\n')
            if line.strip() and '|' in line.strip()
        ]

    def _get_accounts_parsed(self):
        """Parse tai khoan tu text box thanh list dict."""
        accounts = []
        for line in self._get_accounts_raw():
            parts = line.split('|')
            if len(parts) >= 2:
                acc = {
                    'id': parts[0].strip(),
                    'password': parts[1].strip(),
                    'totp_secret': parts[2].strip() if len(parts) >= 3 else '',
                }
                accounts.append(acc)
        return accounts

    def _add_ipv6_to_machine(self):
        """Them IPv6 vao network interface bang netsh."""
        ipv6_list = self._get_ipv6_list()
        if not ipv6_list:
            self.ipv6_status_label.config(text="Chua nhap IPv6!", fg=RED)
            return

        self.ipv6_add_btn.config(state='disabled', text="DANG THEM...")
        self.ipv6_status_label.config(text="", fg=FG2)
        threading.Thread(target=self._do_add_ipv6, args=(ipv6_list,), daemon=True).start()

    def _do_add_ipv6(self, ipv6_list):
        """Thread: chay netsh de add IPv6."""
        import subprocess
        added = 0
        skipped = 0
        failed = 0

        # Tim network interface name
        iface = self._detect_interface()

        for ip in ipv6_list:
            try:
                result = subprocess.run(
                    ['netsh', 'interface', 'ipv6', 'add', 'address', iface, ip],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    added += 1
                elif 'already' in result.stderr.lower() or 'da ton tai' in result.stderr.lower() \
                        or result.returncode == 1:
                    # Co the da ton tai
                    skipped += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

        msg = f"Them: {added}  Co san: {skipped}  Loi: {failed}"
        color = GREEN if failed == 0 else YELLOW
        self.after(0, lambda: self.ipv6_status_label.config(text=msg, fg=color))
        self.after(0, lambda: self.ipv6_add_btn.config(state='normal', text="THEM VAO MAY"))

    def _detect_interface(self):
        """Tim ten network interface chinh (Ethernet/Wi-Fi)."""
        import subprocess
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'ipv6', 'show', 'address'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                line = line.strip()
                if line.startswith('Interface') and ':' in line:
                    name = line.split(':', 1)[1].strip()
                    if name.lower() not in ('loopback pseudo-interface 1',):
                        return name
        except Exception:
            pass
        return "Ethernet"

    def _test_ipv6(self):
        """Test IPv6 - kiem tra IPv6 nao da duoc assign va hoat dong."""
        ipv6_list = self._get_ipv6_list()
        if not ipv6_list:
            self.ipv6_status_label.config(text="Chua nhap IPv6!", fg=RED)
            return

        self.ipv6_test_btn.config(state='disabled', text="DANG TEST...")
        self.ipv6_status_label.config(text="", fg=FG2)
        threading.Thread(target=self._do_test_ipv6, args=(ipv6_list,), daemon=True).start()

    def _do_test_ipv6(self, ipv6_list):
        """Thread: kiem tra IPv6."""
        import subprocess
        import socket

        # 1. Lay danh sach IPv6 hien co tren may
        assigned = set()
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'ipv6', 'show', 'address'],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.split('\n'):
                line = line.strip()
                if '2001:' in line or '::' in line:
                    parts = line.split()
                    for p in parts:
                        if ':' in p and not p.endswith('%'):
                            # Loai bo %interface suffix
                            clean = p.split('%')[0]
                            if clean.startswith('2001:') or clean.startswith('fe80:'):
                                assigned.add(clean.lower())
        except Exception:
            pass

        ok_count = 0
        fail_count = 0
        results = []

        for ip in ipv6_list:
            ip_lower = ip.lower()
            if ip_lower in assigned:
                # Da assign → test bind
                try:
                    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                    sock.bind((ip, 0))
                    sock.close()
                    results.append(f"  OK  {ip}")
                    ok_count += 1
                except Exception:
                    results.append(f"  BIND FAIL  {ip}")
                    fail_count += 1
            else:
                results.append(f"  CHUA ADD  {ip}")
                fail_count += 1

        # Hien ket qua trong popup
        msg = f"OK: {ok_count}  Loi: {fail_count} / {len(ipv6_list)}"
        color = GREEN if fail_count == 0 else (YELLOW if ok_count > 0 else RED)
        self.after(0, lambda: self.ipv6_status_label.config(text=msg, fg=color))
        self.after(0, lambda: self.ipv6_test_btn.config(state='normal', text="TEST IPv6"))

        # Show detail popup
        detail = f"IPv6 Test Results ({ok_count}/{len(ipv6_list)} OK)\n\n" + "\n".join(results)
        self.after(0, lambda: self._show_ipv6_result(detail))

    def _show_ipv6_result(self, detail):
        """Hien popup ket qua test IPv6."""
        popup = tk.Toplevel(self)
        popup.title("IPv6 Test Results")
        popup.geometry("500x400")
        popup.configure(bg=BG)
        popup.transient(self)

        text = tk.Text(popup, bg=BG, fg=FG, font=("Consolas", 10),
                       wrap='none', bd=0, padx=10, pady=10)
        text.pack(fill='both', expand=True)

        for line in detail.split('\n'):
            if 'OK' in line and 'FAIL' not in line and 'CHUA' not in line:
                text.insert('end', line + '\n', 'ok')
            elif 'FAIL' in line or 'CHUA' in line:
                text.insert('end', line + '\n', 'fail')
            else:
                text.insert('end', line + '\n')

        text.tag_config('ok', foreground=GREEN)
        text.tag_config('fail', foreground=RED)
        text.config(state='disabled')

        tk.Button(popup, text="DONG", font=("Segoe UI", 11, "bold"),
                  bg=BLUE, fg='#0f172a', relief='flat',
                  command=popup.destroy).pack(pady=10)

    def _get_chrome_count(self):
        val = self.chrome_combo.get()
        if val == "Tat ca":
            return 0
        try:
            return int(val)
        except:
            return 0

    # ============================================================
    # Update
    # ============================================================
    def _run_update(self):
        """Cap nhat code tu GitHub - giong vm_manager_gui.py."""
        import subprocess
        import urllib.request
        import zipfile
        import shutil

        GITHUB_ZIP_URL = "https://github.com/nguyenvantuong161978-dotcom/ve3-tool-simple/archive/refs/heads/main.zip"
        GITHUB_GIT_URL = "https://github.com/nguyenvantuong161978-dotcom/ve3-tool-simple.git"

        def do_update():
            self.update_btn.config(state="disabled", text="DANG CAP NHAT...", bg='#666')

            try:
                # Kiem tra git co san khong
                git_available = False
                try:
                    result = subprocess.run(
                        ["git", "--version"],
                        capture_output=True, text=True, timeout=10
                    )
                    git_available = (result.returncode == 0)
                except:
                    git_available = False

                if git_available:
                    # === DUNG GIT ===
                    # Kiem tra remote origin
                    result = subprocess.run(
                        ["git", "remote", "get-url", "origin"],
                        cwd=str(TOOL_DIR), capture_output=True, text=True, timeout=10
                    )
                    if result.returncode != 0:
                        subprocess.run(
                            ["git", "remote", "add", "origin", GITHUB_GIT_URL],
                            cwd=str(TOOL_DIR), capture_output=True, timeout=10
                        )
                    elif GITHUB_GIT_URL not in result.stdout.strip():
                        subprocess.run(
                            ["git", "remote", "set-url", "origin", GITHUB_GIT_URL],
                            cwd=str(TOOL_DIR), capture_output=True, timeout=10
                        )

                    # Fetch va reset
                    for cmd in [
                        ["git", "fetch", "origin", "main"],
                        ["git", "checkout", "main"],
                        ["git", "reset", "--hard", "origin/main"]
                    ]:
                        subprocess.run(cmd, cwd=str(TOOL_DIR), capture_output=True, text=True, timeout=120)

                else:
                    # === KHONG CO GIT - TAI ZIP ===
                    import ssl
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                    zip_path = TOOL_DIR / "update_temp.zip"
                    extract_dir = TOOL_DIR / "update_temp"

                    cache_buster = f"?t={int(time.time())}"
                    with urllib.request.urlopen(GITHUB_ZIP_URL + cache_buster, context=ssl_context) as response:
                        with open(str(zip_path), 'wb') as out_file:
                            out_file.write(response.read())

                    with zipfile.ZipFile(str(zip_path), 'r') as zip_ref:
                        zip_ref.extractall(str(extract_dir))

                    extracted_folder = extract_dir / "ve3-tool-simple-main"

                    # Copy files
                    files_to_update = [
                        "vm_manager.py", "vm_manager_gui.py", "run_excel_api.py",
                        "run_worker.py", "START.py", "START.bat", "START_SERVER.bat",
                        "requirements.txt", "_run_chrome1.py", "_run_chrome2.py",
                        "google_login.py", "VERSION.txt",
                    ]
                    for f in files_to_update:
                        src = extracted_folder / f
                        dst = TOOL_DIR / f
                        if src.exists():
                            shutil.copy2(str(src), str(dst))

                    # Copy modules/
                    src_modules = extracted_folder / "modules"
                    dst_modules = TOOL_DIR / "modules"
                    if src_modules.exists():
                        for py_file in src_modules.glob("*.py"):
                            shutil.copy2(str(py_file), str(dst_modules / py_file.name))
                        for sub_dir in src_modules.iterdir():
                            if sub_dir.is_dir():
                                dst_sub = dst_modules / sub_dir.name
                                if dst_sub.exists():
                                    shutil.rmtree(str(dst_sub))
                                shutil.copytree(str(sub_dir), str(dst_sub))

                    # Copy server/
                    src_server = extracted_folder / "server"
                    dst_server = TOOL_DIR / "server"
                    if src_server.exists():
                        dst_server.mkdir(exist_ok=True)
                        for py_file in src_server.glob("*.py"):
                            shutil.copy2(str(py_file), str(dst_server / py_file.name))

                    # Cleanup
                    if zip_path.exists():
                        zip_path.unlink()
                    if extract_dir.exists():
                        shutil.rmtree(str(extract_dir))

                # Restart
                self.update_btn.config(text="XONG - KHOI DONG LAI...", bg='#00ff88')
                self.after(1000, lambda: os.execv(sys.executable, [sys.executable] + sys.argv))

            except Exception as e:
                self.update_btn.config(text="LOI", bg=RED)
                print(f"Update error: {e}")
                from tkinter import messagebox
                messagebox.showerror("Loi cap nhat", f"Loi: {e}\n\nThu tai thu cong:\n{GITHUB_ZIP_URL}")
            finally:
                self.after(3000, lambda: self.update_btn.config(state="normal", text="UPDATE", bg='#0984e3'))

        threading.Thread(target=do_update, daemon=True).start()

    # ============================================================
    # Start Server
    # ============================================================
    def _on_start(self):
        if self._server_started:
            return

        self._server_started = True
        self.start_btn.config(text="DANG KHOI DONG...", bg='#475569', state='disabled')
        self._save_settings()

        use_ipv6 = self.ipv6_var.get()
        chrome_count = self._get_chrome_count()

        # Thu thap IPv6 bo sung tu text box
        extra_ipv6 = self._get_ipv6_list()

        # Parse accounts tu text box
        gui_accounts = self._get_accounts_parsed()

        # Switch to monitor page
        self.after(500, lambda: self._switch_to_monitor(use_ipv6, chrome_count, extra_ipv6, gui_accounts))

    def _switch_to_monitor(self, use_ipv6, chrome_count, extra_ipv6=None, gui_accounts=None):
        self.setup_frame.destroy()
        self._build_monitor_page()

        # Start server in background
        threading.Thread(
            target=self._start_server,
            args=(use_ipv6, chrome_count, extra_ipv6 or [], gui_accounts or []),
            daemon=True,
        ).start()

    def _start_server(self, use_ipv6, chrome_count, extra_ipv6=None, gui_accounts=None):
        """Start Flask + Chrome workers in background."""
        self._add_log("Khoi dong server...", "INFO")

        # Import and configure app
        from server.app import (
            app, server_settings, settings_lock, _do_start_workers,
            server_log, cleanup_old_tasks, server_logs, log_lock
        )

        # Apply settings
        with settings_lock:
            server_settings['use_ipv6'] = use_ipv6
            server_settings['chrome_count'] = chrome_count
            server_settings['extra_ipv6'] = extra_ipv6 or []
            server_settings['gui_accounts'] = gui_accounts or []
            server_settings['mode'] = 'gop'
            server_settings['started'] = True
            # v1.0.545: Proxy Provider config
            server_settings['proxy_config'] = self._get_proxy_config()

        # Redirect server_log to our GUI
        self._server_logs_ref = server_logs
        self._server_log_lock = log_lock

        self._add_log(f"IPv6: {'BAT' if use_ipv6 else 'TAT'}", "INFO")
        self._add_log(f"Chrome: {chrome_count or 'TAT CA'}", "INFO")

        # Start cleanup
        threading.Thread(target=cleanup_old_tasks, daemon=True).start()

        # Start Chrome workers
        threading.Thread(target=_do_start_workers, daemon=True).start()
        self._add_log("Chrome workers dang setup...", "INFO")

        # Start Flask (blocking)
        self._add_log("Flask server: http://0.0.0.0:5000/", "OK")
        try:
            app.run(host='0.0.0.0', port=5000, debug=False, threaded=True, use_reloader=False)
        except Exception as e:
            self._add_log(f"Flask error: {e}", "ERROR")

    # ============================================================
    # Monitor Page
    # ============================================================
    def _build_monitor_page(self):
        self.monitor_frame = tk.Frame(self, bg=BG)
        self.monitor_frame.pack(fill='both', expand=True)

        # Header
        header = tk.Frame(self.monitor_frame, bg=BG2)
        header.pack(fill='x')

        tk.Label(header, text="Chrome Server", font=("Segoe UI", 14, "bold"),
                 bg=BG2, fg=BLUE).pack(side='left', padx=16, pady=10)

        self.header_status = tk.Label(header, text="Starting...", font=("Segoe UI", 10),
                                      bg=BG2, fg=YELLOW)
        self.header_status.pack(side='right', padx=16)

        # Stats row
        stats_frame = tk.Frame(self.monitor_frame, bg=BG)
        stats_frame.pack(fill='x', padx=12, pady=(12, 0))

        self.stat_labels = {}
        stat_defs = [
            ("workers", "Workers Ready", BLUE),
            ("queue", "In Queue", ORANGE),
            ("completed", "Completed", GREEN),
            ("failed", "Failed", RED),
        ]

        for key, label, color in stat_defs:
            box = tk.Frame(stats_frame, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
            box.pack(side='left', fill='x', expand=True, padx=4)
            num = tk.Label(box, text="0", font=("Segoe UI", 22, "bold"), bg=BG2, fg=color)
            num.pack(pady=(8, 0))
            tk.Label(box, text=label.upper(), font=("Segoe UI", 8), bg=BG2, fg=FG2).pack(pady=(0, 8))
            self.stat_labels[key] = num

        # Workers list
        workers_frame = tk.LabelFrame(self.monitor_frame, text=" Chrome Workers ",
                                       font=("Segoe UI", 10, "bold"),
                                       bg=BG2, fg=FG2, bd=1, relief='solid')
        workers_frame.pack(fill='x', padx=12, pady=(12, 0))

        self.workers_container = tk.Frame(workers_frame, bg=BG2)
        self.workers_container.pack(fill='x', padx=8, pady=8)

        self.worker_labels = {}

        # Log area
        log_frame = tk.LabelFrame(self.monitor_frame, text=" Server Logs ",
                                   font=("Segoe UI", 10, "bold"),
                                   bg=BG2, fg=FG2, bd=1, relief='solid')
        log_frame.pack(fill='both', expand=True, padx=12, pady=12)

        self.log_text = tk.Text(log_frame, bg=BG, fg=FG2, font=("Consolas", 9),
                                wrap='none', state='disabled', bd=0,
                                selectbackground='#334155')
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.log_text.pack(fill='both', expand=True, padx=4, pady=4)

        # Color tags
        self.log_text.tag_config('INFO', foreground=FG2)
        self.log_text.tag_config('OK', foreground=GREEN)
        self.log_text.tag_config('WARN', foreground=YELLOW)
        self.log_text.tag_config('ERROR', foreground=RED)

        # Start update loop
        self._last_log_count = 0
        self._update_monitor()

    def _add_log(self, msg, level="INFO"):
        ts = time.strftime("%H:%M:%S")
        self._logs.append({"time": ts, "level": level, "msg": msg})

    def _update_monitor(self):
        """Update monitor every 2s."""
        try:
            self._update_stats()
            self._update_workers_display()
            self._update_logs()
        except Exception:
            pass

        self.after(2000, self._update_monitor)

    def _update_stats(self):
        try:
            from server.app import chrome_pool, task_queue, queue_lock, stats, external_workers, external_workers_lock
            ready = 0
            total = 0
            if chrome_pool:
                ready = chrome_pool.total_ready()
                total = len(chrome_pool.workers)

            # Include external workers
            with external_workers_lock:
                for wid, ew in external_workers.items():
                    total += 1
                    if ew["status"] in ("ready", "busy"):
                        ready += 1

            self.stat_labels['workers'].config(text=f"{ready}/{total}")
            if ready > 0:
                self.header_status.config(text=f"{ready} workers ready", fg=GREEN)
            elif total > 0:
                self.header_status.config(text="Setting up...", fg=YELLOW)

            with queue_lock:
                self.stat_labels['queue'].config(text=str(len(task_queue)))

            self.stat_labels['completed'].config(text=str(stats['total_completed']))
            self.stat_labels['failed'].config(text=str(stats['total_failed']))
        except:
            pass

    def _update_workers_display(self):
        try:
            from server.app import chrome_pool, external_workers, external_workers_lock

            # Internal workers (from chrome_pool)
            if chrome_pool:
                workers = chrome_pool.workers
                for w in workers:
                    wid = f"w{w.index}"
                    if wid not in self.worker_labels:
                        frame = tk.Frame(self.workers_container, bg=BG, highlightbackground=BORDER,
                                         highlightthickness=1, padx=8, pady=4)
                        frame.pack(side='left', padx=4, fill='y')

                        name_lbl = tk.Label(frame, text=f"Chrome-{w.index}", font=("Segoe UI", 10, "bold"),
                                            bg=BG, fg=FG)
                        name_lbl.pack(anchor='w')

                        status_lbl = tk.Label(frame, text="SETUP", font=("Segoe UI", 9),
                                              bg=BG, fg=YELLOW)
                        status_lbl.pack(anchor='w')

                        info_lbl = tk.Label(frame, text="", font=("Segoe UI", 8),
                                            bg=BG, fg=FG2)
                        info_lbl.pack(anchor='w')

                        self.worker_labels[wid] = {
                            'frame': frame,
                            'status': status_lbl,
                            'info': info_lbl,
                        }

                    labels = self.worker_labels[wid]
                    if w.busy:
                        labels['status'].config(text="BUSY", fg=ORANGE)
                        labels['frame'].config(highlightbackground=ORANGE)
                    elif w.ready:
                        labels['status'].config(text="READY", fg=GREEN)
                        labels['frame'].config(highlightbackground=GREEN)
                    else:
                        labels['status'].config(text="SETUP", fg=YELLOW)
                        labels['frame'].config(highlightbackground=YELLOW)

                    acc = w.account['id'].split('@')[0] if w.account else ""
                    labels['info'].config(text=f"{acc}\nDone:{w.total_completed} Fail:{w.total_failed}")

            # External workers (separate processes)
            with external_workers_lock:
                for ewid, ew in external_workers.items():
                    wid = f"ext{ew['index']}"
                    if wid not in self.worker_labels:
                        frame = tk.Frame(self.workers_container, bg=BG, highlightbackground=BORDER,
                                         highlightthickness=1, padx=8, pady=4)
                        frame.pack(side='left', padx=4, fill='y')

                        name_lbl = tk.Label(frame, text=f"Ext-{ew['index']}", font=("Segoe UI", 10, "bold"),
                                            bg=BG, fg=FG)
                        name_lbl.pack(anchor='w')

                        status_lbl = tk.Label(frame, text="EXT", font=("Segoe UI", 9),
                                              bg=BG, fg=YELLOW)
                        status_lbl.pack(anchor='w')

                        info_lbl = tk.Label(frame, text="", font=("Segoe UI", 8),
                                            bg=BG, fg=FG2)
                        info_lbl.pack(anchor='w')

                        self.worker_labels[wid] = {
                            'frame': frame,
                            'status': status_lbl,
                            'info': info_lbl,
                        }

                    labels = self.worker_labels[wid]
                    status = ew.get("status", "starting")
                    if status == "busy":
                        labels['status'].config(text="BUSY", fg=ORANGE)
                        labels['frame'].config(highlightbackground=ORANGE)
                    elif status == "ready":
                        labels['status'].config(text="READY", fg=GREEN)
                        labels['frame'].config(highlightbackground=GREEN)
                    elif status == "failed":
                        labels['status'].config(text="FAIL", fg=RED)
                        labels['frame'].config(highlightbackground=RED)
                    else:
                        labels['status'].config(text="SETUP", fg=YELLOW)
                        labels['frame'].config(highlightbackground=YELLOW)

                    acc = str(ew.get('account', '')).split('@')[0] if ew.get('account') else ""
                    labels['info'].config(text=f"{acc}\nDone:{ew.get('total_completed',0)} Fail:{ew.get('total_failed',0)}")

        except:
            pass

    def _update_logs(self):
        """Pull logs from server_logs."""
        try:
            from server.app import server_logs, log_lock
            with log_lock:
                new_logs = list(server_logs[self._last_log_count:])
                self._last_log_count = len(server_logs)

            if new_logs:
                self.log_text.config(state='normal')
                for log in new_logs:
                    level = log.get('level', 'INFO')
                    line = f"[{log['time']}] {log['msg']}\n"
                    self.log_text.insert('end', line, level)
                self.log_text.see('end')
                self.log_text.config(state='disabled')
        except:
            pass


def main():
    gui = ServerGUI()
    gui.mainloop()


if __name__ == '__main__':
    main()
