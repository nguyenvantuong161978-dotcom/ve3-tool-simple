"""
Chrome Session Manager - Quản lý Chrome cho proxy server.

Tái sử dụng flow từ tool (drission_flow_api.py):
1. Mở ChromePortable
2. Vào labs.google/fx/tools/flow
3. Tạo project mới
4. Sẵn sàng nhận request

Mỗi request:
1. Inject interceptor (thay bearer token + projectId)
2. Paste prompt → Enter
3. Chờ response → trả kết quả
4. Cleanup browser data → sẵn sàng cho request tiếp
"""
import sys
import os
import time
import json
import base64
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOOL_DIR = Path(__file__).parent.parent

# ============================================================
# Flow URL + Constants
# ============================================================
FLOW_URL = "https://labs.google/fx/vi/tools/flow"

# Model name → index trong dropdown
MODEL_INDEX_MAP = {
    'GEM_PIX_2': 0,       # Nano Banana Pro (default)
    'NARWHAL': 1,          # Nano Banana 2
    'IMAGEN_3_5': 2,       # Imagen 4
}

# ============================================================
# JavaScript snippets (từ drission_flow_api.py + test_local_proxy.py)
# ============================================================

JS_CLEANUP = """
(function() {
    try { localStorage.clear(); } catch(e) {}
    try { sessionStorage.clear(); } catch(e) {}
    try {
        indexedDB.databases().then(function(dbs) {
            dbs.forEach(function(db) { indexedDB.deleteDatabase(db.name); });
        });
    } catch(e) {}
    try {
        document.cookie.split(";").forEach(function(c) {
            document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
        });
    } catch(e) {}
    try {
        caches.keys().then(function(names) {
            names.forEach(function(name) { caches.delete(name); });
        });
    } catch(e) {}
    try {
        navigator.serviceWorker.getRegistrations().then(function(regs) {
            regs.forEach(function(r) { r.unregister(); });
        });
    } catch(e) {}
    return 'CLEANED';
})();
"""

# Fingerprint spoof data
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
    """Tao JS spoof WebGL/Canvas/Hardware fingerprint tu seed."""
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
        // Hardware (try/catch vi CDP co the da inject truoc)
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


JS_CLICK_NEW_PROJECT = """
(function() {
    // Tìm nút "Dự án mới" (có icon add_2)
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
        var t = btns[i].textContent.trim();
        if (t.indexOf('add_2') >= 0 || t.indexOf('Dự án mới') >= 0 || t.indexOf('New project') >= 0) {
            btns[i].click();
            return 'CLICKED';
        }
    }

    // Fallback: "Create with Flow" hoặc tương tự
    var links = document.querySelectorAll('a');
    for (var i = 0; i < links.length; i++) {
        var t = links[i].textContent.trim();
        if (t.indexOf('Create') >= 0 && t.indexOf('Flow') >= 0) {
            links[i].click();
            return 'CLICKED_LINK';
        }
    }

    return 'NOT_FOUND';
})();
"""

JS_SELECT_MODEL = """
(function(modelIndex) {
    window._modelSelectResult = 'PENDING';
    var keywords = ['Banana', 'Imagen', 'Veo', 'Video', 'Fast'];
    var btns = document.querySelectorAll('button');
    var halfH = window.innerHeight * 0.5;
    var btn1 = null;
    for (var i = 0; i < btns.length; i++) {
        var t = btns[i].textContent.trim();
        var rect = btns[i].getBoundingClientRect();
        if (rect.width > 50 && rect.y > halfH) {
            for (var k = 0; k < keywords.length; k++) {
                if (t.indexOf(keywords[k]) >= 0) { btn1 = btns[i]; break; }
            }
            if (btn1) break;
        }
    }
    if (btn1) {
        btn1.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
        btn1.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
    } else { window._modelSelectResult = 'NO_BUTTON'; return; }

    setTimeout(function() {
        var tab = document.querySelector('[id*="trigger-IMAGE"]');
        if (tab) {
            tab.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
            tab.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
            tab.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }
        setTimeout(function() {
            var t169 = document.querySelector('[id*="trigger-LANDSCAPE"]');
            if (t169) {
                t169.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                t169.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                t169.dispatchEvent(new MouseEvent('click', {bubbles: true}));
            }
            setTimeout(function() {
                var x1 = document.querySelector('[id*="trigger-1"]');
                if (x1) {
                    x1.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    x1.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    x1.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                }
                setTimeout(function() {
                    var btns = document.querySelectorAll('button');
                    for (var i = 0; i < btns.length; i++) {
                        var t = btns[i].textContent.trim();
                        if (t.indexOf('arrow_drop_down') >= 0 && btns[i].getBoundingClientRect().width > 0) {
                            btns[i].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                            btns[i].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                            break;
                        }
                    }
                    setTimeout(function() {
                        var items = document.querySelectorAll('[role="menuitem"]');
                        if (items.length > modelIndex) {
                            items[modelIndex].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                            items[modelIndex].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                            items[modelIndex].click();
                            window._modelSelectResult = 'SELECTED_' + modelIndex;
                        } else { window._modelSelectResult = 'NO_ITEMS'; }
                        setTimeout(function() {
                            document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                            document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                        }, 500);
                    }, 800);
                }, 500);
            }, 300);
        }, 300);
    }, 1500);
})(MODEL_INDEX);
"""


