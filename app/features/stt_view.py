from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import flet as ft

from app.features.base import BaseFeatureView
from app.services.stt_service import SttCallbacks, SttService
from utils.stt_processor import (
    DEFAULT_STT_OUTPUT_DIR,
    SUPPORTED_AUDIO_EXTENSIONS,
    SttProgress,
    SttResult,
    TranscriptSegment,
    find_latest_vocals,
    format_segment_time,
    merge_segments,
    normalize_language,
    normalize_segments,
    save_transcript,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
LANGUAGE_OPTIONS = [
    ("auto", "Auto"),
    ("vi", "vi"),
    ("en", "en"),
    ("zh", "zh"),
    ("ja", "ja"),
    ("ko", "ko"),
    ("fr", "fr"),
    ("de", "de"),
    ("es", "es"),
    ("th", "th"),
]
MODEL_OPTIONS = ["tiny", "base", "small", "medium", "large-v3"]
SPEAKER_OPTIONS = ["1 người nói", "2 người nói", "Nhiều người nói"]


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
                "--title=Chọn thư mục lưu transcript",
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
    picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu transcript", initial_dir)
    if owns_app and app:
        app.quit()
    return picked or None


def pick_audio_file_native(initial_dir: str) -> Optional[str]:
    if shutil.which("zenity"):
        pattern = "File âm thanh | *.wav *.mp3 *.m4a *.aac *.flac *.ogg"
        result = subprocess.run(
            [
                "zenity",
                "--file-selection",
                "--title=Chọn file âm thanh",
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
        "Chọn file âm thanh",
        initial_dir,
        "File âm thanh (*.wav *.mp3 *.m4a *.aac *.flac *.ogg)",
    )
    if owns_app and app:
        app.quit()
    return picked or None


class SttView(BaseFeatureView):
    feature_id = "speech_to_text"
    title = "Giọng Nói Thành Văn Bản"
    icon = ft.Icons.TRANSCRIBE

    def __init__(self) -> None:
        self.service = SttService()
        self._audio_path: str = ""
        self._output_dir: str = str(DEFAULT_STT_OUTPUT_DIR)
        self._speaker_mode: str = SPEAKER_OPTIONS[0]
        self._model_size: str = "base"
        self._language: str = "auto"
        self._status_text: str = ""
        self._show_progress_card: bool = False
        self._stage_text: str = "--"
        self._current_file_text: str = "--"
        self._progress_value: Optional[float] = None
        self._progress_visible: bool = False
        self._segments: list[TranscriptSegment] = []
        self._source_segments: list[TranscriptSegment] = []
        self._group_size: str = "5"
        self._line_count_text: str = "Tổng số dòng: 0"
        self._busy: bool = False
        self._output_file: Optional[str] = None
        self._open_folder_visible: bool = False
        self._save_button_visible: bool = False
        self._controls: dict[str, ft.Control] = {}
        self._page: Optional[ft.Page] = None

    def _maybe_prefill_latest_vocals(self) -> None:
        if self._audio_path:
            return
        latest = find_latest_vocals(DEFAULT_STT_OUTPUT_DIR)
        if latest:
            self._audio_path = str(latest)
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
        for index, segment in enumerate(self._segments, start=1):
            rows.append(
                ft.Container(
                    bgcolor=SURFACE_BG,
                    border_radius=8,
                    padding=10,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        controls=[
                            ft.Text(str(index), width=34, color=ft.Colors.BLUE_GREY_200),
                            ft.Text(
                                f"[{format_segment_time(segment.start_time, segment.end_time)}]",
                                width=132,
                                color=ACCENT,
                                selectable=True,
                            ),
                            ft.Text(segment.content, expand=True, selectable=True),
                        ],
                    ),
                )
            )
        return rows

    def _sync_controls(self) -> None:
        controls = self._controls
        if not controls:
            return

        controls["audio_path_field"].value = self._audio_path
        controls["output_dir_field"].value = self._output_dir
        controls["speaker_dropdown"].value = self._speaker_mode
        controls["model_dropdown"].value = self._model_size
        controls["language_dropdown"].value = self._language
        controls["status_text"].value = self._status_text
        controls["current_file_text"].value = self._current_file_text
        controls["stage_text"].value = self._stage_text
        controls["progress_bar"].visible = self._progress_visible
        controls["progress_bar"].value = self._progress_value
        controls["progress_card"].visible = self._show_progress_card
        controls["group_size_field"].value = self._group_size
        controls["line_count_text"].value = self._line_count_text
        controls["result_list"].controls = self._build_result_rows()
        controls["save_button"].visible = self._save_button_visible
        controls["open_folder_button"].visible = self._open_folder_visible

        for key in (
            "choose_audio_button",
            "choose_output_button",
            "reset_output_button",
            "speaker_dropdown",
            "model_dropdown",
            "language_dropdown",
            "process_button",
            "merge_button",
            "normalize_button",
            "save_button",
        ):
            controls[key].disabled = self._busy
        controls["process_button"].text = "Đang xử lý..." if self._busy else "Bắt đầu nhận diện"
        controls["process_button"].icon = ft.Icons.HOURGLASS_TOP if self._busy else ft.Icons.PLAY_ARROW

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        self._maybe_prefill_latest_vocals()

        audio_path_field = ft.TextField(
            label="Âm Thanh Đầu Vào",
            value=self._audio_path,
            hint_text="Chưa chọn file âm thanh",
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
        speaker_dropdown = ft.Dropdown(
            label="Số người nói",
            value=self._speaker_mode,
            options=[ft.dropdown.Option(key=value, text=value) for value in SPEAKER_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=180,
        )
        model_dropdown = ft.Dropdown(
            label="Model",
            value=self._model_size,
            options=[ft.dropdown.Option(key=value, text=value) for value in MODEL_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=150,
        )
        language_dropdown = ft.Dropdown(
            label="Ngôn Ngữ",
            value=self._language,
            options=[ft.dropdown.Option(key=key, text=text) for key, text in LANGUAGE_OPTIONS],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=150,
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
                            ft.Icon(ft.Icons.MIC, color=ft.Colors.BLUE_200),
                            current_file_text,
                        ]
                    ),
                    progress_bar,
                    stage_text,
                    status_text,
                ],
            ),
        )

        result_list = ft.ListView(
            controls=self._build_result_rows(),
            spacing=8,
            height=300,
            auto_scroll=False,
        )
        line_count_text = ft.Text(self._line_count_text, color=ft.Colors.BLUE_GREY_100)
        group_size_field = ft.TextField(
            label="Số dòng gộp",
            value=self._group_size,
            border_radius=12,
            width=140,
            bgcolor=SURFACE_BG,
        )
        choose_audio_button = ft.OutlinedButton("Chọn file", icon=ft.Icons.AUDIO_FILE)
        choose_output_button = ft.OutlinedButton("Chọn thư mục", icon=ft.Icons.FOLDER)
        reset_output_button = ft.OutlinedButton("Mặc định", icon=ft.Icons.RESTART_ALT)
        process_button = ft.ElevatedButton(
            "Bắt đầu nhận diện",
            icon=ft.Icons.PLAY_ARROW,
            bgcolor=ACCENT,
            color=ft.Colors.BLACK,
        )
        merge_button = ft.OutlinedButton("Gộp", icon=ft.Icons.MERGE_TYPE)
        normalize_button = ft.OutlinedButton("Chuẩn hóa", icon=ft.Icons.AUTO_FIX_HIGH)
        save_button = ft.ElevatedButton(
            "Lưu kết quả",
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
            "audio_path_field": audio_path_field,
            "output_dir_field": output_dir_field,
            "speaker_dropdown": speaker_dropdown,
            "model_dropdown": model_dropdown,
            "language_dropdown": language_dropdown,
            "status_text": status_text,
            "current_file_text": current_file_text,
            "stage_text": stage_text,
            "progress_bar": progress_bar,
            "progress_card": progress_card,
            "result_list": result_list,
            "line_count_text": line_count_text,
            "group_size_field": group_size_field,
            "choose_audio_button": choose_audio_button,
            "choose_output_button": choose_output_button,
            "reset_output_button": reset_output_button,
            "process_button": process_button,
            "merge_button": merge_button,
            "normalize_button": normalize_button,
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

        def ui_progress(progress: SttProgress) -> None:
            self._stage_text = progress.message
            if progress.percent is None:
                self._progress_value = None
            else:
                self._progress_value = max(0.0, min(1.0, progress.percent / 100))
            request_ui_refresh()

        def ui_success(result: SttResult) -> None:
            set_busy(False, refresh=False)
            self._segments = result.segments
            self._source_segments = list(result.segments)
            update_line_count()
            self._stage_text = "Hoàn tất"
            self._progress_value = 1
            self._progress_visible = True
            self._status_text = ""
            self._save_button_visible = bool(self._segments)
            self._open_folder_visible = bool(self._output_file)
            request_ui_refresh()
            notify("Nhận diện giọng nói hoàn tất.", ft.Colors.GREEN_700)

        def ui_error(result: SttResult) -> None:
            set_busy(False, refresh=False)
            self._status_text = result.error_message or "Nhận diện thất bại."
            request_ui_refresh()

        def choose_audio(_: ft.ControlEvent) -> None:
            start_dir = str(Path(self._audio_path).parent) if self._audio_path else str(DEFAULT_STT_OUTPUT_DIR)
            picked = pick_audio_file_native(start_dir)
            if not picked:
                return
            extension = Path(picked).suffix.lower()
            if extension not in SUPPORTED_AUDIO_EXTENSIONS:
                self._status_text = "Định dạng âm thanh không hỗ trợ."
                request_ui_refresh()
                return
            self._audio_path = picked
            self._current_file_text = Path(picked).name
            self._status_text = ""
            request_ui_refresh()

        def choose_output(_: ft.ControlEvent) -> None:
            picked = pick_directory_native(self._output_dir or str(DEFAULT_STT_OUTPUT_DIR))
            if not picked:
                return
            self._output_dir = picked
            self._status_text = ""
            request_ui_refresh()

        def reset_output(_: ft.ControlEvent) -> None:
            self._output_dir = str(DEFAULT_STT_OUTPUT_DIR)
            self._status_text = ""
            request_ui_refresh()

        def on_speaker_change(event: ft.ControlEvent) -> None:
            self._speaker_mode = event.control.value or SPEAKER_OPTIONS[0]
            request_ui_refresh()

        def on_model_change(event: ft.ControlEvent) -> None:
            self._model_size = event.control.value or "base"
            request_ui_refresh()

        def on_language_change(event: ft.ControlEvent) -> None:
            self._language = event.control.value or "auto"
            request_ui_refresh()

        def start_processing(_: ft.ControlEvent) -> None:
            selected_speaker = speaker_dropdown.value or self._speaker_mode
            self._speaker_mode = selected_speaker
            self._model_size = model_dropdown.value or self._model_size
            self._language = language_dropdown.value or self._language

            if self.service.is_processing:
                self._status_text = "Đang có tác vụ nhận diện chạy, vui lòng đợi hoàn tất."
                request_ui_refresh()
                return
            if selected_speaker != SPEAKER_OPTIONS[0]:
                self._status_text = "Chức năng sắp ra mắt."
                request_ui_refresh()
                notify("Chức năng sắp ra mắt.", ft.Colors.BLUE_GREY_700)
                return
            if not self._audio_path:
                self._status_text = "Vui lòng chọn file âm thanh."
                request_ui_refresh()
                return

            self._show_progress_card = True
            self._progress_visible = True
            self._progress_value = None
            self._stage_text = "Đang chuẩn bị nhận diện..."
            self._current_file_text = Path(self._audio_path).name
            self._status_text = ""
            self._output_file = None
            self._open_folder_visible = False
            self._save_button_visible = False
            self._segments = []
            self._source_segments = []
            update_line_count()
            set_busy(True)

            callbacks = SttCallbacks(on_progress=ui_progress)
            audio_path = self._audio_path
            output_dir = self._output_dir
            model_size = self._model_size
            language = normalize_language(self._language)

            def worker() -> None:
                try:
                    result = self.service.run_job(
                        audio_path=audio_path,
                        output_dir=output_dir,
                        model_size=model_size,
                        language=language,
                        callbacks=callbacks,
                    )
                    if result.ok:
                        ui_success(result)
                    else:
                        ui_error(result)
                except Exception as exc:
                    ui_error(
                        SttResult(
                            ok=False,
                            segments=[],
                            output_file=None,
                            language=None,
                            language_probability=None,
                            elapsed_sec=0,
                            error_message=str(exc),
                        )
                    )

            page.run_thread(worker)

        def merge_current_segments(_: ft.ControlEvent) -> None:
            if not self._segments:
                self._status_text = "Chưa có kết quả để gộp."
                request_ui_refresh()
                return
            self._group_size = group_size_field.value or "1"
            try:
                group_size = int(self._group_size)
                self._segments = merge_segments(self._segments, group_size)
                update_line_count()
                self._status_text = ""
                request_ui_refresh()
            except Exception as exc:
                self._status_text = str(exc)
                request_ui_refresh()

        def normalize_current_segments(_: ft.ControlEvent) -> None:
            if not self._segments:
                self._status_text = "Chưa có kết quả để chuẩn hóa."
                request_ui_refresh()
                return
            self._segments = normalize_segments(self._segments)
            self._status_text = ""
            request_ui_refresh()

        def save_current_result(_: ft.ControlEvent) -> None:
            if not self._segments:
                self._status_text = "Chưa có kết quả để lưu."
                request_ui_refresh()
                return
            try:
                self._output_file = save_transcript(
                    self._segments,
                    self._output_dir,
                    Path(self._audio_path).name or "audio",
                    output_format="srt",
                )
                self._open_folder_visible = True
                self._status_text = f"Đã lưu: {self._output_file}"
                request_ui_refresh()
                notify("Đã lưu transcript SRT.", ft.Colors.GREEN_700)
            except Exception as exc:
                self._status_text = str(exc)
                request_ui_refresh()

        def open_output_folder(_: ft.ControlEvent) -> None:
            if self._output_file:
                open_folder(str(Path(self._output_file).parent))
            else:
                open_folder(self._output_dir)

        choose_audio_button.on_click = choose_audio
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        speaker_dropdown.on_select = on_speaker_change
        model_dropdown.on_select = on_model_change
        language_dropdown.on_select = on_language_change
        process_button.on_click = start_processing
        merge_button.on_click = merge_current_segments
        normalize_button.on_click = normalize_current_segments
        save_button.on_click = save_current_result
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
                            ft.Icon(ft.Icons.TRANSCRIBE, color=ACCENT, size=28),
                            ft.Text("Giọng Nói Thành Văn Bản", size=26, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Container(
                        bgcolor=CARD_BG,
                        border_radius=14,
                        padding=16,
                        content=ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row([audio_path_field, choose_audio_button], spacing=12),
                                ft.Row([output_dir_field, choose_output_button, reset_output_button], spacing=12),
                                ft.Row(
                                    [
                                        speaker_dropdown,
                                        model_dropdown,
                                        language_dropdown,
                                        process_button,
                                    ],
                                    spacing=12,
                                ),
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
                                        ft.Text("Kết quả nhận diện", size=18, weight=ft.FontWeight.BOLD),
                                        ft.Container(expand=True),
                                        line_count_text,
                                    ]
                                ),
                                result_list,
                                ft.Row(
                                    [
                                        group_size_field,
                                        merge_button,
                                        normalize_button,
                                        save_button,
                                        open_folder_button,
                                    ],
                                    spacing=12,
                                ),
                                status_text,
                            ],
                        ),
                    ),
                ],
            ),
        )
