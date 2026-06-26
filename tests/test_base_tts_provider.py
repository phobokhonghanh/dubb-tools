import pytest
from core.ports.tts import BaseTTSProvider

def test_base_tts_provider_cannot_be_instantiated():
    """Kiểm tra không thể khởi tạo trực tiếp lớp abstract BaseTTSProvider."""
    with pytest.raises(TypeError) as excinfo:
        BaseTTSProvider()
    assert "Can't instantiate abstract class" in str(excinfo.value)
