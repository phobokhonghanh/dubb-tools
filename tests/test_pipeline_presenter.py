import pytest
from unittest.mock import MagicMock, patch

from app.presenter.pipeline_presenter import PipelinePresenter
from core.use_cases.pipeline_orchestrator import PipelineStepStatus, PipelineResult, PipelineProgress, JobContext


class MockView:
    def __init__(self):
        self.source_mode = "url"
        self.selected_steps = []
        self.workspace_root = ""
        self.input_url = ""
        self.local_video_path = ""
        self.input_audio_path = ""
        self.input_srt_path = ""
        self.translated_srt_path = ""
        self.merge_muted_video = ""
        self.merge_speech_audio = ""
        self.merge_background_audio = ""

        self.download_use_proxy = True
        self.stt_model_size = "base"
        self.stt_language = "auto"
        self.stt_speaker_mode = "1 người nói"
        self.translate_batch_enabled = True
        self.translate_batch_size = "10"
        self.stt_auto_normalize_enabled = False
        self.translate_model = "gemini-1.5-flash"
        self.translate_api_key = ""
        self.translate_target_language = "vi"
        self.translate_content_safety = False
        self.translate_replace_enabled = False
        self.translate_find_text = ""
        self.translate_replace_text = ""

        self.tts_provider = "edge-tts"
        self.tts_language = "vi"
        self.tts_voice_id = ""
        self.tts_rate = 0
        self.tts_volume = 0
        self.tts_pitch = 0
        self.tts_keep_segments = True
        self.tts_api_key = ""
        self.tts_voices = []

        self.intro_video = ""
        self.outro_video = ""
        self.merge_output_name = ""
        self.merge_speech_volume = 100
        self.merge_background_volume = 125

        self.busy = False
        self.job_dir = ""
        self.status_text = ""
        self.progress_value = 0.0
        self.progress_label = "Chưa chạy"
        self.logs = []
        self.step_statuses = {}
        self.result = None
        self.failed_step = ""

        self.refreshed = False
        self.notified_msg = None
        self.notified_color = None
        self.thread_target = None

    def refresh(self):
        self.refreshed = True

    def notify(self, message: str, color: str):
        self.notified_msg = message
        self.notified_color = color

    def run_in_thread(self, target):
        self.thread_target = target
        # Simulate synchronous execution in test
        target()


def test_pipeline_presenter_init():
    mock_service = MagicMock()
    mock_service.load_config.return_value = {
        "source_mode": "local_video",
        "selected_steps": ["split", "stt"],
        "workspace_root": "/tmp/workspace",
        "local_video_path": "/tmp/video.mp4",
    }
    mock_service.load_last_result.return_value = None

    view = MockView()
    presenter = PipelinePresenter(view, service=mock_service)
    
    # Mock nested services config load
    presenter.translate_service = MagicMock()
    presenter.translate_service.load_config.return_value = {}
    presenter.tts_service = MagicMock()
    presenter.tts_service.load_config.return_value = {}
    presenter.tts_service.list_voices.return_value = []

    presenter.init_presenter()

    assert view.source_mode == "local_video"
    assert "split" in view.selected_steps
    assert "stt" in view.selected_steps
    assert view.workspace_root == "/tmp/workspace"
    assert view.local_video_path == "/tmp/video.mp4"
    assert view.refreshed is True


def test_pipeline_presenter_start_pipeline_success():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    # Setup dummy successful job result
    expected_result = PipelineResult(
        ok=True,
        job_dir="/tmp/job_123",
        context=JobContext(job_id="job_123", job_dir="/tmp/job_123", source_stem="test"),
        steps=[PipelineStepStatus(step="split", state="done", output_path="/tmp/muted.mp4")],
        final_video="/tmp/job_123/final.mp4",
        error_message=None,
        elapsed_sec=5.0
    )
    mock_service.run_job.return_value = expected_result

    view = MockView()
    view.selected_steps = ["split"]
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.translate_service = MagicMock()
    presenter.translate_service.load_config.return_value = {}
    presenter.tts_service = MagicMock()
    presenter.tts_service.load_config.return_value = {}
    presenter.tts_service.list_voices.return_value = []

    presenter.init_presenter()
    presenter.start_pipeline()

    assert view.busy is False
    assert view.progress_value == 1.0
    assert view.progress_label == "Quy trình đã hoàn thành"
    assert "final.mp4" in view.status_text
    assert view.notified_msg == "Quy trình đã hoàn thành."


def test_pipeline_presenter_start_pipeline_error():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    # Setup dummy failed job result
    expected_result = PipelineResult(
        ok=False,
        job_dir="/tmp/job_123",
        context=JobContext(job_id="job_123", job_dir="/tmp/job_123", source_stem="test"),
        steps=[PipelineStepStatus(step="split", state="error", error_message="ONNX failed")],
        final_video=None,
        error_message="Lỗi chia tách",
        elapsed_sec=2.0
    )
    mock_service.run_job.return_value = expected_result

    view = MockView()
    view.selected_steps = ["split"]
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.translate_service = MagicMock()
    presenter.translate_service.load_config.return_value = {}
    presenter.tts_service = MagicMock()
    presenter.tts_service.load_config.return_value = {}
    presenter.tts_service.list_voices.return_value = []

    presenter.init_presenter()
    presenter.start_pipeline()

    assert view.busy is False
    assert view.failed_step == "split"
    assert "Lỗi chia tách" in view.status_text
    assert presenter.can_retry() is True


def test_pipeline_presenter_stop():
    mock_service = MagicMock()
    view = MockView()
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.stop_pipeline()
    mock_service.stop.assert_called_once()
    assert "yêu cầu dừng" in view.status_text


def test_pipeline_presenter_open_job_nonexistent():
    mock_service = MagicMock()
    view = MockView()
    view.job_dir = "/nonexistent/job_path"
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.open_job()
    assert "không tồn tại" in view.status_text


@patch("app.presenter.pipeline_presenter.open_folder")
@patch("app.presenter.pipeline_presenter.Path.exists")
def test_pipeline_presenter_open_job_exists(mock_exists, mock_open_folder):
    mock_exists.return_value = True
    mock_service = MagicMock()
    view = MockView()
    view.job_dir = "/existent/job_path"
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.open_job()
    mock_open_folder.assert_called_once_with("/existent/job_path")


def test_pipeline_presenter_sync_configs():
    mock_service = MagicMock()
    view = MockView()
    view.translate_model = "test-model"
    view.translate_api_key = "test-key"
    view.tts_provider = "gemini-tts"
    view.tts_api_key = "tts-key"
    view.tts_voice_id = "test-voice"
    
    presenter = PipelinePresenter(view, service=mock_service)
    
    presenter.translate_service = MagicMock()
    presenter.tts_service = MagicMock()
    presenter.tts_service.load_config.return_value = {"api_keys": {}, "voice_ids": {}}
    
    presenter.sync_configs_to_services()
    
    presenter.translate_service.save_config.assert_called_once()
    presenter.tts_service.save_config.assert_called_once()

