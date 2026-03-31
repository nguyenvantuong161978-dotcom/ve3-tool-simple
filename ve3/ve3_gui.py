#!/usr/bin/env python3
"""
VE3 Simple - GUI Tạo Ảnh qua Server

Entry point chính. Chạy: python ve3_gui.py

Giao diện:
- Cấu hình server (URL, token, project ID)
- Upload Excel hoặc tạo từ SRT
- Xem tiến độ tạo ảnh realtime
- Start/Stop/Open folder
"""

import sys
import os
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime

# Đảm bảo import từ thư mục ve3
VE3_DIR = Path(__file__).parent
sys.path.insert(0, str(VE3_DIR))

# =============================================================================
# CONSTANTS
# =============================================================================

APP_TITLE = "VE3 Simple - Image Generator"
WINDOW_SIZE = "950x720"

# Colors (dark theme)
BG_COLOR = "#1a1a2e"
BG_SECONDARY = "#16213e"
BG_FRAME = "#0f3460"
FG_COLOR = "#e8e8e8"
FG_DIM = "#888888"
ACCENT_COLOR = "#e94560"
SUCCESS_COLOR = "#4ecca3"
WARN_COLOR = "#ffc107"
BUTTON_BG = "#0f3460"
BUTTON_FG = "#e8e8e8"
ENTRY_BG = "#16213e"
ENTRY_FG = "#e8e8e8"


# =============================================================================
# MAIN GUI
# =============================================================================

