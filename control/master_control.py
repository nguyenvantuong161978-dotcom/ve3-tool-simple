#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - Master Control Panel v3

v1.0.372: Redesign - compact cards, per-VM log, daily stats, stale warning.

Chay:
    python master_control.py
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
MASTER_PROJECTS = VE3_DIR / "PROJECTS"
VISUAL_DIR = AUTO_PATH / "visual"

for d in [CONTROL_DIR, COMMANDS_DIR, STATUS_DIR, MASTER_PROJECTS, VISUAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

REFRESH_MS = 8000
CLAIM_TIMEOUT_HOURS = 8
STALE_MINUTES = 30  # Canh bao neu khong co anh moi sau X phut


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
# QUEUE HELPERS
# ============================================================================

def _is_claim_expired(claimed_file: Path) -> bool:
    try:
        content = claimed_file.read_text(encoding='utf-8').strip()
        lines = content.split('\n')
        if len(lines) < 2:
            return True
        claim_time = datetime.strptime(lines[1].strip(), "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - claim_time).total_seconds() / 3600 > CLAIM_TIMEOUT_HOURS
    except Exception:
        return True


def _read_claim_vm_id(claimed_file: Path):
    try:
        content = claimed_file.read_text(encoding='utf-8').strip()
        return content.split('\n')[0].strip() or None
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
            if not item.is_dir():
                continue
            if not list(item.glob("*.srt")):
                continue
            if _is_in_visual(item.name):
                status["visual"] += 1
                continue
            status["total"] += 1
            claimed_file = item / "_CLAIMED"
            if not claimed_file.exists():
                status["available"] += 1
            elif _is_claim_expired(claimed_file):
                status["expired"] += 1
            else:
                vm_id = _read_claim_vm_id(claimed_file)
                if vm_id:
                    status["claimed"].setdefault(vm_id, []).append(item.name)
    except Exception:
        pass
    return status


def count_visual_today() -> int:
    """Dem so folder trong visual/ duoc tao/sua hom nay."""
    count = 0
    today = date.today()
    try:
        if VISUAL_DIR.exists():
            for item in VISUAL_DIR.iterdir():
                if item.is_dir():
                    try:
                        mtime = datetime.fromtimestamp(item.stat().st_mtime).date()
                        if mtime == today:
                            count += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return count


def _time_ago(ts_str: str) -> str:
    """Chuyen timestamp thanh 'X phut truoc' / 'X gio truoc'."""
    if not ts_str:
        return "--"
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        diff = (datetime.now() - ts).total_seconds()
        if diff < 60:
            return f"{int(diff)}s"
        elif diff < 3600:
            return f"{int(diff / 60)}p"
        else:
            h = int(diff / 3600)
            m = int((diff % 3600) / 60)
            return f"{h}h{m:02d}"
    except Exception:
        return "--"


def _progress_bar(pct: float, width: int = 15) -> str:
    """Tao progress bar bang ky tu: ████░░░░"""
    filled = int(pct * width)
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


# ============================================================================
# MASTER CONTROL GUI
# ============================================================================

class MasterControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Master Control")
        self.root.configure(bg=BG)
        self.root.geometry("1100x800")
        self.root.minsize(900, 600)

        self.vm_widgets = {}  # VM_ID -> widget dict
        self.vm_logs = {}  # VM_ID -> list of (timestamp, message, tag)
        self._stop = threading.Event()

        self._build()
        self._refresh()

    # ------------------------------------------------------------------ UI
    def _build(self):
        # === HEADER ===
        hdr = tk.Frame(self.root, bg=BG2, pady=6)
        hdr.pack(fill=tk.X)

        left = tk.Frame(hdr, bg=BG2)
        left.pack(side=tk.LEFT, padx=12)

        tk.Label(left, text="MASTER CONTROL", font=("Segoe UI", 13, "bold"),
                 bg=BG2, fg=PURPLE).pack(side=tk.LEFT)

        self.summary_lbl = tk.Label(left, text="", font=("Segoe UI", 10),
                                     bg=BG2, fg=FG_MUTED)
        self.summary_lbl.pack(side=tk.LEFT, padx=12)

        # ALL buttons
        bf = tk.Frame(hdr, bg=BG2)
        bf.pack(side=tk.RIGHT, padx=12)
        for txt, clr, cmd in [("RUN ALL", GREEN, "run"),
                               ("STOP ALL", RED, "stop"),
                               ("UPD ALL", BLUE, "update")]:
            tk.Button(bf, text=txt, bg=clr, fg=BG, font=("Segoe UI", 9, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=14, pady=3,
                      command=lambda c=cmd: self._cmd_all(c)).pack(side=tk.LEFT, padx=3)

        # === STATS BAR ===
        stats = tk.Frame(self.root, bg=BG, pady=2)
        stats.pack(fill=tk.X)

        self.queue_lbl = tk.Label(stats, text="", font=("Consolas", 10),
                                   bg=BG, fg=FG_DIM, anchor=tk.W)
        self.queue_lbl.pack(side=tk.LEFT, padx=15)

        self.daily_lbl = tk.Label(stats, text="", font=("Consolas", 10),
                                    bg=BG, fg=GREEN, anchor=tk.E)
        self.daily_lbl.pack(side=tk.RIGHT, padx=15)

        # Separator
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill=tk.X, padx=10)

        # === VM CONTAINER (scrollable) ===
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        self.vm_canvas = tk.Canvas(container, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.vm_canvas.yview)
        self.vm_inner = tk.Frame(self.vm_canvas, bg=BG)
        self.vm_inner.bind("<Configure>",
                           lambda e: self.vm_canvas.configure(scrollregion=self.vm_canvas.bbox("all")))
        self.vm_canvas.create_window((0, 0), window=self.vm_inner, anchor="nw", tags="inner")
        self.vm_canvas.configure(yscrollcommand=sb.set)
        self.vm_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.vm_canvas.bind("<Configure>",
                            lambda e: self.vm_canvas.itemconfig("inner", width=e.width))
        self.vm_canvas.bind_all("<MouseWheel>",
                                lambda e: self.vm_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    # ------------------------------------------------------------------ VM Log (per card)
    def _add_vm_log(self, vm_id: str, msg: str, tag: str = "info"):
        if vm_id not in self.vm_logs:
            self.vm_logs[vm_id] = []
        ts = datetime.now().strftime("%H:%M")
        self.vm_logs[vm_id].append((ts, msg, tag))
        # Giu toi da 5 dong
        if len(self.vm_logs[vm_id]) > 5:
            self.vm_logs[vm_id] = self.vm_logs[vm_id][-5:]
        # Update widget
        self._render_vm_log(vm_id)

    def _render_vm_log(self, vm_id: str):
        w = self.vm_widgets.get(vm_id)
        if not w or "log" not in w:
            return
        log_lbl = w["log"]
        lines = self.vm_logs.get(vm_id, [])
        if not lines:
            log_lbl.config(text="")
            return
        # Show last 3 lines
        display = lines[-3:]
        text_parts = []
        for ts, msg, tag in display:
            text_parts.append(f"{ts} {msg}")
        log_lbl.config(text="  |  ".join(text_parts))

    # ------------------------------------------------------------------ Refresh
    def _refresh(self):
        if self._stop.is_set():
            return
        try:
            self._update_queue()
            self._update_vms()
        except Exception as e:
            print(f"Refresh error: {e}")
        self.root.after(REFRESH_MS, self._refresh)

    def _update_queue(self):
        qs = get_queue_status()
        claimed_count = sum(len(v) for v in qs["claimed"].values())
        vm_count = len(qs["claimed"])
        self.queue_lbl.config(
            text=f"Cho: {qs['available']}   |   Dang lam: {claimed_count} ({vm_count} VM)"
                 f"   |   Het han: {qs['expired']}   |   Xong: {qs['visual']}")

        # Daily stats
        today_count = count_visual_today()
        self.daily_lbl.config(text=f"Hom nay: {today_count} ma xong")

        # Summary
        total_vms = len(self.vm_widgets)
        running = sum(1 for w in self.vm_widgets.values()
                      if "running" in w.get("_state", ""))
        self.summary_lbl.config(text=f"{running}/{total_vms} VM   |   {AUTO_PATH}")

    def _update_vms(self):
        vm_data = {}

        # Read status files
        try:
            for f in STATUS_DIR.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    vm_data[f.stem] = data
                except Exception:
                    continue
        except Exception:
            pass

        # Detect from _CLAIMED
        try:
            qs = get_queue_status()
            for vm_id, codes in qs.get("claimed", {}).items():
                if vm_id not in vm_data:
                    vm_data[vm_id] = {
                        "channel": vm_id,
                        "state": "claimed",
                        "timestamp": "",
                        "project": ", ".join(codes),
                    }
        except Exception:
            pass

        # Update cards
        for vm_id in sorted(vm_data.keys()):
            if vm_id not in self.vm_widgets:
                self._create_card(vm_id)
            self._update_card(vm_id, vm_data[vm_id])

        # Remove stale
        for vm_id in list(self.vm_widgets.keys()):
            if vm_id not in vm_data:
                self.vm_widgets[vm_id]["frame"].destroy()
                del self.vm_widgets[vm_id]

    # ------------------------------------------------------------------ VM Card
    def _create_card(self, vm_id: str):
        card = tk.Frame(self.vm_inner, bg=BG_CARD, bd=0,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.X, padx=8, pady=3)

        # === ROW 1: Name | State | Project | Version | Buttons ===
        row1 = tk.Frame(card, bg=BG_CARD)
        row1.pack(fill=tk.X, padx=8, pady=(6, 0))

        # Dot
        dot = tk.Canvas(row1, width=10, height=10, bg=BG_CARD, highlightthickness=0)
        dot.pack(side=tk.LEFT, padx=(0, 4))
        dot_id = dot.create_oval(1, 1, 9, 9, fill=FG_DIM, outline="")

        # VM name
        name_lbl = tk.Label(row1, text=vm_id, font=("Segoe UI", 11, "bold"),
                            bg=BG_CARD, fg=FG, anchor=tk.W)
        name_lbl.pack(side=tk.LEFT, padx=(0, 6))

        # State
        state_lbl = tk.Label(row1, text="--", font=("Consolas", 10),
                             bg=BG_CARD, fg=FG_DIM, anchor=tk.W)
        state_lbl.pack(side=tk.LEFT, padx=(0, 8))

        # Project
        proj_lbl = tk.Label(row1, text="", font=("Consolas", 10, "bold"),
                            bg=BG_CARD, fg=YELLOW, anchor=tk.W)
        proj_lbl.pack(side=tk.LEFT, padx=(0, 6))

        # Version (right side)
        ver_lbl = tk.Label(row1, text="", font=("Consolas", 9),
                           bg=BG_CARD, fg=FG_DIM)
        ver_lbl.pack(side=tk.RIGHT, padx=(0, 4))

        # Buttons
        btn_frame = tk.Frame(row1, bg=BG_CARD)
        btn_frame.pack(side=tk.RIGHT, padx=(4, 0))
        for txt, clr, cmd in [("RUN", GREEN, "run"),
                               ("STOP", RED, "stop"),
                               ("DONE", ORANGE, "done"),
                               ("UPD", BLUE, "update")]:
            tk.Button(btn_frame, text=txt, bg=clr, fg=BG,
                      font=("Segoe UI", 8, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=7, pady=0,
                      command=lambda v=vm_id, c=cmd: self._cmd(v, c)
                      ).pack(side=tk.LEFT, padx=1)

        # === ROW 2: Progress bar | Images | Excel | Daily | Last image ===
        row2 = tk.Frame(card, bg=BG_CARD)
        row2.pack(fill=tk.X, padx=8, pady=(2, 0))

        progress_lbl = tk.Label(row2, text="", font=("Consolas", 10),
                                bg=BG_CARD, fg=CYAN, anchor=tk.W)
        progress_lbl.pack(side=tk.LEFT, padx=(14, 0))

        # Stale warning (right side of row2)
        warn_lbl = tk.Label(row2, text="", font=("Segoe UI", 9, "bold"),
                            bg=BG_CARD, fg=RED, anchor=tk.E)
        warn_lbl.pack(side=tk.RIGHT, padx=(0, 4))

        # Daily + last image
        stats_lbl = tk.Label(row2, text="", font=("Consolas", 9),
                             bg=BG_CARD, fg=FG_MUTED, anchor=tk.E)
        stats_lbl.pack(side=tk.RIGHT, padx=(8, 4))

        # === ROW 3: Per-VM log ===
        row3 = tk.Frame(card, bg=BG_CARD)
        row3.pack(fill=tk.X, padx=8, pady=(1, 5))

        log_lbl = tk.Label(row3, text="", font=("Consolas", 8),
                           bg=BG_CARD, fg=FG_DIM, anchor=tk.W)
        log_lbl.pack(side=tk.LEFT, padx=(14, 0), fill=tk.X, expand=True)

        self.vm_widgets[vm_id] = {
            "frame": card,
            "dot": dot,
            "dot_id": dot_id,
            "state": state_lbl,
            "project": proj_lbl,
            "progress": progress_lbl,
            "stats": stats_lbl,
            "warn": warn_lbl,
            "version": ver_lbl,
            "log": log_lbl,
            "_state": "",
            "_prev_images": 0,
        }

    def _update_card(self, vm_id: str, data: dict):
        w = self.vm_widgets.get(vm_id)
        if not w:
            return

        state = data.get("state", "unknown")
        project = data.get("project", "")
        version = data.get("version", "")
        uptime = data.get("uptime_minutes", 0)
        project_elapsed = data.get("project_elapsed_minutes", 0)
        images_done = data.get("images_done", 0)
        total_scenes = data.get("total_scenes", 0)
        excel_step = data.get("excel_step", "")
        completed_today = data.get("completed_today", 0)
        last_image_time = data.get("last_image_time", "")

        # --- State ---
        state_parts = [state]
        if uptime:
            h, m = uptime // 60, uptime % 60
            state_parts.append(f"{h}h{m:02d}m")
        w["state"].config(text=" | ".join(state_parts))
        w["_state"] = state

        # State color
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

        # --- Project ---
        proj_text = ""
        if project:
            proj_text = project
            if project_elapsed:
                ph, pm = project_elapsed // 60, project_elapsed % 60
                proj_text = f"{project} ({ph}h{pm:02d}m)"
        w["project"].config(text=proj_text)

        # --- Progress ---
        progress_parts = []
        if total_scenes > 0:
            pct = images_done / total_scenes
            bar = _progress_bar(pct, 12)
            progress_parts.append(f"{bar} {images_done}/{total_scenes} ({int(pct * 100)}%)")
        if excel_step:
            if excel_step == "done":
                progress_parts.append("Excel: done")
            else:
                progress_parts.append(f"Excel: {excel_step}")
        w["progress"].config(text="   ".join(progress_parts))

        # --- Daily stats + last image ---
        stats_parts = []
        if completed_today > 0:
            stats_parts.append(f"Hom nay: {completed_today} ma")
        last_ago = _time_ago(last_image_time)
        if last_ago != "--":
            stats_parts.append(f"Anh moi: {last_ago}")
        w["stats"].config(text="   ".join(stats_parts))

        # --- Stale warning ---
        is_stale = False
        if "running" in state.lower() and last_image_time:
            try:
                ts = datetime.strptime(last_image_time, "%Y-%m-%d %H:%M:%S")
                minutes_ago = (datetime.now() - ts).total_seconds() / 60
                if minutes_ago > STALE_MINUTES:
                    is_stale = True
                    w["warn"].config(text=f"!! CHAM ({int(minutes_ago)}p)")
                    w["frame"].config(highlightbackground=BORDER_WARN)
            except Exception:
                pass
        if not is_stale:
            w["warn"].config(text="")

        # --- Version ---
        w["version"].config(text=f"v{version}" if version else "")

        # --- Render per-VM log ---
        self._render_vm_log(vm_id)

    # ------------------------------------------------------------------ Commands
    def _cmd(self, vm_id: str, cmd: str):
        """Send command to VM with auto-retry on timeout."""
        max_retries = 5

        def _send_and_wait(attempt: int):
            cmd_file = COMMANDS_DIR / f"{vm_id}.{cmd}"
            ack_file = COMMANDS_DIR / f"{vm_id}.{cmd}.ack"
            try:
                if ack_file.exists():
                    ack_file.unlink()
                cmd_file.write_text(json.dumps({
                    "command": cmd,
                    "timestamp": datetime.now().isoformat()
                }), encoding='utf-8')
                if attempt == 1:
                    self.root.after(0, lambda: self._add_vm_log(
                        vm_id, f"Gui {cmd.upper()}", "info"))
                else:
                    self.root.after(0, lambda a=attempt: self._add_vm_log(
                        vm_id, f"Retry {cmd.upper()} ({a}/{max_retries})", "warn"))
            except Exception as e:
                self.root.after(0, lambda: self._add_vm_log(
                    vm_id, f"LOI: {e}", "err"))
                return

            # Wait ACK
            max_wait = 120 if cmd == "update" else 30
            for _ in range(max_wait):
                time.sleep(1)
                if ack_file.exists():
                    try:
                        ack = json.loads(ack_file.read_text(encoding='utf-8'))
                        result = ack.get('result', '?')
                        tag = "ok" if "OK" in str(result) else "warn"
                        self.root.after(0, lambda r=result, t=tag: self._add_vm_log(
                            vm_id, f"{cmd.upper()} -> {r}", t))
                        ack_file.unlink()
                        return
                    except Exception:
                        pass

            # TIMEOUT -> retry
            if attempt < max_retries:
                self.root.after(0, lambda: self._add_vm_log(
                    vm_id, f"{cmd.upper()} TIMEOUT -> retry", "warn"))
                time.sleep(2)
                _send_and_wait(attempt + 1)
            else:
                self.root.after(0, lambda: self._add_vm_log(
                    vm_id, f"{cmd.upper()} THAT BAI ({max_retries} lan)", "err"))

        threading.Thread(target=lambda: _send_and_wait(1), daemon=True).start()

    def _cmd_all(self, cmd: str):
        """Send command to all VMs."""
        vms = list(self.vm_widgets.keys())
        if not vms:
            return
        for vm_id in vms:
            self._cmd(vm_id, cmd)

    def on_close(self):
        self._stop.set()
        self.root.destroy()


# ============================================================================
# MAIN
# ============================================================================

def main():
    root = tk.Tk()
    app = MasterControlGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
