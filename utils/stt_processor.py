from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from faster_whisper import WhisperModel


DEFAULT_STT_OUTPUT_DIR = Path("resources/layer/process")
SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
SUPPORTED_LANGUAGES = {"auto", "vi", "en", "zh", "ja", "ko", "fr", "de", "es", "th"}


@dataclass
class TranscriptSegment:
    start_time: float
    end_time: float
    content: str


@dataclass
class SttProgress:
    stage: str
    message: str
    percent: Optional[float] = None


@dataclass
class SttResult:
    ok: bool
    segments: list[TranscriptSegment]
    output_file: Optional[str]
    language: Optional[str]
    language_probability: Optional[float]
    elapsed_sec: float
    error_message: Optional[str]


def normalize_language(language: Optional[str]) -> Optional[str]:
    value = (language or "").strip().lower()
    if not value or value == "auto":
        return None
    return value


def validate_audio_path(audio_path: str | Path) -> Path:
    source = Path(audio_path).expanduser()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy file âm thanh: {source}")
    if source.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError(f"Định dạng âm thanh không hỗ trợ: {source.suffix}")
    return source


def ensure_output_dir(output_dir: str | Path) -> Path:
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def sanitize_stem(path: str | Path) -> str:
    stem = Path(path).stem.strip()
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in stem) or "audio"


def find_latest_vocals(base_dir: str | Path = DEFAULT_STT_OUTPUT_DIR) -> Optional[Path]:
    directory = Path(base_dir).expanduser()
    if not directory.exists():
        return None
    candidates = [path for path in directory.glob("*_vocals.wav") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _emit(
    callback: Optional[Callable[[SttProgress], None]],
    *,
    stage: str,
    message: str,
    percent: Optional[float] = None,
) -> None:
    if callback:
        callback(SttProgress(stage=stage, message=message, percent=percent))


def _check_stop(stop_event: Optional[Event]) -> None:
    if stop_event and stop_event.is_set():
        raise RuntimeError("Đã dừng tác vụ nhận diện giọng nói.")


def _format_srt_timestamp(seconds: float) -> str:
    total_ms = max(int(round(seconds * 1000)), 0)
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    sec = total_seconds % 60
    total_minutes = total_seconds // 60
    minute = total_minutes % 60
    hour = total_minutes // 60
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def format_segment_time(start_time: float, end_time: float) -> str:
    def compact(seconds: float) -> str:
        total_seconds = max(int(seconds), 0)
        minutes, sec = divmod(total_seconds, 60)
        hour, minutes = divmod(minutes, 60)
        if hour:
            return f"{hour:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    return f"{compact(start_time)} - {compact(end_time)}"


def merge_segments(segments: list[TranscriptSegment], group_size: int) -> list[TranscriptSegment]:
    if group_size < 1:
        raise ValueError("Số dòng muốn gộp phải lớn hơn hoặc bằng 1.")
    merged: list[TranscriptSegment] = []
    for index in range(0, len(segments), group_size):
        group = segments[index : index + group_size]
        if not group:
            continue
        content = " ".join(segment.content.strip() for segment in group if segment.content.strip())
        merged.append(
            TranscriptSegment(
                start_time=group[0].start_time,
                end_time=group[-1].end_time,
                content=content,
            )
        )
    return merged


def _normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value.strip())
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])([^\s,.!?;:])", r"\1 \2", text)
    if text:
        text = text[0].upper() + text[1:]
    return text


def normalize_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            start_time=segment.start_time,
            end_time=segment.end_time,
            content=_normalize_text(segment.content),
        )
        for segment in segments
    ]


