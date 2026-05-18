from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.video_merger import (
    DEFAULT_PROCESS_DIR,
    MergeProgress,
    MergeResult,
    default_output_name,
    merge_video_with_audio,
)


CONFIG_PATH = Path("config/merger_config.json")


@dataclass
class MergerCallbacks:
    on_progress: Optional[Callable[[MergeProgress], None]] = None
    on_success: Optional[Callable[[MergeResult], None]] = None
    on_error: Optional[Callable[[MergeResult], None]] = None


def default_config() -> dict:
    return {
        "main_video": "",
        "speech_audio": "",
        "background_audio": "",
        "intro_video": "",
        "outro_video": "",
        "output_dir": str(DEFAULT_PROCESS_DIR),
        "output_name": "",
        "speech_volume": 100,
        "background_volume": 125,
    }


class MergerService:
    def __init__(self, config_path: str | Path = CONFIG_PATH) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()
        self.config_path = Path(config_path)

    @property
    def is_processing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def load_config(self) -> dict:
        config = default_config()
        if not self.config_path.exists():
            return config
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return config
        if isinstance(loaded, dict):
            config.update({key: loaded.get(key, value) for key, value in config.items()})
        return config

    def save_config(self, config: dict) -> None:
        data = self.load_config()
        data.update({key: value for key, value in config.items() if key in data})
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_job(
        self,
        *,
        main_video: str,
        speech_audio: str,
        background_audio: str = "",
        intro_video: str = "",
        outro_video: str = "",
        output_dir: str,
        output_name: str = "",
        speech_volume: float = 1.0,
        background_volume: float = 1.25,
        callbacks: Optional[MergerCallbacks] = None,
    ) -> MergeResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có tác vụ gộp video chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or MergerCallbacks()
        try:
            self.save_config(
                {
                    "main_video": main_video,
                    "speech_audio": speech_audio,
                    "background_audio": background_audio,
                    "intro_video": intro_video,
                    "outro_video": outro_video,
                    "output_dir": output_dir,
                    "output_name": output_name or default_output_name(main_video),
                    "speech_volume": int(round(speech_volume * 100)),
                    "background_volume": int(round(background_volume * 100)),
                }
            )
            result = merge_video_with_audio(
                main_video=main_video,
                speech_audio=speech_audio,
                background_audio=background_audio or None,
                intro_video=intro_video or None,
                outro_video=outro_video or None,
                output_dir=output_dir,
                output_name=output_name or None,
                speech_volume=speech_volume,
                background_volume=background_volume,
                on_progress=callbacks.on_progress,
            )
            if result.ok:
                if callbacks.on_success:
                    callbacks.on_success(result)
            elif callbacks.on_error:
                callbacks.on_error(result)
            return result
        except Exception as exc:
            result = MergeResult(ok=False, output_file=None, elapsed_sec=0, error_message=str(exc))
            if callbacks.on_error:
                callbacks.on_error(result)
            return result
        finally:
            with self._lock:
                self._active = False
