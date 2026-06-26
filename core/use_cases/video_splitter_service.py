from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Optional

from utils.video_splitter import VideoSplitProgress, VideoSplitResult, split_video_audio


@dataclass
class VideoSplitterCallbacks:
    on_progress: Optional[Callable[[VideoSplitProgress], None]] = None
    on_success: Optional[Callable[[VideoSplitResult], None]] = None
    on_error: Optional[Callable[[VideoSplitResult], None]] = None


class VideoSplitterService:
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
        video_path: str,
        output_dir: str,
        callbacks: Optional[VideoSplitterCallbacks] = None,
    ) -> VideoSplitResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có một tác vụ xử lý video chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or VideoSplitterCallbacks()
        try:
            return split_video_audio(
                video_path=video_path,
                output_dir=output_dir,
                on_progress=callbacks.on_progress,
                on_success=callbacks.on_success,
                on_error=callbacks.on_error,
                stop_event=self._stop_event,
            )
        finally:
            with self._lock:
                self._active = False
