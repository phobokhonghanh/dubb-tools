from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from core.use_cases.tts_service import TtsCallbacks, TtsService
from infrastructure.providers.tts import DEFAULT_TTS_OUTPUT_DIR, DEFAULT_TTS_PROVIDER, TtsProgress, TtsResult

if TYPE_CHECKING:
    pass

class TtsPresenter:
    def __init__(self, view: Any, service: Optional[TtsService] = None) -> None:
        self.view = view
        self.service = service or TtsService()
        
    def init_presenter(self) -> None:
        """Khởi tạo trạng thái ban đầu của cấu hình từ Service và lưu vào View."""
        config = self.service.load_config()
        self.view.provider = str(config.get("provider") or DEFAULT_TTS_PROVIDER)
        self.view.language = str(config.get("language") or "vi")
        self.view.voice_ids = dict(config.get("voice_ids") or {})
        self.view.voice_id = str(self.view.voice_ids.get(self.view.provider) or "")
        self.view.rate = int(config.get("rate") or 0)
        self.view.volume = int(config.get("volume") or 0)
        self.view.pitch = int(config.get("pitch") or 0)
        self.view.keep_segments = bool(config.get("keep_segments", True))
        self.view.auto_merge = bool(config.get("auto_merge", True))
        self.view.max_workers = int(config.get("max_workers") or 5)
        if not self.view.auto_merge:
            self.view.keep_segments = True
        
        api_keys = config.get("api_keys")
        self.view.api_keys = dict(api_keys) if isinstance(api_keys, dict) else {}
        self.view.api_key = str(self.view.api_keys.get("gemini-tts") or "")
        
        self.reload_voices()
        self.maybe_prefill_latest_srt()
        self.view.refresh()

    def reload_voices(self) -> None:
        """Tải danh sách giọng đọc từ nhà cung cấp đã chọn."""
        try:
            self.view.voices = self.service.list_voices(
                provider=self.view.provider,
                language=self.view.language,
                api_key=self.view.api_key if self.view.provider == "gemini-tts" else None,
            )
        except Exception:
            self.view.voices = []
        self.ensure_voice_selected()

    def ensure_voice_selected(self) -> None:
        """Đảm bảo luôn có giọng đọc hợp lệ được chọn."""
        if self.view.voice_id and any(voice.id == self.view.voice_id for voice in self.view.voices):
            return
        self.view.voice_id = self.view.voices[0].id if self.view.voices else ""
        self.view.voice_ids[self.view.provider] = self.view.voice_id

    def maybe_prefill_latest_srt(self) -> None:
        """Tự động điền file SRT đã dịch gần nhất nếu có."""
        if self.view.input_srt:
            return
        latest = self.find_latest_translated_srt()
        if latest:
            self.view.input_srt = str(latest)
            self.view.current_file_text = latest.name

    def find_latest_translated_srt(self) -> Optional[Path]:
        directory = Path(DEFAULT_TTS_OUTPUT_DIR).expanduser()
        if not directory.exists():
            return None
        preferred = [path for path in directory.glob("*_vi.srt") if path.is_file()]
        candidates = preferred or [path for path in directory.glob("*.srt") if path.is_file()]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def set_busy(self, busy: bool) -> None:
        self.view.busy = busy
        self.view.refresh()

    def update_line_count(self) -> None:
        self.view.line_count_text = f"Đã tạo: {len(self.view.segments)} segment"

    def handle_provider_change(self, provider: str) -> None:
        self.view.provider = provider
        self.reload_voices()
        self.view.refresh()

    def handle_language_change(self, language: str) -> None:
        self.view.language = language
        self.reload_voices()
        self.view.refresh()

    def handle_voice_change(self, voice_id: str) -> None:
        self.view.voice_id = voice_id
        self.view.voice_ids[self.view.provider] = voice_id
        self.view.refresh()

    def handle_api_key_change(self, api_key: str) -> None:
        self.view.api_key = api_key
        self.view.api_keys["gemini-tts"] = api_key

    def handle_rate_change(self, rate: int) -> None:
        self.view.rate = rate
        self.view.refresh()

    def handle_volume_change(self, volume: int) -> None:
        self.view.volume = volume
        self.view.refresh()

    def handle_max_workers_change(self, max_workers: int) -> None:
        self.view.max_workers = max_workers
        self.view.refresh()

    def handle_keep_segments_change(self, keep_segments: bool) -> None:
        self.view.keep_segments = keep_segments
        self.view.refresh()

    def handle_auto_merge_change(self, auto_merge: bool) -> None:
        self.view.auto_merge = auto_merge
        if not auto_merge:
            self.view.keep_segments = True
        self.view.refresh()

    def handle_srt_selected(self, picked_path: str) -> None:
        if Path(picked_path).suffix.lower() != ".srt":
            self.view.status_text = "Vui lòng chọn file .srt."
            self.view.refresh()
            return
        self.view.input_srt = picked_path
        self.view.current_file_text = Path(picked_path).name
        self.view.status_text = ""
        self.view.refresh()

    def handle_output_dir_selected(self, picked_dir: str) -> None:
        self.view.output_dir = picked_dir
        self.view.status_text = ""
        self.view.refresh()

    def handle_reset_output_dir(self) -> None:
        self.view.output_dir = str(DEFAULT_TTS_OUTPUT_DIR)
        self.view.status_text = ""
        self.view.refresh()

    def start_tts(self) -> None:
        """Khởi động luồng xử lý chuyển đổi văn bản sang âm thanh."""
        if self.service.is_processing:
            self.view.status_text = "Đang có tác vụ lồng tiếng chạy, vui lòng đợi hoàn tất."
            self.view.refresh()
            return
        if not self.view.input_srt:
            self.view.status_text = "Vui lòng chọn file .srt đã dịch."
            self.view.refresh()
            return
        if not self.view.voice_id:
            self.view.status_text = "Vui lòng chọn giọng đọc."
            self.view.refresh()
            return
        if self.view.provider == "gemini-tts" and not self.view.api_key.strip():
            self.view.status_text = "Vui lòng nhập Gemini API key."
            self.view.refresh()
            return

        self.view.show_progress_card = True
        self.view.progress_visible = True
        self.view.progress_value = None
        self.view.stage_text = "Đang khởi tạo..."
        self.view.current_file_text = Path(self.view.input_srt).name
        self.view.status_text = ""
        self.view.segments = []
        self.update_line_count()
        self.view.output_file = None
        self.view.open_folder_visible = False
        self.set_busy(True)

        def ui_progress(progress: TtsProgress) -> None:
            self.view.stage_text = progress.message
            self.view.progress_value = None if progress.percent is None else max(0.0, min(1.0, progress.percent / 100))
            self.view.refresh()

        def ui_segment_done(segments: list[Any]) -> None:
            self.view.segments = segments
            self.update_line_count()
            self.view.refresh()

        def ui_success(result: TtsResult) -> None:
            self.set_busy(False)
            self.view.segments = result.segments
            self.update_line_count()
            self.view.stage_text = "Hoàn tất"
            self.view.progress_value = 1.0
            self.view.progress_visible = True
            if result.output_file:
                self.view.status_text = f"Đã lưu: {result.output_file}"
                self.view.output_file = result.output_file
                self.view.open_folder_visible = True
            else:
                self.view.status_text = "Tạo phân đoạn lồng tiếng hoàn tất. Hãy bấm 'Gộp âm thanh' để gộp file tổng."
                self.view.output_file = None
                self.view.open_folder_visible = False
            self.view.refresh()
            self.view.notify("Lồng tiếng hoàn tất.", "#2E7D32")  # Màu xanh lá đậm đại diện cho GREEN_700

        def ui_error(err_msg: str, segments: list[Any]) -> None:
            self.set_busy(False)
            self.view.segments = segments
            self.update_line_count()
            self.view.status_text = err_msg or "Lồng tiếng thất bại."
            self.view.refresh()

        callbacks = TtsCallbacks(on_progress=ui_progress, on_segment_done=ui_segment_done)
        
        # Sao chép các biến để tránh xung đột luồng
        input_srt = self.view.input_srt
        output_dir = self.view.output_dir
        provider = self.view.provider
        language = self.view.language
        voice_id = self.view.voice_id
        rate = self.view.rate
        volume = self.view.volume
        pitch = self.view.pitch
        keep_segments = self.view.keep_segments
        auto_merge = self.view.auto_merge
        max_workers = self.view.max_workers
        api_key = self.view.api_key

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
                    auto_merge=auto_merge,
                    max_workers=max_workers,
                    api_key=api_key,
                    callbacks=callbacks,
                )
                if result.ok:
                    ui_success(result)
                else:
                    ui_error(result.error_message, result.segments)
            except Exception as exc:
                ui_error(str(exc), [])

        self.view.run_in_thread(worker)

    def merge_audio(self) -> None:
        """Gộp các segment riêng biệt thành file audio tổng chỉnh chu."""
        if not self.view.input_srt:
            self.view.status_text = "Vui lòng chọn file .srt đã dịch."
            self.view.refresh()
            return
        if not self.view.segments:
            self.view.status_text = "Không có phân đoạn nào để gộp."
            self.view.refresh()
            return

        self.view.show_progress_card = True
        self.view.progress_visible = True
        self.view.progress_value = None
        self.view.stage_text = "Đang gộp file audio tổng..."
        self.view.status_text = ""
        self.set_busy(True)

        input_srt = self.view.input_srt
        output_dir = self.view.output_dir
        generated_segments = self.view.segments

        def worker() -> None:
            try:
                output_file = self.service.merge_segments(
                    input_srt=input_srt,
                    output_dir=output_dir,
                    generated_segments=generated_segments,
                )
                self.set_busy(False)
                self.view.stage_text = "Gộp hoàn tất"
                self.view.progress_value = 1.0
                self.view.progress_visible = True
                self.view.status_text = f"Đã gộp thành công: {output_file}"
                self.view.output_file = output_file
                self.view.open_folder_visible = True
                self.view.refresh()
                self.view.notify("Gộp file lồng tiếng hoàn tất.", "#2E7D32")
            except Exception as exc:
                self.set_busy(False)
                self.view.status_text = f"Lỗi gộp file: {exc}"
                self.view.refresh()

        self.view.run_in_thread(worker)
