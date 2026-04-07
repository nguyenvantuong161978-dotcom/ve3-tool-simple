# VE3 Tool Simple - Project Context

## Tổng quan
**Phần mềm tạo video YouTube tự động** sử dụng Veo3 Flow (labs.google/fx).

- **Owner**: nguyenvantuong161978-dotcom
- **Repo**: https://github.com/nguyenvantuong161978-dotcom/ve3-tool-simple
- Tool chạy trên **MÁY ẢO (VM)**, tạo Excel → Ảnh → Video → copy về **MÁY CHỦ (Master)**

## Workflow tổng quan

```
MÁY CHỦ (Master - Z:\AUTO)
  │ (1) Chứa SRT gốc trong AUTO/{code}/
  ▼
MÁY ẢO (VM) - Tool này
  ├── Excel Worker: SRT → Excel (7 steps qua API DeepSeek/Gemini)
  ├── Chrome Worker 1: Excel → Ảnh scenes chẵn + Reference images (nv/loc)
  └── Chrome Worker 2: Excel → Ảnh scenes lẻ
  │ (2) Copy kết quả về master
  ▼
MÁY CHỦ (Master)
  └── AUTO/visual/{code}/ (Excel + img/ + nv/ + thumb/)
```

## 2 Chức năng chính

1. **PY Đạo Diễn (Excel Worker)**: SRT → Excel kịch bản (7 bước API)
2. **Flow Image/Video (Chrome Workers)**: Prompts → Ảnh/Video qua Google Veo3 Flow

## Chế độ chạy (Video Modes)

| Mode | Mô tả |
|------|--------|
| `full` | Tạo tất cả scenes + videos |
| `small` | Chỉ tạo ảnh, KHÔNG tạo video |
| `basic` | Tối thiểu - ít scenes hơn |

---

## Kiến trúc file

### Entry Points
| File | Mô tả |
|------|--------|
| `vm_manager_gui.py` | GUI chính (Tkinter), điều phối workers |
| `vm_manager.py` | VMManager class - logic điều phối |
| `START.py` / `START.bat` | Khởi động tool |
| `run_excel_api.py` | Excel Worker - SRT → Excel (7 bước API), chạy `--loop` continuous |
| `_run_chrome1.py` | Chrome Worker 1 - scenes chẵn + references |
| `_run_chrome2.py` | Chrome Worker 2 - scenes lẻ |
| `google_login.py` | Đăng nhập Gmail cho Chrome workers |
| `_pre_login.py` | Pre-login setup |
| `run_worker.py` | Worker runner |

### Modules chính (`modules/`)

| File | Mô tả |
|------|--------|
| `smart_engine.py` | **Engine chính** - điều phối tạo ảnh/video, quản lý references, retry logic |
| `drission_flow_api.py` | **DrissionPage API** - browser automation cho Google Flow, fingerprint spoof, proxy, 403 recovery |
| `browser_flow_generator.py` | Browser automation - submit prompts, poll results, download images |
| `progressive_prompts.py` | **7-step pipeline** SRT → Excel (story → segments → chars → locs → director → planning → prompts) |
| `excel_manager.py` | PromptWorkbook class - đọc/ghi Excel (characters, locations, scenes sheets) |
| `ai_providers.py` | API calls DeepSeek/Gemini với retry logic |
| `google_flow_api.py` | Google Flow API (REST mode, không dùng browser) |
| `server_pool.py` | Load balancing nhiều server |
| `chrome_manager.py` | Quản lý Chrome processes, kill by port/folder, clear data |
| `fingerprint_data.py` | Browser fingerprint data cho anti-detection |
| `chrome_token_extractor.py` | Extract auth token từ Chrome |
| `auto_token.py` | Auto-refresh token |
| `ipv6_manager.py` | Quản lý IPv6 rotation (legacy) |
| `ipv6_rotator.py` | IPv6 rotation logic |
| `ipv6_proxy.py` | IPv6 proxy setup |
| `ipv6_pool_client.py` | Client cho IPv6 Pool HTTP API |
| `agent_protocol.py` | Workers giao tiếp qua `.agent/status/*.json` |
| `robust_copy.py` | Copy project master↔VM, SMB reconnect, claim accounts |
| `shared_403_tracker.py` | Track 403 errors across workers |
| `reference_validator.py` | Validate reference images |
| `ken_burns.py` | Ken Burns effect cho video |
| `process_killer.py` | Kill processes |
| `settings_sync.py` | Sync settings |
| `central_logger.py` | Centralized logging |
| `utils.py` | Utilities |
| `voice_to_srt.py` | Voice → SRT conversion |
| `flow_image_generator.py` | Flow image generation |
| `parallel_flow_generator.py` | Parallel image generation |
| `prompts_generator.py` | Prompt generation |
| `prompts_loader.py` | Load prompts |

