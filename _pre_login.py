#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - PRE-LOGIN Script (v1.0.115) - Visible CMD Window

Script riêng để:
1. Xóa Chrome data
2. Login Chrome 1
3. Login Chrome 2
4. Lưu account vào Excel

Chạy TRƯỚC khi start các Chrome workers.
"""

import sys
import os
import shutil
from pathlib import Path

# Fix Unicode encoding for Windows CMD
if sys.platform == 'win32':
    os.system('chcp 65001 > nul 2>&1')  # UTF-8 code page
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

def main():
    print("\n" + "="*60)
    print("[PRE-LOGIN] Starting pre-login process...")
    print("="*60)

    LOCAL_PROJECTS = TOOL_DIR / "PROJECTS"

    # Tìm project pending đầu tiên (có Excel, 0 ảnh)
    if not LOCAL_PROJECTS.exists():
        print("[PRE-LOGIN] No PROJECTS folder - creating it")
        LOCAL_PROJECTS.mkdir(parents=True, exist_ok=True)

    pending_project = None
    for item in LOCAL_PROJECTS.iterdir():
        if not item.is_dir():
            continue
        code = item.name
        excel_path = item / f"{code}_prompts.xlsx"
        img_dir = item / "img"

        # Chỉ xử lý project có Excel
        if not excel_path.exists():
            print(f"  {code}: No Excel yet, skip")
            continue

        # Đếm số ảnh
        img_count = 0
        if img_dir.exists():
            img_count = len(list(img_dir.glob("*.png"))) + len(list(img_dir.glob("*.jpg")))

        print(f"  {code}: {img_count} images")

        # Nếu 0 ảnh → cần login
        if img_count == 0:
            pending_project = (code, item, excel_path)
            break

    if not pending_project:
        print("\n[PRE-LOGIN] No pending project with 0% images")
        print("[PRE-LOGIN] Skipping login - Chrome already has session")
        print("="*60)
        input("\nPress Enter to close...")
        return

    code, project_dir, excel_path = pending_project
    print(f"\n[PRE-LOGIN] Found pending project: {code}")

    # Import google_login functions
    try:
        from google_login import (
            extract_channel_from_machine_code, get_current_account_for_channel,
            save_account_to_excel, login_google_chrome, detect_machine_code
        )
    except ImportError as e:
        print(f"[PRE-LOGIN] Import error: {e}")
        input("\nPress Enter to close...")
        return

    # v1.0.117: Dùng machine_code từ folder path (AR8-T1), KHÔNG phải project code (AR8-0003)
    machine_code = detect_machine_code()
    channel = extract_channel_from_machine_code(machine_code)
    print(f"[PRE-LOGIN] Machine code: {machine_code}, Channel: {channel}")

    # Lấy account từ Google Sheet
    print("[PRE-LOGIN] Getting account from Google Sheet...")
    current_account = get_current_account_for_channel(channel, machine_code=machine_code)

    if not current_account:
        print("[PRE-LOGIN] ERROR: No account found in sheet!")
        input("\nPress Enter to close...")
        return

    print(f"[PRE-LOGIN] Account: {current_account['id']}")

    # Xóa Chrome data
    print("\n[PRE-LOGIN] Clearing Chrome data...")
    chrome1_data = TOOL_DIR / "GoogleChromePortable" / "Data" / "profile"
    chrome2_data = TOOL_DIR / "GoogleChromePortable - Copy" / "Data" / "profile"

    for data_path in [chrome1_data, chrome2_data]:
        if data_path.exists():
            print(f"  Clearing: {data_path.parent.parent.name}")
            first_run = data_path / "First Run"
            for item in data_path.iterdir():
                if item.name == "First Run":
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink()
                except Exception as e:
                    print(f"    Cannot delete {item.name}: {e}")
            if not first_run.exists():
                first_run.touch()

    print("[PRE-LOGIN] Chrome data cleared!")

    # Login Chrome 1
    chrome1_exe = str(TOOL_DIR / "GoogleChromePortable" / "GoogleChromePortable.exe")
    chrome2_exe = str(TOOL_DIR / "GoogleChromePortable - Copy" / "GoogleChromePortable.exe")

    print("\n[PRE-LOGIN] === LOGIN CHROME 1 ===")
    result1 = login_google_chrome(current_account, chrome_portable=chrome1_exe, worker_id=0)
    print(f"[PRE-LOGIN] Chrome 1 login: {'SUCCESS' if result1 else 'FAILED'}")

    print("\n[PRE-LOGIN] === LOGIN CHROME 2 ===")
    result2 = login_google_chrome(current_account, chrome_portable=chrome2_exe, worker_id=1)
    print(f"[PRE-LOGIN] Chrome 2 login: {'SUCCESS' if result2 else 'FAILED'}")

    # Lưu account vào Excel
    print(f"\n[PRE-LOGIN] Saving account to Excel: {excel_path.name}")
    save_account_to_excel(
        str(excel_path),
        channel,
        current_account['index'],
        current_account['id']
    )

    print("\n" + "="*60)
    print("[PRE-LOGIN] DONE! Both Chrome logged in.")
    print("="*60)

    # Tự động đóng sau 3 giây
    import time
    print("\nClosing in 3 seconds...")
    time.sleep(3)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[PRE-LOGIN] ERROR: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to close...")
