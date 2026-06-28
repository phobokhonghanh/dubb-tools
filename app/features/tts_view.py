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
from constants import (
    DEFAULT_TTS_OUTPUT_DIR,
    DEFAULT_TTS_PROVIDER,
    TTS_LANGUAGE_OPTIONS as LANGUAGE_OPTIONS,
)
from infrastructure.providers.tts import (
    GeneratedSegment,
)


CARD_BG = "#1E1E1E"
SURFACE_BG = "#151515"
ACCENT = "#00D4FF"
WARN = "#FF8080"
PROVIDER_OPTIONS = [("edge-tts", "Edge-TTS"), ("gemini-tts", "Gemini TTS"), ("capcut", "CapCut TTS")]


def open_folder(path: str) -> None:
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603,S607
    else:
        os.startfile(path)  # type: ignore[attr-defined]


def pick_directory_native(initial_dir: str) -> Optional[str]:
    # 1. Try Zenity
    if shutil.which("zenity"):
        try:
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
            if result.returncode == 0:
                picked = result.stdout.strip()
                return picked or None
            elif result.returncode == 1:
                # User clicked Cancel
                return None
        except Exception:
            pass

    # 2. Try PySide6
    try:
        from PySide6.QtWidgets import QApplication, QFileDialog
        app = QApplication.instance()
        owns_app = app is None
        if owns_app:
            app = QApplication([])
        picked = QFileDialog.getExistingDirectory(None, "Chọn thư mục lưu audio", initial_dir)
        if owns_app and app:
            app.quit()
        return picked or None
    except Exception:
        pass

    # 3. Try Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        picked = filedialog.askdirectory(initialdir=initial_dir, title="Chọn thư mục lưu audio")
        root.destroy()
        return picked or None
    except Exception:
        pass

    return None


def pick_srt_file_native(initial_dir: str) -> Optional[str]:
    # 1. Try Zenity
    if shutil.which("zenity"):
        try:
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
            if result.returncode == 0:
                picked = result.stdout.strip()
                return picked or None
            elif result.returncode == 1:
                # User clicked Cancel
                return None
        except Exception:
            pass

    # 2. Try PySide6
    try:
        from PySide6.QtWidgets import QApplication, QFileDialog
        app = QApplication.instance()
        owns_app = app is None
        if owns_app:
            app = QApplication([])
        picked, _ = QFileDialog.getOpenFileName(None, "Chọn file SRT đã dịch", initial_dir, "File SRT (*.srt)")
        if owns_app and app:
            app.quit()
        return picked or None
    except Exception:
        pass

    # 3. Try Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        picked = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Chọn file SRT đã dịch",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )
        root.destroy()
        return picked or None
    except Exception:
        pass

    return None


def pick_audio_file_native(initial_dir: str) -> Optional[str]:
    # 1. Try Zenity
    if shutil.which("zenity"):
        try:
            result = subprocess.run(
                [
                    "zenity",
                    "--file-selection",
                    "--title=Chọn file âm thanh cần import",
                    f"--filename={initial_dir.rstrip('/')}/",
                    "--file-filter=Audio files | *.mp3 *.wav *.m4a *.aac *.flac *.MP3 *.WAV *.M4A *.AAC *.FLAC",
                    "--file-filter=All files | *",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                picked = result.stdout.strip()
                return picked or None
            elif result.returncode == 1:
                # User clicked Cancel
                return None
        except Exception:
            pass

    # 2. Try PySide6
    try:
        from PySide6.QtWidgets import QApplication, QFileDialog
        app = QApplication.instance()
        owns_app = app is None
        if owns_app:
            app = QApplication([])
        picked, _ = QFileDialog.getOpenFileName(
            None,
            "Chọn file âm thanh cần import",
            initial_dir,
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.MP3 *.WAV *.M4A *.AAC *.FLAC);;All Files (*)"
        )
        if owns_app and app:
            app.quit()
        return picked or None
    except Exception:
        pass

    # 3. Try Tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        picked = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Chọn file âm thanh cần import",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.m4a *.aac *.flac *.MP3 *.WAV *.M4A *.AAC *.FLAC"),
                ("All files", "*.*")
            ]
        )
        root.destroy()
        return picked or None
    except Exception:
        pass

    return None