### Proxy Providers (`modules/proxy_providers/`)

Hệ thống proxy pluggable - mỗi provider kế thừa `ProxyProvider` ABC.

| File | Mô tả |
|------|--------|
| `base_provider.py` | Abstract base - interface: `get_ip()`, `rotate()`, `has_ttl()`, `get_ttl()`, `ensure_proxy_alive()` |
| `ipv6_provider.py` | IPv6 trực tiếp qua MikroTik router (cần ipv6_list.txt) |
| `ipv6_pool_provider.py` | IPv6 Pool HTTP API (port 8765) - quản lý pool IPv6 tập trung |
| `webshare_provider.py` | Webshare.io proxy service |
| `proxyxoay_provider.py` | ProxyXoay.shop - proxy xoay Việt Nam (SOCKS5/HTTP), mỗi worker 1 API key |
| `__init__.py` | Factory - chọn provider theo config (`ipv6`/`ipv6_pool`/`webshare`/`proxyxoay`) |

**TTL-aware proxy** (v1.0.663): Providers có TTL (ProxyXoay) tự rotate khi TTL thấp. `drission_flow_api.py` gọi `ensure_proxy_alive(min_ttl)` trước khi tạo ảnh (120s) hoặc video (420s).

### Topic Prompts (`modules/topic_prompts/`)

Prompt templates theo chủ đề cho 7-step pipeline.

| File | Chủ đề |
|------|--------|
| `story_prompts.py` | Story/narrative (default) |
| `psychology_prompts.py` | Tâm lý học |
| `psychology_video_prompts.py` | Tâm lý (video mode) |
| `finance_history_prompts.py` | Tài chính/lịch sử |
| `finance_history_vn_prompts.py` | Tài chính/lịch sử (VN) |
| `finance_video_prompts.py` | Tài chính (video mode) |

### Server Mode (`server/`)

Server nhận requests tạo ảnh từ nhiều VM (distributed mode).

| File | Mô tả |
|------|--------|
| `app.py` | Flask API server |
| `server_gui.py` | Server GUI (Tkinter) - config proxy, Chrome count |
| `chrome_pool.py` | Pool Chrome instances cho server, setup proxy providers |
| `chrome_session.py` | Quản lý Chrome session, login, fingerprint sync |
| `worker.py` | Server worker xử lý requests |
| `start_server.py` | Entry point server |

### IPv6 Pool (`ipv6/`)

Quản lý pool IPv6 tập trung qua MikroTik router API.

| File | Mô tả |
|------|--------|
| `ipv6_pool.py` | Core pool - manage IPs (available/in_use/burned/cooldown), auto-recover burned subnets |
| `ipv6_server.py` | HTTP API server (port 8765) - GET/ROTATE/BURN/STATUS endpoints |
| `ipv6_gui.py` | Pool GUI - hiển thị stats, logs, reset pool |
| `mikrotik_api.py` | RouterOS API - add/remove IPv6 addresses & routes, reserved subnet protection |

**Key concepts**:
- Subnet = /64 prefix, mỗi subnet có 1 gateway + nhiều IP
- Reserved subnets (01-65): 100 IP YouTube, KHÔNG BAO GIỜ bị pool đụng vào
- Burned subnet auto-recover sau 10 phút cooldown
- `rotate_all()`: Đổi toàn bộ pool (có delay 0.1s/lệnh để không crash router)

### Cấu trúc dữ liệu

```
PROJECTS/
└── {project_code}/
    ├── {code}.srt              # File phụ đề gốc
    ├── {code}_prompts.xlsx     # Excel kịch bản (7 sheets)
    ├── nv/                     # Reference images: nv1.png, nv2.png, loc1.png...
    ├── img/                    # Scene images: scene_001.png, scene_002.png...
    ├── video/                  # Scene videos: scene_001.mp4... (mode full)
    └── thumb/                  # Thumbnail (main character image)
```

### Config (`config/`)

