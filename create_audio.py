# To run this code you need to install the following dependencies:
# pip install google-genai

import mimetypes
import os
import re
import struct
from google import genai
from google.genai import types


DEFAULT_AUDIO_PROFILE = "A smooth, premium commercial voice."
DEFAULT_DIRECTOR_NOTE = (
    "Style: Open, conversational, natural reaction-style delivery, light breathiness, "
    "close-to-mic presence, expressive and emotionally reactive with subtle laughs and "
    "natural emphasis, natural dynamic pace, Southern Vietnamese accent."
)
DEFAULT_SCENE = (
    "A premium Vietnamese commercial voiceover delivered like a natural, emotionally "
    "responsive reaction to the product or story. The speaker should sound close, warm, "
    "confident, and genuinely engaged rather than overly scripted."
)
DEFAULT_SAMPLE_CONTEXT = (
    "Use a close-to-mic conversational delivery with natural pacing, subtle breath, soft "
    "emotional emphasis, and light expressive reactions where the transcript suggests it."
)


def save_binary_file(file_name, data):
    f = open(file_name, "wb")
    f.write(data)
    f.close()
    print(f"File saved to to: {file_name}")
    return file_name


def generate():
    # This function expects the caller to provide the textual pieces via
    # parameters. See `main()` below for CLI parsing.
    raise RuntimeError("generate() should be called with parameters. Use create_audio.generate_with_params(...)")


def normalize_prompt_part(value: str | None, default: str) -> str:
    if value is None:
        return default

    value = value.strip()
    return value or default


def build_content_text(*,
        transcript: str,
        audio_profile: str | None = None,
        director_note: str | None = None,
        scene: str | None = None,
        sample_context: str | None = None,
    ) -> str:
    transcript = transcript.strip()
    if not transcript:
        raise ValueError("transcript is required and cannot be blank.")

    audio_profile = normalize_prompt_part(audio_profile, DEFAULT_AUDIO_PROFILE)
    director_note = normalize_prompt_part(director_note, DEFAULT_DIRECTOR_NOTE)
    scene = normalize_prompt_part(scene, DEFAULT_SCENE)
    sample_context = normalize_prompt_part(sample_context, DEFAULT_SAMPLE_CONTEXT)

    return (
        "Read the following transcript based on the audio profile and director's note.\n\n"
        f"# Audio Profile\n{audio_profile}\n\n"
        f"# Director's note\n{director_note}\n\n"
        f"## Scene:\n{scene}\n\n"
        f"## Sample Context:\n{sample_context}\n\n"
        f"## Transcript:\n{transcript}"
    )


def generate_with_params(*,
        transcript: str,
        audio_profile: str | None = None,
        director_note: str | None = None,
        scene: str | None = None,
        sample_context: str | None = None,
        voice_name: str = "Orus",
        out_prefix: str = "ENTER_FILE_NAME",
        api_key: str | None = None,
    ) -> list[str]:
    client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
    model = "gemini-3.1-flash-tts-preview"

    content_text = build_content_text(
        transcript=transcript,
        audio_profile=audio_profile,
        director_note=director_note,
        scene=scene,
        sample_context=sample_context,
    )

    generate_content_config = types.GenerateContentConfig(
        temperature=1,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
            )
        ),
    )

    file_index = 0
    saved_files = []
    for chunk in client.models.generate_content_stream(
        model=model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=content_text)])],
        config=generate_content_config,
    ):
        if chunk.parts is None:
            continue
        if chunk.parts[0].inline_data and chunk.parts[0].inline_data.data:
            file_name = f"{out_prefix}_{file_index}"
            file_index += 1
            inline_data = chunk.parts[0].inline_data
            data_buffer = inline_data.data
            file_extension = mimetypes.guess_extension(inline_data.mime_type)
            if file_extension is None:
                file_extension = ".wav"
                data_buffer = convert_to_wav(inline_data.data, inline_data.mime_type)
            saved_files.append(save_binary_file(f"{file_name}{file_extension}", data_buffer))
        else:
            if text := chunk.text:
                print(text)
    return saved_files

def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """Generates a WAV file header for the given audio data and parameters.

    Args:
        audio_data: The raw audio data as a bytes object.
        mime_type: Mime type of the audio data.

    Returns:
        A bytes object representing the WAV file header.
    """
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size  # 36 bytes for header fields before data chunk size

    # http://soundfile.sapp.org/doc/WaveFormat/

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",          # ChunkID
        chunk_size,       # ChunkSize (total file size - 8 bytes)
        b"WAVE",          # Format
        b"fmt ",          # Subchunk1ID
        16,               # Subchunk1Size (16 for PCM)
        1,                # AudioFormat (1 for PCM)
        num_channels,     # NumChannels
        sample_rate,      # SampleRate
        byte_rate,        # ByteRate
        block_align,      # BlockAlign
        bits_per_sample,  # BitsPerSample
        b"data",          # Subchunk2ID
        data_size         # Subchunk2Size (size of audio data)
    )
    return header + audio_data

def parse_audio_mime_type(mime_type: str) -> dict[str, int | None]:
    """Parses bits per sample and rate from an audio MIME type string.

    Assumes bits per sample is encoded like "L16" and rate as "rate=xxxxx".

    Args:
        mime_type: The audio MIME type string (e.g., "audio/L16;rate=24000").

    Returns:
        A dictionary with "bits_per_sample" and "rate" keys. Values will be
        integers if found, otherwise None.
    """
    bits_per_sample = 16
    rate = 24000

    # Extract rate from parameters
    parts = mime_type.split(";")
    for param in parts: # Skip the main type part
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                # Handle cases like "rate=" with no value or non-integer value
                pass # Keep rate as default
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass # Keep bits_per_sample as default if conversion fails

    return {"bits_per_sample": bits_per_sample, "rate": rate}


if __name__ == "__main__":
    generate()
