#!/usr/bin/env python3
"""
TEST: Drop ảnh tham chiếu vào prompt area của Google Flow.
Mở Chrome Portable → vào Flow → test các cách attach ảnh.

Usage:
    python test_drop_reference.py
"""

import sys
import os
import time
import json
import base64

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
FLOW_URL = "https://labs.google/fx/vi/tools/flow"


def find_test_image():
    """Tìm 1 ảnh PNG bất kỳ để test."""
    projects_dir = os.path.join(TOOL_DIR, "PROJECTS")
    if os.path.exists(projects_dir):
        for proj in os.listdir(projects_dir):
            for sub in ["nv", "img", "thumbnail"]:
                d = os.path.join(projects_dir, proj, sub)
                if os.path.isdir(d):
                    for f in os.listdir(d):
                        if f.endswith('.png'):
                            return os.path.abspath(os.path.join(d, f))
    return None


def main():
    test_img = find_test_image()
    if not test_img:
        print("[x] Không tìm thấy ảnh PNG trong PROJECTS/")
        return

    fname = os.path.basename(test_img)
    file_path = os.path.abspath(test_img).replace('\\', '/')
    print(f"[v] Test image: {fname}")
    print(f"    Path: {file_path}")
    print()

    # Mở Chrome Portable trực tiếp
    from DrissionPage import ChromiumPage, ChromiumOptions

    chrome_exe = os.path.join(TOOL_DIR, "GoogleChromePortable", "GoogleChromePortable.exe")
    profile_dir = os.path.join(TOOL_DIR, "GoogleChromePortable", "Data", "profile")

    if not os.path.exists(chrome_exe):
        print(f"[x] Chrome không tồn tại: {chrome_exe}")
        return

    print(f"[v] Chrome: {chrome_exe}")
    print(f"[v] Profile: {profile_dir}")
    print()

    options = ChromiumOptions()
    options.set_local_port(19222)  # Port riêng cho test
    options.set_browser_path(chrome_exe)
    options.set_user_data_path(profile_dir)
    options.set_argument('--window-size', '1400,900')
    options.set_argument('--window-position', '100,50')
    # Không ẩn
    options.headless(False)

    print("Mở Chrome...")
    try:
        page = ChromiumPage(options)
    except Exception as e:
        print(f"[x] Không mở được Chrome: {e}")
        return

    print("[v] Chrome đã mở!")

    # Vào Google Flow
    print(f"Vào {FLOW_URL}...")
    page.get(FLOW_URL)
    time.sleep(5)

    print()
    print("=" * 60)
    print("Chrome đã mở Flow. Hãy:")
    print("1. Login Google nếu cần")
    print("2. Chọn hoặc tạo 1 project")
    print("3. Đợi tới khi thấy khung nhập prompt")
    print("=" * 60)
    input("Nhấn Enter khi đã sẵn sàng (thấy khung prompt)...")

    # =====================================================
    # SCAN: Xem cấu trúc DOM xung quanh prompt area
    # =====================================================
    print()
    print("=" * 60)
    print("SCAN: Cấu trúc DOM prompt area")
    print("=" * 60)

    scan = page.run_js("""
        var results = {};

        // 1. contenteditable
        var ce = document.querySelector('[contenteditable="true"]');
        if (ce) {
            var rect = ce.getBoundingClientRect();
            results.contenteditable = {
                tag: ce.tagName,
                x: Math.round(rect.x + rect.width/2),
                y: Math.round(rect.y + rect.height/2),
                w: Math.round(rect.width),
                h: Math.round(rect.height)
            };
        }

        // 2. file inputs
        var inputs = document.querySelectorAll('input[type="file"]');
        results.fileInputs = [];
        for (var i = 0; i < inputs.length; i++) {
            var inp = inputs[i];
            var rect = inp.getBoundingClientRect();
            var p = inp.parentElement;
            results.fileInputs.push({
                idx: i,
                accept: inp.accept || '',
                multiple: inp.multiple,
                visible: rect.width > 0,
                parentText: p ? p.textContent.trim().substring(0, 40) : ''
            });
        }

        // 3. buttons phía dưới
        var btns = document.querySelectorAll('button');
        results.buttons = [];
        var halfH = window.innerHeight * 0.4;
        for (var i = 0; i < btns.length; i++) {
            var rect = btns[i].getBoundingClientRect();
            if (rect.y > halfH && rect.width > 0) {
                results.buttons.push({
                    text: (btns[i].textContent||'').trim().substring(0, 40),
                    aria: btns[i].getAttribute('aria-label') || '',
                    x: Math.round(rect.x + rect.width/2),
                    y: Math.round(rect.y + rect.height/2)
                });
            }
        }

        return JSON.stringify(results, null, 2);
    """)

    if scan:
        data = json.loads(scan)
        print(f"\nContenteditable: {json.dumps(data.get('contenteditable', {}))}")
        print(f"\nFile inputs ({len(data.get('fileInputs', []))}):")
        for fi in data.get('fileInputs', []):
            print(f"  [{fi['idx']}] accept='{fi['accept']}' multiple={fi['multiple']} visible={fi['visible']} parent='{fi['parentText']}'")
        print(f"\nButtons phía dưới ({len(data.get('buttons', []))}):")
        for b in data.get('buttons', []):
            print(f"  '{b['text']}' aria='{b['aria']}' at ({b['x']},{b['y']})")

    # =====================================================
    # TEST 1: CDP drag-drop
    # =====================================================
    print()
    print("=" * 60)
    print(f"TEST 1: CDP Input.dispatchDragEvent với {fname}")
    print("=" * 60)

    pos = data.get('contenteditable', {})
    if not pos:
        print("[x] Không có contenteditable!")
    else:
        x, y = pos['x'], pos['y']
        drag_data = {
            'items': [{'mimeType': 'image/png', 'data': ''}],
            'files': [file_path],
            'dragOperationsMask': 19
        }

        try:
            print(f"  dragEnter tại ({x}, {y})...")
            page.run_cdp('Input.dispatchDragEvent',
                type='dragEnter', x=x, y=y, data=drag_data
            )
            time.sleep(2)

            # Tìm zone "Thêm thành phần"
            zone_js = page.run_js("""
                var all = document.querySelectorAll('*');
                var results = [];
                for (var i = 0; i < all.length; i++) {
                    var text = (all[i].textContent || '').trim();
                    if (text.length < 40 && text.length > 2) {
                        var lower = text.toLowerCase();
                        if (lower.indexOf('thêm') > -1 || lower.indexOf('add') > -1 ||
                            lower.indexOf('thành phần') > -1 || lower.indexOf('component') > -1 ||
                            lower.indexOf('element') > -1 || lower.indexOf('drop') > -1) {
                            var rect = all[i].getBoundingClientRect();
                            if (rect.width > 20 && rect.height > 20 && rect.width < 500) {
                                results.push({
                                    tag: all[i].tagName,
                                    text: text,
                                    x: Math.round(rect.x + rect.width/2),
                                    y: Math.round(rect.y + rect.height/2),
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height)
                                });
                            }
                        }
                    }
                }
                return JSON.stringify(results);
            """)

            zones = json.loads(zone_js) if zone_js else []
            print(f"  Zones tìm thấy ({len(zones)}):")
            for z in zones:
                print(f"    <{z['tag']}> '{z['text']}' at ({z['x']},{z['y']}) {z['w']}x{z['h']}")

            if zones:
                # Drop vào zone đầu tiên
                z = zones[0]
                print(f"\n  dragOver tại zone ({z['x']}, {z['y']})...")
                page.run_cdp('Input.dispatchDragEvent',
                    type='dragOver', x=z['x'], y=z['y'], data=drag_data
                )
                time.sleep(0.5)

                print(f"  drop tại zone...")
                page.run_cdp('Input.dispatchDragEvent',
                    type='drop', x=z['x'], y=z['y'], data=drag_data
                )
                time.sleep(3)
                print("  → KIỂM TRA CHROME: Ảnh có xuất hiện trong prompt không?")
            else:
                print("  [!] Không tìm thấy zone. Thử drop vào prompt area...")
                page.run_cdp('Input.dispatchDragEvent',
                    type='dragOver', x=x, y=y, data=drag_data
                )
                time.sleep(0.5)
                page.run_cdp('Input.dispatchDragEvent',
                    type='drop', x=x, y=y, data=drag_data
                )
                time.sleep(3)
                print("  → KIỂM TRA CHROME: Có gì thay đổi không?")

        except Exception as e:
            print(f"  [x] Error: {e}")
            try:
                page.run_cdp('Input.dispatchDragEvent',
                    type='dragCancel', x=x, y=y, data=drag_data
                )
            except:
                pass

    input("\nNhấn Enter để test cách 2...")

    # =====================================================
    # TEST 2: JS DataTransfer drop
    # =====================================================
    print()
    print("=" * 60)
    print("TEST 2: JavaScript DataTransfer drop")
    print("=" * 60)

    with open(test_img, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()
    print(f"  Image: {len(img_b64)} chars base64")

    result = page.run_js("""
        (function() {
            var b64 = arguments[0];
            var fname = arguments[1];

            try {
                var binary = atob(b64);
                var array = new Uint8Array(binary.length);
                for (var i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
                var file = new File([array], fname, {type: 'image/png', lastModified: Date.now()});

                var dt = new DataTransfer();
                dt.items.add(file);

                var target = document.querySelector('[contenteditable="true"]');
                if (!target) return JSON.stringify({ok: false, reason: 'no contenteditable'});

                // dragenter
                target.dispatchEvent(new DragEvent('dragenter', {
                    dataTransfer: dt, bubbles: true, cancelable: true
                }));

                return JSON.stringify({ok: true, step: 'dragenter done'});
            } catch(e) {
                return JSON.stringify({ok: false, reason: e.message});
            }
        })()
    """, img_b64, fname)

    print(f"  dragenter: {result}")

    if result and json.loads(result).get('ok'):
        time.sleep(2)

        # Scan for zone after dragenter
        zone_js2 = page.run_js("""
            var all = document.querySelectorAll('*');
            var results = [];
            for (var i = 0; i < all.length; i++) {
                var text = (all[i].textContent || '').trim();
                if (text.length < 40 && text.length > 2) {
                    var lower = text.toLowerCase();
                    if (lower.indexOf('thêm') > -1 || lower.indexOf('add') > -1 ||
                        lower.indexOf('thành phần') > -1 || lower.indexOf('drop') > -1) {
                        var rect = all[i].getBoundingClientRect();
                        if (rect.width > 20 && rect.height > 20 && rect.width < 500) {
                            results.push({
                                tag: all[i].tagName,
                                text: text,
                                x: Math.round(rect.x + rect.width/2),
                                y: Math.round(rect.y + rect.height/2)
                            });
                        }
                    }
                }
            }
            return JSON.stringify(results);
        """)

        zones2 = json.loads(zone_js2) if zone_js2 else []
        print(f"  Zones after JS dragenter ({len(zones2)}):")
        for z in zones2:
            print(f"    <{z['tag']}> '{z['text']}' at ({z['x']},{z['y']})")

        # Drop
        drop_result = page.run_js("""
            (function() {
                var b64 = arguments[0];
                var fname = arguments[1];

                var binary = atob(b64);
                var array = new Uint8Array(binary.length);
                for (var i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
                var file = new File([array], fname, {type: 'image/png', lastModified: Date.now()});

                var dt = new DataTransfer();
                dt.items.add(file);

                // Tìm zone hoặc contenteditable
                var zone = null;
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var text = (all[i].textContent || '').trim();
                    if (text.length < 30 && (text.indexOf('Thêm thành phần') > -1 || text.indexOf('Add component') > -1)) {
                        var rect = all[i].getBoundingClientRect();
                        if (rect.width > 20) { zone = all[i]; break; }
                    }
                }

                var target = zone || document.querySelector('[contenteditable="true"]');
                var name = zone ? 'zone' : 'contenteditable';

                target.dispatchEvent(new DragEvent('dragover', {
                    dataTransfer: dt, bubbles: true, cancelable: true
                }));

                var dropEvt = new DragEvent('drop', {
                    dataTransfer: dt, bubbles: true, cancelable: true
                });
                target.dispatchEvent(dropEvt);

                return JSON.stringify({ok: true, target: name, zoneFound: zone != null});
            })()
        """, img_b64, fname)

        print(f"  drop: {drop_result}")
        time.sleep(3)
        print("  → KIỂM TRA CHROME: Ảnh có xuất hiện trong prompt không?")

    input("\nNhấn Enter để test cách 3...")

    # =====================================================
    # TEST 3: Tìm file input gần prompt, set file lên đó
    # =====================================================
    print()
    print("=" * 60)
    print("TEST 3: DOM.setFileInputFiles trên từng input[type=file]")
    print("=" * 60)

    num_inputs = page.run_js("return document.querySelectorAll('input[type=\"file\"]').length;")
    print(f"  Có {num_inputs} input[type=file]")

    for i in range(num_inputs or 0):
        print(f"\n  --- Thử input[{i}] ---")
        info = page.run_js(f"""
            var inp = document.querySelectorAll('input[type="file"]')[{i}];
            if (!inp) return null;
            var p = inp.parentElement;
            var pp = p ? p.parentElement : null;
            return JSON.stringify({{
                accept: inp.accept || '*',
                parentText: p ? p.textContent.trim().substring(0, 50) : '',
                grandparentText: pp ? pp.textContent.trim().substring(0, 50) : ''
            }});
        """)
        if info:
            print(f"  Info: {info}")

        ans = input(f"  Set file lên input[{i}]? (y/n): ").strip().lower()
        if ans == 'y':
            try:
                obj = page.run_cdp('Runtime.evaluate',
                    expression=f'document.querySelectorAll("input[type=\\"file\\"]")[{i}]',
                    returnByValue=False
                )
                oid = obj.get('result', {}).get('objectId')
                if oid:
                    page.run_cdp('DOM.setFileInputFiles',
                        files=[file_path],
                        objectId=oid
                    )
                    time.sleep(3)
                    print(f"  → KIỂM TRA CHROME: Ảnh có xuất hiện trong prompt không?")
                else:
                    print(f"  [x] Không lấy được objectId")
            except Exception as e:
                print(f"  [x] Error: {e}")

    print()
    print("=" * 60)
    print("TEST XONG!")
    print("=" * 60)
    print()
    print("Ghi nhận kết quả:")
    print("- TEST 1 (CDP drag): Zone 'Thêm thành phần' có hiện không? Drop có vào không?")
    print("- TEST 2 (JS drag):  Zone có hiện không? Drop có vào không?")
    print("- TEST 3 (file input): Input nào làm ảnh vào prompt (không phải gallery)?")
    print()
    input("Nhấn Enter để đóng Chrome...")

    try:
        page.quit()
    except:
        pass


if __name__ == "__main__":
    main()
