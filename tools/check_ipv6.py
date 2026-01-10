#!/usr/bin/env python3
"""
IPv6 Connectivity Diagnostic Tool
==================================
Kiểm tra IPv6 connectivity trên Windows VM.

Chạy: python tools/check_ipv6.py

Kết quả sẽ cho biết:
- IPv6 có được cấu hình đúng không
- IPv6 có thể ping ra internet không
- Gateway IPv6 có đúng không
- DNS IPv6 có hoạt động không
"""

import subprocess
import socket
import sys
import re
from pathlib import Path


def run_cmd(cmd: str, timeout: int = 10) -> tuple:
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
        return False, "Command timeout"
    except Exception as e:
        return False, str(e)


def check_ipv6_addresses():
    """Check IPv6 addresses on interfaces."""
    print("\n" + "="*60)
    print("1. IPv6 ADDRESSES")
    print("="*60)

    success, output = run_cmd('netsh interface ipv6 show addresses')
    if success:
        # Find global IPv6 addresses (not link-local fe80::)
        global_ips = []
        lines = output.split('\n')
        for line in lines:
            if 'Address' in line:
                match = re.search(r'(2[0-9a-fA-F]{3}:[0-9a-fA-F:]+)', line)
                if match:
                    global_ips.append(match.group(1))

        if global_ips:
            print(f"[OK] Found {len(global_ips)} global IPv6 address(es):")
            for ip in global_ips[:5]:  # Show first 5
                print(f"     - {ip}")
            return True
        else:
            print("[FAIL] No global IPv6 addresses found")
            print("       Only link-local (fe80::) addresses present")
            return False
    else:
        print(f"[FAIL] Could not get IPv6 addresses: {output}")
        return False


def check_ipv6_route():
    """Check IPv6 default route."""
    print("\n" + "="*60)
    print("2. IPv6 GATEWAY/ROUTE")
    print("="*60)

    success, output = run_cmd('netsh interface ipv6 show route')
    if success:
        # Find default route ::/0
        lines = output.split('\n')
        default_gw = None
        for line in lines:
            if '::/0' in line and '2001' in line.lower() or '::' in line:
                # Found default route
                parts = line.split()
                for part in parts:
                    if part.startswith('2') and ':' in part:
                        default_gw = part
                        break

        if default_gw:
            print(f"[OK] Default IPv6 gateway: {default_gw}")
            return True
        else:
            # Check if there's any route
            if '::/0' in output:
                print("[WARN] Default route exists but gateway unclear")
                print("       Run: netsh interface ipv6 show route")
                return True
            else:
                print("[FAIL] No IPv6 default route found")
                print("       Need to add gateway route")
                return False
    else:
        print(f"[FAIL] Could not get IPv6 routes: {output}")
        return False


def check_ipv6_dns():
    """Check if DNS resolves IPv6 addresses."""
    print("\n" + "="*60)
    print("3. IPv6 DNS RESOLUTION")
    print("="*60)

    try:
        # Try to resolve google.com to IPv6
        results = socket.getaddrinfo('google.com', 80, socket.AF_INET6, socket.SOCK_STREAM)
        if results:
            ipv6_addr = results[0][4][0]
            print(f"[OK] google.com resolves to IPv6: {ipv6_addr}")
            return True
        else:
            print("[FAIL] No IPv6 address for google.com")
            return False
    except socket.gaierror as e:
        print(f"[FAIL] DNS resolution failed: {e}")
        print("       This could mean:")
        print("       - DNS server doesn't support IPv6")
        print("       - No IPv6 connectivity at all")
        return False


