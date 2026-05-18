from __future__ import annotations

import re
import struct


DEFAULT_AUDIO_PROFILE = "A smooth, premium commercial voice."
DEFAULT_DIRECTOR_NOTE = (
    "Style: Open, conversational, natural reaction-style delivery, light breathiness, "
    "close-to-mic presence, expressive and emotionally reactive with subtle laughs and "
    "natural emphasis, natural dynamic pace, Southern Vietnamese accent."
)
DEFAULT_SCENE = (
    "A premium Vietnamese commercial voiceover delivered like a natural, emotionally "
    "responsive reaction to the product or story. The speaker should sound close, warm, "
    "confident, and genuinely engaged rather than overly scripted."
)
DEFAULT_SAMPLE_CONTEXT = (
    "Use a close-to-mic conversational delivery with natural pacing, subtle breath, soft "
    "emotional emphasis, and light expressive reactions where the transcript suggests it."
)


def normalize_prompt_part(value: str | None, default: str) -> str:
    if value is None:
        return default

    value = value.strip()
    return value or default


def build_content_text(
    *,
    transcript: str,
    audio_profile: str | None = None,
    director_note: str | None = None,
    scene: str | None = None,
    sample_context: str | None = None,
) -> str:
    transcript = transcript.strip()
    if not transcript:
        raise ValueError("transcript is required and cannot be blank.")

    audio_profile = normalize_prompt_part(audio_profile, DEFAULT_AUDIO_PROFILE)
    director_note = normalize_prompt_part(director_note, DEFAULT_DIRECTOR_NOTE)
    scene = normalize_prompt_part(scene, DEFAULT_SCENE)
    sample_context = normalize_prompt_part(sample_context, DEFAULT_SAMPLE_CONTEXT)

    return (
        "Read the following transcript based on the audio profile and director's note.\n\n"
        f"# Audio Profile\n{audio_profile}\n\n"
        f"# Director's note\n{director_note}\n\n"
        f"## Scene:\n{scene}\n\n"
        f"## Sample Context:\n{sample_context}\n\n"
        f"## Transcript:\n{transcript}"
    )


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict[str, int]:
    bits_per_sample = 16
    rate = 24000

    for param in re.split(r";\s*", mime_type):
        if param.lower().startswith("rate="):
            try:
                rate = int(param.split("=", 1)[1])
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass

    return {"bits_per_sample": bits_per_sample, "rate": rate}
