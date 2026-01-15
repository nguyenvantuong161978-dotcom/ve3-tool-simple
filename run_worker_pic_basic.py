#!/usr/bin/env python3
"""
VE3 Tool - Worker PIC BASIC Mode
================================
Phiên bản đơn giản:
- KHÔNG đổi IP - dùng IP máy có sẵn
- KHÔNG giới hạn 8s - theo nội dung segment
- Số ảnh = số ảnh từ Step 1.5 (story segments)
- Duration = duration của segment / số ảnh

Usage:
    python run_worker_pic_basic.py                     (quét và xử lý tự động)
    python run_worker_pic_basic.py AR47-0028           (chạy 1 project cụ thể)
"""

import sys
import os
import time
import shutil
from pathlib import Path

# Add current directory to path
TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

# Import từ run_worker (dùng chung logic)
from run_worker import (
    detect_auto_path,
    POSSIBLE_AUTO_PATHS,
    get_channel_from_folder,
    matches_channel,
    is_project_complete_on_master,
    has_excel_with_prompts,
    needs_api_completion,
    copy_from_master,
    copy_to_visual,
    delete_local_project,
    SCAN_INTERVAL,
)

# Detect paths
AUTO_PATH = detect_auto_path()
if AUTO_PATH:
    MASTER_PROJECTS = AUTO_PATH / "ve3-tool-simple" / "PROJECTS"
    MASTER_VISUAL = AUTO_PATH / "VISUAL"
else:
    MASTER_PROJECTS = Path(r"\\tsclient\D\AUTO\ve3-tool-simple\PROJECTS")
    MASTER_VISUAL = Path(r"\\tsclient\D\AUTO\VISUAL")

LOCAL_PROJECTS = TOOL_DIR / "PROJECTS"
WORKER_CHANNEL = get_channel_from_folder()


