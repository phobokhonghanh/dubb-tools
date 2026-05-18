from __future__ import annotations

import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PYVIDEOTRANS_REPO_URL = "https://github.com/jianchang512/pyvideotrans.git"
PYVIDEOTRANS_ZIP_URL = "https://github.com/jianchang512/pyvideotrans/archive/refs/heads/main.zip"
PYVIDEOTRANS_RELATIVE_DIR = Path("vendor/pyvideotrans")
PYVIDEOTRANS_REQUIRED_RELATIVE_PATHS = (
    Path("videotrans/process/prepare_audio.py"),
    Path("models/onnx/vocals.fp16.onnx"),
    Path("models/onnx/accompaniment.fp16.onnx"),
)


@dataclass(frozen=True)
class VendorStatus:
    ready: bool
    vendor_dir: Path
    missing_paths: list[Path]


def get_runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def get_pyvideotrans_dir(runtime_root: str | Path | None = None) -> Path:
    root = Path(runtime_root).expanduser().resolve() if runtime_root else get_runtime_root()
    return root / PYVIDEOTRANS_RELATIVE_DIR


def check_pyvideotrans_vendor(runtime_root: str | Path | None = None) -> VendorStatus:
    vendor_dir = get_pyvideotrans_dir(runtime_root)
    missing_paths = [
        vendor_dir / relative_path
        for relative_path in PYVIDEOTRANS_REQUIRED_RELATIVE_PATHS
        if not (vendor_dir / relative_path).exists()
    ]
    return VendorStatus(ready=not missing_paths, vendor_dir=vendor_dir, missing_paths=missing_paths)


def ensure_pyvideotrans_vendor(
    *,
    runtime_root: str | Path | None = None,
    repo_url: str = PYVIDEOTRANS_REPO_URL,
    zip_url: str = PYVIDEOTRANS_ZIP_URL,
    on_progress: Callable[[str], None] | None = None,
) -> VendorStatus:
    status = check_pyvideotrans_vendor(runtime_root)
    if status.ready:
        _emit(on_progress, "Vendor pyvideotrans đã sẵn sàng.")
        return status

    vendor_dir = status.vendor_dir
    if vendor_dir.exists():
        _emit(on_progress, "Vendor pyvideotrans đã tồn tại, đang kiểm tra file bắt buộc...")
        return check_pyvideotrans_vendor(runtime_root)

    vendor_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        _emit(on_progress, "Đang clone pyvideotrans từ GitHub...")
        subprocess.run(["git", "clone", repo_url, str(vendor_dir)], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        if vendor_dir.exists():
            return check_pyvideotrans_vendor(runtime_root)
        _emit(on_progress, "Không dùng được Git, đang tải bản ZIP từ GitHub...")
        _download_vendor_zip(zip_url=zip_url, destination=vendor_dir, on_progress=on_progress)

    return check_pyvideotrans_vendor(runtime_root)


def format_vendor_error(status: VendorStatus) -> str:
    relative_missing = ", ".join(str(path) for path in status.missing_paths)
    return (
        "Vendor pyvideotrans chưa sẵn sàng. Thiếu: "
        f"{relative_missing}. App sẽ tự clone vendor khi thư mục chưa tồn tại; "
        "hãy kiểm tra kết nối mạng nếu lỗi vẫn xảy ra."
    )


def _download_vendor_zip(
    *,
    zip_url: str,
    destination: Path,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix="pyvideotrans_") as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "pyvideotrans.zip"
        extract_dir = temp_path / "extract"

        _emit(on_progress, "Đang tải vendor pyvideotrans...")
        urllib.request.urlretrieve(zip_url, archive_path)

        _emit(on_progress, "Đang giải nén vendor pyvideotrans...")
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)

        roots = [path for path in extract_dir.iterdir() if path.is_dir()]
        if not roots:
            raise RuntimeError("File ZIP pyvideotrans không có thư mục nguồn hợp lệ.")
        roots[0].rename(destination)


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    if callback:
        callback(message)
