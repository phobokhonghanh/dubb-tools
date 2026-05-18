from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_TTS_OUTPUT_DIR = Path("resources/layer/process")
DEFAULT_TTS_PROVIDER = "edge-tts"
GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
LANGUAGE_OPTIONS = {
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "中文",
    "ja": "日本語",
    "ko": "한국어",
    "th": "ไทย",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
}
GEMINI_VOICES = [
    "Orus",
    "Zephyr",
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Leda",
    "Aoede",
]


@dataclass
class TtsSegment:
    index: int
    start_time: str
    end_time: str
    text: str
    start_sec: float
    end_sec: float
    target_duration_sec: float


@dataclass
class TtsVoice:
    id: str
    name: str
    locale: str
    gender: str
    provider: str


@dataclass
class GeneratedSegment:
    index: int
    start_time: str
    end_time: str
    target_duration_sec: float
    raw_duration_sec: Optional[float]
    final_duration_sec: Optional[float]
    file_path: Optional[str]
    status: str


@dataclass
class TtsProgress:
    stage: str
    message: str
    percent: Optional[float] = None


@dataclass
class TtsResult:
    ok: bool
    output_file: Optional[str]
    segment_dir: Optional[str]
    segments: list[GeneratedSegment]
    elapsed_sec: float
    error_message: Optional[str]
