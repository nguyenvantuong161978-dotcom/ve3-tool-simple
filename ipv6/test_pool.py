#!/usr/bin/env python3
"""
Test script cho IPv6 Dynamic Pool.
====================================

Chay:
    python -m ipv6.test_pool              # Test tat ca
    python -m ipv6.test_pool --connect    # Chi test ket noi MikroTik
    python -m ipv6.test_pool --pool       # Chi test pool operations
    python -m ipv6.test_pool --rotate     # Test rotate flow (403 simulation)
    python -m ipv6.test_pool --reset      # Reset pool (xoa tat ca IP)
    python -m ipv6.test_pool --status     # Xem trang thai pool

Config: ipv6/config_test.json (tao tu dong neu chua co)
"""

import sys
import json
import time
import argparse
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ipv6.mikrotik_api import MikroTikAPI
from ipv6.ipv6_pool import IPv6Pool


# =========================================================================
# CONFIG
# =========================================================================

CONFIG_FILE = Path(__file__).parent / "config_test.json"

DEFAULT_CONFIG = {
    "mikrotik": {
        "host": "192.168.88.1",
        "username": "admin",
        "password": "",
        "interface": "ether1",
        "prefix": "2001:ee0:4f89:30",
        "subnet_start": 101,
        "subnet_end": 255,
        "pool_min": 3,
        "pool_max": 20,
    }
}


def load_config() -> dict:
    """Load config tu file, tao default neu chua co."""
    if not CONFIG_FILE.exists():
        print(f"[CONFIG] Tao file config mau: {CONFIG_FILE}")
        print(f"[CONFIG] HAY SUA LAI THONG TIN TRUOC KHI CHAY!")
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        print(f"\n{'='*60}")
        print(f"File: {CONFIG_FILE}")
        print(f"{'='*60}")
        print(json.dumps(DEFAULT_CONFIG, indent=2))
        print(f"{'='*60}")
        print(f"\nSua xong → chay lai script nay")
        sys.exit(0)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# =========================================================================
# TEST FUNCTIONS
# =========================================================================

def test_connection(config: dict):
    """Test ket noi MikroTik REST API."""
    print("\n" + "=" * 60)
    print("TEST 1: KET NOI MIKROTIK")
    print("=" * 60)

    mk_cfg = config["mikrotik"]
    api = MikroTikAPI(
        host=mk_cfg["host"],
        username=mk_cfg["username"],
        password=mk_cfg["password"],
        interface=mk_cfg["interface"],
        prefix=mk_cfg["prefix"],
        subnet_start=mk_cfg.get("subnet_start", 0x52),
        subnet_end=mk_cfg.get("subnet_end", 0xFF),
    )

    # Test connection
    ok = api.test_connection()
    print(f"\nKet noi: {'OK' if ok else 'THAT BAI'}")

    if ok:
        # List current IPv6 addresses
        addrs = api.list_ipv6_addresses()
        print(f"\nIPv6 addresses hien tai ({len(addrs)}):")
        for addr in addrs:
            print(f"  {addr.get('.id', '?')} | {addr.get('address', '?')} | {addr.get('interface', '?')}")

    return ok


def test_pool_operations(config: dict):
    """Test pool add/get/release/burn."""
    print("\n" + "=" * 60)
    print("TEST 2: POOL OPERATIONS")
    print("=" * 60)

    from ipv6 import create_pool
    pool = create_pool(config)

    # Init pool
    ok = pool.init()
    if not ok:
        print("[!] Pool init failed - co the chua co IP nao")
        print("[*] Thu add IP moi...")

    # Status
    status = pool.get_status()
    print(f"\nPool status: {json.dumps(status, indent=2)}")

    # Get IP
    print("\n--- GET IP ---")
    ip1 = pool.get_ip()
    if ip1:
        print(f"Got IP: {ip1}")
    else:
        print("Khong lay duoc IP!")
        return

    ip2 = pool.get_ip()
    if ip2:
        print(f"Got IP: {ip2}")

    # Status
    status = pool.get_status()
    print(f"\nPool status: {json.dumps(status, indent=2)}")

    # Release IP 1
    print("\n--- RELEASE IP ---")
    pool.release_ip(ip1)
    print(f"Released: {ip1}")

    # Burn IP 2
    if ip2:
        print("\n--- BURN IP (simulate 403) ---")
        pool.burn_ip(ip2, reason="test_403")
        print(f"Burned: {ip2}")

    # Final status
    status = pool.get_status()
    print(f"\nFinal pool status: {json.dumps(status, indent=2)}")


