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
        self.geometry("700x650")
        self.configure(bg=BG)
        self.resizable(True, True)

        self._server_started = False
        self._logs = []
        self._workers_info = []

        self._build_setup_page()

    # ============================================================
    # Setup Page
    # ============================================================
    def _build_setup_page(self):
        self.setup_frame = tk.Frame(self, bg=BG)
        self.setup_frame.pack(fill='both', expand=True)

        # Title
        tk.Label(self.setup_frame, text="Chrome Server", font=("Segoe UI", 22, "bold"),
                 bg=BG, fg=BLUE).pack(pady=(40, 5))
        tk.Label(self.setup_frame, text="Cai dat va khoi dong server", font=("Segoe UI", 11),
                 bg=BG, fg=FG2).pack(pady=(0, 30))

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

        self.ipv6_text = tk.Text(ipv6_text_frame, height=4, width=50,
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
        tk.Frame(card, bg=BORDER, height=1).pack(fill='x', padx=20, pady=15)

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
                 font=("Segoe UI", 9), bg=BG2, fg=FG2).pack(padx=20, anchor='w', pady=(0, 20))

        # START button
        self.start_btn = tk.Button(self.setup_frame, text="START SERVER",
                                   font=("Segoe UI", 16, "bold"),
                                   bg=GREEN, fg='#0f172a', activebackground='#16a34a',
                                   relief='flat', cursor='hand2', height=2,
                                   command=self._on_start)
        self.start_btn.pack(fill='x', padx=80, pady=30)

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
    # Start Server
    # ============================================================
    def _on_start(self):
        if self._server_started:
            return

        self._server_started = True
        self.start_btn.config(text="DANG KHOI DONG...", bg='#475569', state='disabled')

        use_ipv6 = self.ipv6_var.get()
        chrome_count = self._get_chrome_count()

        # Thu thap IPv6 bo sung tu text box
        extra_ipv6_text = self.ipv6_text.get("1.0", "end").strip()
        extra_ipv6 = [
            line.strip() for line in extra_ipv6_text.split('\n')
            if line.strip() and ':' in line.strip()  # IPv6 phai co dau ':'
        ]

        # Switch to monitor page
        self.after(500, lambda: self._switch_to_monitor(use_ipv6, chrome_count, extra_ipv6))

    def _switch_to_monitor(self, use_ipv6, chrome_count, extra_ipv6=None):
        self.setup_frame.destroy()
        self._build_monitor_page()

        # Start server in background
        threading.Thread(
            target=self._start_server,
            args=(use_ipv6, chrome_count, extra_ipv6 or []),
            daemon=True,
        ).start()

    def _start_server(self, use_ipv6, chrome_count, extra_ipv6=None):
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
            server_settings['mode'] = 'gop'
            server_settings['started'] = True

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
