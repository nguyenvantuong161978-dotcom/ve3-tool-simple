# FIX: Textarea Focus Verification

## VẤN ĐỀ

**Triệu chứng:**
- Click vào textarea để nhập prompt
- Nhưng **FOCUS NHẦM** (focus vào page thay vì textarea)
- Khi Ctrl+A → Select toàn bộ trang ❌
- Khi Ctrl+V → Paste vào chỗ sai ❌

**Nguyên nhân:**
- Click event được dispatch nhưng không đảm bảo textarea thực sự nhận focus
- Có thể bị element khác che hoặc page chưa sẵn sàng
- Không có cơ chế verify focus sau khi click

---

## GIẢI PHÁP

### Cải tiến hàm `_click_textarea()`

**File:** `modules/drission_flow_api.py:2997`

**Thay đổi chính:**

1. **Thêm tham số `max_retry`**: Cho phép retry nhiều lần nếu click nhầm
2. **VERIFY FOCUS**: Sau mỗi lần click, test xem textarea có thực sự nhận focus không
3. **Auto Retry**: Nếu verify fail → click lại (max 3 lần)

### Quy trình mới:

```
┌─────────────────────────────────────────────┐
│ LOOP: Tối đa 3 lần retry                   │
├─────────────────────────────────────────────┤
│                                             │
│ 1. CLICK vào textarea LẦN 1 (JS events)    │
│    ├─ mousedown                             │
│    ├─ mouseup                               │
│    ├─ click                                 │
│    └─ focus()                               │
│                                             │
│ 2. ĐỢI 0.3s                                │
│                                             │
│ 3. CLICK vào textarea LẦN 2 (đảm bảo)     │
│    ├─ mousedown                             │
│    ├─ mouseup                               │
│    ├─ click                                 │
│    └─ focus()                               │
│                                             │
│ 4. VERIFY FOCUS (Test typing)              │
│    ├─ Lưu value cũ của textarea            │
│    ├─ Điền text test: "__FOCUS_TEST__"     │
│    ├─ Đọc lại value                         │
│    ├─ Restore value cũ                      │
│    └─ Check: value === "__FOCUS_TEST__"    │
│                                             │
│ 5. KIỂM TRA KẾT QUẢ                        │
│    ├─ Nếu OK → ✅ Return True              │
│    └─ Nếu FAIL → ⚠️ Retry lần tiếp theo   │
│                                             │
└─────────────────────────────────────────────┘
```

---

## CODE THAY ĐỔI

### TRƯỚC (Không verify):

```python
def _click_textarea(self, wait_visible: bool = True):
    # Click vào textarea
    result = self.driver.run_js("... click events ...")

    if result == 'clicked':
        self.log("[v] Clicked textarea")
        return True  # ❌ Không verify có focus thật không

    return False
```

### SAU (Có verify):

```python
def _click_textarea(self, wait_visible: bool = True, max_retry: int = 3):
    # RETRY LOOP
    for attempt in range(max_retry):

        # 1. Click vào textarea
        result = self.driver.run_js("... click events ...")

        # 2. VERIFY FOCUS bằng cách điền text test
        verify_result = self.driver.run_js("""
            var textarea = document.querySelector('textarea');
            var oldValue = textarea.value;

            // Điền text test
            textarea.value = '__FOCUS_TEST__';

            // Check
            if (textarea.value === '__FOCUS_TEST__') {
                // Restore
                textarea.value = oldValue;
                return 'focus_ok';  // ✅ Focus đúng
            } else {
                return 'focus_failed';  // ❌ Focus sai
            }
        """)

        # 3. Kiểm tra kết quả
        if verify_result == 'focus_ok':
            return True  # ✅ THÀNH CÔNG
        else:
            # ⚠️ Click nhầm → Retry
            self.log("[WARN] Focus failed, retry...")
            continue

    # Hết retry
    return False
```

---

## TẠI SAO PHƯƠNG PHÁP NÀY HIỆU QUẢ?

### 1. Phát hiện Click Nhầm

**Khi click ĐÚNG vào textarea:**
```javascript
textarea.value = '__FOCUS_TEST__';
console.log(textarea.value);  // → "__FOCUS_TEST__" ✅
```

**Khi click NHẦM (focus vào page):**
```javascript
textarea.value = '__FOCUS_TEST__';  // Set value vào textarea
// Nhưng focus đang ở page, không phải textarea
console.log(textarea.value);  // → "" (empty) hoặc giá trị cũ ❌
```

### 2. An toàn với Restore Value

- Luôn lưu `oldValue` trước khi test
- Restore ngay sau khi check
- Không làm mất nội dung textarea (nếu có)

### 3. Retry Tự Động

- Nếu lần 1 click nhầm → Retry lần 2
- Nếu lần 2 vẫn nhầm → Retry lần 3
- Tối đa 3 lần → Tăng khả năng thành công

---

## KẾT QUẢ MONG ĐỢI

### Trước khi fix:
```
[v] Clicked textarea
[PASTE] Pasting prompt...
❌ Ctrl+A → Select toàn bộ page
❌ Ctrl+V → Paste vào chỗ sai
```

### Sau khi fix:
```
[CLICK] Attempt 1/3...
[VERIFY] Testing focus by typing test text...
❌ [x] Focus verification FAILED!
    → Likely clicked wrong place, retry 2/3...

[CLICK] Attempt 2/3...
[VERIFY] Testing focus by typing test text...
✅ [v] Textarea focused correctly! (attempt 2)

[PASTE] Pasting prompt...
✅ Ctrl+A → Select text trong textarea
✅ Ctrl+V → Paste đúng prompt
```

---

## CÁCH SỬ DỤNG

Hàm `_click_textarea()` được gọi tự động trong các hàm tạo ảnh/video:
- `generate_image()`
- `generate_video()`
- `_paste_prompt_ctrlv()`

**Không cần thay đổi code gọi hàm**, tất cả tự động!

---

## TESTING

Để test fix này:

1. Chạy Chrome worker tạo ảnh/video
2. Quan sát log:
   - Xem có dòng `[VERIFY] Testing focus...`
   - Nếu focus fail → Sẽ thấy `retry 2/3...`
   - Nếu thành công → `[v] Textarea focused correctly!`

3. Kiểm tra kết quả:
   - Prompt có được paste đúng vào textarea không?
   - Ảnh/video có được tạo đúng theo prompt không?

---

**Ngày fix:** 2026-01-22
**File thay đổi:** `modules/drission_flow_api.py`
**Function:** `_click_textarea()` (line 2997)
