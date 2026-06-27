import pytest
from unittest.mock import MagicMock, patch
from app.presenter.tts_presenter import TtsPresenter

class MockView:
    def __init__(self):
        self.input_srt = ""
        self.input_mode = "file"
        self.input_text = ""
        self.output_dir = ""
        self.provider = ""
        self.language = ""
        self.voice_ids = {}
        self.voice_id = ""
        self.rate = 0
        self.volume = 0
        self.pitch = 0
        self.keep_segments = True
        self.auto_merge = True
        self.max_workers = 5
        self.api_keys = {}
        self.api_key = ""
        self.voices = []
        self.status_text = ""
        self.stage_text = ""
        self.current_file_text = ""
        self.progress_value = None
        self.progress_visible = False
        self.show_progress_card = False
        self.segments = []
        self.line_count_text = ""
        self.busy = False
        self.output_file = None
        self.open_folder_visible = False
        
        self.refreshed = False
        self.notified_msg = None
        self.notified_color = None
        self.thread_target = None
        
    def refresh(self):
        self.refreshed = True
        
    def notify(self, message: str, bgcolor: str):
        self.notified_msg = message
        self.notified_color = bgcolor
        
    def run_in_thread(self, target):
        self.thread_target = target
        # Chạy trực tiếp target đồng bộ để mô phỏng kiểm thử dễ dàng
        target()

def test_presenter_init():
    mock_service = MagicMock()
    mock_service.load_config.return_value = {
        "provider": "edge-tts",
        "language": "vi",
        "voice_ids": {"edge-tts": "vi-VN-HoaiMyNeural"},
        "rate": 10,
        "volume": -5,
        "keep_segments": False,
        "auto_merge": True,
        "max_workers": 4,
    }
    from infrastructure.providers.tts.models import TtsVoice
    mock_service.list_voices.return_value = [
        TtsVoice(id="vi-VN-HoaiMyNeural", name="Hoài My", locale="vi-VN", gender="Female", provider="edge-tts"),
        TtsVoice(id="vi-VN-NamMinhNeural", name="Nam Minh", locale="vi-VN", gender="Male", provider="edge-tts"),
    ]
    
    view = MockView()
    presenter = TtsPresenter(view, service=mock_service)
    presenter.init_presenter()
    
    assert view.provider == "edge-tts"
    assert view.language == "vi"
    assert view.voice_id == "vi-VN-HoaiMyNeural"
    assert view.rate == 10
    assert view.volume == -5
    assert view.keep_segments is False
    assert view.max_workers == 4
    assert view.refreshed is True

def test_presenter_start_tts():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    from infrastructure.providers.tts.models import TtsResult, GeneratedSegment
    expected_result = TtsResult(
        ok=True,
        output_file="out.mp3",
        segment_dir="segments",
        segments=[GeneratedSegment(
            index=1,
            start_time="00:00:01",
            end_time="00:00:03",
            target_duration_sec=2.0,
            raw_duration_sec=2.1,
            final_duration_sec=2.0,
            file_path="out1.mp3",
            status="success"
        )],
        elapsed_sec=1.5,
        error_message=None
    )
    mock_service.run_job.return_value = expected_result
    
    view = MockView()
    view.input_srt = "test.srt"
    view.voice_id = "vi-VN-HoaiMyNeural"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    
    assert view.busy is False
    assert view.stage_text == "Hoàn tất"
    assert len(view.segments) == 1
    assert view.output_file == "out.mp3"
    assert view.open_folder_visible is True
    assert view.notified_msg == "Lồng tiếng hoàn tất."

def test_presenter_start_tts_error():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    mock_service.run_job.side_effect = Exception("TTS failed API limit")
    
    view = MockView()
    view.input_srt = "test.srt"
    view.voice_id = "vi-VN-HoaiMyNeural"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    
    assert view.busy is False
    assert view.status_text == "TTS failed API limit"
    assert len(view.segments) == 0

def test_presenter_merge_audio():
    mock_service = MagicMock()
    mock_service.merge_segments.return_value = "final_output.mp3"
    
    view = MockView()
    view.input_srt = "test.srt"
    from infrastructure.providers.tts.models import GeneratedSegment
    view.segments = [GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=2.1,
        final_duration_sec=2.0,
        file_path="out1.mp3",
        status="success"
    )]
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.merge_audio()
    
    assert view.busy is False
    assert view.stage_text == "Gộp hoàn tất"
    assert view.output_file == "final_output.mp3"
    assert view.open_folder_visible is True
    assert view.notified_msg == "Gộp file lồng tiếng hoàn tất."

