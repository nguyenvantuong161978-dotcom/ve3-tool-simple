#!/usr/bin/env python3
"""
VE3 Tool - Worker PIC Chrome 2 (Image Generation với Chrome 2)
==============================================================
Script riêng cho Chrome 2, dùng SmartEngine GIỐNG HỆT Chrome 1.
Được gọi từ run_worker_pic_basic_2.py như subprocess.

Chrome 2 dùng:
- chrome_portable_2 (GoogleChromePortable - Copy)
- profile: pic2 (riêng biệt với Chrome 1)
- worker_id=1 (bên PHẢI màn hình)

Usage:
    python run_worker_pic_chrome2.py --excel <path>
"""

import sys
import os
import time
from pathlib import Path

# Add current directory to path
TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))


def load_chrome2_path() -> str:
    """Load chrome_portable_2 from settings.yaml."""
    import yaml

    settings_path = TOOL_DIR / "config" / "settings.yaml"
    if not settings_path.exists():
        return None

    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f) or {}

    chrome2 = settings.get('chrome_portable_2', '')

    # Auto-detect if not configured
    if not chrome2:
        copy_chrome = TOOL_DIR / "GoogleChromePortable - Copy" / "GoogleChromePortable.exe"
        if copy_chrome.exists():
            chrome2 = str(copy_chrome)

    return chrome2


def ensure_profile_exists():
    """Tạo profile pic2 nếu chưa có."""
    profiles_dir = TOOL_DIR / "chrome_profiles"
    pic2_dir = profiles_dir / "pic2"

    if not pic2_dir.exists():
        profiles_dir.mkdir(exist_ok=True)
        pic2_dir.mkdir(exist_ok=True)
        print(f"[Chrome2-PIC] Created profile: {pic2_dir}", flush=True)

    return "pic2"


def run_chrome2_pic_worker(excel_path: str):
    """
    Chrome 2 worker for image generation.
    Uses SmartEngine GIỐNG HỆT Chrome 1 - chỉ khác chrome_portable và profile.
    """
    # Force UTF-8 encoding và flush output
    sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    print(f"[Chrome2-PIC] Starting worker...", flush=True)

    # Đợi Chrome 1 khởi động trước
    wait_time = 10
    print(f"[Chrome2-PIC] Waiting {wait_time}s for Chrome 1 to start...", flush=True)
    time.sleep(wait_time)

    chrome2 = load_chrome2_path()
    if not chrome2:
        print(f"[Chrome2-PIC] ERROR: chrome_portable_2 not configured!", flush=True)
        return

    print(f"[Chrome2-PIC] Chrome: {chrome2}", flush=True)
    print(f"[Chrome2-PIC] Excel: {excel_path}", flush=True)

    # Safe print function
    def safe_print(msg):
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode('ascii', 'replace').decode('ascii'), flush=True)

    def log_callback(msg, level="INFO"):
        safe_print(f"[Chrome2-PIC] {msg}")

    # Tạo profile pic2 nếu chưa có
    profile_name = ensure_profile_exists()

    try:
        from modules.smart_engine import SmartEngine

        # Create SmartEngine với:
        # - chrome_portable = chrome_portable_2 (Chrome khác)
        # - assigned_profile = "pic2" (profile riêng)
        # - worker_id = 1 (bên PHẢI màn hình)
        # - total_workers = 2 (chia đôi màn hình)
        engine = SmartEngine(
            assigned_profile=profile_name,
            worker_id=1,  # Chrome 2 = bên PHẢI
            total_workers=2,  # Chia đôi màn hình
            chrome_portable=chrome2  # Override settings.yaml
        )

        # Override log function
        original_log = engine.log
        def custom_log(msg, level="INFO"):
            safe_print(f"[Chrome2-PIC] {msg}")
        engine.log = custom_log

        safe_print(f"[Chrome2-PIC] SmartEngine initialized!")
        safe_print(f"[Chrome2-PIC]   Profile: {profile_name}")
        safe_print(f"[Chrome2-PIC]   Chrome: {chrome2}")
        safe_print(f"[Chrome2-PIC]   Worker ID: 1 (right side)")

        # Run engine - IMAGES ONLY
        # skip_compose=True: không ghép video
        # skip_video=True: không tạo video
        # skip_references=True: Chrome 1 đã tạo characters/locations
        safe_print(f"\n[Chrome2-PIC] Running SmartEngine...")

        result = engine.run(
            excel_path,
            callback=log_callback,
            skip_compose=True,
            skip_video=True,
            skip_references=True  # Chrome 1 tạo nv/loc, Chrome 2 chỉ tạo scenes
        )

        safe_print(f"\n[Chrome2-PIC] Done! Result: {result}")

    except Exception as e:
        safe_print(f"[Chrome2-PIC] ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='VE3 Worker PIC Chrome 2')
    parser.add_argument('--excel', type=str, required=True, help='Excel path')
    args = parser.parse_args()

    run_chrome2_pic_worker(args.excel)


if __name__ == "__main__":
    main()
