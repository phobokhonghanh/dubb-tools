from __future__ import annotations

import json
import re

from google import genai
from google.genai import types

from utils.translator.base import BaseTranslator
from utils.translator.models import LANGUAGE_OPTIONS, SrtSegment
from utils.translator.srt import total_duration_sec


class GeminiTranslator(BaseTranslator):
    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key.strip():
            raise ValueError("Vui lòng nhập Gemini API key.")
        self.client = genai.Client(api_key=api_key.strip())
        self.model = model

    def translate_segments(
        self,
        *,
        segments: list[SrtSegment],
        all_segments: list[SrtSegment],
        target_language: str,
        content_safety: bool,
        source_name: str,
    ) -> list[str]:
        prompt = build_prompt(
            segments=segments,
            all_segments=all_segments,
            target_language=target_language,
            content_safety=content_safety,
            source_name=source_name,
        )
        config = types.GenerateContentConfig(
            temperature=0.3,
            response_modalities=["text"],
        )

        chunks: list[str] = []
        for chunk in self.client.models.generate_content_stream(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=config,
        ):
            if chunk.text:
                chunks.append(chunk.text)

        translated = parse_translation_json("".join(chunks), expected_count=len(segments))
        return translated


def build_prompt(
    *,
    segments: list[SrtSegment],
    all_segments: list[SrtSegment],
    target_language: str,
    content_safety: bool,
    source_name: str,
) -> str:
    target_name = LANGUAGE_OPTIONS.get(target_language, target_language)
    full_text = " ".join(segment.text for segment in all_segments)
    context_summary = {
        "source_file": source_name,
        "target_language": target_name,
        "total_lines": len(all_segments),
        "total_duration_sec": round(total_duration_sec(all_segments), 2),
        "full_text": full_text,
    }
    chunk_payload = [
        {
            "index": segment.index,
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text,
        }
        for segment in segments
    ]
    safety_text = ""
    if content_safety:
        safety_text = (
            "Apply mild content safety when translating: reduce unnecessarily graphic or sensitive wording "
            "while preserving meaning, timing, and viewer comprehension."
        )

    return f"""You are a professional subtitle translator.
Translate each subtitle line into {target_name}.
Use the full context to keep pronouns, tone, terminology, and continuity consistent.
{safety_text}

Rules:
- Return only valid JSON.
- Return a JSON array with exactly {len(segments)} strings.
- Keep the same order as input.
- Do not include timestamps, indexes, markdown, explanations, or extra keys.
- Preserve natural subtitle length and readability.

Context summary:
{json.dumps(context_summary, ensure_ascii=False)}

Subtitle chunk:
{json.dumps(chunk_payload, ensure_ascii=False)}
"""


def parse_translation_json(raw_text: str, *, expected_count: int) -> list[str]:
    cleaned = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError("AI không trả về JSON hợp lệ.") from exc

    if isinstance(payload, dict):
        for key in ("translations", "items", "result"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    if not isinstance(payload, list):
        raise ValueError("AI response phải là JSON array.")

    translated = [str(item).strip() for item in payload]
    if len(translated) != expected_count:
        raise ValueError(f"AI trả về {len(translated)} dòng, nhưng cần {expected_count} dòng.")
    return translated