def test_rotate_flow(config: dict):
    """Test rotate flow - mo phong 403 lien tiep."""
    print("\n" + "=" * 60)
    print("TEST 3: ROTATE FLOW (403 SIMULATION)")
    print("=" * 60)

    from ipv6 import create_pool
    pool = create_pool(config)
    pool.init()

    # Simulate: lay IP → dung → bi 403 → doi IP moi
    current_ip = pool.get_ip()
    if not current_ip:
        print("Khong co IP de test!")
        return

    print(f"\nBat dau voi: {current_ip}")

    for i in range(3):
        print(f"\n--- Vong {i+1}: 403 detected! ---")
        time.sleep(1)

        new_ip = pool.rotate_ip(current_ip, reason=f"403_test_{i+1}")
        if new_ip:
            print(f"Doi thanh cong: {current_ip} → {new_ip}")
            current_ip = new_ip
        else:
            print(f"HET IP! Khong doi duoc nua!")
            break

    # Release IP cuoi
    if current_ip:
        pool.release_ip(current_ip)

    # Status
    status = pool.get_status()
    print(f"\nFinal status: {json.dumps(status, indent=2)}")


def show_status(config: dict):
    """Hien thi trang thai pool hien tai."""
    print("\n" + "=" * 60)
    print("POOL STATUS")
    print("=" * 60)

    from ipv6 import create_pool
    pool = create_pool(config)
    pool._load_pool()

    status = pool.get_status()
    print(f"\nTong quan:")
    print(f"  Available:  {status['available']}")
    print(f"  In use:     {status['in_use']}")
    print(f"  In pool:    {status['total']}")
    print(f"  Burned:     {status.get('burned_total', 0)}")
    print(f"  Range:      {status.get('range_remaining', '?')} / {status.get('range_total', '?')} con dung duoc")

    print(f"\nChi tiet:")
    for entry in pool.pool:
        status_emoji = {"available": "[v]", "in_use": "[>]", "burned": "[x]", "cooldown": "[~]"}
        s = entry.get("status", "?")
        icon = status_emoji.get(s, "[?]")
        print(f"  {icon} {entry['address']} (subnet {entry.get('subnet_hex', '??')}) - {s}")
        if s == "burned":
            print(f"      Reason: {entry.get('burn_reason', '?')}")


def reset_pool(config: dict):
    """Reset pool - xoa tat ca IP khoi router."""
    print("\n" + "=" * 60)
    print("RESET POOL")
    print("=" * 60)

    confirm = input("Ban co chac muon RESET pool? (yes/no): ")
    if confirm.lower() != "yes":
        print("Huy reset")
        return

    from ipv6 import create_pool
    pool = create_pool(config)
    pool.init()
    pool.reset_pool()
    print("Da reset pool!")


