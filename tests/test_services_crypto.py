import json
from pathlib import Path
import pytest
from core.use_cases.tts_service import TtsService
from core.use_cases.translate_service import TranslateService
from core.use_cases.pipeline_service import PipelineService

def test_tts_service_config_encryption(tmp_path):
    """Kiểm tra mã hóa/giải mã API keys của TtsService trực tiếp thông qua cf_tts.json."""
    config_file = tmp_path / "cf_tts.json"
    service = TtsService(config_path=config_file)
    
    # 1. Lưu cấu hình với api_keys dạng thô (cleartext)
    raw_config = {
        "provider": "gemini-tts",
        "api_keys": {
            "gemini-tts": "my-plain-gemini-tts-key"
        }
    }
    service.save_config(raw_config)
    
    # File cf_tts.json phải được tạo ra và lưu giá trị mã hóa
    assert config_file.exists()
    raw_file_content = json.loads(config_file.read_text(encoding="utf-8"))
    
    # Kiểm tra rằng key trong file đã được mã hóa (bắt đầu bằng gAAAAA) và không ở dạng cleartext
    models = raw_file_content["model"]
    gemini_model = next(item for item in models if item["provider"] == "gemini-tts")
    encrypted_val = gemini_model["key"]
    assert encrypted_val != "my-plain-gemini-tts-key"
    assert encrypted_val.startswith("gAAAAA")
    
    # 2. Đọc lại từ cấu hình -> Phải giải mã tự động
    loaded = service.load_config()
    assert loaded["api_keys"]["gemini-tts"] == "my-plain-gemini-tts-key"


def test_translator_service_config_encryption(tmp_path):
    """Kiểm tra mã hóa/giải mã API key của TranslateService thông qua cf_translators.json."""
    config_file = tmp_path / "cf_translators.json"
    service = TranslateService(config_path=config_file)
    
    default_cfg = service.default_config()
    assert default_cfg["api_key"] == ""
    
    # Lưu cấu hình với api_key dạng thô
    cfg = service.default_config()
    cfg["api_key"] = "my-plain-gemini-key"
    service.save_config(cfg)
    
    # File cf_translators.json phải lưu key mã hóa
    assert config_file.exists()
    raw_cf = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw_cf["api_key"] != "my-plain-gemini-key"
    assert raw_cf["api_key"].startswith("gAAAAA")
    
    # Đọc cấu hình -> Phải giải mã tự động
    loaded = service.load_config()
    assert loaded["api_key"] == "my-plain-gemini-key"


def test_pipeline_service_config_encryption(tmp_path):
    """Kiểm tra mã hóa/giải mã API keys của PipelineService trực tiếp trong pipeline_config.json."""
    config_file = tmp_path / "pipeline_config.json"
    service = PipelineService(config_path=config_file)

    # Ghi cấu hình dạng thô
    raw_config = {
        "source_mode": "local_video",
        "translate_api_key": "new-translate-key",
        "tts_api_key": "new-tts-key"
    }
    service.save_config(raw_config)

    # File pipeline_config.json phải lưu khóa dưới dạng mã hóa
    assert config_file.exists()
    raw_config_after_save = json.loads(config_file.read_text(encoding="utf-8"))
    
    assert raw_config_after_save["translate_api_key"] != "new-translate-key"
    assert raw_config_after_save["translate_api_key"].startswith("gAAAAA")
    assert raw_config_after_save["tts_api_key"] != "new-tts-key"
    assert raw_config_after_save["tts_api_key"].startswith("gAAAAA")

    # Đọc lại cấu hình -> Tự động giải mã thành công
    service2 = PipelineService(config_path=config_file)
    loaded2 = service2.load_config()
    assert loaded2["translate_api_key"] == "new-translate-key"
    assert loaded2["tts_api_key"] == "new-tts-key"
