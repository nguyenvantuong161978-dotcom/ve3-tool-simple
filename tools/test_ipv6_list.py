#!/usr/bin/env python3
"""
IPv6 List Tester
================
Test tất cả IPv6 trong danh sách để tìm những cái hoạt động.

Chạy với Admin: python tools/test_ipv6_list.py

Kết quả sẽ lưu vào:
- config/ipv6_working.txt: Các IPv6 hoạt động
- config/ipv6_dead.txt: Các IPv6 không hoạt động
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple


def is_admin() -> bool:
    """Check if running as admin."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def run_cmd(cmd: str, timeout: int = 10) -> Tuple[bool, str]:
    """Run command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def get_gateway_for_ipv6(ipv6: str) -> str:
    """Get gateway for IPv6 (::1 in same subnet)."""
    parts = ipv6.split('::')
    if parts:
        return f"{parts[0]}::1"
    return ""


def test_ipv6(ipv6: str, interface: str = "Ethernet") -> bool:
    """
    Test if an IPv6 address works.

    Steps:
    1. Delete old routes
    2. Add new IPv6 address
    3. Set gateway
    4. Ping test
    5. Cleanup
    """
    gateway = get_gateway_for_ipv6(ipv6)
    if not gateway:
        return False

    # Delete old route (ignore errors)
    run_cmd(f'netsh interface ipv6 delete route ::/0 "{interface}"', timeout=5)

    # Add IPv6 address
    run_cmd(f'netsh interface ipv6 add address "{interface}" {ipv6}', timeout=5)

    # Add gateway route
    success, _ = run_cmd(f'netsh interface ipv6 add route ::/0 "{interface}" {gateway}', timeout=5)

    # Wait for route to take effect
    time.sleep(1)

    # Ping test (Google DNS IPv6)
    success, output = run_cmd('ping -n 1 -w 3000 2001:4860:4860::8888', timeout=5)

    # Check if ping succeeded
    is_working = success and 'Reply from' in output

    # Cleanup - remove the address we just added
    run_cmd(f'netsh interface ipv6 delete address "{interface}" {ipv6}', timeout=5)

    return is_working


def load_ipv6_list() -> List[str]:
    """Load IPv6 list from file."""
    ipv6_file = Path(__file__).parent.parent / "config" / "ipv6_list.txt"

    if not ipv6_file.exists():
        print(f"[ERROR] File not found: {ipv6_file}")
        return []

    with open(ipv6_file, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]


def save_results(working: List[str], dead: List[str]):
    """Save test results to files."""
    base_dir = Path(__file__).parent.parent / "config"

    # Save working IPs
    working_file = base_dir / "ipv6_working.txt"
    with open(working_file, 'w') as f:
        f.write("# IPv6 addresses that passed connectivity test\n")
        f.write(f"# Tested: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total working: {len(working)}\n\n")
        for ip in working:
            f.write(f"{ip}\n")
    print(f"\n[SAVED] Working IPs: {working_file}")

    # Save dead IPs
    dead_file = base_dir / "ipv6_dead.txt"
    with open(dead_file, 'w') as f:
        f.write("# IPv6 addresses that failed connectivity test\n")
        f.write(f"# Tested: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total dead: {len(dead)}\n\n")
        for ip in dead:
            f.write(f"{ip}\n")
    print(f"[SAVED] Dead IPs: {dead_file}")


def main():
    print("=" * 60)
    print("IPv6 LIST TESTER")
    print("=" * 60)

    if sys.platform != 'win32':
        print("[ERROR] This script only works on Windows")
        return 1

    if not is_admin():
        print("[ERROR] Please run as Administrator!")
        print("Right-click Command Prompt -> Run as administrator")
        return 1

    # Load IPv6 list
    ipv6_list = load_ipv6_list()
    if not ipv6_list:
        print("[ERROR] No IPv6 addresses to test")
        return 1

    print(f"\nFound {len(ipv6_list)} IPv6 addresses to test")
    print("This will take a few minutes...\n")

    working = []
    dead = []

    for i, ipv6 in enumerate(ipv6_list, 1):
        # Progress
        pct = (i / len(ipv6_list)) * 100
        sys.stdout.write(f"\r[{i}/{len(ipv6_list)}] ({pct:.1f}%) Testing {ipv6}... ")
        sys.stdout.flush()

        if test_ipv6(ipv6):
            working.append(ipv6)
            print("OK")
        else:
            dead.append(ipv6)
            print("FAIL")

        # Small delay between tests
        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total tested: {len(ipv6_list)}")
    print(f"Working: {len(working)} ({len(working)/len(ipv6_list)*100:.1f}%)")
    print(f"Dead: {len(dead)} ({len(dead)/len(ipv6_list)*100:.1f}%)")

    # Save results
    if working or dead:
        save_results(working, dead)

    # Suggest updating ipv6_list.txt
    if working:
        print(f"\n[TIP] To use only working IPs, copy ipv6_working.txt to ipv6_list.txt")

    return 0 if working else 1


if __name__ == '__main__':
    sys.exit(main())
