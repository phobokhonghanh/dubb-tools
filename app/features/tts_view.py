from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.presenter.tts_presenter import TtsPresenter
from infrastructure.providers.tts import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    GeneratedSegment,
    LANGUAGE_OPTIONS,
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
        # Gọi trực tiếp qua subprocess.run thay vì run_process để tránh đăng ký vào ProcessManager.
        # Điều này ngăn việc tiến trình hộp thoại GUI tương tác bị tắt nhầm khi bấm "Hủy tất cả".
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
        # Gọi trực tiếp qua subprocess.run thay vì run_process để tránh đăng ký vào ProcessManager.
        # Điều này ngăn việc tiến trình hộp thoại GUI tương tác bị tắt nhầm khi bấm "Hủy tất cả".
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


class TtsView(BaseFeatureView):
    feature_id = "text_to_speech"
    title = "Lồng Tiếng AI"
    icon = ft.Icons.RECORD_VOICE_OVER

    def __init__(self) -> None:
        self.presenter = TtsPresenter(self)
        self.input_srt: str = ""
        self.output_dir: str = str(DEFAULT_TTS_OUTPUT_DIR)
        self.provider: str = ""
        self.language: str = ""
        self.voice_ids: dict = {}
        self.voice_id: str = ""
        self.rate: int = 0
        self.volume: int = 0
        self.pitch: int = 0
        self.keep_segments: bool = True
        self.auto_merge: bool = True
        self.max_workers: int = 5
        self.api_keys: dict = {}
        self.api_key: str = ""
        self.voices: list = []
        self.status_text: str = ""
        self.stage_text: str = "--"
        self.current_file_text: str = "--"
        self.progress_value: Optional[float] = None
        self.progress_visible: bool = False
        self.show_progress_card: bool = False
        self.segments: list[GeneratedSegment] = []
        self.line_count_text: str = "Đã tạo: 0 segment"
        self.busy: bool = False
        self.output_file: Optional[str] = None
        self.open_folder_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None
        
        self.presenter.init_presenter()

    def refresh(self) -> None:
        self._sync_controls()
        self._request_ui_refresh()

    def dispose(self) -> None:
        """Dọn dẹp tài nguyên âm thanh khi đóng view."""
        if self._page and hasattr(self, "_audio_player") and self._audio_player:
            if self._audio_player in self._page.overlay:
                self._page.overlay.remove(self._audio_player)
            self._audio_player = None
            self._request_ui_refresh()

    def notify(self, message: str, bgcolor: str = ft.Colors.BLUE_GREY_700) -> None:
        if self._page:
            self._page.snack_bar = ft.SnackBar(content=ft.Text(message), bgcolor=bgcolor, open=True)
            self._request_ui_refresh()

    def run_in_thread(self, target: Callable[[], None]) -> None:
        if self._page:
            self._page.run_thread(target)

    def _request_ui_refresh(self) -> None:
        if not self._page:
            return
        try:
            self._page.schedule_update()
        except Exception:
            self._page.update()

    def _play_audio(self, path: str) -> None:
        if not self._page:
            return
        if not hasattr(self, "_audio_player") or self._audio_player is None:
            try:
                import flet_audio as fta
                self._audio_player = fta.Audio(src=path, autoplay=True)
            except ImportError:
                self._audio_player = ft.Audio(src=path, autoplay=True)
            self._page.overlay.append(self._audio_player)
            self._page.update()
        else:
            self._audio_player.src = path
            self._audio_player.update()
            self._audio_player.play()

    def _build_result_rows(self) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for segment in self.segments:
            raw = "--" if segment.raw_duration_sec is None else f"{segment.raw_duration_sec:.2f}s"
            final = "--" if segment.final_duration_sec is None else f"{segment.final_duration_sec:.2f}s"
            
            # Nút nghe thử phân đoạn
            play_btn = None
            if segment.file_path and os.path.exists(segment.file_path):
                play_btn = ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    icon_color=ACCENT,
                    icon_size=20,
                    tooltip="Nghe thử phân đoạn này",
                    on_click=lambda e, path=segment.file_path: self._play_audio(path),
                )
            else:
                play_btn = ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    icon_color=ft.Colors.BLUE_GREY_700,
                    icon_size=20,
                    disabled=True,
                )

            rows.append(
                ft.Container(
                    bgcolor=SURFACE_BG,
                    border_radius=8,
                    padding=5,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            play_btn,
                            ft.Text(str(segment.index), width=34, color=ft.Colors.BLUE_GREY_200),
                            ft.Text(
                                f"[{segment.start_time} - {segment.end_time}]",
                                width=200,
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

        controls["input_srt_field"].value = self.input_srt
        controls["output_dir_field"].value = self.output_dir
        controls["provider_dropdown"].value = self.provider
        controls["language_dropdown"].value = self.language
        controls["voice_dropdown"].options = [
            ft.dropdown.Option(key=voice.id, text=f"{voice.name} ({voice.locale} {voice.gender})")
            for voice in self.voices
        ]
        controls["voice_dropdown"].value = self.voice_id
        controls["api_key_field"].value = self.api_key
        controls["api_key_field"].visible = self.provider == "gemini-tts"
        controls["rate_slider"].value = self.rate
        controls["rate_value"].value = f"{self.rate:+d}%"
        controls["volume_slider"].value = self.volume
        controls["volume_value"].value = f"{self.volume:+d}%"
        controls["max_workers_slider"].value = self.max_workers
        controls["max_workers_value"].value = f"{self.max_workers} luồng"
        controls["keep_segments_checkbox"].value = self.keep_segments
        controls["keep_segments_checkbox"].disabled = self.busy or not self.auto_merge
        controls["auto_merge_checkbox"].value = self.auto_merge
        controls["auto_merge_checkbox"].disabled = self.busy
        controls["merge_button"].disabled = self.busy or not self.segments
        controls["status_text"].value = self.status_text
        controls["stage_text"].value = self.stage_text
        controls["current_file_text"].value = self.current_file_text
        controls["progress_bar"].visible = self.progress_visible
        controls["progress_bar"].value = self.progress_value
        controls["progress_card"].visible = self.show_progress_card
        controls["result_list"].controls = self._build_result_rows()
        controls["line_count_text"].value = self.line_count_text
        controls["open_folder_button"].visible = self.open_folder_visible

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
            "max_workers_slider",
            "keep_segments_checkbox",
            "auto_merge_checkbox",
            "start_button",
            "merge_button",
        ):
            controls[key].disabled = self.busy
        controls["start_button"].text = "Đang xử lý..." if self.busy else "Bắt đầu lồng tiếng"
        controls["start_button"].icon = ft.Icons.HOURGLASS_TOP if self.busy else ft.Icons.RECORD_VOICE_OVER

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        self.presenter.maybe_prefill_latest_srt()

        input_srt_field = ft.TextField(
            label="File SRT Đầu Vào",
            value=self.input_srt,
            hint_text="Chưa chọn file .srt đã dịch",
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        output_dir_field = ft.TextField(
            label="Thư Mục Lưu",
            value=self.output_dir,
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        provider_dropdown = ft.Dropdown(
            label="Nhà Cung Cấp",
            value=self.provider,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in PROVIDER_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=180,
        )
        language_dropdown = ft.Dropdown(
            label="Ngôn Ngữ",
            value=self.language,
            options=[ft.dropdown.Option(key=key, text=value) for key, value in LANGUAGE_OPTIONS.items()],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=160,
        )
        voice_dropdown = ft.Dropdown(
            label="Giọng Đọc",
            value=self.voice_id,
            options=[],
            bgcolor=SURFACE_BG,
            border_radius=12,
            expand=True,
        )
        api_key_field = ft.TextField(
            label="Gemini API Key",
            value=self.api_key,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self.provider == "gemini-tts",
        )
        rate_value = ft.Text(f"{self.rate:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        volume_value = ft.Text(f"{self.volume:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        max_workers_value = ft.Text(f"{self.max_workers} luồng", color=ft.Colors.BLUE_GREY_100, width=58)
        rate_slider = ft.Slider(min=-50, max=100, divisions=150, value=self.rate, label="{value}%", active_color=ACCENT)
        volume_slider = ft.Slider(min=-50, max=100, divisions=150, value=self.volume, label="{value}%", active_color=ACCENT)
        max_workers_slider = ft.Slider(min=1, max=10, divisions=9, value=self.max_workers, label="{value} luồng", active_color=ACCENT)
        keep_segments_checkbox = ft.Checkbox(label="Giữ segment lẻ", value=self.keep_segments, active_color=ACCENT)
        auto_merge_checkbox = ft.Checkbox(label="Tự động gộp âm thanh", value=self.auto_merge, active_color=ACCENT)

        status_text = ft.Text(self.status_text, color=WARN, size=13, selectable=True)
        current_file_text = ft.Text(self.current_file_text, color=ft.Colors.WHITE)
        stage_text = ft.Text(self.stage_text, color=ft.Colors.BLUE_GREY_100)
        progress_bar = ft.ProgressBar(
            value=self.progress_value,
            color=ACCENT,
            bgcolor="#2E2E2E",
            visible=self.progress_visible,
        )
        progress_card = ft.Container(
            visible=self.show_progress_card,
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
        line_count_text = ft.Text(self.line_count_text, color=ft.Colors.BLUE_GREY_100)

        choose_input_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        start_button = ft.ElevatedButton(
            "Bắt đầu lồng tiếng",
            icon=ft.Icons.RECORD_VOICE_OVER,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        merge_button = ft.ElevatedButton(
            "Gộp âm thanh",
            icon=ft.Icons.CALL_MERGE,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục lưu",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self.open_folder_visible,
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
            "max_workers_slider": max_workers_slider,
            "max_workers_value": max_workers_value,
            "keep_segments_checkbox": keep_segments_checkbox,
            "auto_merge_checkbox": auto_merge_checkbox,
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
            "merge_button": merge_button,
            "open_folder_button": open_folder_button,
        }

        def choose_input(_: ft.ControlEvent) -> None:
            start_dir = str(Path(self.input_srt).parent) if self.input_srt else str(DEFAULT_TTS_OUTPUT_DIR)
            picked = pick_srt_file_native(start_dir)
            if picked:
                self.presenter.handle_srt_selected(picked)

        def choose_output(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self.output_dir or str(DEFAULT_TTS_OUTPUT_DIR))
            if picked:
                self.presenter.handle_output_dir_selected(picked)

        def reset_output(_: ft.ControlEvent) -> None:
            self.presenter.handle_reset_output_dir()

        def on_provider_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_provider_change(event.control.value or DEFAULT_TTS_PROVIDER)

        def on_language_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_language_change(event.control.value or "vi")

        def on_voice_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_voice_change(event.control.value or "")

        def on_api_key_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_api_key_change(event.control.value or "")

        def on_rate_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_rate_change(int(event.control.value or 0))

        def on_volume_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_volume_change(int(event.control.value or 0))

        def on_max_workers_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_max_workers_change(int(event.control.value or 5))

        def on_keep_segments_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_keep_segments_change(bool(event.control.value))

        def on_auto_merge_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_auto_merge_change(bool(event.control.value))

        def start_tts(_: ft.ControlEvent) -> None:
            self.provider = provider_dropdown.value or self.provider
            self.language = language_dropdown.value or self.language
            self.voice_id = voice_dropdown.value or self.voice_id
            self.api_key = api_key_field.value or ""
            self.rate = int(rate_slider.value or 0)
            self.volume = int(volume_slider.value or 0)
            self.max_workers = int(max_workers_slider.value or 5)
            self.auto_merge = bool(auto_merge_checkbox.value)
            self.keep_segments = bool(keep_segments_checkbox.value)
            self.presenter.start_tts()

        def merge_audio_action(_: ft.ControlEvent) -> None:
            self.presenter.merge_audio()

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self.output_file:
                open_folder(str(Path(self.output_file).parent))
            else:
                open_folder(self.output_dir)

        choose_input_button.on_click = choose_input
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        provider_dropdown.on_select = on_provider_change
        language_dropdown.on_select = on_language_change
        voice_dropdown.on_select = on_voice_change
        api_key_field.on_change = on_api_key_change
        rate_slider.on_change = on_rate_change
        volume_slider.on_change = on_volume_change
        max_workers_slider.on_change = on_max_workers_change
        keep_segments_checkbox.on_change = on_keep_segments_change
        auto_merge_checkbox.on_change = on_auto_merge_change
        start_button.on_click = start_tts
        merge_button.on_click = merge_audio_action
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
                                                    expand=True,
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
                                                    expand=True,
                                                ),
                                                volume_slider,
                                            ],
                                        ),
                                    ],
                                    spacing=12,
                                ),
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.DENSITY_MEDIUM, color=ACCENT),
                                        ft.Column(
                                            expand=True,
                                            controls=[
                                                ft.Row([ft.Text("Số luồng xử lý song song"), max_workers_value]),
                                                ft.Text(
                                                    "Tăng số luồng để tạo audio song song nhanh hơn. Khuyên dùng từ 3 - 5 luồng.",
                                                    size=12,
                                                    color=ft.Colors.BLUE_GREY_200,
                                                    expand=True,
                                                ),
                                                max_workers_slider,
                                            ],
                                        ),
                                    ],
                                    spacing=12,
                                ),
                                ft.Row(
                                    [
                                        auto_merge_checkbox,
                                        keep_segments_checkbox,
                                    ],
                                    spacing=24,
                                ),
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
                                ft.Row([start_button, merge_button, open_folder_button], spacing=12),
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
