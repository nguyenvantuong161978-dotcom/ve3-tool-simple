#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VE3 Tool - Google Login Helper

Đọc thông tin tài khoản từ Google Sheet và đăng nhập vào Chrome.

v1.0.105: Đọc từ sheet THÔNG TIN (thay vì ve3)
- Cột B: Mã kênh (AR35, AR47, KA2...)
- Cột AT: Tài khoản Veo3 (nhiều dòng, format: id|pass|2fa)

Hỗ trợ xoay vòng tài khoản:
- Mỗi kênh có thể có 1-3 tài khoản
- Mỗi khi xong 1 mã, sẽ chuyển sang tài khoản tiếp theo
- Xoay vòng khi hết danh sách

Cách detect mã kênh:
- Từ đường dẫn: Documents\AR35-T1\ve3-tool-simple\ → kênh là AR35
"""

import sys
import os
import json
import time
import re
from pathlib import Path

TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

CONFIG_FILE = TOOL_DIR / "config" / "config.json"
ACCOUNT_INDEX_FILE = TOOL_DIR / "config" / ".account_index.json"  # Track account rotation
SHEET_NAME = "THÔNG TIN"  # v1.0.105: Sheet mới chứa thông tin tài khoản
CHANNEL_COLUMN = "B"  # Cột B: Mã kênh (AR35, AR47, KA2...)
ACCOUNTS_COLUMN = "AT"  # Cột AT: Tài khoản Veo3 (nhiều dòng, format: id|pass|2fa)


def log(msg: str, level: str = "INFO"):
    """Print log with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")


def col_letter_to_index(col: str) -> int:
    """
    Convert column letter to 0-based index.
    A=0, B=1, ..., Z=25, AA=26, ..., AT=45
    """
    col = col.upper()
    result = 0
    for char in col:
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1  # 0-based


def load_account_index(channel: str) -> int:
    """Load current account index for a channel from file."""
    try:
        if ACCOUNT_INDEX_FILE.exists():
            data = json.loads(ACCOUNT_INDEX_FILE.read_text(encoding="utf-8"))
            return data.get(channel, 0)
    except Exception as e:
        log(f"Error loading account index: {e}", "WARN")
    return 0


def save_account_index(channel: str, index: int):
    """Save current account index for a channel to file."""
    try:
        data = {}
        if ACCOUNT_INDEX_FILE.exists():
            data = json.loads(ACCOUNT_INDEX_FILE.read_text(encoding="utf-8"))
        data[channel] = index
        ACCOUNT_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNT_INDEX_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Error saving account index: {e}", "WARN")


def rotate_account_index(channel: str, total_accounts: int) -> int:
    """
    Rotate to next account index for a channel.
    Returns new index (wraps around if exceeds total).
    """
    current = load_account_index(channel)
    new_index = (current + 1) % total_accounts
    save_account_index(channel, new_index)
    log(f"Account rotated: {channel} -> index {new_index + 1}/{total_accounts}")
    return new_index


def parse_accounts_cell(cell_value: str) -> list:
    """
    Parse accounts from cell value.
    Format per line: id|pass|2fa

    Returns list of dicts: [{"id": "...", "password": "...", "totp_secret": "..."}, ...]
    """
    accounts = []
    if not cell_value:
        return accounts

    # Split by newlines (cell có thể có nhiều dòng)
    lines = cell_value.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split('|')
        if len(parts) >= 2:
            account = {
                "id": parts[0].strip(),
                "password": parts[1].strip(),
                "totp_secret": parts[2].strip() if len(parts) >= 3 else ""
            }
            if account["id"] and account["password"]:
                accounts.append(account)

    return accounts


