from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.pipeline_service import PipelineCallbacks, PipelineService
from app.services.translate_service import TranslateService
from app.services.tts_service import TtsService
from utils.pipeline_orchestrator import (
    DEFAULT_PIPELINE_WORKSPACE,
    PIPELINE_STEPS,
    STEP_TITLES,
    PipelineConfig,
    PipelineProgress,
    PipelineResult,
    PipelineStepStatus,
)
from utils.translator import DEFAULT_TRANSLATE_MODEL, LANGUAGE_OPTIONS as TRANSLATE_LANGUAGES
from utils.tts import DEFAULT_TTS_PROVIDER, LANGUAGE_OPTIONS as TTS_LANGUAGES


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
SOURCE_OPTIONS = [("url", "Tải từ URL"), ("local_video", "Chọn file từ máy")]
STT_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
SPEAKER_OPTIONS = ["1 người nói", "2 người nói", "Nhiều người nói"]
STT_LANGUAGES = {
    "auto": "Auto",
    "vi": "vi",
    "en": "en",
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "th": "th",
}
TTS_PROVIDERS = [("edge-tts", "Edge-TTS"), ("gemini-tts", "Gemini TTS")]
VIDEO_FILTER = "File video (*.mp4 *.mov *.mkv *.avi *.webm)"
AUDIO_FILTER = "File âm thanh (*.mp3 *.wav *.m4a *.aac *.flac *.ogg)"
SRT_FILTER = "File SRT (*.srt)"
STATUS_LABELS = {
    "pending": "Đang chờ",
    "running": "Đang chạy",
    "done": "Hoàn thành",
    "error": "Thất bại",
    "skipped": "Bỏ qua",
}


def open_folder(path: str) -> None:
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603,S607
    else:
        os.startfile(path)  # type: ignore[attr-defined]


