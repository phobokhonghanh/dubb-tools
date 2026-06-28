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
from constants import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    save_user_output_dir,
    TTS_CONFIG_PATH,
)
from infrastructure.providers.tts import (
    GeneratedSegment,
    TtsProgress,
    TtsResult,
    TtsSegment,
    TtsVoice,
    TTSAudioDownloadError,
    adjust_speed,
    apply_volume,
    compose_timeline,
    get_duration,
    parse_tts_segments,
    require_ffmpeg,
)


@dataclass
class TtsCallbacks:
    on_progress: Optional[Callable[[TtsProgress], None]] = None
    on_segment_done: Optional[Callable[[list[GeneratedSegment]], None]] = None
    on_success: Optional[Callable[[TtsResult], None]] = None
    on_error: Optional[Callable[[TtsResult], None]] = None


def default_config() -> dict:
    from constants.tts import DEFAULT_TTS_PROVIDER, DEFAULT_VOICE_IDS
    model_list = []
    # edge-tts
    model_list.append({
        "provider": "edge-tts",
        "voice": DEFAULT_VOICE_IDS.get("edge-tts", "vi-VN-NamMinhNeural"),
        "key": "",
        "default": DEFAULT_TTS_PROVIDER == "edge-tts"
    })
    # gemini-tts
    model_list.append({
        "provider": "gemini-tts",
        "voice": DEFAULT_VOICE_IDS.get("gemini-tts", "Orus"),
        "key": "",
        "default": DEFAULT_TTS_PROVIDER == "gemini-tts"
    })
    # capcut
    model_list.append({
        "provider": "capcut",
        "voice": DEFAULT_VOICE_IDS.get("capcut", "7102355709945188865"),
        "key": "",
        "default": DEFAULT_TTS_PROVIDER == "capcut"
    })

    return {
        "model": model_list,
        "rate": 0,
        "volume": 20,
        "pitch": 0,
        "keep_segments": True,
        "auto_merge": False,
        "max_workers": 5,
        "language": "vi"
    }


