import os
from pathlib import Path
from infrastructure.database.checkpoint import (
    init_db,
    save_step_checkpoint,
    get_completed_steps,
    clear_job_checkpoints,
)


def test_checkpoint_flow(tmp_path):
    db_file = tmp_path / "test_checkpoints.db"

    # 1. Khởi tạo DB
    init_db(db_file)
    assert db_file.exists()

    # 2. Lấy dữ liệu khi chưa có gì
    steps = get_completed_steps("job-123", db_path=db_file)
    assert steps == {}

    # 3. Ghi nhận checkpoint cho bước đầu tiên
    save_step_checkpoint("job-123", "download", "success", "/path/to/video.mp4", db_path=db_file)
    steps = get_completed_steps("job-123", db_path=db_file)
    assert "download" in steps
    assert steps["download"]["status"] == "success"
    assert steps["download"]["output_path"] == "/path/to/video.mp4"

    # 4. Ghi đè cập nhật checkpoint
    save_step_checkpoint("job-123", "download", "success", "/path/to/video_new.mp4", db_path=db_file)
    steps = get_completed_steps("job-123", db_path=db_file)
    assert steps["download"]["output_path"] == "/path/to/video_new.mp4"

    # 5. Xóa checkpoints của job
    clear_job_checkpoints("job-123", db_path=db_file)
    steps = get_completed_steps("job-123", db_path=db_file)
    assert steps == {}
