from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.providers.tts.models import TtsVoice

class BaseTTSProvider(ABC):
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
