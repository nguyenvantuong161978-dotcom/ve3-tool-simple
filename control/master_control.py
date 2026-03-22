#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - Master Control Panel v2

GUI trên máy chủ để quản lý các VM đang chạy ve3-tool-simple.
File độc lập - không cần import module nào khác.

v1.0.350: Redesign - bỏ popup, thêm log panel, layout gọn hơn.

Chạy:
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
from datetime import datetime


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

# Tự tạo thư mục
for d in [CONTROL_DIR, COMMANDS_DIR, STATUS_DIR, MASTER_PROJECTS, VISUAL_DIR]:
    d.mkdir(parents=True, exist_ok=True)

REFRESH_MS = 8000  # 8 seconds
CLAIM_TIMEOUT_HOURS = 8


# ============================================================================
# COLORS
# ============================================================================

BG = "#0f0f17"
BG2 = "#1a1a2e"
BG_CARD = "#16213e"
BG_CARD_HOVER = "#1a2744"
FG = "#e0e0e0"
FG_DIM = "#6c7086"
FG_MUTED = "#8890a0"
GREEN = "#4ade80"
GREEN_DIM = "#22543d"
RED = "#f87171"
RED_DIM = "#7f1d1d"
BLUE = "#60a5fa"
YELLOW = "#fbbf24"
ORANGE = "#fb923c"
PURPLE = "#a78bfa"
CYAN = "#22d3ee"
BORDER = "#2a2a4e"


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


# ============================================================================
# MASTER CONTROL GUI
# ============================================================================

class MasterControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Master Control")
        self.root.configure(bg=BG)
        self.root.geometry("900x700")
        self.root.minsize(700, 500)

        self.vm_widgets = {}  # VM_ID → widget dict
        self._stop = threading.Event()
        self._log_lines = []  # Log history

        self._build()
        self._refresh()

    # ------------------------------------------------------------------ UI
    def _build(self):
        # === HEADER ===
        hdr = tk.Frame(self.root, bg=BG2, pady=8)
        hdr.pack(fill=tk.X)

        tk.Label(hdr, text="MASTER CONTROL", font=("Segoe UI", 14, "bold"),
                 bg=BG2, fg=PURPLE).pack(side=tk.LEFT, padx=15)

        self.summary_lbl = tk.Label(hdr, text="", font=("Segoe UI", 10),
                                     bg=BG2, fg=FG_MUTED)
        self.summary_lbl.pack(side=tk.LEFT, padx=10)

        # ALL buttons
        bf = tk.Frame(hdr, bg=BG2)
        bf.pack(side=tk.RIGHT, padx=10)
        for txt, clr, cmd in [("RUN ALL", GREEN, "run"),
                               ("STOP ALL", RED, "stop"),
                               ("UPDATE ALL", BLUE, "update")]:
            tk.Button(bf, text=txt, bg=clr, fg=BG, font=("Segoe UI", 9, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=12, pady=2,
                      command=lambda c=cmd: self._cmd_all(c)).pack(side=tk.LEFT, padx=3)

        # === QUEUE BAR ===
        self.queue_lbl = tk.Label(self.root, text="", font=("Consolas", 10),
                                   bg=BG, fg=FG_DIM, anchor=tk.W)
        self.queue_lbl.pack(fill=tk.X, padx=15, pady=(6, 2))

        # === MAIN: VM list (top) + Log (bottom) ===
        pw = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg=BG,
                            sashwidth=4, sashrelief=tk.FLAT)
        pw.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # -- VM container --
        vm_outer = tk.Frame(pw, bg=BG)
        pw.add(vm_outer, stretch="always")

        self.vm_canvas = tk.Canvas(vm_outer, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(vm_outer, orient=tk.VERTICAL, command=self.vm_canvas.yview)
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

        # -- Log panel --
        log_frame = tk.Frame(pw, bg=BG2)
        pw.add(log_frame, height=140)

        tk.Label(log_frame, text="Log", font=("Segoe UI", 9, "bold"),
                 bg=BG2, fg=FG_DIM).pack(anchor=tk.W, padx=8, pady=(4, 0))

        self.log_text = tk.Text(log_frame, bg=BG, fg=FG_MUTED, font=("Consolas", 9),
                                height=6, bd=0, highlightthickness=0,
                                state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 6))

        # Tag colors for log
        self.log_text.tag_config("ok", foreground=GREEN)
        self.log_text.tag_config("err", foreground=RED)
        self.log_text.tag_config("warn", foreground=YELLOW)
        self.log_text.tag_config("info", foreground=BLUE)
        self.log_text.tag_config("time", foreground=FG_DIM)

    # ------------------------------------------------------------------ Log
    def _log(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{ts} ", "time")
        self.log_text.insert(tk.END, f"{msg}\n", tag)
        self.log_text.see(tk.END)
        # Giữ tối đa 200 dòng
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 200:
            self.log_text.delete('1.0', f'{lines - 200}.0')
        self.log_text.config(state=tk.DISABLED)

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
            text=f"Queue: {qs['available']} cho  |  {claimed_count} dang lam ({vm_count} VM)  |  "
                 f"{qs['expired']} het han  |  {qs['visual']} xong")

        # Summary in header
        total_vms = len(self.vm_widgets)
        running = sum(1 for w in self.vm_widgets.values()
                      if "running" in w.get("_state", ""))
        self.summary_lbl.config(text=f"{running}/{total_vms} VM dang chay   |   "
                                     f"AUTO: {AUTO_PATH}")

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
        card.pack(fill=tk.X, padx=4, pady=3)

        # Row layout
        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill=tk.X, padx=2, pady=6)

        # Indicator dot
        dot = tk.Canvas(row, width=10, height=10, bg=BG_CARD, highlightthickness=0)
        dot.pack(side=tk.LEFT, padx=(8, 6), pady=0)
        dot_id = dot.create_oval(1, 1, 9, 9, fill=FG_DIM, outline="")

        # VM name
        name = tk.Label(row, text=vm_id, font=("Segoe UI", 11, "bold"),
                        bg=BG_CARD, fg=FG, width=12, anchor=tk.W)
        name.pack(side=tk.LEFT, padx=(0, 8))

        # State
        state_lbl = tk.Label(row, text="--", font=("Consolas", 10),
                             bg=BG_CARD, fg=FG_DIM, width=18, anchor=tk.W)
        state_lbl.pack(side=tk.LEFT, padx=4)

        # Project + progress (v1.0.364)
        proj_lbl = tk.Label(row, text="", font=("Consolas", 10),
                            bg=BG_CARD, fg=YELLOW, anchor=tk.W)
        proj_lbl.pack(side=tk.LEFT, padx=4)

        # Progress detail
        progress_lbl = tk.Label(row, text="", font=("Consolas", 9),
                                bg=BG_CARD, fg=CYAN, anchor=tk.W)
        progress_lbl.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # Version
        ver_lbl = tk.Label(row, text="", font=("Consolas", 9),
                           bg=BG_CARD, fg=FG_DIM)
        ver_lbl.pack(side=tk.LEFT, padx=4)

        # Buttons (compact)
        for txt, clr, cmd in [("RUN", GREEN, "run"),
                               ("STOP", RED, "stop"),
                               ("DONE", ORANGE, "done"),
                               ("UPD", BLUE, "update")]:
            tk.Button(row, text=txt, bg=clr, fg=BG, font=("Segoe UI", 8, "bold"),
                      activebackground=clr, relief=tk.FLAT, padx=8, pady=1,
                      command=lambda v=vm_id, c=cmd: self._cmd(v, c)
                      ).pack(side=tk.LEFT, padx=2)

        self.vm_widgets[vm_id] = {
            "frame": card,
            "dot": dot,
            "dot_id": dot_id,
            "state": state_lbl,
            "project": proj_lbl,
            "progress": progress_lbl,
            "version": ver_lbl,
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
        timestamp = data.get("timestamp", "")

        # v1.0.364: Project progress data
        project_elapsed = data.get("project_elapsed_minutes", 0)
        images_done = data.get("images_done", 0)
        total_scenes = data.get("total_scenes", 0)
        excel_step = data.get("excel_step", "")

        # State text
        state_parts = [state]
        if uptime:
            h, m = uptime // 60, uptime % 60
            state_parts.append(f"{h}h{m:02d}m")
        w["state"].config(text=" | ".join(state_parts))
        w["_state"] = state

        # Project + elapsed time
        proj_text = project
        if project and project_elapsed:
            ph, pm = project_elapsed // 60, project_elapsed % 60
            proj_text = f"{project} ({ph}h{pm:02d}m)"
        w["project"].config(text=proj_text if proj_text else "")

        # Progress: images + excel step
        progress_parts = []
        if total_scenes > 0:
            pct = int(images_done / total_scenes * 100)
            progress_parts.append(f"{images_done}/{total_scenes} anh ({pct}%)")
        if excel_step and excel_step != "done":
            progress_parts.append(f"Excel: {excel_step}")
        w["progress"].config(text=" | ".join(progress_parts))

        # Version
        w["version"].config(text=f"v{version}" if version else "")

        # Dot color
        if "running" in state.lower():
            color = GREEN
        elif state in ("idle", "claimed"):
            color = ORANGE
        elif state in ("stopped", "killed"):
            color = RED
        elif state in ("updating", "starting"):
            color = BLUE
        else:
            color = FG_DIM
        w["dot"].itemconfig(w["dot_id"], fill=color)

        # Card border color
        border = GREEN if "running" in state.lower() else BORDER
        w["frame"].config(highlightbackground=border)

        # State label color
        if "running" in state.lower():
            w["state"].config(fg=GREEN)
        elif state in ("stopped", "killed"):
            w["state"].config(fg=RED)
        else:
            w["state"].config(fg=FG_MUTED)

    # ------------------------------------------------------------------ Commands
    def _cmd(self, vm_id: str, cmd: str):
        """Send command to VM, show result in log (no popup)."""
        cmd_file = COMMANDS_DIR / f"{vm_id}.{cmd}"
        ack_file = COMMANDS_DIR / f"{vm_id}.{cmd}.ack"
        try:
            if ack_file.exists():
                ack_file.unlink()
            cmd_file.write_text(json.dumps({
                "command": cmd,
                "timestamp": datetime.now().isoformat()
            }), encoding='utf-8')
            self._log(f"[{vm_id}] Gui lenh {cmd.upper()}", "info")
        except Exception as e:
            self._log(f"[{vm_id}] LOI gui {cmd}: {e}", "err")
            return

        # Wait ACK in background
        def wait():
            max_wait = 120 if cmd == "update" else 30
            for _ in range(max_wait):
                time.sleep(1)
                if ack_file.exists():
                    try:
                        ack = json.loads(ack_file.read_text(encoding='utf-8'))
                        result = ack.get('result', '?')
                        self.root.after(0, lambda r=result: self._log(
                            f"[{vm_id}] {cmd.upper()} → {r}", "ok" if "OK" in str(r) else "warn"))
                        ack_file.unlink()
                        return
                    except Exception:
                        pass
            self.root.after(0, lambda: self._log(
                f"[{vm_id}] {cmd.upper()} → TIMEOUT ({max_wait}s)", "err"))

        threading.Thread(target=wait, daemon=True).start()

    def _cmd_all(self, cmd: str):
        """Send command to all VMs."""
        vms = list(self.vm_widgets.keys())
        if not vms:
            self._log("Khong co VM nao", "warn")
            return
        self._log(f"Gui {cmd.upper()} toi {len(vms)} VM...", "info")
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
