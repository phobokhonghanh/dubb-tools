import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.use_cases.tts_service import TtsService
from infrastructure.providers.tts.models import GeneratedSegment

@patch("core.use_cases.tts_service.require_ffmpeg")
@patch("core.use_cases.tts_service.TTSProviderFactory")
@patch("core.use_cases.tts_service.get_duration")
@patch("infrastructure.providers.tts.composer.create_silence")
@patch("infrastructure.providers.tts.composer.concat_audio")
def test_tts_service_run_job_text_mode(
    mock_concat, mock_silence, mock_get_duration, mock_factory, mock_require_ffmpeg, tmp_path
):
    # Setup paths
    config_file = tmp_path / "tts_config.json"
    output_dir = tmp_path / "output"
    
    # Mock behavior
    mock_get_duration.return_value = 2.0
    
    mock_provider = MagicMock()
    mock_provider.synthesize_segment.side_effect = lambda text, voice_id, output_path, **kwargs: Path(output_path)
    mock_factory.get_provider.return_value = mock_provider
    
    service = TtsService(config_path=config_file)
    
    # Run job in text mode
    result = service.run_job(
        input_srt="",
        input_text="Dòng một.\nDòng hai.",
        input_mode="text",
        output_dir=str(output_dir),
        provider="mock-provider",
        language="vi",
        voice_id="mock-voice",
        rate=0,
        volume=0,
        pitch=0,
        keep_segments=False,
        auto_merge=True
    )
    
    assert result.ok is True
    assert len(result.segments) == 2
    
    # Check that synthesis was called for each line
    assert mock_provider.synthesize_segment.call_count == 2
    
    # Check that silence was created
    mock_silence.assert_called_once()
    
    # Check that concat was called
    mock_concat.assert_called_once()


@patch("core.use_cases.tts_service.require_ffmpeg")
@patch("core.use_cases.tts_service.TTSProviderFactory")
@patch("core.use_cases.tts_service.get_duration")
def test_tts_service_run_job_with_segment_error(
    mock_get_duration, mock_factory, mock_require_ffmpeg, tmp_path
):
    config_file = tmp_path / "tts_config.json"
    output_dir = tmp_path / "output"
    
    mock_get_duration.return_value = 2.0
    
    mock_provider = MagicMock()
    # First segment succeeds, second raises Exception
    mock_provider.synthesize_segment.side_effect = [
        Path("dummy1.mp3"),
        Exception("API quota exceeded")
    ]
    mock_factory.get_provider.return_value = mock_provider
    
    service = TtsService(config_path=config_file)
    
    result = service.run_job(
        input_srt="",
        input_text="Câu một.\nCâu hai.",
        input_mode="text",
        output_dir=str(output_dir),
        provider="mock-provider",
        language="vi",
        voice_id="mock-voice",
        rate=0,
        volume=0,
        pitch=0,
        keep_segments=False,
        auto_merge=True
    )
    
    # The run_job should still complete (ok=True)
    assert result.ok is True
    assert len(result.segments) == 2
    # Segment 1 should be done, Segment 2 should be error
    assert result.segments[0].status == "done"
    assert result.segments[1].status == "error"
    # Result output_file should be None since auto-merge was skipped due to errors
    assert result.output_file is None


@patch("core.use_cases.tts_service.require_ffmpeg")
@patch("core.use_cases.tts_service.TTSProviderFactory")
@patch("core.use_cases.tts_service.get_duration")
def test_tts_service_synthesize_single_segment(
    mock_get_duration, mock_factory, mock_require_ffmpeg, tmp_path
):
    mock_get_duration.return_value = 1.5
    
    mock_provider = MagicMock()
    mock_provider.synthesize_segment.side_effect = lambda text, voice_id, output_path, **kwargs: Path(output_path)
    mock_factory.get_provider.return_value = mock_provider
    
    service = TtsService(config_path=tmp_path / "config.json")
    
    segment = service.synthesize_single_segment(
        index=3,
        text="Thử nghiệm đơn lẻ.",
        start_time="00:01:00,000",
        end_time="00:01:02,000",
        target_duration_sec=2.0,
        segment_dir=tmp_path / "segments",
        provider="mock-provider",
        voice_id="mock-voice",
        rate=0,
        volume=0,
        pitch=0
    )
    
    assert segment.index == 3
    assert segment.status == "done"
    assert segment.raw_duration_sec == 1.5
    assert segment.final_duration_sec == 1.5
    assert "0003_raw.mp3" in segment.file_path