def build_interceptor_js(client_bearer_token: str, client_project_id: str,
                         image_inputs: list = None) -> str:
    """
    JS Interceptor - THAY bearer token + projectId + inject imageInputs.

    Flow:
    1. Chrome gửi request với recaptchaToken hợp lệ
    2. Interceptor THAY: bearer token → client's token, projectId → client's projectId
    3. Inject imageInputs (reference images) nếu có
    4. GIỮ NGUYÊN recaptchaToken từ Chrome
    5. Google nhận: token khách + captcha hợp lệ → tạo ảnh dưới tài khoản khách
    """
    safe_token = client_bearer_token.replace("\\", "\\\\").replace("'", "\\'")
    safe_project = client_project_id.replace("\\", "\\\\").replace("'", "\\'")

    # imageInputs JSON (hoặc null nếu không có)
    if image_inputs and len(image_inputs) > 0:
        import json
        image_inputs_json = json.dumps(image_inputs)
    else:
        image_inputs_json = "null"

    return """
window._response = null;
window._responseError = null;
window._requestPending = false;
window._clientBearerToken = '""" + safe_token + """';
window._clientProjectId = '""" + safe_project + """';
window._imageInputs = """ + image_inputs_json + """;

(function() {
    if (window.__proxyInterceptReady) return 'ALREADY';
    window.__proxyInterceptReady = true;

    var origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        var urlStr = typeof url === 'string' ? url : url.url;

        if (urlStr.includes('aisandbox') && (urlStr.includes('batchGenerate') || urlStr.includes('flowMedia'))) {
            console.log('[PROXY] Caught request:', urlStr);

            if (!window._response) {
                window._requestPending = true;
                window._response = null;
                window._responseError = null;
            }

            // 1. THAY BEARER TOKEN
            if (window._clientBearerToken && opts) {
                if (!opts.headers) opts.headers = {};
                if (opts.headers instanceof Headers) {
                    opts.headers.set('Authorization', 'Bearer ' + window._clientBearerToken);
                } else {
                    opts.headers['Authorization'] = 'Bearer ' + window._clientBearerToken;
                }
                console.log('[PROXY] 1. Replaced bearer token');
            }

            // 2. THAY projectId + inject imageInputs trong body
            // QUAN TRONG: Chi xu ly khi co clientProjectId (giong test file)
            if (window._clientProjectId && opts && opts.body) {
                try {
                    var body = JSON.parse(opts.body);

                    // Thay projectId trong clientContext
                    if (body.clientContext) {
                        var oldProjId = body.clientContext.projectId;
                        body.clientContext.projectId = window._clientProjectId;
                        console.log('[PROXY] 2a. Body projectId: ' + oldProjId + ' → ' + window._clientProjectId);
                    }

                    // Thay projectId trong mỗi request
                    if (body.requests) {
                        body.requests.forEach(function(req) {
                            if (req.clientContext) {
                                req.clientContext.projectId = window._clientProjectId;
                            }
                            console.log('[PROXY] 2b. Prompt: ' + (req.prompt || '').substring(0, 60));
                        });
                    }

                    // Inject imageInputs (reference images) nếu có
                    if (window._imageInputs && body.requests) {
                        body.requests.forEach(function(req) {
                            req.imageInputs = window._imageInputs;
                        });
                        console.log('[PROXY] 2c. Injected ' + window._imageInputs.length + ' reference images');
                    }

                    // GIỮ NGUYÊN recaptchaToken từ Chrome!
                    var recaptcha = body.clientContext ? body.clientContext.recaptchaToken : '';
                    console.log('[PROXY] 2d. recaptchaToken kept: ' + (recaptcha ? recaptcha.substring(0, 20) + '...' : 'EMPTY'));

                    opts.body = JSON.stringify(body);
                } catch(e) {
                    console.log('[PROXY] Parse body error:', e);
                }
            }

            // 3. THAY projectId trong URL
            if (window._clientProjectId) {
                var newUrl = urlStr.replace(/projects\\/[^/]+/, 'projects/' + window._clientProjectId);
                if (newUrl !== urlStr) {
                    console.log('[PROXY] 3. URL project replaced');
                    url = newUrl;
                }
            }

            try {
                var response = await origFetch.apply(this, [url, opts]);
                var cloned = response.clone();
                var data = await cloned.json();

                console.log('[PROXY] Status:', response.status);

                if (response.status === 200 && data.media) {
                    window._response = data;
                    console.log('[PROXY] OK! ' + data.media.length + ' images');
                } else if (data.error) {
                    window._response = {error: data.error};
                    window._responseError = 'Error ' + (data.error.code || response.status) + ': ' + (data.error.message || '');
                    console.log('[PROXY] ERROR:', window._responseError);
                } else {
                    window._response = data;
                }

                window._requestPending = false;
                return response;
            } catch(e) {
                window._responseError = 'Fetch error: ' + e.message;
                window._requestPending = false;
                return origFetch.apply(this, [url, opts]);
            }
        }

        return origFetch.apply(this, [url, opts]);
    };

    return 'PROXY_INTERCEPTOR_READY';
})();
"""


