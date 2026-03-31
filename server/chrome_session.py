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

# v1.0.512: Import tu fingerprint_data.py (pool 65 GPU, 15 screen, 53M+ combos)
from modules.fingerprint_data import (
    FAKE_GPUS as _FAKE_GPUS,
    FAKE_SCREENS as _FAKE_SCREENS,
    FAKE_CORES as _FAKE_CORES,
    FAKE_MEMORY as _FAKE_MEMORY,
    build_fingerprint_js as _build_fingerprint_js,
    get_unique_seed as _get_unique_seed,
)


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

# v1.0.634: JS chuyen sang Video mode
# Flow: Open settings → Video tab → Thanh phan (VIDEO_REFERENCES) → LANDSCAPE → x1 → chon model bat ky
# Khong bat buoc Lower Priority - server Chrome chi can o Video mode, interceptor se thay model tu VM
JS_SELECT_VIDEO_MODE = """
(function() {
    window._videoModeResult = 'PENDING';

    // 1. Check panel da mo chua, neu chua thi mo settings
    var vidTab = document.querySelector('[id*="trigger-IMAGE"]');
    if (!vidTab) vidTab = document.querySelector('[id*="trigger-VIDEO"]:not([id*="FRAMES"]):not([id*="REFERENCES"])');
    if (!vidTab || vidTab.getBoundingClientRect().width === 0) {
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
            console.log('[VIDEO-MODE] 1. Opened settings: ' + btn1.textContent.trim().substring(0, 40));
        } else {
            console.log('[VIDEO-MODE] 1. WARN: No settings button found');
        }
    } else {
        console.log('[VIDEO-MODE] 1. Panel already open');
    }

    setTimeout(function() {
        // 2. Click tab Video (MouseEvent cho Radix)
        var tabs = document.querySelectorAll('[role="tab"]');
        for (var i = 0; i < tabs.length; i++) {
            if ((tabs[i].id || '').indexOf('trigger-VIDEO') >= 0 && (tabs[i].id || '').indexOf('FRAMES') < 0 && (tabs[i].id || '').indexOf('REFERENCES') < 0) {
                tabs[i].dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                tabs[i].dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                tabs[i].dispatchEvent(new MouseEvent('click', {bubbles: true}));
                console.log('[VIDEO-MODE] 2. Video tab: ' + tabs[i].getAttribute('data-state'));
                break;
            }
        }

        // 3. Click Thanh phan (VIDEO_REFERENCES) = I2V mode
        setTimeout(function() {
            var tp = document.querySelector('[id*="trigger-VIDEO_REFERENCES"]');
            if (tp) {
                tp.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                tp.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                tp.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                console.log('[VIDEO-MODE] 3. Thanh phan: ' + tp.getAttribute('data-state'));
            }

            setTimeout(function() {
                // 4. Click LANDSCAPE (16:9)
                var t169 = document.querySelector('[id*="trigger-LANDSCAPE"]');
                if (t169) {
                    t169.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                    t169.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                    t169.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    console.log('[VIDEO-MODE] 4. 16:9');
                }

                // 5. Click x1
                setTimeout(function() {
                    var x1 = document.querySelector('[id*="trigger-1"]');
                    if (x1) {
                        x1.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        x1.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        x1.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        console.log('[VIDEO-MODE] 5. x1');
                    }

                    // 6. Mo model dropdown
                    setTimeout(function() {
                        var btns = document.querySelectorAll('button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = btns[i].textContent.trim();
                            if (t.indexOf('arrow_drop_down') >= 0 && (t.indexOf('Veo') >= 0 || t.indexOf('Fast') >= 0)) {
                                btns[i].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                btns[i].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                console.log('[VIDEO-MODE] 6. Dropdown: ' + t.substring(0, 40));
                                break;
                            }
                        }

                        // 7. Chon model bat ky (chi can o Video mode, interceptor se thay model tu VM)
                        setTimeout(function() {
                            var items = document.querySelectorAll('[role="menuitem"]');
                            if (items.length > 0) {
                                // Chon model dau tien co san
                                items[0].dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                items[0].dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                items[0].click();
                                console.log('[VIDEO-MODE] 7. Selected: ' + items[0].textContent.substring(0, 40));
                                window._videoModeResult = 'SUCCESS';
                            }
                            // 8. Dong menu
                            setTimeout(function() {
                                document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                                document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
                                console.log('[VIDEO-MODE] 8. Done! ' + window._videoModeResult);
                            }, 500);
                        }, 800);
                    }, 500);
                }, 300);
            }, 300);
        }, 500);
    }, 1500);
})();
"""


