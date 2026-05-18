# To run this code you need to install the following dependencies:
# pip install google-genai

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from google import genai
from google.genai import types


ENV_PATH = Path(__file__).with_name(".env")


def load_env_file(env_path=ENV_PATH):
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


DEFAULT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
DEFAULT_PROMPT_PATH = Path(__file__).with_name("promt_translate.txt")
DEFAULT_TRANSCRIPT_PATH = Path(__file__).with_name("transcript.jsonl")
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("audio_translate")
DEFAULT_PROMPT = """Act as a professional translator and media content editor.
Your task is to process the provided JSON data and return the result EXCLUSIVELY in JSON format, without any introductory or concluding text.

# Processing Requirements

## metadata_vi
- title: Catchy Vietnamese title, maximum 30 characters.
- description: Vietnamese summary, maximum 50 words.
- hashtags: An array of 3 Vietnamese hashtags, written as concatenated words (e.g., #xaynhatietkiem), each hashtag should not exceed 4 base words.

## batch
- Translate the text field into Vietnamese and place it in a new field named context.
- Use the comprehensive context from the full.text field to ensure that each individual batch translation is accurate and consistent.
- Keep start and end values unchanged.

## translate
- text: Translate the entire full text into Vietnamese fluently.
- total_duration: Keep the original value.

## voice
Based on the content of translate.text, generate the following fields in English:
- scene: A description of the delivery style. Replace "[Content Type]" with the actual category of the video (e.g., construction tips, cooking tutorial, storytelling...).
- scene template: "A premium, versatile commercial voiceover capable of adapting to [Content Type]. The delivery exudes professionalism, authenticity, and reliability, creating a direct connection with the listener."
- sample_context: Instructions for the voice talent. Incorporate these elements: "Use a natural conversational delivery with a fluid rhythm and strategic pauses to emphasize key information. Focus on clear articulation and subtle emotional transitions that follow the flow of the text."

# Strict Rule
Return only valid JSON code. No preamble, no explanation, no markdown filler outside the JSON block.

# Input Data
{{INPUT_JSON}}"""


def generate():
    raise RuntimeError("generate() should be called with parameters. Use translate.translate_with_params(...)")


def read_text_file(file_path: str | Path | None) -> str:
    if file_path is None:
        return DEFAULT_PROMPT

    path = Path(file_path)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return DEFAULT_PROMPT
    return text


def read_jsonl(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc

    if not records:
        raise ValueError(f"Transcript JSONL has no records: {path}")
    return records


def get_record_name(record: dict, fallback: str = "translation") -> str:
    name = record.get("info", {}).get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return fallback


def build_translate_input(record: dict) -> dict:
    info = record.get("info", {})
    full = record.get("full", {})

    return {
        "name": get_record_name(record),
        "source_language": info.get("language"),
        "source_language_probability": info.get("language_probability"),
        "segments": record.get("batch", []),
        "full_text": full.get("text", ""),
        "total_duration": full.get("total_duration"),
    }


def build_content_text(*, prompt: str, transcript_record: dict) -> str:
    prompt = prompt.strip()
    if not prompt:
        raise ValueError("prompt is required and cannot be blank.")

    translate_input = build_translate_input(transcript_record)
    input_json = json.dumps(translate_input, ensure_ascii=False, separators=(",", ":"))
    if "{{INPUT_JSON}}" in prompt:
        return prompt.replace("{{INPUT_JSON}}", input_json)
    return f"{prompt} Input Data: {input_json}"


def default_output_path(record: dict, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> Path:
    name = get_record_name(record)
    return Path(output_dir) / f"{name}_translate.jsonl"


def save_translation_record(file_path: str | Path, record: dict, *, append: bool = False) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"

    with path.open(mode, encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Saved translation to: {path}")


def translate_record(*,
        client: genai.Client,
        model: str,
        prompt: str,
        transcript_record: dict,
    ) -> str:
    content_text = build_content_text(prompt=prompt, transcript_record=transcript_record)
    generate_content_config = types.GenerateContentConfig(
        temperature=0.4,
        response_modalities=["text"],
    )

    chunks = []
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=content_text)])],
        config=generate_content_config,
    ):
        if text := chunk.text:
            print(text, end="")
            chunks.append(text)

    if chunks:
        print()
    return "".join(chunks).strip()


def translate_with_params(*,
        transcript_path: str | Path = DEFAULT_TRANSCRIPT_PATH,
        prompt_path: str | Path | None = None,
        output_dir: str | Path = DEFAULT_OUTPUT_DIR,
        output_path: str | Path | None = None,
        model: str = DEFAULT_MODEL,
        api_key: str | None = None,
        append: bool = False,
    ) -> list[dict]:
    prompt = read_text_file(prompt_path)
    transcript_records = read_jsonl(transcript_path)
    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    translated_records = []

    for transcript_record in transcript_records:
        translation = translate_record(
            client=client,
            model=model,
            prompt=prompt,
            transcript_record=transcript_record,
        )
        translated_record = {
            "info": transcript_record.get("info", {}),
            "input": build_translate_input(transcript_record),
            "translation": translation,
        }
        destination = Path(output_path) if output_path else default_output_path(transcript_record, output_dir)
        save_translation_record(destination, translated_record, append=append)
        translated_records.append(translated_record)

    return translated_records


def main():
    parser = argparse.ArgumentParser(description="Translate transcript JSONL with Gemini")
    parser.add_argument("--transcript", "-i", default=DEFAULT_TRANSCRIPT_PATH, help="Input transcript JSONL file")
    parser.add_argument("--prompt", "-p", default=None, help="Prompt text file. Defaults to embedded prompt")
    parser.add_argument("--out-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory when --out is not set")
    parser.add_argument("--out", "-o", default=None, help="Output JSONL file. Defaults to info.name-based file")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Gemini text model")
    parser.add_argument("--append", action="store_true", help="Append to output JSONL instead of overwriting")
    args = parser.parse_args()

    translate_with_params(
        transcript_path=args.transcript,
        prompt_path=args.prompt,
        output_dir=args.out_dir,
        output_path=args.out,
        model=args.model,
        append=args.append,
    )


if __name__ == "__main__":
    main()
