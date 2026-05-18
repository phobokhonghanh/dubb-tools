# To run this code you need to install the following dependencies:
# pip install -r requirements.txt

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import audio_speed
import create_audio
import download
import extract_audio
import extract_text
import translate
from google import genai


DEFAULT_RESOURCES_DIR = Path("resources")
PYVIDEOTRANS_VENDOR_DIR = Path(__file__).resolve().parent / "vendor" / "pyvideotrans"


@dataclass
class PipelinePaths:
    resources_dir: Path
    audio_basic_dir: Path
    layer_dir: Path
    download_dir: Path
    process_root_dir: Path
    process_dir: Path
    downloaded_video: Path
    raw_video: Path
    raw_origin: Path
    sound_raw: Path
    raw_text: Path
    process_text: Path
    process_audio_generated_prefix: Path
    intro_audio: Path
    process_tts_unsynced: Path
    process_tts_timed: Path
    process_audio_unsynced: Path
    process_audio: Path
    process_video: Path
    checkpoint: Path
    log_file: Path


def setup_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("media_pipeline.executor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


def safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value)
    return safe.strip("_") or "download"


def build_download_name(url: str) -> str:
    parsed = urlparse(url)
    path_name = Path(parsed.path).stem
    if path_name:
        return safe_name(path_name)

    domain = parsed.netloc.split(":")[0].removeprefix("www.")
    if "." in domain:
        domain = domain.rsplit(".", 1)[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return safe_name(f"{domain or 'download'}_{timestamp}")


def build_paths(url: str, resources_dir: str | Path = DEFAULT_RESOURCES_DIR) -> PipelinePaths:
    resources_dir = Path(resources_dir)
    audio_basic_dir = resources_dir / "audio_basic"
    layer_dir = resources_dir / "layer"
    download_dir = layer_dir / "download"
    process_root_dir = layer_dir / "process"
    name = build_download_name(url)
    process_dir = process_root_dir / name

    return PipelinePaths(
        resources_dir=resources_dir,
        audio_basic_dir=audio_basic_dir,
        layer_dir=layer_dir,
        download_dir=download_dir,
        process_root_dir=process_root_dir,
        process_dir=process_dir,
        downloaded_video=download_dir / f"{name}.mp4",
        raw_video=process_dir / "raw_video.mp4",
        raw_origin=process_dir / "raw_origin.wav",
        sound_raw=process_dir / "sound_raw.wav",
        raw_text=process_dir / "raw_text.json",
        process_text=process_dir / "process_text.json",
        process_audio_generated_prefix=process_dir / "process_audio_generated",
        intro_audio=process_dir / "intro_audio.wav",
        process_tts_unsynced=process_dir / "process_tts_unsynced.wav",
        process_tts_timed=process_dir / "process_tts_timed.wav",
        process_audio_unsynced=process_dir / "process_audio_unsynced.wav",
        process_audio=process_dir / "process_audio.wav",
        process_video=process_dir / "process_video.mp4",
        checkpoint=process_dir / "checkpoint.json",
        log_file=layer_dir / "pipeline.log",
    )


def ensure_pipeline_dirs(paths: PipelinePaths) -> None:
    paths.download_dir.mkdir(parents=True, exist_ok=True)
    paths.process_dir.mkdir(parents=True, exist_ok=True)


def get_audio_basic_files(source_dir: str | Path) -> list[Path]:
    source_dir = Path(source_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Missing audio_basic directory: {source_dir}")

    intro_files = sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
    )
    if not intro_files:
        raise FileNotFoundError(f"No audio_basic files found in: {source_dir}")
    return intro_files


def write_json(file_path: str | Path, data: dict) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(file_path: str | Path) -> dict:
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def file_ready(file_path: str | Path) -> bool:
    path = Path(file_path)
    return path.exists() and path.stat().st_size > 0


def find_generated_audio_files(output_prefix: str | Path) -> list[Path]:
    prefix = Path(output_prefix)
    return sorted(
        path
        for path in prefix.parent.glob(f"{prefix.name}_*")
        if path.is_file()
        and file_ready(path)
        and path.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
    )


def output_ready(output_path: str | Path, logger: logging.Logger, overwrite: bool = False) -> bool:
    path = Path(output_path)
    if file_ready(path) and not overwrite:
        logger.info("Output already exists, skipping save: %s", path)
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    return False


def load_checkpoint(paths: PipelinePaths) -> dict:
    if not file_ready(paths.checkpoint):
        return {"process_name": paths.process_dir.name, "completed": []}
    return read_json(paths.checkpoint)


def mark_checkpoint(paths: PipelinePaths, checkpoint: dict, stage: str, logger: logging.Logger) -> None:
    completed = checkpoint.setdefault("completed", [])
    if stage not in completed:
        completed.append(stage)
    checkpoint["process_name"] = paths.process_dir.name
    checkpoint["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(paths.checkpoint, checkpoint)
    logger.info("Checkpoint saved: %s", stage)


def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def concat_audio_files(input_paths: list[Path], output_path: Path, logger: logging.Logger, overwrite: bool = False) -> Path:
    if not input_paths:
        raise ValueError("input_paths cannot be empty")
    if output_ready(output_path, logger, overwrite):
        return output_path

    filter_inputs = "".join(f"[{index}:a]" for index in range(len(input_paths)))
    filter_complex = f"{filter_inputs}concat=n={len(input_paths)}:v=0:a=1[outa]"
    cmd = ["ffmpeg", "-y"]
    for input_path in input_paths:
        cmd.extend(["-i", str(input_path)])
    cmd.extend(["-filter_complex", filter_complex, "-map", "[outa]", "-c:a", "pcm_s16le", str(output_path)])

    logger.info("Concatenating %d audio files into %s", len(input_paths), output_path)
    subprocess.run(cmd, check=True)
    return output_path


def mix_audio_tracks(
    *,
    voice_path: Path,
    sound_path: Path,
    output_path: Path,
    logger: logging.Logger,
    voice_volume: float = 1.25,
    sound_volume: float = 1.0,
    sound_delay: float = 0.0,
    overwrite: bool = False,
) -> Path:
    if output_ready(output_path, logger, overwrite):
        return output_path

    inputs = [voice_path, sound_path]

    cmd = ["ffmpeg", "-y"]
    for input_path in inputs:
        cmd.extend(["-i", str(input_path)])

    filters = [
        f"[0:a]volume={voice_volume}[a0]",
        f"[1:a]adelay={int(max(0, sound_delay) * 1000)}:all=1,volume={sound_volume}[a1]",
    ]
    mix_inputs = "[a0][a1]"
    filters.append(f"{mix_inputs}amix=inputs=2:duration=first:dropout_transition=0[outa]")
    cmd.extend(["-filter_complex", ";".join(filters), "-map", "[outa]", "-c:a", "pcm_s16le", str(output_path)])

    logger.info(
        "Mixing voice and sound_raw into %s | voice_volume=%.2f sound_volume=%.2f sound_delay=%.2fs",
        output_path,
        voice_volume,
        sound_volume,
        sound_delay,
    )
    subprocess.run(cmd, check=True)
    return output_path


def create_silent_audio_like(input_path: Path, output_path: Path, logger: logging.Logger, overwrite: bool = False) -> Path:
    if output_ready(output_path, logger, overwrite):
        return output_path

    duration = audio_speed.get_duration(input_path)
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{duration:.3f}",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    logger.warning(
        "Vocal separator is unavailable; creating silent sound_raw without speech: %s",
        output_path,
    )
    subprocess.run(cmd, check=True)
    return output_path


def build_sound_raw(
    input_path: Path,
    output_path: Path,
    process_dir: Path,
    logger: logging.Logger,
    overwrite: bool = False,
) -> Path:
    if output_ready(output_path, logger, overwrite):
        return output_path

    vocal_path = process_dir / "vocal_raw.wav"
    try:
        if PYVIDEOTRANS_VENDOR_DIR.exists():
            vendor_path = str(PYVIDEOTRANS_VENDOR_DIR)
            if vendor_path not in sys.path:
                sys.path.insert(0, vendor_path)
        from videotrans.process.prepare_audio import vocal_bgm

        ok, error = vocal_bgm(
            input_file=str(input_path),
            vocal_file=str(vocal_path),
            instr_file=str(output_path),
            uvr_models="spleeter",
        )
        if ok and file_ready(output_path):
            logger.info("Sound raw without vocal ready: %s", output_path)
            return output_path
        raise RuntimeError(f"Vocal separation failed: {error}")
    except Exception as exc:
        logger.warning("Cannot create instrumental sound_raw automatically: %s", exc)
        return create_silent_audio_like(input_path, output_path, logger, overwrite=overwrite)


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path, logger: logging.Logger, overwrite: bool = False) -> Path:
    if output_ready(output_path, logger, overwrite):
        return output_path

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path),
    ]
    logger.info("Merging video and audio into %s", output_path)
    subprocess.run(cmd, check=True)
    return output_path


