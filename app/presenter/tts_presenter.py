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
        self.view.input_mode = str(config.get("input_mode") or "file")
        self.view.input_text = str(config.get("input_text") or "")
        if not self.view.auto_merge:
            self.view.keep_segments = True
        
        api_keys = config.get("api_keys")
        self.view.api_keys = dict(api_keys) if isinstance(api_keys, dict) else {}
        self.view.api_key = str(self.view.api_keys.get("gemini-tts") or "")
        
        # Load CapCut config
        capcut_key = str(self.view.api_keys.get("capcut") or "")
        self.view.capcut_version = "v2"
        self.view.capcut_cookie = ""
        self.view.capcut_workspace_id = ""
        self.view.capcut_device_id = ""
        self.view.proxy = ""
        if capcut_key:
            try:
                import json
                capcut_data = json.loads(capcut_key)
                self.view.capcut_version = capcut_data.get("version", "v2")
                self.view.capcut_cookie = capcut_data.get("cookie", "")
                self.view.capcut_workspace_id = capcut_data.get("workspace_id", "")
                self.view.capcut_device_id = capcut_data.get("device_id", "")
                self.view.proxy = capcut_data.get("proxy", "")
            except Exception:
                if ":" in capcut_key:
                    parts = capcut_key.split(":", 1)
                    self.view.capcut_workspace_id = parts[0]
                    self.view.capcut_cookie = parts[1]
                else:
                    self.view.capcut_cookie = capcut_key

        self.reload_voices()
        self.maybe_prefill_latest_srt()
        self.view.refresh()

    def _get_current_provider_api_key(self) -> str:
        provider = self.view.provider
        if provider == "capcut":
            import json
            return json.dumps({
                "version": getattr(self.view, "capcut_version", "v2"),
                "cookie": getattr(self.view, "capcut_cookie", ""),
                "workspace_id": getattr(self.view, "capcut_workspace_id", ""),
                "device_id": getattr(self.view, "capcut_device_id", ""),
                "proxy": getattr(self.view, "proxy", "")
            })
        return self.view.api_key

    def reload_voices(self) -> None:
        """Tải danh sách giọng đọc từ nhà cung cấp đã chọn."""
        try:
            api_key = self._get_current_provider_api_key()
            self.view.voices = self.service.list_voices(
                provider=self.view.provider,
                language=self.view.language,
                api_key=api_key,
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

    def handle_input_mode_change(self, input_mode: str) -> None:
        self.view.input_mode = input_mode
        self.view.refresh()

    def handle_input_text_change(self, input_text: str) -> None:
        self.view.input_text = input_text

    def start_tts(self) -> None:
        """Khởi động luồng xử lý chuyển đổi văn bản sang âm thanh."""
        if self.service.is_processing:
            self.view.status_text = "Đang có tác vụ lồng tiếng chạy, vui lòng đợi hoàn tất."
            self.view.refresh()
            return
        input_mode = getattr(self.view, "input_mode", "file")
        input_text = getattr(self.view, "input_text", "")
        if input_mode == "file" and not self.view.input_srt:
            self.view.status_text = "Vui lòng chọn file .srt đã dịch."
            self.view.refresh()
            return
        if input_mode == "text" and not input_text.strip():
            self.view.status_text = "Vui lòng nhập văn bản cần lồng tiếng."
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
        if self.view.provider == "capcut":
            version = getattr(self.view, "capcut_version", "v2")
            if version == "v2":
                if not getattr(self.view, "capcut_cookie", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Cookie."
                    self.view.refresh()
                    return
                if not getattr(self.view, "capcut_workspace_id", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Workspace ID."
                    self.view.refresh()
                    return
            elif version == "v1":
                if not getattr(self.view, "capcut_device_id", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Device ID."
                    self.view.refresh()
                    return

        self.view.show_progress_card = True
        self.view.progress_visible = True
        self.view.progress_value = None
        self.view.stage_text = "Đang khởi tạo..."
        self.view.current_file_text = "Văn bản trực tiếp" if input_mode == "text" else Path(self.view.input_srt).name
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
        api_key = self._get_current_provider_api_key()

        def worker() -> None:
            try:
                result = self.service.run_job(
                    input_srt=input_srt,
                    input_text=input_text,
                    input_mode=input_mode,
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
        input_mode = getattr(self.view, "input_mode", "file")
        if input_mode == "file" and not self.view.input_srt:
            self.view.status_text = "Vui lòng chọn file .srt đã dịch."
            self.view.refresh()
            return
        if input_mode == "text":
            self.view.status_text = "Chế độ nhập văn bản tự động gộp, không cần gộp thủ công."
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

    def get_segment_dir(self) -> Path:
        """Lấy đường dẫn thư mục lưu trữ các segment."""
        input_mode = getattr(self.view, "input_mode", "file")
        out_dir = Path(self.view.output_dir or "resources/layer/process").expanduser()
        if input_mode == "text":
            import hashlib
            text_bytes = (self.view.input_text or "").encode("utf-8")
            text_hash = hashlib.md5(text_bytes).hexdigest()[:8]
            source_stem = f"text_{text_hash}"
        else:
            source = Path(self.view.input_srt).expanduser()
            source_stem = source.stem
        return out_dir / f"{source_stem}_segments"

    def preview_adjusted_speed(self, segment_index: int, speed: float) -> Optional[str]:
        """Tạo file preview tạm thời với tốc độ mong muốn."""
        try:
            segment_dir = self.get_segment_dir()
            target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
            if not target_segment:
                return None

            raw_path = segment_dir / f"{segment_index:04d}_raw.mp3"
            if not raw_path.exists():
                if target_segment.file_path:
                    raw_path = Path(target_segment.file_path)
                else:
                    return None

            raw_duration = target_segment.raw_duration_sec or 1.0
            target_duration = raw_duration / speed
            preview_path = segment_dir / f"{segment_index:04d}_preview.mp3"

            from infrastructure.providers.tts.timing import adjust_speed
            adjust_speed(raw_path, preview_path, target_duration)
            return str(preview_path)
        except Exception as exc:
            print(f"[Preview Error] {exc}")
            return None

    def apply_adjusted_speed(self, segment_index: int, speed: float) -> None:
        """Áp dụng thay đổi tốc độ thực tế (ghi đè file timed)."""
        try:
            segment_dir = self.get_segment_dir()
            target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
            if not target_segment:
                self.view.notify("Không tìm thấy phân đoạn.", "#D32F2F")
                return

            raw_path = segment_dir / f"{segment_index:04d}_raw.mp3"
            if not raw_path.exists():
                if target_segment.file_path:
                    raw_path = Path(target_segment.file_path)
                else:
                    self.view.notify("Không tìm thấy tệp âm thanh gốc.", "#D32F2F")
                    return

            # Check if this segment uses raw only (e.g. imported)
            use_raw_only = bool(target_segment.is_imported)

            raw_duration = target_segment.raw_duration_sec or 1.0
            target_duration = raw_duration / speed

            from infrastructure.providers.tts.timing import adjust_speed, get_duration

            if use_raw_only:
                temp_raw_path = segment_dir / f"{segment_index:04d}_temp_raw.mp3"
                adjust_speed(raw_path, temp_raw_path, target_duration)
                
                # Replace the original raw_path with the adjusted audio
                import shutil
                if temp_raw_path.exists():
                    shutil.move(str(temp_raw_path), str(raw_path))

                # Update the segment
                new_duration = get_duration(raw_path)
                target_segment.file_path = str(raw_path)
                target_segment.raw_duration_sec = new_duration
                target_segment.final_duration_sec = new_duration
            else:
                timed_path = segment_dir / f"{segment_index:04d}_timed.mp3"
                adjust_speed(raw_path, timed_path, target_duration)

                # Update the segment
                target_segment.file_path = str(timed_path)
                target_segment.final_duration_sec = get_duration(timed_path)

            # Xóa file preview
            preview_path = segment_dir / f"{segment_index:04d}_preview.mp3"
            if preview_path.exists():
                try:
                    preview_path.unlink()
                except Exception as e:
                    print(f"[Apply Error] Không thể xóa file preview: {e}")

            self.view.notify(f"Đã áp dụng tốc độ {speed:.2f}x cho phân đoạn {segment_index}.", "#2E7D32")
            self.view.refresh()
        except Exception as exc:
            self.view.notify(f"Lỗi áp dụng tốc độ: {exc}", "#D32F2F")

    def cancel_adjusted_speed(self, segment_index: int) -> None:
        """Hủy bộ chỉnh tốc độ, khôi phục lại file gốc."""
        try:
            segment_dir = self.get_segment_dir()
            target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
            if not target_segment:
                return

            raw_path = segment_dir / f"{segment_index:04d}_raw.mp3"
            if raw_path.exists():
                target_segment.file_path = str(raw_path)
                target_segment.final_duration_sec = target_segment.raw_duration_sec

            # Xóa file preview
            preview_path = segment_dir / f"{segment_index:04d}_preview.mp3"
            if preview_path.exists():
                try:
                    preview_path.unlink()
                except Exception as e:
                    print(f"[Cancel Error] Không thể xóa file preview: {e}")

            self.view.refresh()
        except Exception as exc:
            print(f"[Cancel Error] {exc}")

    def regenerate_segment(self, segment_index: int) -> None:
        """Làm lại (Restart) phân đoạn đơn lẻ."""
        segment_dir = self.get_segment_dir()
        target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
        if not target_segment:
            self.view.notify("Không tìm thấy phân đoạn.", "#D32F2F")
            return

        # Lấy văn bản gốc của phân đoạn
        try:
            input_mode = getattr(self.view, "input_mode", "file")
            if input_mode == "text":
                lines = [line.strip() for line in (self.view.input_text or "").split("\n") if line.strip()]
                segment_text = lines[segment_index - 1]
            else:
                from infrastructure.providers.tts import parse_tts_segments
                srt_segments = parse_tts_segments(self.view.input_srt)
                segment_text = srt_segments[segment_index - 1].text
        except Exception as exc:
            self.view.notify(f"Không thể lấy văn bản gốc cho phân đoạn: {exc}", "#D32F2F")
            return

        self.set_busy(True)
        self.view.stage_text = f"Đang tạo lại phân đoạn {segment_index}..."
        self.view.refresh()

        # Gather current values from view
        provider = self.view.provider
        voice_id = self.view.voice_id
        rate = self.view.rate
        volume = self.view.volume
        pitch = self.view.pitch
        api_key = self._get_current_provider_api_key()

        def worker() -> None:
            try:
                # Call service to synthesize single segment
                new_seg = self.service.synthesize_single_segment(
                    index=segment_index,
                    text=segment_text,
                    start_time=target_segment.start_time,
                    end_time=target_segment.end_time,
                    target_duration_sec=target_segment.target_duration_sec,
                    segment_dir=segment_dir,
                    provider=provider,
                    voice_id=voice_id,
                    rate=rate,
                    volume=volume,
                    pitch=pitch,
                    api_key=api_key,
                )
                # Replace the segment in segments list
                for i, s in enumerate(self.view.segments):
                    if s.index == segment_index:
                        self.view.segments[i] = new_seg
                        break
                self.set_busy(False)
                self.view.stage_text = f"Đã làm lại xong phân đoạn {segment_index}"
                self.view.refresh()
                self.view.notify(f"Đã tạo lại phân đoạn {segment_index} thành công.", "#2E7D32")
            except Exception as exc:
                self.set_busy(False)
                target_segment.status = "error"
                target_segment.file_path = None
                target_segment.raw_duration_sec = None
                target_segment.final_duration_sec = None
                self.view.stage_text = f"Lỗi tạo lại phân đoạn {segment_index}"
                self.view.refresh()
                self.view.notify(f"Lỗi tạo lại phân đoạn {segment_index}", "#D32F2F")
                print(f"[TTS Error] Lỗi tạo lại phân đoạn {segment_index}: {exc}")

        self.view.run_in_thread(worker)

    def download_audio_url_manually(self, segment_index: int, audio_url: str) -> None:
        """Tải xuống thủ công từ CDN khi lấy được audio_url nhưng download bị timeout."""
        target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
        if not target_segment:
            self.view.notify("Không tìm thấy phân đoạn.", "#D32F2F")
            return

        segment_dir = self.get_segment_dir()
        if not segment_dir:
            self.view.notify("Thư mục lưu trữ không khả dụng.", "#D32F2F")
            return

        segment_dir.mkdir(parents=True, exist_ok=True)
        raw_path = segment_dir / f"{segment_index:04d}_raw.mp3"

        self.set_busy(True)
        self.view.stage_text = f"Đang tải lại âm thanh segment {segment_index}..."
        self.view.refresh()

        def worker() -> None:
            try:
                import requests
                proxies = None
                if self.view.proxy:
                    proxies = {"http": self.view.proxy, "https": self.view.proxy}
                
                # Thực hiện tải xuống
                res = requests.get(audio_url, proxies=proxies, timeout=45)
                res.raise_for_status()
                
                # Ghi file
                raw_path.write_bytes(res.content)

                # Cập nhật thời lượng
                from infrastructure.providers.tts import get_duration
                raw_duration = get_duration(raw_path)
                
                # Cập nhật trạng thái segment
                target_segment.file_path = str(raw_path)
                target_segment.raw_duration_sec = raw_duration
                target_segment.final_duration_sec = raw_duration
                target_segment.status = "done"

                self.view.refresh()
                self.view.notify(f"Tải thành công segment {segment_index}!", "#2E7D32")
            except Exception as exc:
                self.view.notify(f"Lỗi khi tải segment {segment_index}: {exc}", "#D32F2F")
            finally:
                self.set_busy(False)
                self.view.stage_text = "--"
                self.view.refresh()

        self.view.run_in_thread(worker)

    def import_segment_audio(self, segment_index: int, source_audio_path: str) -> None:
        """Import file âm thanh ngoài thay thế cho phân đoạn hiện tại."""
        target_segment = next((s for s in self.view.segments if s.index == segment_index), None)
        if not target_segment:
            self.view.notify("Không tìm thấy phân đoạn.", "#D32F2F")
            return

        src_path = Path(source_audio_path)
        if not src_path.exists() or not src_path.is_file():
            self.view.notify("File âm thanh nguồn không tồn tại.", "#D32F2F")
            return

        self.set_busy(True)
        self.view.stage_text = f"Đang import âm thanh segment {segment_index}..."
        self.view.refresh()

        def worker() -> None:
            try:
                segment_dir = self.get_segment_dir()
                segment_dir.mkdir(parents=True, exist_ok=True)
                
                raw_path = segment_dir / f"{segment_index:04d}_raw.mp3"
                timed_path = segment_dir / f"{segment_index:04d}_timed.mp3"

                import shutil
                if src_path.suffix.lower() == ".mp3":
                    shutil.copy2(src_path, raw_path)
                else:
                    from infrastructure.providers.tts.composer import convert_to_mp3
                    convert_to_mp3(src_path, raw_path)
                
                # Delete timed_path if it exists to keep only raw
                if timed_path.exists():
                    try:
                        timed_path.unlink()
                    except Exception:
                        pass

                from infrastructure.providers.tts import get_duration
                duration = get_duration(raw_path)

                target_segment.file_path = str(raw_path)
                target_segment.raw_duration_sec = duration
                target_segment.final_duration_sec = duration
                target_segment.is_imported = True
                target_segment.status = "done"

                self.view.refresh()
                self.view.notify(f"Đã import thành công file âm thanh cho phân đoạn {segment_index}!", "#2E7D32")
            except Exception as exc:
                self.view.notify(f"Lỗi khi import âm thanh: {exc}", "#D32F2F")
            finally:
                self.set_busy(False)
                self.view.stage_text = "--"
                self.view.refresh()

        self.view.run_in_thread(worker)

    def import_segment_directory(self, import_dir_path: str) -> None:
        """Import toàn bộ thư mục chứa các file âm thanh phân đoạn."""
        import_dir = Path(import_dir_path)
        if not import_dir.exists() or not import_dir.is_dir():
            self.view.notify("Thư mục import không tồn tại.", "#D32F2F")
            return

        self.set_busy(True)
        self.view.stage_text = "Đang import thư mục segment..."
        self.view.refresh()

        def worker() -> None:
            try:
                import re
                import shutil
                from infrastructure.providers.tts import get_duration
                from infrastructure.providers.tts.models import GeneratedSegment

                segment_dir = self.get_segment_dir()
                segment_dir.mkdir(parents=True, exist_ok=True)

                # Gom nhóm các file theo index
                files_by_idx = {}
                for f in import_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
                        match = re.search(r'\d+', f.name)
                        if match:
                            idx = int(match.group(0))
                            if idx not in files_by_idx:
                                files_by_idx[idx] = []
                            files_by_idx[idx].append(f)

                if not files_by_idx:
                    self.view.notify("Không tìm thấy file âm thanh hợp lệ trong thư mục chọn.", "#D32F2F")
                    return

                # Chuyển đổi list segments hiện tại thành dict để dễ tra cứu/cập nhật
                existing_segments = {s.index: s for s in self.view.segments}
                imported_count = 0

                def format_seconds_to_srt(seconds: float) -> str:
                    h = int(seconds // 3600)
                    m = int((seconds % 3600) // 60)
                    s = int(seconds % 60)
                    ms = int(round((seconds - int(seconds)) * 1000))
                    if ms >= 1000:
                        ms = 999
                    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

                for idx, candidates in files_by_idx.items():
                    # Lựa chọn file tối ưu nhất cho index này
                    selected_file = None
                    # Ưu tiên các file chứa từ khóa "timed" hoặc "final"
                    for c in candidates:
                        if "timed" in c.name.lower() or "final" in c.name.lower():
                            selected_file = c
                            break
                    # Kế đến ưu tiên "raw" hoặc "speech"
                    if not selected_file:
                        for c in candidates:
                            if "raw" in c.name.lower() or "speech" in c.name.lower():
                                selected_file = c
                                break
                    # Fallback về file đầu tiên
                    if not selected_file:
                        selected_file = candidates[0]

                    # Thực hiện copy sang segment_dir của dự án
                    raw_path = segment_dir / f"{idx:04d}_raw.mp3"
                    timed_path = segment_dir / f"{idx:04d}_timed.mp3"

                    if selected_file.suffix.lower() == ".mp3":
                        shutil.copy2(selected_file, raw_path)
                    else:
                        from infrastructure.providers.tts.composer import convert_to_mp3
                        convert_to_mp3(selected_file, raw_path)
                    
                    # Delete timed_path if it exists to keep only raw
                    if timed_path.exists():
                        try:
                            timed_path.unlink()
                        except Exception:
                            pass

                    # Đo thời lượng và cập nhật hoặc tạo mới segment
                    duration = get_duration(raw_path)

                    if idx in existing_segments:
                        segment = existing_segments[idx]
                        segment.file_path = str(raw_path)
                        segment.raw_duration_sec = duration
                        segment.final_duration_sec = duration
                        segment.is_imported = True
                        segment.status = "done"
                    else:
                        # Tạo mới segment nếu chưa tồn tại
                        new_seg = GeneratedSegment(
                            index=idx,
                            start_time="00:00:00,000",
                            end_time=format_seconds_to_srt(duration),
                            target_duration_sec=duration,
                            raw_duration_sec=duration,
                            final_duration_sec=duration,
                            file_path=str(raw_path),
                            status="done",
                            is_imported=True
                        )
                        existing_segments[idx] = new_seg
                    imported_count += 1

                # Gán lại danh sách segment đã sắp xếp theo index
                sorted_segments = [existing_segments[k] for k in sorted(existing_segments.keys())]
                self.view.segments = sorted_segments
                self.update_line_count()

                # Đảm bảo slider_values cũng được khởi tạo cho các segment mới
                for segment in sorted_segments:
                    if segment.index not in self.view.slider_values:
                        self.view.slider_values[segment.index] = 1.0

                self.view.refresh()
                self.view.notify(f"Đã import thành công {imported_count} phân đoạn từ thư mục!", "#2E7D32")
            except Exception as exc:
                self.view.notify(f"Lỗi khi import thư mục: {exc}", "#D32F2F")
            finally:
                self.set_busy(False)
                self.view.stage_text = "--"
                self.view.refresh()

        self.view.run_in_thread(worker)
