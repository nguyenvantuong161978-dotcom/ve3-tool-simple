#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST FLOW CORRECT - Dung flow dung cua tool
1. JS interceptor -> Tao anh
2. NUCLEAR CLEANUP (JS)
3. Restart Chrome
4. JS interceptor -> Tao anh voi reference
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
print("TEST FLOW CORRECT - Reference + Scenes")
print("=" * 60)

chrome_path = Path("GoogleChromePortable/GoogleChromePortable.exe")
if not chrome_path.exists():
    chrome_path = Path("GoogleChromePortable - Copy/GoogleChromePortable.exe")

profile_path = Path("GoogleChromePortable/Data/profile_flow_test")


def create_chrome(clean_profile=False):
    """Tao Chrome - GIU profile de khong can dang nhap lai"""
    if clean_profile and profile_path.exists():
        # Chi xoa khi lan dau hoac yeu cau
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


def inject_interceptor(page, image_count=1, image_inputs=None):
    """Inject JS interceptor"""
    config = {"imageCount": image_count}
    if image_inputs:
        config["imageInputs"] = image_inputs

    page.run_js(f"""
window._response = null;
window.__got403 = false;
window._modifyConfig = {json.dumps(config)};
window._imageCallCount = 0;
window._maxImageCalls = {image_count};

if (!window.__interceptorInjected) {{
    window.__interceptorInjected = true;
    var _orig = window.fetch;
    window.fetch = async function(url, opts) {{
        var urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox') && (urlStr.includes('batchGenerate') || urlStr.includes('flowMedia'))) {{
            if (window._maxImageCalls > 0 && window._imageCallCount >= window._maxImageCalls) {{
                return new Response(JSON.stringify({{blocked: true}}), {{status: 200}});
            }}
            window._imageCallCount++;

            if (window._modifyConfig && opts && opts.body) {{
                try {{
                    var body = JSON.parse(opts.body);
                    var cfg = window._modifyConfig;
                    if (cfg.imageCount && body.requests) {{
                        body.requests = body.requests.slice(0, cfg.imageCount);
                    }}
                    if (cfg.imageInputs && body.requests) {{
                        body.requests.forEach(r => r.imageInputs = cfg.imageInputs);
                        console.log('[MODIFY] Added refs');
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
                console.log('[RESP] Data keys:', Object.keys(data).join(','));

                // Capture RAW response for debug
                window._rawResponse = data;
                window._rawStatus = resp.status;

                if (resp.status === 403) {{
                    window.__got403 = true;
                    console.log('[RESP] 403!');
                }}
                else if (data.error) {{
                    console.log('[RESP] Error:', JSON.stringify(data.error));
                    window._responseError = data.error;
                }}
                else if (data.media && data.media.length > 0) {{
                    console.log('[RESP] Media count:', data.media.length);
                    var ready = data.media.filter(m => m.image && m.image.generatedImage && m.image.generatedImage.fifeUrl);
                    console.log('[RESP] Ready count:', ready.length);
                    if (ready.length > 0) window._response = data;
                }}
            }} catch(e) {{
                console.log('[RESP] Parse error:', e);
            }}
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
    # Check input element
    check = page.run_js("""
        var ce = document.querySelectorAll('[contenteditable="true"]').length;
        return 'contenteditable=' + ce;
    """)
    print(f"  -> Elements: {check}")

    page.run_js("""
        var input = document.querySelector('[contenteditable="true"]');
        if (input) { input.focus(); input.click(); }
    """)
    time.sleep(0.3)

    pyperclip.copy(prompt)
    page.actions.key_down(Keys.CONTROL).key_down('v').key_up('v').key_up(Keys.CONTROL)
    time.sleep(0.5)

    # Check content
    content = page.run_js("""
        var input = document.querySelector('[contenteditable="true"]');
        return input ? (input.textContent || '').length : 0;
    """)
    print(f"  -> Content: {content} chars")

    page.run_js("window._response = null; window.__got403 = false; window._imageCallCount = 0;")
    page.actions.key_down(Keys.ENTER).key_up(Keys.ENTER)
    print(f"  -> Enter sent")

    start = time.time()
    while time.time() - start < timeout:
        got403 = page.run_js("return window.__got403;")
        if got403:
            return {"error": 403}

        response = page.run_js("return window._response;")
        if response and response.get("media"):
            return {"success": True, "time": int(time.time() - start), "response": response}

        # Debug: check call count moi 20s
        elapsed = int(time.time() - start)
        if elapsed > 0 and elapsed % 20 == 0:
            call_count = page.run_js("return window._imageCallCount;")
            print(f"  -> Waiting... {elapsed}s, calls={call_count}")

        time.sleep(2)

    # Final debug
    call_count = page.run_js("return window._imageCallCount;")
    raw_status = page.run_js("return window._rawStatus;")
    raw_error = page.run_js("return window._responseError;")
    raw_keys = page.run_js("return window._rawResponse ? Object.keys(window._rawResponse).join(',') : 'NO_RAW';")
    print(f"  -> Timeout! calls={call_count}, status={raw_status}, keys={raw_keys}")
    if raw_error:
        print(f"  -> Error: {raw_error}")
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
# STEP 1: Tao reference image
# ============================================
print("\n[1] Mo Chrome moi (lan dau - xoa profile cu)...")
page = create_chrome(clean_profile=True)  # Lan dau xoa profile

print("[2] Vao Flow project...")
page.get("https://labs.google/fx/vi/tools/flow/project/b8a9706e-321e-40d1-bd62-bc731297fadc")
time.sleep(5)

if "accounts.google" in page.url:
    print("[!] DANG NHAP GOOGLE")
    try:
        input(">>> ")
    except:
        time.sleep(120)

print(f"[3] URL: {page.url}")
time.sleep(10)

print("[4] Inject interceptor...")
inject_interceptor(page, image_count=1, image_inputs=None)

print("\n" + "=" * 60)
print("STEP 1: Tao reference image")
print("=" * 60)

ref_prompt = "A young woman with long black hair, wearing blue dress, standing, white background"
print(f"Prompt: {ref_prompt[:50]}...")

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

        print("  -> NUCLEAR CLEANUP...")
        nuclear_cleanup(page)

        print("  -> Quit Chrome...")
        page.quit()
        time.sleep(2)

        print("  -> Mo Chrome moi (GIU profile - khong xoa)...")
        page = create_chrome(clean_profile=False)  # GIU profile de khong can login lai

        print("  -> Vao Flow project...")
        page.get("https://labs.google/fx/vi/tools/flow/project/b8a9706e-321e-40d1-bd62-bc731297fadc")
        time.sleep(5)

        if "accounts.google" in page.url:
            print("  [!] DANG NHAP LAI GOOGLE")
            try:
                input(">>> ")
            except:
                time.sleep(60)

        time.sleep(10)

        # ============================================
        # STEP 2: Tao scene voi reference
        # ============================================
        print("\n" + "=" * 60)
        print("STEP 2: Tao scene voi reference")
        print(f"Reference: {media_id}")
        print("=" * 60)

        print("  -> Inject interceptor voi reference...")
        image_input = {
            "name": media_id,
            "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"
        }
        inject_interceptor(page, image_count=1, image_inputs=[image_input])

        # DEBUG: Check interceptor
        check = page.run_js("""
            return {
                interceptorInjected: !!window.__interceptorInjected,
                modifyConfig: window._modifyConfig,
                maxImageCalls: window._maxImageCalls
            };
        """)
        print(f"  DEBUG: {check}")

        scene_prompt = "The woman walking in a garden with flowers, golden hour"
        print(f"Prompt: {scene_prompt[:50]}...")

        result2 = type_and_send(page, scene_prompt, 120)

        if result2.get("success"):
            scene_id = get_media_id(result2)
            print(f"  [OK] Scene in {result2['time']}s")
            print(f"  Scene ID: {scene_id}")
            print("\n" + "=" * 60)
            print("THANH CONG!")
            print("=" * 60)
        else:
            print(f"  [X] Scene FAILED: {result2}")
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