def get_translate_payload(process_text: dict) -> dict:
    if "translation" in process_text and isinstance(process_text["translation"], dict):
        return process_text["translation"]
    return process_text


def build_audio_from_translation(
    *,
    process_text: dict,
    output_prefix: Path,
    voice_name: str,
    api_key: str | None,
) -> list[Path]:
    payload = get_translate_payload(process_text)
    translated = payload.get("translate", {})
    voice = payload.get("voice", {})
    transcript = translated.get("text")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("process_text.json must contain translate.text")

    generated_files = create_audio.generate_with_params(
        transcript=transcript,
        scene=voice.get("scene"),
        sample_context=voice.get("sample_context"),
        voice_name=voice_name,
        out_prefix=str(output_prefix),
        api_key=api_key,
    )
    if not generated_files:
        raise RuntimeError("Gemini TTS did not return any audio files")
    return [Path(file_path) for file_path in generated_files]


def get_target_duration(raw_text: dict, process_text: dict, raw_audio_path: Path | None = None) -> float:
    duration = raw_text.get("full", {}).get("total_duration")
    if duration is None and raw_audio_path and file_ready(raw_audio_path):
        duration = audio_speed.get_duration(raw_audio_path)
    if duration is None:
        payload = get_translate_payload(process_text)
        translated = payload.get("translate", {})
        duration = translated.get("total_duration")
    if duration is None:
        raise ValueError("Cannot find target duration in raw_text.full.total_duration, raw audio, or process_text.translate.total_duration")
    return float(duration)


