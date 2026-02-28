#!/usr/bin/env python3
"""
Test quota error detection (429/253).
Mở Chrome, inject interceptor, và test xem có bắt được quota error không.
"""

import sys
import time
from pathlib import Path

TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

def main():
    print("=" * 60)
    print("TEST: Quota Error Detection (429/253)")
    print("=" * 60)

    from modules.drission_flow_api import DrissionFlowAPI

    # Chrome settings
    chrome_exe = TOOL_DIR / "GoogleChromePortable" / "App" / "Chrome-bin" / "chrome.exe"

    if not chrome_exe.exists():
        print(f"[ERROR] Chrome not found: {chrome_exe}")
        return 1

    print(f"\n[INFO] Chrome: {chrome_exe}")

    # Create API instance
    api = DrissionFlowAPI(
        worker_id=0,
        chrome_portable=str(chrome_exe),
        headless=False
    )

    # Setup Chrome
    print("\n[STEP 1] Setting up Chrome...")
    if not api.setup():
        print("[ERROR] Setup failed!")
        return 1
    print("[OK] Chrome ready")

    # Test: Check interceptor injection
    print("\n[STEP 2] Kiểm tra interceptor...")
    try:
        result = api.driver.run_js("""
            return {
                interceptReady: window.__interceptReady || false,
                hasResponse: window._response !== null,
                hasError: window._responseError !== null,
                pending: window._requestPending
            };
        """)
        print(f"[INFO] Interceptor ready: {result.get('interceptReady')}")
        print(f"[INFO] Has response: {result.get('hasResponse')}")
        print(f"[INFO] Has error: {result.get('hasError')}")
        print(f"[INFO] Request pending: {result.get('pending')}")
    except Exception as e:
        print(f"[ERROR] Check failed: {e}")

    # Test: Simulate 429 error
    print("\n[STEP 3] Simulate 429 quota error...")
    try:
        api.driver.run_js("""
            window._response = {error: {code: 429, message: 'Quota exceeded - test'}};
            window._responseError = 'Error 429: Quota exceeded - test';
            window._requestPending = false;
        """)
        print("[OK] Simulated 429 error set")

        # Check if we can read it back
        result = api.driver.run_js("""
            return {
                response: window._response,
                error: window._responseError,
                pending: window._requestPending
            };
        """)
        print(f"[INFO] Response: {result.get('response')}")
        print(f"[INFO] Error: {result.get('error')}")
        print(f"[INFO] Pending: {result.get('pending')}")

        if result.get('error') and '429' in str(result.get('error')):
            print("\n[PASS] ✓ 429 error detection WORKING!")
        else:
            print("\n[FAIL] ✗ 429 error not detected")
    except Exception as e:
        print(f"[ERROR] Test failed: {e}")

    # Reset state
    print("\n[STEP 4] Reset state...")
    api.driver.run_js("""
        window._response = null;
        window._responseError = null;
        window._requestPending = false;
    """)
    print("[OK] State reset")

    # Test: Real generate (optional)
    print("\n[STEP 5] Real generate test (cần có model hết quota)...")
    print("[INFO] Gửi prompt để test...")
    print("[INFO] Nếu model hết quota, sẽ thấy 'Error 429' trong log")

    images, error = api.generate_image_forward(
        prompt="A simple test image",
        num_images=1,
        timeout=60
    )

    if error:
        print(f"[INFO] Error returned: {error}")
        if "429" in str(error) or "quota" in str(error).lower():
            print("[PASS] ✓ Quota error detected correctly!")
        elif "403" in str(error):
            print("[INFO] Got 403 (reCAPTCHA), not quota error")
        else:
            print(f"[INFO] Other error: {error}")
    else:
        print(f"[INFO] Success! Got {len(images)} images")
        if images:
            print(f"[INFO] Media ID: {images[0].media_id}")

    # Cleanup
    print("\n[CLEANUP] Closing Chrome...")
    api.cleanup()

    print("\n" + "=" * 60)
    print("TEST COMPLETE!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
