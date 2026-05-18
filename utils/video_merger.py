from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


DEFAULT_PROCESS_DIR = Path("resources/layer/process")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


@dataclass
class MediaInfo:
    path: str
    duration_sec: float
    width: Optional[int]
    height: Optional[int]
    fps: Optional[float]
    has_video: bool
    has_audio: bool


@dataclass
class MergeProgress:
    stage: str
    message: str
    percent: Optional[float] = None


@dataclass
class MergeResult:
    ok: bool
    output_file: Optional[str]
    elapsed_sec: float
    error_message: Optional[str]


@dataclass
class MergeInputSuggestion:
    main_video: Optional[str]
    speech_audio: Optional[str]
    background_audio: Optional[str]


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(f"Thiếu công cụ hệ thống: {', '.join(missing)}.")


def find_latest_merge_inputs(base_dir: str | Path = DEFAULT_PROCESS_DIR) -> MergeInputSuggestion:
    directory = Path(base_dir).expanduser()
    return MergeInputSuggestion(
        main_video=_latest_match(directory, "*_muted.mp4"),
        speech_audio=_latest_match(directory, "*_speech.mp3"),
        background_audio=_latest_match(directory, "*_background.wav"),
    )


def default_output_name(main_video: str | Path) -> str:
    stem = Path(main_video).stem
    return f"{stem}_final.mp4"


def probe_media(file_path: str | Path) -> MediaInfo:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file: {path}")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    data = json.loads(subprocess.check_output(cmd).decode("utf-8"))
    duration = float(data.get("format", {}).get("duration") or 0)
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    has_video = False
    has_audio = False

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and not has_video:
            has_video = True
            width = int(stream.get("width") or 0) or None
            height = int(stream.get("height") or 0) or None
            fps = _parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
        elif codec_type == "audio":
            has_audio = True

    return MediaInfo(
        path=str(path),
        duration_sec=duration,
        width=width,
        height=height,
        fps=fps,
        has_video=has_video,
        has_audio=has_audio,
    )


def merge_video_with_audio(
    *,
    main_video: str | Path,
    speech_audio: str | Path,
    output_dir: str | Path,
    output_name: Optional[str] = None,
    background_audio: str | Path | None = None,
    intro_video: str | Path | None = None,
    outro_video: str | Path | None = None,
    speech_volume: float = 1.0,
    background_volume: float = 1.25,
    on_progress: Optional[Callable[[MergeProgress], None]] = None,
) -> MergeResult:
    started_at = time.monotonic()
    output_path: Optional[Path] = None
    temp_dir: Optional[Path] = None

    try:
        require_ffmpeg()
        _emit(on_progress, stage="validate", message="Đang kiểm tra định dạng...", percent=5)
        main_path = _validate_video(main_video, required=True, label="video chính")
        speech_path = _validate_audio(speech_audio, required=True, label="âm thanh lồng tiếng")
        background_path = _validate_audio(background_audio, required=False, label="âm thanh nền")
        intro_path = _validate_video(intro_video, required=False, label="video mở đầu")
        outro_path = _validate_video(outro_video, required=False, label="video kết thúc")

        main_info = probe_media(main_path)
        if not main_info.width or not main_info.height:
            raise ValueError("Không đọc được resolution của main video.")
        fps = main_info.fps or 30
        intro_duration = probe_media(intro_path).duration_sec if intro_path else 0.0

        output_directory = Path(output_dir).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
        output_path = output_directory / (output_name or default_output_name(main_path))
        if output_path.suffix.lower() != ".mp4":
            output_path = output_path.with_suffix(".mp4")
        temp_dir = output_directory / f".merge_tmp_{output_path.stem}"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        _emit(on_progress, stage="timeline", message="Đang tính toán timeline...", percent=15)
        normalized_videos: list[Path] = []
        video_sources = [path for path in (intro_path, main_path, outro_path) if path]
        for index, source in enumerate(video_sources, start=1):
            _emit(
                on_progress,
                stage="normalize",
                message=f"Đang chuẩn hóa video {index}/{len(video_sources)}...",
                percent=15 + (index / max(len(video_sources), 1)) * 35,
            )
            normalized_videos.append(
                _normalize_video(
                    source,
                    temp_dir / f"segment_{index:02d}.mp4",
                    width=main_info.width,
                    height=main_info.height,
                    fps=fps,
                )
            )

        _emit(on_progress, stage="render", message="Đang render video final...", percent=60)
        video_track = _concat_videos(normalized_videos, temp_dir / "video_track.mp4")
        audio_track = _build_audio_mix(
            speech_audio=speech_path,
            background_audio=background_path,
            output_path=temp_dir / "audio_mix.m4a",
            intro_delay_sec=intro_duration,
            speech_volume=speech_volume,
            background_volume=background_volume,
        )
        _mux_video_audio(video_track, audio_track, output_path)

        elapsed = time.monotonic() - started_at
        shutil.rmtree(temp_dir, ignore_errors=True)
        _emit(on_progress, stage="done", message="Hoàn tất", percent=100)
        return MergeResult(ok=True, output_file=str(output_path), elapsed_sec=elapsed, error_message=None)
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        return MergeResult(
            ok=False,
            output_file=str(output_path) if output_path else None,
            elapsed_sec=elapsed,
            error_message=str(exc),
        )