def get_server_accounts() -> list:
    """
    Đọc danh sách tài khoản server từ Google Sheet.
    Sheet: "SERVER", Cột B: tài khoản (format: email|password|2fa mỗi dòng)

    Returns: [{"id": "email", "password": "pass", "totp_secret": "..."}, ...]
    """
    try:
        sys.path.insert(0, str(TOOL_DIR))
        from google_login import load_gsheet_client, parse_accounts_cell, col_letter_to_index

        gc, spreadsheet_name = load_gsheet_client()
        if not gc:
            print("[SERVER] Khong load duoc Google Sheet client")
            return []

        ws = gc.open(spreadsheet_name).worksheet("SERVER")
        all_data = ws.get_all_values()

        if not all_data:
            print("[SERVER] Sheet 'SERVER' trong!")
            return []

        # Cot B (index 1) chua tai khoan - doc tat ca dong
        accounts = []
        col_b = col_letter_to_index("B")  # = 1

        for row_idx, row in enumerate(all_data, start=1):
            if len(row) <= col_b:
                continue

            cell_value = str(row[col_b]).strip()
            if not cell_value:
                continue

            # Parse tung dong trong cell (co the co nhieu tai khoan trong 1 cell)
            parsed = parse_accounts_cell(cell_value)
            if parsed:
                accounts.extend(parsed)

        if accounts:
            print(f"[SERVER] Tim thay {len(accounts)} tai khoan tu sheet 'SERVER':")
            for i, acc in enumerate(accounts):
                has_2fa = " [2FA]" if acc.get('totp_secret') else ""
                print(f"  {i+1}. {acc['id']}{has_2fa}")

        return accounts

    except Exception as e:
        print(f"[SERVER] Loi doc sheet 'SERVER': {e}")
        return []


