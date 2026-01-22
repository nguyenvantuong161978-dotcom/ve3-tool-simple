"""
Test script: Kill Chrome theo portable path

Mục đích: Verify logic kill chỉ 1 Chrome worker, không kill all
"""
import subprocess
import time
import sys

def list_chrome_processes():
    """List tất cả Chrome processes với commandline và PID"""
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'commandline,processid'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            chrome_procs = []
            for line in lines[1:]:  # Skip header
                if 'GoogleChromePortable' in line and 'processid' not in line.lower():
                    parts = line.strip().split()
                    if parts and parts[-1].isdigit():
                        pid = parts[-1]
                        is_copy = 'Copy' in line
                        chrome_procs.append({
                            'pid': pid,
                            'is_chrome2': is_copy,
                            'cmdline': line[:100]
                        })
            return chrome_procs
        return []
    except Exception as e:
        print(f"Error listing Chrome: {e}")
        return []

def kill_chrome_by_portable_path(worker_id: int):
    """Kill Chrome theo portable path của worker"""
    portable_marker = 'GoogleChromePortable - Copy' if worker_id == 2 else 'GoogleChromePortable'
    # Không chứa "Copy" nếu là worker 1
    if worker_id == 1:
        portable_marker = 'GoogleChromePortable'
        # Exclude "Copy"
        exclude_marker = 'Copy'
    else:
        exclude_marker = None

    print(f"\n[KILL] Worker {worker_id} - Tìm Chrome với '{portable_marker}'...")

    try:
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='chrome.exe'", 'get', 'commandline,processid'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            killed_count = 0
            for line in lines:
                # Check marker
                if portable_marker in line:
                    # Worker 1: exclude "Copy"
                    if worker_id == 1 and exclude_marker and exclude_marker in line:
                        continue

                    parts = line.strip().split()
                    if parts and parts[-1].isdigit():
                        pid = parts[-1]
                        subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True, timeout=5)
                        print(f"   Killed PID {pid}")
                        killed_count += 1

            print(f"   → Killed {killed_count} Chrome processes")
            return killed_count > 0
        return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

def main():
    print("="*60)
    print("TEST: Kill Chrome Worker (không kill all)")
    print("="*60)

    # 1. List Chrome hiện tại
    print("\n[1] Chrome processes trước khi test:")
    procs = list_chrome_processes()
    if not procs:
        print("   → Không có Chrome Portable nào đang chạy!")
        print("\n   Vui lòng:")
        print("   1. Mở Chrome 1: GoogleChromePortable/GoogleChromePortable.exe")
        print("   2. Mở Chrome 2: GoogleChromePortable - Copy/GoogleChromePortable.exe")
        print("   3. Chạy lại script này")
        return

    print(f"   → Tìm thấy {len(procs)} Chrome processes:")
    for p in procs:
        label = "Chrome 2 (Copy)" if p['is_chrome2'] else "Chrome 1"
        print(f"      - {label}: PID {p['pid']}")

    chrome1_count = sum(1 for p in procs if not p['is_chrome2'])
    chrome2_count = sum(1 for p in procs if p['is_chrome2'])
    print(f"\n   → Chrome 1: {chrome1_count} processes")
    print(f"   → Chrome 2: {chrome2_count} processes")

    # 2. Hỏi user muốn kill worker nào
    print("\n[2] Test kill:")
    print("   1 = Kill Chrome 1")
    print("   2 = Kill Chrome 2")
    choice = input("   Chọn worker để kill (1 hoặc 2): ").strip()

    if choice not in ['1', '2']:
        print("   → Hủy test")
        return

    worker_id = int(choice)

    # 3. Kill Chrome theo worker
    kill_chrome_by_portable_path(worker_id)
    print("\n   Đợi 3s...")
    time.sleep(3)

    # 4. List lại Chrome sau khi kill
    print("\n[3] Chrome processes sau khi kill:")
    procs_after = list_chrome_processes()

    if not procs_after:
        print("   → KHÔNG CÒN Chrome nào (FAIL - killed all!)")
    else:
        print(f"   → Còn {len(procs_after)} Chrome processes:")
        for p in procs_after:
            label = "Chrome 2 (Copy)" if p['is_chrome2'] else "Chrome 1"
            print(f"      - {label}: PID {p['pid']}")

        chrome1_after = sum(1 for p in procs_after if not p['is_chrome2'])
        chrome2_after = sum(1 for p in procs_after if p['is_chrome2'])

        print(f"\n   → Chrome 1: {chrome1_after} processes")
        print(f"   → Chrome 2: {chrome2_after} processes")

        # Verify
        print("\n[RESULT]")
        if worker_id == 1:
            if chrome1_after == 0 and chrome2_after > 0:
                print("   ✓ PASS: Chrome 1 đã kill, Chrome 2 còn sống")
            else:
                print("   ✗ FAIL: Logic kill không đúng")
        else:
            if chrome2_after == 0 and chrome1_after > 0:
                print("   ✓ PASS: Chrome 2 đã kill, Chrome 1 còn sống")
            else:
                print("   ✗ FAIL: Logic kill không đúng")

if __name__ == '__main__':
    main()