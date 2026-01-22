# VE3 Tool Simple - Project Context

## Tổng quan
**Phần mềm tạo video YouTube tự động** sử dụng Veo3 Flow (labs.google/fx).

### Mục đích
- Tool này chạy trên **MÁY ẢO (VM)**
- Các VM tạo: Excel (kịch bản) → Ảnh → Video → Visual
- Sau đó chuyển kết quả về **MÁY CHỦ (Master)**

### 2 Chức năng chính
1. **PY Đạo Diễn (Excel Worker)**: Tạo Excel kịch bản từ SRT - phân tích story, tạo segments, characters, locations, director plan, scene prompts
2. **Flow Image/Video (Chrome Workers)**: Tạo ảnh và video từ prompts bằng Google Veo3 Flow

- **Owner**: nguyenvantuong161978-dotcom
- **Repo chính thức**: https://github.com/nguyenvantuong161978-dotcom/ve3-tool-simple

## Kiến trúc chính

### Entry Points
- `vm_manager_gui.py` - GUI chính (Tkinter), quản lý workers
- `vm_manager.py` - Logic điều phối workers (VMManager class)
- `START.py` / `START.bat` - Khởi động tool

### Workers (chạy song song)
- **Excel Worker** (`run_excel_api.py`): Tạo Excel từ SRT (7 bước: story → segments → characters → locations → director_plan → scene_planning → prompts)
- **Chrome Worker 1** (`_run_chrome1.py`): Tạo ảnh scenes chẵn (2,4,6...) + reference images (nv/loc)
- **Chrome Worker 2** (`_run_chrome2.py`): Tạo ảnh scenes lẻ (1,3,5...)

### Modules quan trọng
- `modules/smart_engine.py` - Engine chính tạo ảnh/video
- `modules/drission_flow_api.py` - DrissionPage API cho Google Flow
- `modules/browser_flow_generator.py` - Browser automation
- `modules/excel_manager.py` - Quản lý Excel (PromptWorkbook)
- `modules/ipv6_manager.py` - Quản lý IPv6 rotation
- `modules/chrome_manager.py` - Quản lý Chrome instances

### Cấu trúc dữ liệu
```
PROJECTS/
└── {project_code}/
    ├── {code}.srt           # File phụ đề
    ├── {code}_prompts.xlsx  # Excel chứa prompts
    ├── nv/                  # Reference images (characters/locations)
    └── img/                 # Scene images (scene_001.png, ...)
```

## Config
- `config/settings.yaml` - Cấu hình chính (API keys, Chrome paths, IPv6...)
- `config/ipv6_list.txt` - Danh sách IPv6 addresses

## Quy tắc xử lý lỗi

### 403 Errors (Google Flow bị block)
- 3 lỗi liên tiếp → Xóa Chrome data + Restart worker
- 5 lỗi (bất kỳ worker) → Rotate IPv6 + Restart tất cả

### Chrome Data Clearing
- Xóa tất cả trong `Data/` folder
- GIỮ LẠI `Data/profile/First Run` để tránh first-run prompts

## Commands thường dùng

```bash
# Chạy GUI
python vm_manager_gui.py

# Chạy worker riêng
python run_excel_api.py --loop
python _run_chrome1.py
python _run_chrome2.py

# Git
git push official main  # Push lên repo chính thức
```

## Lưu ý quan trọng

1. **Chrome Portable**: Sử dụng 2 Chrome Portable riêng biệt
   - Chrome 1: `GoogleChromePortable/`
   - Chrome 2: `GoogleChromePortable - Copy/`

2. **Google Login**: Chrome phải đăng nhập Google trước khi chạy

3. **IPv6**: Cần có IPv6 list trong `config/ipv6_list.txt` để bypass rate limit

4. **Agent Protocol**: Workers giao tiếp qua `.agent/status/*.json`

## Recent Fixes

### 2026-01-22 - Chrome 2 Control Fix
- **CRITICAL**: Fixed Chrome 2 using wrong portable path
  - Added `not self._chrome_portable` check to prevent auto-detect override
  - Added relative-to-absolute path conversion in drission_flow_api.py
- Created check_version.py to verify fixes are applied
- Created FIX_CHROME2_INSTRUCTIONS.txt for user update guide
- Fixed CMD hiding (START.bat uses pythonw)
- Fixed Chrome window positioning (even split, no overlap)
- Added show_cmd_windows() function

### 2026-01-20
- Fix GUI hiển thị đúng ProjectStatus attributes
- Fix bug `scene_number` → `scene_id` trong `get_project_status()`
- Thêm Chrome data clearing khi 403 errors
- Xóa log cũ khi start worker mới
- Đổi UPDATE URL sang repo mới `ve3-tool-simple`

---

## GHI CHÚ CÔNG VIỆC (Session Notes)

> **QUAN TRỌNG**: Claude Code phải cập nhật section này sau mỗi phiên làm việc để phiên sau sử dụng hiệu quả.

### Phiên hiện tại: 2026-01-22 (Continued Session)

**RESOLUTION - Chrome 2 Portable Path Issue:**
- ✅ Fixes are IMPLEMENTED and VERIFIED on codebase (commit 43d3158)
- ✅ Both fixes confirmed present via check_version.py:
  1. Auto-detect skip check - prevents override when chrome_portable is set
  2. Relative-to-absolute path conversion - handles ./GoogleChromePortable paths
- ⚠️ User (thutruc) needs to UPDATE their code to get fixes
- 📄 Created FIX_CHROME2_INSTRUCTIONS.txt with step-by-step update guide

**Root Cause Identified:**
- Auto-detect code in drission_flow_api.py was running even when chrome_portable was set
- This caused Chrome 2 to use Chrome 1's portable path
- Fix: Added `not self._chrome_portable` check to auto-detect condition (line 2104)

**Fixes Applied (in modules/drission_flow_api.py):**
1. Line 2104: `if not chrome_exe and not self._chrome_portable and platform.system()...`
   - Auto-detect only runs if chrome_portable is NOT already set
2. Lines 2086-2088: Convert relative paths to absolute
   ```python
   if not os.path.isabs(chrome_exe):
       tool_dir = Path(__file__).parent.parent
       chrome_exe = str(tool_dir / chrome_exe)
   ```

**Completed this session:**
- [x] Created check_version.py script to verify fixes
- [x] Fixed Unicode errors in check_version.py (use ASCII instead)
- [x] Verified both fixes present in codebase
- [x] Created FIX_CHROME2_INSTRUCTIONS.txt for user
- [x] Committed and pushed to GitHub (commit 43d3158)
- [x] Updated CLAUDE.md documentation

**Next Steps for User (thutruc):**
1. Close tool completely
2. Run UPDATE_MANUAL.bat OR click UPDATE in GUI OR git pull
3. Run check_version.py to verify
4. Start tool and verify Chrome 2 uses correct path with " - Copy"

### Backlog (việc cần làm)
- [ ] Worker logs không hiển thị trong GUI (trade-off để Chrome automation hoạt động)
- [ ] Kiểm tra và làm sạch IPv6 list
- [ ] Test auto-recovery khi Chrome disconnect

### Lịch sử phiên trước
_(Thêm tóm tắt phiên cũ vào đây)_