def get_channel_accounts(channel_code: str, max_retries: int = 3) -> list:
    """
    Lấy danh sách tài khoản Veo3 cho một kênh từ Google Sheet.

    v1.0.110: Tìm cả mã đầy đủ (AR8-T1) và mã channel (AR8)
    - Cột B: Mã máy đầy đủ (AR8-T1, KA2-T2...)
    - Cột AT: Tài khoản Veo3 (format: id|pass|2fa per line)

    Args:
        channel_code: Mã cần tìm (có thể là AR8-T1 hoặc AR8)
        max_retries: Số lần retry khi gặp lỗi

    Returns:
        List of account dicts: [{"id": "...", "password": "...", "totp_secret": "..."}, ...]
    """
    import time

    code_upper = channel_code.upper()
    last_error = None

    # Get column indices
    channel_col_idx = col_letter_to_index(CHANNEL_COLUMN)  # B = 1
    accounts_col_idx = col_letter_to_index(ACCOUNTS_COLUMN)  # AT = 45

    for attempt in range(max_retries):
        if attempt > 0:
            wait_time = 2 * attempt
            log(f"Retry đọc Google Sheet ({attempt + 1}/{max_retries}) sau {wait_time}s...")
            time.sleep(wait_time)

        gc, spreadsheet_name = load_gsheet_client()
        if not gc:
            last_error = "Cannot load gsheet client"
            continue

        try:
            ws = gc.open(spreadsheet_name).worksheet(SHEET_NAME)
            all_data = ws.get_all_values()

            if not all_data:
                log(f"Sheet '{SHEET_NAME}' is empty", "ERROR")
                return []

            # v1.0.110: Tìm theo nhiều cách:
            # 1. Khớp chính xác (AR8-T1 == AR8-T1)
            # 2. Khớp bắt đầu bằng (AR8-T1 starts with AR8)
            # 3. Khớp channel (AR8 == AR8)
            for row_idx, row in enumerate(all_data, start=1):
                if len(row) <= max(channel_col_idx, accounts_col_idx):
                    continue

                row_code = str(row[channel_col_idx]).strip().upper()

                # Kiểm tra khớp: chính xác HOẶC bắt đầu bằng
                is_match = (
                    row_code == code_upper or  # Khớp chính xác
                    row_code.startswith(code_upper + "-") or  # AR8 matches AR8-T1
                    code_upper.startswith(row_code + "-")  # AR8-T1 matches AR8
                )

                if is_match:
                    accounts_cell = str(row[accounts_col_idx]).strip()
                    accounts = parse_accounts_cell(accounts_cell)

                    if accounts:
                        log(f"Found {len(accounts)} accounts for {code_upper} (matched: {row_code})")
                        for i, acc in enumerate(accounts):
                            log(f"  Account {i+1}: {acc['id']} (2FA: {'Yes' if acc['totp_secret'] else 'No'})")
                        return accounts
                    else:
                        log(f"No valid accounts in cell AT for {row_code}", "WARN")
                        return []

            last_error = f"Code '{code_upper}' not found in sheet column B"
            if attempt < max_retries - 1:
                log(f"Không tìm thấy mã {code_upper}, thử lại...", "WARN")
                continue

        except Exception as e:
            last_error = str(e)
            log(f"Error reading sheet (attempt {attempt + 1}): {e}", "WARN")
            continue

    log(f"Code '{code_upper}' not found after {max_retries} attempts: {last_error}", "ERROR")
    return []


