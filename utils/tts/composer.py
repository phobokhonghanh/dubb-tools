from __future__ import annotations

import subprocess
from pathlib import Path

from utils.tts.models import GeneratedSegment, TtsSegment
from utils.tts.timing import get_duration


def create_silence(output_path: str | Path, duration_sec: float) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{max(duration_sec, 0.01):.3f}",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output


def convert_to_mp3(input_path: str | Path, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-q:a",
            "3",
            "-acodec",
            "libmp3lame",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output


def concat_audio(inputs: list[Path], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output.parent / f"{output.stem}_concat.txt"
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
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        concat_file.unlink(missing_ok=True)
    return output


def compose_timeline(
    *,
    segments: list[TtsSegment],
    generated: list[GeneratedSegment],
    output_path: str | Path,
    work_dir: str | Path,
) -> Path:
    parts: list[Path] = []
    previous_end = 0.0
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    for segment, generated_segment in zip(segments, generated):
        gap = segment.start_sec - previous_end
        if gap > 0.01:
            parts.append(create_silence(work / f"gap_{segment.index:04d}.mp3", gap))
        if generated_segment.file_path:
            source = Path(generated_segment.file_path)
            mp3_path = source if source.suffix.lower() == ".mp3" else convert_to_mp3(
                source, work / f"segment_{segment.index:04d}.mp3"
            )
            parts.append(mp3_path)
            previous_end = segment.start_sec + get_duration(mp3_path)
        else:
            previous_end = segment.start_sec

        if previous_end < segment.end_sec:
            pad = segment.end_sec - previous_end
            parts.append(create_silence(work / f"pad_{segment.index:04d}.mp3", pad))
            previous_end = segment.end_sec

    if not parts:
        raise RuntimeError("Không có audio segment để gộp.")
    return concat_audio(parts, output_path)
