import os
import threading
from pathlib import Path
from cryptography.fernet import Fernet

from config.paths import Paths

KEY_FILE_PATH = Paths.CONFIG_DIR / ".key"

_cached_key = None
_key_lock = threading.Lock()

def _get_or_create_key() -> bytes:
    """
    Lấy khóa mã hóa từ biến môi trường DUBB_ENCRYPTION_KEY.
    Nếu không có, tìm kiếm trong tệp config/.key.
    Nếu không tồn tại tệp, tự sinh khóa ngẫu nhiên và ghi lại vào tệp config/.key.
    Thực hiện bảo vệ thread-safe bằng Lock.
    """
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    with _key_lock:
        if _cached_key is not None:
            return _cached_key

        # 1. Thử lấy từ biến môi trường
        env_key = os.environ.get("DUBB_ENCRYPTION_KEY")
        if env_key:
            try:
                key_bytes = env_key.encode("utf-8")
                # Kiểm tra tính hợp lệ của khóa Fernet
                Fernet(key_bytes)
                _cached_key = key_bytes
                return _cached_key
            except Exception:
                pass

        # 2. Thử lấy từ tệp config/.key
        if KEY_FILE_PATH.exists():
            try:
                key_bytes = KEY_FILE_PATH.read_bytes().strip()
                # Kiểm tra tính hợp lệ của khóa Fernet
                Fernet(key_bytes)
                _cached_key = key_bytes
                return _cached_key
            except Exception:
                pass

        # 3. Tự động sinh khóa mới nếu không có nguồn nào hợp lệ
        key_bytes = Fernet.generate_key()
        try:
            KEY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            KEY_FILE_PATH.write_bytes(key_bytes)
        except Exception:
            # Nếu lỗi không ghi được file (ví dụ phân quyền), giữ khóa trong memory
            pass
        _cached_key = key_bytes
        return _cached_key

def encrypt(plaintext: str) -> str:
    """
    Mã hóa một chuỗi văn bản thô bằng Fernet.
    Trả về chuỗi mã hóa dạng URL-safe base64.
    """
    if not plaintext:
        return ""
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        ciphertext = f.encrypt(plaintext.encode("utf-8"))
        return ciphertext.decode("utf-8")
    except Exception:
        return plaintext

def decrypt(ciphertext: str) -> str | None:
    """
    Giải mã một chuỗi văn bản đã được mã hóa bằng Fernet.
    Trả về chuỗi thô ban đầu. Nếu giải mã thất bại (lỗi khóa, chuỗi thô cũ), trả về None.
    """
    if not ciphertext:
        return ""
    try:
        key = _get_or_create_key()
        f = Fernet(key)
        plaintext = f.decrypt(ciphertext.encode("utf-8"))
        return plaintext.decode("utf-8")
    except Exception:
        return None
