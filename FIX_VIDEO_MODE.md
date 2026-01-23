# FIX: Video Mode Logic (BASIC vs FULL)

## VẤN ĐỀ

**Triệu chứng:**
- Đặt `video_mode: basic` trong settings.yaml
- Nhưng Chrome workers vẫn tạo video cho **TẤT CẢ scenes** có ảnh
- Không phân biệt Segment 1 hay Segment 2+

**Nguyên nhân:**
- Code trong `browser_flow_generator.py` (dòng 4501-4526) chỉ check:
  - Scene có `media_id` không?
  - Scene có `video_path` chưa?
  - Scene `status_vid` đã done chưa?
- **KHÔNG CHECK mode** hay segment nào!

---

## GIẢI PHÁP

### Logic mới: Dùng field `video_note` để đánh dấu

**Nguyên tắc:**
- BASIC mode: Chỉ Segment 1 làm video → Segment 2+ đánh dấu "SKIP"
- FULL mode: Tất cả segments làm video → Không có "SKIP"

### Quy trình:

```
┌─────────────────────────────────────────────────────────┐
│ BƯỚC 1: EXCEL WORKER TẠO SCENES                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Khi tạo Scene object (progressive_prompts.py):        │
│                                                         │
│ IF excel_mode == "basic" AND segment_id > 1:          │
│    video_note = "SKIP"                                 │
│ ELSE:                                                   │
│    video_note = ""  (tạo video)                        │
│                                                         │
└─────────────────────────────────────────────────────────┘

                         ↓

┌─────────────────────────────────────────────────────────┐
│ BƯỚC 2: EXCEL LƯU SCENES VÀO FILE                      │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Scene object lưu vào Excel với field video_note:      │
│                                                         │
│ Scene 1 (Segment 1): video_note = ""                   │
│ Scene 2 (Segment 1): video_note = ""                   │
│ Scene 3 (Segment 2): video_note = "SKIP"  ← Bỏ qua    │
│ Scene 4 (Segment 2): video_note = "SKIP"  ← Bỏ qua    │
│                                                         │
└─────────────────────────────────────────────────────────┘

                         ↓

┌─────────────────────────────────────────────────────────┐
│ BƯỚC 3: CHROME WORKER TẠO VIDEO                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ FOR each scene:                                        │
│    IF scene.video_note == "SKIP":                      │
│       continue  ← Bỏ qua, không tạo video             │
│                                                         │
│    ELSE:                                                │
│       Tạo video từ media_id                            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## CODE CHANGES

### 1. Scene Class (excel_manager.py)

**Thêm field `video_note`:**

```python
class Scene:
    def __init__(
        self,
        # ... existing fields ...
        video_note: str = "",  # NEW: Ghi chú video: "SKIP" = bỏ qua
    ):
        # ... initialization ...
        self.video_note = video_note

    def to_dict(self):
        return {
            # ... existing fields ...
            "video_note": self.video_note,  # NEW
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            # ... existing fields ...
            video_note=str(data.get("video_note", "") or ""),  # NEW
        )
```

### 2. Director Plan - Lưu segment_id (progressive_prompts.py:1849)

**Lưu segment_id để biết scene thuộc segment nào:**

```python
for seg_idx in range(len(story_segments)):
    seg_scenes = segment_results.get(seg_idx, [])
    segment_id = seg_idx + 1  # Segment 1, 2, 3...
    for scene in seg_scenes:
        scene["scene_id"] = scene_id_counter
        scene["segment_id"] = segment_id  # LƯU segment_id
        all_scenes.append(scene)
        scene_id_counter += 1
```

### 3. Set video_note khi tạo Scene (progressive_prompts.py:2420-2429)

**Set "SKIP" cho Segment 2+ trong BASIC mode:**

```python
# Xác định video_note dựa trên mode và segment
video_note = ""
excel_mode = self.config.get("excel_mode", "full").lower()
segment_id = original.get("segment_id", 1)  # Default segment 1
if excel_mode == "basic" and segment_id > 1:
    video_note = "SKIP"  # BASIC mode: chỉ làm video cho Segment 1

scene = Scene(
    scene_id=scene_id,
    # ... other fields ...
    video_note=video_note  # GHI CHÚ VIDEO
)
```

### 4. Check video_note khi tạo video (browser_flow_generator.py:4518-4525)

**Bỏ qua scenes có video_note="SKIP":**

```python
video_note = getattr(scene, 'video_note', '') or ''

if not media_id:
    scenes_without_media_id.append(scene_id)