| File | Mô tả |
|------|--------|
| `settings.yaml` | Config chính: API keys, Chrome paths, IPv6, proxy, video mode, server URLs |
| `prompts.yaml` | Custom prompt templates |
| `accounts.csv` | Google accounts cho login |
| `proxies.txt` | Proxy list |
| `session_state.yaml` | Session state tracking |

---

## Chi tiết 7-Step Pipeline (Excel Worker)

```
Input: {code}.srt → Output: {code}_prompts.xlsx

Step 1: Story Analysis     → Phân tích thể loại, mood, style
Step 2: Segments           → Chia SRT thành đoạn (~5-15 entries/đoạn)
                             + VALIDATION 1: Split segments ratio > 15
                             + VALIDATION 2: API bổ sung missing ranges
Step 3: Characters         → Phân tích nhân vật (id, name, appearance)
Step 4: Locations          → Phân tích địa điểm (id, name, atmosphere)
Step 5: Director Plan      → Tạo scenes cho từng segment
                             + GAP-FILL: Đảm bảo 100% SRT coverage
                             + 8s rule: scene duration 5-8s (full mode)
Step 6: Scene Planning     → Chi tiết: camera, lighting, composition
                             (parallel: 15 scenes/batch, max 10 concurrent)
Step 7: Scene Prompts      → Tạo img_prompt cho từng scene
                             (parallel: 10 scenes/batch, max 10 concurrent)
                             + Duplicate detection + fallback
                             + Metadata parse từ prompt (nv/loc IDs)
```

**Resume logic**: Mỗi step lưu status. Nếu bị ngắt → chạy lại từ step đang dở, không mất work.

**API retry**: Exponential backoff (3s base, max 15 retries). Handles 429, 5xx, timeout.

---

## Hệ thống chống 403 (5 lớp phòng thủ)

Google Flow rate limit/block IP khi request nhiều. 5 lớp xử lý:

```
Layer 1: Browser Cleanup
  → Xóa localStorage, IndexedDB, cookies, cache, service workers
  → Chạy NGAY sau 403 + sau mỗi ảnh thành công

Layer 2: Fingerprint Rotation
  → Browser fingerprint spoof (canvas, webGL, audio, navigator)
  → Đồng bộ fingerprint giữa login và tạo ảnh (cùng seed)
  → Đổi seed khi 403

Layer 3: Model Switch
  → 3 consecutive 403 → switch model (image ↔ video)
  → Counter tăng qua setup() (skip_403_reset=True)

Layer 4: IP Rotation
  → 5 total 403 → rotate IPv6/proxy
  → IPv6: Đổi IP trên MikroTik router
  → ProxyXoay: Rotate qua API (cooldown 60s)

Layer 5: Account Switch
  → Đổi Google account (từ accounts.csv)
  → Last resort
```

**Chrome Data Clearing**: Xóa `ChromePortable/Data/profile/*` NGOẠI TRỪ `First Run` file.

**403 Tracker**: `config/.403_tracker.json` - đếm 403 mỗi worker.

---

## Proxy System

### Chọn proxy (`modules/proxy_providers/__init__.py`)

```python
# Factory chọn provider theo settings.yaml > proxy_type:
# "ipv6"       → IPv6Provider (MikroTik trực tiếp)
# "ipv6_pool"  → IPv6PoolProvider (HTTP API port 8765)
# "webshare"   → WebshareProvider
# "proxyxoay"  → ProxyXoayProvider
```

### IPv6 Provider flow
```
MikroTik Router ←→ ipv6_provider.py
  → Add IPv6 address lên interface
  → Add default route ::/0 qua gateway
  → DNS: Gateway ::1 (primary) + Google (fallback)
  → Firewall: Block IPv4 cho Chrome (chỉ dùng IPv6)
  → Rotate: Xóa IP cũ + thêm IP mới
```

### ProxyXoay flow
```
proxyxoay.shop API ←→ proxyxoay_provider.py
  → Mỗi worker 1 API key riêng
  → SOCKS5/HTTP proxy endpoint
  → TTL tracking → auto-rotate khi TTL thấp
  → Auto-whitelist VM IPv4
```

### IPv6 Pool flow
```
ipv6_pool.py (port 8765) ←→ ipv6_pool_provider.py (client)
  → Pool quản lý ~150 subnets trên MikroTik
  → VM workers gọi GET /get_ip → nhận IPv6
  → 403 → POST /burn_ip → pool xóa subnet, chọn subnet mới
  → Burned subnets auto-recover sau 10 phút
  → Reserved subnets (01-65) KHÔNG BAO GIỜ bị đụng
```

