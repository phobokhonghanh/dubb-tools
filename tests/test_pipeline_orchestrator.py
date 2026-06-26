from pathlib import Path
from unittest.mock import MagicMock, patch

from infrastructure.database.checkpoint import (
    get_completed_steps,
    init_db,
    save_step_checkpoint,
)
from core.use_cases.pipeline_orchestrator import (
    JobContext,
    PipelineConfig,
    run_pipeline,
)


def test_pipeline_checkpoint_skip(tmp_path):
    # Thiết lập cơ sở dữ liệu tạm thời
    db_file = tmp_path / "test_pipeline_checkpoints.db"
    init_db(db_file)

    # Thư mục workspace giả lập
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    job_dir = workspace_dir / "job_abc"
    job_dir.mkdir()

    # Tạo tệp tin tải về giả lập trên đĩa để pass qua kiểm tra tồn tại
    fake_downloaded_video = job_dir / "test_download.mp4"
    fake_downloaded_video.touch()

    # Lưu checkpoint hoàn thành bước download vào DB
    save_step_checkpoint(
        job_id="job_abc",
        step_name="download",
        status="success",
        output_path=str(fake_downloaded_video),
        db_path=db_file,
    )

    # Khởi tạo PipelineConfig
    config = PipelineConfig(
        source_mode="url",
        selected_steps=["download", "split"],
        workspace_root=str(workspace_dir),
        input_url="https://example.com/video.mp4",
    )

    # Khởi tạo JobContext để resume
    resume_ctx = JobContext(job_id="job_abc", job_dir=str(job_dir), source_stem="test")

    # Mock các bước chạy và hàm checkpoint
    with patch("core.use_cases.pipeline_orchestrator.get_completed_steps") as mock_get_completed_steps, patch(
        "core.use_cases.pipeline_orchestrator.save_step_checkpoint"
    ) as mock_save_step_checkpoint, patch("core.use_cases.pipeline_orchestrator._run_download") as mock_run_download, patch(
        "core.use_cases.pipeline_orchestrator._run_split"
    ) as mock_run_split, patch(
        "core.use_cases.pipeline_orchestrator.validate_pipeline_requirements"
    ) as mock_validate:

        # Trỏ các lệnh gọi kiểm tra/lưu checkpoint vào DB test tạm thời của chúng ta
        mock_get_completed_steps.side_effect = lambda job_id: get_completed_steps(job_id, db_path=db_file)
        mock_save_step_checkpoint.side_effect = (
            lambda job_id, step_name, status, output_path: save_step_checkpoint(
                job_id, step_name, status, output_path, db_path=db_file
            )
        )

        # Thực thi pipeline
        result = run_pipeline(config, resume_context=resume_ctx)

        # Kiểm tra kết quả thành công
        assert result.ok

        # Bước download phải được bỏ qua (không gọi hàm chạy download thực tế)
        mock_run_download.assert_not_called()

        # Bước split chưa có checkpoint nên phải được thực thi
        mock_run_split.assert_called_once()

        # Kiểm tra dữ liệu trả về cho bước download chứa đúng tệp tin phục hồi từ DB
        download_step = next(s for s in result.steps if s.step == "download")
        assert download_step.state == "done"
        assert download_step.output_path == str(fake_downloaded_video)

        # Kiểm tra xem bước split sau khi hoàn tất đã được ghi checkpoint mới chưa
        completed_after_run = get_completed_steps("job_abc", db_path=db_file)
        assert "split" in completed_after_run
        assert completed_after_run["split"]["status"] == "success"