def _latest_match(directory: Path, pattern: str) -> Optional[str]:
    if not directory.exists():
        return None
    candidates = [path for path in directory.glob(pattern) if path.is_file()]
    if not candidates:
        return None
    return str(max(candidates, key=lambda path: path.stat().st_mtime))


def _parse_fps(value: str | None) -> Optional[float]:
    if not value or value == "0/0":
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_float = float(denominator)
        if denominator_float == 0:
            return None
        return float(numerator) / denominator_float
    return float(value)


def _emit(
    callback: Optional[Callable[[MergeProgress], None]],
    *,
    stage: str,
    message: str,
    percent: Optional[float] = None,
) -> None:
    if callback:
        callback(MergeProgress(stage=stage, message=message, percent=percent))


def _validate_video(file_path: str | Path | None, *, required: bool, label: str) -> Optional[Path]:
    if not file_path:
        if required:
            raise ValueError(f"Vui lòng chọn {label}.")
        return None
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy {label}: {path}")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"{label} không phải định dạng video hỗ trợ.")
    info = probe_media(path)
    if not info.has_video:
        raise ValueError(f"{label} không có video stream.")
    return path


def _validate_audio(file_path: str | Path | None, *, required: bool, label: str) -> Optional[Path]:
    if not file_path:
        if required:
            raise ValueError(f"Vui lòng chọn {label}.")
        return None
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy {label}: {path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"{label} không phải định dạng audio hỗ trợ.")
    info = probe_media(path)
    if not info.has_audio:
        raise ValueError(f"{label} không có audio stream.")
    return path


def _normalize_video(source: Path, output_path: Path, *, width: int, height: int, fps: float) -> Path:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps:.3f},setsar=1,format=yuv420p"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output_path


def _concat_videos(inputs: list[Path], output_path: Path) -> Path:
    if not inputs:
        raise ValueError("Không có video segment để concat.")
    concat_file = output_path.parent / "video_concat.txt"
    concat_file.write_text(
        "\n".join(f"file '{path.resolve().as_posix()}'" for path in inputs),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        concat_file.unlink(missing_ok=True)
    return output_path


def _build_audio_mix(
    *,
    speech_audio: Path,
    background_audio: Optional[Path],
    output_path: Path,
    intro_delay_sec: float,
    speech_volume: float,
    background_volume: float,
) -> Path:
    delay_ms = int(max(intro_delay_sec, 0) * 1000)
    cmd = ["ffmpeg", "-y", "-i", str(speech_audio)]
    if background_audio:
        cmd.extend(["-i", str(background_audio)])
        filters = [
            f"[0:a]adelay={delay_ms}:all=1,volume={max(speech_volume, 0):.3f}[speech]",
            f"[1:a]adelay={delay_ms}:all=1,volume={max(background_volume, 0):.3f}[bg]",
            "[speech][bg]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
        ]
    else:
        filters = [
            f"[0:a]adelay={delay_ms}:all=1,volume={max(speech_volume, 0):.3f}[aout]",
        ]
    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


def _mux_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output_path
