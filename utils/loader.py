import json
from pathlib import Path

def load_json_file(file_path: Path) -> any:
    """Đọc và giải mã dữ liệu từ tệp JSON sử dụng định dạng UTF-8."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