def get_current_account_for_channel(channel_code: str, machine_code: str = None) -> dict:
    """
    Lấy tài khoản hiện tại cho một kênh (theo index rotation).

    v1.0.110: Dùng machine_code (mã đầy đủ) để tìm trong sheet,
    nhưng dùng channel_code để track rotation (tất cả máy cùng kênh dùng chung).

    Args:
        channel_code: Mã kênh (AR8, KA2) - dùng để track rotation
        machine_code: Mã máy đầy đủ (AR8-T1, KA2-T2) - dùng để tìm trong sheet
                      Nếu không có, dùng channel_code

    Returns:
        Account dict: {"id": "...", "password": "...", "totp_secret": "...", "index": N, "total": M}
        or None if no accounts found
    """
    # Dùng machine_code để tìm trong sheet, fallback to channel_code
    search_code = machine_code if machine_code else channel_code
    accounts = get_channel_accounts(search_code)

    if not accounts:
        return None

    # Dùng channel_code để track rotation
    current_index = load_account_index(channel_code)
    # Ensure index is within bounds
    if current_index >= len(accounts):
        current_index = 0
        save_account_index(channel_code, 0)

    account = accounts[current_index].copy()
    account["index"] = current_index
    account["total"] = len(accounts)

    log(f"Using account {current_index + 1}/{len(accounts)} for {channel_code}: {account['id']}")
    return account


def get_account_by_index(machine_code: str, index: int) -> dict:
    """
    v1.0.154: Lấy tài khoản theo index cố định (không rotate).
    Dùng khi cần login lại đúng account đã dùng ban đầu.

    Args:
        machine_code: Mã máy đầy đủ (KA2-T2, AR8-T1) - KHÔNG phải channel code!
        index: Index của account (0-based)

    Returns:
        Account dict: {"id": "...", "password": "...", "totp": "...", "index": N}
        or None if not found
    """
    accounts = get_channel_accounts(machine_code)
    if not accounts:
        log(f"No accounts found for machine: {machine_code}", "WARN")
        return None

    if index < 0 or index >= len(accounts):
        log(f"Invalid index {index} for machine {machine_code} (total: {len(accounts)})", "WARN")
        return None

    account = accounts[index].copy()
    account["index"] = index
    account["total"] = len(accounts)

    log(f"Get account by index {index + 1}/{len(accounts)} for {machine_code}: {account['id']}")
    return account


# ============================================================================
# EXCEL ACCOUNT TRACKING (v1.0.106)
# Lưu/đọc thông tin tài khoản trong Excel để resume đúng account
# ============================================================================

def save_account_to_excel(excel_path: str, channel: str, account_index: int, account_email: str) -> bool:
    """
    Lưu thông tin tài khoản đang sử dụng vào Excel config sheet.

    Args:
        excel_path: Đường dẫn đến file Excel
        channel: Mã kênh (VD: AR35, AR47)
        account_index: Index của tài khoản (0-based)
        account_email: Email của tài khoản

    Returns:
        True nếu lưu thành công
    """
    try:
        from openpyxl import load_workbook
        from pathlib import Path

        path = Path(excel_path)
        if not path.exists():
            log(f"Excel file not found: {excel_path}", "WARN")
            return False

        wb = load_workbook(str(path))

        # Tạo sheet config nếu chưa có
        if 'config' not in wb.sheetnames:
            ws = wb.create_sheet('config')
            ws['A1'] = 'key'
            ws['B1'] = 'value'
        else:
            ws = wb['config']

        # Các key cần lưu
        config_items = {
            'account_channel': channel,
            'account_index': str(account_index),
            'account_email': account_email,
        }

        for key, value in config_items.items():
            # Tìm row có key này để update
            found = False
            for row in range(2, ws.max_row + 1):
                cell_key = ws.cell(row=row, column=1).value
                if cell_key and str(cell_key).strip().lower() == key.lower():
                    ws.cell(row=row, column=2, value=value)
                    found = True
                    break

            # Nếu chưa có, thêm row mới
            if not found:
                next_row = ws.max_row + 1
                ws.cell(row=next_row, column=1, value=key)
                ws.cell(row=next_row, column=2, value=value)

        wb.save(str(path))
        log(f"Saved account info to Excel: {account_email} (index {account_index})")
        return True

    except Exception as e:
        log(f"Error saving account to Excel: {e}", "ERROR")
        return False


