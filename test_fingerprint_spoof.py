"""
Test fingerprint spoof - Mo Chrome voi WebGL/Canvas spoof de bypass 403.

Usage:
    python test_fingerprint_spoof.py
    python test_fingerprint_spoof.py --no-spoof    # Mo binh thuong de so sanh
"""
import sys
import os
import time
import random
import hashlib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from pathlib import Path
TOOL_DIR = Path(__file__).parent

# ============================================================
# FINGERPRINT SPOOF CONFIG
# ============================================================

# Danh sach GPU renderer gia (pho bien, khong gay nghi ngo)
FAKE_GPUS = [
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 2070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
]

# Danh sach screen resolution gia
FAKE_SCREENS = [
    {"width": 1920, "height": 1080},
    {"width": 2560, "height": 1440},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]

# Danh sach hardware concurrency (CPU cores)
FAKE_CORES = [4, 6, 8, 12, 16]

# Danh sach device memory (GB)
FAKE_MEMORY = [4, 8, 16, 32]


def generate_spoof_seed(machine_id: str = "") -> int:
    """Tao seed tu machine_id de fingerprint consistent giua cac lan restart."""
    if not machine_id:
        machine_id = os.environ.get('COMPUTERNAME', 'default')
    return int(hashlib.md5(machine_id.encode()).hexdigest()[:8], 16)


def get_fingerprint_js(seed: int = None) -> str:
    """
    Tao JavaScript spoof WebGL, Canvas, AudioContext, hardware info.
    Seed de chon fingerprint consistent (khong random moi lan).
    """
    if seed is None:
        seed = random.randint(0, 99999)

    rng = random.Random(seed)

    gpu = rng.choice(FAKE_GPUS)
    screen = rng.choice(FAKE_SCREENS)
    cores = rng.choice(FAKE_CORES)
    memory = rng.choice(FAKE_MEMORY)

    # Noise value cho canvas (nho, khong nhin thay bang mat)
    noise_r = rng.randint(1, 5)
    noise_g = rng.randint(1, 5)
    noise_b = rng.randint(1, 5)

    print(f"\n[SPOOF] Fingerprint config (seed={seed}):")
    print(f"  GPU: {gpu['renderer']}")
    print(f"  Screen: {screen['width']}x{screen['height']}")
    print(f"  Cores: {cores}, Memory: {memory}GB")
    print(f"  Canvas noise: R+{noise_r} G+{noise_g} B+{noise_b}")

    js = f"""
    // ========== FINGERPRINT SPOOF ==========

    // 1. WebGL Renderer/Vendor spoof
    (function() {{
        const FAKE_VENDOR = "{gpu['vendor']}";
        const FAKE_RENDERER = "{gpu['renderer']}";

        const getParamOrig = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            // UNMASKED_VENDOR_WEBGL = 0x9245
            if (param === 0x9245 || param === 37445) return FAKE_VENDOR;
            // UNMASKED_RENDERER_WEBGL = 0x9246
            if (param === 0x9246 || param === 37446) return FAKE_RENDERER;
            return getParamOrig.call(this, param);
        }};

        // WebGL2 cung can spoof
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const getParam2Orig = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {{
                if (param === 0x9245 || param === 37445) return FAKE_VENDOR;
                if (param === 0x9246 || param === 37446) return FAKE_RENDERER;
                return getParam2Orig.call(this, param);
            }};
        }}
    }})();

    // 2. Canvas fingerprint noise
    (function() {{
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type) {{
            // Them noise nho vao canvas truoc khi export
            const ctx = this.getContext('2d');
            if (ctx) {{
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 2), 1);
                if (imageData.data.length >= 4) {{
                    imageData.data[0] = (imageData.data[0] + {noise_r}) % 256;
                    imageData.data[1] = (imageData.data[1] + {noise_g}) % 256;
                    imageData.data[2] = (imageData.data[2] + {noise_b}) % 256;
                    ctx.putImageData(imageData, 0, 0);
                }}
            }}
            return origToDataURL.call(this, type);
        }};

        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {{
            const ctx = this.getContext('2d');
            if (ctx) {{
                const imageData = ctx.getImageData(0, 0, Math.min(this.width, 2), 1);
                if (imageData.data.length >= 4) {{
                    imageData.data[0] = (imageData.data[0] + {noise_r}) % 256;
                    imageData.data[1] = (imageData.data[1] + {noise_g}) % 256;
                    imageData.data[2] = (imageData.data[2] + {noise_b}) % 256;
                    ctx.putImageData(imageData, 0, 0);
                }}
            }}
            return origToBlob.call(this, callback, type, quality);
        }};
    }})();

    // 3. Hardware info spoof
    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {cores} }});
    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {memory} }});

    // 4. Screen resolution spoof
    Object.defineProperty(screen, 'width', {{ get: () => {screen['width']} }});
    Object.defineProperty(screen, 'height', {{ get: () => {screen['height']} }});
    Object.defineProperty(screen, 'availWidth', {{ get: () => {screen['width']} }});
    Object.defineProperty(screen, 'availHeight', {{ get: () => {screen['height']} - 40 }});

    // 5. AudioContext fingerprint noise
    (function() {{
        const origGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
        AnalyserNode.prototype.getFloatFrequencyData = function(array) {{
            origGetFloatFrequencyData.call(this, array);
            // Them noise nho
            for (let i = 0; i < Math.min(array.length, 10); i++) {{
                array[i] += {rng.uniform(-0.1, 0.1):.6f};
            }}
        }};
    }})();

    // 6. WebGL debug info extension spoof
    (function() {{
        const origGetExtension = WebGLRenderingContext.prototype.getExtension;
        WebGLRenderingContext.prototype.getExtension = function(name) {{
            const ext = origGetExtension.call(this, name);
            if (name === 'WEBGL_debug_renderer_info' && ext) {{
                // Extension van tra ve nhung getParameter da bi override
                return ext;
            }}
            return ext;
        }};
    }})();

    console.log('[SPOOF] Fingerprint spoof active: GPU={gpu['renderer'][:40]}...');
    """
    return js