def check_ipv6_ping():
    """Check if IPv6 can reach internet."""
    print("\n" + "="*60)
    print("4. IPv6 CONNECTIVITY (PING)")
    print("="*60)

    # Try pinging Google's IPv6 DNS
    targets = [
        ("Google DNS", "2001:4860:4860::8888"),
        ("Cloudflare DNS", "2606:4700:4700::1111"),
    ]

    success_count = 0
    for name, ip in targets:
        # Windows ping -6 or ping with IPv6 address
        success, output = run_cmd(f'ping -n 1 -w 3000 {ip}', timeout=5)
        if success and 'Reply from' in output:
            print(f"[OK] Can reach {name} ({ip})")
            success_count += 1
        elif 'General failure' in output:
            print(f"[FAIL] {name}: General failure")
            print("       This means IPv6 is not properly configured on the network")
        elif 'timed out' in output.lower() or 'timeout' in output.lower():
            print(f"[FAIL] {name}: Timeout")
            print("       IPv6 address exists but can't reach internet")
        else:
            print(f"[FAIL] {name}: {output[:100]}")

    return success_count > 0


def check_ipv6_list():
    """Check if ipv6_list.txt exists and has valid addresses."""
    print("\n" + "="*60)
    print("5. IPv6 LIST FILE")
    print("="*60)

    ipv6_file = Path(__file__).parent.parent / "config" / "ipv6_list.txt"

    if not ipv6_file.exists():
        print(f"[FAIL] File not found: {ipv6_file}")
        return False

    with open(ipv6_file, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith('#')]

    if lines:
        print(f"[OK] Found {len(lines)} IPv6 addresses in list")
        print(f"     First: {lines[0]}")
        print(f"     Last:  {lines[-1]}")

        # Extract subnet from addresses
        if lines[0].startswith('2001:'):
            parts = lines[0].split(':')
            if len(parts) >= 4:
                subnet = ':'.join(parts[:4])
                print(f"     Subnet: {subnet}::/56")

        return True
    else:
        print("[FAIL] IPv6 list is empty")
        return False


def suggest_fixes(results: dict):
    """Suggest fixes based on check results."""
    print("\n" + "="*60)
    print("DIAGNOSIS & RECOMMENDATIONS")
    print("="*60)

    if not results['addresses']:
        print("\n[FIX] No IPv6 addresses configured:")
        print("      1. Contact VPS provider to enable IPv6")
        print("      2. Or add IPv6 manually:")
        print('         netsh interface ipv6 add address "Ethernet" 2001:xxx::2')
        return

    if not results['route']:
        print("\n[FIX] No IPv6 gateway configured:")
        print('      netsh interface ipv6 add route ::/0 "Ethernet" GATEWAY_IPv6')
        print("      Replace GATEWAY_IPv6 with your provider's gateway")
        return

    if not results['ping']:
        print("\n[ISSUE] IPv6 configured but can't reach internet")
        print("        Possible causes:")
        print("        1. Wrong gateway address")
        print("        2. ISP doesn't route IPv6 properly")
        print("        3. Firewall blocking IPv6")
        print("\n[CHECK] Verify with your VPS provider:")
        print("        - Is IPv6 enabled on your account?")
        print("        - What is the correct IPv6 gateway?")
        print("        - Is the /56 subnet properly routed?")

    if all(results.values()):
        print("\n[SUCCESS] IPv6 is working correctly!")
        print("          You can enable IPv6 rotation in settings.yaml:")
        print("          ipv6_rotation:")
        print("            enabled: true")


def main():
    print("="*60)
    print("IPv6 CONNECTIVITY DIAGNOSTIC")
    print("="*60)
    print(f"Platform: {sys.platform}")

    if sys.platform != 'win32':
        print("\n[WARN] This script is designed for Windows")
        print("       Some checks may not work on Linux/Mac")

    results = {
        'addresses': check_ipv6_addresses(),
        'route': check_ipv6_route(),
        'dns': check_ipv6_dns(),
        'ping': check_ipv6_ping(),
        'list': check_ipv6_list(),
    }

    suggest_fixes(results)

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for check, passed in results.items():
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {check}")

    all_ok = all(results.values())
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
