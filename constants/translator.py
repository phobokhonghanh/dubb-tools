from pathlib import Path
from config.paths import Paths
from utils.loader import load_json_file

_TRANSLATORS_JSON_PATH = Paths.CONFIG_DIR / "system" / "model_translators.json"
_LANGUAGES_JSON_PATH = Paths.CONFIG_DIR / "system" / "languages.json"
CONFIG_PATH = Paths.CONFIG_DIR / "user" / "cf_translators.json"

# Load languages
LANGUAGE_OPTIONS = load_json_file(_LANGUAGES_JSON_PATH)

# Load translator config
_translator_config = load_json_file(_TRANSLATORS_JSON_PATH)
DEFAULT_TRANSLATE_MODEL = _translator_config["default"]
TRANSLATE_MODELS = _translator_config["models"]