def create_excel_with_api_basic(project_dir: Path, code: str, callback=None) -> bool:
    """
    Create Excel with prompts using API - BASIC mode.
    Uses segment-based image counts (no 8s limit).
    """
    def log(msg, level="INFO"):
        if callback:
            callback(msg, level)
        else:
            print(msg)

    try:
        from modules.progressive_prompts import ProgressivePromptsGenerator
        from modules.excel_manager import PromptWorkbook
        from modules.utils import parse_srt_file, load_config

        # Load config
        config = load_config()

        # Check SRT file
        srt_path = project_dir / f"{code}.srt"
        txt_path = project_dir / f"{code}.txt"

        if not srt_path.exists():
            log(f"  ERROR: No SRT file found!", "ERROR")
            return False

        srt_entries = parse_srt_file(str(srt_path))
        txt_content = txt_path.read_text(encoding='utf-8') if txt_path.exists() else ""

        # Create workbook
        excel_path = project_dir / f"{code}_prompts.xlsx"
        workbook = PromptWorkbook(str(excel_path))

        # Create generator
        generator = ProgressivePromptsGenerator(config)
        generator.log_callback = callback

        # Run steps - BASIC mode (segment-based)
        log(f"\n[STEP 1] Analyzing story...")
        result = generator.step_analyze_story(project_dir, code, workbook, srt_entries, txt_content)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        log(f"\n[STEP 1.5] Analyzing story segments...")
        result = generator.step_analyze_story_segments(project_dir, code, workbook, srt_entries)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        log(f"\n[STEP 2] Creating characters...")
        result = generator.step_create_characters(project_dir, code, workbook, srt_entries, txt_content)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        log(f"\n[STEP 3] Creating locations...")
        result = generator.step_create_locations(project_dir, code, workbook)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        # BASIC MODE: Use segment-based director plan
        log(f"\n[STEP 4] Creating director's plan (BASIC - segment-based)...")
        result = generator.step_create_director_plan_basic(project_dir, code, workbook, srt_entries)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        # Skip Step 4.5 in basic mode - not needed

        log(f"\n[STEP 5] Creating scene prompts...")
        result = generator.step_create_scene_prompts(project_dir, code, workbook)
        if result.status.value == "failed":
            log(f"  FAILED: {result.message}", "ERROR")
            return False

        log(f"\n✅ Excel created successfully (BASIC mode)!")
        return True

    except Exception as e:
        log(f"  ERROR: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False


def is_local_pic_complete(project_dir: Path, name: str) -> bool:
    """Check if local project has images created."""
    img_dir = project_dir / "img"
    if not img_dir.exists():
        return False

    img_files = list(img_dir.glob("*.png")) + list(img_dir.glob("*.jpg"))

    if len(img_files) == 0:
        return False

    try:
        from modules.excel_manager import PromptWorkbook
        excel_path = project_dir / f"{name}_prompts.xlsx"
        if excel_path.exists():
            wb = PromptWorkbook(str(excel_path))
            scenes = wb.get_scenes()
            expected = len([s for s in scenes if s.img_prompt])

            if len(img_files) >= expected:
                print(f"    [{name}] Images: {len(img_files)}/{expected} - COMPLETE")
                return True
            else:
                print(f"    [{name}] Images: {len(img_files)}/{expected} - incomplete")
                return False
    except Exception as e:
        print(f"    [{name}] Warning: {e}")

    return len(img_files) > 0


def process_project_pic_basic(code: str, callback=None) -> bool:
    """Process a single project - BASIC mode (no IP rotation)."""

    def log(msg, level="INFO"):
        if callback:
            callback(msg, level)
        else:
            print(msg)

    log(f"\n{'='*60}")
    log(f"[PIC BASIC] Processing: {code}")
    log(f"{'='*60}")

    # Step 1: Check if already done on master
    if is_project_complete_on_master(code):
        log(f"  Already in VISUAL folder, skip!")
        return True

    # Step 2: Copy from master
    local_dir = copy_from_master(code)
    if not local_dir:
        return False

    # Step 3: Check/Create Excel (BASIC mode)
    excel_path = local_dir / f"{code}_prompts.xlsx"
    srt_path = local_dir / f"{code}.srt"

    if not excel_path.exists():
        if srt_path.exists():
            log(f"  No Excel found, creating (BASIC mode)...")
            if not create_excel_with_api_basic(local_dir, code, callback):
                log(f"  Failed to create Excel, skip!", "ERROR")
                return False
        else:
            log(f"  No Excel and no SRT, skip!")
            return False
    elif not has_excel_with_prompts(local_dir, code):
        log(f"  Excel empty/corrupt, recreating (BASIC mode)...")
        excel_path.unlink()
        if not create_excel_with_api_basic(local_dir, code, callback):
            log(f"  Failed to recreate Excel, skip!", "ERROR")
            return False

    # Step 4: Create images - NO IP ROTATION (use local IP)
    try:
        from modules.drission_flow_api import DrissionFlowAPI
        from modules.excel_manager import PromptWorkbook
        from modules.utils import load_config

        config = load_config()

        # Load workbook
        wb = PromptWorkbook(str(excel_path))
        scenes = wb.get_scenes()
        characters = wb.get_characters()

        # Filter scenes and characters that need images
        pending_scenes = [s for s in scenes if s.img_prompt and s.status_img == "pending"]
        pending_chars = [c for c in characters if c.english_prompt and c.status == "pending"]

        log(f"  Excel: {excel_path.name}")
        log(f"  Mode: BASIC (no IP rotation)")
        log(f"  Pending: {len(pending_chars)} characters, {len(pending_scenes)} scenes")

        if not pending_chars and not pending_scenes:
            log(f"  Nothing to generate!")
            return True

        # Create DrissionFlowAPI (no proxy)
        flow = DrissionFlowAPI(config)
        flow.log_callback = callback

        # Generate character images first
        if pending_chars:
            log(f"\n  Generating {len(pending_chars)} character images...")
            img_dir = local_dir / "img"
            img_dir.mkdir(exist_ok=True)

            for char in pending_chars:
                if char.status == "skip":
                    continue

                log(f"    -> {char.id}: {char.name}")

                # Generate image
                result = flow.generate_image(
                    prompt=char.english_prompt,
                    output_path=str(img_dir / char.image_file),
                    reference_images=[]
                )

                if result:
                    char.status = "done"
                    wb.update_character(char)
                    wb.save()
                else:
                    log(f"       Failed!", "ERROR")

        # Generate scene images
        if pending_scenes:
            log(f"\n  Generating {len(pending_scenes)} scene images...")
            img_dir = local_dir / "img"
            img_dir.mkdir(exist_ok=True)

            for scene in pending_scenes:
                log(f"    -> Scene {scene.scene_id}")

                # Get reference images
                ref_images = []
                if scene.reference_files:
                    import json
                    try:
                        refs = json.loads(scene.reference_files) if isinstance(scene.reference_files, str) else scene.reference_files
                        for ref in refs:
                            ref_path = img_dir / ref
                            if ref_path.exists():
                                ref_images.append(str(ref_path))
                    except:
                        pass

                # Generate image
                output_file = f"scene_{scene.scene_id:03d}.png"
                result = flow.generate_image(
                    prompt=scene.img_prompt,
                    output_path=str(img_dir / output_file),
                    reference_images=ref_images
                )

                if result:
                    scene.status_img = "done"
                    wb.update_scene(scene)
                    wb.save()
                else:
                    log(f"       Failed!", "ERROR")

        # Close browser
        flow.close()

    except Exception as e:
        log(f"  Exception: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return False

    # Step 5: Check completion
    if is_local_pic_complete(local_dir, code):
        log(f"  Images complete!")
        return True
    else:
        log(f"  Images incomplete", "WARN")
        return False


def scan_incomplete_local_projects() -> list:
    """Scan local PROJECTS for incomplete projects."""
    incomplete = []

    if not LOCAL_PROJECTS.exists():
        return incomplete

    for item in LOCAL_PROJECTS.iterdir():
        if not item.is_dir():
            continue

        code = item.name

        if not matches_channel(code):
            continue

        if is_project_complete_on_master(code):
            continue

        if is_local_pic_complete(item, code):
            continue

        srt_path = item / f"{code}.srt"
        if has_excel_with_prompts(item, code):
            print(f"    - {code}: incomplete (has Excel, no images)")
            incomplete.append(code)
        elif srt_path.exists():
            print(f"    - {code}: has SRT, no Excel")
            incomplete.append(code)

    return sorted(incomplete)


def scan_master_projects() -> list:
    """Scan master PROJECTS folder for pending projects."""
    pending = []

    if not MASTER_PROJECTS.exists():
        return pending

    for item in MASTER_PROJECTS.iterdir():
        if not item.is_dir():
            continue

        code = item.name

        if not matches_channel(code):
            continue

        if is_project_complete_on_master(code):
            continue

        excel_path = item / f"{code}_prompts.xlsx"
        srt_path = item / f"{code}.srt"

        if has_excel_with_prompts(item, code):
            print(f"    - {code}: ready (has prompts)")
            pending.append(code)
        elif srt_path.exists():
            print(f"    - {code}: has SRT")
            pending.append(code)

    return sorted(pending)


def run_scan_loop():
    """Run continuous scan loop for IMAGE generation (BASIC mode)."""
    print(f"\n{'='*60}")
    print(f"  VE3 TOOL - WORKER PIC BASIC")
    print(f"{'='*60}")
    print(f"  Worker folder:   {TOOL_DIR.parent.name}")
    print(f"  Channel filter:  {WORKER_CHANNEL or 'ALL'}")
    print(f"  Mode:            BASIC (no IP rotation)")
    print(f"  Duration:        Segment-based (no 8s limit)")
    print(f"{'='*60}")

    cycle = 0

    while True:
        cycle += 1
        print(f"\n[BASIC CYCLE {cycle}] Scanning...")

        incomplete_local = scan_incomplete_local_projects()
        pending_master = scan_master_projects()
        pending = list(dict.fromkeys(incomplete_local + pending_master))

        if not pending:
            print(f"  No pending projects")
            print(f"\n  Waiting {SCAN_INTERVAL}s... (Ctrl+C to stop)")
            try:
                time.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print("\n\nStopped by user.")
                break
        else:
            print(f"  Found: {len(pending)} pending projects")

            for code in pending:
                try:
                    success = process_project_pic_basic(code)
                    if not success:
                        print(f"  Skipping {code}, moving to next...")
                        continue
                except KeyboardInterrupt:
                    print("\n\nStopped by user.")
                    return
                except Exception as e:
                    print(f"  Error processing {code}: {e}")
                    continue

            print(f"\n  Processed all pending projects!")
            print(f"  Waiting {SCAN_INTERVAL}s... (Ctrl+C to stop)")
            try:
                time.sleep(SCAN_INTERVAL)
            except KeyboardInterrupt:
                print("\n\nStopped by user.")
                break


def main():
    import argparse
    parser = argparse.ArgumentParser(description='VE3 Worker PIC BASIC - No IP Rotation')
    parser.add_argument('project', nargs='?', default=None, help='Project code')
    args = parser.parse_args()

    if args.project:
        process_project_pic_basic(args.project)
    else:
        run_scan_loop()


if __name__ == "__main__":
    main()