def pick_directory_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--directory",
                "--title=Chọn workspace pipeline",
                f"--filename={initial_dir.rstrip('/')}/",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        picked = result.stdout.strip()
        return picked or None

    try:
        from PySide6.QtWidgets import QApplication, QFileDialog
    except Exception:
        return None

    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    picked = QFileDialog.getExistingDirectory(None, "Chọn workspace pipeline", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_file_native(initial_dir: str, title: str, file_filter: str) -> Optional[str]:
    if shutil.which("zenity"):
        zenity_filter = file_filter.replace("Files", "files").replace("(", "| ").replace(")", "")
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                f"--title={title}",
                f"--filename={initial_dir.rstrip('/')}/",
                f"--file-filter={zenity_filter}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        picked = result.stdout.strip()
        return picked or None

    try:
        from PySide6.QtWidgets import QApplication, QFileDialog
    except Exception:
        return None

    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    picked, _ = QFileDialog.getOpenFileName(None, title, initial_dir, file_filter)
    if owns_app and app:
        app.quit()
    return picked or None


class PipelineView(BaseFeatureView):
    feature_id = "full_pipeline"
    title = "Tự Động Hóa Quy Trình"
    icon = ft.Icons.ACCOUNT_TREE

    def __init__(self) -> None:
        self.service = PipelineService()
        config = self.service.load_config()
        translator_config = TranslateService().load_config()
        tts_config = TtsService().load_config()

        self._source_mode: str = str(config.get("source_mode") or "url")
        self._selected_steps: list[str] = list(config.get("selected_steps") or PIPELINE_STEPS)
        self._workspace_root: str = str(config.get("workspace_root") or DEFAULT_PIPELINE_WORKSPACE)
        self._input_url: str = str(config.get("input_url") or "")
        self._local_video_path: str = str(config.get("local_video_path") or "")
        self._input_audio_path: str = str(config.get("input_audio_path") or "")
        self._input_srt_path: str = str(config.get("input_srt_path") or "")
        self._translated_srt_path: str = str(config.get("translated_srt_path") or "")
        self._merge_muted_video: str = str(config.get("merge_muted_video") or "")
        self._merge_speech_audio: str = str(config.get("merge_speech_audio") or "")
        self._merge_background_audio: str = str(config.get("merge_background_audio") or "")

        self._download_use_proxy: bool = bool(config.get("download_use_proxy", True))
        self._stt_model_size: str = str(config.get("stt_model_size") or "base")
        self._stt_language: str = str(config.get("stt_language") or "auto")
        self._stt_speaker_mode: str = str(config.get("stt_speaker_mode") or SPEAKER_OPTIONS[0])
        self._translate_batch_enabled: bool = bool(config.get("translate_batch_enabled", True))
        self._translate_batch_size: str = str(config.get("translate_batch_size") or 10)
        self._stt_auto_normalize_enabled: bool = bool(config.get("stt_auto_normalize_enabled", False))
        self._translate_model: str = str(config.get("translate_model") or translator_config.get("model") or DEFAULT_TRANSLATE_MODEL)
        api_keys = translator_config.get("api_keys") if isinstance(translator_config.get("api_keys"), dict) else {}
        self._translate_api_key: str = str(
            config.get("translate_api_key")
            or api_keys.get(self._translate_model)
            or translator_config.get("gemini_api_key")
            or ""
        )
        self._translate_target_language: str = str(
            config.get("translate_target_language") or translator_config.get("target_language") or "vi"
        )
        self._translate_content_safety: bool = bool(
            config.get("translate_content_safety", translator_config.get("content_safety", False))
        )
        self._translate_replace_enabled: bool = bool(config.get("translate_replace_enabled", False))
        self._translate_find_text: str = str(config.get("translate_find_text") or "")
        self._translate_replace_text: str = str(config.get("translate_replace_text") or "")

        self._tts_provider: str = str(config.get("tts_provider") or tts_config.get("provider") or DEFAULT_TTS_PROVIDER)
        self._tts_language: str = str(config.get("tts_language") or tts_config.get("language") or "vi")
        voice_ids = tts_config.get("voice_ids") if isinstance(tts_config.get("voice_ids"), dict) else {}
        self._tts_voice_id: str = str(config.get("tts_voice_id") or voice_ids.get(self._tts_provider) or "")
        self._tts_rate: int = int(config.get("tts_rate") or tts_config.get("rate") or 0)
        self._tts_volume: int = int(config.get("tts_volume") or tts_config.get("volume") or 0)
        self._tts_pitch: int = int(config.get("tts_pitch") or tts_config.get("pitch") or 0)
        self._tts_keep_segments: bool = bool(config.get("tts_keep_segments", tts_config.get("keep_segments", True)))
        tts_api_keys = tts_config.get("api_keys") if isinstance(tts_config.get("api_keys"), dict) else {}
        self._tts_api_key: str = str(config.get("tts_api_key") or tts_api_keys.get("gemini-tts") or "")
        self._tts_voices = self._load_tts_voices()
        self._ensure_tts_voice()

        self._intro_video: str = str(config.get("intro_video") or "")
        self._outro_video: str = str(config.get("outro_video") or "")
        self._merge_output_name: str = str(config.get("merge_output_name") or "")
        self._merge_speech_volume: int = int(config.get("merge_speech_volume") or 100)
        self._merge_background_volume: int = int(config.get("merge_background_volume") or 125)

        self._busy = False
        self._job_dir: str = ""
        self._status_text = ""
        self._progress_value: float = 0
        self._progress_label = "Chưa chạy"
        self._logs: list[str] = []
        self._step_statuses: dict[str, PipelineStepStatus] = {
            step: PipelineStepStatus(step=step, state="pending", message="Chờ chạy") for step in PIPELINE_STEPS
        }
        self._result: Optional[PipelineResult] = None
        self._failed_step: str = ""
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None
        self._normalize_steps_for_source()
        self._restore_last_result()

    def _load_tts_voices(self):
        try:
            return TtsService().list_voices(
                provider=self._tts_provider,
                language=self._tts_language,
                api_key=self._tts_api_key if self._tts_provider == "gemini-tts" else None,
            )
        except Exception:
            return []

    def _ensure_tts_voice(self) -> None:
        if self._tts_voice_id and any(voice.id == self._tts_voice_id for voice in self._tts_voices):
            return
        self._tts_voice_id = self._tts_voices[0].id if self._tts_voices else ""

    def _normalize_steps_for_source(self) -> None:
        steps = set(self._selected_steps)
        if self._source_mode == "url":
            steps.add("download")
        else:
            steps.discard("download")
            if not steps:
                steps.add("split")
        self._selected_steps = [step for step in PIPELINE_STEPS if step in steps]

    def _request_ui_refresh(self) -> None:
        if not self._page:
            return
        try:
            self._page.schedule_update()
        except Exception:
            self._page.update()

    def _first_selected_step(self) -> str:
        return self._selected_steps[0] if self._selected_steps else ""

    def _sync_controls(self) -> None:
        controls = self._controls
        if not controls:
            return

        controls["source_dropdown"].value = self._source_mode
        controls["url_field"].value = self._input_url
        controls["url_field"].visible = self._source_mode == "url"
        controls["local_video_row"].visible = self._source_mode == "local_video"
        controls["local_video_field"].value = self._local_video_path
        controls["workspace_field"].value = self._workspace_root
        controls["job_dir_text"].value = self._job_dir or "Thư mục Job sẽ được tạo khi nhấn bắt đầu."

        for step in PIPELINE_STEPS:
            checkbox = controls[f"step_{step}"]
            checkbox.value = step in self._selected_steps
            checkbox.disabled = self._busy or (step == "download" and self._source_mode in {"url", "local_video"})

        first_step = self._first_selected_step()
        controls["input_override_card"].visible = first_step in {"stt", "translate", "tts", "merge"}
        controls["audio_override_row"].visible = first_step == "stt"
        controls["srt_override_row"].visible = first_step == "translate"
        controls["translated_override_row"].visible = first_step == "tts"
        controls["merge_override_hint"].visible = first_step == "merge"
        controls["merge_override_column"].visible = "merge" in self._selected_steps
        controls["input_audio_field"].value = self._input_audio_path
        controls["input_srt_field"].value = self._input_srt_path
        controls["translated_srt_field"].value = self._translated_srt_path
        controls["merge_muted_field"].value = self._merge_muted_video
        controls["merge_speech_field"].value = self._merge_speech_audio
        controls["merge_background_field"].value = self._merge_background_audio

        controls["download_proxy_checkbox"].value = self._download_use_proxy
        controls["stt_model_dropdown"].value = self._stt_model_size
        controls["stt_language_dropdown"].value = self._stt_language
        controls["stt_speaker_dropdown"].value = self._stt_speaker_mode
        controls["stt_auto_merge_checkbox"].value = self._translate_batch_enabled
        controls["stt_merge_group_field"].value = self._translate_batch_size
        controls["stt_auto_normalize_checkbox"].value = self._stt_auto_normalize_enabled
        controls["translate_model_field"].value = self._translate_model
        controls["translate_api_key_field"].value = self._translate_api_key
        controls["translate_target_dropdown"].value = self._translate_target_language
        controls["translate_safety_checkbox"].value = self._translate_content_safety
        controls["translate_replace_checkbox"].value = self._translate_replace_enabled
        controls["translate_find_field"].value = self._translate_find_text
        controls["translate_replace_field"].value = self._translate_replace_text
        controls["tts_provider_dropdown"].value = self._tts_provider
        controls["tts_language_dropdown"].value = self._tts_language
        controls["tts_voice_dropdown"].options = [
            ft.dropdown.Option(key=voice.id, text=f"{voice.name} ({voice.locale} {voice.gender})")
            for voice in self._tts_voices
        ]
        controls["tts_voice_dropdown"].value = self._tts_voice_id
        controls["tts_api_key_field"].value = self._tts_api_key
        controls["tts_api_key_field"].visible = self._tts_provider == "gemini-tts"
        controls["tts_rate_slider"].value = self._tts_rate
        controls["tts_rate_value"].value = f"{self._tts_rate:+d}%"
        controls["tts_volume_slider"].value = self._tts_volume
        controls["tts_volume_value"].value = f"{self._tts_volume:+d}%"
        controls["tts_pitch_slider"].value = self._tts_pitch
        controls["tts_pitch_value"].value = f"{self._tts_pitch:+d}%"
        controls["tts_keep_segments_checkbox"].value = self._tts_keep_segments
        controls["intro_video_field"].value = self._intro_video
        controls["outro_video_field"].value = self._outro_video
        controls["merge_output_name_field"].value = self._merge_output_name
        controls["merge_speech_slider"].value = self._merge_speech_volume
        controls["merge_speech_value"].value = f"{self._merge_speech_volume}%"
        controls["merge_background_slider"].value = self._merge_background_volume
        controls["merge_background_value"].value = f"{self._merge_background_volume}%"

        controls["progress_bar"].value = self._progress_value
        controls["progress_label"].value = self._progress_label
        controls["status_text"].value = self._status_text
        controls["log_list"].controls = [ft.Text(line, size=12, color=ft.Colors.BLUE_GREY_100, selectable=True) for line in self._logs[-250:]]
        controls["step_list"].controls = self._build_step_rows()
        controls["open_job_button"].visible = bool(self._job_dir)
        controls["start_button"].disabled = self._busy
        controls["retry_button"].visible = self._can_retry()
        controls["retry_button"].disabled = self._busy or not self._can_retry()
        controls["stop_button"].disabled = not self._busy

        for step in PIPELINE_STEPS:
            card = controls.get(f"{step}_config_card")
            badge = controls.get(f"{step}_config_badge")
            if card:
                card.opacity = 1 if step in self._selected_steps else 0.45
            if badge:
                badge.value = "Sẽ chạy" if step in self._selected_steps else "Không chạy"

        for key, control in controls.items():
            if (
                key.startswith("choose_")
                or key.startswith("clear_")
                or key.endswith("_dropdown")
                or key.endswith("_field")
                or key.endswith("_slider")
                or key.endswith("_checkbox")
            ):
                if key not in {"status_text"}:
                    control.disabled = self._busy
        controls["tts_pitch_slider"].disabled = True

    def _build_step_rows(self) -> list[ft.Control]:
        rows: list[ft.Control] = []
        colors = {
            "pending": ft.Colors.BLUE_GREY_400,
            "running": ACCENT,
            "done": ft.Colors.GREEN_400,
            "error": WARN,
            "skipped": ft.Colors.BLUE_GREY_400,
        }
        for step in PIPELINE_STEPS:
            status = self._step_statuses.get(step, PipelineStepStatus(step=step))
            rows.append(
                ft.Container(
                    bgcolor=SURFACE_BG,
                    border_radius=8,
                    padding=10,
                    content=ft.Column(
                        spacing=4,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(STEP_TITLES.get(step, step), width=150, weight=ft.FontWeight.BOLD),
                                    ft.Text(STATUS_LABELS.get(status.state, status.state), width=90, color=colors.get(status.state, ft.Colors.WHITE)),
                                    ft.Text(
                                        "--" if status.percent is None else f"{int(status.percent)}%",
                                        width=52,
                                        color=ft.Colors.BLUE_GREY_100,
                                    ),
                                    ft.Text(status.message or "", expand=True, selectable=True),
                                ]
                            ),
                            ft.Text(status.output_path or status.error_message or "", size=12, color=ft.Colors.BLUE_GREY_200, selectable=True),
                        ],
                    ),
                )
            )
        return rows

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page

        source_dropdown = ft.Dropdown(
            label="Nguồn đầu vào",
            value=self._source_mode,
            width=220,
            bgcolor=SURFACE_BG,
            border_radius=12,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in SOURCE_OPTIONS],
        )
        url_field = ft.TextField(label="URL video", value=self._input_url, border_radius=12, expand=True, bgcolor=SURFACE_BG)
        local_video_field = self._readonly_field("File video gốc", "Chưa chọn video", self._local_video_path)
        workspace_field = self._readonly_field("Workspace", "Thư mục chứa các Job", self._workspace_root)
        choose_local_button = ft.OutlinedButton("Chọn file video gốc", icon=ft.Icons.VIDEO_FILE)
        choose_workspace_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        job_dir_text = ft.Text(self._job_dir or "Thư mục Job sẽ được tạo khi nhấn bắt đầu.", color=ft.Colors.BLUE_GREY_100, selectable=True)

        step_controls = {
            step: ft.Checkbox(label=STEP_TITLES.get(step, step), value=step in self._selected_steps, active_color=ACCENT)
            for step in PIPELINE_STEPS
        }

        download_proxy_checkbox = ft.Checkbox(label="Sử dụng proxy", value=self._download_use_proxy, active_color=ACCENT)

        input_audio_field = self._readonly_field("Âm Thanh Cho STT", "Chọn file vocals/audio", self._input_audio_path)
        input_srt_field = self._readonly_field("SRT Cho Translate", "Chọn transcript .srt", self._input_srt_path)
        translated_srt_field = self._readonly_field("SRT Đã Dịch Cho TTS", "Chọn translated .srt", self._translated_srt_path)
        merge_muted_field = self._readonly_field("Video Đã Tắt Tiếng", "Chọn *_muted.mp4", self._merge_muted_video)
        merge_speech_field = self._readonly_field("Âm Thanh Lồng Tiếng", "Chọn *_speech.mp3", self._merge_speech_audio)
        merge_background_field = self._readonly_field("Âm Thanh Nền", "Không bắt buộc", self._merge_background_audio)

        stt_model_dropdown = self._dropdown("STT Model", self._stt_model_size, [(item, item) for item in STT_MODELS], 160)
        stt_language_dropdown = self._dropdown("Ngôn Ngữ Gốc", self._stt_language, list(STT_LANGUAGES.items()), 180)
        stt_speaker_dropdown = self._dropdown(
            "Số người nói",
            self._stt_speaker_mode,
            [(item, item) for item in SPEAKER_OPTIONS],
            180,
        )
        stt_auto_merge_checkbox = ft.Checkbox(label="Dịch theo batch", value=self._translate_batch_enabled, active_color=ACCENT)
        stt_merge_group_field = ft.TextField(
            label="Số dòng mỗi batch",
            value=self._translate_batch_size,
            width=160,
            border_radius=12,
            bgcolor=SURFACE_BG,
        )
        stt_auto_normalize_checkbox = ft.Checkbox(label="Tự chuẩn hóa text", value=self._stt_auto_normalize_enabled, active_color=ACCENT)
        translate_model_field = ft.TextField(label="Model Dịch", value=self._translate_model, border_radius=12, width=230, bgcolor=SURFACE_BG)
        translate_api_key_field = ft.TextField(
            label="Gemini API Key",
            value=self._translate_api_key,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        translate_target_dropdown = self._dropdown(
            "Ngôn Ngữ Đích",
            self._translate_target_language,
            list(TRANSLATE_LANGUAGES.items()),
            180,
        )
        translate_safety_checkbox = ft.Checkbox(label="Lọc Nội Dung Nhạy Cảm", value=self._translate_content_safety, active_color=ACCENT)
        translate_replace_checkbox = ft.Checkbox(label="Replace sau khi dịch", value=self._translate_replace_enabled, active_color=ACCENT)
        translate_find_field = ft.TextField(
            label="Tìm từ ngữ",
            value=self._translate_find_text,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        translate_replace_field = ft.TextField(
            label="Thay thế bằng",
            value=self._translate_replace_text,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )

        tts_provider_dropdown = self._dropdown("Nhà Cung Cấp TTS", self._tts_provider, TTS_PROVIDERS, 180)
        tts_language_dropdown = self._dropdown("Ngôn Ngữ TTS", self._tts_language, list(TTS_LANGUAGES.items()), 160)
        tts_voice_dropdown = ft.Dropdown(label="Giọng Đọc", value=self._tts_voice_id, options=[], bgcolor=SURFACE_BG, border_radius=12, expand=True)
        tts_api_key_field = ft.TextField(
            label="Gemini TTS API Key",
            value=self._tts_api_key,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self._tts_provider == "gemini-tts",
        )
        tts_rate_value = ft.Text(f"{self._tts_rate:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        tts_volume_value = ft.Text(f"{self._tts_volume:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        tts_pitch_value = ft.Text(f"{self._tts_pitch:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        tts_rate_slider = ft.Slider(min=-50, max=100, divisions=150, value=self._tts_rate, label="{value}%", active_color=ACCENT)
        tts_volume_slider = ft.Slider(min=-50, max=100, divisions=150, value=self._tts_volume, label="{value}%", active_color=ACCENT)
        tts_pitch_slider = ft.Slider(min=-50, max=50, divisions=100, value=self._tts_pitch, label="{value}%", active_color=ACCENT, disabled=True)
        tts_keep_segments_checkbox = ft.Checkbox(label="Giữ segment lẻ", value=self._tts_keep_segments, active_color=ACCENT)

        intro_video_field = self._readonly_field("Video Mở Đầu", "Không bắt buộc", self._intro_video)
        outro_video_field = self._readonly_field("Video Kết Thúc", "Không bắt buộc", self._outro_video)
        merge_output_name_field = ft.TextField(
            label="Tên File Xuất",
            value=self._merge_output_name,
            hint_text="Để trống để dùng <source>_final.mp4",
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        merge_speech_value = ft.Text(f"{self._merge_speech_volume}%", color=ft.Colors.BLUE_GREY_100, width=54)
        merge_background_value = ft.Text(f"{self._merge_background_volume}%", color=ft.Colors.BLUE_GREY_100, width=54)
        merge_speech_slider = ft.Slider(min=0, max=200, divisions=200, value=self._merge_speech_volume, label="{value}%", active_color=ACCENT)
        merge_background_slider = ft.Slider(min=0, max=200, divisions=200, value=self._merge_background_volume, label="{value}%", active_color=ACCENT)

        progress_bar = ft.ProgressBar(value=self._progress_value, color=ACCENT, bgcolor="#2E2E2E")
        progress_label = ft.Text(self._progress_label, color=ft.Colors.BLUE_GREY_100)
        status_text = ft.Text(self._status_text, color=WARN, selectable=True)
        start_button = ft.ElevatedButton("Bắt đầu quy trình", icon=ft.Icons.PLAY_ARROW, bgcolor=ACCENT, color=ft.Colors.BLACK)
        retry_button = ft.OutlinedButton("Chạy lại từ bước lỗi", icon=ft.Icons.RESTART_ALT, visible=self._can_retry())
        stop_button = ft.OutlinedButton("Dừng", icon=ft.Icons.STOP, disabled=True)
        open_job_button = ft.OutlinedButton("Mở thư mục Job", icon=ft.Icons.FOLDER_OPEN, visible=bool(self._job_dir))
        log_list = ft.ListView(spacing=3, height=260, auto_scroll=True)
        step_list = ft.ListView(spacing=8, height=340)

        choose_audio_button = ft.OutlinedButton("Chọn audio", icon=ft.Icons.AUDIO_FILE)
        choose_srt_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        choose_translated_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        choose_merge_muted_button = ft.OutlinedButton("Chọn video", icon=ft.Icons.VIDEO_FILE)
        choose_merge_speech_button = ft.OutlinedButton("Chọn audio", icon=ft.Icons.AUDIO_FILE)
        choose_merge_background_button = ft.OutlinedButton("Chọn nền", icon=ft.Icons.AUDIO_FILE)
        choose_intro_button = ft.OutlinedButton("Chọn intro", icon=ft.Icons.MOVIE)
        clear_intro_button = ft.OutlinedButton("Xóa", icon=ft.Icons.CLOSE)
        choose_outro_button = ft.OutlinedButton("Chọn outro", icon=ft.Icons.MOVIE)
        clear_outro_button = ft.OutlinedButton("Xóa", icon=ft.Icons.CLOSE)

        local_video_row = ft.Row([local_video_field, choose_local_button], spacing=12)
        audio_override_row = ft.Row([input_audio_field, choose_audio_button], spacing=12)
        srt_override_row = ft.Row([input_srt_field, choose_srt_button], spacing=12)
        translated_override_row = ft.Row([translated_srt_field, choose_translated_button], spacing=12)
        merge_override_hint = ft.Text(
            "Input cho bước Gộp Video nằm trong card Cấu hình Gộp Video bên dưới.",
            size=12,
            color=ft.Colors.BLUE_GREY_200,
        )
        merge_override_column = ft.Column(
            spacing=12,
            controls=[
                ft.Text("Input bắt buộc khi bắt đầu/retry từ bước Gộp Video", size=12, color=ft.Colors.BLUE_GREY_200),
                ft.Row([merge_muted_field, choose_merge_muted_button], spacing=12),
                ft.Row([merge_speech_field, choose_merge_speech_button], spacing=12),
                ft.Row([merge_background_field, choose_merge_background_button], spacing=12),
            ],
        )
        input_override_card = ft.Container(
            bgcolor=CARD_BG,
            border_radius=14,
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row([ft.Icon(ft.Icons.INPUT, color=ACCENT), ft.Text("Đầu Vào Khi Chạy Từ Giữa Quy Trình", size=18, weight=ft.FontWeight.BOLD)]),
                    audio_override_row,
                    srt_override_row,
                    translated_override_row,
                    merge_override_hint,
                ],
            ),
        )

        download_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)
        split_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)
        stt_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)
        translate_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)
        tts_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)
        merge_badge = ft.Text("", color=ft.Colors.BLUE_GREY_200)

        download_config_card = self._config_card(
            ft.Icons.DOWNLOAD,
            "Cấu hình Tải File",
            download_badge,
            [
                download_proxy_checkbox,
                ft.Text("URL/source được lấy từ card nguồn đầu vào phía trên.", size=12, color=ft.Colors.BLUE_GREY_200),
            ],
        )
        split_config_card = self._config_card(
            ft.Icons.CALL_SPLIT,
            "Cấu hình Bộ Tách Video",
            split_badge,
            [
                ft.Text("Output: *_muted.mp4, *_vocals.wav, *_background.wav", color=ft.Colors.BLUE_GREY_100),
                ft.Text("Model ONNX đang cố định trong vendor pyvideotrans.", size=12, color=ft.Colors.BLUE_GREY_200),
            ],
        )
        stt_config_card = self._config_card(
            ft.Icons.TRANSCRIBE,
            "Cấu hình Giọng Nói Thành Văn Bản",
            stt_badge,
            [
                ft.Row([stt_model_dropdown, stt_language_dropdown, stt_speaker_dropdown], spacing=12),
                ft.Row([stt_auto_merge_checkbox, stt_merge_group_field, stt_auto_normalize_checkbox], spacing=12),
                ft.Text("Dịch theo batch giúp giảm số request nhưng vẫn giữ timestamp từng dòng để lồng tiếng không lệch.", size=12, color=ft.Colors.BLUE_GREY_200),
            ],
        )
        translate_config_card = self._config_card(
            ft.Icons.TRANSLATE,
            "Cấu hình Dịch Phụ Đề",
            translate_badge,
            [
                ft.Row([translate_model_field, translate_target_dropdown, translate_safety_checkbox], spacing=12),
                ft.Row([translate_api_key_field], spacing=12),
                ft.Row([translate_replace_checkbox, translate_find_field, translate_replace_field], spacing=12),
                ft.Text("Replace sau dịch chỉ sửa state/file SRT đã dịch, không gọi lại AI.", size=12, color=ft.Colors.BLUE_GREY_200),
            ],
        )
        tts_config_card = self._config_card(
            ft.Icons.RECORD_VOICE_OVER,
            "Cấu hình Lồng Tiếng AI",
            tts_badge,
            [
                ft.Row([tts_provider_dropdown, tts_language_dropdown, tts_voice_dropdown], spacing=12),
                ft.Row([tts_api_key_field], spacing=12),
                ft.Row([ft.Text("Tốc độ đọc", width=120), tts_rate_value, tts_rate_slider], spacing=12),
                ft.Text("Tăng/giảm tốc độ đọc. Nếu audio dài hơn subtitle, hệ thống vẫn tự tăng tốc thêm để khớp thời gian.", size=12, color=ft.Colors.BLUE_GREY_200),
                ft.Row([ft.Text("Âm lượng", width=120), tts_volume_value, tts_volume_slider], spacing=12),
                ft.Text("Điều chỉnh âm lượng giọng đọc trước khi gộp file audio tổng.", size=12, color=ft.Colors.BLUE_GREY_200),
                ft.Row([ft.Text("Pitch", width=120), tts_pitch_value, tts_pitch_slider], spacing=12),
                ft.Text("Pitch đang giữ để mở rộng, hiện chưa bật vì provider chưa hỗ trợ ổn định.", size=12, color=ft.Colors.BLUE_GREY_200),
                tts_keep_segments_checkbox,
            ],
        )
        merge_config_card = self._config_card(
            ft.Icons.MERGE_TYPE,
            "Cấu hình Gộp Video",
            merge_badge,
            [
                merge_override_column,
                ft.Text("Nếu workflow không chạy bước Tách Video hoặc bị lỗi ở Merge, hãy chọn thủ công file *_muted.mp4 và *_speech.mp3 tại đây.", size=12, color=ft.Colors.BLUE_GREY_200),
                ft.Row([merge_output_name_field], spacing=12),
                ft.Row([intro_video_field, choose_intro_button, clear_intro_button], spacing=12),
                ft.Row([outro_video_field, choose_outro_button, clear_outro_button], spacing=12),
                ft.Row([ft.Text("Âm lượng lồng tiếng", width=140), merge_speech_value, merge_speech_slider], spacing=12),
                ft.Text("Điều chỉnh độ lớn giọng lồng tiếng trong video cuối.", size=12, color=ft.Colors.BLUE_GREY_200),
                ft.Row([ft.Text("Âm lượng nền", width=140), merge_background_value, merge_background_slider], spacing=12),
                ft.Text("Điều chỉnh độ lớn âm thanh nền trước khi mix với giọng đọc.", size=12, color=ft.Colors.BLUE_GREY_200),
            ],
        )

        self._controls = {
            "source_dropdown": source_dropdown,
            "url_field": url_field,
            "local_video_row": local_video_row,
            "local_video_field": local_video_field,
            "workspace_field": workspace_field,
            "choose_local_button": choose_local_button,
            "choose_workspace_button": choose_workspace_button,
            "job_dir_text": job_dir_text,
            "input_override_card": input_override_card,
            "audio_override_row": audio_override_row,
            "srt_override_row": srt_override_row,
            "translated_override_row": translated_override_row,
            "merge_override_hint": merge_override_hint,
            "merge_override_column": merge_override_column,
            "input_audio_field": input_audio_field,
            "input_srt_field": input_srt_field,
            "translated_srt_field": translated_srt_field,
            "merge_muted_field": merge_muted_field,
            "merge_speech_field": merge_speech_field,
            "merge_background_field": merge_background_field,
            "choose_audio_button": choose_audio_button,
            "choose_srt_button": choose_srt_button,
            "choose_translated_button": choose_translated_button,
            "choose_merge_muted_button": choose_merge_muted_button,
            "choose_merge_speech_button": choose_merge_speech_button,
            "choose_merge_background_button": choose_merge_background_button,
            "download_proxy_checkbox": download_proxy_checkbox,
            "stt_model_dropdown": stt_model_dropdown,
            "stt_language_dropdown": stt_language_dropdown,
            "stt_speaker_dropdown": stt_speaker_dropdown,
            "stt_auto_merge_checkbox": stt_auto_merge_checkbox,
            "stt_merge_group_field": stt_merge_group_field,
            "stt_auto_normalize_checkbox": stt_auto_normalize_checkbox,
            "translate_model_field": translate_model_field,
            "translate_api_key_field": translate_api_key_field,
            "translate_target_dropdown": translate_target_dropdown,
            "translate_safety_checkbox": translate_safety_checkbox,
            "translate_replace_checkbox": translate_replace_checkbox,
            "translate_find_field": translate_find_field,
            "translate_replace_field": translate_replace_field,
            "tts_provider_dropdown": tts_provider_dropdown,
            "tts_language_dropdown": tts_language_dropdown,
            "tts_voice_dropdown": tts_voice_dropdown,
            "tts_api_key_field": tts_api_key_field,
            "tts_rate_slider": tts_rate_slider,
            "tts_rate_value": tts_rate_value,
            "tts_volume_slider": tts_volume_slider,
            "tts_volume_value": tts_volume_value,
            "tts_pitch_slider": tts_pitch_slider,
            "tts_pitch_value": tts_pitch_value,
            "tts_keep_segments_checkbox": tts_keep_segments_checkbox,
            "intro_video_field": intro_video_field,
            "outro_video_field": outro_video_field,
            "merge_output_name_field": merge_output_name_field,
            "choose_intro_button": choose_intro_button,
            "clear_intro_button": clear_intro_button,
            "choose_outro_button": choose_outro_button,
            "clear_outro_button": clear_outro_button,
            "merge_speech_slider": merge_speech_slider,
            "merge_speech_value": merge_speech_value,
            "merge_background_slider": merge_background_slider,
            "merge_background_value": merge_background_value,
            "progress_bar": progress_bar,
            "progress_label": progress_label,
            "status_text": status_text,
            "start_button": start_button,
            "retry_button": retry_button,
            "stop_button": stop_button,
            "open_job_button": open_job_button,
            "log_list": log_list,
            "step_list": step_list,
            "download_config_card": download_config_card,
            "split_config_card": split_config_card,
            "stt_config_card": stt_config_card,
            "translate_config_card": translate_config_card,
            "tts_config_card": tts_config_card,
            "merge_config_card": merge_config_card,
            "download_config_badge": download_badge,
            "split_config_badge": split_badge,
            "stt_config_badge": stt_badge,
            "translate_config_badge": translate_badge,
            "tts_config_badge": tts_badge,
            "merge_config_badge": merge_badge,
        }
        self._controls.update({f"step_{step}": control for step, control in step_controls.items()})

        def request_ui_refresh() -> None:
            self._sync_controls()
            self._request_ui_refresh()

        def choose_file(target: str, title: str, file_filter: str) -> None:
            current = getattr(self, target)
            start_dir = str(Path(current).parent) if current else str(DEFAULT_PIPELINE_WORKSPACE)
            picked = pick_file_native(start_dir, title, file_filter)
            if picked:
                setattr(self, target, picked)
                self._status_text = ""
                request_ui_refresh()

        def reload_tts_voices() -> None:
            self._tts_voices = self._load_tts_voices()
            self._ensure_tts_voice()

        def sync_from_controls() -> None:
            self._source_mode = source_dropdown.value or self._source_mode
            self._input_url = url_field.value or ""
            self._workspace_root = workspace_field.value or self._workspace_root
            self._selected_steps = [step for step in PIPELINE_STEPS if step_controls[step].value]
            self._download_use_proxy = bool(download_proxy_checkbox.value)
            self._stt_model_size = stt_model_dropdown.value or "base"
            self._stt_language = stt_language_dropdown.value or "auto"
            self._stt_speaker_mode = stt_speaker_dropdown.value or SPEAKER_OPTIONS[0]
            self._translate_batch_enabled = bool(stt_auto_merge_checkbox.value)
            self._translate_batch_size = stt_merge_group_field.value or "10"
            self._stt_auto_normalize_enabled = bool(stt_auto_normalize_checkbox.value)
            self._translate_model = translate_model_field.value or DEFAULT_TRANSLATE_MODEL
            self._translate_api_key = translate_api_key_field.value or ""
            self._translate_target_language = translate_target_dropdown.value or "vi"
            self._translate_content_safety = bool(translate_safety_checkbox.value)
            self._translate_replace_enabled = bool(translate_replace_checkbox.value)
            self._translate_find_text = translate_find_field.value or ""
            self._translate_replace_text = translate_replace_field.value or ""
            self._tts_provider = tts_provider_dropdown.value or DEFAULT_TTS_PROVIDER
            self._tts_language = tts_language_dropdown.value or "vi"
            self._tts_voice_id = tts_voice_dropdown.value or self._tts_voice_id
            self._tts_api_key = tts_api_key_field.value or ""
            self._tts_rate = int(tts_rate_slider.value or 0)
            self._tts_volume = int(tts_volume_slider.value or 0)
            self._tts_pitch = int(tts_pitch_slider.value or 0)
            self._tts_keep_segments = bool(tts_keep_segments_checkbox.value)
            self._merge_output_name = merge_output_name_field.value or ""
            self._merge_speech_volume = int(merge_speech_slider.value or 100)
            self._merge_background_volume = int(merge_background_slider.value or 125)
            self._normalize_steps_for_source()

        def build_pipeline_config() -> PipelineConfig:
            sync_from_controls()
            return PipelineConfig(
                source_mode=self._source_mode,
                selected_steps=self._selected_steps,
                workspace_root=self._workspace_root,
                input_url=self._input_url,
                local_video_path=self._local_video_path,
                input_audio_path=self._input_audio_path,
                input_srt_path=self._input_srt_path,
                translated_srt_path=self._translated_srt_path,
                merge_muted_video=self._merge_muted_video,
                merge_speech_audio=self._merge_speech_audio,
                merge_background_audio=self._merge_background_audio,
                download_use_proxy=self._download_use_proxy,
                stt_model_size=self._stt_model_size,
                stt_language=self._stt_language,
                stt_speaker_mode=self._stt_speaker_mode,
                stt_auto_merge_enabled=False,
                stt_merge_group_size=1,
                stt_auto_normalize_enabled=self._stt_auto_normalize_enabled,
                translate_model=self._translate_model,
                translate_api_key=self._translate_api_key,
                translate_target_language=self._translate_target_language,
                translate_content_safety=self._translate_content_safety,
                translate_batch_enabled=self._translate_batch_enabled,
                translate_batch_size=self._positive_int(self._translate_batch_size, 10),
                translate_replace_enabled=self._translate_replace_enabled,
                translate_find_text=self._translate_find_text,
                translate_replace_text=self._translate_replace_text,
                tts_provider=self._tts_provider,
                tts_language=self._tts_language,
                tts_voice_id=self._tts_voice_id,
                tts_rate=self._tts_rate,
                tts_volume=self._tts_volume,
                tts_pitch=self._tts_pitch,
                tts_keep_segments=self._tts_keep_segments,
                tts_api_key=self._tts_api_key,
                intro_video=self._intro_video,
                outro_video=self._outro_video,
                merge_output_name=self._merge_output_name,
                merge_speech_volume=self._merge_speech_volume,
                merge_background_volume=self._merge_background_volume,
            )

        def on_source_change(event: ft.ControlEvent) -> None:
            self._source_mode = event.control.value or "url"
            self._normalize_steps_for_source()
            request_ui_refresh()

        def on_step_change(_: ft.ControlEvent) -> None:
            self._selected_steps = [step for step in PIPELINE_STEPS if step_controls[step].value]
            self._normalize_steps_for_source()
            request_ui_refresh()

        def on_tts_provider_change(event: ft.ControlEvent) -> None:
            self._tts_provider = event.control.value or DEFAULT_TTS_PROVIDER
            reload_tts_voices()
            request_ui_refresh()

        def on_tts_language_change(event: ft.ControlEvent) -> None:
            self._tts_language = event.control.value or "vi"
            reload_tts_voices()
            request_ui_refresh()

        def on_slider_change(_: ft.ControlEvent) -> None:
            sync_from_controls()
            request_ui_refresh()

        def ui_log(message: str) -> None:
            self._logs.append(message)
            request_ui_refresh()

        def ui_progress(progress: PipelineProgress) -> None:
            self._job_dir = progress.context.job_dir
            self._progress_value = max(0, min(1, progress.overall_percent / 100))
            self._progress_label = f"Bước {progress.step_index}/{progress.total_steps}: {STEP_TITLES.get(progress.current_step, progress.current_step)}"
            self._status_text = progress.message
            status = self._step_statuses.get(progress.current_step)
            if status and status.state in {"pending", "running"}:
                status.state = "running"
                status.message = progress.message
                status.percent = progress.step_percent
            request_ui_refresh()

        def ui_step_done(status: PipelineStepStatus) -> None:
            self._step_statuses[status.step] = status
            request_ui_refresh()

        def ui_success(result: PipelineResult) -> None:
            self._busy = False
            self._result = result
            self._failed_step = ""
            self._job_dir = result.job_dir or self._job_dir
            self._progress_value = 1
            self._progress_label = "Quy trình đã hoàn thành"
            self._status_text = f"Đã hoàn tất: {result.final_video or result.job_dir}"
            for status in result.steps:
                self._step_statuses[status.step] = status
            self.service.save_last_result(self._build_visible_result(result))
            request_ui_refresh()
            page.snack_bar = ft.SnackBar(content=ft.Text("Quy trình đã hoàn thành."), bgcolor=ft.Colors.GREEN_700, open=True)
            request_ui_refresh()

        def ui_error(result: PipelineResult) -> None:
            self._busy = False
            self._result = result
            self._failed_step = self._find_failed_step(result)
            self._job_dir = result.job_dir or self._job_dir
            if self._failed_step and result.context:
                self._status_text = (
                    f"{result.error_message or 'Quy trình thất bại.'} "
                    f"Sau khi chỉnh config, có thể chạy lại từ bước {STEP_TITLES.get(self._failed_step, self._failed_step)}."
                )
            else:
                self._status_text = result.error_message or "Quy trình thất bại."
            for status in result.steps:
                self._step_statuses[status.step] = status
            for step in PIPELINE_STEPS:
                current = self._step_statuses.get(step)
                if current and current.state == "pending":
                    current.state = "skipped"
                    current.message = "Đã dừng do quy trình gặp lỗi ở bước trước."
            self.service.save_last_result(self._build_visible_result(result))
            request_ui_refresh()

        def start_pipeline(_: ft.ControlEvent) -> None:
            if self.service.is_processing:
                self._status_text = "Đang có quy trình chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            config = build_pipeline_config()
            self._busy = True
            self._job_dir = ""
            self._progress_value = 0
            self._progress_label = "Đang chuẩn bị..."
            self._status_text = ""
            self._logs = []
            self._result = None
            self._failed_step = ""
            self._step_statuses = {
                step: PipelineStepStatus(
                    step=step,
                    state="pending" if step in config.selected_steps else "skipped",
                    message="Chờ chạy" if step in config.selected_steps else "Không chọn",
                )
                for step in PIPELINE_STEPS
            }
            request_ui_refresh()

            callbacks = PipelineCallbacks(
                on_progress=ui_progress,
                on_step_done=ui_step_done,
                on_log=ui_log,
            )

            def worker() -> None:
                result = self.service.run_job(config=config, callbacks=callbacks)
                if result.ok:
                    ui_success(result)
                else:
                    ui_error(result)

            page.run_thread(worker)

        def retry_pipeline(_: ft.ControlEvent) -> None:
            if self.service.is_processing:
                self._status_text = "Đang có quy trình chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            if not self._can_retry() or not self._result or not self._result.context:
                self._status_text = "Chưa có bước lỗi để chạy lại."
                request_ui_refresh()
                return
            config = build_pipeline_config()
            if self._failed_step not in config.selected_steps:
                self._status_text = "Vui lòng giữ bước lỗi trong danh sách bước để chạy lại."
                request_ui_refresh()
                return

            self._busy = True
            self._progress_value = 0
            self._progress_label = f"Đang chuẩn bị chạy lại từ bước {STEP_TITLES.get(self._failed_step, self._failed_step)}..."
            self._status_text = ""
            self._logs.append(
                f"--- Chạy lại từ bước {STEP_TITLES.get(self._failed_step, self._failed_step)} bằng config mới ---"
            )
            self._mark_retry_steps(config)
            request_ui_refresh()

            callbacks = PipelineCallbacks(
                on_progress=ui_progress,
                on_step_done=ui_step_done,
                on_log=ui_log,
            )
            resume_context = self._result.context
            start_step = self._failed_step

            def worker() -> None:
                result = self.service.run_job(
                    config=config,
                    callbacks=callbacks,
                    resume_context=resume_context,
                    start_step=start_step,
                )
                if result.ok:
                    ui_success(result)
                else:
                    ui_error(result)

            page.run_thread(worker)

        def stop_pipeline(_: ft.ControlEvent) -> None:
            self.service.stop()
            self._status_text = "Đang yêu cầu dừng quy trình..."
            request_ui_refresh()

        def open_job(_: ft.ControlEvent) -> None:
            if self._job_dir:
                open_folder(self._job_dir)

        source_dropdown.on_select = on_source_change
        for checkbox in step_controls.values():
            checkbox.on_change = on_step_change
        choose_local_button.on_click = lambda _: choose_file("_local_video_path", "Chọn file video gốc", VIDEO_FILTER)
        choose_workspace_button.on_click = lambda _: self._choose_workspace(request_ui_refresh)
        choose_audio_button.on_click = lambda _: choose_file("_input_audio_path", "Chọn audio cho STT", AUDIO_FILTER)
        choose_srt_button.on_click = lambda _: choose_file("_input_srt_path", "Chọn SRT cho bước dịch", SRT_FILTER)
        choose_translated_button.on_click = lambda _: choose_file("_translated_srt_path", "Chọn SRT đã dịch cho TTS", SRT_FILTER)
        choose_merge_muted_button.on_click = lambda _: choose_file("_merge_muted_video", "Chọn video đã tắt tiếng", VIDEO_FILTER)
        choose_merge_speech_button.on_click = lambda _: choose_file("_merge_speech_audio", "Chọn âm thanh lồng tiếng", AUDIO_FILTER)
        choose_merge_background_button.on_click = lambda _: choose_file("_merge_background_audio", "Chọn âm thanh nền", AUDIO_FILTER)
        choose_intro_button.on_click = lambda _: choose_file("_intro_video", "Chọn video mở đầu", VIDEO_FILTER)
        clear_intro_button.on_click = lambda _: self._clear_attr("_intro_video", request_ui_refresh)
        choose_outro_button.on_click = lambda _: choose_file("_outro_video", "Chọn video kết thúc", VIDEO_FILTER)
        clear_outro_button.on_click = lambda _: self._clear_attr("_outro_video", request_ui_refresh)
        tts_provider_dropdown.on_select = on_tts_provider_change
        tts_language_dropdown.on_select = on_tts_language_change
        download_proxy_checkbox.on_change = on_slider_change
        stt_speaker_dropdown.on_select = on_slider_change
        stt_auto_merge_checkbox.on_change = on_slider_change
        stt_merge_group_field.on_change = on_slider_change
        stt_auto_normalize_checkbox.on_change = on_slider_change
        translate_safety_checkbox.on_change = on_slider_change
        translate_replace_checkbox.on_change = on_slider_change
        translate_find_field.on_change = on_slider_change
        translate_replace_field.on_change = on_slider_change
        tts_rate_slider.on_change = on_slider_change
        tts_volume_slider.on_change = on_slider_change
        tts_pitch_slider.on_change = on_slider_change
        tts_keep_segments_checkbox.on_change = on_slider_change
        merge_output_name_field.on_change = on_slider_change
        merge_speech_slider.on_change = on_slider_change
        merge_background_slider.on_change = on_slider_change
        start_button.on_click = start_pipeline
        retry_button.on_click = retry_pipeline
        stop_button.on_click = stop_pipeline
        open_job_button.on_click = open_job

        self._sync_controls()

        return ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                spacing=16,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ACCOUNT_TREE, color=ACCENT, size=28),
                            ft.Text("Tự Động Hóa Quy Trình", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([source_dropdown, url_field], spacing=12),
                                local_video_row,
                                ft.Row([workspace_field, choose_workspace_button], spacing=12),
                                job_dir_text,
                            ],
                        ),
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=8,
                            controls=[
                                ft.Row([ft.Icon(ft.Icons.CHECKLIST, color=ACCENT), ft.Text("Các bước", size=18, weight=ft.FontWeight.BOLD)]),
                                ft.Row(list(step_controls.values()), wrap=True),
                            ],
                        ),
                    ),
                    input_override_card,
                    ft.Row([download_config_card, split_config_card], spacing=16),
                    stt_config_card,
                    translate_config_card,
                    tts_config_card,
                    merge_config_card,
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([ft.Icon(ft.Icons.PLAY_CIRCLE, color=ACCENT), ft.Text("Tiến trình tổng", size=18, weight=ft.FontWeight.BOLD)]),
                                progress_bar,
                                progress_label,
                                status_text,
                                ft.Row([start_button, retry_button, stop_button, open_job_button], spacing=12),
                            ],
                        ),
                    ),
                    ft.Row(
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Container(
                                expand=True,
                                bgcolor=CARD_BG,
                                border_radius=14,
                                padding=16,
                                content=ft.Column(
                                    spacing=10,
                                    controls=[
                                        ft.Text("Nhật Ký Thực Thi", size=18, weight=ft.FontWeight.BOLD),
                                        ft.Container(bgcolor="#0E0E0E", border_radius=8, padding=12, content=log_list),
                                    ],
                                ),
                            ),
                            ft.Container(
                                expand=True,
                                bgcolor=CARD_BG,
                                border_radius=14,
                                padding=16,
                                content=ft.Column(
                                    spacing=10,
                                    controls=[
                                        ft.Text("Kết Quả Từng Bước", size=18, weight=ft.FontWeight.BOLD),
                                        step_list,
                                    ],
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _choose_workspace(self, refresh) -> None:
        picked = pick_directory_native(self._workspace_root or str(DEFAULT_PIPELINE_WORKSPACE))
        if picked:
            self._workspace_root = picked
            self._status_text = ""
            refresh()

    def _clear_attr(self, name: str, refresh) -> None:
        setattr(self, name, "")
        self._status_text = ""
        refresh()

    def _restore_last_result(self) -> None:
        result = self.service.load_last_result()
        if not result or not result.job_dir:
            return
        self._result = result
        self._job_dir = result.job_dir
        self._failed_step = self._find_failed_step(result)
        for status in result.steps:
            self._step_statuses[status.step] = status

        if result.ok:
            self._progress_value = 1
            self._progress_label = "Lần chạy gần nhất đã hoàn thành"
            self._status_text = f"Job gần nhất: {result.final_video or result.job_dir}"
        else:
            completed = sum(1 for status in self._step_statuses.values() if status.state == "done")
            selected_count = max(len([step for step in PIPELINE_STEPS if step in self._selected_steps]), 1)
            self._progress_value = max(0, min(1, completed / selected_count))
            if self._failed_step:
                self._progress_label = f"Lần chạy gần nhất lỗi ở bước {STEP_TITLES.get(self._failed_step, self._failed_step)}"
                self._status_text = (
                    f"{result.error_message or 'Quy trình thất bại.'} "
                    "Bạn có thể chỉnh config rồi chạy lại từ bước lỗi."
                )
            else:
                self._progress_label = "Lần chạy gần nhất chưa hoàn thành"
                self._status_text = result.error_message or "Quy trình gần nhất chưa hoàn thành."

    def _build_visible_result(self, base_result: PipelineResult) -> PipelineResult:
        steps = [
            self._step_statuses.get(step, PipelineStepStatus(step=step))
            for step in PIPELINE_STEPS
        ]
        return PipelineResult(
            ok=base_result.ok,
            job_dir=base_result.job_dir or self._job_dir or None,
            context=base_result.context or (self._result.context if self._result else None),
            steps=steps,
            final_video=base_result.final_video,
            error_message=base_result.error_message,
            elapsed_sec=base_result.elapsed_sec,
        )

    def _can_retry(self) -> bool:
        return bool(
            self._result
            and not self._result.ok
            and self._result.context
            and self._failed_step
        )

    @staticmethod
    def _find_failed_step(result: PipelineResult) -> str:
        for status in result.steps:
            if status.state == "error":
                return status.step
        return ""

    def _mark_retry_steps(self, config: PipelineConfig) -> None:
        should_reset = False
        for step in PIPELINE_STEPS:
            status = self._step_statuses.get(step, PipelineStepStatus(step=step))
            if step == self._failed_step:
                should_reset = True
            if step not in config.selected_steps:
                status.state = "skipped"
                status.message = "Không chọn"
                status.percent = None
                status.error_message = None
            elif should_reset:
                status.state = "pending"
                status.message = "Chờ chạy lại"
                status.percent = None
                status.error_message = None
            self._step_statuses[step] = status

    @staticmethod
    def _readonly_field(label: str, hint_text: str, value: str) -> ft.TextField:
        return ft.TextField(
            label=label,
            value=value,
            hint_text=hint_text,
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )

    @staticmethod
    def _config_card(icon: str, title: str, badge: ft.Text, controls: list[ft.Control]) -> ft.Container:
        return ft.Container(
            expand=True,
            bgcolor=CARD_BG,
            border_radius=14,
            padding=16,
            content=ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Row([ft.Icon(icon, color=ACCENT), ft.Text(title, size=18, weight=ft.FontWeight.BOLD)]),
                            badge,
                        ],
                    ),
                    *controls,
                ],
            ),
        )

    @staticmethod
    def _dropdown(label: str, value: str, options: list[tuple[str, str]], width: int) -> ft.Dropdown:
        return ft.Dropdown(
            label=label,
            value=value,
            width=width,
            bgcolor=SURFACE_BG,
            border_radius=12,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in options],
        )

    @staticmethod
    def _positive_int(value: str, default: int) -> int:
        try:
            return max(int(str(value).strip()), 1)
        except (TypeError, ValueError):
            return default
