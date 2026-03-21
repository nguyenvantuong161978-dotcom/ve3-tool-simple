"""
Distributed Task Queue - Quản lý claim/release projects giữa nhiều VM.

Cơ chế:
- Mỗi project trên master có thể được "claim" bởi 1 VM duy nhất
- Claim = tạo file _CLAIMED trong thư mục project
- Race condition: ghi → đợi → đọc lại → verify
- Timeout: VM chết → _CLAIMED quá hạn → tự giải phóng

Sử dụng:
    from modules.task_queue import TaskQueue

    tq = TaskQueue(master_projects_path, vm_id="AR8-T1")
    project = tq.claim_next()  # Lấy 1 project chưa ai claim
    if project:
        # Làm việc với project
        tq.release(project)    # Xong → giải phóng
"""

import os
import time
import random
import socket
from pathlib import Path
from typing import Optional, List, Callable
from datetime import datetime


CLAIMED_FILE = "_CLAIMED"
CLAIM_TIMEOUT_HOURS = 8  # VM chết → giải phóng sau 8 giờ


def _log_default(msg: str, level: str = "INFO"):
    """Default log function."""
    print(f"  [{level}] {msg}")


class TaskQueue:
    """Distributed task queue dùng file-based claiming."""

    def __init__(
        self,
        master_projects: str,
        vm_id: str,
        visual_path: str = None,
        timeout_hours: float = CLAIM_TIMEOUT_HOURS,
        log: Callable = None,
    ):
        """
        Args:
            master_projects: Đường dẫn MASTER PROJECTS (e.g., Z:\\AUTO\\ve3-tool-simple\\PROJECTS)
            vm_id: ID của VM này (e.g., "AR8-T1")
            visual_path: Đường dẫn VISUAL folder để check done (e.g., Z:\\AUTO\\visual)
            timeout_hours: Sau bao nhiêu giờ thì coi VM đã chết
            log: Hàm log
        """
        self.master_projects = Path(master_projects)
        self.vm_id = vm_id
        self.visual_path = Path(visual_path) if visual_path else None
        self.timeout_hours = timeout_hours
        self.log = log or _log_default
        self.hostname = socket.gethostname()

    def scan_available(self) -> List[str]:
        """
        Scan tất cả projects chưa được claim.

        Returns:
            Danh sách project codes available
        """
        available = []

        if not self.master_projects.exists():
            return available

        try:
            for item in self.master_projects.iterdir():
                if not item.is_dir():
                    continue

                code = item.name
                claimed_file = item / CLAIMED_FILE

                # Kiểm tra có SRT không (project hợp lệ)
                srt_files = list(item.glob("*.srt"))
                if not srt_files:
                    continue

                # Đã có trong visual → đã xong
                if self._is_in_visual(code):
                    continue

                # Kiểm tra _CLAIMED
                if claimed_file.exists():
                    # Check timeout
                    if self._is_claim_expired(claimed_file):
                        self.log(f"[QUEUE] {code}: claim expired, giải phóng", "WARN")
                        self._remove_claimed(claimed_file)
                    else:
                        continue  # Đã có VM khác claim

                available.append(code)
        except Exception as e:
            self.log(f"[QUEUE] Lỗi scan: {e}", "ERROR")

        return sorted(available)

    def claim_next(self, preferred_channel: str = None) -> Optional[str]:
        """
        Claim project tiếp theo chưa ai lấy.

        Args:
            preferred_channel: Channel ưu tiên (e.g., "AR8"). Lấy channel này trước,
                               nếu hết thì lấy channel khác.

        Returns:
            Project code nếu claim thành công, None nếu không có
        """
        available = self.scan_available()
        if not available:
            self.log(f"[QUEUE] Không có project nào available")
            return None

        # Sắp xếp: ưu tiên channel của mình trước
        if preferred_channel:
            own_channel = [c for c in available if c.startswith(preferred_channel)]
            other_channel = [c for c in available if not c.startswith(preferred_channel)]
            ordered = own_channel + other_channel
        else:
            ordered = available

        # Thử claim từng project
        for code in ordered:
            if self.claim(code):
                return code

        self.log(f"[QUEUE] Không claim được project nào (tất cả đã bị lấy)")
        return None

    def claim(self, code: str) -> bool:
        """
        Claim 1 project cụ thể.

        Flow:
        1. Ghi file _CLAIMED với VM_ID + timestamp
        2. Đợi random 2-4 giây (tránh race condition đồng bộ)
        3. Đọc lại _CLAIMED → verify là mình

        Returns:
            True nếu claim thành công
        """
        project_dir = self.master_projects / code
        claimed_file = project_dir / CLAIMED_FILE

        if not project_dir.exists():
            return False

        # Đã có _CLAIMED → skip
        if claimed_file.exists() and not self._is_claim_expired(claimed_file):
            return False

        try:
            # Bước 1: Ghi _CLAIMED
            claim_content = self._make_claim_content()
            claimed_file.write_text(claim_content, encoding='utf-8')

            # Bước 2: Đợi random 2-4 giây
            wait_time = 2 + random.random() * 2
            time.sleep(wait_time)

            # Bước 3: Đọc lại và verify
            try:
                read_back = claimed_file.read_text(encoding='utf-8').strip()
                first_line = read_back.split('\n')[0].strip()
            except Exception:
                # Không đọc được → fail
                self.log(f"[QUEUE] {code}: không đọc lại được _CLAIMED", "WARN")
                return False

            if first_line == self.vm_id:
                self.log(f"[QUEUE] CLAIMED: {code} → {self.vm_id}")
                return True
            else:
                # VM khác đã ghi đè
                self.log(f"[QUEUE] {code}: đã bị {first_line} claim trước", "INFO")
                return False

        except Exception as e:
            self.log(f"[QUEUE] Lỗi claim {code}: {e}", "ERROR")
            return False

    def release(self, code: str) -> bool:
        """
        Giải phóng claim sau khi xong việc.
        Thường gọi sau khi copy visual về master.

        Returns:
            True nếu release thành công
        """
        claimed_file = self.master_projects / code / CLAIMED_FILE
        return self._remove_claimed(claimed_file)

    def is_claimed_by_me(self, code: str) -> bool:
        """Check xem project có được claim bởi VM này không."""
        claimed_file = self.master_projects / code / CLAIMED_FILE
        if not claimed_file.exists():
            return False
        try:
            content = claimed_file.read_text(encoding='utf-8').strip()
            first_line = content.split('\n')[0].strip()
            return first_line == self.vm_id
        except Exception:
            return False

    def get_my_claims(self) -> List[str]:
        """Lấy danh sách projects mà VM này đang claim."""
        claims = []
        if not self.master_projects.exists():
            return claims

        try:
            for item in self.master_projects.iterdir():
                if item.is_dir() and self.is_claimed_by_me(item.name):
                    claims.append(item.name)
        except Exception:
            pass

        return sorted(claims)

    def cleanup_stale_claims(self) -> List[str]:
        """
        Dọn dẹp claims quá hạn (VM chết).

        Returns:
            Danh sách projects đã được giải phóng
        """
        released = []
        if not self.master_projects.exists():
            return released

        try:
            for item in self.master_projects.iterdir():
                if not item.is_dir():
                    continue
                claimed_file = item / CLAIMED_FILE
                if claimed_file.exists() and self._is_claim_expired(claimed_file):
                    self.log(f"[QUEUE] Timeout: {item.name} → giải phóng", "WARN")
                    self._remove_claimed(claimed_file)
                    released.append(item.name)
        except Exception as e:
            self.log(f"[QUEUE] Lỗi cleanup: {e}", "ERROR")

        return released

    def get_status(self) -> dict:
        """
        Lấy trạng thái tổng quan của queue.

        Returns:
            {
                "total": int,
                "available": int,
                "claimed": {"VM_ID": [codes]},
                "expired": int,
            }
        """
        status = {
            "total": 0,
            "available": 0,
            "claimed": {},
            "expired": 0,
        }

        if not self.master_projects.exists():
            return status

        try:
            for item in self.master_projects.iterdir():
                if not item.is_dir():
                    continue
                # Kiểm tra có SRT
                srt_files = list(item.glob("*.srt"))
                if not srt_files:
                    continue

                if self._is_in_visual(item.name):
                    continue

                status["total"] += 1
                claimed_file = item / CLAIMED_FILE

                if not claimed_file.exists():
                    status["available"] += 1
                elif self._is_claim_expired(claimed_file):
                    status["expired"] += 1
                else:
                    vm_id = self._read_claim_vm_id(claimed_file)
                    if vm_id:
                        if vm_id not in status["claimed"]:
                            status["claimed"][vm_id] = []
                        status["claimed"][vm_id].append(item.name)
        except Exception:
            pass

        return status

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _make_claim_content(self) -> str:
        """Tạo nội dung file _CLAIMED."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{self.vm_id}\n{timestamp}\n{self.hostname}\n"

    def _is_claim_expired(self, claimed_file: Path) -> bool:
        """Check xem claim đã quá hạn chưa."""
        try:
            content = claimed_file.read_text(encoding='utf-8').strip()
            lines = content.split('\n')
            if len(lines) < 2:
                return True  # File không hợp lệ → coi như expired

            timestamp_str = lines[1].strip()
            claim_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            elapsed_hours = (datetime.now() - claim_time).total_seconds() / 3600

            return elapsed_hours > self.timeout_hours
        except Exception:
            return True  # Không parse được → coi như expired

    def _read_claim_vm_id(self, claimed_file: Path) -> Optional[str]:
        """Đọc VM ID từ file _CLAIMED."""
        try:
            content = claimed_file.read_text(encoding='utf-8').strip()
            first_line = content.split('\n')[0].strip()
            return first_line if first_line else None
        except Exception:
            return None

    def _is_in_visual(self, code: str) -> bool:
        """Check xem project đã có trong visual chưa."""
        if not self.visual_path:
            return False
        try:
            visual_dir = self.visual_path / code
            return visual_dir.exists() and any(visual_dir.iterdir())
        except Exception:
            return False

    def _remove_claimed(self, claimed_file: Path) -> bool:
        """Xóa file _CLAIMED."""
        try:
            if claimed_file.exists():
                os.unlink(str(claimed_file))
            return True
        except Exception as e:
            self.log(f"[QUEUE] Không xóa được _CLAIMED: {e}", "WARN")
            return False