def build_video_interceptor_js(client_bearer_token: str, client_project_id: str,
                                media_id: str, video_model: str = '') -> str:
    """
    v1.0.634: Video interceptor - THAY bearer token + projectId + inject mediaId + videoModelKey.

    Chrome DA O VIDEO MODE (da click chuyen sang video UI).
    Interceptor:
    - Thay token → client's token (VM co quyen Lower Priority)
    - Thay projectId → client's projectId
    - Inject referenceImages voi mediaId (anh lam khung dau)
    - Thay videoModelKey → model VM yeu cau (VD: lower priority)
    - GIU NGUYEN recaptchaToken tu Chrome (hop le cho video mode)
    """
    safe_token = client_bearer_token.replace("\\", "\\\\").replace("'", "\\'")
    safe_project = client_project_id.replace("\\", "\\\\").replace("'", "\\'")
    safe_media = media_id.replace("\\", "\\\\").replace("'", "\\'")
    safe_model = video_model.replace("\\", "\\\\").replace("'", "\\'") if video_model else ''

    return """
window._response = null;
window._responseError = null;
window._requestPending = false;
window._videoResponse = null;
window._videoError = null;
window._videoPending = false;
window._clientBearerToken = '""" + safe_token + """';
window._clientProjectId = '""" + safe_project + """';
window._clientMediaId = '""" + safe_media + """';
window._clientVideoModel = '""" + safe_model + """';

return (function() {
    if (window.__proxyInterceptReady) return 'ALREADY';
    window.__proxyInterceptReady = true;

    var origFetch = window.fetch;
    window.fetch = async function(url, opts) {
        var urlStr = typeof url === 'string' ? url : url.url;

        // Catch VIDEO request (batchAsync... hoac batchGenerate)
        if (urlStr.includes('aisandbox') && (urlStr.includes('batchAsync') || urlStr.includes('batchGenerate') || urlStr.includes('flowMedia') || urlStr.includes('video:'))) {
            console.log('[VIDEO-PROXY] Caught request:', urlStr.substring(0, 100));

            window._videoPending = true;
            window._videoResponse = null;
            window._videoError = null;

            // 1. THAY BEARER TOKEN
            if (window._clientBearerToken && opts) {
                if (!opts.headers) opts.headers = {};
                if (opts.headers instanceof Headers) {
                    opts.headers.set('Authorization', 'Bearer ' + window._clientBearerToken);
                } else {
                    opts.headers['Authorization'] = 'Bearer ' + window._clientBearerToken;
                }
                console.log('[VIDEO-PROXY] 1. Replaced bearer token');
            }

            // 2. THAY projectId + inject mediaId trong body
            if (opts && opts.body) {
                try {
                    var body = JSON.parse(opts.body);

                    // Thay projectId
                    if (body.clientContext && window._clientProjectId) {
                        body.clientContext.projectId = window._clientProjectId;
                        console.log('[VIDEO-PROXY] 2a. ProjectId → ' + window._clientProjectId);
                    }

                    // Inject referenceImages voi mediaId + thay videoModelKey
                    if (body.requests) {
                        body.requests.forEach(function(req) {
                            if (window._clientMediaId) {
                                req.referenceImages = [{
                                    imageUsageType: 'IMAGE_USAGE_TYPE_ASSET',
                                    mediaId: window._clientMediaId
                                }];
                                console.log('[VIDEO-PROXY] 2b. Injected mediaId: ' + window._clientMediaId.substring(0, 50) + '...');
                            }
                            if (window._clientVideoModel) {
                                req.videoModelKey = window._clientVideoModel;
                                console.log('[VIDEO-PROXY] 2c-model. videoModelKey → ' + window._clientVideoModel);
                            }
                        });
                    }

                    // GIU NGUYEN recaptchaToken tu Chrome!
                    var recaptcha = body.clientContext ? body.clientContext.recaptchaToken : '';
                    console.log('[VIDEO-PROXY] 2c. recaptchaToken kept: ' + (recaptcha ? recaptcha.substring(0, 20) + '...' : 'EMPTY'));

                    opts.body = JSON.stringify(body);
                } catch(e) {
                    console.log('[VIDEO-PROXY] Parse body error:', e);
                }
            }

            try {
                var response = await origFetch.apply(this, [url, opts]);
                var cloned = response.clone();
                try {
                    var data = await cloned.json();
                    console.log('[VIDEO-PROXY] Response status:', response.status);

                    if (response.status === 403 || (data.error && data.error.code === 403)) {
                        window._videoResponse = {error: data.error || {code: 403, message: 'Permission denied'}};
                        window._videoError = 'Error 403';
                    } else if (response.status === 429 || (data.error && (data.error.code === 429 || data.error.code === 253))) {
                        window._videoResponse = {error: data.error || {code: 429, message: 'Quota exceeded'}};
                        window._videoError = 'Error 429';
                    } else if (data.operations) {
                        console.log('[VIDEO-PROXY] Got ' + data.operations.length + ' operations!');
                        window._videoResponse = data;
                    } else if (data.error) {
                        window._videoResponse = {error: data.error};
                        window._videoError = 'Error: ' + (data.error.message || JSON.stringify(data.error));
                    } else {
                        window._videoResponse = data;
                    }
                } catch(e) {
                    window._videoResponse = {status: response.status, error: 'parse_failed'};
                }
                window._videoPending = false;
                return response;
            } catch(e) {
                window._videoError = 'Fetch error: ' + e.message;
                window._videoPending = false;
                return origFetch.apply(this, [url, opts]);
            }
        }

        return origFetch.apply(this, [url, opts]);
    };

    return 'PROXY_INTERCEPTOR_READY';
})();
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

    # v1.0.548: Dung return NGAY DAU de DrissionPage bat duoc gia tri tra ve
    return """
