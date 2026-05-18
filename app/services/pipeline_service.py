from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event, Lock
from typing import Callable, Optional

from utils.pipeline_orchestrator import (
    DEFAULT_PIPELINE_WORKSPACE,
    PIPELINE_STEPS,
    PipelineConfig,
    PipelineProgress,
    PipelineResult,
    PipelineStepStatus,
    run_pipeline,
)


CONFIG_PATH = Path("config/pipeline_config.json")


@dataclass
class PipelineCallbacks:
    on_progress: Optional[Callable[[PipelineProgress], None]] = None
    on_step_done: Optional[Callable[[PipelineStepStatus], None]] = None
    on_log: Optional[Callable[[str], None]] = None
    on_success: Optional[Callable[[PipelineResult], None]] = None
    on_error: Optional[Callable[[PipelineResult], None]] = None


def default_config() -> dict:
    return asdict(
        PipelineConfig(
            source_mode="url",
            selected_steps=list(PIPELINE_STEPS),
            workspace_root=str(DEFAULT_PIPELINE_WORKSPACE),
        )
    )


class PipelineService:
    def __init__(self, config_path: str | Path = CONFIG_PATH) -> None:
        self._lock = Lock()
        self._active = False
        self._stop_event = Event()
        self.config_path = Path(config_path)

    @property
    def is_processing(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def load_config(self) -> dict:
        config = default_config()
        if not self.config_path.exists():
            return config
        try:
            loaded = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return config
        if isinstance(loaded, dict):
            config.update({key: value for key, value in loaded.items() if key in config})
        return config

    def save_config(self, config: PipelineConfig | dict) -> None:
        data = self.load_config()
        values = asdict(config) if isinstance(config, PipelineConfig) else dict(config)
        data.update({key: value for key, value in values.items() if key in data})
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_config(self, values: dict) -> PipelineConfig:
        data = self.load_config()
        data.update({key: value for key, value in values.items() if key in data})
        if not isinstance(data.get("selected_steps"), list):
            data["selected_steps"] = list(PIPELINE_STEPS)
        return PipelineConfig(**data)

    def run_job(
        self,
        *,
        config: PipelineConfig,
        callbacks: Optional[PipelineCallbacks] = None,
    ) -> PipelineResult:
        with self._lock:
            if self._active:
                raise RuntimeError("Đang có pipeline chạy, vui lòng đợi hoàn tất.")
            self._active = True
            self._stop_event = Event()

        callbacks = callbacks or PipelineCallbacks()
        try:
            self.save_config(config)
            result = run_pipeline(
                config,
                on_progress=callbacks.on_progress,
                on_step_done=callbacks.on_step_done,
                on_log=callbacks.on_log,
                stop_event=self._stop_event,
            )
            if result.ok:
                if callbacks.on_success:
                    callbacks.on_success(result)
            elif callbacks.on_error:
                callbacks.on_error(result)
            return result
        except Exception as exc:
            result = PipelineResult(
                ok=False,
                job_dir=None,
                context=None,
                steps=[],
                final_video=None,
                error_message=str(exc),
                elapsed_sec=0,
            )
            if callbacks.on_error:
                callbacks.on_error(result)
            return result
        finally:
            with self._lock:
                self._active = False