class TtsService:
    def __init__(self, config_path: str | Path = TTS_CONFIG_PATH) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()
        self.config_path = Path(config_path)

    @property
    def is_processing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def _flatten_config(self, nested: dict) -> dict:
        config = {
            "provider": "edge-tts",
            "language": nested.get("language", "vi"),
            "voice_id": "",
            "rate": nested.get("rate", 0),
            "volume": nested.get("volume", 20),
            "pitch": nested.get("pitch", 0),
            "keep_segments": nested.get("keep_segments", True),
            "auto_merge": nested.get("auto_merge", False),
            "max_workers": nested.get("max_workers", 5),
            "api_keys": {}
        }
        model_list = nested.get("model", [])
        from utils import crypto
        for item in model_list:
            if not isinstance(item, dict):
                continue
            provider = item.get("provider", "")
            voice = item.get("voice", "")
            is_default = item.get("default", False)
            key = item.get("key", "")
            
            dec_key = ""
            if key:
                dec = crypto.decrypt(key)
                dec_key = dec if dec is not None else key
            
            if is_default:
                config["provider"] = provider
                config["voice_id"] = voice
            config["api_keys"][provider] = dec_key
        return config

    def _convert_legacy_loaded(self, loaded: dict) -> dict:
        config = {
            "provider": loaded.get("provider") or "edge-tts",
            "language": loaded.get("language") or "vi",
            "voice_id": loaded.get("voice_id") or "",
            "rate": loaded.get("rate") or 0,
            "volume": loaded.get("volume") or 20,
            "pitch": loaded.get("pitch") or 0,
            "keep_segments": loaded.get("keep_segments", True),
            "auto_merge": loaded.get("auto_merge", False),
            "max_workers": loaded.get("max_workers") or 5,
            "api_keys": {}
        }

        if not config["voice_id"] and "voice_ids" in loaded and isinstance(loaded["voice_ids"], dict):
            config["voice_id"] = loaded["voice_ids"].get(config["provider"], "")

        if not config["voice_id"]:
            from constants.tts import DEFAULT_VOICE_IDS
            config["voice_id"] = DEFAULT_VOICE_IDS.get(config["provider"], "")

        api_keys = loaded.get("api_keys", {})
        if isinstance(api_keys, dict):
            from utils import crypto
            decrypted_keys = {}
            for provider, key in api_keys.items():
                if isinstance(key, str) and key:
                    dec = crypto.decrypt(key)
                    decrypted_keys[provider] = dec if dec is not None else key
                else:
                    decrypted_keys[provider] = key
            config["api_keys"] = decrypted_keys
        
        return config

    def _write_flat_config_to_file(self, config: dict) -> None:
        from constants.tts import DEFAULT_VOICE_IDS
        model_list = []
        providers_list = ["edge-tts", "gemini-tts", "capcut"]
        for p in providers_list:
            is_active = (p == config.get("provider", "edge-tts"))
            
            voice = ""
            if is_active:
                voice = config.get("voice_id", "")
            else:
                if "voice_ids" in config and isinstance(config["voice_ids"], dict):
                    voice = config["voice_ids"].get(p, "")
                
            if not voice:
                voice = DEFAULT_VOICE_IDS.get(p, "")

            raw_key = config.get("api_keys", {}).get(p, "")
            encrypted_key = ""
            if raw_key:
                from utils import crypto
                encrypted_key = crypto.encrypt(raw_key)

            model_list.append({
                "provider": p,
                "voice": voice,
                "key": encrypted_key,
                "default": is_active
            })

        output_data = {
            "model": model_list,
            "rate": config.get("rate", 0),
            "volume": config.get("volume", 20),
            "pitch": config.get("pitch", 0),
            "keep_segments": config.get("keep_segments", True),
            "auto_merge": config.get("auto_merge", False),
            "max_workers": config.get("max_workers", 5),
            "language": config.get("language", "vi")
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_config(self) -> dict:
        config = {
            "provider": "edge-tts",
            "language": "vi",
            "voice_id": "",
            "rate": 0,
            "volume": 20,
            "pitch": 0,
            "keep_segments": True,
            "auto_merge": False,
            "max_workers": 5,
            "api_keys": {}
        }
        
        if not self.config_path.exists():
            return self._flatten_config(default_config())
            
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return self._flatten_config(default_config())

        if not isinstance(loaded, dict):
            return self._flatten_config(default_config())

        # Support migrating old configuration format
        if "model" not in loaded:
            legacy_flat = self._convert_legacy_loaded(loaded)
            try:
                self._write_flat_config_to_file(legacy_flat)
            except Exception:
                pass
            return legacy_flat

        for k in ["rate", "volume", "pitch", "keep_segments", "auto_merge", "max_workers", "language"]:
            if k in loaded:
                config[k] = loaded[k]

        model_list = loaded.get("model", [])
        decrypted_keys = {}
        active_provider = "edge-tts"
        active_voice = ""

        from utils import crypto
        for item in model_list:
            if not isinstance(item, dict):
                continue
            provider = item.get("provider", "")
            voice = item.get("voice", "")
            encrypted_key = item.get("key", "")
            is_default = item.get("default", False)

            decrypted_key = ""
            if encrypted_key:
                dec = crypto.decrypt(encrypted_key)
                decrypted_key = dec if dec is not None else encrypted_key
            decrypted_keys[provider] = decrypted_key

            if is_default:
                active_provider = provider
                active_voice = voice

        config["provider"] = active_provider
        config["voice_id"] = active_voice
        config["api_keys"] = decrypted_keys

        if not config["voice_id"]:
            from constants.tts import DEFAULT_VOICE_IDS
            config["voice_id"] = DEFAULT_VOICE_IDS.get(config["provider"], "")

        return config

    def save_config(self, config: dict) -> None:
        current = self.load_config()
        
        for k in ["language", "rate", "volume", "pitch", "keep_segments", "auto_merge", "max_workers"]:
            if k in config:
                current[k] = config[k]
        if "provider" in config:
            current["provider"] = config["provider"]
        if "voice_id" in config:
            current["voice_id"] = config["voice_id"]
        
        if "api_keys" in config and isinstance(config["api_keys"], dict):
            current["api_keys"].update(config["api_keys"])

        self._write_flat_config_to_file(current)

    def list_voices(self, *, provider: str, language: str, api_key: str | None = None) -> list[TtsVoice]:
        tts = TTSProviderFactory.get_provider(provider, api_key=api_key or "placeholder")
        return tts.list_voices(language)

    def run_job(
        self,
        *,
        input_srt: str = "",
        input_text: Optional[str] = None,
        input_mode: str = "file",
        output_dir: str = "",
        provider: str = "",
        language: str = "",
        voice_id: str = "",
        rate: int = 0,
        volume: int = 0,
        pitch: int = 0,
        keep_segments: bool = True,
        api_key: str | None = None,
        auto_merge: bool = True,
        max_workers: int = 5,
        callbacks: TtsCallbacks = None,
    ) -> TtsResult:
        with self._lock:
            if self._active:
                return TtsResult(ok=False, error_message="Service is busy")
            self._active = True
            self._stop_event.clear()

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
            api_keys = dict(config.get("api_keys") or {})
            if api_key:
                api_keys[provider] = api_key
            save_user_output_dir(output_dir)
            self.save_config(
                {
                    "provider": provider,
                    "language": language,
                    "voice_id": voice_id,
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
                    audio_url = getattr(exc, "audio_url", None)
                    gen_seg = GeneratedSegment(
                        index=segment.index,
                        start_time=segment.start_time,
                        end_time=segment.end_time,
                        target_duration_sec=segment.target_duration_sec,
                        raw_duration_sec=None,
                        final_duration_sec=None,
                        file_path=None,
                        status="error",
                        audio_url=audio_url,
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
