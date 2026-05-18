from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from google import genai
from google.genai import types

from utils.tts.base import BaseTTS
from utils.tts.gemini_audio import build_content_text, convert_to_wav
from utils.tts.models import GEMINI_TTS_MODEL, GEMINI_VOICES, TtsVoice


class GeminiTTSProvider(BaseTTS):
    provider_id = "gemini-tts"

    def __init__(self, *, api_key: str | None = None, model: str = GEMINI_TTS_MODEL) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model = model
        if not self.api_key:
            raise ValueError("Vui lòng nhập Gemini API key khi dùng Gemini TTS.")

    def list_voices(self, language: str | None = None) -> list[TtsVoice]:
        return [
            TtsVoice(id=voice, name=voice, locale=language or "multi", gender="", provider=self.provider_id)
            for voice in GEMINI_VOICES
        ]

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
        client = genai.Client(api_key=self.api_key)
        content_text = build_content_text(transcript=text)
        config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
                )
            ),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        for chunk in client.models.generate_content_stream(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=content_text)])],
            config=config,
        ):
            if chunk.parts is None:
                continue
            inline_data = chunk.parts[0].inline_data
            if inline_data and inline_data.data:
                data = inline_data.data
                extension = mimetypes.guess_extension(inline_data.mime_type)
                destination = output_path
                if extension is None or extension == ".wav":
                    data = convert_to_wav(data, inline_data.mime_type)
                    destination = output_path.with_suffix(".wav")
                destination.write_bytes(data)
                return destination

        raise RuntimeError("Gemini TTS không trả về audio.")
