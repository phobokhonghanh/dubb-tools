import pytest
from core.ports.translator import BaseTranslator

def test_base_translator_cannot_be_instantiated():
    """Kiểm tra không thể khởi tạo trực tiếp lớp abstract BaseTranslator."""
    with pytest.raises(TypeError) as excinfo:
        BaseTranslator()
    assert "Can't instantiate abstract class" in str(excinfo.value)
