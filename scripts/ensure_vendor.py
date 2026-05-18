from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.vendor_bootstrap import (
    PYVIDEOTRANS_REPO_URL,
    check_pyvideotrans_vendor,
    ensure_pyvideotrans_vendor,
    format_vendor_error,
    get_pyvideotrans_dir,
)


def print_validation_error(message: str) -> None:
    print(message, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap vendor/pyvideotrans khi cần.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Chỉ kiểm tra vendor, không clone nếu thiếu.",
    )
    parser.add_argument(
        "--repo-url",
        default=PYVIDEOTRANS_REPO_URL,
        help="Repo pyvideotrans dùng để clone khi vendor chưa có.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    vendor_dir = get_pyvideotrans_dir(PROJECT_ROOT)
    if args.check:
        status = check_pyvideotrans_vendor(PROJECT_ROOT)
    else:
        if vendor_dir.exists():
            print("vendor/pyvideotrans đã tồn tại, bỏ qua clone.")
        else:
            print(f"Đang clone pyvideotrans từ {args.repo_url}...")
        status = ensure_pyvideotrans_vendor(runtime_root=PROJECT_ROOT, repo_url=args.repo_url)

    if not status.ready:
        print_validation_error(format_vendor_error(status))
        return 1

    print("Vendor pyvideotrans đã sẵn sàng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