def test_fingerprint(use_spoof: bool = True):
    """Mo Chrome, inject spoof, vao Flow page de test."""
    from DrissionPage import ChromiumPage, ChromiumOptions

    # Tim Chrome Portable
    chrome_paths = [
        TOOL_DIR / "GoogleChromePortable" / "GoogleChromePortable.exe",
        TOOL_DIR / "GoogleChromePortable - Copy" / "GoogleChromePortable.exe",
    ]
    chrome_path = None
    for p in chrome_paths:
        if p.exists():
            chrome_path = p
            break

    if not chrome_path:
        print("[ERROR] Khong tim thay Chrome Portable!")
        return

    print(f"\n[INFO] Chrome: {chrome_path}")
    print(f"[INFO] Spoof: {'ON' if use_spoof else 'OFF'}")

    # Setup Chrome
    co = ChromiumOptions()
    co.set_browser_path(str(chrome_path))
    data_path = str(chrome_path.parent / "Data" / "profile")
    co.set_user_data_path(data_path)
    co.set_address('127.0.0.1:19333')  # Port rieng cho test
    co.set_argument('--no-first-run')
    co.set_argument('--no-default-browser-check')

    print("[INFO] Opening Chrome...")
    page = ChromiumPage(co)
    print(f"[OK] Chrome opened: {page.title}")

    if use_spoof:
        # Inject fingerprint spoof
        seed = generate_spoof_seed()
        js = get_fingerprint_js(seed)

        # Inject vao page hien tai truoc
        try:
            page.run_js(js)
            print("[OK] Fingerprint spoof injected!")
        except Exception as e:
            print(f"[WARN] Inject error: {e}")

    # Vao Flow page
    flow_url = "https://labs.google/fx/vi/tools/flow"
    print(f"\n[INFO] Navigating to: {flow_url}")
    page.get(flow_url)
    time.sleep(3)

    if use_spoof:
        # Re-inject sau khi navigate (page moi = context moi)
        try:
            page.run_js(js)
            print("[OK] Re-injected spoof after navigation")
        except Exception as e:
            print(f"[WARN] Re-inject error: {e}")

    # Kiem tra fingerprint hien tai
    print("\n[CHECK] Current fingerprint:")
    try:
        # WebGL
        webgl_info = page.run_js("""
            try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                if (ext) {
                    return {
                        vendor: gl.getParameter(ext.UNMASKED_VENDOR_WEBGL),
                        renderer: gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)
                    };
                }
                return {vendor: 'N/A', renderer: 'N/A'};
            } catch(e) {
                return {vendor: 'Error', renderer: String(e)};
            }
        """)
        print(f"  WebGL Vendor: {webgl_info.get('vendor', 'N/A')}")
        print(f"  WebGL Renderer: {webgl_info.get('renderer', 'N/A')}")

        # Hardware
        hw_info = page.run_js("""
            return {
                cores: navigator.hardwareConcurrency,
                memory: navigator.deviceMemory,
                screenW: screen.width,
                screenH: screen.height,
                platform: navigator.platform,
                userAgent: navigator.userAgent.substring(0, 80)
            };
        """)
        print(f"  CPU Cores: {hw_info.get('cores', 'N/A')}")
        print(f"  Memory: {hw_info.get('memory', 'N/A')}GB")
        print(f"  Screen: {hw_info.get('screenW', '?')}x{hw_info.get('screenH', '?')}")
        print(f"  Platform: {hw_info.get('platform', 'N/A')}")
        print(f"  UA: {hw_info.get('userAgent', 'N/A')}...")
    except Exception as e:
        print(f"  [ERROR] Check failed: {e}")

    print(f"\n[INFO] URL: {page.url}")
    print(f"\n{'='*60}")
    print(f"Chrome dang mo - hay thu tao anh de xem co bi 403 khong.")
    print(f"Nhan Enter de dong Chrome...")
    print(f"{'='*60}")

    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass

    try:
        page.quit()
        print("[OK] Chrome closed")
    except:
        pass


if __name__ == "__main__":
    no_spoof = "--no-spoof" in sys.argv
    test_fingerprint(use_spoof=not no_spoof)
