import json
from pathlib import Path
import pytest
from core.use_cases.tts_service import TtsService
from core.use_cases.translate_service import TranslateService

def test_tts_service_config_encryption(tmp_path):
    """Kiểm tra mã hóa/giải mã API key của TtsService."""
    config_file = tmp_path / "tts_config.json"
    service = TtsService(config_path=config_file)
    
    # 1. Trường hợp tương thích ngược: file config lưu key dạng thô (cleartext)
    raw_config = {
        "provider": "gemini-tts",
        "api_keys": {
            "gemini-tts": "my-plain-gemini-tts-key"
        }
    }
    config_file.write_text(json.dumps(raw_config), encoding="utf-8")
    
    # Đọc cấu hình -> Key phải khớp chính xác
    loaded = service.load_config()
    assert loaded["api_keys"]["gemini-tts"] == "my-plain-gemini-tts-key"
    
    # 2. Ghi cấu hình -> Key ghi xuống file phải được mã hóa
    service.save_config(loaded)
    
    # Đọc file thô từ đĩa
    raw_file_content = json.loads(config_file.read_text(encoding="utf-8"))
    encrypted_val = raw_file_content["api_keys"]["gemini-tts"]
    assert encrypted_val != "my-plain-gemini-tts-key"
    assert encrypted_val.startswith("gAAAAA")  # Định dạng token Fernet mặc định
    
    # 3. Đọc lại từ cấu hình đã mã hóa -> Phải giải mã tự động
    service2 = TtsService(config_path=config_file)
    loaded2 = service2.load_config()
    assert loaded2["api_keys"]["gemini-tts"] == "my-plain-gemini-tts-key"


def test_translate_service_config_encryption(tmp_path):
    """Kiểm tra mã hóa/giải mã API key của TranslateService."""
    config_file = tmp_path / "translator_config.json"
    service = TranslateService(config_path=config_file)
    
    # 1. Tương thích ngược: file chứa api key dạng thô
    raw_config = {
        "provider": "gemini",
        "gemini_api_key": "my-plain-gemini-key",
        "api_keys": {
            "gemini-2.0-flash": "another-plain-key"
        }
    }
    config_file.write_text(json.dumps(raw_config), encoding="utf-8")
    
    # Đọc cấu hình -> Phải giải mã
    loaded = service.load_config()
    assert loaded["gemini_api_key"] == "my-plain-gemini-key"
    assert loaded["api_keys"]["gemini-2.0-flash"] == "another-plain-key"
    
    # 2. Ghi cấu hình -> Phải mã hóa tự động
    service.save_config(loaded)
    
    # Đọc file thô từ đĩa
    raw_file_content = json.loads(config_file.read_text(encoding="utf-8"))
    assert raw_file_content["gemini_api_key"] != "my-plain-gemini-key"
    assert raw_file_content["gemini_api_key"].startswith("gAAAAA")
    assert raw_file_content["api_keys"]["gemini-2.0-flash"] != "another-plain-key"
    assert raw_file_content["api_keys"]["gemini-2.0-flash"].startswith("gAAAAA")
    
    # 3. Đọc lại cấu hình đã mã hóa -> Tự động giải mã
    service2 = TranslateService(config_path=config_file)
    loaded2 = service2.load_config()
    assert loaded2["gemini_api_key"] == "my-plain-gemini-key"
    assert loaded2["api_keys"]["gemini-2.0-flash"] == "another-plain-key"
