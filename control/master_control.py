#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - Master Control Panel v3

v1.0.373: Compact 2-row cards, per-VM log inline, daily stats, stale warning.
"""

import os
import sys
import json
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from datetime import datetime, date
import yaml


# ============================================================================
# CONFIG
# ============================================================================

POSSIBLE_AUTO_PATHS = [
    Path(r"D:\AUTO"),
    Path(r"C:\AUTO"),
    Path(r"Z:\AUTO"),
    Path(r"Y:\AUTO"),
]

AUTO_PATH = None
for p in POSSIBLE_AUTO_PATHS:
    try:
        if p.exists():
            AUTO_PATH = p
            break
    except Exception:
        continue

if not AUTO_PATH:
    print("ERROR: Cannot find AUTO path!")
    sys.exit(1)

VE3_DIR = AUTO_PATH / "ve3-tool-simple"
CONTROL_DIR = VE3_DIR / "control"
COMMANDS_DIR = CONTROL_DIR / "commands"
STATUS_DIR = CONTROL_DIR / "status"
SETTINGS_DIR = CONTROL_DIR / "settings"  # v1.0.592: Master settings cho VM
MASTER_PROJECTS = VE3_DIR / "PROJECTS"
VISUAL_DIR = AUTO_PATH / "visual"

for d in [CONTROL_DIR, COMMANDS_DIR, STATUS_DIR, SETTINGS_DIR, MASTER_PROJECTS, VISUAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

REFRESH_MS = 8000
CLAIM_TIMEOUT_HOURS = 8
STALE_MINUTES = 30


# ============================================================================
# COLORS
# ============================================================================

BG = "#0d0d14"
BG2 = "#151520"
BG_CARD = "#1a1a2e"
FG = "#e0e0e0"
FG_DIM = "#5a5f75"
FG_MUTED = "#8890a0"
GREEN = "#4ade80"
RED = "#f87171"
BLUE = "#60a5fa"
YELLOW = "#fbbf24"
ORANGE = "#fb923c"
PURPLE = "#a78bfa"
CYAN = "#22d3ee"
BORDER = "#2a2a4e"
BORDER_RUN = "#2d5a3d"
BORDER_WARN = "#5a3a1d"


# ============================================================================
# HELPERS
# ============================================================================

def _is_claim_expired(claimed_file: Path) -> bool:
    """v1.0.429: Luôn trả về False - không tự động xóa claim."""
    return False


def _read_claim_vm_id(claimed_file: Path):
    try:
        return claimed_file.read_text(encoding='utf-8').strip().split('\n')[0].strip() or None
    except Exception:
        return None


def _is_in_visual(code: str) -> bool:
    try:
        d = VISUAL_DIR / code
        return d.exists() and any(d.iterdir())
    except Exception:
        return False


def get_queue_status() -> dict:
    status = {"total": 0, "available": 0, "claimed": {}, "expired": 0, "visual": 0}
    if not MASTER_PROJECTS.exists():
        return status
    try:
        for item in MASTER_PROJECTS.iterdir():
            if not item.is_dir() or not list(item.glob("*.srt")):
                continue
            if _is_in_visual(item.name):
                status["visual"] += 1
                continue
            status["total"] += 1
            cf = item / "_CLAIMED"
            if not cf.exists():
                status["available"] += 1
            elif _is_claim_expired(cf):
                status["expired"] += 1
            else:
                vm_id = _read_claim_vm_id(cf)
                if vm_id:
                    status["claimed"].setdefault(vm_id, []).append(item.name)
    except Exception:
        pass
    return status


def count_visual_today() -> int:
    count = 0
    today = date.today()
    try:
        if VISUAL_DIR.exists():
            for item in VISUAL_DIR.iterdir():
                if item.is_dir():
                    try:
                        if datetime.fromtimestamp(item.stat().st_mtime).date() == today:
                            count += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return count


def _time_ago(ts_str: str) -> str:
    if not ts_str:
        return ""
    try:
        diff = (datetime.now() - datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")).total_seconds()
        if diff < 60:
            return f"{int(diff)}s"
        elif diff < 3600:
            return f"{int(diff / 60)}p"
        else:
            return f"{int(diff / 3600)}h{int((diff % 3600) / 60):02d}"
    except Exception:
        return ""


def _bar(pct: float, w: int = 10) -> str:
    f = int(pct * w)
    return "\u2588" * f + "\u2591" * (w - f)


# ============================================================================
# GUI
# ============================================================================

class MasterControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Master Control")
        self.root.configure(bg=BG)
        # Full screen width, tall
        self.root.geometry("1200x900")
        self.root.minsize(900, 500)

        self.vm_widgets = {}
        self.vm_logs = {}
        self._stop = threading.Event()

        self._build()
        self._refresh()

    def _build(self):
        # === HEADER (1 row) ===
        hdr = tk.Frame(self.root, bg=BG2, pady=4)
        hdr.pack(fill=tk.X)

        tk.Label(hdr, text="MASTER CONTROL", font=("Segoe UI", 12, "bold"),
                 bg=BG2, fg=PURPLE).pack(side=tk.LEFT, padx=10)

        self.summary_lbl = tk.Label(hdr, text="", font=("Consolas", 9),
                                     bg=BG2, fg=FG_MUTED)
        self.summary_lbl.pack(side=tk.LEFT, padx=8)

        self.daily_lbl = tk.Label(hdr, text="", font=("Consolas", 10, "bold"),
                                    bg=BG2, fg=GREEN)
        self.daily_lbl.pack(side=tk.LEFT, padx=8)

        # ALL buttons (right)
        bf = tk.Frame(hdr, bg=BG2)
        bf.pack(side=tk.RIGHT, padx=10)
        for txt, clr, cmd in [("RUN ALL", GREEN, "run"),
                               ("STOP ALL", RED, "stop"),
                               ("UPD ALL", BLUE, "update")]:
            tk.Button(bf, text=txt, bg=clr, fg=BG, font=("Segoe UI", 9, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=10, pady=2,
                      command=lambda c=cmd: self._cmd_all(c)).pack(side=tk.LEFT, padx=2)

        # SETTINGS button
        tk.Button(bf, text="SETTINGS", bg=PURPLE, fg="white",
                  font=("Segoe UI", 9, "bold"), activebackground=PURPLE,
                  relief=tk.FLAT, padx=10, pady=2,
                  command=self._open_settings).pack(side=tk.LEFT, padx=2)

        # === QUEUE BAR ===
        self.queue_lbl = tk.Label(self.root, text="", font=("Consolas", 9),
                                   bg=BG, fg=FG_DIM, anchor=tk.W, pady=2)
        self.queue_lbl.pack(fill=tk.X, padx=12)

        # === VM LIST (no scroll needed with compact cards) ===
        self.vm_frame = tk.Frame(self.root, bg=BG)
        self.vm_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)

    # ------------------------------------------------------------------ Log
    def _add_vm_log(self, vm_id: str, msg: str, tag: str = "info"):
        if vm_id not in self.vm_logs:
            self.vm_logs[vm_id] = []
        ts = datetime.now().strftime("%H:%M")
        self.vm_logs[vm_id].append((ts, msg, tag))
        if len(self.vm_logs[vm_id]) > 5:
            self.vm_logs[vm_id] = self.vm_logs[vm_id][-5:]
        self._render_vm_log(vm_id)

    def _render_vm_log(self, vm_id: str):
        w = self.vm_widgets.get(vm_id)
        if not w or "log" not in w:
            return
        lines = self.vm_logs.get(vm_id, [])
        if not lines:
            w["log"].config(text="")
            return
        parts = [f"{ts} {msg}" for ts, msg, _ in lines[-2:]]
        w["log"].config(text="  |  ".join(parts))

    # ------------------------------------------------------------------ Refresh
    def _refresh(self):
        if self._stop.is_set():
            return
        try:
            self._update_all()
        except Exception as e:
            print(f"Refresh error: {e}")
        self.root.after(REFRESH_MS, self._refresh)

    def _update_all(self):
        # Queue
        qs = get_queue_status()
        claimed_n = sum(len(v) for v in qs["claimed"].values())
        vm_n = len(qs["claimed"])
        self.queue_lbl.config(
            text=f"Cho: {qs['available']}  |  Dang lam: {claimed_n} ({vm_n} VM)"
                 f"  |  Het han: {qs['expired']}  |  Xong: {qs['visual']}")

        today_n = count_visual_today()
        self.daily_lbl.config(text=f"Hom nay: {today_n} ma")

        # VMs
        vm_data = {}
        try:
            for f in STATUS_DIR.glob("*.json"):
                try:
                    vm_data[f.stem] = json.loads(f.read_text(encoding='utf-8'))
                except Exception:
                    continue
        except Exception:
            pass

        # From _CLAIMED
        try:
            for vm_id, codes in qs.get("claimed", {}).items():
                if vm_id not in vm_data:
                    vm_data[vm_id] = {"channel": vm_id, "state": "claimed",
                                      "project": ", ".join(codes)}
        except Exception:
            pass

        for vm_id in sorted(vm_data.keys()):
            if vm_id not in self.vm_widgets:
                self._create_card(vm_id)
            self._update_card(vm_id, vm_data[vm_id])

        for vm_id in list(self.vm_widgets.keys()):
            if vm_id not in vm_data:
                self.vm_widgets[vm_id]["frame"].destroy()
                del self.vm_widgets[vm_id]

        # Summary
        total = len(self.vm_widgets)
        running = sum(1 for w in self.vm_widgets.values() if "running" in w.get("_state", ""))
        self.summary_lbl.config(text=f"{running}/{total} VM  |  {AUTO_PATH}")

    # ------------------------------------------------------------------ Card
    def _create_card(self, vm_id: str):
        """2-row compact card."""
        card = tk.Frame(self.vm_frame, bg=BG_CARD, bd=0,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.X, pady=2)

        # === ROW 1: dot | name | state | project(time) | progress | buttons ===
        r1 = tk.Frame(card, bg=BG_CARD)
        r1.pack(fill=tk.X, padx=6, pady=(4, 0))

        dot = tk.Canvas(r1, width=8, height=8, bg=BG_CARD, highlightthickness=0)
        dot.pack(side=tk.LEFT, padx=(0, 4))
        dot_id = dot.create_oval(0, 0, 8, 8, fill=FG_DIM, outline="")

        name_lbl = tk.Label(r1, text=vm_id, font=("Consolas", 10, "bold"),
                            bg=BG_CARD, fg=FG, width=8, anchor=tk.W)
        name_lbl.pack(side=tk.LEFT)

        state_lbl = tk.Label(r1, text="--", font=("Consolas", 9),
                             bg=BG_CARD, fg=FG_DIM, width=16, anchor=tk.W)
        state_lbl.pack(side=tk.LEFT, padx=(4, 0))

        proj_lbl = tk.Label(r1, text="", font=("Consolas", 9, "bold"),
                            bg=BG_CARD, fg=YELLOW, width=18, anchor=tk.W)
        proj_lbl.pack(side=tk.LEFT, padx=(4, 0))

        progress_lbl = tk.Label(r1, text="", font=("Consolas", 9),
                                bg=BG_CARD, fg=CYAN, anchor=tk.W)
        progress_lbl.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)

        # Buttons (right)
        for txt, clr, cmd in [("RUN", GREEN, "run"), ("STOP", RED, "stop"),
                               ("DONE", ORANGE, "done"), ("UPD", BLUE, "update")]:
            tk.Button(r1, text=txt, bg=clr, fg=BG, font=("Segoe UI", 7, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=6, pady=0,
                      command=lambda v=vm_id, c=cmd: self._cmd(v, c)
                      ).pack(side=tk.LEFT, padx=1)

        ver_lbl = tk.Label(r1, text="", font=("Consolas", 8), bg=BG_CARD, fg=FG_DIM)
        ver_lbl.pack(side=tk.LEFT, padx=(4, 2))

        # === ROW 2: stats | last image | warn | log ===
        r2 = tk.Frame(card, bg=BG_CARD)
        r2.pack(fill=tk.X, padx=6, pady=(0, 3))

        stats_lbl = tk.Label(r2, text="", font=("Consolas", 8),
                             bg=BG_CARD, fg=FG_MUTED, anchor=tk.W)
        stats_lbl.pack(side=tk.LEFT, padx=(12, 0))

        warn_lbl = tk.Label(r2, text="", font=("Consolas", 8, "bold"),
                            bg=BG_CARD, fg=RED, anchor=tk.W)
        warn_lbl.pack(side=tk.LEFT, padx=(8, 0))

        log_lbl = tk.Label(r2, text="", font=("Consolas", 8),
                           bg=BG_CARD, fg=FG_DIM, anchor=tk.E)
        log_lbl.pack(side=tk.RIGHT, padx=(0, 4))

        self.vm_widgets[vm_id] = {
            "frame": card, "dot": dot, "dot_id": dot_id,
            "state": state_lbl, "project": proj_lbl,
            "progress": progress_lbl, "stats": stats_lbl,
            "warn": warn_lbl, "version": ver_lbl, "log": log_lbl,
            "_state": "",
        }

    def _update_card(self, vm_id: str, data: dict):
        w = self.vm_widgets.get(vm_id)
        if not w:
            return

        state = data.get("state", "unknown")
        project = data.get("project", "")
        version = data.get("version", "")
        uptime = data.get("uptime_minutes", 0)
        proj_elapsed = data.get("project_elapsed_minutes", 0)
        img_done = data.get("images_done", 0)
        total = data.get("total_scenes", 0)
        excel_step = data.get("excel_step", "")
        completed = data.get("completed_today", 0)
        last_img = data.get("last_image_time", "")

        # State
        st = state
        if uptime:
            st += f" {uptime // 60}h{uptime % 60:02d}"
        w["state"].config(text=st)
        w["_state"] = state

        # Colors
        if "running" in state.lower():
            w["state"].config(fg=GREEN)
            w["dot"].itemconfig(w["dot_id"], fill=GREEN)
            w["frame"].config(highlightbackground=BORDER_RUN)
        elif state in ("stopped", "killed"):
            w["state"].config(fg=RED)
            w["dot"].itemconfig(w["dot_id"], fill=RED)
            w["frame"].config(highlightbackground=BORDER)
        elif state in ("idle", "claimed"):
            w["state"].config(fg=ORANGE)
            w["dot"].itemconfig(w["dot_id"], fill=ORANGE)
            w["frame"].config(highlightbackground=BORDER)
        else:
            w["state"].config(fg=FG_MUTED)
            w["dot"].itemconfig(w["dot_id"], fill=FG_DIM)
            w["frame"].config(highlightbackground=BORDER)

        # Project
        pt = ""
        if project:
            pt = project
            if proj_elapsed:
                pt += f" ({proj_elapsed // 60}h{proj_elapsed % 60:02d})"
        w["project"].config(text=pt)

        # Progress
        pp = []
        if total > 0:
            pct = img_done / total
            pp.append(f"{_bar(pct)} {img_done}/{total} ({int(pct * 100)}%)")
        if excel_step and excel_step != "done":
            pp.append(f"Excel:{excel_step}")
        elif excel_step == "done" and total > 0:
            pass  # Don't show "done" when progress bar already visible
        elif excel_step == "done":
            pp.append("Excel: done")
        w["progress"].config(text="  ".join(pp))

        # Stats row
        sp = []
        if completed > 0:
            sp.append(f"Hom nay:{completed} ma")
        ago = _time_ago(last_img)
        if ago:
            sp.append(f"Anh:{ago}")
        w["stats"].config(text="  ".join(sp))

        # Stale warning
        is_stale = False
        if "running" in state.lower() and last_img:
            try:
                mins = (datetime.now() - datetime.strptime(last_img, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
                if mins > STALE_MINUTES:
                    is_stale = True
                    w["warn"].config(text=f"!! CHAM {int(mins)}p")
                    w["frame"].config(highlightbackground=BORDER_WARN)
            except Exception:
                pass
        if not is_stale:
            w["warn"].config(text="")

        # Version
        w["version"].config(text=f"v{version}" if version else "")

        self._render_vm_log(vm_id)

    # ------------------------------------------------------------------ Commands
    def _cmd(self, vm_id: str, cmd: str):
        max_retries = 5

        def _send(attempt: int):
            cmd_file = COMMANDS_DIR / f"{vm_id}.{cmd}"
            ack_file = COMMANDS_DIR / f"{vm_id}.{cmd}.ack"
            try:
                if ack_file.exists():
                    ack_file.unlink()
                cmd_file.write_text(json.dumps({
                    "command": cmd, "timestamp": datetime.now().isoformat()
                }), encoding='utf-8')
                msg = f"Gui {cmd.upper()}" if attempt == 1 else f"Retry {cmd.upper()} ({attempt}/{max_retries})"
                self.root.after(0, lambda: self._add_vm_log(vm_id, msg))
            except Exception as e:
                self.root.after(0, lambda: self._add_vm_log(vm_id, f"LOI: {e}"))
                return

            max_wait = 120 if cmd == "update" else 30
            for _ in range(max_wait):
                time.sleep(1)
                if ack_file.exists():
                    try:
                        result = json.loads(ack_file.read_text(encoding='utf-8')).get('result', '?')
                        self.root.after(0, lambda r=result: self._add_vm_log(
                            vm_id, f"{cmd.upper()}->{r}"))
                        ack_file.unlink()
                        return
                    except Exception:
                        pass

            if attempt < max_retries:
                self.root.after(0, lambda: self._add_vm_log(vm_id, f"{cmd.upper()} TIMEOUT->retry"))
                time.sleep(2)
                _send(attempt + 1)
            else:
                self.root.after(0, lambda: self._add_vm_log(vm_id, f"{cmd.upper()} FAIL({max_retries}x)"))

        threading.Thread(target=lambda: _send(1), daemon=True).start()

    def _cmd_all(self, cmd: str):
        for vm_id in list(self.vm_widgets.keys()):
            self._cmd(vm_id, cmd)

    def _open_settings(self):
        """Mo Settings Dialog."""
        vm_list = sorted(self.vm_widgets.keys())
        SettingsDialog(self.root, AUTO_PATH, vm_list)

    def on_close(self):
        self._stop.set()
        self.root.destroy()


# ============================================================================
# SETTINGS DIALOG
# ============================================================================

# Settings co the sync tu master → VM
SETTINGS_DEFS = [
    # (key, label, type, options/default)
    ("generation_mode", "Generation Mode", "combo", ["api", "browser", "chrome", "server", "api+server"]),
    ("chrome_model_index", "Chrome Model", "combo", ["0 - Nano Banana Pro", "1 - Nano Banana 2", "2 - Imagen 4"]),
    ("topic", "Topic", "combo", ["story", "psychology", "finance_history"]),
    ("excel_mode", "Excel Mode", "combo", ["full", "basic"]),
    ("video_mode", "Video Mode", "combo", ["full", "basic"]),
    ("browser_headless", "Headless", "combo", ["false", "true"]),
    ("distributed_mode", "Distributed Mode", "combo", ["false", "true"]),
    ("local_server_enabled", "Local Server", "combo", ["false", "true"]),
    ("local_server_url", "Server URL", "entry", ""),
    ("flow_aspect_ratio", "Aspect Ratio", "combo", ["landscape", "portrait", "square"]),
    ("retry_count", "Retry Count", "entry", "3"),
    ("browser_generate_timeout", "Generate Timeout (s)", "entry", "120"),
    ("max_scenes_per_account", "Max Scenes/Account", "entry", "50"),
    ("parallel_chrome", "Parallel Chrome", "entry", "1/2"),
    ("use_proxy", "Use Proxy", "combo", ["true", "false"]),
]

class SettingsDialog:
    """Dialog de master set settings cho VM."""

    def __init__(self, parent, auto_path: Path, vm_list: list):
        self.win = tk.Toplevel(parent)
        self.win.title("VM Settings Control")
        self.win.configure(bg=BG)
        self.win.geometry("700x650")
        self.win.transient(parent)

        self.auto_path = auto_path
        self.vm_list = vm_list
        self.settings_dir = SETTINGS_DIR  # control/settings/
        self.settings_dir.mkdir(parents=True, exist_ok=True)

        self.vars = {}  # key → StringVar
        self.checks = {}  # key → BooleanVar (enable checkbox)

        self._build()
        self._load_current()

    def _build(self):
        # === TARGET SELECTOR ===
        top = tk.Frame(self.win, bg=BG2, pady=6)
        top.pack(fill=tk.X)

        tk.Label(top, text="Ap dung cho:", font=("Segoe UI", 10, "bold"),
                 bg=BG2, fg=FG).pack(side=tk.LEFT, padx=10)

        self.target_var = tk.StringVar(value="_global (TAT CA VM)")
        targets = ["_global (TAT CA VM)"] + self.vm_list
        self.target_combo = ttk.Combobox(top, textvariable=self.target_var,
                                          values=targets, width=25, state="readonly")
        self.target_combo.pack(side=tk.LEFT, padx=4)
        self.target_combo.bind("<<ComboboxSelected>>", lambda e: self._load_current())

        # Buttons
        tk.Button(top, text="LUU & AP DUNG", bg=GREEN, fg=BG,
                  font=("Segoe UI", 10, "bold"), relief=tk.FLAT, padx=15,
                  command=self._save).pack(side=tk.RIGHT, padx=10)

        tk.Button(top, text="XOA", bg=RED, fg="white",
                  font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=10,
                  command=self._delete).pack(side=tk.RIGHT, padx=2)

        # === INFO ===
        info = tk.Label(self.win,
                        text="Tick checkbox = master kiem soat key do. Bo tick = VM giu nguyen local.",
                        font=("Consolas", 8), bg=BG, fg=FG_DIM, anchor=tk.W)
        info.pack(fill=tk.X, padx=12, pady=2)

        # === SETTINGS LIST (scrollable) ===
        canvas = tk.Canvas(self.win, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self.win, orient=tk.VERTICAL, command=canvas.yview)
        self.settings_frame = tk.Frame(canvas, bg=BG)

        self.settings_frame.bind("<Configure>",
                                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.settings_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel scroll
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Build setting rows
        for i, (key, label, stype, options) in enumerate(SETTINGS_DEFS):
            row = tk.Frame(self.settings_frame, bg=BG_CARD if i % 2 == 0 else BG)
            row.pack(fill=tk.X, pady=1)

            # Checkbox (enable/disable)
            chk_var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(row, variable=chk_var, bg=row.cget("bg"),
                                  activebackground=row.cget("bg"), selectcolor=BG)
            chk.pack(side=tk.LEFT, padx=(8, 2))
            self.checks[key] = chk_var

            # Label
            tk.Label(row, text=label, font=("Consolas", 9), width=22, anchor=tk.W,
                     bg=row.cget("bg"), fg=FG).pack(side=tk.LEFT)

            # Input
            var = tk.StringVar()
            if stype == "combo":
                combo = ttk.Combobox(row, textvariable=var, values=options,
                                      width=30, state="readonly")
                combo.pack(side=tk.LEFT, padx=4)
            else:  # entry
                entry = tk.Entry(row, textvariable=var, width=32,
                                 bg=BG2, fg=FG, insertbackground=FG,
                                 font=("Consolas", 9))
                entry.pack(side=tk.LEFT, padx=4)

            self.vars[key] = var

        # === STATUS BAR ===
        self.status_lbl = tk.Label(self.win, text="", font=("Consolas", 9),
                                    bg=BG, fg=GREEN, anchor=tk.W)
        self.status_lbl.pack(fill=tk.X, padx=12, pady=4)

    def _get_target_id(self) -> str:
        """Lay target VM ID tu combobox."""
        val = self.target_var.get()
        if val.startswith("_global"):
            return "_global"
        return val

    def _load_current(self):
        """Load settings hien tai tu file master."""
        target = self._get_target_id()
        if target == "_global":
            fpath = self.settings_dir / "_global.yaml"
        else:
            fpath = self.settings_dir / f"{target}.yaml"

        # Reset all
        for key in self.vars:
            self.vars[key].set("")
            self.checks[key].set(False)

        if fpath.exists():
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}

                for key, var in self.vars.items():
                    if key in cfg:
                        val = cfg[key]
                        # chrome_model_index: hien thi dang "0 - Nano..."
                        if key == "chrome_model_index":
                            for opt in SETTINGS_DEFS:
                                if opt[0] == key:
                                    for o in opt[3]:
                                        if o.startswith(str(val)):
                                            val = o
                                            break
                        # bool → string
                        if isinstance(val, bool):
                            val = "true" if val else "false"
                        var.set(str(val))
                        self.checks[key].set(True)

                self.status_lbl.config(
                    text=f"Da load {len(cfg)} settings tu {fpath.name}", fg=BLUE)
            except Exception as e:
                self.status_lbl.config(text=f"Loi load: {e}", fg=RED)
        else:
            self.status_lbl.config(text=f"Chua co file {fpath.name} - tao moi", fg=FG_DIM)

    def _save(self):
        """Luu settings ra file master."""
        target = self._get_target_id()
        if target == "_global":
            fpath = self.settings_dir / "_global.yaml"
            label = "GLOBAL (tat ca VM)"
        else:
            fpath = self.settings_dir / f"{target}.yaml"
            label = f"VM {target}"

        # Thu thap cac key da tick
        settings = {}
        for key, chk_var in self.checks.items():
            if chk_var.get():
                val = self.vars[key].get()
                if not val:
                    continue

                # Parse types
                if key == "chrome_model_index":
                    # "0 - Nano Banana Pro" → 0
                    try:
                        val = int(val.split(" ")[0])
                    except Exception:
                        val = 0
                elif val == "true":
                    val = True
                elif val == "false":
                    val = False
                elif val.isdigit():
                    val = int(val)

                settings[key] = val

        if not settings:
            self.status_lbl.config(text="Khong co setting nao duoc tick!", fg=RED)
            return

        try:
            with open(fpath, 'w', encoding='utf-8') as f:
                yaml.dump(settings, f, default_flow_style=False, allow_unicode=True)

            self.status_lbl.config(
                text=f"Da luu {len(settings)} settings cho {label}. VM se tu dong cap nhat.",
                fg=GREEN)
        except Exception as e:
            self.status_lbl.config(text=f"Loi luu: {e}", fg=RED)

    def _delete(self):
        """Xoa file settings."""
        target = self._get_target_id()
        if target == "_global":
            fpath = self.settings_dir / "_global.yaml"
        else:
            fpath = self.settings_dir / f"{target}.yaml"

        if fpath.exists():
            fpath.unlink()
            self._load_current()
            self.status_lbl.config(text=f"Da xoa {fpath.name}", fg=ORANGE)
        else:
            self.status_lbl.config(text=f"File {fpath.name} khong ton tai", fg=FG_DIM)


def main():
    root = tk.Tk()
    app = MasterControlGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
