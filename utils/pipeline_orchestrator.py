from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Optional
from urllib.parse import urlparse

from app.services.merger_service import MergerCallbacks, MergerService
from app.services.translate_service import TranslateCallbacks, TranslateService
from app.services.tts_service import TtsCallbacks, TtsService
from utils.download import download
from utils.stt_processor import normalize_segments, save_transcript, transcribe_audio
from utils.translator import parse_srt, replace_all, serialize_srt
from utils.video_merger import require_ffmpeg
from utils.video_splitter import get_model_paths, split_video_audio


DEFAULT_PIPELINE_WORKSPACE = Path("resources/layer/pipeline")
PIPELINE_STEPS = ["download", "split", "stt", "translate", "tts", "merge"]
STEP_TITLES = {
    "download": "Tải File",
    "split": "Bộ Tách Video",
    "stt": "Giọng Nói Thành Văn Bản",
    "translate": "Dịch Phụ Đề",
    "tts": "Lồng Tiếng AI",
    "merge": "Gộp Video",
}


@dataclass
class PipelineConfig:
    source_mode: str = "url"
    selected_steps: list[str] = field(default_factory=lambda: list(PIPELINE_STEPS))
    workspace_root: str = str(DEFAULT_PIPELINE_WORKSPACE)
    input_url: str = ""
    local_video_path: str = ""
    input_audio_path: str = ""
    input_srt_path: str = ""
    translated_srt_path: str = ""
    merge_muted_video: str = ""
    merge_speech_audio: str = ""
    merge_background_audio: str = ""
    download_use_proxy: bool = True
    stt_model_size: str = "base"
    stt_language: str = "auto"
    stt_speaker_mode: str = "1 người nói"
    stt_auto_merge_enabled: bool = False
    stt_merge_group_size: int = 5
    stt_auto_normalize_enabled: bool = False
    translate_provider: str = "gemini"
    translate_model: str = "gemini-2.5-flash"
    translate_api_key: str = ""
    translate_target_language: str = "vi"
    translate_content_safety: bool = False
    translate_batch_enabled: bool = True
    translate_batch_size: int = 10
    translate_replace_enabled: bool = False
    translate_find_text: str = ""
    translate_replace_text: str = ""
    tts_provider: str = "edge-tts"
    tts_language: str = "vi"
    tts_voice_id: str = "vi-VN-HoaiMyNeural"
    tts_rate: int = 0
    tts_volume: int = 0
    tts_pitch: int = 0
    tts_keep_segments: bool = True
    tts_api_key: str = ""
    intro_video: str = ""
    outro_video: str = ""
    merge_output_name: str = ""
    merge_speech_volume: int = 100
    merge_background_volume: int = 125


@dataclass
class JobContext:
    job_id: str
    job_dir: str
    source_stem: str
    downloaded_video: Optional[str] = None
    local_video: Optional[str] = None
    muted_video: Optional[str] = None
    vocals_audio: Optional[str] = None
    background_audio: Optional[str] = None
    transcript_srt: Optional[str] = None
    translated_srt: Optional[str] = None
    speech_audio: Optional[str] = None
    final_video: Optional[str] = None


@dataclass
class PipelineStepStatus:
    step: str
    state: str = "pending"
    message: str = ""
    percent: Optional[float] = None
    output_path: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class PipelineProgress:
    current_step: str
    step_index: int
    total_steps: int
    overall_percent: float
    step_percent: float
    message: str
    context: JobContext


@dataclass
class PipelineResult:
    ok: bool
    job_dir: Optional[str]
    context: Optional[JobContext]
    steps: list[PipelineStepStatus]
    final_video: Optional[str]
    error_message: Optional[str]
    elapsed_sec: float


