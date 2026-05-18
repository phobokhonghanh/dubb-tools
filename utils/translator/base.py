from __future__ import annotations

from abc import ABC, abstractmethod

from utils.translator.models import SrtSegment


class BaseTranslator(ABC):
    @abstractmethod
    def translate_segments(
        self,
        *,
        segments: list[SrtSegment],
        all_segments: list[SrtSegment],
        target_language: str,
        content_safety: bool,
        source_name: str,
    ) -> list[str]:
        raise NotImplementedError