window._response = null;
window._responseError = null;
window._requestPending = false;
window._clientBearerToken = '""" + safe_token + """';
window._clientProjectId = '""" + safe_project + """';
window._imageInputs = """ + image_inputs_json + """;

return (function() {
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

    def __init__(self, chrome_portable_path: str = None, port: int = 19222, ipv6: str = "",
                 proxy_provider=None):
        """
        Args:
            chrome_portable_path: Đường dẫn tới ChromePortable.exe
                                  Mặc định: {tool_dir}/GoogleChromePortable/GoogleChromePortable.exe
            port: Debug port cho Chrome (mặc định 19222 - không trùng với workers 9222/9223)
            ipv6: IPv6 address - nếu có sẽ tạo SOCKS5 proxy để Chrome dùng IPv6
            proxy_provider: ProxyProvider instance (v1.0.545) - neu co thi dung thay IPv6
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
        # v1.0.545: ProxyProvider interface (thay the IPv6 truc tiep)
        self._proxy_provider = proxy_provider
        self.page = None
        self.ready = False
        self.project_url = None
        self._image_mode_selected = False
        self._account = None  # Tai khoan dang dung
        # v1.0.512: LUON tao fingerprint tu dau, khong doi 403
        self._fingerprint_seed = _get_unique_seed()
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

    def rotate_proxy(self, reason: str = "403") -> bool:
        """
        v1.0.545: Doi IP qua ProxyProvider (IPv6/Webshare/...).
        Goi method nay thay vi rotate_ipv6() khi dung ProxyProvider.

        Returns: True neu doi thanh cong.
        """
        if self._proxy_provider:
            ok = self._proxy_provider.rotate(reason)
            if ok:
                self.log(f"[PROXY] Rotated ({reason}): → {self._proxy_provider.get_current_ip()}", "OK")
            else:
                self.log(f"[PROXY] Rotate failed ({reason})", "WARN")
            return ok
        # Fallback: rotate_ipv6
        return self.rotate_ipv6()

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
        self._fingerprint_seed = _get_unique_seed()
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
            # v1.0.532: Reset project_url khi clear data (can tao project moi sau login)
            self.project_url = None

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

        # v1.0.545: ProxyProvider (uu tien) hoac IPv6 truc tiep (backward compat)
        if self._proxy_provider and self._proxy_provider.is_ready():
            # Dung ProxyProvider interface (IPv6/Webshare/...)
            chrome_arg = self._proxy_provider.get_chrome_arg()
            if chrome_arg:
                self.log(f"Proxy ({self._proxy_provider.get_type()}): {self._proxy_provider.get_current_ip()}")
                co.set_argument(f'--proxy-server={chrome_arg}')
                co.set_argument('--proxy-bypass-list=<-loopback>')
                self.log(f"Proxy READY → Chrome dung {self._proxy_provider.get_type()}", "OK")
        elif self.ipv6:
            # Backward compat: IPv6 truc tiep (logic cu)
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
            # v1.0.545: ProxyProvider hoac IPv6 proxy
            if self._proxy_provider and self._proxy_provider.is_ready():
                chrome_arg = self._proxy_provider.get_chrome_arg()
                if chrome_arg:
                    co2.set_argument(f'--proxy-server={chrome_arg}')
                    co2.set_argument('--proxy-bypass-list=<-loopback>')
            elif self._proxy and self._proxy._running:
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
        # v1.0.532: Reuse project URL cu neu co (khong tao project moi thua)
        # Chi tao project moi khi: (1) lan dau setup, (2) sau clear data + login lai
        reuse_url = None
        if self.project_url and not need_login:
            reuse_url = self.project_url
            self.log(f"[REUSE] Co project URL cu: {reuse_url}")
            self.log(f"[REUSE] Navigate thang vao project cu (khong tao moi)")

        target_url = reuse_url or FLOW_URL
        self.log(f"Vao: {target_url}")
        self.page.get(target_url)
        time.sleep(5)
        self.inject_fingerprint_spoof()

        current_url = self.page.url or ''
        self.log(f"URL: {current_url}")

        # Check login fallback (cho truong hop khong co _account)
        if 'accounts.google.com' in current_url:
            self.log("Chua dang nhap! Tu dong dang nhap...", "WARN")
            # Login bi mat → project URL cu cung khong dung duoc nua
            reuse_url = None
            self.project_url = None
            login_ok = self._auto_login()
            if not login_ok:
                self.log("Dang nhap that bai!", "ERROR")
                return False
            # Vao lai Flow sau khi login
            self.page.get(FLOW_URL)
            time.sleep(5)
            self.inject_fingerprint_spoof()
            current_url = self.page.url or ''

        # 6. Reuse project cu hoac tao project moi
        if '/project/' in current_url:
            # Da vao project (reuse thanh cong hoac redirect tu dong)
            if reuse_url:
                self.log(f"[REUSE] Vao lai project cu thanh cong!", "OK")
        else:
            # Chua co project → tao moi
            if reuse_url:
                self.log(f"[REUSE] Project cu khong con → tao project moi", "WARN")
                self.project_url = None
            success = self._create_new_project()
            if not success:
                self.log("Không tạo được project mới!", "ERROR")
                return False

        # 7. Đợi textarea
        if self._wait_for_textarea():
            self.ready = True
            self.project_url = self.page.url
            if reuse_url:
                self.log(f"READY! Reused project: {self.project_url}", "OK")
            else:
                self.log(f"READY! New project: {self.project_url}", "OK")
            return True

        # v1.0.536: Textarea khong xuat hien → retry reload project cu truoc khi tao moi
        self.log("Textarea khong xuat hien - thu reload project cu...", "WARN")

        # Retry 1: Reload project URL cu (F5) - 3 lan
        current_project = self.page.url or ''
        if '/project/' in current_project:
            for retry in range(3):
                self.log(f"[RETRY {retry+1}/3] Reload project cu...")
                try:
                    self.page.get(current_project)
                    time.sleep(3)
                    self.inject_fingerprint_spoof()

                    # Dismiss popup neu co
                    self._dismiss_popups()
                    time.sleep(1)

                    if self._wait_for_textarea(timeout=15):
                        self.ready = True
                        self.project_url = self.page.url
                        self.log(f"READY! Reused project (retry {retry+1}): {self.project_url}", "OK")
                        return True
                except Exception as e:
                    self.log(f"[RETRY {retry+1}/3] Error: {e}", "WARN")

            self.log("Project cu khong phuc hoi sau 3 lan retry → tao project moi", "WARN")

        # Retry 2: Bo project cu, tao project MOI
        self.project_url = None

        try:
            self.page.get(FLOW_URL)
            time.sleep(3)
            self.inject_fingerprint_spoof()
        except Exception:
            pass

        if self._click_create_with_flow():
            self.log("Clicked 'Create with Flow'", "OK")
            time.sleep(2)

        try:
            current_url = self.page.url or ''
            if '/project/' not in current_url:
                success = self._create_new_project()
                if not success:
                    self.log("Khong tao duoc project!", "ERROR")
                    return False
        except:
            pass

        if self._wait_for_textarea():
            self.ready = True
            self.project_url = self.page.url
            self.log(f"READY! New project (fallback): {self.project_url}", "OK")
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
        """Dismiss popup thông báo (Bắt đầu / Get started / Got it / Tôi đồng ý). (giống API mode)"""
        try:
            # 1. Button popups (Bắt đầu / Get started / Got it / Dismiss)
            for sel in ['tag:button@@text():Bắt đầu', 'tag:button@@text():Get started',
                        'tag:button@@text():Bắt Đầu', 'tag:button@@text():Got it',
                        'tag:button@@text():Dismiss',
                        'tag:button@@text():Đã hiểu', 'tag:button@@text():I understand']:
                try:
                    btn = self.page.ele(sel, timeout=0.5)
                    if btn:
                        btn.click()
                        self.log(f"Dismissed popup: {sel.split(':')[-1]}")
                        time.sleep(1)
                        return True
                except:
                    continue

            # 2. Dialog "Tôi đồng ý" / "Agree" / "Accept" (giống API mode line 5746-5760)
            self.page.run_js("""
                var dialog = document.querySelector('[role="dialog"]');
                if (dialog) {
                    var btns = dialog.querySelectorAll('button');
                    for (var i = 0; i < btns.length; i++) {
                        var text = btns[i].textContent.trim();
                        if (text.indexOf('đồng ý') > -1 || text.indexOf('Agree') > -1 ||
                            text.indexOf('Accept') > -1 || text.indexOf('Đã hiểu') > -1 ||
                            text.indexOf('I understand') > -1) {
                            btns[i].click();
                            break;
                        }
                    }
                }
            """)

            # 3. Fallback: Click diem trong de dismiss popup (giong API mode line 1831)
            self.page.run_js('document.elementFromPoint(window.innerWidth/2, 50).click()')
        except:
            pass
        return False

    def _is_logged_out(self) -> bool:
        """Detect logout - check URL redirect ve trang login Google. (giong API mode)"""
        try:
            url = self.page.url or ''
            logout_indicators = [
                "accounts.google.com/signin",
                "accounts.google.com/v3/signin",
                "accounts.google.com/ServiceLogin",
                "accounts.google.com/AccountChooser",
            ]
            for indicator in logout_indicators:
                if indicator in url:
                    self.log(f"[LOGOUT] Detected: {indicator}", "WARN")
                    return True
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

        v1.0.543: Timeout = Flow bị đơ/load chậm → retry tại chỗ (không phải 403).
        Retry tối đa 2 lần nữa (tổng 3 lần) trước khi trả fail.

        Returns: { media: [...] } hoặc { error: "..." }
        """
        if not self.page:
            return {"error": "Chrome not initialized"}

        max_timeout_retries = 3  # v1.0.543: Retry 3 lan khi timeout (Flow bi do)
        last_result = None

        for attempt in range(max_timeout_retries):
            if attempt > 0:
                self.log(f"=== Generate Image [RETRY {attempt}/{max_timeout_retries-1}] ===")
            else:
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

                # 2. Inject interceptor (reset trước khi inject + retry nếu fail)
                self.log("Inject interceptor...")
                if image_inputs:
                    self.log(f"Reference images: {len(image_inputs)} media ID(s)")
                # Reset state trước
                self.page.run_js("window.__proxyInterceptReady = false; window._response = null; window._responseError = null; window._requestPending = false;")
                time.sleep(1)  # v1.0.547: Tang 0.5→1s cho page xu ly

                js = build_interceptor_js(client_bearer_token, client_project_id, image_inputs)

                # v1.0.547: Retry interceptor injection toi da 3 lan
                interceptor_ok = False
                for inject_attempt in range(3):
                    try:
                        r = self.page.run_js(js)
                        self.log(f"Interceptor: {r}")
                        if r and r in ('PROXY_INTERCEPTOR_READY', 'ALREADY'):
                            interceptor_ok = True
                            break
                        # r is None hoac unexpected → retry
                        self.log(f"[WARN] Interceptor inject returned: {r}, retry {inject_attempt+1}/3")
                        time.sleep(1)
                    except Exception as ie:
                        self.log(f"[WARN] Interceptor inject error: {ie}, retry {inject_attempt+1}/3")
                        time.sleep(1)

                # Verify interceptor da inject thanh cong
                if not interceptor_ok:
                    # Thu verify bang check window variable
                    try:
                        check = self.page.run_js("return window.__proxyInterceptReady === true ? 'OK' : 'FAIL';")
                        if check == 'OK':
                            self.log("[OK] Interceptor verified via window check")
                            interceptor_ok = True
                        else:
                            self.log("[ERROR] Interceptor KHONG inject duoc! Request se dung token SAI → 403")
                            return {"error": "Interceptor injection failed - cannot proceed"}
                    except:
                        self.log("[ERROR] Interceptor verification failed!")
                        return {"error": "Interceptor injection failed - cannot proceed"}

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
                result = self._wait_for_response(timeout=180)

                # 7. Cleanup browser data sau mỗi request (tránh bị Google track/flag)
                try:
                    self.page.run_js(JS_CLEANUP)
                    self.log("Cleanup browser data OK")
                except Exception as ce:
                    self.log(f"Cleanup warning: {ce}", "WARN")

                # v1.0.543: Check timeout → retry tai cho (Flow bi do, khong phai 403)
                if 'error' in result:
                    err_str = str(result['error']).lower()
                    is_timeout = 'timeout' in err_str
                    is_403 = '403' in err_str
                    is_400 = '400' in err_str

                    if is_timeout and not is_403 and not is_400:
                        # Timeout = Flow bi do/load cham → retry
                        last_result = result
                        if attempt < max_timeout_retries - 1:
                            self.log(f"[TIMEOUT RETRY] Flow bi do → thu lai lan {attempt + 2}/{max_timeout_retries}...", "WARN")
                            time.sleep(3)  # Doi 3s truoc khi retry
                            continue
                        else:
                            self.log(f"[TIMEOUT RETRY] Het {max_timeout_retries} lan retry, tra fail", "WARN")
                            return result
                    else:
                        # 403/400/loi khac → tra ve ngay, khong retry
                        return result
                else:
                    # Thanh cong!
                    if attempt > 0:
                        self.log(f"[TIMEOUT RETRY] OK sau {attempt + 1} lan!", "OK")
                    return result

            except Exception as e:
                self.log(f"Error: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        # Fallback (khong nen den day)
        return last_result or {"error": "Max retries exceeded"}

    def generate_video(self, client_bearer_token: str, client_project_id: str,
                       client_prompt: str, media_id: str,
                       video_model: str = 'veo_3_1_r2v_fast_landscape_ultra_relaxed',
                       aspect_ratio: str = 'VIDEO_ASPECT_RATIO_LANDSCAPE',
                       seed: int = None) -> dict:
        """
        v1.0.632: Tạo video từ ảnh (I2V) - THỰC SỰ chuyển sang Video mode.

        Flow:
        1. Vào project URL (giống generate_image)
        2. Click chuyển sang Video mode (Video tab → Thành phần → 16:9 → x1 → Lower Priority)
        3. Inject video interceptor (thay token + projectId + inject mediaId)
        4. Paste prompt → Enter → Chrome gửi VIDEO request (đúng URL video)
        5. Interceptor thay token/projectId + inject mediaId
        6. Chờ operations response → trả về cho VM
        7. VM tự poll Google trực tiếp để lấy video URL

        Args:
            client_bearer_token: Bearer token của VM
            client_project_id: Project ID của VM
            client_prompt: Video prompt (mô tả chuyển động)
            media_id: Media ID của ảnh (từ generate_image response)
            video_model: Model video I2V
            aspect_ratio: Tỷ lệ video
            seed: Seed (optional)

        Returns:
            {"operations": [...]} hoặc {"error": "..."}
        """
        if not self.page:
            return {"error": "Chrome not initialized"}

        max_timeout_retries = 3

        for attempt in range(max_timeout_retries):
            if attempt > 0:
                self.log(f"=== Generate Video [RETRY {attempt}/{max_timeout_retries-1}] ===")
            else:
                self.log(f"=== Generate Video (I2V) ===")
            self.log(f"MediaId: {media_id[:50]}...")
            self.log(f"Prompt: {client_prompt[:60]}...")

            try:
                # 1. Vào project
                if self.project_url:
                    self.page.get(self.project_url)
                else:
                    self.page.get(FLOW_URL)
                time.sleep(5)
                self.inject_fingerprint_spoof()

                if not self._wait_for_textarea(timeout=20):
                    self.log("Textarea not found, tao project moi...", "WARN")
                    if not self._create_new_project():
                        return {"error": "Cannot create project"}
                    if not self._wait_for_textarea(timeout=20):
                        return {"error": "Textarea not found after project creation"}
                    self.project_url = self.page.url

                # 2. CHUYỂN SANG VIDEO MODE (click UI thực sự)
                self.log("Chuyen sang Video mode (Video tab → Thanh phan → 16:9 → x1 → Lower Priority)...")
                self.page.run_js("window._videoModeResult = 'PENDING';")
                self.page.run_js(JS_SELECT_VIDEO_MODE)
                time.sleep(7)  # Doi JS async hoan thanh (~5.6s setTimeout chain)

                video_mode_result = self.page.run_js("return window._videoModeResult;")
                self.log(f"Video mode result: {video_mode_result}")

                if video_mode_result != 'SUCCESS':
                    self.log(f"[WARN] Video mode chua SUCCESS: {video_mode_result}, thu lai...", "WARN")
                    # Dong menu va thu lai
                    self.page.run_js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
                    time.sleep(1)
                    self.page.run_js("window._videoModeResult = 'PENDING';")
                    self.page.run_js(JS_SELECT_VIDEO_MODE)
                    time.sleep(7)
                    video_mode_result = self.page.run_js("return window._videoModeResult;")
                    self.log(f"Video mode retry result: {video_mode_result}")

                # 3. Inject VIDEO interceptor (thay token + projectId + inject mediaId)
                self.log("Inject video interceptor...")
                self.page.run_js("""
                    window.__proxyInterceptReady = false;
                    window._response = null; window._responseError = null; window._requestPending = false;
                    window._videoResponse = null; window._videoError = null; window._videoPending = false;
                """)
                time.sleep(1)

                js_video_interceptor = build_video_interceptor_js(
                    client_bearer_token, client_project_id, media_id, video_model
                )

                interceptor_ok = False
                for inject_attempt in range(3):
                    try:
                        r = self.page.run_js(js_video_interceptor)
                        self.log(f"Video interceptor: {r}")
                        if r and r in ('PROXY_INTERCEPTOR_READY', 'ALREADY'):
                            interceptor_ok = True
                            break
                        self.log(f"[WARN] Video interceptor returned: {r}, retry {inject_attempt+1}/3")
                        time.sleep(1)
                    except Exception as ie:
                        self.log(f"[WARN] Video interceptor error: {ie}, retry {inject_attempt+1}/3")
                        time.sleep(1)

                if not interceptor_ok:
                    try:
                        check = self.page.run_js("return window.__proxyInterceptReady === true ? 'OK' : 'FAIL';")
                        if check == 'OK':
                            interceptor_ok = True
                        else:
                            return {"error": "Video interceptor injection failed"}
                    except:
                        return {"error": "Video interceptor injection failed"}

                # 4. Paste video prompt
                self.log(f"Paste video prompt...")
                ok = self._paste_prompt(client_prompt)
                if not ok:
                    return {"error": "Cannot paste prompt"}

                # 5. Doi recaptcha → Enter (Chrome gui VIDEO request, interceptor thay token + inject mediaId)
                self.log("Doi recaptcha (4s)...")
                time.sleep(4)

                from DrissionPage.common import Keys
                self.page.actions.key_down(Keys.ENTER).key_up(Keys.ENTER)
                self.log("Enter sent! Chrome sends VIDEO request (interceptor replaces token + injects mediaId)...")

                # 6. Cho VIDEO response (operations)
                result = self._wait_for_video_response(timeout=60)

                # 7. Cleanup
                try:
                    self.page.run_js(JS_CLEANUP)
                    self.log("Cleanup browser data OK")
                except Exception as ce:
                    self.log(f"Cleanup warning: {ce}", "WARN")

                # Check timeout → retry
                if 'error' in result:
                    err_str = str(result['error']).lower() if isinstance(result['error'], str) else json.dumps(result['error']).lower()
                    is_timeout = 'timeout' in err_str
                    is_403 = '403' in err_str
                    is_400 = '400' in err_str

                    if is_timeout and not is_403 and not is_400:
                        if attempt < max_timeout_retries - 1:
                            self.log(f"[TIMEOUT RETRY] Video timeout → retry {attempt + 2}/{max_timeout_retries}...", "WARN")
                            time.sleep(3)
                            continue
                        else:
                            return result
                    else:
                        return result
                else:
                    if attempt > 0:
                        self.log(f"[TIMEOUT RETRY] Video OK sau {attempt + 1} lan!", "OK")
                    return result

            except Exception as e:
                self.log(f"Video error: {e}", "ERROR")
                import traceback
                traceback.print_exc()
                return {"error": str(e)}

        return {"error": "Max retries exceeded"}

    def _wait_for_video_response(self, timeout: int = 60) -> dict:
        """Chờ video response (operations) từ interceptor."""
        self.log(f"Chờ video response ({timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            elapsed = time.time() - start

            state = self.page.run_js("""
                return {
                    pending: window._videoPending,
                    hasResponse: !!window._videoResponse,
                    error: window._videoError
                };
            """)

            if state and state.get('error'):
                self.log(f"VIDEO ERROR: {state['error']}", "ERROR")
                data = self.page.run_js("return window._videoResponse;")
                if data and isinstance(data, dict) and 'error' in data:
                    return {"error": data['error']}
                return {"error": state['error']}

            if state and state.get('hasResponse') and not state.get('error'):
                self.log(f"Video response sau {elapsed:.1f}s!", "OK")
                data = self.page.run_js("return window._videoResponse;")

                if isinstance(data, dict) and 'operations' in data:
                    ops = data['operations']
                    self.log(f"Got {len(ops)} video operations", "OK")
                    return data

                return data or {"error": "Empty video response"}

            elapsed_int = int(elapsed)
            if elapsed_int > 0 and elapsed_int % 10 == 0 and elapsed_int != getattr(self, '_last_video_wait_log', 0):
                self._last_video_wait_log = elapsed_int
                self.log(f"... chờ video ({elapsed_int}s/{timeout}s)")

            time.sleep(1)

        return {"error": f"Video timeout {timeout}s"}

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

    def _wait_for_response(self, timeout: int = 180) -> dict:
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
            from google_login import login_google_chrome, get_proxy_arg_from_settings

            # Dong Chrome hien tai truoc khi login
            if self.page:
                try:
                    self.page.quit()
                except Exception:
                    pass
                self.page = None

            # Dung port rieng cho login (tranh trung voi port chinh)
            login_port = self.port + 100  # 19222 → 19322, etc.

            # v1.0.571: Proxy arg de login cung dung proxy
            _proxy_arg = get_proxy_arg_from_settings()

            success = login_google_chrome(
                account_info=account,
                chrome_portable=str(self.chrome_path),
                profile_dir=str(self.chrome_data),
                worker_id=login_port - 9222,  # worker_id de tinh port
                proxy_arg=_proxy_arg,
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
