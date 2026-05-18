from __future__ import annotations

import os
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.download_service import DownloadJobCallbacks, DownloadService
from utils.download import (
    DEFAULT_DOWNLOAD_DIR,
    DownloadProgress,
    DownloadResult,
    build_output_filename,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{value} B"


def _format_eta(eta_sec: Optional[float]) -> str:
    if eta_sec is None:
        return "--"
    sec = max(int(eta_sec), 0)
    minutes, seconds = divmod(sec, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def open_folder(path: str) -> None:
    folder = str(Path(path).parent)
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", folder])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])  # noqa: S603,S607
    else:
        os.startfile(folder)  # type: ignore[attr-defined]


def pick_directory_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--directory",
                "--title=Chọn thư mục lưu",
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
    picked = QFileDialog.getExistingDirectory(
        None,
        "Chọn thư mục lưu",
        initial_dir,
    )
    if owns_app and app:
        app.quit()
    return picked or None


class DownloadView(BaseFeatureView):
    feature_id = "download"
    title = "Bộ Tải File"
    icon = ft.Icons.CLOUD_DOWNLOAD

    def __init__(self) -> None:
        self.service = DownloadService()
        self._last_file_path: Optional[str] = None
        self._saved_url: str = ""
        self._selected_dir: str = str(DEFAULT_DOWNLOAD_DIR)
        self._status_text: str = ""
        self._show_progress_card: bool = False
        self._file_name_text: str = "--"
        self._speed_text: str = "--"
        self._size_text: str = "--"
        self._eta_text: str = "--"
        self._progress_value: Optional[float] = 0
        self._busy: bool = False
        self._open_folder_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None

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

        controls["url_input"].value = self._saved_url
        controls["save_dir_input"].value = self._selected_dir
        controls["status_text"].value = self._status_text
        controls["progress_card"].visible = self._show_progress_card
        controls["progress_bar"].value = self._progress_value
        controls["file_name"].value = self._file_name_text
        controls["speed_text"].value = self._speed_text
        controls["size_text"].value = self._size_text
        controls["eta_text"].value = self._eta_text
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in ("url_input", "save_dir_input", "choose_dir_button", "use_default_dir_button", "download_button"):
            controls[key].disabled = self._busy
        controls["download_button"].text = "Đang tải..." if self._busy else "Bắt đầu tải"
        controls["download_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.DOWNLOAD

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        url_input = ft.TextField(
            label="URL",
            value=self._saved_url,
            hint_text="Dán link cần tải vào đây...",
            border_radius=12,
            focused_border_color=ACCENT,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        save_dir_input = ft.TextField(
            label="Thư mục lưu",
            value=self._selected_dir,
            read_only=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        status_text = ft.Text(self._status_text, color=WARN, size=13, selectable=True)
        progress_bar = ft.ProgressBar(value=self._progress_value, color=ACCENT, bgcolor="#2E2E2E")
        file_name = ft.Text(self._file_name_text, color=ft.Colors.WHITE)
        speed_text = ft.Text(self._speed_text, color=ft.Colors.BLUE_GREY_100)
        size_text = ft.Text(self._size_text, color=ft.Colors.BLUE_GREY_100)
        eta_text = ft.Text(self._eta_text, color=ft.Colors.BLUE_GREY_100)
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
                            ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.BLUE_200),
                            file_name,
                        ]
                    ),
                    progress_bar,
                    ft.ResponsiveRow(
                        controls=[
                            ft.Container(ft.Column([ft.Text("Tốc độ"), speed_text]), col=4),
                            ft.Container(ft.Column([ft.Text("Đã tải/Tổng"), size_text]), col=4),
                            ft.Container(ft.Column([ft.Text("ETA"), eta_text]), col=4),
                        ]
                    ),
                    status_text,
                ],
            ),
        )

        download_button = ft.ElevatedButton(
            "Bắt đầu tải",
            icon=ft.Icons.DOWNLOAD,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self._open_folder_visible,
        )
        choose_dir_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        use_default_dir_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        self._controls = {
            "url_input": url_input,
            "save_dir_input": save_dir_input,
            "status_text": status_text,
            "progress_card": progress_card,
            "progress_bar": progress_bar,
            "file_name": file_name,
            "speed_text": speed_text,
            "size_text": size_text,
            "eta_text": eta_text,
            "download_button": download_button,
            "open_folder_button": open_folder_button,
            "choose_dir_button": choose_dir_button,
            "use_default_dir_button": use_default_dir_button,
        }

        def request_ui_refresh() -> None:
            self._sync_controls()
            self._request_ui_refresh()

        def set_busy(busy: bool, refresh: bool = True) -> None:
            self._busy = busy
            if refresh:
                request_ui_refresh()

        def ui_progress(progress: DownloadProgress) -> None:
            self._file_name_text = progress.filename
            file_name.value = self._file_name_text
            if progress.percent is None:
                self._progress_value = None
                progress_bar.value = None
            else:
                self._progress_value = max(0.0, min(1.0, progress.percent / 100))
                progress_bar.value = self._progress_value
            self._speed_text = f"{progress.speed_mbps:.2f} MB/s"
            speed_text.value = self._speed_text
            if progress.total_bytes > 0:
                self._size_text = (
                    f"{_format_bytes(progress.downloaded_bytes)} / {_format_bytes(progress.total_bytes)}"
                )
            else:
                self._size_text = _format_bytes(progress.downloaded_bytes)
            size_text.value = self._size_text
            self._eta_text = _format_eta(progress.eta_sec)
            eta_text.value = self._eta_text
            request_ui_refresh()

        def ui_success(result: DownloadResult) -> None:
            self._last_file_path = result.file_path
            self._open_folder_visible = bool(result.file_path)
            open_folder_button.visible = self._open_folder_visible
            self._status_text = ""
            status_text.value = self._status_text
            set_busy(False, refresh=False)
            page.snack_bar = ft.SnackBar(
                content=ft.Text("Tải file thành công."),
                bgcolor=ft.Colors.GREEN_700,
                open=True,
            )
            request_ui_refresh()

        def ui_error(result: DownloadResult) -> None:
            self._status_text = result.error_message or "Tải file thất bại."
            status_text.value = self._status_text
            set_busy(False, refresh=False)
            request_ui_refresh()

        def run_download(_: ft.ControlEvent) -> None:
            url = (url_input.value or "").strip()
            self._saved_url = url
            if not url:
                self._status_text = "Vui lòng nhập URL trước khi tải."
                status_text.value = self._status_text
                page.update()
                return
            if self.service.is_downloading:
                self._status_text = "Đang có tác vụ chạy, vui lòng chờ hoàn tất."
                status_text.value = self._status_text
                page.update()
                return

            self._show_progress_card = True
            progress_card.visible = self._show_progress_card
            self._open_folder_visible = False
            open_folder_button.visible = self._open_folder_visible
            self._status_text = ""
            status_text.value = self._status_text
            self._progress_value = 0
            progress_bar.value = self._progress_value
            self._file_name_text = "--"
            file_name.value = self._file_name_text
            self._speed_text = "--"
            speed_text.value = self._speed_text
            self._size_text = "--"
            size_text.value = self._size_text
            self._eta_text = "--"
            eta_text.value = self._eta_text
            set_busy(True)
            current_save_dir = (save_dir_input.value or "").strip()
            if not current_save_dir:
                self._status_text = "Vui lòng nhập thư mục lưu."
                status_text.value = self._status_text
                set_busy(False)
                return
            output_path = str(Path(current_save_dir).expanduser() / build_output_filename(url))

            callbacks = DownloadJobCallbacks(
                on_progress=ui_progress,
                on_success=ui_success,
                on_error=ui_error,
            )

            def worker() -> None:
                try:
                    self.service.run_job(url=url, output_name=output_path, callbacks=callbacks)
                except Exception as exc:  # Phòng vệ lỗi ngoài dự kiến.
                    ui_error(
                        DownloadResult(
                            ok=False,
                            file_path=None,
                            total_bytes=0,
                            downloaded_bytes=0,
                            elapsed_sec=0,
                            error_message=str(exc),
                            http_status=None,
                        ),
                    )

            page.run_thread(worker)

        def open_download_folder(_: ft.ControlEvent) -> None:
            if self._last_file_path:
                open_folder(self._last_file_path)

        def choose_save_dir(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self._selected_dir or str(DEFAULT_DOWNLOAD_DIR))
            if picked is None:
                return

            if picked:
                self._selected_dir = picked
                save_dir_input.value = self._selected_dir
                request_ui_refresh()

        def set_default_save_dir(_: ft.ControlEvent) -> None:
            self._selected_dir = str(DEFAULT_DOWNLOAD_DIR)
            save_dir_input.value = self._selected_dir
            request_ui_refresh()

        download_button.on_click = run_download
        open_folder_button.on_click = open_download_folder
        choose_dir_button.on_click = choose_save_dir
        use_default_dir_button.on_click = set_default_save_dir

        set_busy(self._busy, refresh=False)
        self._sync_controls()

        return ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                spacing=16,
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.BOLT, color=ACCENT, size=28),
                            ft.Text("Bộ Tải File", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                url_input,
                                ft.Row([save_dir_input, choose_dir_button, use_default_dir_button], spacing=12),
                                ft.Row([download_button, open_folder_button], spacing=12),
                            ],
                        ),
                    ),
                    progress_card,
                ],
            ),
        )
