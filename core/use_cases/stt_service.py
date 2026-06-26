from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Optional

from utils.stt_processor import SttProgress, SttResult, transcribe_audio


@dataclass
class SttCallbacks:
    on_progress: Optional[Callable[[SttProgress], None]] = None
    on_success: Optional[Callable[[SttResult], None]] = None
    on_error: Optional[Callable[[SttResult], None]] = None


class SttService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()

    @property
    def is_processing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def run_job(
        self,
        *,
        audio_path: str,
        output_dir: str,
        model_size: str,
        language: Optional[str],
        callbacks: Optional[SttCallbacks] = None,
    ) -> SttResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có tác vụ nhận diện chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or SttCallbacks()
        try:
            result = transcribe_audio(
                audio_path=audio_path,
                model_size=model_size,
                language=language,
                on_progress=callbacks.on_progress,
                on_success=callbacks.on_success,
                on_error=callbacks.on_error,
                stop_event=self._stop_event,
            )
            return result
        finally:
            with self._lock:
                self._active = False