---

## Server Mode (Distributed)

```
Server Machine (server/)
  ├── server_gui.py      → GUI config, start server
  ├── app.py             → Flask API: /api/fix/create-image-veo3, /api/fix/task-status
  ├── chrome_pool.py     → Pool Chrome instances + proxy providers
  └── chrome_session.py  → Login + fingerprint sync

VM Machines (clients)
  └── smart_engine.py    → POST prompts → server → poll status → download result
```

**Login trên server**: `chrome_session.py` login cùng port + cùng proxy với worker (v1.0.653). Fingerprint đồng bộ qua seed file (v1.0.650).

---

## SMB / Master Connection

```
VM ←→ Master qua SMB (Z:\AUTO hoặc \\IP\AUTO)
  → robust_copy.py: ensure_smb_connected() tự reconnect sau VM restart
  → Thu 3 IP máy chủ (88.254, 88.14, 88.100)
  → cmdkey lưu credential → Windows không hỏi lại
  → Project xong → copy img/ + Excel + thumb/ về AUTO/visual/{code}/
```

---

## Commands thường dùng

```bash
# Chạy GUI chính
python vm_manager_gui.py

# Chạy workers riêng
python run_excel_api.py --loop    # Excel worker continuous
python _run_chrome1.py            # Chrome worker 1
python _run_chrome2.py            # Chrome worker 2

# Server mode
python server/start_server.py     # hoặc server/server_gui.py

# IPv6 Pool
python -m ipv6.ipv6_gui           # Pool GUI

# Git
git push official main            # Push lên repo chính thức
```

---

## Lưu ý quan trọng

1. **Chrome Portable**: 2 instances riêng biệt
   - Chrome 1: `GoogleChromePortable/`
   - Chrome 2: `GoogleChromePortable - Copy/`
   - Kill Chrome theo thư mục (v1.0.192), KHÔNG kill Chrome khác

2. **Google Login**: Chrome PHẢI đăng nhập Google trước khi tạo ảnh
   - `google_login.py` xử lý login + OTP 2FA
   - Verify login qua myaccount.google.com
   - Retry 2 lần mỗi Chrome, cả 2 fail → DỪNG

3. **IPv6 DNS**: Dùng MikroTik gateway `::1` làm DNS primary (v1.0.679)
   - Google DNS `2001:4860:4860::8888` chỉ là fallback
   - VNPT drop/throttle UDP IPv6 tới Google DNS → mất mạng sau 55s

4. **Firewall IPv4**: Khi dùng IPv6, firewall block IPv4 cho Chrome
   - Khi chuyển sang proxy IPv4 (ProxyXoay/Webshare) → phải xóa firewall rules (v1.0.662)

5. **VERSION.txt**: PHẢI update trong cùng commit với code changes

6. **Agent Protocol**: Workers giao tiếp qua `.agent/status/*.json`

7. **Project Priority**: Project gần xong (completion % cao) → làm trước (v1.0.83)

8. **Auto-copy**: Project done → tự copy về master + tạo thumbnail (v1.0.34-35)

---

## Quy tắc xử lý lỗi

### 403 (Google block IP)
- Level 1: Worker 3x403 → cleanup browser data + restart
- Level 2: Total 5x403 → rotate IP + clear Chrome data + restart all

### Timeout
- Image: 120s timeout → retry 3 lần → skip scene
- Video: 180s timeout → retry 2 lần → mark for regenerate

### Chrome Disconnect
- Detect via DrissionPage → kill Chrome cũ → clear data → restart → resume

### API Errors (Excel Worker)
- 429 rate limit: Exponential backoff (3s × 2^n, max 15 retries)
- Missing data: VALIDATION 1+2, GAP-FILL ensures 100% SRT coverage
- Duplicate prompts (>80%): Tạo unique fallback, không skip batch

### Content Policy Violation
- Server retry 1 lần → nếu vẫn 400 → POLICY_VIOLATION → VM skip prompt + tạo .SKIP file

### SMB Mất kết nối
- `ensure_smb_connected()` tự reconnect, thử 3 IP máy chủ

---

## Phiên bản hiện tại

**VERSION**: 1.0.682 (2026-04-04)

Xem `VERSION.txt` để biết chi tiết tất cả các phiên bản và thay đổi.
