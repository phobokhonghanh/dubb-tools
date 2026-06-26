import pytest
from unittest.mock import MagicMock, patch
from app.presenter.tts_presenter import TtsPresenter

class MockView:
    def __init__(self):
        self.input_srt = ""
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
