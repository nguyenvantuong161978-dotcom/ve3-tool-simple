#!/usr/bin/env python3
"""
Check loc1 status in Excel
"""
import sys
from pathlib import Path

# Try to find Excel file
possible_paths = [
    Path("Z:/AUTO/AR8-0003/AR8-0003_prompts.xlsx"),
    Path("PROJECTS/AR8-0003/AR8-0003_prompts.xlsx"),
    Path("../AUTO/AR8-0003/AR8-0003_prompts.xlsx"),
]

excel_path = None
for p in possible_paths:
    if p.exists():
        excel_path = p
        break

if not excel_path:
    print("[ERROR] Excel file not found in any of these paths:")
    for p in possible_paths:
        print(f"  - {p}")
    sys.exit(1)

print(f"[OK] Found Excel: {excel_path}")
print()

# Read Excel
try:
    import openpyxl
    wb = openpyxl.load_workbook(str(excel_path), read_only=True)
    ws = wb['characters']

    # Find loc1
    found = False
    for row in ws.iter_rows(min_row=2):
        char_id = row[0].value
        if char_id == 'loc1':
            found = True
            print("=" * 70)
            print("LOC1 STATUS IN EXCEL:")
            print("=" * 70)
            print(f"ID: {row[0].value}")
            print(f"Name: {row[1].value}")
            print()
            prompt = row[2].value
            if prompt:
                print(f"English Prompt ({len(prompt)} chars):")
                print(f"  {prompt[:100]}...")
                if "empty" in prompt.lower():
                    print("  ✅ Contains 'empty' (FIXED)")
                else:
                    print("  ❌ Does NOT contain 'empty' (NOT FIXED)")
            else:
                print("English Prompt: [EMPTY]")
            print()

            media_id = row[4].value if len(row) > 4 else None
            if media_id:
                print(f"Media ID ({len(media_id)} chars):")
                print(f"  {media_id[:60]}...")
            else:
                print("Media ID: [EMPTY] ❌")
            print()

            status = row[6].value if len(row) > 6 else None
            print(f"Status: {status}")
            if status == "verified_fixed":
                print("  ✅ SUCCESSFULLY FIXED!")
            elif status == "fixing":
                print("  ⚠️  Still fixing...")
            elif status == "violated":
                print("  ❌ Violated (not fixed)")
            print("=" * 70)
            break

    if not found:
        print("[ERROR] loc1 not found in Excel")

    wb.close()

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
