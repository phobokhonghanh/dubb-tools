from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.translate_service import TranslateCallbacks, TranslateService
from utils.translator import (
    DEFAULT_TRANSLATE_MODEL,
    DEFAULT_TRANSLATE_OUTPUT_DIR,
    LANGUAGE_OPTIONS,
    SrtSegment,
    TranslateProgress,
    TranslateResult,
    build_output_path,
    replace_all,
    serialize_srt,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
MODEL_OPTIONS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]


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
                "--title=Chọn thư mục lưu bản dịch",
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
    picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu bản dịch", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_srt_file_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Chọn file SRT",
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
    picked, _ = QFileDialog.getOpenFileName(None, "Chọn file SRT", initial_dir, "File SRT (*.srt)")
    if owns_app and app:
        app.quit()
    return picked or None


def find_latest_srt(base_dir: str | Path = DEFAULT_TRANSLATE_OUTPUT_DIR) -> Optional[Path]:
    directory = Path(base_dir).expanduser()
    if not directory.exists():
        return None
    candidates = [path for path in directory.glob("*_transcript.srt") if path.is_file()]
    if not candidates:
        candidates = [path for path in directory.glob("*.srt") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


class TranslateView(BaseFeatureView):
    feature_id = "translate"
    title = "Dịch Phụ Đề"
    icon = ft.Icons.TRANSLATE

    def __init__(self) -> None:
        self.service = TranslateService()
        config = self.service.load_config()
        self._input_srt: str = ""
        self._output_dir: str = str(DEFAULT_TRANSLATE_OUTPUT_DIR)
        self._model: str = str(config.get("model") or DEFAULT_TRANSLATE_MODEL)
        api_keys = config.get("api_keys")
        self._api_key: str = ""
        if isinstance(api_keys, dict):
            self._api_key = str(api_keys.get(self._model) or "")
        if not self._api_key:
            self._api_key = str(config.get("gemini_api_key") or "")
        self._target_language: str = str(config.get("target_language") or "vi")
        self._content_safety: bool = bool(config.get("content_safety"))
        self._status_text: str = ""
        self._stage_text: str = "--"
        self._current_file_text: str = "--"
        self._progress_value: Optional[float] = None
        self._progress_visible: bool = False
        self._show_progress_card: bool = False
        self._segments: list[SrtSegment] = []
        self._line_count_text: str = "Tổng số dòng: 0"
        self._find_text: str = ""
        self._replace_text: str = ""
        self._busy: bool = False
        self._output_file: Optional[str] = None
        self._save_button_visible: bool = False
        self._open_folder_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None

    def _maybe_prefill_latest_srt(self) -> None:
        if self._input_srt:
            return
        latest = find_latest_srt(DEFAULT_TRANSLATE_OUTPUT_DIR)
        if latest:
            self._input_srt = str(latest)
            self._current_file_text = latest.name

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
                            ft.Text(segment.text, expand=True, selectable=True),
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
        controls["model_dropdown"].value = self._model
        controls["api_key_field"].value = self._api_key
        controls["target_language_dropdown"].value = self._target_language
        controls["content_safety_checkbox"].value = self._content_safety
        controls["status_text"].value = self._status_text
        controls["stage_text"].value = self._stage_text
        controls["current_file_text"].value = self._current_file_text
        controls["progress_bar"].visible = self._progress_visible
        controls["progress_bar"].value = self._progress_value
        controls["progress_card"].visible = self._show_progress_card
        controls["result_list"].controls = self._build_result_rows()
        controls["line_count_text"].value = self._line_count_text
        controls["find_field"].value = self._find_text
        controls["replace_field"].value = self._replace_text
        controls["save_button"].visible = self._save_button_visible
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in (
            "choose_input_button",
            "choose_output_button",
            "reset_output_button",
            "model_dropdown",
            "api_key_field",
            "target_language_dropdown",
            "content_safety_checkbox",
            "translate_button",
            "replace_button",
            "save_button",
        ):
            controls[key].disabled = self._busy
        controls["translate_button"].text = "Đang dịch..." if self._busy else "Bắt đầu dịch"
        controls["translate_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.TRANSLATE

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        self._maybe_prefill_latest_srt()

        input_srt_field = ft.TextField(
            label="File SRT Đầu Vào",
            value=self._input_srt,
            hint_text="Chưa chọn file .srt",
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
        model_dropdown = ft.Dropdown(
            label="Model",
            value=self._model,
            options=[ft.dropdown.Option(key=value, text=value) for value in MODEL_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=220,
        )
        api_key_field = ft.TextField(
            label="Gemini API Key",
            value=self._api_key,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        target_language_dropdown = ft.Dropdown(
            label="Ngôn Ngữ Đích",
            value=self._target_language,
            options=[ft.dropdown.Option(key=key, text=value) for key, value in LANGUAGE_OPTIONS.items()],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=170,
        )
        content_safety_checkbox = ft.Checkbox(
            label="Lọc Nội Dung Nhạy Cảm",
            value=self._content_safety,
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
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.TRANSLATE, color=ft.Colors.BLUE_200),
                            current_file_text,
                        ]
                    ),
                    progress_bar,
                    stage_text,
                    status_text,
                ],
            ),
        )
        result_list = ft.ListView(controls=self._build_result_rows(), spacing=8, height=320)
        line_count_text = ft.Text(self._line_count_text, color=ft.Colors.BLUE_GREY_100)
        find_field = ft.TextField(
            label="Tìm từ ngữ",
            value=self._find_text,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
        replace_field = ft.TextField(
            label="Thay thế bằng",
            value=self._replace_text,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )

        choose_input_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        translate_button = ft.ElevatedButton(
            "Bắt đầu dịch",
            icon=ft.Icons.TRANSLATE,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        replace_button = ft.OutlinedButton("Thay thế tất cả", icon=ft.Icons.FIND_REPLACE)
        save_button = ft.ElevatedButton(
            "Lưu file .srt",
            icon=ft.Icons.SAVE,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
            visible=self._save_button_visible,
        )
        open_folder_button = ft.OutlinedButton(
            "Mở thư mục lưu",
            icon=ft.Icons.FOLDER_OPEN,
            visible=self._open_folder_visible,
        )

        self._controls = {
            "input_srt_field": input_srt_field,
            "output_dir_field": output_dir_field,
            "model_dropdown": model_dropdown,
            "api_key_field": api_key_field,
            "target_language_dropdown": target_language_dropdown,
            "content_safety_checkbox": content_safety_checkbox,
            "status_text": status_text,
            "stage_text": stage_text,
            "current_file_text": current_file_text,
            "progress_bar": progress_bar,
            "progress_card": progress_card,
            "result_list": result_list,
            "line_count_text": line_count_text,
            "find_field": find_field,
            "replace_field": replace_field,
            "choose_input_button": choose_input_button,
            "choose_output_button": choose_output_button,
            "reset_output_button": reset_output_button,
            "translate_button": translate_button,
            "replace_button": replace_button,
            "save_button": save_button,
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
            self._line_count_text = f"Tổng số dòng: {len(self._segments)}"

        def ui_progress(progress: TranslateProgress) -> None:
            self._stage_text = progress.message
            self._progress_value = None if progress.percent is None else max(0.0, min(1.0, progress.percent / 100))
            request_ui_refresh()

        def ui_chunk_done(segments: list[SrtSegment]) -> None:
            self._segments = segments
            update_line_count()
            self._save_button_visible = bool(self._segments)
            request_ui_refresh()

        def ui_success(result: TranslateResult) -> None:
            set_busy(False, refresh=False)
            self._segments = result.segments
            update_line_count()
            self._stage_text = "Hoàn tất"
            self._progress_value = 1
            self._progress_visible = True
            self._status_text = ""
            self._output_file = result.output_file
            self._save_button_visible = bool(self._segments)
            self._open_folder_visible = bool(self._output_file)
            request_ui_refresh()
            notify("Dịch phụ đề hoàn tất.", ft.Colors.GREEN_700)

        def ui_error(result: TranslateResult) -> None:
            set_busy(False, refresh=False)
            self._segments = result.segments
            update_line_count()
            self._status_text = result.error_message or "Dịch thất bại."
            self._save_button_visible = bool(self._segments)
            request_ui_refresh()

        def sync_input_values() -> None:
            self._model = model_dropdown.value or self._model
            self._api_key = api_key_field.value or ""
            self._target_language = target_language_dropdown.value or "vi"
            self._content_safety = bool(content_safety_checkbox.value)
            self._find_text = find_field.value or ""
            self._replace_text = replace_field.value or ""

        def choose_input(_: ft.ControlEvent) -> None:
            start_dir = str(Path(self._input_srt).parent) if self._input_srt else str(DEFAULT_TRANSLATE_OUTPUT_DIR)
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
            picked = pick_directory_native(self._output_dir or str(DEFAULT_TRANSLATE_OUTPUT_DIR))
            if not picked:
                return
            self._output_dir = picked
            self._status_text = ""
            request_ui_refresh()

        def reset_output(_: ft.ControlEvent) -> None:
            self._output_dir = str(DEFAULT_TRANSLATE_OUTPUT_DIR)
            self._status_text = ""
            request_ui_refresh()

        def on_model_change(event: ft.ControlEvent) -> None:
            self._model = event.control.value or DEFAULT_TRANSLATE_MODEL
            config = self.service.load_config()
            api_keys = config.get("api_keys")
            if isinstance(api_keys, dict):
                self._api_key = str(api_keys.get(self._model) or self._api_key)
            request_ui_refresh()

        def on_language_change(event: ft.ControlEvent) -> None:
            self._target_language = event.control.value or "vi"
            request_ui_refresh()

        def on_safety_change(event: ft.ControlEvent) -> None:
            self._content_safety = bool(event.control.value)
            request_ui_refresh()

        def on_api_key_change(event: ft.ControlEvent) -> None:
            self._api_key = event.control.value or ""

        def on_find_change(event: ft.ControlEvent) -> None:
            self._find_text = event.control.value or ""

        def on_replace_change(event: ft.ControlEvent) -> None:
            self._replace_text = event.control.value or ""

        def start_translate(_: ft.ControlEvent) -> None:
            sync_input_values()
            if self.service.is_processing:
                self._status_text = "Đang có tác vụ dịch chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            if not self._input_srt:
                self._status_text = "Vui lòng chọn file .srt."
                request_ui_refresh()
                return
            if not self._api_key.strip():
                self._status_text = "Vui lòng nhập Gemini API key."
                request_ui_refresh()
                return

            self._show_progress_card = True
            self._progress_visible = True
            self._progress_value = None
            self._stage_text = "Đang chuẩn bị dịch..."
            self._current_file_text = Path(self._input_srt).name
            self._status_text = ""
            self._segments = []
            update_line_count()
            self._output_file = None
            self._save_button_visible = False
            self._open_folder_visible = False
            set_busy(True)

            callbacks = TranslateCallbacks(on_progress=ui_progress, on_chunk_done=ui_chunk_done)
            input_srt = self._input_srt
            output_dir = self._output_dir
            model = self._model
            api_key = self._api_key
            target_language = self._target_language
            content_safety = self._content_safety

            def worker() -> None:
                try:
                    result = self.service.run_job(
                        input_srt=input_srt,
                        output_dir=output_dir,
                        provider="gemini",
                        model=model,
                        api_key=api_key,
                        target_language=target_language,
                        content_safety=content_safety,
                        callbacks=callbacks,
                    )
                    if result.ok:
                        ui_success(result)
                    else:
                        ui_error(result)
                except Exception as exc:
                    ui_error(
                        TranslateResult(
                            ok=False,
                            segments=[],
                            output_file=None,
                            elapsed_sec=0,
                            error_message=str(exc),
                        )
                    )

            page.run_thread(worker)

        def replace_current(_: ft.ControlEvent) -> None:
            sync_input_values()
            if not self._segments:
                self._status_text = "Chưa có kết quả dịch để thay thế."
                request_ui_refresh()
                return
            if not self._find_text:
                self._status_text = "Vui lòng nhập từ ngữ cần tìm."
                request_ui_refresh()
                return
            self._segments = replace_all(self._segments, self._find_text, self._replace_text)
            update_line_count()
            self._status_text = "Đã thay thế tất cả trên kết quả hiện tại."
            request_ui_refresh()

        def save_current(_: ft.ControlEvent) -> None:
            sync_input_values()
            if not self._segments:
                self._status_text = "Chưa có kết quả dịch để lưu."
                request_ui_refresh()
                return
            output_path = build_output_path(self._input_srt, self._output_dir, self._target_language)
            output_path.write_text(serialize_srt(self._segments), encoding="utf-8")
            self._output_file = str(output_path)
            self._open_folder_visible = True
            self._status_text = f"Đã lưu: {self._output_file}"
            request_ui_refresh()
            notify("Đã lưu file SRT.", ft.Colors.GREEN_700)

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self._output_file:
                open_folder(str(Path(self._output_file).parent))
            else:
                open_folder(self._output_dir)

        choose_input_button.on_click = choose_input
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        model_dropdown.on_select = on_model_change
        target_language_dropdown.on_select = on_language_change
        content_safety_checkbox.on_change = on_safety_change
        api_key_field.on_change = on_api_key_change
        find_field.on_change = on_find_change
        replace_field.on_change = on_replace_change
        translate_button.on_click = start_translate
        replace_button.on_click = replace_current
        save_button.on_click = save_current
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
                            ft.Icon(ft.Icons.TRANSLATE, color=ACCENT, size=28),
                            ft.Text("Dịch Phụ Đề", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([model_dropdown, target_language_dropdown, content_safety_checkbox], spacing=12),
                                ft.Row([api_key_field], spacing=12),
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
                                ft.Row([translate_button], spacing=12),
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
                                        ft.Icon(ft.Icons.SUBTITLES, color=ft.Colors.BLUE_200),
                                        ft.Text("Xem Trước Kết Quả", size=18, weight=ft.FontWeight.BOLD),
                                        ft.Container(expand=True),
                                        line_count_text,
                                    ]
                                ),
                                result_list,
                                ft.Row([find_field, replace_field, replace_button], spacing=12),
                                ft.Row([save_button, open_folder_button], spacing=12),
                                status_text,
                            ],
                        ),
                    ),
                ],
            ),
        )
