#!/usr/bin/env python3
"""
TEST: Drop ảnh tham chiếu vào prompt area của Google Flow.
Chạy trên VM sau khi Chrome đã login và vào project.

Usage:
    python test_drop_reference.py

Script này sẽ:
1. Mở Chrome vào project Flow
2. Thử nhiều cách drop/attach ảnh vào prompt
3. In kết quả để biết cách nào hoạt động
"""

import sys
import os
import time
import json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.drission_flow_api import DrissionFlowAPI


def find_test_image():
    """Tìm 1 ảnh tham chiếu trong PROJECTS để test."""
    projects_dir = os.path.join(os.path.dirname(__file__), "PROJECTS")
    if not os.path.exists(projects_dir):
        return None
    for proj in os.listdir(projects_dir):
        nv_dir = os.path.join(projects_dir, proj, "nv")
        if os.path.isdir(nv_dir):
            for f in os.listdir(nv_dir):
                if f.endswith('.png'):
                    return os.path.abspath(os.path.join(nv_dir, f))
    return None


def main():
    test_img = find_test_image()
    if not test_img:
        print("[x] Không tìm thấy ảnh test trong PROJECTS/*/nv/")
        print("    Đặt 1 file .png vào PROJECTS/<code>/nv/ rồi chạy lại")
        return

    print(f"[v] Test image: {test_img}")
    fname = os.path.basename(test_img)
    file_path = test_img.replace('\\', '/')

    # Khởi tạo DrissionFlowAPI
    api = DrissionFlowAPI(worker_id=0)
    api.setup()

    if not api._ready or not api.driver:
        print("[x] Chrome không ready!")
        return

    print("[v] Chrome ready!")
    print()

    # =====================================================
    # TEST 1: CDP Input.dispatchDragEvent
    # =====================================================
    print("=" * 60)
    print("TEST 1: CDP Input.dispatchDragEvent (drag-drop)")
    print("=" * 60)

    # Tìm prompt area
    coords = api.driver.run_js("""
        var el = document.querySelector('[contenteditable="true"]');
        if (!el) return null;
        var rect = el.getBoundingClientRect();
        return JSON.stringify({
            x: Math.round(rect.x + rect.width / 2),
            y: Math.round(rect.y + rect.height / 2),
            w: Math.round(rect.width),
            h: Math.round(rect.height)
        });
    """)

    if not coords:
        print("[x] Không tìm thấy contenteditable")
    else:
        pos = json.loads(coords)
        print(f"[v] Prompt area: ({pos['x']}, {pos['y']}) size {pos['w']}x{pos['h']}")

        drag_data = {
            'items': [{'mimeType': 'image/png', 'data': ''}],
            'files': [file_path],
            'dragOperationsMask': 19
        }

        try:
            # dragEnter
            print("  → dragEnter...")
            api.driver.run_cdp('Input.dispatchDragEvent',
                type='dragEnter',
                x=pos['x'], y=pos['y'],
                data=drag_data
            )
            time.sleep(1.5)

            # Check xem "Thêm thành phần" có xuất hiện không
            zone_info = api.driver.run_js("""
                var results = [];
                var all = document.querySelectorAll('*');
                for (var i = 0; i < all.length; i++) {
                    var text = (all[i].textContent || '').trim();
                    if ((text.indexOf('Thêm thành phần') > -1 || text.indexOf('Add component') > -1
                         || text.indexOf('Add element') > -1 || text.indexOf('thành phần') > -1)
                        && text.length < 50) {
                        var rect = all[i].getBoundingClientRect();
                        if (rect.width > 10 && rect.height > 10) {
                            results.push({
                                tag: all[i].tagName,
                                text: text.substring(0, 40),
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                }
                return JSON.stringify(results);
            """)

            zones = json.loads(zone_info) if zone_info else []
            if zones:
                print(f"  [v] TÌM THẤY {len(zones)} zone 'Thêm thành phần':")
                for z in zones:
                    print(f"      <{z['tag']}> '{z['text']}' at ({z['x']},{z['y']}) {z['w']}x{z['h']}")

                # Drop vào zone đầu tiên
                drop_zone = zones[0]
                print(f"  → dragOver on zone ({drop_zone['x']}, {drop_zone['y']})...")
                api.driver.run_cdp('Input.dispatchDragEvent',
                    type='dragOver',
                    x=drop_zone['x'], y=drop_zone['y'],
                    data=drag_data
                )
                time.sleep(0.5)

                print(f"  → drop on zone...")
                api.driver.run_cdp('Input.dispatchDragEvent',
                    type='drop',
                    x=drop_zone['x'], y=drop_zone['y'],
                    data=drag_data
                )
                time.sleep(3)
                print("  [?] Check Chrome - ảnh có xuất hiện trong prompt không?")
            else:
                print("  [x] KHÔNG tìm thấy zone 'Thêm thành phần'")

                # Cancel drag
                api.driver.run_cdp('Input.dispatchDragEvent',
                    type='dragCancel',
                    x=pos['x'], y=pos['y'],
                    data=drag_data
                )

        except Exception as e:
            print(f"  [x] CDP Error: {e}")

    print()
    input("Nhấn Enter để tiếp tục TEST 2...")

    # =====================================================
    # TEST 2: Tìm tất cả input[type=file] trên trang
    # =====================================================
    print("=" * 60)
    print("TEST 2: Scan tất cả input[type=file] trên trang")
    print("=" * 60)

    file_inputs = api.driver.run_js("""
        var inputs = document.querySelectorAll('input[type="file"]');
        var results = [];
        for (var i = 0; i < inputs.length; i++) {
            var el = inputs[i];
            var rect = el.getBoundingClientRect();
            var parent = el.parentElement;
            var parentText = parent ? (parent.textContent || '').trim().substring(0, 50) : '';
            results.push({
                id: el.id || '',
                name: el.name || '',
                accept: el.accept || '',
                multiple: el.multiple,
                visible: rect.width > 0 && rect.height > 0,
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                parentTag: parent ? parent.tagName : '',
                parentText: parentText
            });
        }
        return JSON.stringify(results);
    """)

    inputs = json.loads(file_inputs) if file_inputs else []
    print(f"Tìm thấy {len(inputs)} input[type=file]:")
    for i, inp in enumerate(inputs):
        print(f"  [{i}] id='{inp['id']}' name='{inp['name']}' accept='{inp['accept']}' "
              f"multiple={inp['multiple']} visible={inp['visible']}")
        print(f"      pos=({inp['x']},{inp['y']}) size={inp['w']}x{inp['h']}")
        print(f"      parent=<{inp['parentTag']}> '{inp['parentText']}'")

    print()
    input("Nhấn Enter để tiếp tục TEST 3...")

    # =====================================================
    # TEST 3: Tìm buttons/elements liên quan đến add reference
    # =====================================================
    print("=" * 60)
    print("TEST 3: Scan buttons liên quan đến reference/add")
    print("=" * 60)

    buttons = api.driver.run_js("""
        var results = [];
        var btns = document.querySelectorAll('button');
        var halfH = window.innerHeight * 0.4;
        for (var i = 0; i < btns.length; i++) {
            var text = (btns[i].textContent || '').trim();
            var rect = btns[i].getBoundingClientRect();
            if (rect.y > halfH && rect.width > 0) {
                results.push({
                    text: text.substring(0, 40),
                    x: Math.round(rect.x + rect.width / 2),
                    y: Math.round(rect.y + rect.height / 2),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    ariaLabel: btns[i].getAttribute('aria-label') || ''
                });
            }
        }
        return JSON.stringify(results);
    """)

    btns = json.loads(buttons) if buttons else []
    print(f"Buttons phía dưới màn hình ({len(btns)}):")
    for b in btns:
        print(f"  '{b['text']}' aria='{b['ariaLabel']}' at ({b['x']},{b['y']}) {b['w']}x{b['h']}")

    print()
    input("Nhấn Enter để tiếp tục TEST 4...")

    # =====================================================
    # TEST 4: JavaScript DataTransfer drop
    # =====================================================
    print("=" * 60)
    print("TEST 4: JavaScript DataTransfer drop (JS-based)")
    print("=" * 60)

    # Đọc ảnh thành base64 trong Python, truyền vào JS
    import base64
    with open(test_img, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    print(f"  Image size: {len(img_b64)} chars (base64)")
    print(f"  Filename: {fname}")

    # Thử drop bằng JS DataTransfer
    result = api.driver.run_js("""
        var b64 = arguments[0];
        var fname = arguments[1];

        try {
            // Convert base64 to Blob
            var binary = atob(b64);
            var array = new Uint8Array(binary.length);
            for (var i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
            var blob = new Blob([array], {type: 'image/png'});
            var file = new File([blob], fname, {type: 'image/png'});

            // Find target
            var target = document.querySelector('[contenteditable="true"]');
            if (!target) return JSON.stringify({ok: false, reason: 'no contenteditable'});

            // Create DataTransfer
            var dt = new DataTransfer();
            dt.items.add(file);

            // Dispatch drag events
            var enterEvt = new DragEvent('dragenter', {dataTransfer: dt, bubbles: true, cancelable: true});
            target.dispatchEvent(enterEvt);

            // Wait for zone to appear, then find it
            return JSON.stringify({ok: true, step: 'dragenter sent, checking zone in 1s...'});
        } catch(e) {
            return JSON.stringify({ok: false, reason: e.message});
        }
    """, img_b64, fname)

    print(f"  dragenter result: {result}")

    if result:
        data = json.loads(result)
        if data.get('ok'):
            time.sleep(1.5)

            # Check zone + drop
            drop_result = api.driver.run_js("""
                var b64 = arguments[0];
                var fname = arguments[1];

                try {
                    var binary = atob(b64);
                    var array = new Uint8Array(binary.length);
                    for (var i = 0; i < binary.length; i++) array[i] = binary.charCodeAt(i);
                    var blob = new Blob([array], {type: 'image/png'});
                    var file = new File([blob], fname, {type: 'image/png'});

                    var dt = new DataTransfer();
                    dt.items.add(file);

                    // Find "Thêm thành phần" zone
                    var zone = null;
                    var all = document.querySelectorAll('*');
                    for (var i = 0; i < all.length; i++) {
                        var text = (all[i].textContent || '').trim();
                        if ((text.indexOf('Thêm thành phần') > -1 || text.indexOf('Add component') > -1)
                            && text.length < 30) {
                            var rect = all[i].getBoundingClientRect();
                            if (rect.width > 20 && rect.height > 20) {
                                zone = all[i];
                                break;
                            }
                        }
                    }

                    var target = zone || document.querySelector('[contenteditable="true"]');
                    var targetName = zone ? 'zone:' + zone.textContent.trim().substring(0, 20) : 'contenteditable';

                    // dragover
                    var overEvt = new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true});
                    target.dispatchEvent(overEvt);

                    // drop
                    var dropEvt = new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true});
                    var prevented = !target.dispatchEvent(dropEvt);

                    return JSON.stringify({
                        ok: true,
                        target: targetName,
                        prevented: prevented,
                        zoneFound: zone != null
                    });
                } catch(e) {
                    return JSON.stringify({ok: false, reason: e.message});
                }
            """, img_b64, fname)

            print(f"  drop result: {drop_result}")
            time.sleep(3)
            print("  [?] Check Chrome - ảnh có xuất hiện trong prompt không?")

    print()
    print("=" * 60)
    print("TEST XONG - Check Chrome để xem cách nào hoạt động!")
    print("=" * 60)
    print()
    print("Ghi nhận:")
    print("- TEST 1 (CDP drag): zone có xuất hiện không?")
    print("- TEST 2 (file inputs): input nào liên quan đến 'Thêm thành phần'?")
    print("- TEST 3 (buttons): button nào để add reference?")
    print("- TEST 4 (JS drop): ảnh có vào prompt không?")
    print()
    input("Nhấn Enter để đóng Chrome...")
    api.close()


if __name__ == "__main__":
    main()
