from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.stt_processor import TranscriptSegment, cleanup_transcript_segments
from utils.loader import load_json_file
from constants import (
    DEFAULT_TRANSLATE_MODEL,
    DEFAULT_TRANSLATE_OUTPUT_DIR,
    TRANSLATE_MODELS,
    save_user_output_dir,
    TRANSLATOR_CONFIG_PATH,
)
from infrastructure.providers.translator import (
    GeminiTranslator,
    SrtSegment,
    TranslateProgress,
    TranslateResult,
    build_output_path,
    chunk_segments,
    parse_srt,
    serialize_srt,
)

@dataclass
class TranslateCallbacks:
    on_progress: Optional[Callable[[TranslateProgress], None]] = None
    on_chunk_done: Optional[Callable[[list[SrtSegment]], None]] = None
    on_success: Optional[Callable[[TranslateResult], None]] = None
    on_error: Optional[Callable[[TranslateResult], None]] = None

class TranslateService:
    def __init__(self, config_path: str | Path = TRANSLATOR_CONFIG_PATH) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()
        self.config_path = Path(config_path)

    @property
    def is_processing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def get_default_model(self) -> str:
        return DEFAULT_TRANSLATE_MODEL

    def default_config(self) -> dict:
        default_model = self.get_default_model()
        return {
            "provider": "gemini",
            "model": default_model,
            "api_key": "",
            "target_language": "vi",
            "content_safety": False,
        }

    def get_model_options(self) -> list[str]:
        return TRANSLATE_MODELS

    def load_config(self) -> dict:
        config = self.default_config()
        if self.config_path.exists():
            try:
                loaded = load_json_file(self.config_path)
                if isinstance(loaded, dict):
                    config.update({k: v for k, v in loaded.items() if k in config})
            except Exception:
                pass
        
        encrypted_key = config.get("api_key", "")
        decrypted_key = ""
        if encrypted_key:
            from utils import crypto
            dec = crypto.decrypt(encrypted_key)
            decrypted_key = dec if dec is not None else encrypted_key
        config["api_key"] = decrypted_key
        
        return config

    def save_config(self, config: dict) -> None:
        data = self.default_config()
        if self.config_path.exists():
            try:
                loaded = load_json_file(self.config_path)
                if isinstance(loaded, dict):
                    data.update({k: v for k, v in loaded.items() if k in data})
            except Exception:
                pass
        
        data.update({key: value for key, value in config.items() if key in data})
        
        api_key = config.get("api_key") or ""
            
        from utils import crypto
        encrypted_key = crypto.encrypt(api_key) if api_key else ""
        data["api_key"] = encrypted_key
            
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
        batch_size: int = 10,
        callbacks: Optional[TranslateCallbacks] = None,
    ) -> TranslateResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang dịch, vui lòng đợi.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or TranslateCallbacks()
        started_at = time.monotonic()
        translated_segments: list[SrtSegment] = []
        output_path: Optional[Path] = None

        try:
            save_user_output_dir(output_dir)
            self.save_config(
                {
                    "provider": provider,
                    "model": model,
                    "api_key": api_key,
                    "target_language": target_language,
                    "content_safety": content_safety,
                }
            )
            self._emit(callbacks.on_progress, stage="parse", message="Đang đọc file SRT...", percent=0)
            source_segments = self._cleanup_source_segments(parse_srt(input_srt))
            if not source_segments:
                raise ValueError("File SRT không còn nội dung hợp lệ sau khi lọc nhiễu.")
            chunks = chunk_segments(source_segments, batch_size=batch_size)
            output_path = build_output_path(input_srt, output_dir or DEFAULT_TRANSLATE_OUTPUT_DIR, target_language)

            translator = GeminiTranslator(api_key=api_key, model=model)

            total_chunks = len(chunks)

            text_models = self.get_model_options()
            fallback_models = [model]
            for m in text_models:
                if m not in fallback_models:
                    fallback_models.append(m)

            current_model_index = 0

            for chunk_index, chunk in enumerate(chunks, start=1):
                self._check_stop()
                
                # Count input characters (only alphanumeric)
                input_chars = sum(sum(1 for c in segment.text if c.isalnum()) for segment in chunk)
                
                max_retries = 5
                retry_delay = 5.0
                translated_texts = None
                success = False
                
                # Sắp xếp các model fallback theo thứ tự thử nghiệm (ưu tiên model hiện tại đang hoạt động tốt)
                ordered_models = fallback_models[current_model_index:] + fallback_models[:current_model_index]
                
                for active_model in ordered_models:
                    translator.model = active_model
                    
                    for attempt in range(1, max_retries + 1):
                        try:
                            self._check_stop()
                            self._emit(
                                callbacks.on_progress,
                                stage="translate",
                                message=f"Đang dịch cụm {chunk_index}/{total_chunks} (Model: {active_model}, Lần thử {attempt}/{max_retries}, Input: {input_chars} ký tự)...",
                                percent=((chunk_index - 1) / total_chunks) * 100,
                            )
                            translated_texts = translator.translate_segments(
                                segments=chunk,
                                all_segments=source_segments,
                                target_language=target_language,
                                content_safety=content_safety,
                                source_name=Path(input_srt).name,
                            )
                            success = True
                            current_model_index = fallback_models.index(active_model)
                            break
                        except Exception as exc:
                            print(f"[TRANSLATE] {exc}")
                            if attempt < max_retries:
                                self._emit(
                                    callbacks.on_progress,
                                    stage="translate",
                                    message=f"Lỗi cụm {chunk_index} ({active_model} Lần {attempt} thất bại). Thử lại sau {int(retry_delay)}s ...",
                                    percent=((chunk_index - 1) / total_chunks) * 100,
                                )
                                if self._stop_event.wait(retry_delay):
                                    raise RuntimeError("Đã dừng tác vụ dịch.")
                            else:
                                print(f"[TRANSLATE] Model {active_model} thất bại.")
                    
                    if success:
                        break
                    
                if not success:
                    raise RuntimeError(f"Tất cả model đều thất bại tại cụm {chunk_index}.")
                
                # Count output characters (only alphanumeric)
                output_chars = sum(sum(1 for c in text if c.isalnum()) for text in translated_texts)
                
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

            output_path.write_text(serialize_srt(translated_segments), encoding="utf-8")

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
    def _cleanup_source_segments(segments: list[SrtSegment]) -> list[SrtSegment]:
        cleaned_srt: list[SrtSegment] = []
        for source_segment in segments:
            cleaned_segments = cleanup_transcript_segments(
                [
                    TranscriptSegment(
                        start_time=0,
                        end_time=0,
                        content=source_segment.text,
                    )
                ]
            )
            if not cleaned_segments:
                continue
            cleaned_segment = cleaned_segments[0]
            cleaned_srt.append(
                SrtSegment(
                    index=source_segment.index,
                    start_time=source_segment.start_time,
                    end_time=source_segment.end_time,
                    text=cleaned_segment.content,
                )
            )
        return cleaned_srt

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
