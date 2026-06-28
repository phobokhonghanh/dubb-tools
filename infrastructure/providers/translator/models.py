from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional



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
