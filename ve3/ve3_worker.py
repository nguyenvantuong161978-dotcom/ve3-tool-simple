#!/usr/bin/env python3
"""
VE3 Simple - Worker tạo ảnh qua server mode

Flow:
1. Load Excel (PromptWorkbook)
2. Tạo reference images (nv/, loc/) qua server
3. Tạo TẤT CẢ scene images (không chia chẵn/lẻ) qua server
4. Tạo thumbnail (nhân vật chính → thumb/)

Usage:
    worker = VE3Worker(project_dir, config, log_func)
    result = worker.run()
"""

import sys
import os
import time
import json
import shutil
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any
from datetime import datetime

# Đảm bảo import modules từ thư mục ve3
VE3_DIR = Path(__file__).parent
sys.path.insert(0, str(VE3_DIR))

from modules.excel_manager import PromptWorkbook, Character, Scene
from modules.google_flow_api import (
    GoogleFlowAPI, GeneratedImage, ImageInput, ImageInputType,
    AspectRatio, ImageModel
)
from modules.server_pool import ServerPool


class VE3Worker:
    """Worker tạo ảnh từ Excel qua server mode."""

    def __init__(
        self,
        project_dir: str,
        config: Dict[str, Any],
        log_func: Callable = None,
        progress_func: Callable = None
    ):
        """
        Args:
            project_dir: Đường dẫn thư mục project (chứa Excel + output)
            config: Dict cấu hình từ settings.yaml
            log_func: Callback log(msg, level) - hiển thị lên GUI
            progress_func: Callback progress(phase, current, total, detail)
        """
        self.project_dir = Path(project_dir)
        self.config = config
        self.log = log_func or (lambda msg, level="INFO": print(f"[{level}] {msg}"))
        self.progress = progress_func or (lambda *a, **kw: None)
        self._stop_flag = False

        # Paths
        self.nv_dir = self.project_dir / "nv"
        self.img_dir = self.project_dir / "img"
        self.thumb_dir = self.project_dir / "thumb"

        # Server config
        self.server_url = config.get("local_server_url", "")
        self.server_list = config.get("local_server_list", [])
        self.bearer_token = config.get("flow_bearer_token", "")
        self.flow_project_id = config.get("flow_project_id", "")
        self.timeout = config.get("flow_timeout", 120)
        self.retry_count = config.get("retry_count", 3)

        # Aspect ratio
        ar_str = config.get("flow_aspect_ratio", "landscape").upper()
        self.aspect_ratio = getattr(AspectRatio, ar_str, AspectRatio.LANDSCAPE)

        # Server pool
        self.pool = None
        self._init_server_pool()

    def _init_server_pool(self):
        """Khởi tạo ServerPool từ config."""
        servers = []
        if self.server_list:
            servers = self.server_list
        elif self.server_url:
            servers = [{"url": self.server_url, "name": "Server-1", "enabled": True}]

        if servers:
            self.pool = ServerPool(servers, log_func=self.log)
            self.pool.refresh_all()
            self.log(f"Server pool: {len(servers)} server(s)")
        else:
            self.log("Không có server URL!", "ERROR")

    def stop(self):
        """Dừng worker."""
        self._stop_flag = True
        self.log("Đang dừng worker...")

    def run(self) -> Dict[str, Any]:
        """
        Pipeline chính: references → scenes → thumbnail.

        Returns:
            Dict kết quả: {success, total, completed, failed, errors}
        """
        result = {"success": False, "total": 0, "completed": 0, "failed": 0, "errors": []}

        if not self.pool:
            result["errors"].append("Không có server URL")
            return result

        # Tìm Excel file
        excel_path = self._find_excel()
        if not excel_path:
            result["errors"].append("Không tìm thấy file Excel trong project")
            return result

        self.log(f"Loading Excel: {excel_path.name}")

        try:
            wb = PromptWorkbook(str(excel_path))
            wb.load_or_create()
        except Exception as e:
            result["errors"].append(f"Lỗi đọc Excel: {e}")
            return result

        # Đọc bearer token từ Excel config nếu chưa có
        if not self.bearer_token:
            self.bearer_token = wb.get_config_value("flow_bearer_token") or ""
        if not self.flow_project_id:
            self.flow_project_id = wb.get_config_value("flow_project_id") or ""

        if not self.bearer_token:
            result["errors"].append("Thiếu bearer token! Nhập trong GUI hoặc sheet config")
            return result

        # Tạo thư mục output
        self.nv_dir.mkdir(parents=True, exist_ok=True)
        self.img_dir.mkdir(parents=True, exist_ok=True)

        # === PHASE 1: References ===
        self.log("=" * 50)
        self.log("PHASE 1: Tạo Reference Images (nhân vật + địa điểm)")
        self.log("=" * 50)
        ref_result = self._generate_references(wb)
        if self._stop_flag:
            result["errors"].append("Đã dừng bởi user")
            return result

        # === PHASE 2: Scenes ===
        self.log("")
        self.log("=" * 50)
        self.log("PHASE 2: Tạo Scene Images")
        self.log("=" * 50)
        scene_result = self._generate_scenes(wb)
        if self._stop_flag:
            result["errors"].append("Đã dừng bởi user")
            return result

        # === PHASE 3: Thumbnail ===
        self.log("")
        self.log("=" * 50)
        self.log("PHASE 3: Tạo Thumbnail")
        self.log("=" * 50)
        self._generate_thumbnail(wb)

        # Tổng kết
        total = ref_result["total"] + scene_result["total"]
        completed = ref_result["completed"] + scene_result["completed"]
        failed = ref_result["failed"] + scene_result["failed"]

        result["success"] = failed == 0 and completed > 0
        result["total"] = total
        result["completed"] = completed
        result["failed"] = failed

        self.log("")
        self.log("=" * 50)
        status = "HOÀN THÀNH" if result["success"] else "CÓ LỖI"
        self.log(f"KẾT QUẢ: {status} - {completed}/{total} ảnh")
        self.log("=" * 50)

        return result

    def _find_excel(self) -> Optional[Path]:
        """Tìm file Excel trong project dir."""
        # Tìm *_prompts.xlsx trước
        for f in self.project_dir.glob("*_prompts.xlsx"):
            if not f.name.startswith("~"):
                return f
        # Fallback: bất kỳ .xlsx
        for f in self.project_dir.glob("*.xlsx"):
            if not f.name.startswith("~"):
                return f
        return None

    # =========================================================================
    # PHASE 1: Reference Images
    # =========================================================================

    def _generate_references(self, wb: PromptWorkbook) -> Dict:
        """Tạo ảnh reference cho nhân vật và địa điểm."""
        result = {"total": 0, "completed": 0, "failed": 0}

        characters = wb.get_characters()
        if not characters:
            self.log("Không có nhân vật/địa điểm trong Excel")
            return result

        # Lọc: chỉ tạo ảnh cho những cái chưa có
        pending = []
        for char in characters:
            if char.is_child:
                self.log(f"  Skip {char.id} (trẻ em)")
                continue
            if char.status and char.status.lower() in ("done", "skip"):
                self.log(f"  Skip {char.id} (status={char.status})")
                continue

            # Xác định output path
            if char.id.lower().startswith("loc"):
                img_path = self.nv_dir / f"{char.id}.png"
            else:
                img_path = self.nv_dir / f"{char.id}.png"

            # Kiểm tra file đã tồn tại và có media_id
            if img_path.exists() and char.media_id:
                self.log(f"  Skip {char.id} (đã có ảnh + media_id)")
                continue

            pending.append((char, img_path))

        result["total"] = len(pending)
        self.log(f"References cần tạo: {len(pending)}/{len(characters)}")

        for i, (char, img_path) in enumerate(pending):
            if self._stop_flag:
                break

            prompt = char.english_prompt or char.vietnamese_prompt or char.name
            if not prompt:
                self.log(f"  [{i+1}/{len(pending)}] {char.id}: SKIP (không có prompt)", "WARN")
                result["failed"] += 1
                continue

            self.log(f"  [{i+1}/{len(pending)}] {char.id}: {prompt[:60]}...")
            self.progress("refs", i + 1, len(pending), char.id)

            success, media_name = self._submit_image(prompt, img_path)

            if success:
                # Cập nhật Excel
                update_data = {"status": "done"}
                if media_name:
                    update_data["media_id"] = media_name
                wb.update_character(char.id, **update_data)
                wb.safe_save()
                result["completed"] += 1
                self.log(f"    → OK (media_id: {media_name[:30] if media_name else 'N/A'})")
            else:
                result["failed"] += 1
                self.log(f"    → FAIL", "WARN")

        return result

    # =========================================================================
    # PHASE 2: Scene Images
    # =========================================================================

    def _generate_scenes(self, wb: PromptWorkbook) -> Dict:
        """Tạo ảnh cho TẤT CẢ scenes."""
        result = {"total": 0, "completed": 0, "failed": 0}

        scenes = wb.get_scenes()
        if not scenes:
            self.log("Không có scenes trong Excel")
            return result

        # Lọc scenes cần tạo
        pending = []
        for scene in scenes:
            if not scene.img_prompt:
                continue
            if scene.status_img and scene.status_img.lower() in ("done", "skip"):
                img_path = self.img_dir / f"scene_{scene.scene_id:03d}.png"
                if img_path.exists():
                    continue

            pending.append(scene)

        result["total"] = len(pending)
        total_scenes = len([s for s in scenes if s.img_prompt])
        self.log(f"Scenes cần tạo: {len(pending)}/{total_scenes}")

        # Load media_ids từ characters cho references
        media_ids = self._load_media_ids(wb)

        for i, scene in enumerate(pending):
            if self._stop_flag:
                break

            scene_id = scene.scene_id
            img_path = self.img_dir / f"scene_{scene_id:03d}.png"
            prompt = scene.img_prompt

            self.log(f"  [{i+1}/{len(pending)}] Scene {scene_id}: {prompt[:60]}...")
            self.progress("scenes", i + 1, len(pending), f"scene_{scene_id:03d}")

            # Build references từ characters_used + location_used
            refs = self._build_references(scene, media_ids)

            success, media_name = self._submit_image(prompt, img_path, refs)

            if success:
                wb.update_scene(scene_id, status_img="done", img_path=str(img_path))
                if media_name:
                    wb.update_scene(scene_id, media_id=media_name)
                wb.safe_save()
                result["completed"] += 1
                self.log(f"    → OK")
            else:
                wb.update_scene(scene_id, status_img="error")
                wb.safe_save()
                result["failed"] += 1
                self.log(f"    → FAIL", "WARN")

        return result

    def _load_media_ids(self, wb: PromptWorkbook) -> Dict[str, str]:
        """Load media_ids từ characters sheet."""
        media_ids = {}
        try:
            characters = wb.get_characters()
            for char in characters:
                if char.media_id:
                    media_ids[char.id] = char.media_id
                    # Cũng map theo filename
                    fname = f"{char.id}.png"
                    media_ids[fname] = char.media_id
        except Exception as e:
            self.log(f"Lỗi load media_ids: {e}", "WARN")
        self.log(f"  Media IDs loaded: {len(media_ids)}")
        return media_ids

    def _build_references(self, scene: Scene, media_ids: Dict[str, str]) -> List[ImageInput]:
        """Build ImageInput references cho scene."""
        refs = []

        # Từ reference_files (JSON list)
        ref_files = []
        if scene.reference_files:
            try:
                ref_files = json.loads(scene.reference_files) if isinstance(scene.reference_files, str) else scene.reference_files
            except (json.JSONDecodeError, TypeError):
                # Thử split by comma
                ref_files = [f.strip() for f in str(scene.reference_files).split(",") if f.strip()]

        for ref_file in ref_files:
            ref_name = ref_file.replace(".png", "").replace(".jpg", "")
            media_id = media_ids.get(ref_file) or media_ids.get(ref_name)
            if media_id:
                refs.append(ImageInput(name=media_id, input_type=ImageInputType.REFERENCE))

        # Fallback: từ characters_used + location_used nếu reference_files trống
        if not refs:
            if scene.characters_used:
                char_ids = [c.strip() for c in str(scene.characters_used).split(",") if c.strip()]
                for cid in char_ids:
                    media_id = media_ids.get(cid) or media_ids.get(f"{cid}.png")
                    if media_id:
                        refs.append(ImageInput(name=media_id, input_type=ImageInputType.REFERENCE))

            if scene.location_used:
                loc_id = scene.location_used.strip()
                media_id = media_ids.get(loc_id) or media_ids.get(f"{loc_id}.png")
                if media_id:
                    refs.append(ImageInput(name=media_id, input_type=ImageInputType.REFERENCE))

        return refs

    # =========================================================================
    # PHASE 3: Thumbnail
    # =========================================================================

    def _generate_thumbnail(self, wb: PromptWorkbook):
        """Tạo thumbnail từ nhân vật chính."""
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

        characters = wb.get_characters()
        if not characters:
            self.log("Không có nhân vật để tạo thumbnail")
            return

        # Lọc bỏ locations
        actual_chars = [c for c in characters if not c.id.lower().startswith("loc") and c.role != "location"]
        if not actual_chars:
            actual_chars = characters

        # Chọn nhân vật chính (protagonist/main, không phải trẻ em)
        selected = None
        for char in actual_chars:
            if char.role and char.role.lower() in ("protagonist", "main") and not char.is_child:
                selected = char
                break

        # Fallback: nhân vật đầu tiên không phải trẻ em
        if not selected:
            for char in actual_chars:
                if not char.is_child:
                    selected = char
                    break

        # Last resort: nhân vật đầu tiên
        if not selected:
            selected = actual_chars[0]

        # Copy ảnh nhân vật vào thumb/
        src_image = self.nv_dir / f"{selected.id}.png"
        if src_image.exists():
            project_code = self.project_dir.name
            dest_image = self.thumb_dir / f"{project_code}.png"
            shutil.copy2(str(src_image), str(dest_image))
            self.log(f"Thumbnail: {selected.id} ({selected.name}) → {dest_image.name}")
        else:
            self.log(f"Ảnh {selected.id}.png chưa tồn tại, bỏ qua thumbnail", "WARN")

    # =========================================================================
    # SERVER COMMUNICATION
    # =========================================================================

    def _submit_image(
        self,
        prompt: str,
        output_path: Path,
        refs: List[ImageInput] = None
    ) -> tuple:
        """
        Gửi prompt tạo ảnh lên server.

        Returns:
            (success: bool, media_name: str or None)
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(self.retry_count):
            if self._stop_flag:
                return False, None

            # Pick server
            server = self.pool.pick_best_server() if self.pool else None
            if not server:
                # Chờ server available
                self.log("  Chờ server available...", "WARN")
                server = self.pool.wait_for_server(timeout=300) if self.pool else None
                if not server:
                    self.log("  Không có server nào available!", "ERROR")
                    return False, None

            try:
                # Tạo API client cho server này
                api = GoogleFlowAPI(
                    bearer_token=self.bearer_token,
                    project_id=self.flow_project_id,
                    timeout=self.timeout,
                    local_server_url=server.url
                )

                # Gọi generate
                success, images, error = api.generate_images(
                    prompt=prompt,
                    count=1,
                    aspect_ratio=self.aspect_ratio,
                    image_inputs=refs or []
                )

                if success and images:
                    # Download/save ảnh
                    img = images[0]
                    filename = output_path.stem  # scene_001 hoặc nv1
                    saved = api.download_image(img, output_path.parent, filename)

                    if saved:
                        self.pool.mark_success(server)
                        return True, img.media_name
                    else:
                        self.log(f"    Download fail (attempt {attempt+1})", "WARN")
                        self.pool.mark_task_failed(server)
                else:
                    self.log(f"    Server error: {error[:100]} (attempt {attempt+1})", "WARN")
                    self.pool.mark_task_failed(server)

            except Exception as e:
                self.log(f"    Exception: {e} (attempt {attempt+1})", "WARN")
                if self.pool and server:
                    self.pool.mark_task_failed(server)

            # Retry delay
            if attempt < self.retry_count - 1:
                delay = 2 * (attempt + 1)
                self.log(f"    Retry sau {delay}s...")
                time.sleep(delay)

        return False, None


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """Chạy worker từ command line."""
    import yaml

    if len(sys.argv) < 2:
        print("Usage: python ve3_worker.py <project_dir>")
        print("  project_dir: Thư mục chứa file Excel")
        sys.exit(1)

    project_dir = sys.argv[1]

    # Load config
    config_path = VE3_DIR / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    worker = VE3Worker(project_dir, config)
    result = worker.run()

    if result["success"]:
        print(f"\nThành công: {result['completed']}/{result['total']} ảnh")
    else:
        print(f"\nCó lỗi: {result['completed']}/{result['total']} ảnh")
        for err in result.get("errors", []):
            print(f"  - {err}")


if __name__ == "__main__":
    main()
