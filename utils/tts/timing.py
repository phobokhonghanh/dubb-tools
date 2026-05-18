from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from utils.translator.srt import parse_srt
from utils.tts.models import TtsSegment


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise RuntimeError(f"Thiếu công cụ hệ thống: {', '.join(missing)}.")


def timestamp_to_seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_tts_segments(input_srt: str | Path) -> list[TtsSegment]:
    segments = []
    for segment in parse_srt(input_srt):
        start_sec = timestamp_to_seconds(segment.start_time)
        end_sec = timestamp_to_seconds(segment.end_time)
        segments.append(
            TtsSegment(
                index=segment.index,
                start_time=segment.start_time,
                end_time=segment.end_time,
                text=segment.text,
                start_sec=start_sec,
                end_sec=end_sec,
                target_duration_sec=max(end_sec - start_sec, 0.01),
            )
        )
    return segments


def get_duration(file_path: str | Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.check_output(cmd)
    return float(result.decode().strip())


def build_atempo_filter(speed: float) -> str:
    if speed <= 0:
        raise ValueError("speed must be greater than 0")
    if 0.5 <= speed <= 2.0:
        return f"atempo={speed:.6g}"

    parts: list[str] = []
    temp_speed = speed
    while temp_speed > 2.0:
        parts.append("atempo=2.0")
        temp_speed /= 2.0
    while temp_speed < 0.5:
        parts.append("atempo=0.5")
        temp_speed /= 0.5
    parts.append(f"atempo={temp_speed:.6g}")
    return ",".join(parts)


def adjust_speed(input_path: str | Path, output_path: str | Path, target_duration: float) -> Path:
    current_duration = get_duration(input_path)
    if target_duration <= 0:
        raise ValueError("target_duration must be greater than 0")
    speed = current_duration / target_duration
    filter_str = build_atempo_filter(speed)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            filter_str,
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output


def apply_volume(input_path: str | Path, output_path: str | Path, volume_percent: int) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    volume = max((100 + volume_percent) / 100, 0)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-filter:a",
            f"volume={volume:.3f}",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output
