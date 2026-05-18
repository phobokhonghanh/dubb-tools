from __future__ import annotations

import re
from pathlib import Path

from utils.translator.models import SrtSegment


TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def parse_srt(file_path: str | Path) -> list[SrtSegment]:
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy file SRT: {path}")
    if path.suffix.lower() != ".srt":
        raise ValueError("Vui lòng chọn file .srt.")

    text = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    segments: list[SrtSegment] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            index = len(segments) + 1

        match = TIMESTAMP_RE.search(lines[1])
        if not match:
            continue

        segments.append(
            SrtSegment(
                index=index,
                start_time=match.group("start"),
                end_time=match.group("end"),
                text=" ".join(lines[2:]).strip(),
            )
        )

    if not segments:
        raise ValueError(f"File SRT không có subtitle hợp lệ: {path}")
    return segments


def serialize_srt(segments: list[SrtSegment]) -> str:
    blocks: list[str] = []
    for fallback_index, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(segment.index or fallback_index),
                    f"{segment.start_time} --> {segment.end_time}",
                    segment.text.strip(),
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def _timestamp_to_seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def total_duration_sec(segments: list[SrtSegment]) -> float:
    if not segments:
        return 0
    return _timestamp_to_seconds(segments[-1].end_time)


def chunk_segments(segments: list[SrtSegment]) -> list[list[SrtSegment]]:
    if len(segments) < 20:
        return [segments]
    return [segments[index : index + 10] for index in range(0, len(segments), 10)]


def build_output_path(input_srt: str | Path, output_dir: str | Path, target_language: str) -> Path:
    source = Path(input_srt)
    directory = Path(output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    lang = (target_language or "vi").strip().lower()
    return directory / f"{source.stem}_{lang}.srt"


def replace_all(segments: list[SrtSegment], find_text: str, replace_text: str) -> list[SrtSegment]:
    if not find_text:
        return list(segments)
    return [
        SrtSegment(
            index=segment.index,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text.replace(find_text, replace_text),
        )
        for segment in segments
    ]