class VE3GUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)
        self.configure(bg=BG_COLOR)
        self.resizable(True, True)

        # State
        self.config = {}
        self.worker = None
        self.worker_thread = None
        self.excel_path = None
        self.project_dir = None

        # Load config
        self._load_config()

        # Build UI
        self._build_ui()

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_reqwidth()) // 2
        y = (self.winfo_screenheight() - self.winfo_reqheight()) // 2
        self.geometry(f"+{x}+{y}")

    def _load_config(self):
        """Load settings.yaml."""
        try:
            import yaml
            config_path = VE3_DIR / "config" / "settings.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Config load error: {e}")
            self.config = {}

    def _save_config(self):
        """Save settings.yaml."""
        try:
            import yaml
            config_path = VE3_DIR / "config" / "settings.yaml"
            # Cập nhật từ GUI
            self.config["local_server_url"] = self.sv_server_url.get().strip()
            self.config["flow_bearer_token"] = self.sv_token.get().strip()
            self.config["flow_project_id"] = self.sv_project_id.get().strip()
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            self._log(f"Config save error: {e}", "WARN")

    # =========================================================================
    # UI BUILDING
    # =========================================================================

    def _build_ui(self):
        """Build toàn bộ giao diện."""

        # === TOP: Title ===
        title_frame = tk.Frame(self, bg=BG_COLOR)
        title_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        tk.Label(title_frame, text="VE3 SIMPLE", font=("Arial", 18, "bold"),
                 bg=BG_COLOR, fg=ACCENT_COLOR).pack(side=tk.LEFT)
        tk.Label(title_frame, text="  Image Generator via Server",
                 font=("Arial", 11), bg=BG_COLOR, fg=FG_DIM).pack(side=tk.LEFT, padx=5)

        # === SERVER CONFIG ===
        server_frame = tk.LabelFrame(self, text=" Server Config ",
                                     font=("Arial", 10, "bold"),
                                     bg=BG_SECONDARY, fg=FG_COLOR,
                                     relief=tk.GROOVE, bd=1)
        server_frame.pack(fill=tk.X, padx=10, pady=5)

        # Row 1: Server URL
        row1 = tk.Frame(server_frame, bg=BG_SECONDARY)
        row1.pack(fill=tk.X, padx=10, pady=(8, 3))
        tk.Label(row1, text="Server:", width=8, anchor="e",
                 bg=BG_SECONDARY, fg=FG_COLOR, font=("Arial", 10)).pack(side=tk.LEFT)
        self.sv_server_url = tk.StringVar(value=self.config.get("local_server_url", "http://192.168.88.145:5000"))
        tk.Entry(row1, textvariable=self.sv_server_url, width=45,
                 bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                 font=("Consolas", 10), relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        tk.Button(row1, text="Test", command=self._test_connection, width=6,
                  bg=BUTTON_BG, fg=BUTTON_FG, relief=tk.FLAT,
                  font=("Arial", 9, "bold"), cursor="hand2").pack(side=tk.LEFT, padx=3)

        # Row 2: Token + Project ID
        row2 = tk.Frame(server_frame, bg=BG_SECONDARY)
        row2.pack(fill=tk.X, padx=10, pady=(3, 3))
        tk.Label(row2, text="Token:", width=8, anchor="e",
                 bg=BG_SECONDARY, fg=FG_COLOR, font=("Arial", 10)).pack(side=tk.LEFT)
        self.sv_token = tk.StringVar(value=self.config.get("flow_bearer_token", ""))
        tk.Entry(row2, textvariable=self.sv_token, width=45, show="*",
                 bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                 font=("Consolas", 10), relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        row3 = tk.Frame(server_frame, bg=BG_SECONDARY)
        row3.pack(fill=tk.X, padx=10, pady=(3, 8))
        tk.Label(row3, text="ProjID:", width=8, anchor="e",
                 bg=BG_SECONDARY, fg=FG_COLOR, font=("Arial", 10)).pack(side=tk.LEFT)
        self.sv_project_id = tk.StringVar(value=self.config.get("flow_project_id", ""))
        tk.Entry(row3, textvariable=self.sv_project_id, width=45,
                 bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                 font=("Consolas", 10), relief=tk.FLAT).pack(side=tk.LEFT, padx=5)

        # === MIDDLE: Excel + Progress ===
        middle_frame = tk.Frame(self, bg=BG_COLOR)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Left: Excel section
        left_frame = tk.LabelFrame(middle_frame, text=" Excel Project ",
                                   font=("Arial", 10, "bold"),
                                   bg=BG_SECONDARY, fg=FG_COLOR,
                                   relief=tk.GROOVE, bd=1, width=280)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        left_frame.pack_propagate(False)

        btn_frame = tk.Frame(left_frame, bg=BG_SECONDARY)
        btn_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        tk.Button(btn_frame, text="📂 Upload Excel", command=self._upload_excel,
                  width=20, bg=BUTTON_BG, fg=BUTTON_FG, relief=tk.FLAT,
                  font=("Arial", 10), cursor="hand2").pack(pady=3)
        tk.Button(btn_frame, text="📝 Tạo từ SRT (API)", command=self._create_from_srt,
                  width=20, bg=BUTTON_BG, fg=BUTTON_FG, relief=tk.FLAT,
                  font=("Arial", 10), cursor="hand2").pack(pady=3)
        tk.Button(btn_frame, text="📋 Tải Excel Mẫu", command=self._download_template,
                  width=20, bg=BUTTON_BG, fg=BUTTON_FG, relief=tk.FLAT,
                  font=("Arial", 10), cursor="hand2").pack(pady=3)

        # Excel info
        info_frame = tk.Frame(left_frame, bg=BG_SECONDARY)
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        self.lbl_file = tk.Label(info_frame, text="File: (chưa có)",
                                 bg=BG_SECONDARY, fg=FG_DIM, font=("Arial", 9),
                                 wraplength=240, justify=tk.LEFT)
        self.lbl_file.pack(anchor=tk.W, pady=2)

        self.lbl_scenes = tk.Label(info_frame, text="Scenes: -",
                                   bg=BG_SECONDARY, fg=FG_COLOR, font=("Arial", 10))
        self.lbl_scenes.pack(anchor=tk.W, pady=2)

        self.lbl_chars = tk.Label(info_frame, text="Characters: -",
                                  bg=BG_SECONDARY, fg=FG_COLOR, font=("Arial", 10))
        self.lbl_chars.pack(anchor=tk.W, pady=2)

        self.lbl_status = tk.Label(info_frame, text="Status: Chờ upload Excel",
                                   bg=BG_SECONDARY, fg=WARN_COLOR, font=("Arial", 10, "bold"))
        self.lbl_status.pack(anchor=tk.W, pady=(10, 2))

        # Right: Progress section
        right_frame = tk.LabelFrame(middle_frame, text=" Progress ",
                                    font=("Arial", 10, "bold"),
                                    bg=BG_SECONDARY, fg=FG_COLOR,
                                    relief=tk.GROOVE, bd=1)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Progress bars
        prog_frame = tk.Frame(right_frame, bg=BG_SECONDARY)
        prog_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # References progress
        tk.Label(prog_frame, text="References:", bg=BG_SECONDARY, fg=FG_COLOR,
                 font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.pb_refs = ttk.Progressbar(prog_frame, mode="determinate", length=300)
        self.pb_refs.grid(row=0, column=1, padx=5, pady=2)
        self.lbl_refs_count = tk.Label(prog_frame, text="0/0", bg=BG_SECONDARY, fg=FG_COLOR,
                                       font=("Arial", 9))
        self.lbl_refs_count.grid(row=0, column=2, pady=2)

        # Scenes progress
        tk.Label(prog_frame, text="Scenes:", bg=BG_SECONDARY, fg=FG_COLOR,
                 font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.pb_scenes = ttk.Progressbar(prog_frame, mode="determinate", length=300)
        self.pb_scenes.grid(row=1, column=1, padx=5, pady=2)
        self.lbl_scenes_count = tk.Label(prog_frame, text="0/0", bg=BG_SECONDARY, fg=FG_COLOR,
                                         font=("Arial", 9))
        self.lbl_scenes_count.grid(row=1, column=2, pady=2)

        # Current task
        self.lbl_current = tk.Label(right_frame, text="", bg=BG_SECONDARY, fg=SUCCESS_COLOR,
                                    font=("Arial", 9))
        self.lbl_current.pack(anchor=tk.W, padx=10)

        # Log text area
        self.log_text = scrolledtext.ScrolledText(
            right_frame, height=15, width=60,
            bg="#0a0a1a", fg="#cccccc",
            font=("Consolas", 9),
            relief=tk.FLAT, wrap=tk.WORD,
            insertbackground="#cccccc"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        self.log_text.config(state=tk.DISABLED)

        # === BOTTOM: Buttons ===
        bottom_frame = tk.Frame(self, bg=BG_COLOR)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        self.btn_start = tk.Button(
            bottom_frame, text="▶ START", command=self._start_worker,
            width=12, bg="#1b5e20", fg="white", relief=tk.FLAT,
            font=("Arial", 12, "bold"), cursor="hand2"
        )
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(
            bottom_frame, text="⏹ STOP", command=self._stop_worker,
            width=12, bg="#b71c1c", fg="white", relief=tk.FLAT,
            font=("Arial", 12, "bold"), cursor="hand2", state=tk.DISABLED
        )
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        tk.Button(
            bottom_frame, text="📁 Open Folder", command=self._open_folder,
            width=12, bg=BUTTON_BG, fg=BUTTON_FG, relief=tk.FLAT,
            font=("Arial", 10), cursor="hand2"
        ).pack(side=tk.LEFT, padx=5)

        # Version label
        tk.Label(bottom_frame, text="v1.0", bg=BG_COLOR, fg=FG_DIM,
                 font=("Arial", 8)).pack(side=tk.RIGHT, padx=5)

    # =========================================================================
    # ACTIONS
    # =========================================================================

    def _test_connection(self):
        """Test kết nối server."""
        url = self.sv_server_url.get().strip()
        if not url:
            messagebox.showwarning("Lỗi", "Nhập Server URL trước!")
            return

        self._log(f"Testing connection: {url}...")

        def _test():
            try:
                import requests
                resp = requests.get(f"{url}/api/status", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    queue = data.get("queue_size", "?")
                    chrome = data.get("chrome_ready", "?")
                    workers = data.get("workers_ready", "?")
                    msg = f"Connected! Queue: {queue}, Chrome: {chrome}, Workers: {workers}"
                    self.after(0, lambda: self._log(msg, "SUCCESS"))
                    self.after(0, lambda: messagebox.showinfo("Kết nối OK", msg))
                else:
                    self.after(0, lambda: self._log(f"Server error: {resp.status_code}", "ERROR"))
            except Exception as e:
                self.after(0, lambda: self._log(f"Connection failed: {e}", "ERROR"))
                self.after(0, lambda: messagebox.showerror("Lỗi kết nối", str(e)))

        threading.Thread(target=_test, daemon=True).start()

    def _upload_excel(self):
        """Upload file Excel."""
        path = filedialog.askopenfilename(
            title="Chọn file Excel",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if not path:
            return

        path = Path(path)
        self._log(f"Loading: {path.name}")

        try:
            from modules.excel_manager import PromptWorkbook

            # Xác định project code từ filename
            code = path.stem.replace("_prompts", "")
            project_dir = VE3_DIR / "PROJECTS" / code
            project_dir.mkdir(parents=True, exist_ok=True)

            # Copy Excel vào project dir
            dest = project_dir / path.name
            if str(path) != str(dest):
                shutil.copy2(str(path), str(dest))

            # Load và hiển thị stats
            wb = PromptWorkbook(str(dest))
            wb.load_or_create()

            scenes = wb.get_scenes()
            chars = wb.get_characters()
            scenes_with_prompt = len([s for s in scenes if s.img_prompt])

            self.excel_path = dest
            self.project_dir = project_dir

            self.lbl_file.config(text=f"File: {path.name}")
            self.lbl_scenes.config(text=f"Scenes: {scenes_with_prompt} (có prompt)")
            self.lbl_chars.config(text=f"Characters: {len(chars)}")
            self.lbl_status.config(text="Status: Sẵn sàng", fg=SUCCESS_COLOR)

            self._log(f"Excel loaded: {scenes_with_prompt} scenes, {len(chars)} characters")

        except Exception as e:
            self._log(f"Excel error: {e}", "ERROR")
            messagebox.showerror("Lỗi", f"Không đọc được Excel:\n{e}")

    def _create_from_srt(self):
        """Tạo Excel từ file SRT qua API (Mode 1)."""
        path = filedialog.askopenfilename(
            title="Chọn file SRT",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )
        if not path:
            return

        # Kiểm tra API key
        api_key = self.config.get("deepseek_api_key", "")
        if not api_key:
            messagebox.showwarning("Thiếu API Key",
                                   "Cần deepseek_api_key trong config/settings.yaml để tạo Excel từ SRT")
            return

        srt_path = Path(path)
        code = srt_path.stem
        project_dir = VE3_DIR / "PROJECTS" / code
        project_dir.mkdir(parents=True, exist_ok=True)

        # Copy SRT
        dest_srt = project_dir / srt_path.name
        if str(srt_path) != str(dest_srt):
            shutil.copy2(str(srt_path), str(dest_srt))

        self._log(f"Tạo Excel từ SRT: {srt_path.name}")
        self.lbl_status.config(text="Status: Đang tạo Excel...", fg=WARN_COLOR)

        def _run_api():
            try:
                from modules.progressive_prompts import ProgressivePromptsGenerator

                excel_path = project_dir / f"{code}_prompts.xlsx"
                gen = ProgressivePromptsGenerator(
                    srt_path=str(dest_srt),
                    output_path=str(excel_path),
                    config=self.config,
                    log_func=lambda msg, level="INFO": self.after(0, lambda m=msg, l=level: self._log(m, l))
                )
                gen.run_all_steps()

                self.excel_path = excel_path
                self.project_dir = project_dir

                # Update GUI
                from modules.excel_manager import PromptWorkbook
                wb = PromptWorkbook(str(excel_path))
                wb.load_or_create()
                scenes = wb.get_scenes()
                chars = wb.get_characters()
                scenes_with_prompt = len([s for s in scenes if s.img_prompt])

                self.after(0, lambda: self.lbl_file.config(text=f"File: {excel_path.name}"))
                self.after(0, lambda: self.lbl_scenes.config(text=f"Scenes: {scenes_with_prompt}"))
                self.after(0, lambda: self.lbl_chars.config(text=f"Characters: {len(chars)}"))
                self.after(0, lambda: self.lbl_status.config(text="Status: Excel tạo xong!", fg=SUCCESS_COLOR))
                self.after(0, lambda: self._log("Excel tạo xong!", "SUCCESS"))

            except Exception as e:
                self.after(0, lambda: self._log(f"SRT→Excel error: {e}", "ERROR"))
                self.after(0, lambda: self.lbl_status.config(text="Status: Lỗi tạo Excel", fg=ACCENT_COLOR))

        threading.Thread(target=_run_api, daemon=True).start()

    def _download_template(self):
        """Save template.xlsx."""
        template_src = VE3_DIR / "templates" / "template.xlsx"
        if not template_src.exists():
            # Tạo nếu chưa có
            from create_template import create_template
            create_template(str(template_src))

        dest = filedialog.asksaveasfilename(
            title="Lưu file Excel mẫu",
            defaultextension=".xlsx",
            initialfile="template.xlsx",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if dest:
            shutil.copy2(str(template_src), dest)
            self._log(f"Template saved: {dest}")
            messagebox.showinfo("OK", f"Đã lưu template:\n{dest}")

    def _start_worker(self):
        """Start worker thread."""
        if not self.excel_path or not self.project_dir:
            messagebox.showwarning("Lỗi", "Upload Excel trước!")
            return

        # Cập nhật config từ GUI
        self.config["local_server_url"] = self.sv_server_url.get().strip()
        self.config["flow_bearer_token"] = self.sv_token.get().strip()
        self.config["flow_project_id"] = self.sv_project_id.get().strip()
        self._save_config()

        if not self.config.get("local_server_url"):
            messagebox.showwarning("Lỗi", "Nhập Server URL!")
            return

        # Clear log
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Reset progress
        self.pb_refs["value"] = 0
        self.pb_scenes["value"] = 0
        self.lbl_refs_count.config(text="0/0")
        self.lbl_scenes_count.config(text="0/0")

        # UI state
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text="Status: Đang chạy...", fg=SUCCESS_COLOR)

        from ve3_worker import VE3Worker

        self.worker = VE3Worker(
            project_dir=str(self.project_dir),
            config=self.config,
            log_func=lambda msg, level="INFO": self.after(0, lambda m=msg, l=level: self._log(m, l)),
            progress_func=lambda *a, **kw: self.after(0, lambda: self._update_progress(*a, **kw))
        )

        def _run():
            result = self.worker.run()
            self.after(0, lambda: self._on_worker_done(result))

        self.worker_thread = threading.Thread(target=_run, daemon=True)
        self.worker_thread.start()
        self._log("Worker started!")

    def _stop_worker(self):
        """Stop worker."""
        if self.worker:
            self.worker.stop()
            self._log("Stopping worker...", "WARN")

    def _on_worker_done(self, result):
        """Callback khi worker xong."""
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

        if result.get("success"):
            self.lbl_status.config(text=f"Status: Hoàn thành {result['completed']}/{result['total']}",
                                   fg=SUCCESS_COLOR)
            self._log(f"DONE: {result['completed']}/{result['total']} ảnh", "SUCCESS")
        else:
            errors = result.get("errors", [])
            err_msg = errors[0] if errors else "Có lỗi"
            self.lbl_status.config(text=f"Status: {err_msg}", fg=ACCENT_COLOR)
            self._log(f"FAILED: {result['completed']}/{result['total']}, errors: {errors}", "ERROR")

    def _open_folder(self):
        """Mở thư mục project."""
        if self.project_dir and self.project_dir.exists():
            os.startfile(str(self.project_dir))
        else:
            projects_dir = VE3_DIR / "PROJECTS"
            projects_dir.mkdir(exist_ok=True)
            os.startfile(str(projects_dir))

    def _update_progress(self, phase, current, total, detail=""):
        """Cập nhật progress bars."""
        if phase == "refs":
            self.pb_refs["maximum"] = max(total, 1)
            self.pb_refs["value"] = current
            self.lbl_refs_count.config(text=f"{current}/{total}")
        elif phase == "scenes":
            self.pb_scenes["maximum"] = max(total, 1)
            self.pb_scenes["value"] = current
            self.lbl_scenes_count.config(text=f"{current}/{total}")

        if detail:
            self.lbl_current.config(text=f"→ {detail}")

    def _log(self, msg: str, level: str = "INFO"):
        """Append log message (thread-safe via self.after)."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Color tag
        tag = level.lower()

        self.log_text.config(state=tk.NORMAL)

        # Add color tags
        if tag not in self.log_text.tag_names():
            colors = {
                "info": "#cccccc",
                "success": SUCCESS_COLOR,
                "warn": WARN_COLOR,
                "error": ACCENT_COLOR,
            }
            self.log_text.tag_configure(tag, foreground=colors.get(tag, "#cccccc"))

        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    app = VE3GUI()
    app.mainloop()


if __name__ == "__main__":
    main()
