"""
Test JS chuyển mode: Image ↔ Video (T2V).
Chỉ test UI switch, không tạo ảnh/video.
"""
import sys, os, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOL_DIR)


def main():
    print("=" * 60)
    print("TEST: CHUYEN MODE IMAGE <-> VIDEO (T2V)")
    print("=" * 60)

    from modules.drission_flow_api import DrissionFlowAPI

    api = DrissionFlowAPI(
        chrome_portable=str(os.path.join(TOOL_DIR, "GoogleChromePortable", "GoogleChromePortable.exe")),
        headless=False, worker_id=0, total_workers=1, chrome_port=19555,
    )

    print("\n[1] Setup Chrome... (mo project truoc khi test)")
    ok = api.setup(wait_for_project=True, timeout=120)
    if not ok:
        print("[ERROR] Setup failed!")
        return
    print("[OK] Chrome ready!")
    time.sleep(2)

    # ==========================================
    # TEST 1: Mo settings panel
    # ==========================================
    print(f"\n{'='*60}")
    print("[TEST 1] Mo settings panel...")
    print(f"{'='*60}")

    result = api._open_settings_panel()
    print(f"  _open_settings_panel(): {result}")
    time.sleep(2)

    # Dong panel
    api.driver.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    time.sleep(1)

    # ==========================================
    # TEST 2: Chuyen sang T2V mode
    # ==========================================
    print(f"\n{'='*60}")
    print("[TEST 2] Chuyen sang T2V mode (Video)...")
    print(f"{'='*60}")

    result_t2v = api.switch_to_t2v_mode()
    print(f"  switch_to_t2v_mode(): {result_t2v}")
    time.sleep(2)

    # Dong panel
    api.driver.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    api.driver.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    time.sleep(1)

    # ==========================================
    # TEST 3: Chuyen ve Image mode (select model)
    # ==========================================
    print(f"\n{'='*60}")
    print("[TEST 3] Chuyen ve Image mode (select model index 0)...")
    print(f"{'='*60}")

    from modules.drission_flow_api import JS_SELECT_MODEL_BY_INDEX
    api.driver.run_js("window._modelSelectResult = 'PENDING';")
    api.driver.run_js(JS_SELECT_MODEL_BY_INDEX % 0)
    time.sleep(6)
    result_model = api.driver.run_js("return window._modelSelectResult;")
    print(f"  JS_SELECT_MODEL_BY_INDEX result: {result_model}")
    time.sleep(1)

    # Dong panel
    api.driver.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    api.driver.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    time.sleep(1)

    # ==========================================
    # TEST 4: Chuyen lai T2V mode lan 2
    # ==========================================
    print(f"\n{'='*60}")
    print("[TEST 4] Chuyen lai T2V mode lan 2...")
    print(f"{'='*60}")

    result_t2v_2 = api.switch_to_t2v_mode()
    print(f"  switch_to_t2v_mode(): {result_t2v_2}")

    # ==========================================
    # KET QUA
    # ==========================================
    print(f"\n{'='*60}")
    print("KET QUA:")
    print(f"{'='*60}")
    print(f"  TEST 1 - Mo settings panel:  {'OK' if result else 'FAIL'}")
    print(f"  TEST 2 - Chuyen T2V mode:    {'OK' if result_t2v else 'FAIL'}")
    print(f"  TEST 3 - Chuyen Image mode:  {'OK' if result_model and 'SELECTED' in str(result_model) else 'FAIL'} ({result_model})")
    print(f"  TEST 4 - Chuyen T2V lan 2:   {'OK' if result_t2v_2 else 'FAIL'}")
    print(f"{'='*60}")

    all_pass = result and result_t2v and result_t2v_2
    if all_pass:
        print(">>> TAT CA TEST PASSED! <<<")
    else:
        print(">>> CO TEST FAIL - xem log tren <<<")

    try:
        api.close()
    except:
        pass


if __name__ == "__main__":
    main()