elif not video_path and status_vid != 'done':
    # CHECK video_note: Nếu là "SKIP" thì bỏ qua scene này
    if video_note == "SKIP":
        continue  # BỎ QUA scene này (BASIC mode, segment > 1)

    video_prompt = getattr(scene, 'video_prompt', '') or 'Subtle cinematic motion'
    scenes_for_video.append({
        'scene_id': scene_id,
        'media_id': media_id,
        'video_prompt': video_prompt
    })
```

---

## KẾT QUẢ

### BASIC Mode (excel_mode: basic, video_mode: basic)

**Story có 3 segments:**
- Segment 1 (Opening): Scenes 1-5
- Segment 2 (Middle): Scenes 6-10
- Segment 3 (End): Scenes 11-15

**ẢNH (Image) creation:**
```
Scenes 1-5:   TẠO ẢNH ✅
Scenes 6-10:  TẠO ẢNH ✅
Scenes 11-15: TẠO ẢNH ✅
```
**Kết quả ảnh:** 15 ảnh (tất cả scenes)

**VIDEO creation:**
```
Scenes 1-5:   video_note = ""     → TẠO VIDEO ✅
Scenes 6-10:  video_note = "SKIP" → BỎ QUA ❌
Scenes 11-15: video_note = "SKIP" → BỎ QUA ❌
```
**Kết quả video:** Chỉ có 5 videos (Segment 1)

**Tóm tắt BASIC mode:**
- Tạo ẢNH cho TẤT CẢ các segments
- Chỉ tạo VIDEO cho Segment 1 (phần opening)
- Segment 2+ chỉ có ảnh, không có video
- **Duration constraint:** Mỗi scene: 5-8 giây (tuân thủ max_scene_duration)

### FULL Mode (excel_mode: full, video_mode: full)

**Story có 3 segments:**
- Segment 1: Scenes 1-5
- Segment 2: Scenes 6-10
- Segment 3: Scenes 11-15

**ẢNH (Image) creation:**
```
Scenes 1-5:   TẠO ẢNH ✅
Scenes 6-10:  TẠO ẢNH ✅
Scenes 11-15: TẠO ẢNH ✅
```
**Kết quả ảnh:** 15 ảnh (tất cả scenes)

**VIDEO creation:**
```
Scenes 1-5:   video_note = "" → TẠO VIDEO ✅
Scenes 6-10:  video_note = "" → TẠO VIDEO ✅
Scenes 11-15: video_note = "" → TẠO VIDEO ✅
```
**Kết quả video:** 15 videos (tất cả scenes)

**Tóm tắt FULL mode:**
- Tạo ẢNH cho TẤT CẢ các segments
- Tạo VIDEO cho TẤT CẢ các segments

---

## TESTING

### Test 1: Video Note Assignment

Chạy: `python test_video_note.py`

**Kết quả:**
```
[OK] BASIC mode, Segment 1 -> should create video
[OK] BASIC mode, Segment 2 -> should SKIP
[OK] BASIC mode, Segment 3 -> should SKIP
[OK] FULL mode, Segment 1 -> should create video
[OK] FULL mode, Segment 2 -> should create video
[OK] FULL mode, Segment 3 -> should create video

RESULT: ALL TESTS PASSED!
```

### Test 2: Video Generation Skip Logic

Chạy: `python test_video_skip_logic.py`

**Kết quả:**
```
Scenes for video creation: 3
  - Scene 1: Motion 1
  - Scene 3: Motion 3
  - Scene 5: Motion 5

Scenes skipped: 2
  - Scene 2: SKIPPED
  - Scene 4: SKIPPED

[OK] Video creation list correct: ['1', '3', '5']
[OK] Skip list correct: ['2', '4']

RESULT: ALL TESTS PASSED!
```

---

## SỬ DỤNG

**Không cần thay đổi gì!** Logic tự động hoạt động dựa trên setting:

```yaml
# config/settings.yaml
excel_mode: basic  # hoặc "full"
video_mode: basic  # hoặc "full"
```

**BASIC mode:**
- Excel worker tạo scenes với `video_note = "SKIP"` cho Segment 2+
- Chrome worker tự động bỏ qua scenes có `video_note = "SKIP"`
- Chỉ tạo video cho Segment 1

**FULL mode:**
- Tất cả scenes có `video_note = ""`
- Chrome worker tạo video cho tất cả scenes có ảnh

---

**Ngày fix:** 2026-01-23
**Files thay đổi:**
- `modules/excel_manager.py` (Scene class)
- `modules/progressive_prompts.py` (director plan + scene creation)
- `modules/browser_flow_generator.py` (video generation)

**Tests:**
- `test_video_note.py` - Test video_note assignment logic
- `test_video_skip_logic.py` - Test video generation skip behavior
