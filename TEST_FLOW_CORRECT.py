#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST FLOW CORRECT v1.0.227 - Dung flow moi:
1. Chon x1 (1 anh) trong UI thay vi JS cut
2. Tao reference image (nhan vat chinh)
3. Tao nhieu scene voi reference
"""
import sys
import time
import json
import shutil
from pathlib import Path

from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.common import Keys
import pyperclip

print("=" * 60)
print("TEST FLOW v1.0.227 - Chon x1 + Reference + Scenes")
print("=" * 60)

chrome_path = Path("GoogleChromePortable/GoogleChromePortable.exe")
if not chrome_path.exists():
    chrome_path = Path("GoogleChromePortable - Copy/GoogleChromePortable.exe")

profile_path = Path("GoogleChromePortable/Data/profile_flow_test")


def create_chrome(clean_profile=False):
    """Tao Chrome - GIU profile de khong can dang nhap lai"""
    if clean_profile and profile_path.exists():
        shutil.rmtree(profile_path, ignore_errors=True)
        time.sleep(1)

    profile_path.mkdir(parents=True, exist_ok=True)

    co = ChromiumOptions()
    co.set_browser_path(str(chrome_path.absolute()))
    co.set_local_port(19100)
    co.set_argument('--window-size=1200,900')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument(f'--user-data-dir={profile_path.absolute()}')

    return ChromiumPage(co)


def select_x1_and_model(page, model_index=0):
    """Chon x1 (1 anh) va model - JS moi khong gay 403"""
    page.run_js(f"""
(function() {{
    window._modelSelectResult = 'PENDING';

    // Buoc 1: Mo menu chinh
    var btn1 = document.querySelector('button.sc-46973129-1');
    if (!btn1) {{
        window._modelSelectResult = 'NO_MENU_BUTTON';
        return;
    }}
    btn1.dispatchEvent(new PointerEvent('pointerdown', {{bubbles: true}}));
    btn1.dispatchEvent(new PointerEvent('pointerup', {{bubbles: true}}));
    console.log('[MODEL] Step 1: Menu opened');

    // Buoc 2: Click x1 (chon 1 anh) - FIX 403
    setTimeout(function() {{
        var allBtns = document.querySelectorAll('button');
        var clickedX1 = false;
        for (var i = 0; i < allBtns.length; i++) {{
            var b = allBtns[i];
            if (b.textContent.trim() === 'x1') {{
                b.dispatchEvent(new MouseEvent('mousedown', {{bubbles: true}}));
                b.dispatchEvent(new MouseEvent('mouseup', {{bubbles: true}}));
                b.dispatchEvent(new MouseEvent('click', {{bubbles: true}}));
                console.log('[MODEL] Step 2: Clicked x1 (1 anh)');
                clickedX1 = true;
                break;
            }}
        }}
        if (!clickedX1) {{
            console.log('[MODEL] Step 2: x1 button not found, continuing...');
        }}

        // Buoc 3: Click dropdown model
        setTimeout(function() {{
            var btn2 = document.querySelector('button.sc-a0dcecfb-1');
            if (!btn2) {{
                window._modelSelectResult = 'NO_DROPDOWN_BUTTON';
                return;
            }}
            btn2.dispatchEvent(new PointerEvent('pointerdown', {{bubbles: true}}));
            btn2.dispatchEvent(new PointerEvent('pointerup', {{bubbles: true}}));
            console.log('[MODEL] Step 3: Model dropdown opened');

            // Buoc 4: Chon model theo index
            setTimeout(function() {{
                var menuItems = document.querySelectorAll('[role="menuitem"]');
                if (menuItems.length > {model_index}) {{
                    var item = menuItems[{model_index}];
                    var modelName = item.textContent || 'Unknown';
                    item.dispatchEvent(new PointerEvent('pointerdown', {{bubbles: true}}));
                    item.dispatchEvent(new PointerEvent('pointerup', {{bubbles: true}}));
                    item.click();
                    console.log('[MODEL] Step 4: Selected ' + modelName);

                    // Buoc 5: Dong menu
                    setTimeout(function() {{
                        document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', bubbles: true}}));
                        setTimeout(function() {{
                            document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', bubbles: true}}));
                            console.log('[MODEL] Step 5: Menu closed');
                            window._modelSelectResult = 'OK';
                        }}, 300);
                    }}, 300);
                }} else {{
                    window._modelSelectResult = 'INVALID_INDEX';
                }}
            }}, 800);
        }}, 500);
    }}, 800);
}})();
    """)

    # Doi ket qua
    for _ in range(10):
        time.sleep(0.5)
        result = page.run_js("return window._modelSelectResult;")
        if result == 'OK':
            return True
        elif result != 'PENDING':
            print(f"  [WARN] Model select: {result}")
            return False
    return False


def inject_interceptor(page, image_inputs=None):
    """Inject JS interceptor - CHI CAPTURE, KHONG CUT (da chon x1)"""
    config = {}
    if image_inputs:
        config["imageInputs"] = image_inputs

    page.run_js(f"""