def auto_detect(config: dict):
    """
    Tu dong detect interface, prefix, subnet range tu MikroTik router.
    Chi can host + username + password.
    """
    print("\n" + "=" * 60)
    print("AUTO DETECT - Tu dong lay thong tin tu router")
    print("=" * 60)

    mk_cfg = config.get("mikrotik", {})
    host = mk_cfg.get("host", "192.168.88.1")
    username = mk_cfg.get("username", "admin")
    password = mk_cfg.get("password", "")

    if not password:
        print("[!] Chua co password trong config!")
        print(f"    Sua file: {CONFIG_FILE}")
        return

    print(f"\nKet noi toi {host} (user: {username})...")

    # Test connection truoc - thu HTTPS roi HTTP
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    session.auth = (username, password)
    session.verify = False

    # Thu HTTPS truoc, neu fail thu HTTP
    base_url = None
    for scheme in ["https", "http"]:
        try:
            test_url = f"{scheme}://{host}/rest/system/identity"
            print(f"  Thu {scheme.upper()}...", end=" ")
            resp = session.get(test_url, timeout=5)
            if resp.status_code == 200:
                base_url = f"{scheme}://{host}/rest"
                identity = resp.json().get("name", "unknown")
                print(f"OK! Router: {identity}")
                break
            elif resp.status_code == 401:
                print(f"SAI MAT KHAU!")
                print("[x] Kiem tra lai username/password")
                return
            else:
                print(f"HTTP {resp.status_code}")
        except requests.exceptions.ConnectionError:
            print(f"khong ket noi duoc")
        except Exception as e:
            print(f"loi: {e}")

    if not base_url:
        print(f"\n[x] Khong ket noi duoc toi {host} (ca HTTPS va HTTP)")
        print(f"    Kiem tra:")
        print(f"    1. Router co bat khong?")
        print(f"    2. IP {host} co dung khong? (thu ping {host})")
        print(f"    3. REST API da bat chua? (RouterOS 7+)")
        print(f"       Vao router chay:")
        print(f"       /ip/service/set www disabled=no")
        print(f"       /ip/service/set www-ssl certificate=local-cert disabled=no")
        return

    print(f"[v] Ket noi OK qua {base_url}")

    # Lay tat ca IPv6 addresses
    print("\nDang lay danh sach IPv6...")
    try:
        resp = session.get(f"{base_url}/ipv6/address", timeout=10)
        addrs = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        print(f"[x] Loi lay IPv6: {e}")
        return

    if not addrs:
        print("[!] Khong co IPv6 nao tren router!")
        print("    Kiem tra ISP da cap IPv6 chua")
        return

    # Hien thi tat ca IPv6
    print(f"\nTim thay {len(addrs)} IPv6 addresses:")
    print("-" * 70)

    # Phan tich de tim prefix va interface
    global_addrs = []  # IPv6 global (khong phai link-local)
    interfaces_found = {}

    for addr in addrs:
        address = addr.get("address", "")
        interface = addr.get("interface", "")
        dynamic = addr.get("dynamic", "false")
        invalid = addr.get("invalid", "false")
        disabled = addr.get("disabled", "false")

        # Phan loai
        is_link_local = address.startswith("fe80")
        is_global = not is_link_local and "::" in address

        status = ""
        if dynamic == "true":
            status += " [dynamic]"
        if invalid == "true":
            status += " [invalid]"
        if disabled == "true":
            status += " [disabled]"

        marker = "[GLOBAL]" if is_global else "[local] "
        print(f"  {marker} {address:<45} {interface:<12}{status}")

        if is_global and invalid != "true" and disabled != "true":
            global_addrs.append({"address": address, "interface": interface, "dynamic": dynamic})
            if interface not in interfaces_found:
                interfaces_found[interface] = []
            interfaces_found[interface].append(address)

    print("-" * 70)

    if not global_addrs:
        print("\n[!] Khong co IPv6 global nao!")
        print("    ISP chua cap IPv6 hoac chua cau hinh")
        return

    # Phan tich prefix
    print(f"\n{'='*60}")
    print("PHAN TICH KET QUA")
    print(f"{'='*60}")

    # Tim prefix chung
    prefixes = {}
    for ga in global_addrs:
        addr = ga["address"].split("/")[0]
        groups = addr.split(":")
        if len(groups) >= 4:
            # Lay 3 groups dau (vd: 2001:ee0:4f89)
            prefix_3 = ":".join(groups[:3])
            group4 = groups[3]
            if len(group4) >= 2:
                # prefix = 3 groups + 2 ky tu dau cua group 4 (vd: 2001:ee0:4f89:30)
                prefix_full = f"{prefix_3}:{group4[:2]}"
                if prefix_full not in prefixes:
                    prefixes[prefix_full] = {"subnets": [], "interfaces": set()}
                try:
                    subnet_hex = int(group4[2:], 16) if len(group4) > 2 else int(group4, 16)
                    prefixes[prefix_full]["subnets"].append(subnet_hex)
                except ValueError:
                    pass
                prefixes[prefix_full]["interfaces"].add(ga["interface"])

    if not prefixes:
        print("[!] Khong phan tich duoc prefix!")
        return

    # Chon prefix tot nhat (co nhieu subnet nhat)
    best_prefix = max(prefixes.keys(), key=lambda p: len(prefixes[p]["subnets"]))
    best_info = prefixes[best_prefix]
    best_interface = list(best_info["interfaces"])[0]
    used_subnets = sorted(best_info["subnets"])

    print(f"\n  Interface:     {best_interface}")
    print(f"  Prefix:        {best_prefix}")
    print(f"  Subnets dung:  {len(used_subnets)} ({', '.join(f'0x{s:02x}' for s in used_subnets[:10])}{'...' if len(used_subnets) > 10 else ''})")

    # Goi y range
    # Giu 100 IP dau (subnet 01-64) cho muc dich khac
    # Dung 155 IP con lai (subnet 65-ff) cho pool rotate
    suggested_start = 0x65  # 101 decimal
    suggested_end = 0xFF    # 255 decimal

    available_in_range = sum(1 for s in used_subnets if suggested_start <= s <= suggested_end)
    total_in_range = suggested_end - suggested_start + 1

    print(f"\n  Giu lai:       100 IP dau (subnet 01-64) cho muc dich khac")
    print(f"  Pool range:    subnet 0x{suggested_start:02x} → 0x{suggested_end:02x} ({total_in_range} subnets)")
    print(f"  IP da co:      {available_in_range} / {total_in_range} (da co tren router)")
    print(f"  Mode:          EXISTING IPs - chi quan ly, khong add/remove tren router")

    # Tao config goi y
    suggested_config = {
        "mikrotik": {
            "host": host,
            "username": username,
            "password": password,
            "interface": best_interface,
            "prefix": best_prefix,
            "subnet_start": suggested_start,
            "subnet_end": suggested_end,
            "pool_min": 3,
            "pool_max": 20
        }
    }

    print(f"\n{'='*60}")
    print("CONFIG GOI Y")
    print(f"{'='*60}")
    print(json.dumps(suggested_config, indent=2))

    # Hoi luu
    print(f"\nLuu config nay vao {CONFIG_FILE}?")
    confirm = input("(yes/no): ").strip().lower()
    if confirm in ("yes", "y"):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(suggested_config, f, indent=2, ensure_ascii=False)
        print(f"[v] Da luu! Gio co the chay:")
        print(f"    python -m ipv6.test_pool --connect   # Test ket noi")
        print(f"    python -m ipv6.test_pool --pool      # Test pool")
        print(f"    python -m ipv6.test_pool --rotate     # Test doi IPv6")
    else:
        print("Khong luu. Ban co the copy config tren va dan vao file:")
        print(f"  {CONFIG_FILE}")


# =========================================================================
# MAIN
# =========================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test IPv6 Dynamic Pool")
    parser.add_argument("--connect", action="store_true", help="Test ket noi MikroTik")
    parser.add_argument("--pool", action="store_true", help="Test pool operations")
    parser.add_argument("--rotate", action="store_true", help="Test rotate flow")
    parser.add_argument("--status", action="store_true", help="Xem trang thai pool")
    parser.add_argument("--reset", action="store_true", help="Reset pool")
    parser.add_argument("--detect", action="store_true", help="Tu dong detect config tu router")

    args = parser.parse_args()
    config = load_config()

    if args.detect:
        auto_detect(config)
    elif args.connect:
        test_connection(config)
    elif args.pool:
        test_pool_operations(config)
    elif args.rotate:
        test_rotate_flow(config)
    elif args.status:
        show_status(config)
    elif args.reset:
        reset_pool(config)
    else:
        # Run all tests
        if test_connection(config):
            test_pool_operations(config)
            test_rotate_flow(config)
            show_status(config)
