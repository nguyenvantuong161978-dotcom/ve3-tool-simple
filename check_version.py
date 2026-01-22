"""
Check if code has latest fixes
"""
import sys
from pathlib import Path

print("=" * 70)
print("CHECKING CODE VERSION")
print("=" * 70)
print()

# Check drission_flow_api.py for fixes #1, #2, #3
drission_file = Path(__file__).parent / "modules" / "drission_flow_api.py"
smart_engine_file = Path(__file__).parent / "modules" / "smart_engine.py"

if not drission_file.exists():
    print("[ERROR] drission_flow_api.py not found!")
    sys.exit(1)

if not smart_engine_file.exists():
    print("[ERROR] smart_engine.py not found!")
    sys.exit(1)

with open(drission_file, 'r', encoding='utf-8') as f:
    drission_content = f.read()

with open(smart_engine_file, 'r', encoding='utf-8') as f:
    smart_content = f.read()

# Check for the fixes
has_fix1 = "if not chrome_exe and not self._chrome_portable and platform.system()" in drission_content
has_fix2 = "if not os.path.isabs(chrome_exe):" in drission_content
has_fix3 = "self._chrome_portable = chrome_exe" not in drission_content or "# NOTE: KHÔNG ghi đè self._chrome_portable" in drission_content

# Fix #4: Video BrowserFlowGenerator chrome_portable
has_fix4 = "chrome_portable=self.chrome_portable if self._chrome_portable_override else None  # CRITICAL: Chrome 2 override" in smart_content

print("Checking for Chrome 2 portable path fixes:")
print()
print(f"1. Auto-detect skip check: {'[OK] FOUND' if has_fix1 else '[X] MISSING'}")
print(f"2. Relative path conversion: {'[OK] FOUND' if has_fix2 else '[X] MISSING'}")
print(f"3. No override in auto-detect: {'[OK] FOUND' if has_fix3 else '[X] MISSING'}")
print(f"4. Video mode chrome_portable: {'[OK] FOUND' if has_fix4 else '[X] MISSING'}")
print()

if has_fix1 and has_fix2 and has_fix3 and has_fix4:
    print("[OK] Code has all 4 fixes!")
    print()
    print("Chrome 2 should now use: GoogleChromePortable - Copy path")
    print()
    print("If Chrome 2 still uses wrong portable:")
    print("  - RESTART all workers (stop and start again)")
    print("  - Python caches modules, need fresh start!")
else:
    print("[ERROR] Code MISSING fixes!")
    print()
    print("YOU NEED TO UPDATE CODE:")
    print("  1. Close tool")
    print("  2. Run UPDATE_MANUAL.bat")
    print("  3. Or click UPDATE button in GUI")
    print("  4. Or: git pull origin main")
    print("  5. RESTART all workers!")

print("=" * 70)
