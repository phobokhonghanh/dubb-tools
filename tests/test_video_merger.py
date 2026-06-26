import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from threading import Event
from utils.video_merger import merge_video_with_audio, MergeResult

@patch("utils.video_merger.probe_media")
@patch("utils.video_merger.run_process")
@patch("shutil.which")
def test_merge_video_with_audio_success(mock_which, mock_run, mock_probe, tmp_path):
    # Giả lập công cụ ffmpeg/ffprobe có sẵn
    mock_which.return_value = "/usr/bin/ffmpeg"
    
    # Giả lập MediaInfo trả về từ probe_media
    from utils.video_merger import MediaInfo
    mock_probe.side_effect = [
        MediaInfo(path="video.mp4", duration_sec=10.0, width=1920, height=1080, fps=30.0, has_video=True, has_audio=False), # _validate_video
        MediaInfo(path="audio.mp3", duration_sec=10.0, width=None, height=None, fps=None, has_video=False, has_audio=True), # _validate_audio
        MediaInfo(path="video.mp4", duration_sec=10.0, width=1920, height=1080, fps=30.0, has_video=True, has_audio=False), # main_info = probe_media
    ]
    
    # Mock CompletedProcess
    mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
    
    main_video = tmp_path / "main.mp4"
    main_video.write_bytes(b"dummy video data")
    speech_audio = tmp_path / "speech.mp3"
    speech_audio.write_bytes(b"dummy audio data")
    
    res = merge_video_with_audio(
        main_video=main_video,
        speech_audio=speech_audio,
        output_dir=tmp_path,
        output_name="output.mp4"
    )
    
    assert res.ok is True
    assert "output.mp4" in res.output_file

@patch("utils.video_merger.probe_media")
@patch("utils.video_merger.run_process")
@patch("shutil.which")
def test_merge_video_with_audio_cancel(mock_which, mock_run, mock_probe, tmp_path):
    # Giả lập công cụ ffmpeg/ffprobe có sẵn
    mock_which.return_value = "/usr/bin/ffmpeg"
    
    stop_event = Event()
    stop_event.set() # Kích hoạt dừng ngay lập tức
    
    main_video = tmp_path / "main.mp4"
    main_video.write_bytes(b"dummy video data")
    speech_audio = tmp_path / "speech.mp3"
    speech_audio.write_bytes(b"dummy audio data")
    
    res = merge_video_with_audio(
        main_video=main_video,
        speech_audio=speech_audio,
        output_dir=tmp_path,
        output_name="output.mp4",
        stop_event=stop_event
    )
    
    assert res.ok is False
    assert "Đã dừng tác vụ ghép video" in res.error_message
