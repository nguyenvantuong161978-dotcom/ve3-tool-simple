"""
Test Fingerprint Spoof - Kiem tra fingerprint co duoc doi thanh cong khong.

Chay: python test_fingerprint.py
- Mo Chrome Portable
- Inject fingerprint spoof (3 seeds khac nhau)
- Verify ket qua tren browserleaks.com
"""
import sys
import os
import time
import random

# Add project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from DrissionPage import Chromium, ChromiumOptions


# === FINGERPRINT DATA (giong chrome_session.py) ===
_FAKE_GPUS = [
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 2070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
]
_FAKE_SCREENS = [
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]
_FAKE_CORES = [4, 6, 8, 12, 16]
_FAKE_MEMORY = [4, 8, 16, 32]


def _build_fingerprint_js(seed: int) -> str:
    """Tao JS spoof - giong het chrome_session.py"""
    import random as _rng
    r = _rng.Random(seed)
    gpu = r.choice(_FAKE_GPUS)
    scr = r.choice(_FAKE_SCREENS)
    cores = r.choice(_FAKE_CORES)
    mem = r.choice(_FAKE_MEMORY)
    nr, ng, nb = r.randint(1, 5), r.randint(1, 5), r.randint(1, 5)
    audio_noise = r.uniform(-0.1, 0.1)

    return f"""
    (function(){{
        // WebGL spoof
        var V="{gpu['vendor']}",R="{gpu['renderer']}";
        var gp=WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter=function(p){{
            if(p===37445||p===0x9245)return V;
            if(p===37446||p===0x9246)return R;
            return gp.call(this,p);
        }};
        if(typeof WebGL2RenderingContext!=='undefined'){{
            var gp2=WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter=function(p){{
                if(p===37445||p===0x9245)return V;
                if(p===37446||p===0x9246)return R;
                return gp2.call(this,p);
            }};
        }}
        // Canvas noise
        var otd=HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL=function(t){{
            try{{var c=this.getContext('2d');if(c){{var d=c.getImageData(0,0,Math.min(this.width,2),1);
            if(d.data.length>=4){{d.data[0]=(d.data[0]+{nr})%256;d.data[1]=(d.data[1]+{ng})%256;d.data[2]=(d.data[2]+{nb})%256;c.putImageData(d,0,0);}}}}}}catch(e){{}}
            return otd.call(this,t);
        }};
        // Hardware
        try{{Object.defineProperty(navigator,'hardwareConcurrency',{{get:()=>{cores},configurable:true}});}}catch(e){{}}
        try{{Object.defineProperty(navigator,'deviceMemory',{{get:()=>{mem},configurable:true}});}}catch(e){{}}
        // Screen
        try{{Object.defineProperty(screen,'width',{{get:()=>{scr['width']},configurable:true}});}}catch(e){{}}
        try{{Object.defineProperty(screen,'height',{{get:()=>{scr['height']},configurable:true}});}}catch(e){{}}
        try{{Object.defineProperty(screen,'availWidth',{{get:()=>{scr['width']},configurable:true}});}}catch(e){{}}
        try{{Object.defineProperty(screen,'availHeight',{{get:()=>{scr['height']}-40,configurable:true}});}}catch(e){{}}
        // Audio
        var ogf=AnalyserNode.prototype.getFloatFrequencyData;
        AnalyserNode.prototype.getFloatFrequencyData=function(a){{ogf.call(this,a);for(var i=0;i<Math.min(a.length,10);i++)a[i]+={audio_noise:.6f};}};
        console.log('[SPOOF] seed={seed} gpu={gpu["renderer"][:30]}...');
    }})();
    """


VERIFY_JS = """
(function() {
    var result = {};

    // Hardware
    result.cores = navigator.hardwareConcurrency;
    result.memory = navigator.deviceMemory || 'N/A';

    // Screen
    result.screen = screen.width + 'x' + screen.height;
    result.availScreen = screen.availWidth + 'x' + screen.availHeight;

    // WebGL
    try {
        var canvas = document.createElement('canvas');
        var gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            result.gpu_vendor = gl.getParameter(37445);
            result.gpu_renderer = gl.getParameter(37446);
        }
    } catch(e) {
        result.gpu = 'ERROR: ' + e.message;
    }

    // Canvas fingerprint
    try {
        var c2 = document.createElement('canvas');
        c2.width = 200; c2.height = 50;
        var ctx = c2.getContext('2d');
        ctx.fillStyle = '#f60';
        ctx.fillRect(0, 0, 200, 50);
        ctx.fillStyle = '#069';
        ctx.font = '14px Arial';
        ctx.fillText('fingerprint test 12345', 10, 30);
        result.canvas_hash = c2.toDataURL().substring(0, 60) + '...';
    } catch(e) {
        result.canvas = 'ERROR';
    }

    // User Agent
    result.userAgent = navigator.userAgent.substring(0, 80) + '...';

    return JSON.stringify(result, null, 2);
})();
"""


