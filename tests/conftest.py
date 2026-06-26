import os
import sys
from pathlib import Path
import pytest

# Thêm thư mục gốc của dự án vào sys.path để các module test có thể import đúng
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Mock môi trường kiểm thử
os.environ["DUBB_TESTING"] = "True"
os.environ["DUBB_ENCRYPTION_KEY"] = "test-encryption-key-must-be-32-bytes-long="

@pytest.fixture(autouse=True)
def block_external_sockets(monkeypatch):
    """
    Tự động chặn các kết nối Socket ra internet để đảm bảo kiểm thử tự động
    không bao giờ gọi API thật (Gemini API, Edge-TTS, v.v.).
    """
    import socket
    original_socket = socket.socket

    def guarded_socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
        # Cho phép AF_UNIX (socket cục bộ cho asyncio pipe) và chặn AF_INET/AF_INET6
        if family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError(
                "Cảnh báo: Đã phát hiện cuộc gọi mạng thực tế trong kiểm thử. "
                "Vui lòng mock toàn bộ các yêu cầu HTTP/gRPC bằng pytest-mock hoặc responses."
            )
        return original_socket(family, type, proto, fileno)

    monkeypatch.setattr(socket, "socket", guarded_socket)
    yield
