from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.tts import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    EdgeTTSProvider,
    GeminiTTSProvider,
    GeneratedSegment,
    TtsProgress,
    TtsResult,
    TtsVoice,
    adjust_speed,
    apply_volume,
    compose_timeline,
    get_duration,
    parse_tts_segments,
    require_ffmpeg,
)


CONFIG_PATH = Path("config/tts_config.json")


@dataclass
class TtsCallbacks:
    on_progress: Optional[Callable[[TtsProgress], None]] = None
    on_segment_done: Optional[Callable[[list[GeneratedSegment]], None]] = None
    on_success: Optional[Callable[[TtsResult], None]] = None
    on_error: Optional[Callable[[TtsResult], None]] = None


def default_config() -> dict:
    return {
        "provider": DEFAULT_TTS_PROVIDER,
        "language": "vi",
        "voice_ids": {
            "edge-tts": "vi-VN-HoaiMyNeural",
            "gemini-tts": "Orus",
        },
        "rate": 0,
        "volume": 0,
        "pitch": 0,
        "keep_segments": True,
        "api_keys": {},
    }


class TtsService:
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
            config.update(loaded)
        if not isinstance(config.get("voice_ids"), dict):
            config["voice_ids"] = default_config()["voice_ids"]
        if not isinstance(config.get("api_keys"), dict):
            config["api_keys"] = {}
        return config

    def save_config(self, config: dict) -> None:
        data = self.load_config()
        data.update({key: value for key, value in config.items() if key in data})
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_voices(self, *, provider: str, language: str, api_key: str | None = None) -> list[TtsVoice]:
        if provider == "gemini-tts":
            return GeminiTTSProvider(api_key=api_key or "placeholder").list_voices(language)
        return EdgeTTSProvider().list_voices(language)

    def run_job(
        self,
        *,
        input_srt: str,
        output_dir: str,
        provider: str,
        language: str,
        voice_id: str,
        rate: int,
        volume: int,
        pitch: int,
        keep_segments: bool,
        api_key: str | None = None,
        callbacks: Optional[TtsCallbacks] = None,
    ) -> TtsResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có tác vụ lồng tiếng chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or TtsCallbacks()
        started_at = time.monotonic()
        generated: list[GeneratedSegment] = []
        segment_dir: Optional[Path] = None
        output_file: Optional[Path] = None

        try:
            require_ffmpeg()
            source = Path(input_srt).expanduser()
            out_dir = Path(output_dir or DEFAULT_TTS_OUTPUT_DIR).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            segment_dir = out_dir / f"{source.stem}_segments"
            segment_dir.mkdir(parents=True, exist_ok=True)
            output_file = out_dir / f"{source.stem}_speech.mp3"

            config = self.load_config()
            voice_ids = dict(config.get("voice_ids") or {})
            voice_ids[provider] = voice_id
            api_keys = dict(config.get("api_keys") or {})
            if api_key:
                api_keys[provider] = api_key
            self.save_config(
                {
                    "provider": provider,
                    "language": language,
                    "voice_ids": voice_ids,
                    "rate": rate,
                    "volume": volume,
                    "pitch": pitch,
                    "keep_segments": keep_segments,
                    "api_keys": api_keys,
                }
            )

            self._emit(callbacks.on_progress, stage="init", message="Đang khởi tạo...", percent=0)
            segments = parse_tts_segments(source)
            tts = self._build_provider(provider, api_key)
            total = len(segments)

            for position, segment in enumerate(segments, start=1):
                self._check_stop()
                self._emit(
                    callbacks.on_progress,
                    stage="synthesize",
                    message=f"Đang tạo audio segment {position}/{total}...",
                    percent=((position - 1) / total) * 90,
                )
                raw_path = segment_dir / f"{segment.index:04d}_raw.mp3"
                try:
                    synthesized = tts.synthesize_segment(
                        text=segment.text,
                        voice_id=voice_id,
                        output_path=raw_path,
                        rate=rate if provider == "edge-tts" else 0,
                        volume=volume if provider == "edge-tts" else 0,
                        pitch=pitch,
                    )
                except Exception as exc:
                    preview = " ".join(segment.text.split())[:120]
                    raise RuntimeError(
                        f"Lỗi tạo audio ở segment {segment.index}: {exc}. Nội dung: {preview}"
                    ) from exc
                raw_duration = get_duration(synthesized)
                working_path = synthesized

                if provider == "gemini-tts":
                    working_path = self._apply_gemini_postprocess(
                        input_path=working_path,
                        segment_dir=segment_dir,
                        index=segment.index,
                        rate=rate,
                        volume=volume,
                    )

                final_path = working_path
                final_duration = get_duration(final_path)
                if final_duration > segment.target_duration_sec:
                    self._emit(
                        callbacks.on_progress,
                        stage="speed",
                        message=f"Đang căn tốc độ segment {position}/{total}...",
                        percent=((position - 1) / total) * 90,
                    )
                    final_path = adjust_speed(
                        final_path,
                        segment_dir / f"{segment.index:04d}_timed.mp3",
                        segment.target_duration_sec,
                    )
                    final_duration = get_duration(final_path)

                generated.append(
                    GeneratedSegment(
                        index=segment.index,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        target_duration_sec=segment.target_duration_sec,
                        raw_duration_sec=raw_duration,
                        final_duration_sec=final_duration,
                        file_path=str(final_path),
                        status="done",
                    )
                )
                if callbacks.on_segment_done:
                    callbacks.on_segment_done(list(generated))
                self._emit(
                    callbacks.on_progress,
                    stage="synthesize",
                    message=f"Đã tạo {position}/{total} segment.",
                    percent=(position / total) * 90,
                )

            self._emit(callbacks.on_progress, stage="compose", message="Đang gộp file audio...", percent=95)
            compose_timeline(
                segments=segments,
                generated=generated,
                output_path=output_file,
                work_dir=segment_dir,
            )
            if not keep_segments and segment_dir.exists():
                shutil.rmtree(segment_dir, ignore_errors=True)

            result = TtsResult(
                ok=True,
                output_file=str(output_file),
                segment_dir=str(segment_dir) if keep_segments else None,
                segments=generated,
                elapsed_sec=time.monotonic() - started_at,
                error_message=None,
            )
            self._emit(callbacks.on_progress, stage="done", message="Hoàn tất", percent=100)
            if callbacks.on_success:
                callbacks.on_success(result)
            return result
        except Exception as exc:
            result = TtsResult(
                ok=False,
                output_file=str(output_file) if output_file else None,
                segment_dir=str(segment_dir) if segment_dir else None,
                segments=generated,
                elapsed_sec=time.monotonic() - started_at,
                error_message=str(exc),
            )
            if callbacks.on_error:
                callbacks.on_error(result)
            return result
        finally:
            with self._lock:
                self._active = False

    def _build_provider(self, provider: str, api_key: str | None):
        if provider == "gemini-tts":
            return GeminiTTSProvider(api_key=api_key)
        if provider == "edge-tts":
            return EdgeTTSProvider()
        raise ValueError(f"Nhà cung cấp TTS không hỗ trợ: {provider}")

    def _apply_gemini_postprocess(
        self,
        *,
        input_path: Path,
        segment_dir: Path,
        index: int,
        rate: int,
        volume: int,
    ) -> Path:
        output = input_path
        factor = max((100 + rate) / 100, 0.1)
        if abs(factor - 1.0) > 0.001:
            target_duration = get_duration(output) / factor
            output = adjust_speed(output, segment_dir / f"{index:04d}_gemini_rate.mp3", target_duration)
        if volume != 0:
            output = apply_volume(output, segment_dir / f"{index:04d}_gemini_volume.mp3", volume)
        return output

    def _check_stop(self) -> None:
        if self._stop_event.is_set():
            raise RuntimeError("Đã dừng tác vụ lồng tiếng.")

    @staticmethod
    def _emit(
        callback: Optional[Callable[[TtsProgress], None]],
        *,
        stage: str,
        message: str,
        percent: Optional[float] = None,
    ) -> None:
        if callback:
            callback(TtsProgress(stage=stage, message=message, percent=percent))
