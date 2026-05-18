from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Callable, Optional

from utils.download import DownloadProgress, DownloadResult, download


@dataclass
class DownloadJobCallbacks:
    on_progress: Optional[Callable[[DownloadProgress], None]] = None
    on_success: Optional[Callable[[DownloadResult], None]] = None
    on_error: Optional[Callable[[DownloadResult], None]] = None


class DownloadService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()

    @property
    def is_downloading(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def run_job(
        self,
        *,
        url: str,
        output_name: Optional[str] = None,
        use_proxy: bool = True,
        callbacks: Optional[DownloadJobCallbacks] = None,
    ) -> DownloadResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có một tác vụ tải chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or DownloadJobCallbacks()
        try:
            return download(
                url=url,
                output_filename=output_name,
                use_proxy=use_proxy,
                on_progress=callbacks.on_progress,
                on_success=callbacks.on_success,
                on_error=callbacks.on_error,
                stop_event=self._stop_event,
            )
        finally:
            with self._lock:
                self._active = False