def save_transcript(
    segments: list[TranscriptSegment],
    output_dir: str | Path,
    source_name: str | Path,
    output_format: str = "srt",
) -> str:
    directory = ensure_output_dir(output_dir)
    file_format = output_format.strip().lower() or "srt"
    if file_format not in {"srt", "txt"}:
        raise ValueError(f"Định dạng xuất không hỗ trợ: {output_format}")

    output_path = directory / f"{sanitize_stem(source_name)}_transcript.{file_format}"
    if file_format == "srt":
        parts: list[str] = []
        for index, segment in enumerate(segments, start=1):
            parts.append(str(index))
            parts.append(
                f"{_format_srt_timestamp(segment.start_time)} --> "
                f"{_format_srt_timestamp(segment.end_time)}"
            )
            parts.append(segment.content)
            parts.append("")
        output_path.write_text("\n".join(parts), encoding="utf-8")
    else:
        lines = [
            f"[{format_segment_time(segment.start_time, segment.end_time)}] {segment.content}"
            for segment in segments
        ]
        output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)


def stt_result_to_legacy_dict(result: SttResult, audio_path: str | Path) -> dict:
    total_duration = max((segment.end_time for segment in result.segments), default=0)
    return {
        "info": {
            "name": Path(audio_path).stem,
            "language": result.language,
            "language_probability": round(result.language_probability or 0, 2),
        },
        "batch": [
            {
                "start": round(segment.start_time, 2),
                "end": round(segment.end_time, 2),
                "text": segment.content.strip(),
            }
            for segment in result.segments
        ],
        "full": {
            "text": " ".join(segment.content.strip() for segment in result.segments).strip(),
            "total_duration": round(total_duration, 2),
        },
    }


def transcribe_audio(
    audio_path: str | Path,
    model_size: str = "base",
    language: Optional[str] = None,
    *,
    on_progress: Optional[Callable[[SttProgress], None]] = None,
    on_success: Optional[Callable[[SttResult], None]] = None,
    on_error: Optional[Callable[[SttResult], None]] = None,
    stop_event: Optional[Event] = None,
) -> SttResult:
    started_at = time.monotonic()
    source: Optional[Path] = None
    segments_result: list[TranscriptSegment] = []
    detected_language: Optional[str] = None
    language_probability: Optional[float] = None

    try:
        source = validate_audio_path(audio_path)
        normalized_language = normalize_language(language)

        _check_stop(stop_event)
        _emit(on_progress, stage="loading_model", message=f"Đang tải model Whisper ({model_size})...", percent=None)
        model = WhisperModel(model_size, device="cpu", compute_type="int8")

        _check_stop(stop_event)
        _emit(on_progress, stage="transcribing", message="Đang nhận diện giọng nói...", percent=None)
        segments, info = model.transcribe(str(source), beam_size=5, language=normalized_language)
        detected_language = getattr(info, "language", None)
        language_probability = getattr(info, "language_probability", None)
        duration = float(getattr(info, "duration", 0) or 0)

        for segment in segments:
            _check_stop(stop_event)
            transcript = TranscriptSegment(
                start_time=round(float(segment.start), 2),
                end_time=round(float(segment.end), 2),
                content=segment.text.strip(),
            )
            segments_result.append(transcript)
            percent = None
            if duration > 0:
                percent = min(max((transcript.end_time / duration) * 100, 0), 99)
            _emit(
                on_progress,
                stage="transcribing",
                message=f"Đã nhận diện {len(segments_result)} dòng...",
                percent=percent,
            )

        _emit(on_progress, stage="finalizing", message="Đang xử lý kết quả...", percent=99)
        elapsed = time.monotonic() - started_at
        result = SttResult(
            ok=True,
            segments=segments_result,
            output_file=None,
            language=detected_language,
            language_probability=language_probability,
            elapsed_sec=elapsed,
            error_message=None,
        )
        _emit(on_progress, stage="done", message="Hoàn tất", percent=100)
        if on_success:
            on_success(result)
        return result
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        result = SttResult(
            ok=False,
            segments=segments_result,
            output_file=None,
            language=detected_language,
            language_probability=language_probability,
            elapsed_sec=elapsed,
            error_message=str(exc),
        )
        if on_error:
            on_error(result)
        return result