def get_account_from_excel(excel_path: str) -> dict:
    """
    Đọc thông tin tài khoản từ Excel config sheet.

    Args:
        excel_path: Đường dẫn đến file Excel

    Returns:
        {"channel": "AR35", "index": 0, "email": "xxx@gmail.com"} hoặc None nếu chưa có
    """
    try:
        from openpyxl import load_workbook
        from pathlib import Path

        path = Path(excel_path)
        if not path.exists():
            return None

        wb = load_workbook(str(path), read_only=True)

        if 'config' not in wb.sheetnames:
            wb.close()
            return None

        ws = wb['config']

        result = {}
        for row in range(2, ws.max_row + 1):
            cell_key = ws.cell(row=row, column=1).value
            cell_value = ws.cell(row=row, column=2).value

            if not cell_key:
                continue

            key = str(cell_key).strip().lower()
            value = str(cell_value) if cell_value else ""

            if key == 'account_channel':
                result['channel'] = value
            elif key == 'account_index':
                try:
                    result['index'] = int(value)
                except:
                    result['index'] = 0
            elif key == 'account_email':
                result['email'] = value

        wb.close()

        # Chỉ trả về nếu có đủ thông tin
        if 'channel' in result and 'index' in result and 'email' in result:
            log(f"Read account from Excel: {result['email']} (index {result['index']})")
            return result

        return None

    except Exception as e:
        log(f"Error reading account from Excel: {e}", "WARN")
        return None


def set_account_index_for_resume(excel_path: str, channel: str) -> bool:
    """
    Đọc thông tin account từ Excel và set vào index tracker để resume đúng account.

    Args:
        excel_path: Đường dẫn đến file Excel
        channel: Mã kênh hiện tại

    Returns:
        True nếu đã restore account index từ Excel
    """
    account_info = get_account_from_excel(excel_path)

    if not account_info:
        return False

    # Kiểm tra channel khớp
    if account_info.get('channel', '').upper() != channel.upper():
        log(f"Channel mismatch: Excel has {account_info.get('channel')}, current is {channel}", "WARN")
        return False

    # Set account index
    saved_index = account_info.get('index', 0)
    save_account_index(channel, saved_index)
    log(f"Restored account index {saved_index} for channel {channel} from Excel")
    return True


def detect_machine_code() -> str:
    """
    Detect mã máy từ đường dẫn thư mục tool.

    Ví dụ:
    - C:\\Users\\Admin\\Documents\\AR57-T1\\ve3-tool-simple → AR57-T1
    - D:\\VMs\\AR4-T1\\ve3-tool-simple → AR4-T1
    - C:\\Users\\hoangmai\\Documents\\AR4-T1\\ve3-tool-simple → AR4-T1
    """
    tool_path = TOOL_DIR.resolve()

    # Lấy thư mục cha của ve3-tool-simple
    parent = tool_path.parent

    # Mã máy thường có dạng: XX#-T# hoặc XX##-T# hoặc XX##-####
    # Ví dụ: AR4-T1, AR57-T1, AR47-0028
    # Pattern linh hoạt: 2 chữ cái + 1-3 số + dash + alphanumeric
    code_pattern = re.compile(r'^[A-Z]{2}\d{1,3}-[A-Z0-9]+$', re.IGNORECASE)

    # Kiểm tra parent folder
    if code_pattern.match(parent.name):
        return parent.name.upper()

    # Kiểm tra grandparent (Documents\AR57-T1\ve3-tool-simple)
    grandparent = parent.parent
    if code_pattern.match(grandparent.name):
        return grandparent.name.upper()

    # Thử tìm trong path
    for part in tool_path.parts:
        if code_pattern.match(part):
            return part.upper()

    return ""


