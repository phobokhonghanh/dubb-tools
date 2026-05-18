from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.translator import (
    DEFAULT_TRANSLATE_MODEL,
    DEFAULT_TRANSLATE_OUTPUT_DIR,
    GeminiTranslator,
    SrtSegment,
    TranslateProgress,
    TranslateResult,
    build_output_path,
    chunk_segments,
    parse_srt,
)


CONFIG_PATH = Path("config/translator_config.json")


@dataclass
class TranslateCallbacks:
    on_progress: Optional[Callable[[TranslateProgress], None]] = None
    on_chunk_done: Optional[Callable[[list[SrtSegment]], None]] = None
    on_success: Optional[Callable[[TranslateResult], None]] = None
    on_error: Optional[Callable[[TranslateResult], None]] = None


def default_config() -> dict:
    return {
        "provider": "gemini",
        "model": DEFAULT_TRANSLATE_MODEL,
        "gemini_api_key": "",
        "api_keys": {},
        "target_language": "vi",
        "content_safety": False,
    }


class TranslateService:
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
            config.update({key: value for key, value in loaded.items() if key in config})
        return config

    def save_config(self, config: dict) -> None:
        data = default_config()
        existing = self.load_config()
        data.update(existing)
        data.update({key: value for key, value in config.items() if key in data})
        model = str(data.get("model") or DEFAULT_TRANSLATE_MODEL)
        api_key = str(config.get("gemini_api_key") or "")
        api_keys = data.get("api_keys")
        if not isinstance(api_keys, dict):
            api_keys = {}
        if api_key:
            api_keys[model] = api_key
        data["api_keys"] = api_keys
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_job(
        self,
        *,
        input_srt: str,
        output_dir: str,
        provider: str,
        model: str,
        api_key: str,
        target_language: str,
        content_safety: bool,
        callbacks: Optional[TranslateCallbacks] = None,
    ) -> TranslateResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có tác vụ dịch chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or TranslateCallbacks()
        started_at = time.monotonic()
        translated_segments: list[SrtSegment] = []
        output_path: Optional[Path] = None

        try:
            self.save_config(
                {
                    "provider": provider,
                    "model": model,
                    "gemini_api_key": api_key,
                    "target_language": target_language,
                    "content_safety": content_safety,
                }
            )
            self._emit(callbacks.on_progress, stage="parse", message="Đang đọc file SRT...", percent=0)
            source_segments = parse_srt(input_srt)
            chunks = chunk_segments(source_segments)
            output_path = build_output_path(input_srt, output_dir or DEFAULT_TRANSLATE_OUTPUT_DIR, target_language)

            if provider != "gemini":
                raise ValueError("Hiện tại chỉ hỗ trợ Gemini.")
            translator = GeminiTranslator(api_key=api_key, model=model)

            total_chunks = len(chunks)
            for chunk_index, chunk in enumerate(chunks, start=1):
                self._check_stop()
                self._emit(
                    callbacks.on_progress,
                    stage="translate",
                    message=f"Đang dịch cụm {chunk_index}/{total_chunks}...",
                    percent=((chunk_index - 1) / total_chunks) * 100,
                )
                translated_texts = translator.translate_segments(
                    segments=chunk,
                    all_segments=source_segments,
                    target_language=target_language,
                    content_safety=content_safety,
                    source_name=Path(input_srt).name,
                )
                translated_chunk = [
                    SrtSegment(
                        index=segment.index,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        text=text,
                    )
                    for segment, text in zip(chunk, translated_texts)
                ]
                translated_segments.extend(translated_chunk)
                if callbacks.on_chunk_done:
                    callbacks.on_chunk_done(list(translated_segments))
                self._emit(
                    callbacks.on_progress,
                    stage="translate",
                    message=f"Đã dịch {len(translated_segments)}/{len(source_segments)} dòng.",
                    percent=(chunk_index / total_chunks) * 100,
                )

            elapsed = time.monotonic() - started_at
            result = TranslateResult(
                ok=True,
                segments=translated_segments,
                output_file=str(output_path),
                elapsed_sec=elapsed,
                error_message=None,
            )
            self._emit(callbacks.on_progress, stage="done", message="Hoàn tất", percent=100)
            if callbacks.on_success:
                callbacks.on_success(result)
            return result
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            result = TranslateResult(
                ok=False,
                segments=translated_segments,
                output_file=str(output_path) if output_path else None,
                elapsed_sec=elapsed,
                error_message=str(exc),
            )
            if callbacks.on_error:
                callbacks.on_error(result)
            return result
        finally:
            with self._lock:
                self._active = False

    def _check_stop(self) -> None:
        if self._stop_event.is_set():
            raise RuntimeError("Đã dừng tác vụ dịch.")

    @staticmethod
    def _emit(
        callback: Optional[Callable[[TranslateProgress], None]],
        *,
        stage: str,
        message: str,
        percent: Optional[float] = None,
    ) -> None:
        if callback:
            callback(TranslateProgress(stage=stage, message=message, percent=percent))