window._response = null;
window.__got403 = false;
window._modifyConfig = {json.dumps(config) if config else 'null'};

if (!window.__interceptorInjected) {{
    window.__interceptorInjected = true;
    var _orig = window.fetch;
    window.fetch = async function(url, opts) {{
        var urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox') && (urlStr.includes('batchGenerate') || urlStr.includes('flowMedia'))) {{
            // CHI THEM imageInputs, KHONG CUT so anh (da chon x1 tren UI)
            if (window._modifyConfig && window._modifyConfig.imageInputs && opts && opts.body) {{
                try {{
                    var body = JSON.parse(opts.body);
                    if (body.requests) {{
                        body.requests.forEach(r => r.imageInputs = window._modifyConfig.imageInputs);
                        console.log('[MODIFY] Added imageInputs');
                    }}
                    opts.body = JSON.stringify(body);
                    window._modifyConfig = null;
                }} catch(e) {{}}
            }}

            var resp = await _orig.apply(this, arguments);
            console.log('[RESP] Status:', resp.status);
            try {{
                var cloned = resp.clone();
                var data = await cloned.json();

                if (resp.status === 403) {{
                    window.__got403 = true;
                    console.log('[RESP] 403!');
                }}
                else if (data.media && data.media.length > 0) {{
                    console.log('[RESP] Media count:', data.media.length);
                    var ready = data.media.filter(m => m.image && m.image.generatedImage && m.image.generatedImage.fifeUrl);
                    if (ready.length > 0) window._response = data;
                }}
            }} catch(e) {{}}
            return resp;
        }}
        return _orig.apply(this, arguments);
    }};
}}
    """)


def nuclear_cleanup(page):
    """NUCLEAR CLEANUP - Xoa tat ca data"""
    page.run_js("""
    (async function() {
        localStorage.clear();
        sessionStorage.clear();
        if (window.indexedDB && window.indexedDB.databases) {
            const dbs = await window.indexedDB.databases();
            for (let db of dbs) {
                window.indexedDB.deleteDatabase(db.name);
            }
        }
        document.cookie.split(";").forEach(function(c) {
            document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
        });
        if ('caches' in window) {
            const cacheNames = await caches.keys();
            for (let name of cacheNames) {
                await caches.delete(name);
            }
        }
        if ('serviceWorker' in navigator) {
            const registrations = await navigator.serviceWorker.getRegistrations();
            for (let reg of registrations) {
                await reg.unregister();
            }
        }
    })();
    """)
    time.sleep(2)


def type_and_send(page, prompt, timeout=120):
    """Gui prompt"""
    page.run_js("""
        var input = document.querySelector('[contenteditable="true"]');
        if (input) { input.focus(); input.click(); }
    """)
    time.sleep(0.3)

    pyperclip.copy(prompt)
    page.actions.key_down(Keys.CONTROL).key_down('v').key_up('v').key_up(Keys.CONTROL)
    time.sleep(0.5)

    page.run_js("window._response = null; window.__got403 = false;")
    page.actions.key_down(Keys.ENTER).key_up(Keys.ENTER)
    print(f"  -> Sent: {prompt[:40]}...")

    start = time.time()
    while time.time() - start < timeout:
        got403 = page.run_js("return window.__got403;")
        if got403:
            return {"error": 403}

        response = page.run_js("return window._response;")
        if response and response.get("media"):
            return {"success": True, "time": int(time.time() - start), "response": response}

        elapsed = int(time.time() - start)
        if elapsed > 0 and elapsed % 20 == 0:
            print(f"  -> Waiting... {elapsed}s")

        time.sleep(2)

    return {"error": "timeout"}


def get_media_id(result):
    response = result.get("response") if isinstance(result, dict) else result
    if not response or not response.get("media"):
        return None
    for m in response.get("media", []):
        name = m.get("name")
        if not name and m.get("image", {}).get("generatedImage"):
            name = m["image"]["generatedImage"].get("name")
        if name:
            return name
    return None


# ============================================
# MAIN TEST
# ============================================
print("\n[1] Mo Chrome moi...")
page = create_chrome(clean_profile=True)

print("[2] Vao Flow project...")
page.get("https://labs.google/fx/vi/tools/flow/project/b8a9706e-321e-40d1-bd62-bc731297fadc")
time.sleep(5)

if "accounts.google" in page.url:
    print("[!] DANG NHAP GOOGLE")
    input(">>> ")

print(f"[3] URL: {page.url}")
time.sleep(10)

# ============================================
# STEP 1: Chon x1 + Model
# ============================================
print("\n" + "=" * 60)
print("STEP 1: Chon x1 (1 anh) + Model")
print("=" * 60)

if select_x1_and_model(page, model_index=0):
    print("  [OK] Da chon x1 + Model")
else:
    print("  [WARN] Khong chon duoc x1/model, tiep tuc...")

time.sleep(2)

# ============================================
# STEP 2: Tao reference (nhan vat chinh)
# ============================================
print("\n" + "=" * 60)
print("STEP 2: Tao reference (nhan vat chinh)")
print("=" * 60)

inject_interceptor(page, image_inputs=None)

ref_prompt = "A young woman with long black hair, wearing elegant blue dress, beautiful face, standing pose, full body, white background, high quality"
result1 = type_and_send(page, ref_prompt, 120)

if result1.get("success"):
    media_id = get_media_id(result1)
    print(f"  [OK] Reference in {result1['time']}s")
    print(f"  Media ID: {media_id}")

    if media_id:
        # ============================================
        # CLEANUP + RESTART
        # ============================================
        print("\n" + "=" * 60)
        print("CLEANUP + RESTART CHROME")
        print("=" * 60)

        nuclear_cleanup(page)
        page.quit()
        time.sleep(2)

        page = create_chrome(clean_profile=False)
        page.get("https://labs.google/fx/vi/tools/flow/project/b8a9706e-321e-40d1-bd62-bc731297fadc")
        time.sleep(5)

        if "accounts.google" in page.url:
            print("  [!] DANG NHAP LAI")
            input(">>> ")

        time.sleep(10)

        # Chon x1 + model lai
        print("  -> Chon x1 + Model...")
        select_x1_and_model(page, model_index=0)
        time.sleep(2)

        # QUAN TRONG: Inject lai interceptor sau restart Chrome!
        print("  -> Inject interceptor...")
        inject_interceptor(page, image_inputs=None)

        # ============================================
        # STEP 3: Tao nhieu scene voi reference
        # ============================================
        print("\n" + "=" * 60)
        print("STEP 3: Tao scene voi reference")
        print(f"Reference: {media_id}")
        print("=" * 60)

        scene_prompts = [
            "The woman walking in a beautiful garden with flowers, golden hour lighting",
            "The woman sitting in a cozy coffee shop, warm ambient lighting",
            "The woman standing on a beach at sunset, ocean waves"
        ]

        image_input = {
            "name": media_id,
            "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"
        }

        results = []
        for i, prompt in enumerate(scene_prompts):
            print(f"\n--- Scene {i+1}/{len(scene_prompts)} ---")

            # Update config voi reference
            page.run_js(f"window._modifyConfig = {{imageInputs: [{json.dumps(image_input)}]}};")

            result = type_and_send(page, prompt, 120)

            if result.get("success"):
                scene_id = get_media_id(result)
                print(f"  [OK] {result['time']}s - ID: {scene_id[:30] if scene_id else 'N/A'}...")
                results.append({"status": "OK", "time": result['time']})
            elif result.get("error") == 403:
                print(f"  [X] 403!")
                results.append({"status": "403"})
                break
            else:
                print(f"  [X] Timeout")
                results.append({"status": "timeout"})

            time.sleep(3)

        # Summary
        print("\n" + "=" * 60)
        print("KET QUA")
        print("=" * 60)
        ok_count = sum(1 for r in results if r["status"] == "OK")
        print(f"Reference: {media_id[:40]}...")
        print(f"Scenes: {ok_count}/{len(results)} OK")
        for i, r in enumerate(results):
            print(f"  {i+1}. {r['status']}" + (f" ({r.get('time')}s)" if r.get('time') else ""))

        if ok_count == len(results):
            print("\nTHANH CONG! Flow x1 + Reference hoat dong!")
    else:
        print("  [X] Khong lay duoc media_id")
else:
    print(f"  [X] Reference FAILED: {result1}")

print("\nNhan Enter de dong...")
try:
    input()
except:
    pass

page.quit()
print("Done!")
