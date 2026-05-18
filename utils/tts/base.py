from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from utils.tts.models import TtsVoice


class BaseTTS(ABC):
    provider_id: str

    @abstractmethod
    def list_voices(self, language: str | None = None) -> list[TtsVoice]:
        raise NotImplementedError

    @abstractmethod
    def synthesize_segment(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: int,
        volume: int,
        pitch: int,
    ) -> Path:
        raise NotImplementedError
