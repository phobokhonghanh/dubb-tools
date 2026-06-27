from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from config.paths import Paths
from core.use_cases.tts_factory import TTSProviderFactory
from infrastructure.providers.tts import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    GeneratedSegment,
    TtsProgress,
    TtsResult,
    TtsSegment,
    TtsVoice,
    adjust_speed,
    apply_volume,
    compose_timeline,
    get_duration,
    parse_tts_segments,
    require_ffmpeg,
)


CONFIG_PATH = Paths.get_config_path("tts_config.json")


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
        "auto_merge": True,
        "max_workers": 5,
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
        
        # Decrypt API Keys
        from utils import crypto
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
        data = self.load_config()
        data.update({key: value for key, value in config.items() if key in data})
        
        # Encrypt API Keys before saving
        from utils import crypto
        api_keys = data.get("api_keys")
        if isinstance(api_keys, dict):
            encrypted_keys = {}
            for k, v in api_keys.items():
                if v:
                    encrypted_keys[k] = crypto.encrypt(v)
                else:
                    encrypted_keys[k] = v
            data["api_keys"] = encrypted_keys

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_voices(self, *, provider: str, language: str, api_key: str | None = None) -> list[TtsVoice]:
        tts = TTSProviderFactory.get_provider(provider, api_key=api_key or "placeholder")
        return tts.list_voices(language)

    def run_job(
        self,
        *,
        input_srt: str,
        input_text: Optional[str] = None,
        input_mode: str = "file",
        output_dir: str,
        provider: str,
        language: str,
        voice_id: str,
        rate: int,
        volume: int,
        pitch: int,
        keep_segments: bool,
        api_key: str | None = None,
        auto_merge: bool = True,
        max_workers: int = 5,
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
            out_dir = Path(output_dir or DEFAULT_TTS_OUTPUT_DIR).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)

            if input_mode == "text":
                import hashlib
                text_bytes = (input_text or "").encode("utf-8")
                text_hash = hashlib.md5(text_bytes).hexdigest()[:8]
                source_stem = f"text_{text_hash}"
            else:
                source = Path(input_srt).expanduser()
                source_stem = source.stem

            segment_dir = out_dir / f"{source_stem}_segments"
            segment_dir.mkdir(parents=True, exist_ok=True)
            output_file = out_dir / f"{source_stem}_speech.mp3"

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
                    "auto_merge": auto_merge,
                    "max_workers": max_workers,
                    "api_keys": api_keys,
                    "input_mode": input_mode,
                    "input_text": input_text or "",
                }
            )

            self._emit(callbacks.on_progress, stage="init", message="Đang khởi tạo...", percent=0)
            
            if input_mode == "text":
                segments = []
                lines = [line.strip() for line in (input_text or "").split("\n") if line.strip()]
                for idx, line in enumerate(lines, start=1):
                    segments.append(
                        TtsSegment(
                            index=idx,
                            start_time="00:00:00,000",
                            end_time="00:00:00,000",
                            text=line,
                            start_sec=0.0,
                            end_sec=0.0,
                            target_duration_sec=999999.0,
                        )
                    )
            else:
                segments = parse_tts_segments(source)

            tts = self._build_provider(provider, api_key)
            total = len(segments)

            progress_lock = Lock()
            completed_count = 0

            def process_segment(item) -> GeneratedSegment:
                position, segment = item
                self._check_stop()

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

                    gen_seg = GeneratedSegment(
                        index=segment.index,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        target_duration_sec=segment.target_duration_sec,
                        raw_duration_sec=raw_duration,
                        final_duration_sec=final_duration,
                        file_path=str(final_path),
                        status="done",
                    )
                except Exception as exc:
                    preview = " ".join(segment.text.split())[:120]
                    print(f"[TTS Error] Lỗi tạo audio ở segment {segment.index}: {exc}. Nội dung: {preview}")
                    gen_seg = GeneratedSegment(
                        index=segment.index,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        target_duration_sec=segment.target_duration_sec,
                        raw_duration_sec=None,
                        final_duration_sec=None,
                        file_path=None,
                        status="error",
                    )

                nonlocal completed_count
                with progress_lock:
                    generated.append(gen_seg)
                    generated.sort(key=lambda s: s.index)
                    completed_count += 1

                    if callbacks.on_segment_done:
                        callbacks.on_segment_done(list(generated))
                    self._emit(
                        callbacks.on_progress,
                        stage="synthesize",
                        message=f"Đã tạo {completed_count}/{total} segment.",
                        percent=(completed_count / total) * 90,
                    )
                return gen_seg

            futures = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for position, segment in enumerate(segments, start=1):
                    if position > 1:
                        import random
                        delay = random.uniform(3.0, 7.0)
                        if self._stop_event.wait(delay):
                            break
                    if self._stop_event.is_set():
                        break
                    futures.append(executor.submit(process_segment, (position, segment)))

                for future in as_completed(futures):
                    if self._stop_event.is_set():
                        for f in futures:
                            f.cancel()
                        raise RuntimeError("Đã dừng tác vụ lồng tiếng.")
                    future.result()

            has_errors = any(s.status == "error" for s in generated)
            if auto_merge and not has_errors:
                self._emit(callbacks.on_progress, stage="compose", message="Đang gộp file audio...", percent=95)
                if input_mode == "text":
                    from infrastructure.providers.tts.composer import create_silence, concat_audio
                    parts = []
                    for idx, gen_seg in enumerate(generated):
                        if gen_seg.file_path:
                            parts.append(Path(gen_seg.file_path))
                            if idx < len(generated) - 1:
                                silence_path = segment_dir / f"silence_{gen_seg.index}.mp3"
                                create_silence(silence_path, 0.5)
                                parts.append(silence_path)
                    if parts:
                        concat_audio(parts, output_file)
                    else:
                        raise RuntimeError("Không có audio segment để gộp.")
                else:
                    compose_timeline(
                        segments=segments,
                        generated=generated,
                        output_path=output_file,
                        work_dir=segment_dir,
                    )
                if not keep_segments and segment_dir.exists():
                    shutil.rmtree(segment_dir, ignore_errors=True)
                out_path_str = str(output_file)
            else:
                if has_errors:
                    self._emit(callbacks.on_progress, stage="synthesize", message="Có phân đoạn bị lỗi. Vui lòng làm lại (Restart) phân đoạn lỗi.", percent=95)
                else:
                    self._emit(callbacks.on_progress, stage="synthesize", message="Đã lưu các segment (bỏ qua gộp âm thanh).", percent=95)
                out_path_str = None

            result = TtsResult(
                ok=True,
                output_file=out_path_str,
                segment_dir=str(segment_dir) if (keep_segments or not auto_merge or has_errors) else None,
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

    def synthesize_single_segment(
        self,
        *,
        index: int,
        text: str,
        start_time: str,
        end_time: str,
        target_duration_sec: float,
        segment_dir: Path | str,
        provider: str,
        voice_id: str,
        rate: int,
        volume: int,
        pitch: int,
        api_key: str | None = None,
    ) -> GeneratedSegment:
        require_ffmpeg()
        segment_dir = Path(segment_dir).expanduser()
        segment_dir.mkdir(parents=True, exist_ok=True)
        raw_path = segment_dir / f"{index:04d}_raw.mp3"

        tts = self._build_provider(provider, api_key)
        synthesized = tts.synthesize_segment(
            text=text,
            voice_id=voice_id,
            output_path=raw_path,
            rate=rate if provider == "edge-tts" else 0,
            volume=volume if provider == "edge-tts" else 0,
            pitch=pitch,
        )
        raw_duration = get_duration(synthesized)
        working_path = synthesized

        if provider == "gemini-tts":
            working_path = self._apply_gemini_postprocess(
                input_path=working_path,
                segment_dir=segment_dir,
                index=index,
                rate=rate,
                volume=volume,
            )

        final_path = working_path
        final_duration = get_duration(final_path)

        return GeneratedSegment(
            index=index,
            start_time=start_time,
            end_time=end_time,
            target_duration_sec=target_duration_sec,
            raw_duration_sec=raw_duration,
            final_duration_sec=final_duration,
            file_path=str(final_path),
            status="done",
        )

    def _build_provider(self, provider: str, api_key: str | None):
        return TTSProviderFactory.get_provider(provider, api_key=api_key)

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

    def merge_segments(
        self,
        *,
        input_srt: str,
        output_dir: str,
        generated_segments: list[GeneratedSegment],
    ) -> str:
        source = Path(input_srt).expanduser()
        out_dir = Path(output_dir or DEFAULT_TTS_OUTPUT_DIR).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        segment_dir = out_dir / f"{source.stem}_segments"
        output_file = out_dir / f"{source.stem}_speech.mp3"
        
        segments = parse_tts_segments(source)
        compose_timeline(
            segments=segments,
            generated=generated_segments,
            output_path=output_file,
            work_dir=segment_dir,
        )
        return str(output_file)