def find_chrome_portable():
    """Tim Chrome Portable trong project."""
    base = os.path.dirname(os.path.abspath(__file__))
    for name in ["GoogleChromePortable", "GoogleChromePortable - Copy"]:
        path = os.path.join(base, name, "GoogleChromePortable.exe")
        if os.path.exists(path):
            return os.path.join(base, name), path
    return None, None


def test_fingerprint():
    chrome_dir, chrome_exe = find_chrome_portable()
    if not chrome_exe:
        print("[ERROR] Khong tim thay GoogleChromePortable!")
        return

    print(f"[INFO] Chrome: {chrome_exe}")
    print(f"[INFO] Data: {chrome_dir}\\Data\\profile")
    print("=" * 70)

    # Test 3 seeds khac nhau
    seeds = [random.randint(10000, 99999) for _ in range(3)]

    for i, seed in enumerate(seeds):
        print(f"\n{'='*70}")
        print(f"  TEST {i+1}/3 - Seed: {seed}")
        print(f"{'='*70}")

        # Build spoof JS
        js = _build_fingerprint_js(seed)

        # Show expected values
        r = random.Random(seed)
        gpu = r.choice(_FAKE_GPUS)
        scr = r.choice(_FAKE_SCREENS)
        cores = r.choice(_FAKE_CORES)
        mem = r.choice(_FAKE_MEMORY)

        print(f"\n[EXPECTED]")
        print(f"  GPU:    {gpu['renderer'][:50]}...")
        print(f"  Screen: {scr['width']}x{scr['height']}")
        print(f"  Cores:  {cores}")
        print(f"  Memory: {mem} GB")

        # Setup Chrome
        co = ChromiumOptions()
        co.set_browser_path(chrome_exe)
        co.set_local_port(19250)  # Port rieng de test
        data_path = os.path.join(chrome_dir, "Data", "test_fingerprint")
        co.set_user_data_path(data_path)
        co.auto_port(True)

        try:
            browser = Chromium(co)
            page = browser.latest_tab

            # 1. CDP inject (TRUOC khi navigate) - giong production
            try:
                result = page.run_cdp('Page.addScriptToEvaluateOnNewDocument', source=js)
                script_id = result.get('identifier', '')
                print(f"\n[CDP] Inject OK (script_id={script_id})")
            except Exception as e:
                print(f"\n[CDP] Inject FAIL: {e}")

            # 2. Navigate to test page
            page.get("https://browserleaks.com/javascript")
            time.sleep(3)

            # 3. Also run_js on current page (giong production)
            try:
                page.run_js(js)
                print("[run_js] Inject OK")
            except Exception as e:
                print(f"[run_js] Error: {e}")

            # 4. Verify
            try:
                verify_result = page.run_js(VERIFY_JS)
                print(f"\n[ACTUAL RESULT]")
                print(verify_result)
            except Exception as e:
                print(f"\n[VERIFY] Error: {e}")

            # 5. Cho user xem browserleaks
            print(f"\n[INFO] Browser dang mo browserleaks.com - kiem tra thu cong")
            print(f"[INFO] Nhan ENTER de tiep tuc test tiep (hoac Ctrl+C de thoat)...")

            try:
                input()
            except KeyboardInterrupt:
                print("\n[INFO] Thoat.")
                browser.quit()
                return

            browser.quit()
            time.sleep(2)

        except Exception as e:
            print(f"\n[ERROR] {e}")
            try:
                browser.quit()
            except:
                pass

    # Cleanup test data
    import shutil
    test_data = os.path.join(chrome_dir, "Data", "test_fingerprint")
    if os.path.exists(test_data):
        try:
            shutil.rmtree(test_data)
            print(f"\n[CLEANUP] Xoa {test_data}")
        except:
            pass

    print(f"\n{'='*70}")
    print(f"  DONE! Da test 3 seeds khac nhau.")
    print(f"  Neu GPU/Screen/Cores thay doi moi lan → Spoof THANH CONG")
    print(f"  Neu giong nhau → Spoof THAT BAI")
    print(f"{'='*70}")


if __name__ == "__main__":
    test_fingerprint()
