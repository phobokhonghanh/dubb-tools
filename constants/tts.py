from pathlib import Path
from config.paths import Paths
from utils.loader import load_json_file

_TTS_JSON_PATH = Paths.CONFIG_DIR / "system" / "model_tts.json"
_LANGUAGES_JSON_PATH = Paths.CONFIG_DIR / "system" / "languages.json"

# Load languages
LANGUAGE_OPTIONS = load_json_file(_LANGUAGES_JSON_PATH)

# Load TTS config
_tts_providers = load_json_file(_TTS_JSON_PATH)

DEFAULT_TTS_PROVIDER = "edge-tts"
for p in _tts_providers:
    if p.get("default"):
        DEFAULT_TTS_PROVIDER = p["provider"]
        break

GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"

GEMINI_VOICES = []
for p in _tts_providers:
    if p["provider"] == "gemini-tts":
        GEMINI_VOICES = [v["name"] for v in p.get("voices", [])]
        break

DEFAULT_VOICE_IDS = {}
for p in _tts_providers:
    prov_name = p["provider"]
    for v in p.get("voices", []):
        if v.get("default"):
            DEFAULT_VOICE_IDS[prov_name] = v["name"]
            break

CONFIG_PATH = Paths.CONFIG_DIR / "user" / "cf_tts.json"
