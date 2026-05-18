from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.merger_service import MergerCallbacks, MergerService
from utils.video_merger import (
    DEFAULT_PROCESS_DIR,
    MergeProgress,
    MergeResult,
    default_output_name,
    find_latest_merge_inputs,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
VIDEO_FILTER = "File video | *.mp4 *.mov *.mkv *.avi *.webm"
AUDIO_FILTER = "File âm thanh | *.mp3 *.wav *.m4a *.aac *.flac *.ogg"


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
                "--title=Chọn thư mục lưu video final",
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
    picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu video final", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_file_native(initial_dir: str, title: str, file_filter: str) -> Optional[str]:
    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                f"--title={title}",
                f"--filename={initial_dir.rstrip('/')}/",
                f"--file-filter={file_filter}",
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
    picked, _ = QFileDialog.getOpenFileName(None, title, initial_dir, file_filter.replace(" | ", " (") + ")")
    if owns_app and app:
        app.quit()
    return picked or None


class MergerView(BaseFeatureView):
    feature_id = "merge_video"
    title = "Gộp Video"
    icon = ft.Icons.MOVIE_FILTER

    def __init__(self) -> None:
        self.service = MergerService()
        config = self.service.load_config()
        suggestion = find_latest_merge_inputs(DEFAULT_PROCESS_DIR)

        self._main_video: str = self._existing_or_default(config.get("main_video"), suggestion.main_video)
        self._speech_audio: str = self._existing_or_default(config.get("speech_audio"), suggestion.speech_audio)
        self._background_audio: str = self._existing_or_default(
            config.get("background_audio"), suggestion.background_audio
        )
        self._intro_video: str = self._existing_or_default(config.get("intro_video"), "")
        self._outro_video: str = self._existing_or_default(config.get("outro_video"), "")
        self._output_dir: str = str(config.get("output_dir") or DEFAULT_PROCESS_DIR)
        self._output_name: str = str(config.get("output_name") or "")
        if self._main_video and not self._output_name:
            self._output_name = default_output_name(self._main_video)

        self._speech_volume: int = int(config.get("speech_volume") or 100)
        self._background_volume: int = int(config.get("background_volume") or 125)
        self._status_text: str = ""
        self._stage_text: str = "--"
        self._current_file_text: str = "--"
        self._progress_value: Optional[float] = None
        self._progress_visible: bool = False
        self._show_progress_card: bool = False
        self._busy: bool = False
        self._output_file: Optional[str] = None
        self._open_folder_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None

    @staticmethod
    def _existing_or_default(primary: object, fallback: object) -> str:
        value = str(primary or "")
        if value and Path(value).expanduser().exists():
            return value
        fallback_value = str(fallback or "")
        if fallback_value and Path(fallback_value).expanduser().exists():
            return fallback_value
        return ""

    def _request_ui_refresh(self) -> None:
        if not self._page:
            return
        try:
            self._page.schedule_update()
        except Exception:
            self._page.update()

    def _sync_controls(self) -> None:
        controls = self._controls
        if not controls:
            return

        controls["main_video_field"].value = self._main_video
        controls["speech_audio_field"].value = self._speech_audio
        controls["background_audio_field"].value = self._background_audio
        controls["intro_video_field"].value = self._intro_video
        controls["outro_video_field"].value = self._outro_video
        controls["output_dir_field"].value = self._output_dir
        controls["output_name_field"].value = self._output_name
        controls["speech_slider"].value = self._speech_volume
        controls["speech_value"].value = f"{self._speech_volume}%"
        controls["background_slider"].value = self._background_volume
        controls["background_value"].value = f"{self._background_volume}%"
        controls["status_text"].value = self._status_text
        controls["stage_text"].value = self._stage_text
        controls["current_file_text"].value = self._current_file_text
        controls["progress_bar"].visible = self._progress_visible
        controls["progress_bar"].value = self._progress_value
        controls["progress_card"].visible = self._show_progress_card
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in (
            "choose_main_button",
            "choose_speech_button",
            "choose_background_button",
            "clear_background_button",
            "choose_intro_button",
            "clear_intro_button",
            "choose_outro_button",
            "clear_outro_button",
            "choose_output_button",
            "reset_output_button",
            "output_name_field",
            "speech_slider",
            "background_slider",
            "start_button",
        ):
            controls[key].disabled = self._busy
        controls["start_button"].text = "Đang xử lý..." if self._busy else "Bắt đầu gộp"
        controls["start_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.MERGE

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page

        main_video_field = self._readonly_field("Video Chính", "Chọn file *_muted.mp4", self._main_video)
        speech_audio_field = self._readonly_field("Âm Thanh Lồng Tiếng", "Chọn file *_speech.mp3", self._speech_audio)
        background_audio_field = self._readonly_field(
            "Âm Thanh Nền", "Không bắt buộc, ví dụ *_background.wav", self._background_audio
        )
        intro_video_field = self._readonly_field("Video Mở Đầu", "Không bắt buộc", self._intro_video)
        outro_video_field = self._readonly_field("Video Kết Thúc", "Không bắt buộc", self._outro_video)
        output_dir_field = self._readonly_field("Thư Mục Lưu", "Thư mục lưu video final", self._output_dir)
        output_name_field = ft.TextField(
            label="Tên File Xuất",
            value=self._output_name,
            hint_text="video_final.mp4",
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )

        speech_value = ft.Text(f"{self._speech_volume}%", color=ft.Colors.BLUE_GREY_100, width=54)
        background_value = ft.Text(f"{self._background_volume}%", color=ft.Colors.BLUE_GREY_100, width=54)
        speech_slider = ft.Slider(
            min=0,
            max=200,
            divisions=200,
            value=self._speech_volume,
            label="{value}%",
            active_color=ACCENT,
        )
        background_slider = ft.Slider(
            min=0,
            max=200,
            divisions=200,
            value=self._background_volume,
            label="{value}%",
            active_color=ACCENT,
        )

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
                    ft.Row([ft.Icon(ft.Icons.MOVIE, color=ft.Colors.BLUE_200), current_file_text]),
                    progress_bar,
                    stage_text,
                    status_text,
                ],
            ),
        )

        choose_main_button = ft.OutlinedButton("Chọn video", icon=ft.Icons.VIDEO_FILE)
        choose_speech_button = ft.OutlinedButton("Chọn audio", icon=ft.Icons.AUDIO_FILE)
        choose_background_button = ft.OutlinedButton("Chọn nền", icon=ft.Icons.AUDIO_FILE)
        clear_background_button = ft.OutlinedButton("Xóa", icon=ft.Icons.CLOSE)
        choose_intro_button = ft.OutlinedButton("Chọn intro", icon=ft.Icons.MOVIE)
        clear_intro_button = ft.OutlinedButton("Xóa", icon=ft.Icons.CLOSE)
        choose_outro_button = ft.OutlinedButton("Chọn outro", icon=ft.Icons.MOVIE)
        clear_outro_button = ft.OutlinedButton("Xóa", icon=ft.Icons.CLOSE)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        start_button = ft.ElevatedButton("Bắt đầu gộp", icon=ft.Icons.MERGE, bgcolor=ACCENT, color=ft.Colors.BLACK)
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục lưu",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self._open_folder_visible,
        )

        self._controls = {
            "main_video_field": main_video_field,
            "speech_audio_field": speech_audio_field,
            "background_audio_field": background_audio_field,
            "intro_video_field": intro_video_field,
            "outro_video_field": outro_video_field,
            "output_dir_field": output_dir_field,
            "output_name_field": output_name_field,
            "speech_slider": speech_slider,
            "speech_value": speech_value,
            "background_slider": background_slider,
            "background_value": background_value,
            "status_text": status_text,
            "stage_text": stage_text,
            "current_file_text": current_file_text,
            "progress_bar": progress_bar,
            "progress_card": progress_card,
            "choose_main_button": choose_main_button,
            "choose_speech_button": choose_speech_button,
            "choose_background_button": choose_background_button,
            "clear_background_button": clear_background_button,
            "choose_intro_button": choose_intro_button,
            "clear_intro_button": clear_intro_button,
            "choose_outro_button": choose_outro_button,
            "clear_outro_button": clear_outro_button,
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

        def pick_video(current: str, title: str) -> Optional[str]:
            start_dir = str(Path(current).parent) if current else str(DEFAULT_PROCESS_DIR)
            return pick_file_native(start_dir, title, VIDEO_FILTER)

        def pick_audio(current: str, title: str) -> Optional[str]:
            start_dir = str(Path(current).parent) if current else str(DEFAULT_PROCESS_DIR)
            return pick_file_native(start_dir, title, AUDIO_FILTER)

        def choose_main(_: ft.ControlEvent) -> None:
            picked = pick_video(self._main_video, "Chọn video chính")
            if not picked:
                return
            self._main_video = picked
            self._output_name = default_output_name(picked)
            self._status_text = ""
            request_ui_refresh()

        def choose_speech(_: ft.ControlEvent) -> None:
            picked = pick_audio(self._speech_audio, "Chọn âm thanh lồng tiếng")
            if not picked:
                return
            self._speech_audio = picked
            self._status_text = ""
            request_ui_refresh()

        def choose_background(_: ft.ControlEvent) -> None:
            picked = pick_audio(self._background_audio, "Chọn âm thanh nền")
            if not picked:
                return
            self._background_audio = picked
            self._status_text = ""
            request_ui_refresh()

        def clear_background(_: ft.ControlEvent) -> None:
            self._background_audio = ""
            self._status_text = ""
            request_ui_refresh()

        def choose_intro(_: ft.ControlEvent) -> None:
            picked = pick_video(self._intro_video, "Chọn video mở đầu")
            if not picked:
                return
            self._intro_video = picked
            self._status_text = ""
            request_ui_refresh()

        def clear_intro(_: ft.ControlEvent) -> None:
            self._intro_video = ""
            self._status_text = ""
            request_ui_refresh()

        def choose_outro(_: ft.ControlEvent) -> None:
            picked = pick_video(self._outro_video, "Chọn video kết thúc")
            if not picked:
                return
            self._outro_video = picked
            self._status_text = ""
            request_ui_refresh()

        def clear_outro(_: ft.ControlEvent) -> None:
            self._outro_video = ""
            self._status_text = ""
            request_ui_refresh()

        def choose_output(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self._output_dir or str(DEFAULT_PROCESS_DIR))
            if not picked:
                return
            self._output_dir = picked
            self._status_text = ""
            request_ui_refresh()

        def reset_output(_: ft.ControlEvent) -> None:
            self._output_dir = str(DEFAULT_PROCESS_DIR)
            self._status_text = ""
            request_ui_refresh()

        def on_output_name_change(event: ft.ControlEvent) -> None:
            self._output_name = event.control.value or ""

        def on_speech_volume_change(event: ft.ControlEvent) -> None:
            self._speech_volume = int(event.control.value or 0)
            request_ui_refresh()

        def on_background_volume_change(event: ft.ControlEvent) -> None:
            self._background_volume = int(event.control.value or 0)
            request_ui_refresh()

        def ui_progress(progress: MergeProgress) -> None:
            self._stage_text = progress.message
            self._progress_value = None if progress.percent is None else max(0.0, min(1.0, progress.percent / 100))
            request_ui_refresh()

        def ui_success(result: MergeResult) -> None:
            set_busy(False, refresh=False)
            self._stage_text = "Hoàn tất"
            self._progress_value = 1
            self._progress_visible = True
            self._status_text = f"Đã lưu: {result.output_file}"
            self._output_file = result.output_file
            self._open_folder_visible = bool(result.output_file)
            request_ui_refresh()
            notify("Gộp video hoàn tất.", ft.Colors.GREEN_700)

        def ui_error(result: MergeResult) -> None:
            set_busy(False, refresh=False)
            self._status_text = result.error_message or "Gộp video thất bại."
            request_ui_refresh()

        def start_merge(_: ft.ControlEvent) -> None:
            self._output_name = output_name_field.value or self._output_name
            if self.service.is_processing:
                self._status_text = "Đang có tác vụ gộp video chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            if not self._main_video:
                self._status_text = "Vui lòng chọn video chính."
                request_ui_refresh()
                return
            if not self._speech_audio:
                self._status_text = "Vui lòng chọn âm thanh lồng tiếng."
                request_ui_refresh()
                return
            if not self._output_name:
                self._output_name = default_output_name(self._main_video)

            self._show_progress_card = True
            self._progress_visible = True
            self._progress_value = None
            self._stage_text = "Đang kiểm tra định dạng..."
            self._current_file_text = Path(self._main_video).name
            self._status_text = ""
            self._output_file = None
            self._open_folder_visible = False
            set_busy(True)

            callbacks = MergerCallbacks(on_progress=ui_progress)
            main_video = self._main_video
            speech_audio = self._speech_audio
            background_audio = self._background_audio
            intro_video = self._intro_video
            outro_video = self._outro_video
            output_dir = self._output_dir
            output_name = self._output_name
            speech_volume = self._speech_volume / 100
            background_volume = self._background_volume / 100

            def worker() -> None:
                result = self.service.run_job(
                    main_video=main_video,
                    speech_audio=speech_audio,
                    background_audio=background_audio,
                    intro_video=intro_video,
                    outro_video=outro_video,
                    output_dir=output_dir,
                    output_name=output_name,
                    speech_volume=speech_volume,
                    background_volume=background_volume,
                    callbacks=callbacks,
                )
                if result.ok:
                    ui_success(result)
                else:
                    ui_error(result)

            page.run_thread(worker)

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self._output_file:
                open_folder(str(Path(self._output_file).parent))
            else:
                open_folder(self._output_dir)

        choose_main_button.on_click = choose_main
        choose_speech_button.on_click = choose_speech
        choose_background_button.on_click = choose_background
        clear_background_button.on_click = clear_background
        choose_intro_button.on_click = choose_intro
        clear_intro_button.on_click = clear_intro
        choose_outro_button.on_click = choose_outro
        clear_outro_button.on_click = clear_outro
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        output_name_field.on_change = on_output_name_change
        speech_slider.on_change = on_speech_volume_change
        background_slider.on_change = on_background_volume_change
        start_button.on_click = start_merge
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
                            ft.Icon(ft.Icons.MOVIE_FILTER, color=ACCENT, size=28),
                            ft.Text("Gộp Video", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([main_video_field, choose_main_button], spacing=12),
                                ft.Row([speech_audio_field, choose_speech_button], spacing=12),
                                ft.Row(
                                    [background_audio_field, choose_background_button, clear_background_button],
                                    spacing=12,
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
                                ft.Row([intro_video_field, choose_intro_button, clear_intro_button], spacing=12),
                                ft.Row([outro_video_field, choose_outro_button, clear_outro_button], spacing=12),
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
                                ft.Row([output_dir_field, choose_output_button, reset_output_button], spacing=12),
                                ft.Row([output_name_field], spacing=12),
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
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.RECORD_VOICE_OVER, color=ACCENT),
                                        ft.Column(
                                            expand=True,
                                            controls=[
                                                ft.Row([ft.Text("Âm lượng lồng tiếng"), speech_value]),
                                                ft.Text(
                                                    "Điều chỉnh độ lớn giọng lồng tiếng trong video cuối.",
                                                    size=12,
                                                    color=ft.Colors.BLUE_GREY_200,
                                                ),
                                                speech_slider,
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
                                                ft.Row([ft.Text("Âm lượng nền"), background_value]),
                                                ft.Text(
                                                    "Điều chỉnh độ lớn âm thanh nền trước khi mix với giọng đọc.",
                                                    size=12,
                                                    color=ft.Colors.BLUE_GREY_200,
                                                ),
                                                background_slider,
                                            ],
                                        ),
                                    ],
                                    spacing=12,
                                ),
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
                            spacing=8,
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Icon(ft.Icons.INFO, color=ft.Colors.BLUE_200),
                                        ft.Text("Trạng thái", size=18, weight=ft.FontWeight.BOLD),
                                    ]
                                ),
                                stage_text,
                                status_text,
                            ],
                        ),
                    ),
                ],
            ),
        )

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
