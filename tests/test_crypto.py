import os
from pathlib import Path
from cryptography.fernet import Fernet
import pytest
from utils import crypto

def test_encrypt_decrypt_success():
    """Kiểm tra mã hóa và giải mã chuỗi thành công."""
    original_text = "my-secret-api-key-123"
    encrypted = crypto.encrypt(original_text)
    assert encrypted != original_text
    assert encrypted != ""
    
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == original_text

def test_decrypt_invalid_token_returns_none():
    """Kiểm tra việc giải mã chuỗi không hợp lệ hoặc cleartext trả về None."""
    invalid_token = "not-a-valid-fernet-token"
    decrypted = crypto.decrypt(invalid_token)
    assert decrypted is None

def test_get_or_create_key_from_env(monkeypatch, tmp_path):
    """Kiểm tra việc lấy khóa từ biến môi trường DUBB_ENCRYPTION_KEY."""
    # Reset cached key
    crypto._cached_key = None
    
    custom_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("DUBB_ENCRYPTION_KEY", custom_key)
    
    key = crypto._get_or_create_key()
    assert key == custom_key.encode("utf-8")
    
    # Clean up cached key
    crypto._cached_key = None

def test_get_or_create_key_from_file(monkeypatch, tmp_path):
    """Kiểm tra việc sinh khóa và đọc từ tệp tin khi không có biến môi trường."""
    # Mock KEY_FILE_PATH to a temp directory
    temp_key_file = tmp_path / ".key"
    monkeypatch.setattr(crypto, "KEY_FILE_PATH", temp_key_file)
    monkeypatch.delenv("DUBB_ENCRYPTION_KEY", raising=False)
    
    # Reset cached key
    crypto._cached_key = None
    
    # Lần đầu: sinh khóa và tạo file
    assert not temp_key_file.exists()
    key1 = crypto._get_or_create_key()
    assert temp_key_file.exists()
    assert key1 == temp_key_file.read_bytes()
    
    # Lần hai: đọc từ file hiện tại
    crypto._cached_key = None
    key2 = crypto._get_or_create_key()
    assert key1 == key2
    
    # Clean up cached key
    crypto._cached_key = None
