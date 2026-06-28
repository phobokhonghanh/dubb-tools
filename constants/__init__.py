import json
from pathlib import Path
from config.paths import Paths
from utils.loader import load_json_file

from constants.translator import (
    DEFAULT_TRANSLATE_MODEL,
    TRANSLATE_MODELS,
    LANGUAGE_OPTIONS,
    CONFIG_PATH as TRANSLATOR_CONFIG_PATH,
)
from constants.tts import (
    DEFAULT_TTS_PROVIDER,
    GEMINI_TTS_MODEL,
    LANGUAGE_OPTIONS as TTS_LANGUAGE_OPTIONS,
    GEMINI_VOICES,
    CONFIG_PATH as TTS_CONFIG_PATH,
    DEFAULT_VOICE_IDS,
)

# ------------------------------------------------------------------
# Global configuration
# ------------------------------------------------------------------

_GLOBAL_JSON_PATH = Paths.CONFIG_DIR / "user" / "global.json"
_DEFAULT_OUTPUT_DIR = "resources/layer/process"


def _load_json(path: Path) -> dict:
    """Load JSON file. Return empty dict if file does not exist or is invalid."""
    try:
        return load_json_file(path)
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    """Save JSON file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def update_global_config(key: str, value) -> None:
    """Update a value in global.json."""
    data = _load_json(_GLOBAL_JSON_PATH)
    data[key] = value
    _save_json(_GLOBAL_JSON_PATH, data)


def _update_output_constants(dir_path: str) -> None:
    """Hot reload output directory constants."""
    import constants

    output = Path(dir_path)

    constants.DEFAULT_OUTPUT_DIR = output
    constants.DEFAULT_TRANSLATE_OUTPUT_DIR = output
    constants.DEFAULT_TTS_OUTPUT_DIR = output


# ------------------------------------------------------------------
# Load default output directory
# ------------------------------------------------------------------

_global_config = _load_json(_GLOBAL_JSON_PATH)

DEFAULT_OUTPUT_DIR = Path(
    _global_config.get("default_output_dir", _DEFAULT_OUTPUT_DIR)
)
DEFAULT_TRANSLATE_OUTPUT_DIR = DEFAULT_OUTPUT_DIR
DEFAULT_TTS_OUTPUT_DIR = DEFAULT_OUTPUT_DIR

# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def save_user_output_dir(dir_path: str) -> None:
    """Save user's default output directory."""
    if not dir_path:
        return

    update_global_config("default_output_dir", dir_path)
    _update_output_constants(dir_path)