def create_job_context(config: PipelineConfig) -> JobContext:
    source_stem = _resolve_source_stem(config)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_id = f"{source_stem}_{timestamp}"
    workspace = Path(config.workspace_root or DEFAULT_PIPELINE_WORKSPACE).expanduser()
    job_dir = workspace / job_id
    counter = 2
    while job_dir.exists():
        job_dir = workspace / f"{job_id}_{counter}"
        counter += 1
    job_dir.mkdir(parents=True, exist_ok=True)
    return JobContext(job_id=job_dir.name, job_dir=str(job_dir), source_stem=source_stem)


def validate_pipeline_requirements(
    config: PipelineConfig,
    *,
    resume_context: Optional[JobContext] = None,
    start_step: Optional[str] = None,
) -> None:
    steps = _selected_steps(config, start_step=start_step)
    if not steps:
        raise ValueError("Vui lòng chọn ít nhất một bước pipeline.")

    first_step = steps[0]
    if first_step == "download":
        if not config.input_url.strip():
            raise ValueError("Vui lòng nhập URL để chạy bước tải file.")
    elif first_step == "split":
        if not (resume_context and (resume_context.downloaded_video or resume_context.local_video)):
            _require_file(config.local_video_path, "video gốc")
    elif first_step == "stt":
        if not (resume_context and resume_context.vocals_audio):
            _require_file(config.input_audio_path, "audio đầu vào cho STT")
    elif first_step == "translate":
        if not (resume_context and resume_context.transcript_srt):
            _require_file(config.input_srt_path, "file SRT đầu vào cho Translate")
    elif first_step == "tts":
        if not (resume_context and resume_context.translated_srt):
            _require_file(config.translated_srt_path, "file SRT đã dịch cho TTS")
    elif first_step == "merge":
        if not (resume_context and resume_context.muted_video):
            _require_file(config.merge_muted_video, "muted video cho Merge")
        if not (resume_context and resume_context.speech_audio):
            _require_file(config.merge_speech_audio, "speech audio cho Merge")

    if "split" in steps:
        get_model_paths()
    if "tts" in steps or "merge" in steps:
        require_ffmpeg()
    if "translate" in steps and not config.translate_api_key.strip():
        raise ValueError("Vui lòng nhập Gemini API key cho bước Translate.")
    if "tts" in steps and config.tts_provider == "gemini-tts" and not config.tts_api_key.strip():
        raise ValueError("Vui lòng nhập Gemini API key cho bước Gemini TTS.")


