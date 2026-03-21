"""
Robust file copy module - xử lý copy qua mạng ổn định.

Ưu tiên:
1. robocopy (Windows native - retry tự động, xử lý network tốt nhất)
2. shutil fallback với retry + verify file size

Sử dụng:
    from modules.robust_copy import robust_copy_file, robust_copy_tree

    # Copy 1 file
    robust_copy_file(src_path, dst_path)

    # Copy cả thư mục
    robust_copy_tree(src_dir, dst_dir)
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable


def _log_default(msg: str, level: str = "INFO"):
    """Default log function."""
    print(f"  [{level}] {msg}")


def robust_copy_file(
    src: str,
    dst: str,
    max_retries: int = 3,
    retry_delay: int = 5,
    verify: bool = True,
    log: Callable = None,
) -> bool:
    """
    Copy 1 file với retry + verify.

    Args:
        src: Đường dẫn file nguồn
        dst: Đường dẫn file đích
        max_retries: Số lần retry tối đa
        retry_delay: Thời gian chờ giữa các retry (giây)
        verify: Kiểm tra file size sau copy
        log: Hàm log

    Returns:
        True nếu copy thành công
    """
    log = log or _log_default
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        log(f"[COPY] File nguồn không tồn tại: {src}", "ERROR")
        return False

    src_size = src_path.stat().st_size

    # Tạo thư mục đích nếu chưa có
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        try:
            # Copy file
            shutil.copy2(str(src_path), str(dst_path))

            # Verify file size
            if verify and dst_path.exists():
                dst_size = dst_path.stat().st_size
                if dst_size == src_size:
                    return True
                else:
                    log(f"[COPY] Size mismatch: src={src_size} dst={dst_size} ({src_path.name})", "WARN")
                    # Xóa file lỗi, retry
                    try:
                        dst_path.unlink()
                    except Exception:
                        pass
            elif not verify:
                return True

        except Exception as e:
            log(f"[COPY] Lỗi copy {src_path.name} (lần {attempt + 1}/{max_retries}): {e}", "WARN")

        if attempt < max_retries - 1:
            log(f"[COPY] Retry sau {retry_delay}s...", "INFO")
            time.sleep(retry_delay)

    log(f"[COPY] THẤT BẠI copy {src_path.name} sau {max_retries} lần!", "ERROR")
    return False


def robust_copy_tree(
    src: str,
    dst: str,
    max_retries: int = 3,
    retry_delay: int = 5,
    verify: bool = True,
    use_robocopy: bool = True,
    log: Callable = None,
) -> bool:
    """
    Copy thư mục với robocopy (ưu tiên) hoặc shutil fallback.

    Args:
        src: Thư mục nguồn
        dst: Thư mục đích
        max_retries: Số lần retry
        retry_delay: Thời gian chờ giữa retry (giây)
        verify: Kiểm tra file count + sizes sau copy
        use_robocopy: Thử robocopy trước (Windows)
        log: Hàm log

    Returns:
        True nếu copy thành công
    """
    log = log or _log_default
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        log(f"[COPY] Thư mục nguồn không tồn tại: {src}", "ERROR")
        return False

    # Đếm files nguồn
    src_files = list(src_path.rglob("*"))
    src_file_count = sum(1 for f in src_files if f.is_file())
    src_total_size = sum(f.stat().st_size for f in src_files if f.is_file())
    log(f"[COPY] {src_path.name}: {src_file_count} files, {src_total_size / 1024 / 1024:.1f} MB")

    # === PHƯƠNG ÁN 1: robocopy (Windows native) ===
    if use_robocopy and os.name == 'nt':
        result = _robocopy_tree(src_path, dst_path, max_retries, retry_delay, log)
        if result:
            if verify:
                ok = _verify_copy(src_path, dst_path, log)
                if ok:
                    return True
                log(f"[COPY] robocopy verify FAIL, thử shutil fallback...", "WARN")
            else:
                return True

    # === PHƯƠNG ÁN 2: shutil với retry từng file ===
    return _shutil_copy_tree(src_path, dst_path, max_retries, retry_delay, verify, log)


def _robocopy_tree(
    src: Path,
    dst: Path,
    max_retries: int,
    retry_delay: int,
    log: Callable,
) -> bool:
    """Copy bằng robocopy (Windows native)."""
    try:
        # robocopy src dst /E /R:retries /W:wait /NP /NFL /NDL
        # /E = copy subdirectories including empty
        # /R:n = number of retries on failed copies
        # /W:n = wait time between retries (seconds)
        # /NP = no progress percentage
        # /MT:4 = multi-threaded (4 threads)
        cmd = [
            'robocopy',
            str(src),
            str(dst),
            '/E',           # Copy tất cả subdirectories
            f'/R:{max_retries}',    # Retry mỗi file
            f'/W:{retry_delay}',    # Wait giữa retry
            '/NP',          # Không hiện progress %
            '/MT:4',        # 4 threads song song
            '/DCOPY:T',     # Copy directory timestamps
            '/COPY:DAT',    # Copy Data, Attributes, Timestamps
        ]

        log(f"[ROBOCOPY] {src.name} → {dst.name}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 phút max
        )

        # robocopy exit codes:
        # 0 = no files copied (already up to date)
        # 1 = files copied successfully
        # 2 = extra files/dirs found
        # 3 = 1+2
        # 4 = mismatched files
        # 8 = some files could not be copied
        # 16 = fatal error
        if result.returncode < 8:
            log(f"[ROBOCOPY] OK (exit code {result.returncode})")
            return True
        else:
            log(f"[ROBOCOPY] FAIL (exit code {result.returncode})", "WARN")
            if result.stderr:
                log(f"[ROBOCOPY] stderr: {result.stderr[:200]}", "WARN")
            return False

    except FileNotFoundError:
        log(f"[ROBOCOPY] robocopy không tồn tại trên máy này", "WARN")
        return False
    except subprocess.TimeoutExpired:
        log(f"[ROBOCOPY] Timeout 10 phút!", "ERROR")
        return False
    except Exception as e:
        log(f"[ROBOCOPY] Lỗi: {e}", "WARN")
        return False


def _shutil_copy_tree(
    src: Path,
    dst: Path,
    max_retries: int,
    retry_delay: int,
    verify: bool,
    log: Callable,
) -> bool:
    """Copy bằng shutil - từng file với retry."""
    log(f"[SHUTIL] Copy {src.name} → {dst.name}")

    # Tạo thư mục đích
    dst.mkdir(parents=True, exist_ok=True)

    failed_files = []
    copied_count = 0
    total_files = 0

    for item in src.rglob("*"):
        if item.is_file():
            total_files += 1
            rel_path = item.relative_to(src)
            dest_file = dst / rel_path

            ok = robust_copy_file(
                str(item),
                str(dest_file),
                max_retries=max_retries,
                retry_delay=retry_delay,
                verify=verify,
                log=log,
            )

            if ok:
                copied_count += 1
            else:
                failed_files.append(str(rel_path))
        elif item.is_dir():
            # Tạo thư mục
            rel_path = item.relative_to(src)
            (dst / rel_path).mkdir(parents=True, exist_ok=True)

    if failed_files:
        log(f"[SHUTIL] FAIL: {len(failed_files)}/{total_files} files lỗi!", "ERROR")
        for f in failed_files[:5]:
            log(f"  - {f}", "ERROR")
        return False

    log(f"[SHUTIL] OK: {copied_count}/{total_files} files")
    return True


def _verify_copy(src: Path, dst: Path, log: Callable) -> bool:
    """Verify copy: so sánh file count + sizes."""
    src_files = {
        str(f.relative_to(src)): f.stat().st_size
        for f in src.rglob("*") if f.is_file()
    }
    dst_files = {
        str(f.relative_to(dst)): f.stat().st_size
        for f in dst.rglob("*") if f.is_file()
    }

    # Check missing files
    missing = set(src_files.keys()) - set(dst_files.keys())
    if missing:
        log(f"[VERIFY] THIẾU {len(missing)} files!", "ERROR")
        for f in list(missing)[:5]:
            log(f"  - {f}", "ERROR")
        return False

    # Check size mismatch
    size_mismatch = []
    for name, src_size in src_files.items():
        if name in dst_files and dst_files[name] != src_size:
            size_mismatch.append((name, src_size, dst_files[name]))

    if size_mismatch:
        log(f"[VERIFY] {len(size_mismatch)} files size SAI!", "ERROR")
        for name, ss, ds in size_mismatch[:5]:
            log(f"  - {name}: src={ss} dst={ds}", "ERROR")
        return False

    log(f"[VERIFY] OK: {len(src_files)} files verified")
    return True


def find_auto_path(log: Callable = None) -> Optional[str]:
    """
    Tìm AUTO path khả dụng - thử nhiều đường dẫn.

    Returns:
        Đường dẫn AUTO path nếu tìm thấy, None nếu không
    """
    log = log or _log_default

    # Danh sách paths theo thứ tự ưu tiên
    candidates = [
        r"Z:\AUTO",
        r"Y:\AUTO",
        r"\\tsclient\D\AUTO",
        r"\\tsclient\C\AUTO",
        r"\\vmware-host\Shared Folders\D\AUTO",
        r"\\VBOXSVR\AUTO",
        r"D:\AUTO",
        r"C:\AUTO",
    ]

    for path in candidates:
        try:
            p = Path(path)
            if p.exists() and p.is_dir():
                log(f"[AUTO] Tìm thấy: {path}")
                return path
        except Exception:
            continue

    log(f"[AUTO] Không tìm thấy AUTO path nào!", "ERROR")
    return None


def robust_delete_tree(
    path: str,
    max_retries: int = 3,
    retry_delay: int = 3,
    log: Callable = None,
) -> bool:
    """
    Xóa thư mục với retry + force delete readonly files.

    Returns:
        True nếu xóa thành công
    """
    log = log or _log_default
    dir_path = Path(path)

    if not dir_path.exists():
        return True

    def _on_rm_error(func, path, exc_info):
        """Handle readonly files on Windows."""
        import stat
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    for attempt in range(max_retries):
        try:
            shutil.rmtree(str(dir_path), onerror=_on_rm_error)
            if not dir_path.exists():
                return True
        except Exception as e:
            log(f"[DELETE] Lỗi xóa {dir_path.name} (lần {attempt + 1}/{max_retries}): {e}", "WARN")

        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    log(f"[DELETE] THẤT BẠI xóa {dir_path.name} sau {max_retries} lần!", "WARN")
    return False
