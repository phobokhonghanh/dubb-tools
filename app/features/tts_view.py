from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.tts_service import TtsCallbacks, TtsService
from utils.tts import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    GeneratedSegment,
    LANGUAGE_OPTIONS,
    TtsProgress,
    TtsResult,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
PROVIDER_OPTIONS = [("edge-tts", "Edge-TTS"), ("gemini-tts", "Gemini TTS")]


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
                "--title=Chọn thư mục lưu audio",
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
    picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu audio", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_srt_file_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Chọn file SRT đã dịch",
                f"--filename={initial_dir.rstrip('/')}/",
                "--file-filter=SRT files | *.srt",
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
    picked, _ = QFileDialog.getOpenFileName(None, "Chọn file SRT đã dịch", initial_dir, "File SRT (*.srt)")
    if owns_app and app:
        app.quit()
    return picked or None


def find_latest_translated_srt(base_dir: str | Path = DEFAULT_TTS_OUTPUT_DIR) -> Optional[Path]:
    directory = Path(base_dir).expanduser()
    if not directory.exists():
        return None
    preferred = [path for path in directory.glob("*_vi.srt") if path.is_file()]
    candidates = preferred or [path for path in directory.glob("*.srt") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


class TtsView(BaseFeatureView):
    feature_id = "text_to_speech"
    title = "Lồng Tiếng AI"
    icon = ft.Icons.RECORD_VOICE_OVER

    def __init__(self) -> None:
        self.service = TtsService()
        config = self.service.load_config()
        self._input_srt: str = ""
        self._output_dir: str = str(DEFAULT_TTS_OUTPUT_DIR)
        self._provider: str = str(config.get("provider") or DEFAULT_TTS_PROVIDER)
        self._language: str = str(config.get("language") or "vi")
        self._voice_ids: dict = dict(config.get("voice_ids") or {})
        self._voice_id: str = str(self._voice_ids.get(self._provider) or "")
        self._rate: int = int(config.get("rate") or 0)
        self._volume: int = int(config.get("volume") or 0)
        self._pitch: int = int(config.get("pitch") or 0)
        self._keep_segments: bool = bool(config.get("keep_segments", True))
        api_keys = config.get("api_keys")
        self._api_keys: dict = dict(api_keys) if isinstance(api_keys, dict) else {}
        self._api_key: str = str(self._api_keys.get("gemini-tts") or "")
        self._voices = self._load_voices()
        self._status_text: str = ""
        self._stage_text: str = "--"
        self._current_file_text: str = "--"
        self._progress_value: Optional[float] = None
        self._progress_visible: bool = False
        self._show_progress_card: bool = False
        self._segments: list[GeneratedSegment] = []
        self._line_count_text: str = "Đã tạo: 0 segment"
        self._busy: bool = False
        self._output_file: Optional[str] = None
        self._open_folder_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None
        self._ensure_voice_selected()

    def _maybe_prefill_latest_srt(self) -> None:
        if self._input_srt:
            return
        latest = find_latest_translated_srt(DEFAULT_TTS_OUTPUT_DIR)
        if latest:
            self._input_srt = str(latest)
            self._current_file_text = latest.name

    def _load_voices(self):
        try:
            voices = self.service.list_voices(
                provider=self._provider,
                language=self._language,
                api_key=self._api_key if self._provider == "gemini-tts" else None,
            )
        except Exception:
            voices = []
        return voices

    def _ensure_voice_selected(self) -> None:
        if self._voice_id and any(voice.id == self._voice_id for voice in self._voices):
            return
        self._voice_id = self._voices[0].id if self._voices else ""
        self._voice_ids[self._provider] = self._voice_id

    def _request_ui_refresh(self) -> None:
        if not self._page:
            return
        try:
            self._page.schedule_update()
        except Exception:
            self._page.update()

    def _build_result_rows(self) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for segment in self._segments:
            raw = "--" if segment.raw_duration_sec is None else f"{segment.raw_duration_sec:.2f}s"
            final = "--" if segment.final_duration_sec is None else f"{segment.final_duration_sec:.2f}s"
            rows.append(
                ft.Container(
                    bgcolor=SURFACE_BG,
                    border_radius=8,
                    padding=10,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Text(str(segment.index), width=34, color=ft.Colors.BLUE_GREY_200),
                            ft.Text(
                                f"[{segment.start_time} - {segment.end_time}]",
                                width=230,
                                color=ACCENT,
                                selectable=True,
                            ),
                            ft.Text(f"mục tiêu {segment.target_duration_sec:.2f}s", width=110),
                            ft.Text(f"gốc {raw}", width=90),
                            ft.Text(f"cuối {final}", width=95),
                            ft.Text(segment.status, expand=True, selectable=True),
                        ],
                    ),
                )
            )
        return rows

    def _sync_controls(self) -> None:
        controls = self._controls
        if not controls:
            return

        controls["input_srt_field"].value = self._input_srt
        controls["output_dir_field"].value = self._output_dir
        controls["provider_dropdown"].value = self._provider
        controls["language_dropdown"].value = self._language
        controls["voice_dropdown"].options = [
            ft.dropdown.Option(key=voice.id, text=f"{voice.name} ({voice.locale} {voice.gender})")
            for voice in self._voices
        ]
        controls["voice_dropdown"].value = self._voice_id
        controls["api_key_field"].value = self._api_key
        controls["api_key_field"].visible = self._provider == "gemini-tts"
        controls["rate_slider"].value = self._rate
        controls["rate_value"].value = f"{self._rate:+d}%"
        controls["volume_slider"].value = self._volume
        controls["volume_value"].value = f"{self._volume:+d}%"
        controls["keep_segments_checkbox"].value = self._keep_segments
        controls["status_text"].value = self._status_text
        controls["stage_text"].value = self._stage_text
        controls["current_file_text"].value = self._current_file_text
        controls["progress_bar"].visible = self._progress_visible
        controls["progress_bar"].value = self._progress_value
        controls["progress_card"].visible = self._show_progress_card
        controls["result_list"].controls = self._build_result_rows()
        controls["line_count_text"].value = self._line_count_text
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in (
            "choose_input_button",
            "choose_output_button",
            "reset_output_button",
            "provider_dropdown",
            "language_dropdown",
            "voice_dropdown",
            "api_key_field",
            "rate_slider",
            "volume_slider",
            "keep_segments_checkbox",
            "start_button",
        ):
            controls[key].disabled = self._busy
        controls["start_button"].text = "Đang xử lý..." if self._busy else "Bắt đầu lồng tiếng"
        controls["start_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.RECORD_VOICE_OVER

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        self._maybe_prefill_latest_srt()

        input_srt_field = ft.TextField(
            label="File SRT Đầu Vào",
            value=self._input_srt,
            hint_text="Chưa chọn file .srt đã dịch",
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        output_dir_field = ft.TextField(
            label="Thư Mục Lưu",
            value=self._output_dir,
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        provider_dropdown = ft.Dropdown(
            label="Nhà Cung Cấp",
            value=self._provider,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in PROVIDER_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=180,
        )
        language_dropdown = ft.Dropdown(
            label="Ngôn Ngữ",
            value=self._language,
            options=[ft.dropdown.Option(key=key, text=value) for key, value in LANGUAGE_OPTIONS.items()],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=160,
        )
        voice_dropdown = ft.Dropdown(
            label="Giọng Đọc",
            value=self._voice_id,
            options=[],
            bgcolor=SURFACE_BG,
            border_radius=12,
            expand=True,
        )
        api_key_field = ft.TextField(
            label="Gemini API Key",
            value=self._api_key,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self._provider == "gemini-tts",
        )
        rate_value = ft.Text(f"{self._rate:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        volume_value = ft.Text(f"{self._volume:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        rate_slider = ft.Slider(min=-50, max=100, divisions=150, value=self._rate, label="{value}%", active_color=ACCENT)
        volume_slider = ft.Slider(min=-50, max=100, divisions=150, value=self._volume, label="{value}%", active_color=ACCENT)
        keep_segments_checkbox = ft.Checkbox(label="Giữ segment lẻ", value=self._keep_segments, active_color=ACCENT)

        status_text = ft.Text(self._status_text, color=WARN, size=13, selectable=True)
        current_file_text = ft.Text(self._current_file_text, color=ft.Colors.WHITE)
        stage_text = ft.Text(self._stage_text, color=ft.Colors.BLUE_GREY_100)
        progress_bar = ft.ProgressBar(
            value=self._progress_value,
            color=ACCENT,
            bgcolor="#2E2E2E",
            visible=self._progress_visible,
        )
        progress_card = ft.Container(
            visible=self._show_progress_card,
            bgcolor=CARD_BG,
            border_radius=14,
            padding=16,
            animate_opacity=250,
            content=ft.Column(
                spacing=10,
                controls=[
                    ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=ft.Colors.BLUE_200), current_file_text]),
                    progress_bar,
                    stage_text,
                    status_text,
                ],
            ),
        )
        result_list = ft.ListView(controls=self._build_result_rows(), spacing=8, height=320)
        line_count_text = ft.Text(self._line_count_text, color=ft.Colors.BLUE_GREY_100)

        choose_input_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        start_button = ft.ElevatedButton(
            "Bắt đầu lồng tiếng",
            icon=ft.Icons.RECORD_VOICE_OVER,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục lưu",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self._open_folder_visible,
        )

        self._controls = {
            "input_srt_field": input_srt_field,
            "output_dir_field": output_dir_field,
            "provider_dropdown": provider_dropdown,
            "language_dropdown": language_dropdown,
            "voice_dropdown": voice_dropdown,
            "api_key_field": api_key_field,
            "rate_slider": rate_slider,
            "rate_value": rate_value,
            "volume_slider": volume_slider,
            "volume_value": volume_value,
            "keep_segments_checkbox": keep_segments_checkbox,
            "status_text": status_text,
            "stage_text": stage_text,
            "current_file_text": current_file_text,
            "progress_bar": progress_bar,
            "progress_card": progress_card,
            "result_list": result_list,
            "line_count_text": line_count_text,
            "choose_input_button": choose_input_button,
            "choose_output_button": choose_output_button,
            "reset_output_button": reset_output_button,
            "start_button": start_button,
            "open_folder_button": open_folder_button,
        }

        def request_ui_refresh() -> None:
            self._sync_controls()
            self._request_ui_refresh()

        def set_busy(busy: bool, refresh: bool = True) -> None:
            self._busy = busy
            if refresh:
                request_ui_refresh()

        def notify(message: str, bgcolor: str = ft.Colors.BLUE_GREY_700) -> None:
            page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=bgcolor, open=True)
            request_ui_refresh()

        def update_line_count() -> None:
            self._line_count_text = f"Đã tạo: {len(self._segments)} segment"

        def reload_voices() -> None:
            self._voices = self._load_voices()
            self._voice_id = self._voice_ids.get(self._provider, "")
            self._ensure_voice_selected()

        def sync_input_values() -> None:
            self._provider = provider_dropdown.value or self._provider
            self._language = language_dropdown.value or self._language
            self._voice_id = voice_dropdown.value or self._voice_id
            self._voice_ids[self._provider] = self._voice_id
            self._api_key = api_key_field.value or ""
            self._api_keys["gemini-tts"] = self._api_key
            self._rate = int(rate_slider.value or 0)
            self._volume = int(volume_slider.value or 0)
            self._keep_segments = bool(keep_segments_checkbox.value)

        def ui_progress(progress: TtsProgress) -> None:
            self._stage_text = progress.message
            self._progress_value = None if progress.percent is None else max(0.0, min(1.0, progress.percent / 100))
            request_ui_refresh()

        def ui_segment_done(segments: list[GeneratedSegment]) -> None:
            self._segments = segments
            update_line_count()
            request_ui_refresh()

        def ui_success(result: TtsResult) -> None:
            set_busy(False, refresh=False)
            self._segments = result.segments
            update_line_count()
            self._stage_text = "Hoàn tất"
            self._progress_value = 1
            self._progress_visible = True
            self._status_text = f"Đã lưu: {result.output_file}"
            self._output_file = result.output_file
            self._open_folder_visible = bool(result.output_file)
            request_ui_refresh()
            notify("Lồng tiếng hoàn tất.", ft.Colors.GREEN_700)

        def ui_error(result: TtsResult) -> None:
            set_busy(False, refresh=False)
            self._segments = result.segments
            update_line_count()
            self._status_text = result.error_message or "Lồng tiếng thất bại."
            request_ui_refresh()

        def choose_input(_: ft.ControlEvent) -> None:
            start_dir = str(Path(self._input_srt).parent) if self._input_srt else str(DEFAULT_TTS_OUTPUT_DIR)
            picked = pick_srt_file_native(start_dir)
            if not picked:
                return
            if Path(picked).suffix.lower() != ".srt":
                self._status_text = "Vui lòng chọn file .srt."
                request_ui_refresh()
                return
            self._input_srt = picked
            self._current_file_text = Path(picked).name
            self._status_text = ""
            request_ui_refresh()

        def choose_output(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self._output_dir or str(DEFAULT_TTS_OUTPUT_DIR))
            if not picked:
                return
            self._output_dir = picked
            self._status_text = ""
            request_ui_refresh()

        def reset_output(_: ft.ControlEvent) -> None:
            self._output_dir = str(DEFAULT_TTS_OUTPUT_DIR)
            self._status_text = ""
            request_ui_refresh()

        def on_provider_change(event: ft.ControlEvent) -> None:
            self._provider = event.control.value or DEFAULT_TTS_PROVIDER
            reload_voices()
            request_ui_refresh()

        def on_language_change(event: ft.ControlEvent) -> None:
            self._language = event.control.value or "vi"
            reload_voices()
            request_ui_refresh()

        def on_voice_change(event: ft.ControlEvent) -> None:
            self._voice_id = event.control.value or self._voice_id
            self._voice_ids[self._provider] = self._voice_id
            request_ui_refresh()

        def on_api_key_change(event: ft.ControlEvent) -> None:
            self._api_key = event.control.value or ""
            self._api_keys["gemini-tts"] = self._api_key

        def on_rate_change(event: ft.ControlEvent) -> None:
            self._rate = int(event.control.value or 0)
            request_ui_refresh()

        def on_volume_change(event: ft.ControlEvent) -> None:
            self._volume = int(event.control.value or 0)
            request_ui_refresh()

        def on_keep_segments_change(event: ft.ControlEvent) -> None:
            self._keep_segments = bool(event.control.value)
            request_ui_refresh()

        def start_tts(_: ft.ControlEvent) -> None:
            sync_input_values()
            if self.service.is_processing:
                self._status_text = "Đang có tác vụ lồng tiếng chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            if not self._input_srt:
                self._status_text = "Vui lòng chọn file .srt đã dịch."
                request_ui_refresh()
                return
            if not self._voice_id:
                self._status_text = "Vui lòng chọn giọng đọc."
                request_ui_refresh()
                return
            if self._provider == "gemini-tts" and not self._api_key.strip():
                self._status_text = "Vui lòng nhập Gemini API key."
                request_ui_refresh()
                return

            self._show_progress_card = True
            self._progress_visible = True
            self._progress_value = None
            self._stage_text = "Đang khởi tạo..."
            self._current_file_text = Path(self._input_srt).name
            self._status_text = ""
            self._segments = []
            update_line_count()
            self._output_file = None
            self._open_folder_visible = False
            set_busy(True)

            callbacks = TtsCallbacks(on_progress=ui_progress, on_segment_done=ui_segment_done)
            input_srt = self._input_srt
            output_dir = self._output_dir
            provider = self._provider
            language = self._language
            voice_id = self._voice_id
            rate = self._rate
            volume = self._volume
            pitch = self._pitch
            keep_segments = self._keep_segments
            api_key = self._api_key

            def worker() -> None:
                try:
                    result = self.service.run_job(
                        input_srt=input_srt,
                        output_dir=output_dir,
                        provider=provider,
                        language=language,
                        voice_id=voice_id,
                        rate=rate,
                        volume=volume,
                        pitch=pitch,
                        keep_segments=keep_segments,
                        api_key=api_key,
                        callbacks=callbacks,
                    )
                    if result.ok:
                        ui_success(result)
                    else:
                        ui_error(result)
                except Exception as exc:
                    ui_error(
                        TtsResult(
                            ok=False,
                            output_file=None,
                            segment_dir=None,
                            segments=[],
                            elapsed_sec=0,
                            error_message=str(exc),
                        )
                    )

            page.run_thread(worker)

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self._output_file:
                open_folder(str(Path(self._output_file).parent))
            else:
                open_folder(self._output_dir)

        choose_input_button.on_click = choose_input
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        provider_dropdown.on_select = on_provider_change
        language_dropdown.on_select = on_language_change
        voice_dropdown.on_select = on_voice_change
        api_key_field.on_change = on_api_key_change
        rate_slider.on_change = on_rate_change
        volume_slider.on_change = on_volume_change
        keep_segments_checkbox.on_change = on_keep_segments_change
        start_button.on_click = start_tts
        open_folder_button.on_click = open_output_folder
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
                            ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ACCENT, size=28),
                            ft.Text("Lồng Tiếng AI", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([provider_dropdown, language_dropdown, voice_dropdown], spacing=12),
                                ft.Row([api_key_field], spacing=12),
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.SPEED, color=ACCENT),
                                        ft.Column(
                                            expand=True,
                                            controls=[
                                                ft.Row([ft.Text("Tốc độ đọc"), rate_value]),
                                                ft.Text(
                                                    "Tăng/giảm tốc độ đọc. Nếu audio dài hơn subtitle, hệ thống vẫn tự tăng tốc thêm để khớp thời gian.",
                                                    size=12,
                                                    color=ft.Colors.BLUE_GREY_200,
                                                ),
                                                rate_slider,
                                            ],
                                        ),
                                    ],
                                    spacing=12,
                                ),
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.VOLUME_UP, color=ACCENT),
                                        ft.Column(
                                            expand=True,
                                            controls=[
                                                ft.Row([ft.Text("Âm lượng"), volume_value]),
                                                ft.Text(
                                                    "Điều chỉnh âm lượng giọng đọc trước khi gộp file audio tổng.",
                                                    size=12,
                                                    color=ft.Colors.BLUE_GREY_200,
                                                ),
                                                volume_slider,
                                            ],
                                        ),
                                    ],
                                    spacing=12,
                                ),
                                keep_segments_checkbox,
                            ],
                        ),
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([input_srt_field, choose_input_button], spacing=12),
                                ft.Row([output_dir_field, choose_output_button, reset_output_button], spacing=12),
                                ft.Row([start_button, open_folder_button], spacing=12),
                            ],
                        ),
                    ),
                    progress_card,
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.AUDIO_FILE, color=ft.Colors.BLUE_200),
                                        ft.Text("Segment Âm Thanh", size=18, weight=ft.FontWeight.BOLD),
                                        ft.Container(expand=True),
                                        line_count_text,
                                    ]
                                ),
                                result_list,
                                status_text,
                            ],
                        ),
                    ),
                ],
            ),
        )
