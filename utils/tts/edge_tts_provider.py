from __future__ import annotations

import asyncio
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
        communicate = edge_tts.Communicate(text=text, voice=voice_id, rate=rate_str, volume=volume_str)
        _run_async(communicate.save, str(output_path))
        return output_path


def _format_percent(value: int) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{int(value)}%"


def _run_async(func, *args):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(func(*args))

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(lambda: asyncio.run(func(*args)))
        return future.result()