def run_pipeline(
    *,
    url: str,
    resources_dir: str | Path = DEFAULT_RESOURCES_DIR,
    language: str | None = None,
    whisper_model_size: str = "base",
    gemini_text_model: str = translate.DEFAULT_MODEL,
    voice_name: str = "Orus",
    api_key: str | None = None,
    match_speed: bool = True,
    voice_volume: float = 1.25,
    sound_volume: float = 1.0,
    proxy_host: str | None = None,
    proxy_port: str | None = None,
    proxy_username: str | None = None,
    proxy_password: str | None = None,
    use_proxy: bool = True,
    force: bool = False,
) -> PipelinePaths:
    paths = build_paths(url, resources_dir)
    ensure_pipeline_dirs(paths)
    logger = setup_logger(paths.log_file)

    logger.info("Starting media pipeline for URL: %s", url)
    intro_files = get_audio_basic_files(paths.audio_basic_dir)
    checkpoint = load_checkpoint(paths)

    logger.info("Stage 1/7: download")
    if file_ready(paths.downloaded_video):
        logger.info("Skipping download; found %s", paths.downloaded_video)
    else:
        if not download.download(
            url,
            str(paths.downloaded_video),
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
            use_proxy=use_proxy,
        ):
            raise RuntimeError(f"Download failed: {url}")
    mark_checkpoint(paths, checkpoint, "download", logger)

    logger.info("Stage 2/7: extract raw video, raw origin audio, and sound raw")
    extract_stage = "extract_sound_raw_no_vocal_v2"
    if file_ready(paths.raw_video) and file_ready(paths.raw_origin) and file_ready(paths.sound_raw):
        logger.info("Skipping extract; found %s, %s, and %s", paths.raw_video, paths.raw_origin, paths.sound_raw)
    else:
        if file_ready(paths.raw_video):
            logger.info("Skipping raw video save; found %s", paths.raw_video)
        elif not extract_audio.save_video_without_audio(paths.downloaded_video, paths.raw_video):
            raise RuntimeError("Failed to save raw_video.mp4")

        if file_ready(paths.raw_origin):
            logger.info("Skipping raw origin audio save; found %s", paths.raw_origin)
        elif not extract_audio.extract_audio(paths.downloaded_video, paths.raw_origin):
            raise RuntimeError("Failed to save raw_origin.wav")

        if file_ready(paths.sound_raw):
            logger.info("Skipping sound raw save; found %s", paths.sound_raw)
        else:
            build_sound_raw(paths.raw_origin, paths.sound_raw, paths.process_dir, logger, overwrite=force)
    mark_checkpoint(paths, checkpoint, extract_stage, logger)

    logger.info("Stage 3/7: extract raw text")
    if file_ready(paths.raw_text):
        logger.info("Skipping transcription; found %s", paths.raw_text)
        raw_text = read_json(paths.raw_text)
    else:
        raw_text = extract_text.transcribe_audio(
            str(paths.raw_origin),
            model_size=whisper_model_size,
            language=language,
        )
        raw_text["info"]["name"] = paths.process_dir.name
        write_json(paths.raw_text, raw_text)
    mark_checkpoint(paths, checkpoint, "transcribe", logger)

    logger.info("Stage 4/7: translate raw text")
    if file_ready(paths.process_text):
        logger.info("Skipping translation; found %s", paths.process_text)
        process_text = read_json(paths.process_text)
    else:
        prompt = translate.read_text_file(None)
        client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        translation_text = translate.translate_record(
            client=client,
            model=gemini_text_model,
            prompt=prompt,
            transcript_record=raw_text,
        )
        process_text = parse_json_response(translation_text)
        write_json(paths.process_text, process_text)
    mark_checkpoint(paths, checkpoint, "translate", logger)

    logger.info("Stage 5/7: create process audio with intro")
    if file_ready(paths.process_audio_unsynced) and file_ready(paths.process_tts_unsynced) and file_ready(paths.intro_audio) and not force:
        logger.info("Skipping audio synthesis; found %s", paths.process_audio_unsynced)
    else:
        generated_audio_files = find_generated_audio_files(paths.process_audio_generated_prefix)
        if generated_audio_files:
            logger.info("Reusing %d generated TTS audio file(s): %s", len(generated_audio_files), paths.process_audio_generated_prefix)
        elif file_ready(paths.process_tts_unsynced):
            logger.info("Reusing existing TTS concat file: %s", paths.process_tts_unsynced)
        else:
            generated_audio_files = build_audio_from_translation(
                process_text=process_text,
                output_prefix=paths.process_audio_generated_prefix,
                voice_name=voice_name,
                api_key=api_key,
            )
        concat_audio_files(intro_files, paths.intro_audio, logger, overwrite=force)
        if generated_audio_files:
            concat_audio_files(generated_audio_files, paths.process_tts_unsynced, logger, overwrite=force)
        concat_audio_files([paths.intro_audio, paths.process_tts_unsynced], paths.process_audio_unsynced, logger, overwrite=force)
    mark_checkpoint(paths, checkpoint, "synthesize_audio", logger)

    logger.info("Stage 6/7: match audio speed and mix sound")
    audio_timing_stage = "time_audio_with_sound_v4"
    if file_ready(paths.process_audio) and audio_timing_stage in checkpoint.get("completed", []) and not force:
        logger.info("Skipping audio timing and sound mix; found %s", paths.process_audio)
    else:
        remix_outputs = force or audio_timing_stage not in checkpoint.get("completed", [])
        intro_duration = audio_speed.get_duration(paths.intro_audio)
        if match_speed:
            target_duration = get_target_duration(raw_text, process_text, paths.raw_origin)
            tts_target_duration = max(0.1, target_duration - intro_duration)
            logger.info(
                "Target total audio duration: %.2fs | intro: %.2fs | TTS target: %.2fs",
                target_duration,
                intro_duration,
                tts_target_duration,
            )
            if not output_ready(paths.process_tts_timed, logger, overwrite=force):
                audio_speed.adjust_speed(paths.process_tts_unsynced, paths.process_tts_timed, tts_target_duration, logger=logger)
        else:
            if not output_ready(paths.process_tts_timed, logger, overwrite=force):
                shutil.copy2(paths.process_tts_unsynced, paths.process_tts_timed)
                logger.info("Skipped speed matching; copied %s", paths.process_tts_timed)
        concat_audio_files([paths.intro_audio, paths.process_tts_timed], paths.process_audio_unsynced, logger, overwrite=force)
        mix_audio_tracks(
            voice_path=paths.process_audio_unsynced,
            sound_path=paths.sound_raw,
            output_path=paths.process_audio,
            logger=logger,
            voice_volume=voice_volume,
            sound_volume=sound_volume,
            sound_delay=intro_duration,
            overwrite=remix_outputs,
        )
    mark_checkpoint(paths, checkpoint, audio_timing_stage, logger)

    logger.info("Stage 7/7: merge final video")
    merge_stage = "merge_video_with_sound_v3"
    if file_ready(paths.process_video) and merge_stage in checkpoint.get("completed", []) and not force:
        logger.info("Skipping final video merge; found %s", paths.process_video)
    else:
        merge_outputs = force or merge_stage not in checkpoint.get("completed", [])
        merge_video_audio(paths.raw_video, paths.process_audio, paths.process_video, logger, overwrite=merge_outputs)
    mark_checkpoint(paths, checkpoint, merge_stage, logger)

    logger.info("Pipeline completed: %s", paths.process_video)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full media translation pipeline")
    parser.add_argument("--url", "-u", required=True, help="MP4 URL to download")
    parser.add_argument("--resources-dir", default=DEFAULT_RESOURCES_DIR, help="Pipeline resources directory")
    parser.add_argument("--language", "-l", default=None, help="Source language hint for Faster Whisper")
    parser.add_argument("--whisper-model-size", default="base", help="Faster Whisper model size")
    parser.add_argument("--gemini-text-model", default=translate.DEFAULT_MODEL, help="Gemini model for translation")
    parser.add_argument("--voice-name", default="Orus", help="Gemini TTS voice name")
    parser.add_argument("--api-key", default=None, help="Gemini API key. Defaults to GEMINI_API_KEY from environment")
    parser.add_argument("--no-speed", action="store_true", help="Skip audio speed matching")
    parser.add_argument("--voice-volume", type=float, default=1.25, help="Volume multiplier for generated/process voice audio")
    parser.add_argument("--sound-volume", type=float, default=1.0, help="Volume multiplier for sound_raw background audio")
    parser.add_argument("--no-proxy", action="store_true", help="Disable proxy for download stage")
    parser.add_argument("--force", action="store_true", help="Run all stages again even when checkpoint files exist")
    args = parser.parse_args()

    paths = run_pipeline(
        url=args.url,
        resources_dir=args.resources_dir,
        language=args.language,
        whisper_model_size=args.whisper_model_size,
        gemini_text_model=args.gemini_text_model,
        voice_name=args.voice_name,
        api_key=args.api_key,
        match_speed=not args.no_speed,
        voice_volume=args.voice_volume,
        sound_volume=args.sound_volume,
        use_proxy=not args.no_proxy,
        force=args.force,
    )
    print(paths.process_video)


if __name__ == "__main__":
    main()
