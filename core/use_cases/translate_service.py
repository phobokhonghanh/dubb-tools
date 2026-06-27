from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.stt_processor import TranscriptSegment, cleanup_transcript_segments
from config.paths import Paths
from infrastructure.providers.translator import (
    DEFAULT_TRANSLATE_MODEL,
    DEFAULT_TRANSLATE_OUTPUT_DIR,
    GeminiTranslator,
    SrtSegment,
    TranslateProgress,
    TranslateResult,
    build_output_path,
    chunk_segments,
    parse_srt,
    serialize_srt,
)


CONFIG_PATH = Paths.get_config_path("translator_config.json")


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
        
        # Decrypt API Keys
        from utils import crypto
        gemini_api_key = config.get("gemini_api_key")
        if gemini_api_key:
            decrypted = crypto.decrypt(gemini_api_key)
            config["gemini_api_key"] = decrypted if decrypted is not None else gemini_api_key

        api_keys = config.get("api_keys")
        if isinstance(api_keys, dict):
            decrypted_keys = {}
            for k, v in api_keys.items():
                if v:
                    decrypted = crypto.decrypt(v)
                    decrypted_keys[k] = decrypted if decrypted is not None else v
                else:
                    decrypted_keys[k] = v
            config["api_keys"] = decrypted_keys
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

        # Encrypt API Keys before saving
        from utils import crypto
        gemini_api_key = data.get("gemini_api_key")
        if gemini_api_key:
            data["gemini_api_key"] = crypto.encrypt(gemini_api_key)

        api_keys_dict = data.get("api_keys")
        if isinstance(api_keys_dict, dict):
            encrypted_keys = {}
            for k, v in api_keys_dict.items():
                if v:
                    encrypted_keys[k] = crypto.encrypt(v)
                else:
                    encrypted_keys[k] = v
            data["api_keys"] = encrypted_keys

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
            source_segments = self._cleanup_source_segments(parse_srt(input_srt))
            if not source_segments:
                raise ValueError("File SRT không còn nội dung hợp lệ sau khi lọc nhiễu.")
            chunks = chunk_segments(source_segments, batch_size=batch_size)
            output_path = build_output_path(input_srt, output_dir or DEFAULT_TRANSLATE_OUTPUT_DIR, target_language)

            if provider != "gemini":
                raise ValueError("Hiện tại chỉ hỗ trợ Gemini.")
            translator = GeminiTranslator(api_key=api_key, model=model)

            total_chunks = len(chunks)
            total_input_chars_all = sum(sum(1 for c in segment.text if c.isalnum()) for segment in source_segments)
            # print(f"[TRANSLATE] Bắt đầu dịch. Tổng số ký tự input của file (chỉ tính từ ngữ): {total_input_chars_all}")

            text_models = [
                "gemini-3.5-flash",
                "gemini-3-flash",
                "gemini-2.5-pro",
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-2.0-flash",
            ]
            fallback_models = [model]
            for m in text_models:
                if m not in fallback_models:
                    fallback_models.append(m)

            current_model_index = 0

            for chunk_index, chunk in enumerate(chunks, start=1):
                self._check_stop()
                
                # Count input characters (only alphanumeric)
                input_chars = sum(sum(1 for c in segment.text if c.isalnum()) for segment in chunk)
                # print(f"[TRANSLATE] Cụm {chunk_index}/{total_chunks} - Trước khi gửi: {input_chars} ký tự input (chỉ tính từ ngữ)")
                
                max_retries = 5
                retry_delay = 5.0
                translated_texts = None
                success = False
                
                for idx in range(current_model_index, len(fallback_models)):
                    active_model = fallback_models[idx]
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
                            current_model_index = idx  # Save this model as the working one
                            break  # Success, exit retry loop for active_model
                        except Exception as exc:
                            print(f"[TRANSLATE] Lỗi dịch cụm {chunk_index} với model {active_model} (Lần thử {attempt}/{max_retries}): {exc}")
                            if attempt < max_retries:
                                # Notify UI of the error and waiting status
                                self._emit(
                                    callbacks.on_progress,
                                    stage="translate",
                                    message=f"Lỗi cụm {chunk_index} ({active_model} Lần {attempt} thất bại). Đang chờ {int(retry_delay)}s để thử lại...",
                                    percent=((chunk_index - 1) / total_chunks) * 100,
                                )
                                # Wait with interruptibility
                                if self._stop_event.wait(retry_delay):
                                    raise RuntimeError("Đã dừng tác vụ dịch.")
                            else:
                                print(f"[TRANSLATE] Model {active_model} thất bại hoàn toàn sau 5 lần thử.")
                    
                    if success:
                        break  # Exit fallback models loop
                    
                if not success:
                    # Try falling back starting from index 0 in case the working model failed but we skipped earlier models
                    if current_model_index > 0:
                        # print(f"[TRANSLATE] Thử lại các model fallback từ đầu danh sách...")
                        for idx in range(0, current_model_index):
                            active_model = fallback_models[idx]
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
                                    current_model_index = idx  # Save this model as the working one
                                    break
                                except Exception as exc:
                                    print(f"[TRANSLATE] Lỗi dịch cụm {chunk_index} với model {active_model} (Lần thử {attempt}/{max_retries}): {exc}")
                                    if attempt < max_retries:
                                        self._emit(
                                            callbacks.on_progress,
                                            stage="translate",
                                            message=f"Lỗi cụm {chunk_index} ({active_model} Lần {attempt} thất bại). Đang chờ {int(retry_delay)}s để thử lại...",
                                            percent=((chunk_index - 1) / total_chunks) * 100,
                                        )
                                        if self._stop_event.wait(retry_delay):
                                            raise RuntimeError("Đã dừng tác vụ dịch.")
                                    else:
                                        print(f"[TRANSLATE] Model {active_model} thất bại hoàn toàn sau 5 lần thử.")
                            if success:
                                break
                    
                if not success:
                    raise RuntimeError(f"Tất cả các model fallback đều thất bại tại cụm {chunk_index}.")
                
                # Count output characters (only alphanumeric)
                output_chars = sum(sum(1 for c in text if c.isalnum()) for text in translated_texts)
                # print(f"[TRANSLATE] Cụm {chunk_index}/{total_chunks} - Sau khi xong: {output_chars} ký tự output (chỉ tính từ ngữ)")
                
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
                    message=f"Đã dịch {len(translated_segments)}/{len(source_segments)} dòng. (Cụm {chunk_index} Output: {output_chars} ký tự)",
                    percent=(chunk_index / total_chunks) * 100,
                )

            total_output_chars_all = sum(sum(1 for c in segment.text if c.isalnum()) for segment in translated_segments)
            # print(f"[TRANSLATE] Dịch hoàn tất. Tổng số ký tự output của file (chỉ tính từ ngữ): {total_output_chars_all}")

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