class ChromeSession:
    """Quản lý Chrome session cho proxy server."""

    def __init__(self, chrome_portable_path: str = None, port: int = 19222, ipv6: str = ""):
        """
        Args:
            chrome_portable_path: Đường dẫn tới ChromePortable.exe
                                  Mặc định: {tool_dir}/GoogleChromePortable/GoogleChromePortable.exe
            port: Debug port cho Chrome (mặc định 19222 - không trùng với workers 9222/9223)
            ipv6: IPv6 address - nếu có sẽ tạo SOCKS5 proxy để Chrome dùng IPv6
        """
        if chrome_portable_path:
            self.chrome_path = Path(chrome_portable_path)
        else:
            self.chrome_path = TOOL_DIR / "GoogleChromePortable" / "GoogleChromePortable.exe"

        self.chrome_data = self.chrome_path.parent / "Data" / "profile"
        self.port = port
        self.ipv6 = ipv6.strip() if ipv6 else ""
        self._proxy_port = 0  # SOCKS5 proxy port (set khi start proxy)
        self._proxy = None  # IPv6SocksProxy instance
        self.page = None
        self.ready = False
        self.project_url = None
        self._image_mode_selected = False
        self._account = None  # Tai khoan dang dung
        self._fingerprint_seed = 0  # 0 = no spoof, >0 = spoof active
        self._consecutive_403 = 0   # Dem 403 lien tiep
        self._current_model_index = 0  # 0=Nano Banana Pro, 1=Nano Banana 2, 2=Imagen 4
        self._cleared_data_for_403 = False  # Da clear data chua

    def log(self, msg: str, level: str = "INFO"):
        prefix = {"INFO": "[INFO]", "OK": "[OK]", "WARN": "[WARN]", "ERROR": "[ERROR]"}
        print(f"  {prefix.get(level, '[INFO]')} {msg}")

    # ============================================================
    # Fingerprint Spoof - Doi fingerprint khi bi 403
    # ============================================================

    def inject_fingerprint_spoof(self):
        """
        Inject fingerprint spoof JS.

        Su dung CDP Page.addScriptToEvaluateOnNewDocument de inject TRUOC khi
        page scripts chay → Google khong thay fingerprint that.
        Dong thoi chay run_js() cho page hien tai.
        """
        if self._fingerprint_seed <= 0 or not self.page:
            return
        try:
            js = _build_fingerprint_js(self._fingerprint_seed)

            # 1. CDP: Inject cho TAT CA page loads sau nay (TRUOC khi scripts chay)
            try:
                # Xoa script cu (neu co)
                if hasattr(self, '_spoof_script_id') and self._spoof_script_id:
                    try:
                        self.page.run_cdp('Page.removeScriptToEvaluateOnNewDocument',
                                          identifier=self._spoof_script_id)
                    except Exception:
                        pass

                result = self.page.run_cdp('Page.addScriptToEvaluateOnNewDocument',
                                            source=js)
                self._spoof_script_id = result.get('identifier', '')
                self.log(f"[SPOOF] CDP pre-load inject OK (seed={self._fingerprint_seed})")
            except Exception as e:
                self.log(f"[SPOOF] CDP inject failed ({e}), fallback run_js", "WARN")

            # 2. run_js: Cho page HIEN TAI (da load roi)
            self.page.run_js(js)

            # 3. VERIFY: Kiem tra fingerprint co hoat dong khong
            try:
                verify = self.page.run_js("""
                    var c = navigator.hardwareConcurrency;
                    var m = navigator.deviceMemory || 'N/A';
                    var w = screen.width;
                    var h = screen.height;
                    var gl = null;
                    try {
                        var canvas = document.createElement('canvas');
                        var ctx = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                        if (ctx) gl = ctx.getParameter(37446);
                    } catch(e) {}
                    return 'cores=' + c + ' mem=' + m + ' screen=' + w + 'x' + h + ' gpu=' + (gl || 'N/A').substring(0, 40);
                """)
                self.log(f"[SPOOF] VERIFY: {verify}")
            except Exception:
                pass
        except Exception as e:
            self.log(f"[SPOOF] Inject error: {e}", "WARN")

    def rotate_ipv6(self, new_ip: str = "") -> bool:
        """
        Doi IPv6 address va restart SOCKS5 proxy.

        Args:
            new_ip: IPv6 moi (tu ChromePool). Neu rong → tu tim tu ipv6_rotator.

        Returns: True neu doi thanh cong.
        """
        try:
            if not new_ip:
                # Fallback: tu tim tu ipv6_rotator
                from modules.ipv6_rotator import get_ipv6_rotator
                rotator = get_ipv6_rotator()
                if not rotator or not rotator.enabled or not rotator.ipv6_list:
                    self.log("[IPv6] Khong co IPv6 de rotate", "WARN")
                    return False
                new_ip = rotator.rotate()
                if not new_ip:
                    self.log("[IPv6] Rotate failed!", "WARN")
                    return False

            old_ip = self.ipv6
            self.ipv6 = new_ip
            self.log(f"[IPv6] Rotated: {old_ip[:20]}... → {new_ip[:20]}...", "OK")

            # Restart SOCKS5 proxy voi IP moi
            if self._proxy:
                try:
                    self._proxy.stop()
                except Exception:
                    pass

            # Tao proxy moi (ke ca khi truoc do khong co proxy)
            if not self._proxy_port:
                self._proxy_port = self.port + 200
            try:
                from modules.ipv6_proxy import IPv6SocksProxy
                self._proxy = IPv6SocksProxy(
                    listen_port=self._proxy_port,
                    ipv6_address=new_ip,
                    log_func=lambda msg: self.log(f"[PROXY] {msg}"),
                )
                if self._proxy.start():
                    self.log(f"[IPv6] SOCKS5 proxy restarted OK", "OK")
                else:
                    self.log(f"[IPv6] SOCKS5 proxy restart FAILED!", "ERROR")
                    return False
            except Exception as e:
                self.log(f"[IPv6] Proxy restart error: {e}", "ERROR")
                return False

            return True
        except Exception as e:
            self.log(f"[IPv6] Rotate error: {e}", "WARN")
            return False

    def restart_with_new_fingerprint(self, clear_data: bool = False) -> bool:
        """
        Restart Chrome voi fingerprint moi.
        Goi khi bi 403 lien tiep.

        Args:
            clear_data: True = xoa Chrome data (force re-login).
                        False = chi restart Chrome (giu login, nhanh hon).

        Returns: True neu restart thanh cong.
        """
        import random
        self._fingerprint_seed = random.randint(10000, 99999)
        action = "RESTART + CLEAR DATA" if clear_data else "RESTART (giu data)"
        self.log(f"[SPOOF] === {action} voi fingerprint moi (seed={self._fingerprint_seed}) ===")

        # 1. Dong Chrome hien tai
        try:
            if self.page:
                self.page.quit()
        except Exception:
            pass
        self.page = None
        self.ready = False

        # 2. Clear Chrome data CHI KHI duoc yeu cau
        if clear_data:
            self._clear_chrome_data()

        # 3. Setup lai (setup() se goi inject_fingerprint_spoof)
        ok = self.setup(skip_403_reset=True)
        if ok:
            self.log(f"[SPOOF] Restart OK - fingerprint moi active", "OK")
        else:
            self.log(f"[SPOOF] Restart FAIL!", "ERROR")
        return ok

    # ============================================================
    # Setup - Khởi tạo Chrome + vào Flow + tạo project
    # ============================================================

    def _clear_chrome_data(self):
        """Xoa Chrome data (giu First Run) de force fresh login."""
        import shutil
        data_dir = self.chrome_data
        if not data_dir.exists():
            return

        self.log(f"Clear Chrome data: {data_dir}")
        first_run = data_dir / "First Run"
        has_first_run = first_run.exists()

        for item in data_dir.iterdir():
            if item.name == "First Run":
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(str(item), ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except Exception:
                pass

        # Tao lai First Run neu can
        if not has_first_run:
            try:
                first_run.touch()
            except Exception:
                pass
        self.log("Chrome data cleared", "OK")

    def _check_current_account(self) -> str:
        """
        Check email dang login trong Chrome hien tai.
        Mo myaccount.google.com → doc email.
        Returns: email string hoac "" neu chua login.
        """
        try:
            if not self.page:
                return ""
            self.page.get("https://myaccount.google.com")
            time.sleep(3)

            current_url = self.page.url or ''
            # Neu redirect ve accounts.google.com → chua login
            if 'accounts.google.com' in current_url:
                return ""

            # Doc email tu page
            email = self.page.run_js("""
                // Tim email trong page
                var els = document.querySelectorAll('[data-email]');
                if (els.length > 0) return els[0].getAttribute('data-email');

                // Fallback: tim text co @ trong header area
                var all = document.querySelectorAll('header *');
                for (var i = 0; i < all.length; i++) {
                    var t = all[i].textContent.trim();
                    if (t.indexOf('@') > 0 && t.indexOf('.') > 0 && t.length < 60) {
                        return t;
                    }
                }

                // Fallback 2: tim trong aria-label
                var btns = document.querySelectorAll('[aria-label*="@"]');
                if (btns.length > 0) {
                    var label = btns[0].getAttribute('aria-label');
                    var match = label.match(/[\\w.-]+@[\\w.-]+/);
                    if (match) return match[0];
                }

                return '';
            """)
            return str(email or '').strip().lower()
        except Exception as e:
            self.log(f"Check account error: {e}", "WARN")
            return ""

    def setup(self, skip_403_reset: bool = False) -> bool:
        """
        Full setup:
        1. Mở Chrome → check account hiện tại
        2. Nếu sai account → clear data + login đúng account
        3. Vào labs.google/fx/tools/flow
        4. Tạo project mới
        5. Đợi textarea sẵn sàng

        Args:
            skip_403_reset: True = khong reset 403 counter (khi restart tu 403 handler)

        Returns: True nếu sẵn sàng
        """
        print("\n[SETUP] Khởi tạo Chrome session...")

        # 1. Check Chrome exists
        if not self.chrome_path.exists():
            self.log(f"Chrome not found: {self.chrome_path}", "ERROR")
            return False

        # 2. Mở Chrome trước để check account
        self.log(f"Mở Chrome: {self.chrome_path}")
        self.log(f"Data: {self.chrome_data}")
        self.log(f"Port: {self.port}")

        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.set_browser_path(str(self.chrome_path))
        co.set_user_data_path(str(self.chrome_data))
        co.set_address(f'127.0.0.1:{self.port}')
        co.set_argument('--no-first-run')
        co.set_argument('--no-default-browser-check')

        # IPv6: Start SOCKS5 proxy và set Chrome dùng proxy
        if self.ipv6:
            self._proxy_port = self.port + 200  # VD: port 19222 → proxy 19422
            self.log(f"IPv6: {self.ipv6}")
            self.log(f"Starting SOCKS5 proxy on 127.0.0.1:{self._proxy_port}...")
            try:
                from modules.ipv6_proxy import IPv6SocksProxy
                self._proxy = IPv6SocksProxy(
                    listen_port=self._proxy_port,
                    ipv6_address=self.ipv6,
                    log_func=lambda msg: self.log(f"[PROXY] {msg}"),
                )
                if self._proxy.start():
                    self.log(f"SOCKS5 proxy READY → Chrome sẽ dùng IPv6", "OK")
                    co.set_argument(f'--proxy-server=socks5://127.0.0.1:{self._proxy_port}')
                    co.set_argument('--proxy-bypass-list=<-loopback>')
                else:
                    self.log(f"SOCKS5 proxy FAILED! Chrome sẽ dùng IPv4", "ERROR")
            except Exception as e:
                self.log(f"IPv6 proxy error: {e}", "ERROR")

        try:
            self.page = ChromiumPage(co)
            self.log(f"Chrome opened: {self.page.title}", "OK")
        except Exception as e:
            self.log(f"Chrome failed: {e}", "ERROR")
            return False

        # 2b. Inject fingerprint NGAY SAU khi mo Chrome, TRUOC khi navigate
        # CDP addScriptToEvaluateOnNewDocument se chay TRUOC moi page load
        # → Google chi thay fingerprint gia tu dau
        if self._fingerprint_seed > 0:
            self.inject_fingerprint_spoof()

        # 3. Check account hien tai
        need_login = False
        if self._account:
            target_email = self._account['id'].strip().lower()
            current_email = self._check_current_account()
            self.log(f"Account hien tai: {current_email or '(chua login)'}")
            self.log(f"Account can dung: {target_email}")

            if current_email == target_email:
                self.log("Account DUNG → khong can login lai", "OK")
            else:
                self.log(f"Account SAI hoac chua login → clear data + login", "WARN")
                need_login = True
        else:
            # Khong co account assign → chi check da login chua
            pass

        # 4. Login neu can
        if need_login:
            # Dong Chrome hien tai
            try:
                self.page.quit()
            except Exception:
                pass
            self.page = None

            # Clear data + login
            self._clear_chrome_data()
            login_ok = self._auto_login()
            if not login_ok:
                self.log(f"Dang nhap that bai: {self._account['id']}", "ERROR")
                return False

            # Mo lai Chrome sau login
            co2 = ChromiumOptions()
            co2.set_browser_path(str(self.chrome_path))
            co2.set_user_data_path(str(self.chrome_data))
            co2.set_address(f'127.0.0.1:{self.port}')
            co2.set_argument('--no-first-run')
            co2.set_argument('--no-default-browser-check')
            # IPv6 proxy (neu da start o tren)
            if self._proxy and self._proxy._running:
                co2.set_argument(f'--proxy-server=socks5://127.0.0.1:{self._proxy_port}')
                co2.set_argument('--proxy-bypass-list=<-loopback>')
            try:
                self.page = ChromiumPage(co2)
                self.log(f"Chrome mo lai: {self.page.title}", "OK")
            except Exception as e:
                self.log(f"Chrome restart failed: {e}", "ERROR")
                return False

            # Inject fingerprint NGAY sau khi mo lai Chrome
            if self._fingerprint_seed > 0:
                self.inject_fingerprint_spoof()

        # 5. Vào Flow page
        self.log(f"Vao Flow: {FLOW_URL}")
        self.page.get(FLOW_URL)
        time.sleep(5)
        self.inject_fingerprint_spoof()

        current_url = self.page.url or ''
        self.log(f"URL: {current_url}")

        # Check login fallback (cho truong hop khong co _account)
        if 'accounts.google.com' in current_url:
            self.log("Chua dang nhap! Tu dong dang nhap...", "WARN")
            login_ok = self._auto_login()
            if not login_ok:
                self.log("Dang nhap that bai!", "ERROR")
                return False
            # Vao lai Flow sau khi login
            self.page.get(FLOW_URL)
            time.sleep(5)
            self.inject_fingerprint_spoof()
            current_url = self.page.url or ''

        # 6. Tạo project mới
        if '/project/' not in current_url:
            success = self._create_new_project()
            if not success:
                self.log("Không tạo được project mới!", "ERROR")
                return False

        # 7. Đợi textarea
        if self._wait_for_textarea():
            self.ready = True
            self.project_url = self.page.url
            self.log(f"READY! Project: {self.project_url}", "OK")
            return True

        # v1.0.506: Textarea không xuất hiện → có thể đang ở trang "Create with Flow"
        # (giống API mode: đã login nhưng page chưa sẵn sàng)
        self.log("Textarea khong xuat hien - check Create with Flow...", "WARN")
        if self._handle_create_with_flow_page():
            # Đã qua trang Create with Flow → thử tạo project mới
            try:
                current_url = self.page.url or ''
                if '/project/' not in current_url:
                    success = self._create_new_project()
                    if not success:
                        self.log("Khong tao duoc project sau Create with Flow!", "ERROR")
                        return False
            except:
                pass
            # Đợi textarea lần nữa
            if self._wait_for_textarea():
                self.ready = True
                self.project_url = self.page.url
                self.log(f"READY! Project: {self.project_url}", "OK")
                return True

        self.log("Textarea không xuất hiện!", "ERROR")
        return False

    def _click_create_with_flow(self) -> bool:
        """Click nút 'Create with Flow' / 'Tạo với Flow' nếu có. (giống API mode)"""
        try:
            click_result = self.page.run_js('''
                (function() {
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var text = (b.textContent || '').trim();
                        if (text.includes('Create with Flow') || text.includes('Tạo với Flow')) {
                            b.click();
                            return 'CLICKED';
                        }
                    }
                    var spans = document.querySelectorAll('span');
                    for (var s of spans) {
                        var text = (s.textContent || '').trim();
                        if (text.includes('Create with Flow') || text.includes('Tạo với Flow')) {
                            var btn = s.closest('button');
                            if (btn) { btn.click(); return 'CLICKED_VIA_SPAN'; }
                        }
                    }
                    return 'NOT_FOUND';
                })();
            ''')
            if click_result and 'CLICKED' in str(click_result):
                return True
        except:
            pass
        return False

    def _dismiss_popups(self):
        """Dismiss popup thông báo (Bắt đầu / Get started / Got it). (giống API mode)"""
        try:
            for sel in ['tag:button@@text():Bắt đầu', 'tag:button@@text():Get started',
                        'tag:button@@text():Bắt Đầu', 'tag:button@@text():Got it',
                        'tag:button@@text():Dismiss']:
                try:
                    btn = self.page.ele(sel, timeout=0.5)
                    if btn:
                        btn.click()
                        self.log(f"Dismissed popup: {sel.split(':')[-1]}")
                        time.sleep(1)
                        return True
                except:
                    continue
        except:
            pass
        return False

    def _create_new_project(self) -> bool:
        """
        v1.0.508: Tạo project mới - COPY Y NGUYÊN logic từ API mode warmup flow.
        1 vòng lặp 20 lần: check Create with Flow + Dự án mới + dismiss popup + reload mỗi 5 lần.
        """
        self.log("Tạo project mới...")
        time.sleep(2)

        # Vòng lặp giống API mode warmup (20 lần retry, reload mỗi 5)
        for attempt in range(20):
            # Check URL - có thể đã vào project rồi
            try:
                current_url = self.page.url or ''
                if '/project/' in current_url:
                    self.log(f"Da vao project: {current_url}", "OK")
                    return True
            except:
                pass

            # Dismiss popup (Bắt đầu / Get started / Got it)
            self._dismiss_popups()

            # Tìm button "Dự án mới" (add_2) - đây là mục tiêu
            try:
                btn = self.page.ele('tag:button@@text():add_2', timeout=1)
                if btn:
                    self.log(f"Clicked 'Du an moi' (attempt {attempt+1})", "OK")
                    btn.click()
                    time.sleep(3)
                    # Đợi vào project
                    for w in range(30):
                        try:
                            if '/project/' in (self.page.url or ''):
                                self.log(f"Project created: {self.page.url}", "OK")
                                return True
                        except:
                            pass
                        time.sleep(1)
                        if w % 10 == 9:
                            self.log(f"  ... doi vao project {w+1}s")
                    # Vẫn chưa vào → tiếp tục retry
                    self.log("Click 'Du an moi' nhung chua vao project, thu lai...", "WARN")
                    continue
            except:
                pass

            # Thử JS click "Dự án mới"
            try:
                result = self.page.run_js(JS_CLICK_NEW_PROJECT)
                if result and 'CLICKED' in str(result):
                    self.log(f"Clicked 'Du an moi' JS (attempt {attempt+1})", "OK")
                    time.sleep(3)
                    for w in range(30):
                        try:
                            if '/project/' in (self.page.url or ''):
                                self.log(f"Project created: {self.page.url}", "OK")
                                return True
                        except:
                            pass
                        time.sleep(1)
                    self.log("Click 'Du an moi' JS nhung chua vao project, thu lai...", "WARN")
                    continue
            except Exception as e:
                if "ContextLost" in str(type(e).__name__) or "refresh" in str(e).lower():
                    self.log("Page dang refresh, doi...")
                    time.sleep(2)
                    try:
                        if '/project/' in (self.page.url or ''):
                            return True
                    except:
                        pass
                    continue

            # Thử click "Create with Flow" nếu có (giống API mode)
            if self._click_create_with_flow():
                self.log(f"Clicked 'Create with Flow' ({attempt+1}/20)")
                time.sleep(1)
                continue  # Check lại ngay

            # Reload page mỗi 5 lần
            if attempt > 0 and attempt % 5 == 0:
                self.log(f"Reload Flow page ({attempt}/20)...", "WARN")
                try:
                    self.page.get(FLOW_URL)
                    time.sleep(3)
                except:
                    pass

            time.sleep(0.5)

        self.log("Khong tao duoc project sau 20 lan!", "ERROR")
        return False

    def _wait_for_textarea(self, timeout: int = 30) -> bool:
        """Đợi textarea/contenteditable xuất hiện."""
        self.log("Đợi textarea...")

        for i in range(timeout):
            result = self.page.run_js("""
                var ce = document.querySelector('[contenteditable="true"]');
                var ta = document.querySelector('textarea:not([class*="recaptcha"])');
                if (ce) return 'contenteditable';
                if (ta) return 'textarea';
                return 'not_found';
            """)

            if result and result != 'not_found':
                self.log(f"Input ready: {result}", "OK")
                return True

            time.sleep(1)

        return False

    # ============================================================
    # Generate Image - Tạo ảnh cho khách
    # ============================================================

    def generate_image(self, client_bearer_token: str, client_project_id: str,
                       client_prompt: str, model_name: str = 'GEM_PIX_2',
                       aspect_ratio: str = 'IMAGE_ASPECT_RATIO_LANDSCAPE',
                       seed: int = None, image_inputs: list = None) -> dict:
        """
        Tạo ảnh - giống y hệt test_local_proxy.py (đã hoạt động).

        Flow (copy từ test):
        1. Vào project URL
        2. Inject interceptor (thay token + projectId)
        3. Setup image mode + model
        4. Paste prompt → đợi 4s recaptcha → Enter
        5. Chờ response → trả base64

        Returns: { media: [...] } hoặc { error: "..." }
        """
        if not self.page:
            return {"error": "Chrome not initialized"}

        self.log(f"=== Generate Image ===")
        self.log(f"Token: {client_bearer_token[:20]}...{client_bearer_token[-10:]}")
        self.log(f"ProjectId: {client_project_id}")
        self.log(f"Prompt: {client_prompt[:60]}...")

        try:
            # 1. Vào project (giống test step 2)
            if self.project_url:
                self.page.get(self.project_url)
            else:
                self.page.get(FLOW_URL)
            time.sleep(5)
            self.inject_fingerprint_spoof()

            # Đợi textarea
            if not self._wait_for_textarea(timeout=20):
                self.log("Textarea not found, tao project moi...", "WARN")
                if not self._create_new_project():
                    return {"error": "Cannot create project"}
                if not self._wait_for_textarea(timeout=20):
                    return {"error": "Textarea not found after project creation"}
                self.project_url = self.page.url

            # 2. Inject interceptor (giống test file - reset trước khi inject)
            self.log("Inject interceptor...")
            if image_inputs:
                self.log(f"Reference images: {len(image_inputs)} media ID(s)")
            # Reset state trước (giống test file)
            self.page.run_js("window.__proxyInterceptReady = false; window._response = null; window._responseError = null; window._requestPending = false;")
            time.sleep(0.5)
            js = build_interceptor_js(client_bearer_token, client_project_id, image_inputs)
            r = self.page.run_js(js)
            self.log(f"Interceptor: {r}")

            # 3. Setup Image mode + model (giống test step 4)
            # v1.0.487: Dung _current_model_index khi da switch model do 403
            model_index = self._current_model_index if self._current_model_index > 0 else MODEL_INDEX_MAP.get(model_name, 0)
            self.log(f"Setup Image mode (model index: {model_index})...")
            js_model = JS_SELECT_MODEL.replace('MODEL_INDEX', str(model_index))
            self.page.run_js("window._modelSelectResult = 'PENDING';")
            self.page.run_js(js_model)
            time.sleep(7)

            model_result = self.page.run_js("return window._modelSelectResult;")
            self.log(f"Model result: {model_result}")

            # 4. Paste prompt (giống test step 5)
            self.log(f"Paste prompt...")
            ok = self._paste_prompt(client_prompt)
            if not ok:
                return {"error": "Cannot paste prompt"}

            # 5. Đợi recaptcha 4s → Enter (giống test step 6)
            self.log("Doi recaptcha (4s)...")
            time.sleep(4)

            from DrissionPage.common import Keys
            self.page.actions.key_down(Keys.ENTER).key_up(Keys.ENTER)
            self.log("Enter sent!")

            # 6. Chờ response (giống test step 7)
            result = self._wait_for_response(timeout=120)

            # 7. Cleanup browser data sau mỗi request (tránh bị Google track/flag)
            try:
                self.page.run_js(JS_CLEANUP)
                self.log("Cleanup browser data OK")
            except Exception as ce:
                self.log(f"Cleanup warning: {ce}", "WARN")

            return result

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def _paste_prompt(self, prompt: str) -> bool:
        """Paste prompt bằng Ctrl+V (giống tool)."""
        import pyperclip
        from DrissionPage.common import Keys

        # Focus input
        input_type = self.page.run_js("""
            var ce = document.querySelector('[contenteditable="true"]');
            var ta = document.querySelector('textarea:not([class*="recaptcha"])');
            if (ce) { ce.focus(); ce.click(); return 'contenteditable'; }
            if (ta) { ta.focus(); ta.click(); return 'textarea'; }
            return 'not_found';
        """)

        if input_type == 'not_found':
            for _ in range(5):
                time.sleep(1)
                input_type = self.page.run_js("""
                    var ce = document.querySelector('[contenteditable="true"]');
                    var ta = document.querySelector('textarea:not([class*="recaptcha"])');
                    if (ce) { ce.focus(); ce.click(); return 'contenteditable'; }
                    if (ta) { ta.focus(); ta.click(); return 'textarea'; }
                    return 'not_found';
                """)
                if input_type != 'not_found':
                    break

        if input_type == 'not_found':
            self.log("Input not found!", "ERROR")
            return False

        self.log(f"Input type: {input_type}")
        time.sleep(0.3)

        # Ctrl+A → Ctrl+V
        self.page.actions.key_down(Keys.CONTROL).key_down('a').key_up('a').key_up(Keys.CONTROL)
        time.sleep(0.2)

        pyperclip.copy(prompt)
        self.page.actions.key_down(Keys.CONTROL).key_down('v').key_up('v').key_up(Keys.CONTROL)
        time.sleep(0.5)

        # Verify
        actual = self.page.run_js("""
            var ce = document.querySelector('[contenteditable="true"]');
            if (ce) return ce.textContent.substring(0, 80);
            var ta = document.querySelector('textarea:not([class*="recaptcha"])');
            if (ta) return ta.value.substring(0, 80);
            return '';
        """)
        self.log(f"Verified: '{actual}'")
        return bool(actual and actual.strip())

    def _wait_for_response(self, timeout: int = 120) -> dict:
        """Chờ response từ interceptor."""
        self.log(f"Chờ response ({timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            elapsed = time.time() - start

            state = self.page.run_js("""
                return {
                    pending: window._requestPending,
                    hasResponse: !!window._response,
                    error: window._responseError
                };
            """)

            if state and state.get('error'):
                self.log(f"ERROR: {state['error']}", "ERROR")
                data = self.page.run_js("return window._response;")
                if data and isinstance(data, dict) and 'error' in data:
                    return {"error": data['error']}
                return {"error": state['error']}

            if state and state.get('hasResponse') and not state.get('error'):
                self.log(f"Response sau {elapsed:.1f}s!", "OK")
                data = self.page.run_js("return window._response;")

                if isinstance(data, dict) and 'media' in data:
                    # Download images (convert fifeUrl → base64 nếu cần)
                    media = data['media']
                    for i, item in enumerate(media):
                        gen_img = item.get('image', {}).get('generatedImage', {})
                        encoded = gen_img.get('encodedImage', '')
                        fife_url = gen_img.get('fifeUrl', '')

                        # Nếu không có base64 nhưng có URL → download
                        if not encoded and fife_url:
                            try:
                                import requests as req
                                r = req.get(fife_url, timeout=30)
                                if r.status_code == 200:
                                    gen_img['encodedImage'] = base64.b64encode(r.content).decode()
                                    self.log(f"Image {i+1} downloaded from URL ({len(r.content):,} bytes)", "OK")
                            except Exception as e:
                                self.log(f"Download failed: {e}", "WARN")

                    self.log(f"Got {len(media)} images", "OK")
                    return data

                return data or {"error": "Empty response"}

            # Log moi 30s (tranh spam)
            elapsed_int = int(elapsed)
            if elapsed_int > 0 and elapsed_int % 30 == 0 and elapsed_int != getattr(self, '_last_wait_log', 0):
                self._last_wait_log = elapsed_int
                self.log(f"... chờ ({elapsed_int}s/{timeout}s)")

            time.sleep(1)

        return {"error": f"Timeout {timeout}s"}

    # ============================================================
    # Auto Login - Doc tai khoan tu sheet "SERVER" cot B
    # ============================================================

    def _auto_login(self) -> bool:
        """
        Tu dong dang nhap Google.

        Uu tien:
        1. Dung self._account neu da set (tu ChromePool)
        2. Fallback: doc tu sheet SERVER + xoay vong
        """
        # 1. Uu tien account da duoc assign
        if self._account:
            account = self._account
            self.log(f"Dung account da assign: {account['id']}")
        else:
            # Fallback: doc tu sheet
            self.log("Doc tai khoan tu sheet 'SERVER' cot B...")
            accounts = get_server_accounts()
            if not accounts:
                self.log("Khong tim thay tai khoan!", "ERROR")
                return False

            server_index_file = TOOL_DIR / "config" / ".server_account_index.json"
            current_index = 0
            try:
                if server_index_file.exists():
                    data = json.loads(server_index_file.read_text(encoding='utf-8'))
                    current_index = data.get('index', 0)
                    if current_index >= len(accounts):
                        current_index = 0
            except Exception:
                pass

            account = accounts[current_index]
            self._account = account
            self.log(f"Dung tai khoan {current_index + 1}/{len(accounts)}: {account['id']}")

        # 2. Goi login
        try:
            sys.path.insert(0, str(TOOL_DIR))
            from google_login import login_google_chrome

            # Dong Chrome hien tai truoc khi login
            if self.page:
                try:
                    self.page.quit()
                except Exception:
                    pass
                self.page = None

            # Dung port rieng cho login (tranh trung voi port chinh)
            login_port = self.port + 100  # 19222 → 19322, etc.

            success = login_google_chrome(
                account_info=account,
                chrome_portable=str(self.chrome_path),
                profile_dir=str(self.chrome_data),
                worker_id=login_port - 9222,  # worker_id de tinh port
            )

            if success:
                self.log(f"Dang nhap thanh cong: {account['id']}", "OK")
                # KHONG mo lai Chrome o day - setup() se mo sau
                return True
            else:
                self.log(f"Dang nhap that bai: {account['id']}", "ERROR")
                return False

        except Exception as e:
            self.log(f"Loi dang nhap: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return False

    # ============================================================
    # Cleanup / Restart
    # ============================================================

    def restart_chrome(self):
        """Restart Chrome (clear data + reopen)."""
        self.log("Restarting Chrome...")
        self.ready = False

        try:
            if self.page:
                self.page.run_js(JS_CLEANUP)
                time.sleep(1)
        except Exception:
            pass

        # Re-setup
        self.setup()

    def close(self):
        """Close Chrome."""
        self.ready = False
        try:
            if self.page:
                self.page.quit()
        except Exception:
            pass
        self.page = None
