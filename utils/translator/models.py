from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_TRANSLATE_OUTPUT_DIR = Path("resources/layer/process")
DEFAULT_TRANSLATE_MODEL = "gemini-2.5-flash"
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


@dataclass
class SrtSegment:
    index: int
    start_time: str
    end_time: str
    text: str


@dataclass
class TranslateProgress:
    stage: str
    message: str
    percent: Optional[float] = None


@dataclass
class TranslateResult:
    ok: bool
    segments: list[SrtSegment]
    output_file: Optional[str]
    elapsed_sec: float
    error_message: Optional[str]