def run_pipeline(
    config: PipelineConfig,
    *,
    on_progress: Optional[Callable[[PipelineProgress], None]] = None,
    on_step_done: Optional[Callable[[PipelineStepStatus], None]] = None,
    on_log: Optional[Callable[[str], None]] = None,
    stop_event: Optional[Event] = None,
    resume_context: Optional[JobContext] = None,
    start_step: Optional[str] = None,
) -> PipelineResult:
    started_at = time.monotonic()
    context: Optional[JobContext] = None
    steps = [PipelineStepStatus(step=step) for step in _selected_steps(config, start_step=start_step)]

    try:
        validate_pipeline_requirements(config, resume_context=resume_context, start_step=start_step)
        context = resume_context or create_job_context(config)
        if resume_context:
            _log(on_log, f"Tiếp tục Job folder: {context.job_dir}")
            if start_step:
                _log(on_log, f"Chạy lại từ bước {STEP_TITLES.get(start_step, start_step)}.")
        else:
            _log(on_log, f"Job folder: {context.job_dir}")

        total_steps = len(steps)
        for index, step_status in enumerate(steps, start=1):
            _check_stop(stop_event)
            step = step_status.step
            step_status.state = "running"
            step_status.percent = 0
            step_status.message = f"Bắt đầu {STEP_TITLES.get(step, step)}..."
            _log(on_log, step_status.message)
            _emit_progress(on_progress, step, index, total_steps, 0, step_status.message, context)

            def sub_progress(message: str, percent: Optional[float]) -> None:
                safe_percent = None if percent is None else max(0.0, min(100.0, percent))
                step_status.percent = safe_percent
                step_status.message = message
                _emit_progress(on_progress, step, index, total_steps, safe_percent or 0, message, context)

            if step == "download":
                _run_download(config, context, sub_progress)
                step_status.output_path = context.downloaded_video
            elif step == "split":
                _run_split(config, context, sub_progress)
                step_status.output_path = context.muted_video
            elif step == "stt":
                _run_stt(config, context, sub_progress)
                step_status.output_path = context.transcript_srt
            elif step == "translate":
                _run_translate(config, context, sub_progress)
                step_status.output_path = context.translated_srt
            elif step == "tts":
                _run_tts(config, context, sub_progress)
                step_status.output_path = context.speech_audio
            elif step == "merge":
                _run_merge(config, context, sub_progress)
                step_status.output_path = context.final_video
            else:
                raise ValueError(f"Bước pipeline không hỗ trợ: {step}")

            step_status.state = "done"
            step_status.percent = 100
            step_status.message = f"Hoàn tất {STEP_TITLES.get(step, step)}."
            _log(on_log, f"{step_status.message} Kết quả: {step_status.output_path or '--'}")
            if on_step_done:
                on_step_done(step_status)
            _emit_progress(on_progress, step, index, total_steps, 100, step_status.message, context)

        elapsed = time.monotonic() - started_at
        return PipelineResult(
            ok=True,
            job_dir=context.job_dir,
            context=context,
            steps=steps,
            final_video=context.final_video,
            error_message=None,
            elapsed_sec=elapsed,
        )
    except Exception as exc:
        elapsed = time.monotonic() - started_at
        message = str(exc)
        failed_step = ""
        for status in steps:
            if status.state == "running":
                status.state = "error"
                status.error_message = message
                status.message = message
                failed_step = status.step
                if on_step_done:
                    on_step_done(status)
                break
        for status in steps:
            if status.state == "pending":
                status.state = "skipped"
                status.message = (
                    f"Đã dừng do lỗi ở bước {STEP_TITLES.get(failed_step, failed_step)}."
                    if failed_step
                    else "Đã dừng do pipeline gặp lỗi."
                )
                if on_step_done:
                    on_step_done(status)
        _log(on_log, f"Lỗi: {message}")
        return PipelineResult(
            ok=False,
            job_dir=context.job_dir if context else None,
            context=context,
            steps=steps,
            final_video=context.final_video if context else None,
            error_message=message,
            elapsed_sec=elapsed,
        )


