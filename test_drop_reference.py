#!/usr/bin/env python3
"""
TEST FULL: Drop anh → doi "dang tai cac thanh phan" bien mat → paste prompt.
"""
import sys, os, time, json

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_URL = "https://labs.google/fx/vi/tools/flow/project/585122d3-ee6b-49a1-a160-036a392e4350"

JS_IS_LOADING = """
    var all = document.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
        var text = (all[i].textContent || '').trim();
        if (text.indexOf('đang tải các thành phần') > -1 ||
            text.indexOf('loading component') > -1 ||
            text.indexOf('Loading component') > -1) {
            var rect = all[i].getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                return true;
            }
        }
    }
    return false;
"""


def find_test_images(max_count=2):
    images = []
    projects_dir = os.path.join(TOOL_DIR, "PROJECTS")
    if os.path.exists(projects_dir):
        for proj in sorted(os.listdir(projects_dir)):
            d = os.path.join(projects_dir, proj, "nv")
            if os.path.isdir(d):
                for f in sorted(os.listdir(d)):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        images.append(os.path.abspath(os.path.join(d, f)))
                        if len(images) >= max_count:
                            return images
    return images


def main():
    test_imgs = find_test_images(2)
    if not test_imgs:
        print("[x] Khong tim thay anh")
        return

    file_paths = [p.replace('\\', '/') for p in test_imgs]
    fnames = [os.path.basename(p) for p in file_paths]
    print(f"[v] Drop {len(file_paths)} anh: {fnames}")

    from DrissionPage import ChromiumPage, ChromiumOptions

    chrome_exe = os.path.join(TOOL_DIR, "GoogleChromePortable - Copy", "GoogleChromePortable.exe")
    profile_dir = os.path.join(TOOL_DIR, "GoogleChromePortable - Copy", "Data", "profile")

    options = ChromiumOptions()
    options.set_local_port(19222)
    options.set_browser_path(chrome_exe)
    options.set_user_data_path(profile_dir)
    options.set_argument('--window-size', '1400,900')
    options.set_argument('--window-position', '100,50')
    options.headless(False)

    print("Mo Chrome...")
    page = ChromiumPage(options)
    page.get(PROJECT_URL)

    for i in range(30):
        if page.run_js("return document.querySelector('[contenteditable=\"true\"]') ? true : false;"):
            print(f"[v] Ready sau {i}s!")
            break
        time.sleep(1)
    time.sleep(3)

    # =====================================================
    # STEP 1: Drop anh
    # =====================================================
    pos = json.loads(page.run_js("""
        var el = document.querySelector('[contenteditable="true"]');
        var rect = el.getBoundingClientRect();
        return JSON.stringify({x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2)});
    """))

    drag_data = {
        'items': [{'mimeType': 'image/png', 'data': ''} for _ in file_paths],
        'files': file_paths,
        'dragOperationsMask': 19
    }

    print()
    print("=" * 60)
    print(f"STEP 1: Drop {len(file_paths)} anh")
    print("=" * 60)

    page.run_cdp('Input.dispatchDragEvent', type='dragEnter', x=pos['x'], y=pos['y'], data=drag_data)
    time.sleep(1.5)

    zone = page.run_js("""
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var text = (all[i].textContent || '').trim();
            if ((text.indexOf('Thêm thành phần') > -1 || text.indexOf('Add component') > -1) && text.length < 30) {
                var rect = all[i].getBoundingClientRect();
                if (rect.width > 50 && rect.height > 15) {
                    return JSON.stringify({x: Math.round(rect.x+rect.width/2), y: Math.round(rect.y+rect.height/2)});
                }
            }
        }
        return null;
    """)
    drop_pos = json.loads(zone) if zone else pos
    print(f"  Drop at ({drop_pos['x']}, {drop_pos['y']})")

    page.run_cdp('Input.dispatchDragEvent', type='dragOver', x=drop_pos['x'], y=drop_pos['y'], data=drag_data)
    time.sleep(0.5)
    page.run_cdp('Input.dispatchDragEvent', type='drop', x=drop_pos['x'], y=drop_pos['y'], data=drag_data)
    time.sleep(1)

    # Handle dialog
    page.run_js("""
        var dialog = document.querySelector('[role="dialog"]');
        if (dialog) {
            var btns = dialog.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var t = btns[i].textContent.trim();
                if (t.indexOf('đồng ý') > -1 || t.indexOf('Agree') > -1) { btns[i].click(); break; }
            }
        }
    """)

    # =====================================================
    # STEP 2: Doi "dang tai cac thanh phan" bien mat
    # =====================================================
    print()
    print("=" * 60)
    print("STEP 2: Doi anh tai xong...")
    print("=" * 60)

    saw_loading = False
    max_wait = 40

    for sec in range(max_wait):
        is_loading = page.run_js(JS_IS_LOADING)

        if is_loading:
            if not saw_loading:
                print(f"  {sec}s: >>> DANG TAI CAC THANH PHAN <<<")
                saw_loading = True
            else:
                print(f"  {sec}s: van dang tai...")
        elif saw_loading:
            print(f"  {sec}s: [v] DA TAI XONG! (loading bien mat)")
            break
        else:
            print(f"  {sec}s: chua thay loading...")
            if sec >= 5 and not saw_loading:
                print(f"  [v] Khong thay loading - tai qua nhanh hoac da xong")
                break

        time.sleep(1)

    # =====================================================
    # STEP 3: Paste prompt
    # =====================================================
    print()
    print("=" * 60)
    print("STEP 3: Paste prompt")
    print("=" * 60)

    test_prompt = "A cinematic photo of an intense confrontation in an office, two people facing each other with dramatic lighting"

    # Focus vao prompt
    page.run_js("""
        var el = document.querySelector('[contenteditable="true"]');
        if (el) el.focus();
    """)
    time.sleep(0.5)

    # Paste
    import subprocess
    process = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE)
    process.communicate(test_prompt.encode('utf-16-le'))
    time.sleep(0.3)

    from DrissionPage.common import Keys
    page.actions.key_down(Keys.CONTROL).key_down('v').key_up('v').key_up(Keys.CONTROL)
    time.sleep(1)

    print(f"  [v] Da paste: {test_prompt[:60]}...")
    print("  (KHONG bam Enter)")

    # Cho xem
    print()
    print("=" * 60)
    print("XONG! Quan sat Chrome.")
    print("Doi 120s... (Ctrl+C)")
    print("=" * 60)

    try:
        time.sleep(120)
    except KeyboardInterrupt:
        pass
    try:
        page.quit()
    except:
        pass


if __name__ == "__main__":
    main()