class TtsView(BaseFeatureView):
    feature_id = "text_to_speech"
    title = "Lồng Tiếng AI"
    icon = ft.Icons.RECORD_VOICE_OVER

    def __init__(self) -> None:
        self.presenter = TtsPresenter(self)
        self.input_srt: str = ""
        self.input_mode: str = "file"
        self.input_text: str = ""
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
        self.capcut_version: str = "v2"
        self.capcut_cookie: str = ""
        self.capcut_workspace_id: str = ""
        self.capcut_device_id: str = ""
        self.proxy: str = ""
        self.voices: list = []
        self.show_advanced: bool = False
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
        if hasattr(self, "_audio_proc") and self._audio_proc is not None:
            try:
                self._audio_proc.terminate()
                self._audio_proc.wait(timeout=0.5)
            except Exception:
                pass
            self._audio_proc = None

        import subprocess
        try:
            self._audio_proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[Audio Playback Error] Không thể chạy ffplay: {e}")

    def _build_result_rows(self) -> list[ft.Control]:
        rows: list[ft.Control] = []
        
        # Đảm bảo các thuộc tính quản lý mở rộng/thu gọn và giá trị slider tồn tại trên self
        if not hasattr(self, "expanded_segments"):
            self.expanded_segments = set()
        if not hasattr(self, "collapsed_segments"):
            self.collapsed_segments = set()
        if not hasattr(self, "slider_values"):
            self.slider_values = {}

        for segment in self.segments:
            raw = "--" if segment.raw_duration_sec is None else f"{segment.raw_duration_sec:.2f}s"
            final = "--" if segment.final_duration_sec is None else f"{segment.final_duration_sec:.2f}s"
            
            is_error = (segment.status == "error")
            is_matched = not is_error and (segment.final_duration_sec <= segment.target_duration_sec or segment.target_duration_sec >= 999999.0)
            is_warning = not is_error and not is_matched

            # Khởi tạo giá trị slider mặc định cho phân đoạn nếu chưa có
            if segment.index not in self.slider_values:
                if is_warning and segment.target_duration_sec > 0:
                    rec_val = segment.raw_duration_sec / segment.target_duration_sec
                    self.slider_values[segment.index] = max(0.5, min(3.0, rec_val))
                else:
                    self.slider_values[segment.index] = 1.0

            # Nút nghe thử phân đoạn gốc/hiện tại
            play_btn = None
            if segment.file_path and os.path.exists(segment.file_path):
                play_btn = ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    icon_color=ACCENT,
                    icon_size=20,
                    tooltip="Nghe thử phân đoạn hiện tại",
                    on_click=lambda e, path=segment.file_path: self._play_audio(path),
                )
            else:
                play_btn = ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW_ROUNDED,
                    icon_color=ft.Colors.BLUE_GREY_700,
                    icon_size=20,
                    disabled=True,
                )

            # Icon trạng thái
            if is_error:
                status_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_700, size=20, tooltip="Trạng thái: E (Lỗi)")
            elif is_matched:
                status_icon = ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=ft.Colors.GREEN_700, size=20, tooltip="Trạng thái: O (Khớp)")
            else:
                status_icon = ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=ft.Colors.AMBER_700, size=20, tooltip="Trạng thái: W (Lệch)")

            # Nút điều chỉnh tốc độ (Tune) - Bấm để ẩn/hiện bộ chọn tốc độ
            def make_tune_click(idx=segment.index):
                def on_click(e):
                    if idx in self.expanded_segments:
                        self.expanded_segments.discard(idx)
                        self.collapsed_segments.add(idx)
                    else:
                        self.expanded_segments.add(idx)
                        self.collapsed_segments.discard(idx)
                    self.refresh()
                return on_click

            tune_btn = ft.IconButton(
                icon=ft.Icons.TUNE_ROUNDED,
                icon_color=ft.Colors.BLUE_GREY_400 if not is_error else ft.Colors.BLUE_GREY_700,
                icon_size=18,
                disabled=is_error,
                tooltip="Điều chỉnh tốc độ",
                on_click=make_tune_click(),
            )

            # Nút làm lại (Restart)
            def make_restart_click(idx=segment.index):
                def on_click(e):
                    self.presenter.regenerate_segment(idx)
                return on_click

            restart_btn = ft.IconButton(
                icon=ft.Icons.REFRESH_ROUNDED,
                icon_color=ft.Colors.BLUE_GREY_400,
                icon_size=18,
                tooltip="Làm lại phân đoạn",
                on_click=make_restart_click(),
            )

            # Nút tải xuống thủ công và sao chép URL khi gặp lỗi tải nhưng đã có audio_url
            def make_download_click(idx=segment.index, url=segment.audio_url):
                def on_click(e):
                    self.presenter.download_audio_url_manually(idx, url)
                return on_click

            def make_copy_click(url=segment.audio_url):
                def on_click(e):
                    self._page.set_clipboard(url)
                    self.notify("Đã sao chép URL tải audio vào clipboard!", ft.Colors.GREEN_700)
                return on_click

            download_btn = ft.IconButton(
                icon=ft.Icons.DOWNLOAD_ROUNDED,
                icon_color=ACCENT,
                icon_size=18,
                tooltip="Tải xuống thủ công từ CDN",
                visible=bool(is_error and segment.audio_url),
                on_click=make_download_click(),
            )

            copy_btn = ft.IconButton(
                icon=ft.Icons.COPY_ALL_ROUNDED,
                icon_color=ACCENT,
                icon_size=18,
                tooltip="Sao chép URL file âm thanh",
                visible=bool(is_error and segment.audio_url),
                on_click=make_copy_click(),
            )

            # Nút Import segment âm thanh ngoài
            def make_import_click(idx=segment.index):
                def on_click(e):
                    picked = pick_audio_file_native(self.output_dir or "resources/layer/process")
                    if picked:
                        self.presenter.import_segment_audio(idx, picked)
                return on_click

            import_btn = ft.IconButton(
                icon=ft.Icons.UPLOAD_FILE,
                icon_color=ACCENT,
                icon_size=18,
                tooltip="Import file âm thanh ngoài",
                on_click=make_import_click(),
            )

            # Xác định ẩn/hiện bộ chỉnh tốc độ
            panel_visible = False
            if not is_error:
                if is_warning and segment.index not in self.collapsed_segments:
                    panel_visible = True
                elif is_matched and segment.index in self.expanded_segments:
                    panel_visible = True

            # Xây dựng bộ slider điều chỉnh tốc độ
            speed_val = self.slider_values[segment.index]
            speed_text = ft.Text(f"{speed_val:.2f}x", width=50, weight=ft.FontWeight.BOLD, color=ACCENT)

            def make_on_change(idx=segment.index, txt_ctrl=speed_text):
                def on_change(e):
                    self.slider_values[idx] = e.control.value
                    txt_ctrl.value = f"{e.control.value:.2f}x"
                    txt_ctrl.update()
                return on_change

            slider = ft.Slider(
                min=0.5,
                max=3.0,
                divisions=25,
                value=speed_val,
                on_change=make_on_change(),
                width=150,
            )

            # Event nghe thử tốc độ điều chỉnh
            def make_preview_click(idx=segment.index):
                def on_click(e):
                    current_speed = self.slider_values[idx]
                    path = self.presenter.preview_adjusted_speed(idx, current_speed)
                    if path:
                        self._play_audio(path)
                    else:
                        self.notify("Không thể tạo file nghe thử.", "#D32F2F")
                return on_click

            # Event áp dụng điều chỉnh tốc độ
            def make_apply_click(idx=segment.index):
                def on_click(e):
                    current_speed = self.slider_values[idx]
                    self.presenter.apply_adjusted_speed(idx, current_speed)
                    self.expanded_segments.discard(idx)
                    self.collapsed_segments.discard(idx)
                    self.refresh()
                return on_click

            # Event hủy điều chỉnh tốc độ
            def make_cancel_click(idx=segment.index):
                def on_click(e):
                    self.presenter.cancel_adjusted_speed(idx)
                    self.collapsed_segments.add(idx)
                    self.expanded_segments.discard(idx)
                    self.refresh()
                return on_click

            panel_row = ft.Row(
                spacing=10,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Tốc độ:", size=13, color=ft.Colors.BLUE_GREY_300),
                    slider,
                    speed_text,
                    ft.IconButton(
                        icon=ft.Icons.VOLUME_UP_ROUNDED,
                        icon_color=ACCENT,
                        icon_size=18,
                        tooltip="Nghe thử",
                        on_click=make_preview_click(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CHECK_ROUNDED,
                        icon_color=ft.Colors.GREEN_700,
                        icon_size=18,
                        tooltip="Áp dụng",
                        on_click=make_apply_click(),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE_ROUNDED,
                        icon_color=ft.Colors.RED_700,
                        icon_size=18,
                        tooltip="Hủy",
                        on_click=make_cancel_click(),
                    ),
                ],
            )

            # Màu nền tương ứng trạng thái cho sinh động và premium
            row_bgcolor = SURFACE_BG
            if is_error:
                row_bgcolor = "#3a1c1c"
            elif is_warning:
                row_bgcolor = "#2e291b"

            rows.append(
                ft.Container(
                    bgcolor=row_bgcolor,
                    border_radius=8,
                    padding=8,
                    content=ft.Column(
                        spacing=5,
                        controls=[
                            ft.Row(
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    play_btn,
                                    ft.Text(str(segment.index), width=30, color=ft.Colors.BLUE_GREY_200, weight=ft.FontWeight.BOLD),
                                    ft.Text(
                                        f"[{segment.start_time} - {segment.end_time}]",
                                        width=150,
                                        color=ACCENT,
                                        selectable=True,
                                    ),
                                    ft.Text(f"M.tiêu: {segment.target_duration_sec:.2f}s" if segment.target_duration_sec < 999999.0 else "M.tiêu: --", width=95),
                                    ft.Text(f"Gốc: {raw}", width=80),
                                    ft.Text(f"Cuối: {final}", width=80),
                                    status_icon,
                                    tune_btn,
                                    restart_btn,
                                    import_btn,
                                    download_btn,
                                    copy_btn,
                                    ft.Text("" if (is_error and segment.audio_url) else segment.status, expand=True, color=ft.Colors.BLUE_GREY_400, size=12, selectable=True),
                                ],
                            ),
                            ft.Row(
                                controls=[
                                    ft.Container(width=180), # Lệch đầu dòng để thẳng với các nút
                                    panel_row
                                ],
                                visible=panel_visible
                            )
                        ],
                    ),
                )
            )
        return rows

    def _sync_controls(self) -> None:
        controls = self._controls
        if not controls:
            return

        controls["input_mode_dropdown"].value = self.input_mode
        controls["input_text_field"].value = self.input_text
        controls["input_text_row"].visible = (self.input_mode == "text")

        controls["input_srt_field"].value = self.input_srt
        controls["input_srt_row"].visible = (self.input_mode == "file")

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
        controls["capcut_cookie_field"].value = self.capcut_cookie
        controls["capcut_cookie_field"].visible = self.provider == "capcut" and self.capcut_version == "v2"
        controls["capcut_workspace_id_field"].value = self.capcut_workspace_id
        controls["capcut_workspace_id_field"].visible = self.provider == "capcut" and self.capcut_version == "v2"
        controls["capcut_version_dropdown"].value = self.capcut_version
        controls["capcut_version_dropdown"].visible = self.provider == "capcut"
        controls["capcut_device_id_field"].value = self.capcut_device_id
        controls["capcut_device_id_field"].visible = self.provider == "capcut" and self.capcut_version == "v1"
        controls["proxy_field"].value = self.proxy
        controls["proxy_field"].visible = self.provider == "capcut"
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
        if "advanced_toggle_btn" in controls:
            controls["advanced_toggle_btn"].icon = ft.Icons.KEYBOARD_ARROW_DOWN if not self.show_advanced else ft.Icons.KEYBOARD_ARROW_UP
        if "advanced_settings_container" in controls:
            controls["advanced_settings_container"].visible = self.show_advanced
        controls["stage_text"].value = self.stage_text
        controls["current_file_text"].value = self.current_file_text
        controls["progress_bar"].visible = self.progress_visible
        controls["progress_bar"].value = self.progress_value
        controls["progress_card"].visible = self.show_progress_card
        controls["result_list"].controls = self._build_result_rows()
        controls["line_count_text"].value = self.line_count_text
        controls["open_folder_button"].visible = self.open_folder_visible

        for key in (
            "input_mode_dropdown",
            "input_text_field",
            "choose_input_button",
            "choose_output_button",
            "reset_output_button",
            "provider_dropdown",
            "language_dropdown",
            "voice_dropdown",
            "api_key_field",
            "capcut_version_dropdown",
            "capcut_cookie_field",
            "capcut_workspace_id_field",
            "capcut_device_id_field",
            "proxy_field",
            "rate_slider",
            "volume_slider",
            "max_workers_slider",
            "start_button",
            "import_dir_button",
            "open_segments_button",
        ):
            controls[key].disabled = self.busy
        controls["start_button"].text = "Đang xử lý..." if self.busy else "Bắt đầu lồng tiếng"
        controls["start_button"].icon = ft.Icons.HOURGLASS_TOP if self.busy else ft.Icons.RECORD_VOICE_OVER

    def build(self, page: ft.Page) -> ft.Control:
        self._page = page
        self.presenter.maybe_prefill_latest_srt()

        input_mode_dropdown = ft.Dropdown(
            label="Chế Độ Nhập",
            value=self.input_mode,
            options=[
                ft.dropdown.Option(key="file", text="File phụ đề (SRT)"),
                ft.dropdown.Option(key="text", text="Nhập văn bản trực tiếp"),
            ],
            bgcolor=SURFACE_BG,
            border_radius=12,
            width=220,
        )
        input_text_field = ft.TextField(
            label="Văn Bản Cần Lồng Tiếng",
            value=self.input_text,
            hint_text="Nhập hoặc dán văn bản tại đây. Mỗi dòng sẽ là một phân đoạn lồng tiếng.",
            multiline=True,
            min_lines=5,
            max_lines=15,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
        )
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
        capcut_cookie_field = ft.TextField(
            label="CapCut Cookie",
            value=self.capcut_cookie,
            password=True,
            can_reveal_password=True,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self.provider == "capcut" and self.capcut_version == "v2",
        )
        capcut_workspace_id_field = ft.TextField(
            label="CapCut Workspace ID",
            value=self.capcut_workspace_id,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self.provider == "capcut" and self.capcut_version == "v2",
        )
        capcut_version_dropdown = ft.Dropdown(
            label="Phiên bản API",
            options=[
                ft.dropdown.Option(key="v1", text="V1"),
                ft.dropdown.Option(key="v2", text="V2"),
            ],
            value=self.capcut_version,
            border_radius=12,
            width=200,
            bgcolor=SURFACE_BG,
            visible=self.provider == "capcut",
        )
        capcut_device_id_field = ft.TextField(
            label="CapCut Device ID",
            value=self.capcut_device_id,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self.provider == "capcut" and self.capcut_version == "v1",
        )
        proxy_field = ft.TextField(
            label="Proxy URL",
            value=self.proxy,
            border_radius=12,
            expand=True,
            bgcolor=SURFACE_BG,
            visible=self.provider == "capcut",
            hint_text="host:port:username:password",
        )
        rate_value = ft.Text(f"{self.rate:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        volume_value = ft.Text(f"{self.volume:+d}%", color=ft.Colors.BLUE_GREY_100, width=58)
        max_workers_value = ft.Text(f"{self.max_workers} luồng", color=ft.Colors.BLUE_GREY_100, width=58)
        rate_slider = ft.Slider(min=-50, max=100, divisions=150, value=self.rate, label="{value}%", active_color=ACCENT)
        volume_slider = ft.Slider(min=-50, max=100, divisions=150, value=self.volume, label="{value}%", active_color=ACCENT)
        max_workers_slider = ft.Slider(min=1, max=10, divisions=9, value=self.max_workers, label="{value} luồng", active_color=ACCENT)
        keep_segments_checkbox = ft.Checkbox(label="Giữ segment lẻ", value=self.keep_segments, active_color=ACCENT)
        auto_merge_checkbox = ft.Checkbox(label="Tự động gộp âm thanh", value=self.auto_merge, active_color=ACCENT)

        def toggle_advanced(e: ft.ControlEvent) -> None:
            self.show_advanced = not self.show_advanced
            self._sync_controls()
            self.refresh()

        advanced_toggle_btn = ft.TextButton(
            "Cài đặt nâng cao (Tốc độ, Âm lượng, Số luồng)",
            icon=ft.Icons.KEYBOARD_ARROW_DOWN if not self.show_advanced else ft.Icons.KEYBOARD_ARROW_UP,
            on_click=toggle_advanced,
            style=ft.ButtonStyle(color=ACCENT),
        )

        advanced_settings_container = ft.Container(
            visible=self.show_advanced,
            padding=ft.Padding(left=8, top=4, right=8, bottom=8),
            content=ft.Column(
                spacing=16,
                controls=[
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
                ]
            )
        )

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
        result_list = ft.ListView(controls=self._build_result_rows(), spacing=8, height=480)
        line_count_text = ft.Text(self.line_count_text, color=ft.Colors.BLUE_GREY_100)

        choose_input_button = ft.OutlinedButton("Chọn SRT", icon=ft.Icons.SUBTITLES)
        input_srt_row = ft.Row([input_srt_field, choose_input_button], spacing=12)
        input_text_row = ft.Row([input_text_field], spacing=12)

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
        open_segments_button = ft.OutlinedButton(
            "Mở thư mục segment",
            icon=ft.Icons.FOLDER_ZIP_OUTLINED,
        )
        import_dir_button = ft.OutlinedButton(
            "Import thư mục segment",
            icon=ft.Icons.DRIVE_FOLDER_UPLOAD,
        )

        self._controls = {
            "import_dir_button": import_dir_button,
            "input_srt_row": input_srt_row,
            "input_text_row": input_text_row,
            "input_mode_dropdown": input_mode_dropdown,
            "input_text_field": input_text_field,
            "input_srt_field": input_srt_field,
            "output_dir_field": output_dir_field,
            "provider_dropdown": provider_dropdown,
            "language_dropdown": language_dropdown,
            "voice_dropdown": voice_dropdown,
            "api_key_field": api_key_field,
            "capcut_version_dropdown": capcut_version_dropdown,
            "capcut_cookie_field": capcut_cookie_field,
            "capcut_workspace_id_field": capcut_workspace_id_field,
            "capcut_device_id_field": capcut_device_id_field,
            "proxy_field": proxy_field,
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
            "advanced_toggle_btn": advanced_toggle_btn,
            "advanced_settings_container": advanced_settings_container,
            "choose_input_button": choose_input_button,
            "choose_output_button": choose_output_button,
            "reset_output_button": reset_output_button,
            "start_button": start_button,
            "merge_button": merge_button,
            "open_folder_button": open_folder_button,
            "open_segments_button": open_segments_button,
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

        def on_capcut_version_change(event: ft.ControlEvent) -> None:
            self.capcut_version = event.control.value or "v2"
            import json
            self.api_keys["capcut"] = json.dumps({
                "version": self.capcut_version,
                "cookie": self.capcut_cookie,
                "workspace_id": self.capcut_workspace_id,
                "device_id": self.capcut_device_id,
                "proxy": self.proxy
            })
            self.presenter.reload_voices()
            self.refresh()

        def on_capcut_cookie_change(event: ft.ControlEvent) -> None:
            self.capcut_cookie = event.control.value or ""
            import json
            self.api_keys["capcut"] = json.dumps({
                "version": self.capcut_version,
                "cookie": self.capcut_cookie,
                "workspace_id": self.capcut_workspace_id,
                "device_id": self.capcut_device_id,
                "proxy": self.proxy
            })

        def on_capcut_workspace_id_change(event: ft.ControlEvent) -> None:
            self.capcut_workspace_id = event.control.value or ""
            import json
            self.api_keys["capcut"] = json.dumps({
                "version": self.capcut_version,
                "cookie": self.capcut_cookie,
                "workspace_id": self.capcut_workspace_id,
                "device_id": self.capcut_device_id,
                "proxy": self.proxy
            })

        def on_capcut_device_id_change(event: ft.ControlEvent) -> None:
            self.capcut_device_id = event.control.value or ""
            import json
            self.api_keys["capcut"] = json.dumps({
                "version": self.capcut_version,
                "cookie": self.capcut_cookie,
                "workspace_id": self.capcut_workspace_id,
                "device_id": self.capcut_device_id,
                "proxy": self.proxy
            })

        def on_proxy_change(event: ft.ControlEvent) -> None:
            self.proxy = event.control.value or ""
            import json
            self.api_keys["capcut"] = json.dumps({
                "version": self.capcut_version,
                "cookie": self.capcut_cookie,
                "workspace_id": self.capcut_workspace_id,
                "device_id": self.capcut_device_id,
                "proxy": self.proxy
            })

        def on_input_mode_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_input_mode_change(event.control.value or "file")

        def on_input_text_change(event: ft.ControlEvent) -> None:
            self.presenter.handle_input_text_change(event.control.value or "")

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
            self.input_mode = input_mode_dropdown.value or self.input_mode
            self.input_text = input_text_field.value or ""
            self.provider = provider_dropdown.value or self.provider
            self.language = language_dropdown.value or self.language
            self.voice_id = voice_dropdown.value or self.voice_id
            if self.provider == "capcut":
                import json
                self.api_key = json.dumps({
                    "version": self.capcut_version,
                    "cookie": self.capcut_cookie,
                    "workspace_id": self.capcut_workspace_id,
                    "device_id": self.capcut_device_id,
                    "proxy": self.proxy
                })
            else:
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

        def open_segments_folder(_: ft.ControlEvent) -> None:
            try:
                segment_dir = self.presenter.get_segment_dir()
                if segment_dir.exists():
                    open_folder(str(segment_dir))
                else:
                    self.notify("Thư mục segment chưa được tạo hoặc đã bị xóa.", "#D32F2F")
            except Exception as exc:
                self.notify(f"Không thể mở thư mục segment: {exc}", "#D32F2F")

        input_mode_dropdown.on_select = on_input_mode_change
        input_text_field.on_change = on_input_text_change
        choose_input_button.on_click = choose_input
        choose_output_button.on_click = choose_output
        reset_output_button.on_click = reset_output
        provider_dropdown.on_select = on_provider_change
        language_dropdown.on_select = on_language_change
        voice_dropdown.on_select = on_voice_change
        api_key_field.on_change = on_api_key_change
        capcut_cookie_field.on_change = on_capcut_cookie_change
        capcut_workspace_id_field.on_change = on_capcut_workspace_id_change
        capcut_version_dropdown.on_select = on_capcut_version_change
        capcut_device_id_field.on_change = on_capcut_device_id_change
        proxy_field.on_change = on_proxy_change
        rate_slider.on_change = on_rate_change
        volume_slider.on_change = on_volume_change
        max_workers_slider.on_change = on_max_workers_change
        keep_segments_checkbox.on_change = on_keep_segments_change
        auto_merge_checkbox.on_change = on_auto_merge_change
        start_button.on_click = start_tts
        merge_button.on_click = merge_audio_action
        open_folder_button.on_click = open_output_folder
        open_segments_button.on_click = open_segments_folder

        def import_segment_dir(e: ft.ControlEvent) -> None:
            picked = pick_directory_native(self.output_dir or str(DEFAULT_TTS_OUTPUT_DIR))
            if picked:
                self.presenter.import_segment_directory(picked)

        import_dir_button.on_click = import_segment_dir

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
                                ft.Row([api_key_field, capcut_version_dropdown, capcut_cookie_field, capcut_workspace_id_field, capcut_device_id_field, proxy_field], spacing=12),
                                advanced_toggle_btn,
                                advanced_settings_container,
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
                                ft.Row([input_mode_dropdown], spacing=12),
                                input_srt_row,
                                input_text_row,
                                ft.Row([output_dir_field, choose_output_button, reset_output_button], spacing=12, visible=False),
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
                                        import_dir_button,
                                        open_segments_button,
                                        line_count_text,
                                    ]
                                ),
                                ft.Container(
                                    content=result_list,
                                    border=ft.Border.all(1, "#333333"),
                                    border_radius=8,
                                    padding=8,
                                    bgcolor=SURFACE_BG,
                                ),
                                status_text,
                            ],
                        ),
                    ),
                ],
            ),
        )
