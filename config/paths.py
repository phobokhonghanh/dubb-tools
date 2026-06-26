from __future__ import annotations

import sys
from pathlib import Path


class Paths:
    # ROOT_DIR: Thư mục chứa mã nguồn/tài nguyên tĩnh (nằm trong _MEIPASS nếu chạy file đóng gói)
    ROOT_DIR: Path = Path(getattr(sys, "_MEIPASS")) if hasattr(sys, "_MEIPASS") else Path(__file__).resolve().parent.parent

    # REAL_ROOT_DIR: Thư mục gốc thực tế nơi ghi file (thư mục chứa file exe/app nếu chạy đóng gói)
    REAL_ROOT_DIR: Path = Path(sys.executable).resolve().parent if hasattr(sys, "_MEIPASS") else ROOT_DIR

    # CONFIG_DIR: Thư mục chứa cấu hình và database
    CONFIG_DIR: Path = REAL_ROOT_DIR / "config"

    # RESOURCES_DIR: Thư mục chứa resources tĩnh
    RESOURCES_DIR: Path = ROOT_DIR / "resources"

    # TEMP_DIR: Thư mục chứa file tạm
    TEMP_DIR: Path = REAL_ROOT_DIR / "temp"

    @classmethod
    def get_config_path(cls, filename: str) -> Path:
        return cls.CONFIG_DIR / filename
