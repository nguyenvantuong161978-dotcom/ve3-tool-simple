#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - Master Control Panel

GUI trên máy chủ để quản lý các VM đang chạy ve3-tool-simple.
File độc lập - không cần import module nào khác.

Giao tiếp: File-based IPC qua shared folder.
- Commands: AUTO/commands/{VM_ID}.{cmd}
- Status:   AUTO/status/{VM_ID}.json
- Queue:    AUTO/ve3-tool-simple/PROJECTS/ (_CLAIMED files)

Chạy:
    python master_control.py
"""

import os
import sys
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
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

# Tự tạo thư mục nếu chưa có
CONTROL_DIR.mkdir(parents=True, exist_ok=True)
COMMANDS_DIR.mkdir(parents=True, exist_ok=True)
STATUS_DIR.mkdir(parents=True, exist_ok=True)
MASTER_PROJECTS.mkdir(parents=True, exist_ok=True)
VISUAL_DIR.mkdir(parents=True, exist_ok=True)

REFRESH_MS = 10000  # 10 seconds
CLAIM_TIMEOUT_HOURS = 8


# ============================================================================
# COLORS (Catppuccin Dark Theme)
# ============================================================================

BG = "#1e1e2e"
BG_CARD = "#313244"
FG = "#cdd6f4"
FG_DIM = "#6c7086"
GREEN = "#a6e3a1"
RED = "#f38ba8"
BLUE = "#89b4fa"
YELLOW = "#f9e2af"
ORANGE = "#fab387"
PURPLE = "#cba6f7"


# ============================================================================
# QUEUE HELPERS (nhúng trực tiếp, không cần import)
# ============================================================================

def _is_claim_expired(claimed_file: Path) -> bool:
    """Check xem claim đã quá hạn chưa."""
    try:
        content = claimed_file.read_text(encoding='utf-8').strip()
        lines = content.split('\n')
        if len(lines) < 2:
            return True
        timestamp_str = lines[1].strip()
        claim_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        elapsed_hours = (datetime.now() - claim_time).total_seconds() / 3600
        return elapsed_hours > CLAIM_TIMEOUT_HOURS
    except Exception:
        return True


def _read_claim_vm_id(claimed_file: Path):
    """Đọc VM ID từ file _CLAIMED."""
    try:
        content = claimed_file.read_text(encoding='utf-8').strip()
        first_line = content.split('\n')[0].strip()
        return first_line if first_line else None
    except Exception:
        return None


def _is_in_visual(code: str) -> bool:
    """Check xem project đã có trong visual chưa."""
    try:
        visual_dir = VISUAL_DIR / code
        return visual_dir.exists() and any(visual_dir.iterdir())
    except Exception:
        return False


def get_queue_status() -> dict:
    """Lấy trạng thái queue (không cần TaskQueue class)."""
    status = {"total": 0, "available": 0, "claimed": {}, "expired": 0}
    if not MASTER_PROJECTS.exists():
        return status
    try:
        for item in MASTER_PROJECTS.iterdir():
            if not item.is_dir():
                continue
            srt_files = list(item.glob("*.srt"))
            if not srt_files:
                continue
            if _is_in_visual(item.name):
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
                    if vm_id not in status["claimed"]:
                        status["claimed"][vm_id] = []
                    status["claimed"][vm_id].append(item.name)
    except Exception:
        pass
    return status


# ============================================================================
# MASTER CONTROL GUI
# ============================================================================

class MasterControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VE3 Tool - Master Control")
        self.root.configure(bg=BG)
        self.root.geometry("1200x800")

        self.vm_frames = {}  # VM_ID → frame widgets
        self._stop_event = threading.Event()

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        """Build main UI."""
        # === TOP BAR ===
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(top, text="VE3 MASTER CONTROL", font=("Consolas", 16, "bold"),
                 bg=BG, fg=PURPLE).pack(side=tk.LEFT)

        tk.Label(top, text=f"AUTO: {AUTO_PATH}", font=("Consolas", 9),
                 bg=BG, fg=FG_DIM).pack(side=tk.LEFT, padx=20)

        # Buttons
        btn_frame = tk.Frame(top, bg=BG)
        btn_frame.pack(side=tk.RIGHT)

        tk.Button(btn_frame, text="RUN ALL", bg=GREEN, fg=BG, font=("Consolas", 10, "bold"),
                  command=lambda: self._send_command_all("run"), width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="STOP ALL", bg=RED, fg=BG, font=("Consolas", 10, "bold"),
                  command=lambda: self._send_command_all("stop"), width=10).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="UPDATE ALL", bg=BLUE, fg=BG, font=("Consolas", 10, "bold"),
                  command=lambda: self._send_command_all("update"), width=10).pack(side=tk.LEFT, padx=2)

        # === QUEUE STATUS ===
        queue_frame = tk.Frame(self.root, bg=BG_CARD, relief=tk.RIDGE, bd=1)
        queue_frame.pack(fill=tk.X, padx=10, pady=5)

        self.queue_label = tk.Label(queue_frame, text="Queue: ...", font=("Consolas", 11),
                                    bg=BG_CARD, fg=FG, anchor=tk.W)
        self.queue_label.pack(fill=tk.X, padx=10, pady=5)

        # === VM LIST (scrollable) ===
        canvas_frame = tk.Frame(self.root, bg=BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(canvas_frame, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.vm_container = tk.Frame(self.canvas, bg=BG)

        self.vm_container.bind("<Configure>",
                               lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.vm_container, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel scroll
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _refresh(self):
        """Refresh VM status + queue status."""
        if self._stop_event.is_set():
            return

        try:
            self._update_queue_status()
            self._update_vm_list()
        except Exception as e:
            print(f"Refresh error: {e}")

        self.root.after(REFRESH_MS, self._refresh)

    def _update_queue_status(self):
        """Update queue status display."""
        try:
            status = get_queue_status()

            claimed_str = ""
            for vm_id, codes in status["claimed"].items():
                claimed_str += f"  {vm_id}: {', '.join(codes)}"

            text = (f"Queue: {status['total']} total | "
                    f"{status['available']} available | "
                    f"{len(status['claimed'])} VMs working | "
                    f"{status['expired']} expired")
            if claimed_str:
                text += f"\n  Claims:{claimed_str}"

            self.queue_label.config(text=text)
        except Exception as e:
            self.queue_label.config(text=f"Queue: Error - {e}")

    def _update_vm_list(self):
        """Update VM status cards."""
        vm_statuses = {}

        # Read status files
        try:
            for f in STATUS_DIR.glob("*.json"):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    vm_id = f.stem
                    vm_statuses[vm_id] = data
                except Exception:
                    continue
        except Exception:
            pass

        # Detect VMs from _CLAIMED files
        try:
            queue_status = get_queue_status()
            for vm_id in queue_status.get("claimed", {}):
                if vm_id not in vm_statuses:
                    vm_statuses[vm_id] = {
                        "channel": vm_id,
                        "state": "claimed (no status)",
                        "timestamp": "",
                        "project": ", ".join(queue_status["claimed"][vm_id]),
                    }
        except Exception:
            pass

        # Update/create VM cards
        for vm_id in sorted(vm_statuses.keys()):
            data = vm_statuses[vm_id]
            if vm_id not in self.vm_frames:
                self._create_vm_card(vm_id)
            self._update_vm_card(vm_id, data)

        # Remove old VMs
        for vm_id in list(self.vm_frames.keys()):
            if vm_id not in vm_statuses:
                self.vm_frames[vm_id]["frame"].destroy()
                del self.vm_frames[vm_id]

    def _create_vm_card(self, vm_id: str):
        """Create a VM status card."""
        frame = tk.Frame(self.vm_container, bg=BG_CARD, relief=tk.RIDGE, bd=1)
        frame.pack(fill=tk.X, padx=5, pady=3)

        # Left: info
        info = tk.Frame(frame, bg=BG_CARD)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)

        name_label = tk.Label(info, text=vm_id, font=("Consolas", 13, "bold"),
                              bg=BG_CARD, fg=FG)
        name_label.pack(anchor=tk.W)

        status_label = tk.Label(info, text="...", font=("Consolas", 10),
                                bg=BG_CARD, fg=FG_DIM)
        status_label.pack(anchor=tk.W)

        project_label = tk.Label(info, text="", font=("Consolas", 10),
                                 bg=BG_CARD, fg=YELLOW)
        project_label.pack(anchor=tk.W)

        # Right: buttons
        btns = tk.Frame(frame, bg=BG_CARD)
        btns.pack(side=tk.RIGHT, padx=10, pady=5)

        tk.Button(btns, text="RUN", bg=GREEN, fg=BG, font=("Consolas", 9),
                  command=lambda v=vm_id: self._send_command(v, "run"), width=7).pack(pady=1)
        tk.Button(btns, text="STOP", bg=RED, fg=BG, font=("Consolas", 9),
                  command=lambda v=vm_id: self._send_command(v, "stop"), width=7).pack(pady=1)
        tk.Button(btns, text="UPDATE", bg=BLUE, fg=BG, font=("Consolas", 9),
                  command=lambda v=vm_id: self._send_command(v, "update"), width=7).pack(pady=1)

        # Status indicator
        indicator = tk.Label(frame, text="  ", bg=FG_DIM, width=2)
        indicator.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 0))

        self.vm_frames[vm_id] = {
            "frame": frame,
            "name": name_label,
            "status": status_label,
            "project": project_label,
            "indicator": indicator,
        }

    def _update_vm_card(self, vm_id: str, data: dict):
        """Update a VM card with new data."""
        widgets = self.vm_frames.get(vm_id)
        if not widgets:
            return

        state = data.get("state", "unknown")
        timestamp = data.get("timestamp", "")
        project = data.get("project", data.get("current_project", ""))
        version = data.get("version", "")
        uptime = data.get("uptime_minutes", 0)

        # Status text
        parts = []
        if state:
            parts.append(f"State: {state}")
        if version:
            parts.append(f"v{version}")
        if uptime:
            hours = uptime // 60
            mins = uptime % 60
            parts.append(f"Uptime: {hours}h{mins}m")
        if timestamp:
            parts.append(f"Last: {timestamp}")

        widgets["status"].config(text=" | ".join(parts))

        # Project
        if project:
            widgets["project"].config(text=f"Project: {project}")
        else:
            widgets["project"].config(text="")

        # Indicator color
        color_map = {
            "running": GREEN,
            "idle": ORANGE,
            "stopped": RED,
            "killed": RED,
            "updating": BLUE,
            "starting": BLUE,
        }
        color = GREEN if "running" in state.lower() else color_map.get(state, FG_DIM)
        widgets["indicator"].config(bg=color)

    def _send_command(self, vm_id: str, cmd: str):
        """Send command to a specific VM."""
        cmd_file = COMMANDS_DIR / f"{vm_id}.{cmd}"
        try:
            # Xóa ACK cũ trước khi gửi lệnh mới
            ack_file = COMMANDS_DIR / f"{vm_id}.{cmd}.ack"
            if ack_file.exists():
                ack_file.unlink()

            cmd_file.write_text(json.dumps({"command": cmd, "timestamp": datetime.now().isoformat()}),
                               encoding='utf-8')
            print(f"[CMD] Sent {cmd} to {vm_id}")

            # Chờ ACK (tối đa 15s)
            def wait_ack():
                import time
                for _ in range(15):
                    time.sleep(1)
                    if ack_file.exists():
                        try:
                            ack_data = json.loads(ack_file.read_text(encoding='utf-8'))
                            result = ack_data.get('result', '?')
                            ts = ack_data.get('timestamp', '')
                            print(f"[ACK] {vm_id}: {cmd} → {result} ({ts})")
                            # Hiển thị trên GUI
                            self.root.after(0, lambda: messagebox.showinfo(
                                "ACK", f"{vm_id} đã nhận lệnh {cmd.upper()}\n\nKết quả: {result}"))
                            ack_file.unlink()
                            return
                        except Exception:
                            pass
                print(f"[ACK] {vm_id}: {cmd} → TIMEOUT (VM chưa phản hồi)")

            threading.Thread(target=wait_ack, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Error", f"Cannot send {cmd} to {vm_id}: {e}")

    def _send_command_all(self, cmd: str):
        """Send command to all VMs."""
        confirm = messagebox.askyesno("Confirm", f"Send '{cmd.upper()}' to ALL VMs?")
        if not confirm:
            return

        for vm_id in list(self.vm_frames.keys()):
            self._send_command(vm_id, cmd)

    def on_close(self):
        """Handle window close."""
        self._stop_event.set()
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
