from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from config.paths import Paths

DEFAULT_DB_PATH = Paths.get_config_path("pipeline_checkpoints.db")


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Khởi tạo cấu trúc bảng SQLite nếu chưa tồn tại."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                job_id TEXT,
                step_name TEXT,
                status TEXT,
                output_path TEXT,
                updated_at TEXT,
                PRIMARY KEY (job_id, step_name)
            )
            """
        )
        conn.commit()


def save_step_checkpoint(
    job_id: str,
    step_name: str,
    status: str,
    output_path: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    """Lưu hoặc ghi đè trạng thái của một bước chạy thuộc Job."""
    init_db(db_path)
    now_str = datetime.now().isoformat()
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO checkpoints (job_id, step_name, status, output_path, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, step_name, status, output_path, now_str),
        )
        conn.commit()


def get_completed_steps(job_id: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, dict[str, Any]]:
    """Lấy danh sách các bước đã hoàn tất của một Job."""
    init_db(db_path)
    steps = {}
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT step_name, status, output_path, updated_at
            FROM checkpoints
            WHERE job_id = ?
            """,
            (job_id,),
        )
        for row in cursor.fetchall():
            steps[row["step_name"]] = {
                "status": row["status"],
                "output_path": row["output_path"],
                "updated_at": row["updated_at"],
            }
    return steps


def clear_job_checkpoints(job_id: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    """Xóa toàn bộ checkpoints của một Job cụ thể."""
    init_db(db_path)
    with sqlite3.connect(str(db_path), timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM checkpoints
            WHERE job_id = ?
            """,
            (job_id,),
        )
        conn.commit()
