from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.video_splitter_service import VideoSplitterCallbacks, VideoSplitterService
from utils.video_splitter import DEFAULT_OUTPUT_DIR, SUPPORTED_VIDEO_EXTENSIONS, VideoSplitProgress, VideoSplitResult


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"


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
                "--title=Chọn thư mục lưu kết quả",
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
    picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu kết quả", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_video_file_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        pattern = "File video | *.mp4 *.mkv *.avi *.mov"
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Chọn video đầu vào",
                f"--filename={initial_dir.rstrip('/')}/",
                f"--file-filter={pattern}",
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
    picked, _ = QFileDialog.getOpenFileName(
        None,
        "Chọn video đầu vào",
        initial_dir,
        "File video (*.mp4 *.mkv *.avi *.mov)",
    )
    if owns_app and app:
        app.quit()
    return picked or None


class VideoSplitterView(BaseFeatureView):
    feature_id = "video_splitter"
    title = "Bộ Tách Video"
    icon = ft.Icons.AUDIOTRACK

    def __init__(self) -> None:
        self.service = VideoSplitterService()
        self._last_output_dir: Optional[str] = None
        self._input_video: str = ""
        self._output_dir: str = str(DEFAULT_OUTPUT_DIR)
        self._status_text: str = ""
        self._show_progress_card: bool = False
        self._stage_text: str = "--"
        self._current_file_text: str = "--"
        self._progress_visible: bool = False
        self._progress_value: Optional[float] = None
        self._open_folder_visible: bool = False
        self._busy: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None
        self._notified_success: bool = False

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

        controls["input_path_field"].value = self._input_video
        controls["output_dir_field"].value = self._output_dir
        controls["status_text"].value = self._status_text
        controls["current_file_text"].value = self._current_file_text
        controls["stage_text"].value = self._stage_text
        controls["progress_bar"].visible = self._progress_visible
        controls["progress_bar"].value = self._progress_value
        controls["progress_card"].visible = self._show_progress_card
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in ("choose_input_button", "choose_output_button", "reset_output_button", "process_button"):
            controls[key].disabled = self._busy
        controls["process_button"].text = "Đang xử lý..." if self._busy else "Bắt đầu tách"
        controls["process_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.PLAY_ARROW

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        input_path_field = ft.TextField(
            label="Video Đầu Vào",
            value=self._input_video,
            hint_text="Chưa chọn video đầu vào",
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        output_dir_field = ft.TextField(
            label="Thư mục lưu",
            value=self._output_dir,
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
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
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.MOVIE, color=ft.Colors.BLUE_200),
                            current_file_text,
                        ]
                    ),
                    progress_bar,
                    stage_text,
                    status_text,
                ],
            ),
        )

        choose_input_button = ft.OutlinedButton("Chọn file", icon=ft.Icons.VIDEO_FILE)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        process_button = ft.ElevatedButton(
            "Bắt đầu tách",
            icon=ft.Icons.PLAY_ARROW,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục lưu",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self._open_folder_visible,
        )
        self._controls = {
            "input_path_field": input_path_field,
            "output_dir_field": output_dir_field,
            "status_text": status_text,
            "current_file_text": current_file_text,
            "stage_text": stage_text,
            "progress_bar": progress_bar,
            "progress_card": progress_card,
            "choose_input_button": choose_input_button,
            "choose_output_button": choose_output_button,
            "reset_output_button": reset_output_button,
            "process_button": process_button,
            "open_folder_button": open_folder_button,
        }

        def request_ui_refresh() -> None:
            self._sync_controls()
            self._request_ui_refresh()

        def set_busy(busy: bool, refresh: bool = True) -> None:
            self._busy = busy
            if refresh:
                request_ui_refresh()

        def ui_progress(progress: VideoSplitProgress) -> None:
            self._stage_text = progress.message
            stage_text.value = self._stage_text
            if progress.percent is None:
                self._progress_value = None
                progress_bar.value = None
            else:
                self._progress_value = max(0.0, min(1.0, progress.percent / 100))
                progress_bar.value = self._progress_value
            request_ui_refresh()

        def ui_success(result: VideoSplitResult) -> None:
            self._notified_success = True
            set_busy(False, refresh=False)
            self._stage_text = "Hoàn thành"
            stage_text.value = self._stage_text
            self._status_text = ""
            status_text.value = self._status_text
            self._progress_visible = True
            progress_bar.visible = self._progress_visible
            self._progress_value = 1
            progress_bar.value = self._progress_value
            success_output = Path(result.muted_video).parent if result.muted_video else Path(self._output_dir)
            self._output_dir = str(success_output)
            output_dir_field.value = self._output_dir
            self._last_output_dir = self._output_dir
            self._open_folder_visible = True
            open_folder_button.visible = self._open_folder_visible
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Tách video và âm thanh thành công."),
                bgcolor=ft.Colors.GREEN_700,
                open=True,
            )
            request_ui_refresh()

        def ui_error(result: VideoSplitResult) -> None:
            set_busy(False, refresh=False)
            self._status_text = result.error_message or "Xử lý thất bại."
            status_text.value = self._status_text
            self._open_folder_visible = bool(self._last_output_dir)
            open_folder_button.visible = self._open_folder_visible
            request_ui_refresh()

        def choose_input(_: ft.ControlEvent) -> None:
            start_dir = str(Path(self._input_video).parent) if self._input_video else str(Path.home())
            picked = pick_video_file_native(start_dir)
            if not picked:
                return
            extension = Path(picked).suffix.lower()
            if extension not in SUPPORTED_VIDEO_EXTENSIONS:
                self._status_text = "Định dạng video không hỗ trợ."
                status_text.value = self._status_text
                request_ui_refresh()
                return
            self._input_video = picked
            input_path_field.value = self._input_video
            self._current_file_text = Path(self._input_video).name
            current_file_text.value = self._current_file_text
            self._status_text = ""
            status_text.value = self._status_text
            request_ui_refresh()

        def choose_output(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self._output_dir or str(DEFAULT_OUTPUT_DIR))
            if not picked:
                return
            self._output_dir = picked
            output_dir_field.value = self._output_dir
            self._status_text = ""
            status_text.value = self._status_text
            request_ui_refresh()

        def reset_output(_: ft.ControlEvent) -> None:
            self._output_dir = str(DEFAULT_OUTPUT_DIR)
            output_dir_field.value = self._output_dir
            request_ui_refresh()

        def start_processing(_: ft.ControlEvent) -> None:
            if self.service.is_processing:
                self._status_text = "Đang có tác vụ xử lý, vui lòng chờ hoàn tất."
                status_text.value = self._status_text
                page.update()
                return

            if not self._input_video:
                self._status_text = "Vui lòng chọn video đầu vào."
                status_text.value = self._status_text
                page.update()
                return

            progress_card.visible = True
            self._show_progress_card = True
            self._progress_visible = True
            progress_bar.visible = self._progress_visible
            self._open_folder_visible = False
            open_folder_button.visible = self._open_folder_visible
            self._stage_text = "Đang chuẩn bị xử lý..."
            stage_text.value = self._stage_text
            self._status_text = ""
            status_text.value = self._status_text
            self._current_file_text = Path(self._input_video).name
            current_file_text.value = self._current_file_text
            self._progress_value = None
            progress_bar.value = self._progress_value
            self._notified_success = False
            set_busy(True)

            callbacks = VideoSplitterCallbacks(
                on_progress=ui_progress,
                on_success=None,
                on_error=None,
            )

            def worker() -> None:
                try:
                    result = self.service.run_job(
                        video_path=self._input_video,
                        output_dir=self._output_dir,
                        callbacks=callbacks,
                    )
                    if result.ok:
                        ui_success(result)
                    else:
                        ui_error(result)
                except Exception as exc:  # Phòng vệ lỗi ngoài dự kiến.
                    ui_error(
                        VideoSplitResult(
                            ok=False,
                            muted_video=None,
                            vocals_audio=None,
                            background_audio=None,
                            elapsed_sec=0,
                            error_message=str(exc),
                        )
                    )

            page.run_thread(worker)

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self._last_output_dir:
                open_folder(self._last_output_dir)

        choose_input_button.on_click = choose_input
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        process_button.on_click = start_processing
        open_folder_button.on_click = open_output_folder
        self._sync_controls()

        return ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.GRAPHIC_EQ, color=ACCENT, size=28),
                            ft.Text("Bộ Tách Video", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([input_path_field, choose_input_button], spacing=12),
                                ft.Row([output_dir_field, choose_output_button, reset_output_button], spacing=12),
                                ft.Row([process_button, open_folder_button], spacing=12),
                            ],
                        ),
                    ),
                    progress_card,
                ],
            ),
        )