def load_gsheet_client():
    """Load Google Sheet client."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        log("gspread not installed. Run: pip install gspread google-auth", "ERROR")
        return None, None

    if not CONFIG_FILE.exists():
        log(f"Config file not found: {CONFIG_FILE}", "ERROR")
        return None, None

    try:
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))

        sa_path = (
            cfg.get("SERVICE_ACCOUNT_JSON") or
            cfg.get("service_account_json") or
            cfg.get("CREDENTIAL_PATH") or
            cfg.get("credential_path")
        )

        if not sa_path:
            log("Missing SERVICE_ACCOUNT_JSON in config", "ERROR")
            return None, None

        spreadsheet_name = cfg.get("SPREADSHEET_NAME")
        if not spreadsheet_name:
            log("Missing SPREADSHEET_NAME in config", "ERROR")
            return None, None

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]

        sa_file = Path(sa_path)
        if not sa_file.exists():
            sa_file = TOOL_DIR / "config" / sa_path

        if not sa_file.exists():
            log(f"Service account file not found: {sa_path}", "ERROR")
            return None, None

        creds = Credentials.from_service_account_file(str(sa_file), scopes=scopes)
        gc = gspread.authorize(creds)

        return gc, spreadsheet_name

    except Exception as e:
        log(f"Error loading gsheet client: {e}", "ERROR")
        return None, None


def extract_channel_from_machine_code(machine_code: str) -> str:
    """
    Extract channel code from machine code.
    Examples:
        AR35-T1 -> AR35
        AR47-T2 -> AR47
        KA2-T1 -> KA2
    """
    if "-T" in machine_code.upper():
        return machine_code.upper().split("-T")[0]
    if "-" in machine_code:
        return machine_code.rsplit("-", 1)[0].upper()
    return machine_code.upper()


def get_account_info(machine_code: str, max_retries: int = 3) -> dict:
    """
    Lấy thông tin tài khoản từ Google Sheet.

    v1.0.105: Đọc từ sheet THÔNG TIN theo mã kênh (không phải mã máy).
    - Cột B: Mã kênh (AR35, AR47, KA2...)
    - Cột AT: Tài khoản Veo3 (format: id|pass|2fa per line)

    Hỗ trợ xoay vòng tài khoản: mỗi kênh có thể có nhiều tài khoản,
    sẽ lần lượt sử dụng từng tài khoản.

    Args:
        machine_code: Mã máy (VD: AR35-T1) - sẽ extract thành mã kênh (AR35)
        max_retries: Số lần retry khi gặp lỗi

    Returns:
        {"id": "email@gmail.com", "password": "xxx", "totp_secret": "...", "index": N, "total": M}
        or None if not found
    """
    # Extract channel from machine code
    channel_code = extract_channel_from_machine_code(machine_code)
    log(f"Machine code: {machine_code} -> Channel: {channel_code}")

    # Get current account for this channel (with rotation support)
    account = get_current_account_for_channel(channel_code)

    if account:
        log(f"Account for {channel_code}: {account['id']} (index {account['index']+1}/{account['total']})")
        if account.get('totp_secret'):
            log(f"  -> 2FA secret found ({len(account['totp_secret'])} chars)")

    return account


def login_google_chrome(account_info: dict, chrome_portable: str = None, profile_dir: str = None, worker_id: int = 0) -> bool:
    """
    Mở Chrome và đăng nhập Google bằng JavaScript.

    Do Google có nhiều biện pháp chống bot, script này sẽ:
    1. Mở Chrome đến trang đăng nhập
    2. Dùng JavaScript để điền email/password và trigger events
    3. Để user xác thực nếu cần

    Args:
        account_info: Dict với 'id' (email) và 'password'
        chrome_portable: Đường dẫn Chrome Portable cụ thể (nếu có).
                        Quan trọng khi có nhiều Chrome chạy song song.
        profile_dir: Đường dẫn profile Chrome cụ thể (nếu có).
                    Dùng cho Chrome 2 với profile riêng (ví dụ: pic2).
        worker_id: Worker ID để dùng port khác nhau cho mỗi Chrome.
    """
    try:
        from DrissionPage import ChromiumPage, ChromiumOptions
    except ImportError:
        log("DrissionPage not installed. Run: pip install DrissionPage", "ERROR")
        return False

    email = account_info["id"]
    password = account_info["password"]

    log(f"Opening Chrome for login: {email}")

    try:
        # Setup Chrome options
        options = ChromiumOptions()

        # === Port riêng cho mỗi Chrome (tránh conflict) ===
        # Chrome 1 (worker_id=0): port 9222
        # Chrome 2 (worker_id=1): port 9223
        base_port = 9222 + worker_id
        options.set_local_port(base_port)  # Dùng set_local_port như drission_flow_api.py
        log(f"Using port: {base_port} (worker_id={worker_id})")

        # Ưu tiên chrome_portable được truyền vào (cho Chrome 2 song song)
        chrome_exe = None
        if chrome_portable and Path(chrome_portable).exists():
            chrome_exe = chrome_portable
            log(f"Using specified Chrome: {chrome_exe}")
        else:
            # Fallback: Tìm Chrome Portable mặc định
            chrome_paths = [
                TOOL_DIR / "GoogleChromePortable" / "GoogleChromePortable.exe",
                Path.home() / "Documents" / "GoogleChromePortable" / "GoogleChromePortable.exe",
            ]
            for cp in chrome_paths:
                if cp.exists():
                    chrome_exe = str(cp)
                    break

        if chrome_exe:
            options.set_browser_path(chrome_exe)
            log(f"Using Chrome: {chrome_exe}")

            # === Profile: ưu tiên profile_dir được truyền vào ===
            if profile_dir and Path(profile_dir).exists():
                options.set_user_data_path(str(profile_dir))
                log(f"Using profile: {profile_dir}")
            else:
                # Fallback: dùng profile mặc định của Chrome Portable
                chrome_dir = Path(chrome_exe).parent
                for data_path in [chrome_dir / "Data" / "profile", chrome_dir / "User Data"]:
                    if data_path.exists():
                        options.set_user_data_path(str(data_path))
                        log(f"Using default profile: {data_path}")
                        break

        # Mở Chrome mới
        driver = ChromiumPage(options)

        # Đi đến trang đăng nhập Google
        log("Navigating to Google login...")
        driver.get("https://accounts.google.com/signin")
        time.sleep(3)

        # Kiểm tra xem đã đăng nhập chưa
        if "myaccount.google.com" in driver.url or "google.com/search" in driver.url:
            log("Already logged in!", "OK")
            return True

        # === BƯỚC 1: ĐIỀN EMAIL ===
        log("Finding email input...")
        try:
            # Tìm input email
            email_input = driver.ele('#identifierId', timeout=5)
            if not email_input:
                email_input = driver.ele('input[type="email"]', timeout=3)

            if email_input:
                log(f"Found email input, filling: {email}")
                # Click để focus
                email_input.click()
                time.sleep(0.3)

                # Dùng JavaScript để set value và trigger events
                js_set_email = f'''
                    this.value = "{email}";
                    this.dispatchEvent(new Event('input', {{bubbles: true}}));
                    this.dispatchEvent(new Event('change', {{bubbles: true}}));
                '''
                email_input.run_js(js_set_email)
                log(f"Email filled via JS")
                time.sleep(0.5)

                # Nhấn Enter hoặc click Next
                log("Clicking Next button...")
                try:
                    next_btn = driver.ele('button:contains("Next")', timeout=2) or \
                               driver.ele('button:contains("Tiếp theo")', timeout=2) or \
                               driver.ele('button:contains("Tiếp tục")', timeout=2)
                    if next_btn:
                        next_btn.click()
                        log("Clicked Next button")
                    else:
                        # Fallback: nhấn Enter
                        email_input.input('\n')
                        log("Pressed Enter")
                except:
                    email_input.input('\n')
                    log("Pressed Enter (fallback)")

                time.sleep(3)
            else:
                log("Email input not found!", "WARN")
        except Exception as e:
            log(f"Email step error: {e}", "WARN")

        # === BƯỚC 2: ĐIỀN PASSWORD (Ctrl+V) ===
        log("Entering password with Ctrl+V...")
        try:
            # Đợi trang password load
            time.sleep(3)

            # Copy password vào clipboard
            try:
                import pyperclip
                pyperclip.copy(password)
                log("Password copied to clipboard")
            except ImportError:
                # Fallback nếu không có pyperclip - dùng Windows clipboard
                import subprocess
                subprocess.run(['clip'], input=password.encode(), check=True)
                log("Password copied to clipboard (via clip)")

            # Gửi Ctrl+V để paste
            from DrissionPage.common import Actions
            actions = Actions(driver)
            actions.key_down('ctrl').key_down('v').key_up('v').key_up('ctrl')
            log("Sent Ctrl+V")
            time.sleep(0.5)

            # Nhấn Enter để submit
            actions.key_down('enter').key_up('enter')
            log("Pressed Enter")
        except Exception as e:
            log(f"Password step error: {e}", "WARN")

        # === BƯỚC 3: XỬ LÝ 2FA (nếu có) ===
        totp_secret = account_info.get("totp_secret", "")
        if totp_secret:
            log(f"2FA secret found ({len(totp_secret)} chars), checking for 2FA prompt...")
            time.sleep(3)

            try:
                # v1.0.125: Cải thiện 2FA handling
                # Một số nick: sau pass → OTP input xuất hiện luôn (không cần click option)
                # Một số nick: sau pass → cần click "Google Authenticator" → rồi mới nhập OTP

                # 1. Tạo OTP và copy vào clipboard trước
                import pyotp
                clean_secret = totp_secret.replace(" ", "").replace("-", "").upper()
                totp = pyotp.TOTP(clean_secret)
                otp_code = totp.now()
                log(f"Generated OTP: {otp_code}")

                try:
                    import pyperclip
                    pyperclip.copy(otp_code)
                    log("OTP copied to clipboard")
                except ImportError:
                    import subprocess
                    subprocess.run(['clip'], input=otp_code.encode(), check=True)
                    log("OTP copied to clipboard (via clip)")

                from DrissionPage.common import Actions
                actions = Actions(driver)

                # 2. Thử Ctrl+V + Enter trực tiếp (cho nick không cần click option)
                log("Trying direct Ctrl+V for OTP...")
                actions.key_down('ctrl').key_down('v').key_up('v').key_up('ctrl')
                time.sleep(0.5)
                actions.key_down('enter').key_up('enter')
                log("Sent Ctrl+V + Enter")
                time.sleep(2)

                # 3. Kiểm tra xem có cần click option không (nếu vẫn còn trên trang 2FA)
                # Nếu có option "Google Authenticator" → click và nhập lại OTP
                auth_selectors = [
                    'text:Google Authenticator',
                    'text:Ứng dụng xác thực',
                    'text:Authenticator app',
                    'text:Use your authenticator app',
                    'text:Dùng ứng dụng xác thực',
                    'text=Google Authenticator',
                    'text=Authenticator',
                ]

                for selector in auth_selectors:
                    try:
                        auth_option = driver.ele(selector, timeout=1)
                        if auth_option:
                            log(f"Found 2FA option: {selector} - clicking...")
                            auth_option.click()
                            time.sleep(2)

                            # Ctrl+V + Enter lại sau khi click option
                            log("Sending Ctrl+V + Enter after clicking option...")
                            actions.key_down('ctrl').key_down('v').key_up('v').key_up('ctrl')
                            time.sleep(0.5)
                            actions.key_down('enter').key_up('enter')
                            log("Sent Ctrl+V + Enter")
                            break
                    except:
                        continue

            except ImportError:
                log("pyotp not installed! Run: pip install pyotp", "ERROR")
            except Exception as e:
                log(f"2FA step error: {e}", "WARN")

        # === KIỂM TRA LOGIN THỰC SỰ THÀNH CÔNG ===
        log("Waiting for login to complete...")
        time.sleep(5)

        # Kiểm tra URL sau khi login
        max_check = 5
        login_success = False
        for check in range(max_check):
            current_url = driver.url.lower()
            log(f"Check {check+1}/{max_check}: URL = {current_url[:60]}...")

            # Login thành công nếu URL không còn ở trang accounts.google.com/signin
            if "accounts.google.com/signin" not in current_url and \
               "accounts.google.com/v3/signin" not in current_url:
                # Kiểm tra thêm: không phải trang error/challenge
                if "accounts.google.com" not in current_url or \
                   "myaccount.google.com" in current_url:
                    login_success = True
                    log("Login SUCCESS - URL changed!", "OK")
                    break

            time.sleep(2)

        if not login_success:
            log("Login FAILED - still on login page!", "ERROR")
            # Đóng Chrome
            try:
                driver.quit()
            except:
                pass
            return False

        # v1.0.149: Retry 30 lần, reload mỗi 10 lần
        log("Navigating to Flow to warm up session...")
        flow_url = "https://labs.google/fx/vi/tools/flow"
        try:
            driver.get(flow_url)
            time.sleep(3)  # Đợi ngắn rồi tìm ngay
            log(f"Flow: {driver.url[:50]}")

            click_success = False

            for attempt in range(30):
                # Reload page mỗi 10 lần
                if attempt > 0 and attempt % 10 == 0:
                    log(f"Reloading page (attempt {attempt})...")
                    driver.refresh()
                    time.sleep(3)

                log(f"Finding button ({attempt + 1}/30)...")

                # Tìm button "add_2" (Dự án mới)
                try:
                    btn = driver.ele('tag:button@@text():add_2', timeout=2)
                    if btn:
                        log("Found 'add_2' button - page ready!")
                        click_success = True
                        break
                except:
                    pass

                # Thử click "Create" button
                try:
                    create_btn = driver.ele('tag:button@@text():Create', timeout=2)
                    if create_btn:
                        log("Clicking 'Create'...")
                        create_btn.click()
                        time.sleep(2)
                except:
                    pass

                time.sleep(1)

            if click_success:
                log("Session warmed up!")
            else:
                log("Button not found after 30 attempts", "WARN")

        except Exception as e:
            log(f"Flow warm up error (non-critical): {e}", "WARN")

        log("Closing browser...")

        # Đóng Chrome
        try:
            driver.quit()
            log("Chrome closed")
        except:
            pass

        return True

    except Exception as e:
        log(f"Login error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("  VE3 TOOL - GOOGLE LOGIN HELPER")
    print("=" * 60)

    # 1. Detect machine code
    machine_code = detect_machine_code()

    if not machine_code:
        log("Cannot detect machine code from path", "ERROR")
        log(f"Current path: {TOOL_DIR}")
        log("Expected pattern: XX#-T# hoặc XX##-T# (ví dụ: AR4-T1, AR57-T1)")

        # Cho user nhập manual
        machine_code = input("\nEnter machine code (e.g., AR57-T1): ").strip().upper()
        if not machine_code:
            log("No machine code provided", "ERROR")
            return 1

    log(f"Machine code: {machine_code}")

    # 2. Get account info from sheet
    log(f"Reading account info from sheet '{SHEET_NAME}'...")
    account_info = get_account_info(machine_code)

    if not account_info:
        log("Cannot get account info", "ERROR")
        return 1

    # 3. Login to Google
    log("Starting Google login...")
    success = login_google_chrome(account_info)

    if success:
        log("=" * 60)
        log("  LOGIN COMPLETED!")
        log("=" * 60)
        return 0
    else:
        log("Login failed", "ERROR")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