def test_presenter_tts_callbacks():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    def fake_run_job(*args, **kwargs):
        callbacks = kwargs.get("callbacks")
        if callbacks:
            from infrastructure.providers.tts.models import TtsProgress, GeneratedSegment
            callbacks.on_progress(TtsProgress(stage="process", message="Đang xử lý...", percent=50.0))
            callbacks.on_segment_done([GeneratedSegment(
                index=1,
                start_time="00:00:01",
                end_time="00:00:03",
                target_duration_sec=2.0,
                raw_duration_sec=2.1,
                final_duration_sec=2.0,
                file_path="out1.mp3",
                status="success"
            )])
        from infrastructure.providers.tts.models import TtsResult
        return TtsResult(ok=True, output_file="out.mp3", segment_dir="segments", segments=[], elapsed_sec=1.0, error_message=None)
        
    mock_service.run_job.side_effect = fake_run_job
    
    view = MockView()
    view.input_srt = "test.srt"
    view.voice_id = "vi-VN-HoaiMyNeural"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    
    assert view.stage_text == "Hoàn tất"

def test_presenter_start_tts_validation():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    view = MockView()
    view.input_srt = ""
    view.voice_id = "voice"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    assert "Vui lòng chọn file .srt đã dịch." in view.status_text
    
    view.input_srt = "test.srt"
    view.voice_id = ""
    presenter.start_tts()
    assert "Vui lòng chọn giọng đọc." in view.status_text
    
    view.voice_id = "voice"
    view.provider = "gemini-tts"
    view.api_key = ""
    presenter.start_tts()
    assert "Vui lòng nhập Gemini API key." in view.status_text

def test_presenter_merge_audio_validation():
    mock_service = MagicMock()
    
    view = MockView()
    view.input_srt = ""
    presenter = TtsPresenter(view, service=mock_service)
    presenter.merge_audio()
    assert "Vui lòng chọn file .srt đã dịch." in view.status_text
    
    view.input_srt = "test.srt"
    view.segments = []
    presenter.merge_audio()
    assert "Không có phân đoạn nào để gộp." in view.status_text

def test_presenter_start_tts_text_mode():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    from infrastructure.providers.tts.models import TtsResult, GeneratedSegment
    expected_result = TtsResult(
        ok=True,
        output_file="out.mp3",
        segment_dir="segments",
        segments=[GeneratedSegment(
            index=1,
            start_time="00:00:00",
            end_time="00:00:03",
            target_duration_sec=3.0,
            raw_duration_sec=3.0,
            final_duration_sec=3.0,
            file_path="out1.mp3",
            status="success"
        )],
        elapsed_sec=1.5,
        error_message=None
    )
    mock_service.run_job.return_value = expected_result
    
    view = MockView()
    view.input_mode = "text"
    view.input_text = "Xin chào các bạn.\nHôm nay là thứ sáu."
    view.voice_id = "vi-VN-HoaiMyNeural"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    
    assert view.busy is False
    assert view.stage_text == "Hoàn tất"
    assert view.current_file_text == "Văn bản trực tiếp"
    assert len(view.segments) == 1
    assert view.output_file == "out.mp3"
    
    mock_service.run_job.assert_called_once()
    call_kwargs = mock_service.run_job.call_args[1]
    assert call_kwargs["input_srt"] == ""
    assert call_kwargs["input_text"] == "Xin chào các bạn.\nHôm nay là thứ sáu."
    assert call_kwargs["input_mode"] == "text"
    assert call_kwargs["voice_id"] == "vi-VN-HoaiMyNeural"
    assert call_kwargs["rate"] == 0
    assert call_kwargs["volume"] == 0
    assert call_kwargs["max_workers"] == 5

def test_presenter_start_tts_text_mode_validation():
    mock_service = MagicMock()
    mock_service.is_processing = False
    
    view = MockView()
    view.input_mode = "text"
    view.input_text = ""
    view.voice_id = "voice"
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.start_tts()
    assert "Vui lòng nhập văn bản cần lồng tiếng." in view.status_text

def test_presenter_merge_audio_text_mode():
    mock_service = MagicMock()
    
    view = MockView()
    view.input_mode = "text"
    presenter = TtsPresenter(view, service=mock_service)
    presenter.merge_audio()
    assert "Chế độ nhập văn bản tự động gộp, không cần gộp thủ công." in view.status_text


@patch("app.presenter.tts_presenter.TtsPresenter.get_segment_dir")
@patch("infrastructure.providers.tts.timing.adjust_speed")
def test_presenter_preview_adjusted_speed(mock_adjust_speed, mock_get_segment_dir, tmp_path):
    mock_get_segment_dir.return_value = tmp_path
    
    mock_service = MagicMock()
    view = MockView()
    from infrastructure.providers.tts.models import GeneratedSegment
    seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=2.0,
        final_duration_sec=2.0,
        file_path=str(tmp_path / "0001_raw.mp3"),
        status="done"
    )
    view.segments = [seg]
    
    # Pre-create raw file
    raw_file = tmp_path / "0001_raw.mp3"
    raw_file.write_text("dummy audio content")
    
    presenter = TtsPresenter(view, service=mock_service)
    preview_path = presenter.preview_adjusted_speed(segment_index=1, speed=1.5)
    
    assert preview_path is not None
    assert "0001_preview.mp3" in preview_path
    mock_adjust_speed.assert_called_once()


