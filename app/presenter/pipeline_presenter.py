from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Optional

from core.use_cases.pipeline_service import PipelineCallbacks, PipelineService
from core.use_cases.translate_service import TranslateService
from core.use_cases.tts_service import TtsService
from core.use_cases.pipeline_orchestrator import (
    DEFAULT_PIPELINE_WORKSPACE,
    PIPELINE_STEPS,
    STEP_TITLES,
    PipelineConfig,
    PipelineProgress,
    PipelineResult,
    PipelineStepStatus,
)

from constants import DEFAULT_TTS_PROVIDER


def open_folder(path: str) -> None:
    if sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])  # noqa: S603,S607
    else:
        os.startfile(path)  # type: ignore[attr-defined]


class PipelinePresenter:
    def __init__(self, view: Any, service: Optional[PipelineService] = None) -> None:
        self.view = view
        self.service = service or PipelineService()
        self.translate_service = TranslateService()
        self.tts_service = TtsService()

    def init_presenter(self) -> None:
        """Khởi tạo trạng thái ban đầu của cấu hình từ Service và lưu vào View."""
        config = self.service.load_config()
        translator_config = self.translate_service.load_config()
        tts_config = self.tts_service.load_config()

        # Ánh xạ các cấu hình cấu hình sang view
        self.view.source_mode = str(config.get("source_mode") or "url")
        self.view.selected_steps = list(config.get("selected_steps") or PIPELINE_STEPS)
        self.view.workspace_root = str(config.get("workspace_root") or DEFAULT_PIPELINE_WORKSPACE)
        self.view.input_url = str(config.get("input_url") or "")
        self.view.local_video_path = str(config.get("local_video_path") or "")
        self.view.input_audio_path = str(config.get("input_audio_path") or "")
        self.view.input_srt_path = str(config.get("input_srt_path") or "")
        self.view.translated_srt_path = str(config.get("translated_srt_path") or "")
        self.view.merge_muted_video = str(config.get("merge_muted_video") or "")
        self.view.merge_speech_audio = str(config.get("merge_speech_audio") or "")
        self.view.merge_background_audio = str(config.get("merge_background_audio") or "")

        self.view.download_use_proxy = bool(config.get("download_use_proxy", True))
        self.view.stt_model_size = str(config.get("stt_model_size") or "base")
        self.view.stt_language = str(config.get("stt_language") or "auto")
        self.view.stt_speaker_mode = str(config.get("stt_speaker_mode") or "1 người nói")
        self.view.translate_batch_enabled = bool(config.get("translate_batch_enabled", True))
        self.view.translate_batch_size = str(config.get("translate_batch_size") or "10")
        self.view.stt_auto_normalize_enabled = bool(config.get("stt_auto_normalize_enabled", False))
        self.view.translate_model = str(config.get("translate_model") or translator_config.get("model") or self.translate_service.get_default_model())
        
        self.view.translate_api_key = str(
            config.get("translate_api_key")
            or translator_config.get("api_key")
            or translator_config.get("gemini_api_key")
            or ""
        )
        self.view.translate_target_language = str(
            config.get("translate_target_language") or translator_config.get("target_language") or "vi"
        )
        self.view.translate_content_safety = bool(
            config.get("translate_content_safety", translator_config.get("content_safety", False))
        )
        self.view.translate_replace_enabled = bool(config.get("translate_replace_enabled", False))
        self.view.translate_find_text = str(config.get("translate_find_text") or "")
        self.view.translate_replace_text = str(config.get("translate_replace_text") or "")

        self.view.tts_provider = str(config.get("tts_provider") or tts_config.get("provider") or DEFAULT_TTS_PROVIDER)
        self.view.tts_language = str(config.get("tts_language") or tts_config.get("language") or "vi")
        from constants.tts import DEFAULT_VOICE_IDS
        default_voice = DEFAULT_VOICE_IDS.get(self.view.tts_provider, "")
        self.view.tts_voice_id = str(config.get("tts_voice_id") or tts_config.get("voice_id") or default_voice)
        self.view.tts_rate = int(config.get("tts_rate") or tts_config.get("rate") or 0)
        self.view.tts_volume = int(config.get("tts_volume") or tts_config.get("volume") or 0)
        self.view.tts_pitch = int(config.get("tts_pitch") or tts_config.get("pitch") or 0)
        self.view.tts_keep_segments = bool(config.get("tts_keep_segments", tts_config.get("keep_segments", True)))
        tts_api_keys = tts_config.get("api_keys") if isinstance(tts_config.get("api_keys"), dict) else {}
        self.view.tts_api_key = str(config.get("tts_api_key") or tts_api_keys.get(self.view.tts_provider) or "")
        
        # Parse CapCut config if provider is capcut
        self.view.tts_capcut_cookie = ""
        self.view.tts_capcut_workspace_id = ""
        capcut_key = str(config.get("tts_api_key") or tts_api_keys.get("capcut") or "")
        if capcut_key:
            try:
                import json
                capcut_data = json.loads(capcut_key)
                self.view.tts_capcut_cookie = capcut_data.get("cookie", "")
                self.view.tts_capcut_workspace_id = capcut_data.get("workspace_id", "")
            except Exception:
                if ":" in capcut_key:
                    parts = capcut_key.split(":", 1)
                    self.view.tts_capcut_workspace_id = parts[0]
                    self.view.tts_capcut_cookie = parts[1]
                else:
                    self.view.tts_capcut_cookie = capcut_key
        
        self.reload_tts_voices()
        self.ensure_tts_voice()

        self.view.intro_video = str(config.get("intro_video") or "")
        self.view.outro_video = str(config.get("outro_video") or "")
        self.view.merge_output_name = str(config.get("merge_output_name") or "")
        self.view.merge_speech_volume = int(config.get("merge_speech_volume") or 100)
        self.view.merge_background_volume = int(config.get("merge_background_volume") or 125)

        self.view.busy = False
        self.view.job_dir = ""
        self.view.status_text = ""
        self.view.progress_value = 0
        self.view.progress_label = "Chưa chạy"
        self.view.logs = []
        self.view.step_statuses = {
            step: PipelineStepStatus(step=step, state="pending", message="Chờ chạy") for step in PIPELINE_STEPS
        }
        self.view.result = None
        self.view.failed_step = ""

        self.normalize_steps_for_source()
        self.restore_last_result()
        self.view.refresh()

    def reload_tts_voices(self) -> None:
        try:
            api_key = None
            if self.view.tts_provider == "gemini-tts":
                api_key = self.view.tts_api_key
            elif self.view.tts_provider == "capcut":
                import json
                api_key = json.dumps({
                    "cookie": getattr(self.view, "tts_capcut_cookie", ""),
                    "workspace_id": getattr(self.view, "tts_capcut_workspace_id", "")
                })
            self.view.tts_voices = self.tts_service.list_voices(
                provider=self.view.tts_provider,
                language=self.view.tts_language,
                api_key=api_key,
            )
        except Exception:
            self.view.tts_voices = []

    def ensure_tts_voice(self) -> None:
        if self.view.tts_voice_id and any(voice.id == self.view.tts_voice_id for voice in self.view.tts_voices):
            return
        self.view.tts_voice_id = self.view.tts_voices[0].id if self.view.tts_voices else ""

    def normalize_steps_for_source(self) -> None:
        steps = set(self.view.selected_steps)
        if self.view.source_mode == "url":
            steps.add("download")
        else:
            steps.discard("download")
            if not steps:
                steps.add("split")
        self.view.selected_steps = [step for step in PIPELINE_STEPS if step in steps]

    def first_selected_step(self) -> str:
        return self.view.selected_steps[0] if self.view.selected_steps else ""

    def restore_last_result(self) -> None:
        result = self.service.load_last_result()
        if not result or not result.job_dir:
            return
        self.view.result = result
        self.view.job_dir = result.job_dir
        self.view.failed_step = self._find_failed_step(result)
        for status in result.steps:
            self.view.step_statuses[status.step] = status

        if result.ok:
            self.view.progress_value = 1.0
            self.view.progress_label = "Lần chạy gần nhất đã hoàn thành"
            self.view.status_text = f"Job gần nhất: {result.final_video or result.job_dir}"
        else:
            completed = sum(1 for status in self.view.step_statuses.values() if status.state == "done")
            selected_count = max(len([step for step in PIPELINE_STEPS if step in self.view.selected_steps]), 1)
            self.view.progress_value = max(0.0, min(1.0, completed / selected_count))
            if self.view.failed_step:
                self.view.progress_label = f"Lần chạy gần nhất lỗi ở bước {STEP_TITLES.get(self.view.failed_step, self.view.failed_step)}"
                self.view.status_text = (
                    f"{result.error_message or 'Quy trình thất bại.'} "
                    "Bạn có thể chỉnh config rồi chạy lại từ bước lỗi."
                )
            else:
                self.view.progress_label = "Lần chạy gần nhất chưa hoàn thành"
                self.view.status_text = result.error_message or "Quy trình gần nhất chưa hoàn thành."

    def build_pipeline_config(self) -> PipelineConfig:
        return PipelineConfig(
            source_mode=self.view.source_mode,
            selected_steps=self.view.selected_steps,
            workspace_root=self.view.workspace_root,
            input_url=self.view.input_url,
            local_video_path=self.view.local_video_path,
            input_audio_path=self.view.input_audio_path,
            input_srt_path=self.view.input_srt_path,
            translated_srt_path=self.view.translated_srt_path,
            merge_muted_video=self.view.merge_muted_video,
            merge_speech_audio=self.view.merge_speech_audio,
            merge_background_audio=self.view.merge_background_audio,
            download_use_proxy=self.view.download_use_proxy,
            stt_model_size=self.view.stt_model_size,
            stt_language=self.view.stt_language,
            stt_speaker_mode=self.view.stt_speaker_mode,
            stt_auto_merge_enabled=False,
            stt_merge_group_size=1,
            stt_auto_normalize_enabled=self.view.stt_auto_normalize_enabled,
            translate_model=self.view.translate_model,
            translate_api_key=self.view.translate_api_key,
            translate_target_language=self.view.translate_target_language,
            translate_content_safety=self.view.translate_content_safety,
            translate_batch_enabled=self.view.translate_batch_enabled,
            translate_batch_size=self._positive_int(self.view.translate_batch_size, 10),
            translate_replace_enabled=self.view.translate_replace_enabled,
            translate_find_text=self.view.translate_find_text,
            translate_replace_text=self.view.translate_replace_text,
            tts_provider=self.view.tts_provider,
            tts_language=self.view.tts_language,
            tts_voice_id=self.view.tts_voice_id,
            tts_rate=self.view.tts_rate,
            tts_volume=self.view.tts_volume,
            tts_pitch=self.view.tts_pitch,
            tts_keep_segments=self.view.tts_keep_segments,
            tts_api_key=self.view.tts_api_key,
            intro_video=self.view.intro_video,
            outro_video=self.view.outro_video,
            merge_output_name=self.view.merge_output_name,
            merge_speech_volume=self.view.merge_speech_volume,
            merge_background_volume=self.view.merge_background_volume,
        )

    def start_pipeline(self) -> None:
        if self.service.is_processing:
            self.view.status_text = "Đang có quy trình chạy, vui lòng đợi hoàn tất."
            self.view.refresh()
            return

        self.sync_configs_to_services()
        config = self.build_pipeline_config()
        if "tts" in config.selected_steps:
            if config.tts_provider == "gemini-tts" and not config.tts_api_key.strip():
                self.view.status_text = "Vui lòng nhập Gemini TTS API key."
                self.view.refresh()
                return
            if config.tts_provider == "capcut":
                if not getattr(self.view, "tts_capcut_cookie", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Cookie."
                    self.view.refresh()
                    return
                if not getattr(self.view, "tts_capcut_workspace_id", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Workspace ID."
                    self.view.refresh()
                    return
        self.view.busy = True
        self.view.job_dir = ""
        self.view.progress_value = 0.0
        self.view.progress_label = "Đang chuẩn bị..."
        self.view.status_text = ""
        self.view.logs = []
        self.view.result = None
        self.view.failed_step = ""
        self.view.step_statuses = {
            step: PipelineStepStatus(
                step=step,
                state="pending" if step in config.selected_steps else "skipped",
                message="Chờ chạy" if step in config.selected_steps else "Không chọn",
            )
            for step in PIPELINE_STEPS
        }
        self.view.refresh()

        def ui_progress(progress: PipelineProgress) -> None:
            self.view.job_dir = progress.context.job_dir
            self.view.progress_value = max(0.0, min(1.0, progress.overall_percent / 100))
            self.view.progress_label = f"Bước {progress.step_index}/{progress.total_steps}: {STEP_TITLES.get(progress.current_step, progress.current_step)}"
            self.view.status_text = progress.message
            status = self.view.step_statuses.get(progress.current_step)
            if status and status.state in {"pending", "running"}:
                status.state = "running"
                status.message = progress.message
                status.percent = progress.step_percent
            self.view.refresh()

        def ui_step_done(status: PipelineStepStatus) -> None:
            self.view.step_statuses[status.step] = status
            self.view.refresh()

        def ui_success(result: PipelineResult) -> None:
            self.view.busy = False
            self.view.result = result
            self.view.failed_step = ""
            self.view.job_dir = result.job_dir or self.view.job_dir
            self.view.progress_value = 1.0
            self.view.progress_label = "Quy trình đã hoàn thành"
            self.view.status_text = f"Đã hoàn tất: {result.final_video or result.job_dir}"
            for status in result.steps:
                self.view.step_statuses[status.step] = status
            self.service.save_last_result(self._build_visible_result(result))
            self.view.refresh()
            self.view.notify("Quy trình đã hoàn thành.", "#2E7D32")

        def ui_error(result: PipelineResult) -> None:
            self.view.busy = False
            self.view.result = result
            self.view.failed_step = self._find_failed_step(result)
            self.view.job_dir = result.job_dir or self.view.job_dir
            if self.view.failed_step and result.context:
                self.view.status_text = (
                    f"{result.error_message or 'Quy trình thất bại.'} "
                    f"Sau khi chỉnh config, có thể chạy lại từ bước {STEP_TITLES.get(self.view.failed_step, self.view.failed_step)}."
                )
            else:
                self.view.status_text = result.error_message or "Quy trình thất bại."
            for status in result.steps:
                self.view.step_statuses[status.step] = status
            for step in PIPELINE_STEPS:
                current = self.view.step_statuses.get(step)
                if current and current.state == "pending":
                    current.state = "skipped"
                    current.message = "Đã dừng do quy trình gặp lỗi ở bước trước."
            self.service.save_last_result(self._build_visible_result(result))
            self.view.refresh()

        def ui_log(message: str) -> None:
            self.view.logs.append(message)
            self.view.refresh()

        callbacks = PipelineCallbacks(
            on_progress=ui_progress,
            on_step_done=ui_step_done,
            on_log=ui_log,
        )

        def worker() -> None:
            result = self.service.run_job(config=config, callbacks=callbacks)
            if result.ok:
                ui_success(result)
            else:
                ui_error(result)

        self.view.run_in_thread(worker)

    def retry_pipeline(self) -> None:
        if self.service.is_processing:
            self.view.status_text = "Đang có quy trình chạy, vui lòng đợi hoàn tất."
            self.view.refresh()
            return
        if not self.can_retry() or not self.view.result or not self.view.result.context:
            self.view.status_text = "Chưa có bước lỗi để chạy lại."
            self.view.refresh()
            return

        self.sync_configs_to_services()
        config = self.build_pipeline_config()
        if "tts" in config.selected_steps:
            if config.tts_provider == "gemini-tts" and not config.tts_api_key.strip():
                self.view.status_text = "Vui lòng nhập Gemini TTS API key."
                self.view.refresh()
                return
            if config.tts_provider == "capcut":
                if not getattr(self.view, "tts_capcut_cookie", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Cookie."
                    self.view.refresh()
                    return
                if not getattr(self.view, "tts_capcut_workspace_id", "").strip():
                    self.view.status_text = "Vui lòng nhập CapCut Workspace ID."
                    self.view.refresh()
                    return
        if self.view.failed_step not in config.selected_steps:
            self.view.status_text = "Vui lòng giữ bước lỗi trong danh sách bước để chạy lại."
            self.view.refresh()
            return

        self.view.busy = True
        self.view.progress_value = 0.0
        self.view.progress_label = f"Đang chuẩn bị chạy lại từ bước {STEP_TITLES.get(self.view.failed_step, self.view.failed_step)}..."
        self.view.status_text = ""
        self.view.logs.append(
            f"--- Chạy lại từ bước {STEP_TITLES.get(self.view.failed_step, self.view.failed_step)} bằng config mới ---"
        )
        self._mark_retry_steps(config)
        self.view.refresh()

        def ui_progress(progress: PipelineProgress) -> None:
            self.view.job_dir = progress.context.job_dir
            self.view.progress_value = max(0.0, min(1.0, progress.overall_percent / 100))
            self.view.progress_label = f"Bước {progress.step_index}/{progress.total_steps}: {STEP_TITLES.get(progress.current_step, progress.current_step)}"
            self.view.status_text = progress.message
            status = self.view.step_statuses.get(progress.current_step)
            if status and status.state in {"pending", "running"}:
                status.state = "running"
                status.message = progress.message
                status.percent = progress.step_percent
            self.view.refresh()

        def ui_step_done(status: PipelineStepStatus) -> None:
            self.view.step_statuses[status.step] = status
            self.view.refresh()

        def ui_success(result: PipelineResult) -> None:
            self.view.busy = False
            self.view.result = result
            self.view.failed_step = ""
            self.view.job_dir = result.job_dir or self.view.job_dir
            self.view.progress_value = 1.0
            self.view.progress_label = "Quy trình đã hoàn thành"
            self.view.status_text = f"Đã hoàn tất: {result.final_video or result.job_dir}"
            for status in result.steps:
                self.view.step_statuses[status.step] = status
            self.service.save_last_result(self._build_visible_result(result))
            self.view.refresh()
            self.view.notify("Quy trình đã hoàn thành.", "#2E7D32")

        def ui_error(result: PipelineResult) -> None:
            self.view.busy = False
            self.view.result = result
            self.view.failed_step = self._find_failed_step(result)
            self.view.job_dir = result.job_dir or self.view.job_dir
            if self.view.failed_step and result.context:
                self.view.status_text = (
                    f"{result.error_message or 'Quy trình thất bại.'} "
                    f"Sau khi chỉnh config, có thể chạy lại từ bước {STEP_TITLES.get(self.view.failed_step, self.view.failed_step)}."
                )
            else:
                self.view.status_text = result.error_message or "Quy trình thất bại."
            for status in result.steps:
                self.view.step_statuses[status.step] = status
            for step in PIPELINE_STEPS:
                current = self.view.step_statuses.get(step)
                if current and current.state == "pending":
                    current.state = "skipped"
                    current.message = "Đã dừng do quy trình gặp lỗi ở bước trước."
            self.service.save_last_result(self._build_visible_result(result))
            self.view.refresh()

        def ui_log(message: str) -> None:
            self.view.logs.append(message)
            self.view.refresh()

        callbacks = PipelineCallbacks(
            on_progress=ui_progress,
            on_step_done=ui_step_done,
            on_log=ui_log,
        )
        resume_context = self.view.result.context
        start_step = self.view.failed_step

        def worker() -> None:
            result = self.service.run_job(
                config=config,
                callbacks=callbacks,
                resume_context=resume_context,
                start_step=start_step,
            )
            if result.ok:
                ui_success(result)
            else:
                ui_error(result)

        self.view.run_in_thread(worker)

    def stop_pipeline(self) -> None:
        self.service.stop()
        self.view.status_text = "Đang yêu cầu dừng quy trình..."
        self.view.refresh()

    def open_job(self) -> None:
        if self.view.job_dir and Path(self.view.job_dir).exists():
            try:
                open_folder(self.view.job_dir)
            except Exception as exc:
                self.view.status_text = f"Không thể mở thư mục Job: {exc}"
                self.view.refresh()
        else:
            self.view.status_text = "Thư mục Job không tồn tại trên đĩa."
            self.view.refresh()

    def can_retry(self) -> bool:
        return bool(
            self.view.result
            and not self.view.result.ok
            and self.view.result.context
            and self.view.failed_step
        )

    @staticmethod
    def _find_failed_step(result: PipelineResult) -> str:
        for status in result.steps:
            if status.state == "error":
                return status.step
        return ""

    def _mark_retry_steps(self, config: PipelineConfig) -> None:
        should_reset = False
        for step in PIPELINE_STEPS:
            status = self.view.step_statuses.get(step, PipelineStepStatus(step=step))
            if step == self.view.failed_step:
                should_reset = True
            if step not in config.selected_steps:
                status.state = "skipped"
                status.message = "Không chọn"
                status.percent = None
                status.error_message = None
            elif should_reset:
                status.state = "pending"
                status.message = "Chờ chạy lại"
                status.percent = None
                status.error_message = None
            self.view.step_statuses[step] = status

    def _build_visible_result(self, base_result: PipelineResult) -> PipelineResult:
        steps = [
            self.view.step_statuses.get(step, PipelineStepStatus(step=step))
            for step in PIPELINE_STEPS
        ]
        return PipelineResult(
            ok=base_result.ok,
            job_dir=base_result.job_dir or self.view.job_dir or None,
            context=base_result.context or (self.view.result.context if self.view.result else None),
            steps=steps,
            final_video=base_result.final_video,
            error_message=base_result.error_message,
            elapsed_sec=base_result.elapsed_sec,
        )

    @staticmethod
    def _positive_int(value: str, default: int) -> int:
        try:
            return max(int(str(value).strip()), 1)
        except (TypeError, ValueError):
            return default

    def sync_configs_to_services(self) -> None:
        """Đồng bộ hóa cấu hình dịch thuật và lồng tiếng ngược lại các service tương ứng."""
        try:
            translate_config = {
                "model": self.view.translate_model,
                "api_key": self.view.translate_api_key,
                "target_language": self.view.translate_target_language,
                "content_safety": self.view.translate_content_safety,
            }
            self.translate_service.save_config(translate_config)
        except Exception:
            pass

        try:
            tts_config = {
                "provider": self.view.tts_provider,
                "language": self.view.tts_language,
                "rate": self.view.tts_rate,
                "volume": self.view.tts_volume,
                "pitch": self.view.tts_pitch,
                "keep_segments": self.view.tts_keep_segments,
            }
            current_tts_config = self.tts_service.load_config()
            api_keys = dict(current_tts_config.get("api_keys") or {})
            if self.view.tts_provider == "gemini-tts" and self.view.tts_api_key:
                api_keys["gemini-tts"] = self.view.tts_api_key
            elif self.view.tts_provider == "capcut" and self.view.tts_api_key:
                api_keys["capcut"] = self.view.tts_api_key
            tts_config["api_keys"] = api_keys
            
            if self.view.tts_voice_id:
                tts_config["voice_id"] = self.view.tts_voice_id

            self.tts_service.save_config(tts_config)
        except Exception:
            pass
