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
        "subnet_start": 82,
        "subnet_end": 255,
        "pool_min": 3,
        "pool_max": 10,
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
    print(f"  Burned:     {status['burned']}")
    print(f"  Total:      {status['total']}")
    print(f"  Subnets used:      {status['subnets_used']}")
    print(f"  Subnets remaining: {status['subnets_remaining']}")

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

    args = parser.parse_args()
    config = load_config()

    if args.connect:
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
