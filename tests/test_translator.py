import pytest
from unittest.mock import MagicMock, patch
import json

from infrastructure.providers.translator.gemini import GeminiTranslator
from infrastructure.providers.translator.models import SrtSegment
from core.ports.translator import BaseTranslator

def test_gemini_translator_inheritance():
    """Kiểm tra GeminiTranslator kế thừa đúng BaseTranslator."""
    translator = GeminiTranslator(api_key="mock-key", model="gemini-2.5-flash")
    assert isinstance(translator, BaseTranslator)

def test_gemini_translator_empty_key():
    """Kiểm tra việc truyền key trống sẽ ném ra lỗi ValueError."""
    with pytest.raises(ValueError) as excinfo:
        GeminiTranslator(api_key="   ", model="gemini-2.5-flash")
    assert "Vui lòng nhập Gemini API key" in str(excinfo.value)

@patch("google.genai.Client")
def test_gemini_translator_translate_success(mock_client_class):
    """Kiểm tra việc dịch phụ đề thành công bằng mock Client."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    # Giả lập luồng kết quả stream trả về từ API dưới dạng JSON array
    mock_chunk = MagicMock()
    mock_chunk.text = json.dumps(["Xin chào", "Tạm biệt"])
    mock_client.models.generate_content_stream.return_value = [mock_chunk]
    
    translator = GeminiTranslator(api_key="mock-key", model="gemini-2.5-flash")
    
    segments = [
        SrtSegment(index=1, start_time="00:00:01,000", end_time="00:00:03,000", text="Hello"),
        SrtSegment(index=2, start_time="00:00:03,500", end_time="00:00:05,000", text="Goodbye"),
    ]
    
    res = translator.translate_segments(
        segments=segments,
        all_segments=segments,
        target_language="vi",
        content_safety=True,
        source_name="test.srt"
    )
    
    assert res == ["Xin chào", "Tạm biệt"]

@patch("google.genai.Client")
def test_gemini_translator_invalid_json(mock_client_class):
    """Kiểm tra khi AI không trả về định dạng JSON hợp lệ."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_chunk = MagicMock()
    mock_chunk.text = "Plain text response from AI, not JSON"
    mock_client.models.generate_content_stream.return_value = [mock_chunk]
    
    translator = GeminiTranslator(api_key="mock-key", model="gemini-2.5-flash")
    segments = [
        SrtSegment(index=1, start_time="00:00:01,000", end_time="00:00:03,000", text="Hello"),
    ]
    
    with pytest.raises(ValueError) as excinfo:
        translator.translate_segments(
            segments=segments,
            all_segments=segments,
            target_language="vi",
            content_safety=False,
            source_name="test.srt"
        )
    assert "không trả về JSON hợp lệ" in str(excinfo.value)

@patch("google.genai.Client")
def test_gemini_translator_incorrect_count(mock_client_class):
    """Kiểm tra khi AI trả về số lượng dòng dịch không khớp số dòng gốc."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_chunk = MagicMock()
    mock_chunk.text = json.dumps(["Chỉ có một dòng"])
    mock_client.models.generate_content_stream.return_value = [mock_chunk]
    
    translator = GeminiTranslator(api_key="mock-key", model="gemini-2.5-flash")
    segments = [
        SrtSegment(index=1, start_time="00:00:01,000", end_time="00:00:03,000", text="Hello"),
        SrtSegment(index=2, start_time="00:00:03,500", end_time="00:00:05,000", text="Goodbye"),
    ]
    
    with pytest.raises(ValueError) as excinfo:
        translator.translate_segments(
            segments=segments,
            all_segments=segments,
            target_language="vi",
            content_safety=False,
            source_name="test.srt"
        )
    assert "cần 2 dòng" in str(excinfo.value)