@patch("app.presenter.tts_presenter.TtsPresenter.get_segment_dir")
@patch("infrastructure.providers.tts.timing.adjust_speed")
@patch("infrastructure.providers.tts.timing.get_duration")
def test_presenter_apply_adjusted_speed(mock_get_duration, mock_adjust_speed, mock_get_segment_dir, tmp_path):
    mock_get_segment_dir.return_value = tmp_path
    mock_get_duration.return_value = 1.33
    
    mock_service = MagicMock()
    view = MockView()
    from infrastructure.providers.tts.models import GeneratedSegment
    seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=2.0,
        final_duration_sec=2.0,
        file_path=str(tmp_path / "0001_raw.mp3"),
        status="done"
    )
    view.segments = [seg]
    
    # Pre-create raw file
    raw_file = tmp_path / "0001_raw.mp3"
    raw_file.write_text("dummy audio content")
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.apply_adjusted_speed(segment_index=1, speed=1.5)
    
    assert seg.final_duration_sec == 1.33
    assert "0001_timed.mp3" in seg.file_path
    assert "Đã áp dụng tốc độ 1.50x" in view.notified_msg


@patch("app.presenter.tts_presenter.TtsPresenter.get_segment_dir")
def test_presenter_cancel_adjusted_speed(mock_get_segment_dir, tmp_path):
    mock_get_segment_dir.return_value = tmp_path
    
    mock_service = MagicMock()
    view = MockView()
    from infrastructure.providers.tts.models import GeneratedSegment
    seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=2.0,
        final_duration_sec=1.5,
        file_path=str(tmp_path / "0001_timed.mp3"),
        status="done"
    )
    view.segments = [seg]
    
    # Pre-create raw file
    raw_file = tmp_path / "0001_raw.mp3"
    raw_file.write_text("dummy audio content")
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.cancel_adjusted_speed(segment_index=1)
    
    assert seg.final_duration_sec == 2.0
    assert "0001_raw.mp3" in seg.file_path


@patch("app.presenter.tts_presenter.TtsPresenter.get_segment_dir")
def test_presenter_regenerate_segment(mock_get_segment_dir, tmp_path):
    mock_get_segment_dir.return_value = tmp_path
    
    mock_service = MagicMock()
    from infrastructure.providers.tts.models import GeneratedSegment
    new_seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=1.8,
        final_duration_sec=1.8,
        file_path=str(tmp_path / "0001_raw.mp3"),
        status="done"
    )
    mock_service.synthesize_single_segment.return_value = new_seg
    
    view = MockView()
    view.input_mode = "text"
    view.input_text = "Dòng một"
    view.provider = "mock-provider"
    view.voice_id = "mock-voice"
    view.rate = 10
    view.volume = 5
    view.pitch = 0
    view.api_key = "abc"
    
    seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=None,
        final_duration_sec=None,
        file_path=None,
        status="error"
    )
    view.segments = [seg]
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.regenerate_segment(segment_index=1)
    
    # Assert background thread worker did its job
    assert view.segments[0].status == "done"
    assert view.segments[0].raw_duration_sec == 1.8
    assert "Đã tạo lại phân đoạn 1 thành công." in view.notified_msg
    mock_service.synthesize_single_segment.assert_called_once_with(
        index=1,
        text="Dòng một",
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        segment_dir=tmp_path,
        provider="mock-provider",
        voice_id="mock-voice",
        rate=10,
        volume=5,
        pitch=0,
        api_key="abc"
    )


@patch("app.presenter.tts_presenter.TtsPresenter.get_segment_dir")
def test_presenter_regenerate_segment_error(mock_get_segment_dir, tmp_path):
    mock_get_segment_dir.return_value = tmp_path
    
    mock_service = MagicMock()
    mock_service.synthesize_single_segment.side_effect = Exception("CapCut API Error")
    
    view = MockView()
    view.input_mode = "text"
    view.input_text = "Dòng một"
    view.provider = "mock-provider"
    
    from infrastructure.providers.tts.models import GeneratedSegment
    seg = GeneratedSegment(
        index=1,
        start_time="00:00:01",
        end_time="00:00:03",
        target_duration_sec=2.0,
        raw_duration_sec=None,
        final_duration_sec=None,
        file_path=None,
        status="done"
    )
    view.segments = [seg]
    
    presenter = TtsPresenter(view, service=mock_service)
    presenter.regenerate_segment(segment_index=1)
    
    # Assert background thread worker did its job and caught exception
    assert view.segments[0].status == "error"
    assert view.stage_text == "Lỗi tạo lại phân đoạn 1"
    assert view.notified_msg == "Lỗi tạo lại phân đoạn 1"

