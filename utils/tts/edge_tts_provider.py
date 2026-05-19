from __future__ import annotations

import asyncio
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from utils.tts.base import BaseTTS
from utils.tts.models import TtsVoice


EDGE_FALLBACK_VOICES = [
    TtsVoice("vi-VN-HoaiMyNeural", "HoaiMy", "vi-VN", "Female", "edge-tts"),
    TtsVoice("vi-VN-NamMinhNeural", "NamMinh", "vi-VN", "Male", "edge-tts"),
    TtsVoice("en-US-JennyNeural", "Jenny", "en-US", "Female", "edge-tts"),
    TtsVoice("en-US-GuyNeural", "Guy", "en-US", "Male", "edge-tts"),
    TtsVoice("zh-CN-XiaoxiaoNeural", "Xiaoxiao", "zh-CN", "Female", "edge-tts"),
    TtsVoice("zh-CN-YunxiNeural", "Yunxi", "zh-CN", "Male", "edge-tts"),
]


class EdgeTTSProvider(BaseTTS):
    provider_id = "edge-tts"
    _voice_cache: list[TtsVoice] | None = None
    max_chunk_chars = 240

    def list_voices(self, language: str | None = None) -> list[TtsVoice]:
        try:
            import edge_tts
        except Exception:
            voices = EDGE_FALLBACK_VOICES
        else:
            if self._voice_cache is None:
                raw_voices = _run_async(edge_tts.list_voices)
                self._voice_cache = [
                    TtsVoice(
                        id=str(item.get("ShortName", "")),
                        name=str(item.get("FriendlyName") or item.get("ShortName", "")),
                        locale=str(item.get("Locale", "")),
                        gender=str(item.get("Gender", "")),
                        provider=self.provider_id,
                    )
                    for item in raw_voices
                    if item.get("ShortName")
                ]
            voices = self._voice_cache

        if not language:
            return voices
        prefix = language.lower()
        filtered = [voice for voice in voices if voice.locale.lower().startswith(prefix)]
        return filtered or voices

    def synthesize_segment(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: int,
        volume: int,
        pitch: int,
    ) -> Path:
        try:
            import edge_tts
        except Exception as exc:
            raise RuntimeError("Thiếu dependency edge-tts. Hãy cài requirements trước khi dùng Edge-TTS.") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        rate_str = _format_percent(rate)
        volume_str = _format_percent(volume)
        chunks = _split_text(text, self.max_chunk_chars)
        if len(chunks) == 1:
            _save_edge_chunk(
                edge_tts=edge_tts,
                text=chunks[0],
                voice_id=voice_id,
                rate=rate_str,
                volume=volume_str,
                output_path=output_path,
            )
            _ensure_audio_file(output_path)
            return output_path

        chunk_paths: list[Path] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_path = output_path.with_name(f"{output_path.stem}_part_{index:02d}{output_path.suffix}")
            _save_edge_chunk(
                edge_tts=edge_tts,
                text=chunk,
                voice_id=voice_id,
                rate=rate_str,
                volume=volume_str,
                output_path=chunk_path,
            )
            _ensure_audio_file(chunk_path)
            chunk_paths.append(chunk_path)
            time.sleep(0.25)

        _concat_audio(chunk_paths, output_path)
        _ensure_audio_file(output_path)
        return output_path


def _format_percent(value: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{int(value)}%"


def _save_edge_chunk(
    *,
    edge_tts,
    text: str,
    voice_id: str,
    rate: str,
    volume: str,
    output_path: Path,
    retries: int = 3,
) -> None:
    last_error: Exception | None = None
    voice_candidates = [voice_id]
    fallback_voice = _fallback_voice(voice_id)
    if fallback_voice:
        voice_candidates.append(fallback_voice)

    for candidate in voice_candidates:
        for attempt in range(1, retries + 1):
            try:
                communicate = edge_tts.Communicate(text=text, voice=candidate, rate=rate, volume=volume)
                _run_async(communicate.save, str(output_path))
                _ensure_audio_file(output_path)
                return
            except Exception as exc:
                last_error = exc
                if output_path.exists():
                    output_path.unlink(missing_ok=True)
                if attempt < retries:
                    time.sleep(0.8 * attempt)
    raise RuntimeError(
        f"Edge-TTS không trả về audio sau {retries} lần thử với voice {voice_id}."
    ) from last_error


def _fallback_voice(voice_id: str) -> str:
    fallbacks = {
        "vi-VN-NamMinhNeural": "vi-VN-HoaiMyNeural",
    }
    return fallbacks.get(voice_id, "")


def _split_text(text: str, max_chars: int) -> list[str]:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return [normalized]

    chunks: list[str] = []
    current = ""
    for part in _sentence_parts(normalized):
        if not current:
            current = part
        elif len(current) + 1 + len(part) <= max_chars:
            current = f"{current} {part}"
        else:
            chunks.extend(_hard_split(current, max_chars))
            current = part
    if current:
        chunks.extend(_hard_split(current, max_chars))
    return [chunk for chunk in chunks if chunk.strip()]


def _sentence_parts(text: str) -> list[str]:
    parts: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in ".!?;:。！？":
            parts.append(current.strip())
            current = ""
    if current.strip():
        parts.append(current.strip())
    return parts


def _hard_split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[index : index + max_chars] for index in range(0, len(word), max_chars))
        elif not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def _concat_audio(inputs: list[Path], output_path: Path) -> None:
    list_path = output_path.with_name(f"{output_path.stem}_concat.txt")
    lines = [f"file '{path.resolve().as_posix()}'" for path in inputs]
    list_path.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _ensure_audio_file(path: Path) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"Edge-TTS không tạo được audio: {path.name}")


def _run_async(func, *args):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(func(*args))

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(func(*args)))
        return future.result()
