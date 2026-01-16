#!/usr/bin/env python3
"""
VE3 Tool - Worker PIC Chrome 2 (Image Generation với Chrome 2)
==============================================================
Script riêng cho Chrome 2, dùng SmartEngine giống run_worker_pic.py
Được gọi từ run_worker_pic_basic_2.py như subprocess.

Usage:
    python run_worker_pic_chrome2.py --excel <path>
"""

import sys
import os
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


def run_chrome2_pic_worker(excel_path: str):
    """
    Chrome 2 worker for image generation.
    Uses SmartEngine like run_worker_pic.py does.
    """
    # Force flush output
    sys.stdout.reconfigure(line_buffering=True)

    print(f"[Chrome2-PIC] Starting worker...", flush=True)

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

    try:
        from modules.smart_engine import SmartEngine

        # Create engine with Chrome 2 settings
        # worker_id=1 để Chrome ở bên PHẢI màn hình
        # chrome_portable=chrome2 để dùng Chrome Portable thứ 2
        engine = SmartEngine(
            worker_id=1,  # Chrome 2 = bên phải
            total_workers=2,  # Chia đôi màn hình
            chrome_portable=chrome2  # Override settings.yaml
        )

        safe_print(f"[Chrome2-PIC] Running SmartEngine...")

        # Run engine - images only, skip video
        result = engine.run(
            excel_path,
            callback=log_callback,
            skip_compose=True,
            skip_video=True
        )

        safe_print(f"[Chrome2-PIC] Done! Result: {result}")

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