def _run_download(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    output_path = Path(context.job_dir) / f"{context.source_stem}.mp4"

    def on_download_progress(item) -> None:
        progress(f"Đang tải {item.filename}...", item.percent)

    result = download(
        url=config.input_url,
        output_filename=str(output_path),
        use_proxy=config.download_use_proxy,
        on_progress=on_download_progress,
    )
    if not result.ok or not result.file_path:
        raise RuntimeError(result.error_message or "Tải file thất bại.")
    context.downloaded_video = result.file_path
    context.local_video = result.file_path


def _run_split(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    video_path = context.downloaded_video
    if not video_path and config.source_mode == "local_video" and config.local_video_path:
        video_path = _copy_local_video_to_job(config, context)
    if not video_path:
        video_path = context.local_video
    if not video_path:
        video_path = _copy_local_video_to_job(config, context)
    result = split_video_audio(
        video_path=video_path,
        output_dir=context.job_dir,
        on_progress=lambda item: progress(item.message, item.percent),
    )
    if not result.ok:
        raise RuntimeError(result.error_message or "Tách video thất bại.")
    context.muted_video = result.muted_video
    context.vocals_audio = result.vocals_audio
    context.background_audio = result.background_audio


def _run_stt(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    audio_path = context.vocals_audio or config.input_audio_path
    if not audio_path:
        raise ValueError("Không có audio đầu vào cho STT.")
    if config.stt_speaker_mode != "1 người nói":
        raise ValueError("Chức năng nhiều người nói sắp ra mắt.")
    language = None if config.stt_language in {"", "auto"} else config.stt_language
    result = transcribe_audio(
        audio_path=audio_path,
        model_size=config.stt_model_size,
        language=language,
        on_progress=lambda item: progress(item.message, item.percent),
    )
    if not result.ok:
        raise RuntimeError(result.error_message or "Nhận diện giọng nói thất bại.")
    segments = result.segments
    if config.stt_auto_normalize_enabled:
        progress("Đang chuẩn hóa text nhận diện...", None)
        segments = normalize_segments(segments)
    context.transcript_srt = save_transcript(segments, context.job_dir, audio_path, "srt")


def _run_translate(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    input_srt = context.transcript_srt or config.input_srt_path
    if not input_srt:
        raise ValueError("Không có file SRT đầu vào cho Translate.")
    service = TranslateService()
    result = service.run_job(
        input_srt=input_srt,
        output_dir=context.job_dir,
        provider=config.translate_provider,
        model=config.translate_model,
        api_key=config.translate_api_key,
        target_language=config.translate_target_language,
        content_safety=config.translate_content_safety,
        batch_size=config.translate_batch_size if config.translate_batch_enabled else 10_000_000,
        callbacks=TranslateCallbacks(on_progress=lambda item: progress(item.message, item.percent)),
    )
    if not result.ok or not result.output_file:
        raise RuntimeError(result.error_message or "Dịch subtitle thất bại.")
    context.translated_srt = _wait_for_file_ready(
        result.output_file,
        timeout_sec=2.0,
        progress=progress,
        waiting_message="Đang chờ file phụ đề dịch hoàn tất ghi xuống đĩa...",
        missing_label="file SRT đã dịch",
    )
    if config.translate_replace_enabled and config.translate_find_text:
        progress("Đang replace nội dung phụ đề sau khi dịch...", None)
        translated_segments = parse_srt(context.translated_srt)
        replaced_segments = replace_all(
            translated_segments,
            config.translate_find_text,
            config.translate_replace_text,
        )
        Path(context.translated_srt).write_text(serialize_srt(replaced_segments), encoding="utf-8")


def _run_tts(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    input_srt = context.translated_srt or config.translated_srt_path
    if not input_srt:
        raise ValueError("Không có file SRT đã dịch cho TTS.")
    input_srt = _wait_for_file_ready(
        input_srt,
        timeout_sec=2.0,
        progress=progress,
        waiting_message="Đang xác nhận file SRT đầu vào cho bước Lồng Tiếng AI...",
        missing_label="file SRT cho TTS",
    )
    service = TtsService()
    result = service.run_job(
        input_srt=input_srt,
        output_dir=context.job_dir,
        provider=config.tts_provider,
        language=config.tts_language,
        voice_id=config.tts_voice_id,
        rate=config.tts_rate,
        volume=config.tts_volume,
        pitch=config.tts_pitch,
        keep_segments=config.tts_keep_segments,
        api_key=config.tts_api_key or None,
        callbacks=TtsCallbacks(on_progress=lambda item: progress(item.message, item.percent)),
    )
    if not result.ok or not result.output_file:
        raise RuntimeError(result.error_message or "Tạo audio lồng tiếng thất bại.")
    context.speech_audio = result.output_file


def _run_merge(config: PipelineConfig, context: JobContext, progress: Callable[[str, Optional[float]], None]) -> None:
    muted_video = context.muted_video or config.merge_muted_video
    speech_audio = context.speech_audio or config.merge_speech_audio
    background_audio = context.background_audio or config.merge_background_audio
    if not muted_video:
        raise ValueError("Không có muted video cho Merge.")
    if not speech_audio:
        raise ValueError("Không có speech audio cho Merge.")
    service = MergerService()
    result = service.run_job(
        main_video=muted_video,
        speech_audio=speech_audio,
        background_audio=background_audio or "",
        intro_video=config.intro_video,
        outro_video=config.outro_video,
        output_dir=context.job_dir,
        output_name=_resolve_merge_output_name(config, context),
        speech_volume=config.merge_speech_volume / 100,
        background_volume=config.merge_background_volume / 100,
        callbacks=MergerCallbacks(on_progress=lambda item: progress(item.message, item.percent)),
    )
    if not result.ok or not result.output_file:
        raise RuntimeError(result.error_message or "Gộp video thất bại.")
    context.final_video = result.output_file


def _resolve_merge_output_name(config: PipelineConfig, context: JobContext) -> str:
    raw_name = (config.merge_output_name or "").strip()
    if not raw_name:
        return f"{context.source_stem}_final.mp4"
    path = Path(raw_name)
    filename = path.name
    if not filename.lower().endswith(".mp4"):
        filename = f"{filename}.mp4"
    return _safe_stem(Path(filename).stem) + ".mp4"


def _copy_local_video_to_job(config: PipelineConfig, context: JobContext) -> str:
    source = _require_file(config.local_video_path, "video gốc")
    destination = Path(context.job_dir) / f"{context.source_stem}{source.suffix.lower()}"
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    context.local_video = str(destination)
    return str(destination)


def _selected_steps(config: PipelineConfig, *, start_step: Optional[str] = None) -> list[str]:
    steps = [step for step in PIPELINE_STEPS if step in set(config.selected_steps)]
    if not start_step:
        return steps
    if start_step not in steps:
        raise ValueError("Bước lỗi cần chạy lại không còn nằm trong danh sách bước được chọn.")
    return steps[steps.index(start_step) :]


def _resolve_source_stem(config: PipelineConfig) -> str:
    if config.source_mode == "url" and config.input_url.strip():
        parsed = urlparse(config.input_url)
        path_stem = Path(parsed.path).stem if parsed.path else ""
        if path_stem:
            return _safe_stem(path_stem)
        domain = (parsed.netloc or "download").split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        if "." in domain:
            domain = domain.rsplit(".", 1)[0]
        return _safe_stem(domain)
    for value in (
        config.local_video_path,
        config.input_audio_path,
        config.input_srt_path,
        config.translated_srt_path,
        config.merge_muted_video,
        config.merge_speech_audio,
    ):
        if value:
            return _safe_stem(Path(value).stem)
    parsed = urlparse(config.input_url)
    fallback = Path(parsed.path).stem if parsed.path else "pipeline"
    return _safe_stem(fallback or "pipeline")


def _safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value.strip())
    return cleaned.strip("._") or "pipeline"


def _require_file(file_path: str, label: str) -> Path:
    if not file_path:
        raise ValueError(f"Vui lòng chọn {label}.")
    path = Path(file_path).expanduser()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy {label}: {path}")
    return path


def _check_stop(stop_event: Optional[Event]) -> None:
    if stop_event and stop_event.is_set():
        raise RuntimeError("Đã dừng pipeline.")


def _emit_progress(
    callback: Optional[Callable[[PipelineProgress], None]],
    current_step: str,
    step_index: int,
    total_steps: int,
    step_percent: float,
    message: str,
    context: JobContext,
) -> None:
    if not callback:
        return
    overall = ((step_index - 1) + max(0.0, min(100.0, step_percent)) / 100) / max(total_steps, 1) * 100
    callback(
        PipelineProgress(
            current_step=current_step,
            step_index=step_index,
            total_steps=total_steps,
            overall_percent=overall,
            step_percent=max(0.0, min(100.0, step_percent)),
            message=message,
            context=context,
        )
    )


def _log(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        callback(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


def _wait_for_file_ready(
    file_path: str,
    *,
    timeout_sec: float,
    progress: Callable[[str, Optional[float]], None],
    waiting_message: str,
    missing_label: str,
) -> str:
    path = Path(file_path).expanduser()
    deadline = time.monotonic() + timeout_sec
    informed = False
    while time.monotonic() <= deadline:
        if path.exists() and path.is_file():
            return str(path)
        if not informed:
            progress(waiting_message, None)
            informed = True
        time.sleep(0.1)
    raise FileNotFoundError(f"Không tìm thấy {missing_label}: {path}")
