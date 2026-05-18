from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Optional

import numpy as np
import sherpa_onnx
import soundfile as sf
from moviepy import VideoFileClip

from utils.vendor_bootstrap import check_pyvideotrans_vendor, format_vendor_error


DEFAULT_OUTPUT_DIR = Path("resources/layer/process")
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
V2_MODELS_DIR = Path("vendor/pyvideotrans/models/onnx")
VOCALS_MODEL = "vocals.fp16.onnx"
BACKGROUND_MODEL = "accompaniment.fp16.onnx"


@dataclass
class VideoSplitProgress:
    stage: str
    message: str
    percent: Optional[float] = None


@dataclass
class VideoSplitResult:
    ok: bool
    muted_video: Optional[str]
    vocals_audio: Optional[str]
    background_audio: Optional[str]
    elapsed_sec: float
    error_message: Optional[str]


def sanitize_video_stem(path: str | Path) -> str:
    stem = Path(path).stem.strip()
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in stem) or "video"


def ensure_output_dir(output_dir: str | Path) -> Path:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def validate_video_path(video_path: str | Path) -> Path:
    source_path = Path(video_path).expanduser()
    if not source_path.exists() or not source_path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file video: {source_path}")
    if source_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(f"Định dạng video không hỗ trợ: {source_path.suffix}")
    return source_path


def get_model_paths(models_dir: str | Path = V2_MODELS_DIR) -> tuple[Path, Path]:
    if Path(models_dir) == V2_MODELS_DIR:
        status = check_pyvideotrans_vendor()
        if not status.ready:
            raise FileNotFoundError(format_vendor_error(status))

    base = Path(models_dir).expanduser()
    vocals = base / VOCALS_MODEL
    background = base / BACKGROUND_MODEL
    if not vocals.exists() or not background.exists():
        raise FileNotFoundError(
            "Thiếu model tách nguồn âm thanh. Cần có "
            f"{vocals} và {background}. "
            "App sẽ tự chuẩn bị vendor khi khởi động; hãy kiểm tra kết nối mạng nếu lỗi vẫn xảy ra."
        )
    return vocals, background


def _emit(
    callback: Optional[Callable[[VideoSplitProgress], None]],
    *,
    stage: str,
    message: str,
    percent: Optional[float] = None,
) -> None:
    if callback:
        callback(VideoSplitProgress(stage=stage, message=message, percent=percent))


def _check_stop(stop_event: Optional[Event]) -> None:
    if stop_event and stop_event.is_set():
        raise RuntimeError("Đã dừng tác vụ tách video.")


def _extract_audio(video_path: Path, output_audio: Path) -> None:
    clip = VideoFileClip(str(video_path))
    try:
        if clip.audio is None:
            raise ValueError("Video không có audio track để xử lý.")
        clip.audio.write_audiofile(str(output_audio), codec="pcm_s16le", logger=None)
    finally:
        clip.close()


def _save_muted_video(video_path: Path, muted_output: Path) -> None:
    clip = VideoFileClip(str(video_path))
    try:
        muted = clip.without_audio()
        try:
            muted.write_videofile(str(muted_output), codec="libx264", audio=False, logger=None)
        finally:
            muted.close()
    finally:
        clip.close()


def _separate_audio(
    input_audio: Path,
    vocals_output: Path,
    background_output: Path,
    *,
    models_dir: str | Path = V2_MODELS_DIR,
) -> None:
    vocals_model, background_model = get_model_paths(models_dir)
    config = sherpa_onnx.OfflineSourceSeparationConfig(
        model=sherpa_onnx.OfflineSourceSeparationModelConfig(
            spleeter=sherpa_onnx.OfflineSourceSeparationSpleeterModelConfig(
                vocals=str(vocals_model),
                accompaniment=str(background_model),
            ),
            num_threads=4,
            debug=False,
            provider="cpu",
        )
    )
    if not config.validate():
        raise ValueError("Cấu hình source separation không hợp lệ.")

    separator = sherpa_onnx.OfflineSourceSeparation(config)
    samples, sample_rate = sf.read(str(input_audio), dtype="float32", always_2d=True)
    samples = np.transpose(samples)
    samples = np.ascontiguousarray(samples)

    output = separator.process(sample_rate=sample_rate, samples=samples)
    if len(output.stems) < 2:
        raise RuntimeError("Không nhận đủ 2 stem từ source separation.")

    vocals = np.transpose(output.stems[0].data)
    background = np.transpose(output.stems[1].data)
    sf.write(str(vocals_output), vocals, samplerate=output.sample_rate)
    sf.write(str(background_output), background, samplerate=output.sample_rate)


def split_video_audio(
    video_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    on_progress: Optional[Callable[[VideoSplitProgress], None]] = None,
    on_success: Optional[Callable[[VideoSplitResult], None]] = None,
    on_error: Optional[Callable[[VideoSplitResult], None]] = None,
    stop_event: Optional[Event] = None,
    models_dir: str | Path = V2_MODELS_DIR,
) -> VideoSplitResult:
    started_at = time.monotonic()
    muted_video_path: Optional[Path] = None
    vocals_path: Optional[Path] = None
    background_path: Optional[Path] = None
    raw_audio_path: Optional[Path] = None

    try:
        source = validate_video_path(video_path)
        out_dir = ensure_output_dir(output_dir)
        stem = sanitize_video_stem(source)
        muted_video_path = out_dir / f"{stem}_muted.mp4"
        vocals_path = out_dir / f"{stem}_vocals.wav"
        background_path = out_dir / f"{stem}_background.wav"
        raw_audio_path = out_dir / f"{stem}_raw_audio.wav"

        _check_stop(stop_event)
        _emit(on_progress, stage="prepare_vendor", message="Đang kiểm tra vendor pyvideotrans...", percent=None)
        get_model_paths(models_dir)

        _check_stop(stop_event)
        _emit(on_progress, stage="extract_audio", message="Đang trích xuất audio...", percent=None)
        _extract_audio(source, raw_audio_path)

        _check_stop(stop_event)
        _emit(on_progress, stage="separate_audio", message="Đang tách giọng nói & nhạc nền...", percent=None)
        _separate_audio(raw_audio_path, vocals_path, background_path, models_dir=models_dir)

        _check_stop(stop_event)
        _emit(on_progress, stage="export_muted", message="Đang xuất video không âm thanh...", percent=None)
        _save_muted_video(source, muted_video_path)

        if raw_audio_path.exists():
            raw_audio_path.unlink(missing_ok=True)

        elapsed = time.monotonic() - started_at
        result = VideoSplitResult(
            ok=True,
            muted_video=str(muted_video_path),
            vocals_audio=str(vocals_path),
            background_audio=str(background_path),
            elapsed_sec=elapsed,
            error_message=None,
        )
        _emit(on_progress, stage="done", message="Hoàn thành", percent=100.0)
        if on_success:
            on_success(result)
        return result
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        result = VideoSplitResult(
            ok=False,
            muted_video=str(muted_video_path) if muted_video_path and muted_video_path.exists() else None,
            vocals_audio=str(vocals_path) if vocals_path and vocals_path.exists() else None,
            background_audio=str(background_path) if background_path and background_path.exists() else None,
            elapsed_sec=elapsed,
            error_message=str(exc),
        )
        if on_error:
            on_error(result)
        return result
