from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_URL = "https://github.com/jianchang512/pyvideotrans.git"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PROJECT_ROOT / "vendor"
PYVIDEOTRANS_DIR = VENDOR_ROOT / "pyvideotrans"
REQUIRED_PATHS = (
    PYVIDEOTRANS_DIR / "videotrans" / "process" / "prepare_audio.py",
    PYVIDEOTRANS_DIR / "models" / "onnx" / "vocals.fp16.onnx",
    PYVIDEOTRANS_DIR / "models" / "onnx" / "accompaniment.fp16.onnx",
)


def validate_vendor() -> list[Path]:
    return [path for path in REQUIRED_PATHS if not path.exists()]


def clone_vendor(repo_url: str) -> None:
    if PYVIDEOTRANS_DIR.exists():
        print("vendor/pyvideotrans đã tồn tại, bỏ qua clone.")
        return
    if PYVIDEOTRANS_DIR.is_file():
        raise RuntimeError("vendor/pyvideotrans đang là file, không thể clone vendor.")

    VENDOR_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"Đang clone pyvideotrans từ {repo_url}...")
    subprocess.run(["git", "clone", repo_url, str(PYVIDEOTRANS_DIR)], check=True)


def print_validation_error(missing_paths: list[Path]) -> None:
    print("Vendor pyvideotrans chưa đầy đủ. Thiếu các path sau:", file=sys.stderr)
    for path in missing_paths:
        print(f"- {path.relative_to(PROJECT_ROOT)}", file=sys.stderr)
    print(
        "Hãy đảm bảo repo pyvideotrans đã clone đầy đủ hoặc chạy lại: "
        "rtk ./venb/bin/python scripts/ensure_vendor.py",
        file=sys.stderr,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap vendor/pyvideotrans khi cần.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Chỉ kiểm tra vendor, không clone nếu thiếu.",
    )
    parser.add_argument(
        "--repo-url",
        default=REPO_URL,
        help="Repo pyvideotrans dùng để clone khi vendor chưa có.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.check:
        try:
            clone_vendor(args.repo_url)
        except subprocess.CalledProcessError as exc:
            print(f"Clone pyvideotrans thất bại với mã lỗi {exc.returncode}.", file=sys.stderr)
            return exc.returncode or 1
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if not PYVIDEOTRANS_DIR.exists():
        print(
            "Chưa có vendor/pyvideotrans. Hãy chạy: "
            "rtk ./venb/bin/python scripts/ensure_vendor.py",
            file=sys.stderr,
        )
        return 1

    missing_paths = validate_vendor()
    if missing_paths:
        print_validation_error(missing_paths)
        return 1

    print("Vendor pyvideotrans đã sẵn sàng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
