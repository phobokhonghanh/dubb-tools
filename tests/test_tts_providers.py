import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Mock edge_tts module since it might not be installed or to avoid network
class MockCommunicate:
    def __init__(self, text, voice, rate, volume):
        self.text = text
        self.voice = voice
        self.rate = rate
        self.volume = volume

    async def save(self, output_path):
        # Viết file giả lập để vượt qua kiểm tra _ensure_audio_file
        Path(output_path).write_bytes(b"dummy audio")

sys.modules["edge_tts"] = MagicMock()
sys.modules["edge_tts"].Communicate = MockCommunicate

from infrastructure.providers.tts.edge_tts_provider import EdgeTTSProvider
from infrastructure.providers.tts.gemini_tts_provider import GeminiTTSProvider
from core.ports.tts import BaseTTSProvider

def test_edge_tts_provider_inheritance():
    """Kiểm tra EdgeTTSProvider kế thừa đúng BaseTTSProvider."""
    provider = EdgeTTSProvider()
    assert isinstance(provider, BaseTTSProvider)

def test_edge_tts_provider_list_voices():
    """Kiểm tra hàm list_voices của EdgeTTSProvider."""
    provider = EdgeTTSProvider()
    # Mocking cache để tránh list_voices thật chạy
    provider._voice_cache = []
    voices = provider.list_voices("vi")
    assert isinstance(voices, list)

def test_edge_tts_provider_synthesize_segment(tmp_path):
    """Kiểm tra EdgeTTSProvider tạo audio thành công (mock)."""
    provider = EdgeTTSProvider()
    output_file = tmp_path / "test.mp3"
    
    res = provider.synthesize_segment(
        text="Xin chào Việt Nam",
        voice_id="vi-VN-HoaiMyNeural",
        output_path=output_file,
        rate=0,
        volume=0,
        pitch=0
    )
    assert res == output_file
    assert output_file.exists()
    assert output_file.read_bytes() == b"dummy audio"

def test_gemini_tts_provider_inheritance():
    """Kiểm tra GeminiTTSProvider kế thừa đúng BaseTTSProvider."""
    provider = GeminiTTSProvider(api_key="mock-api-key")
    assert isinstance(provider, BaseTTSProvider)

def test_gemini_tts_provider_list_voices():
    """Kiểm tra danh sách giọng nói của GeminiTTSProvider."""
    provider = GeminiTTSProvider(api_key="mock-api-key")
    voices = provider.list_voices("vi")
    assert len(voices) > 0
    assert voices[0].provider == "gemini-tts"

@patch("google.genai.Client")
def test_gemini_tts_provider_synthesize_segment(mock_client_class, tmp_path):
    """Kiểm tra GeminiTTSProvider tạo audio thành công (mock Client)."""
    # Cấu hình mock cho client.models.generate_content_stream
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    
    mock_chunk = MagicMock()
    mock_chunk.parts = [MagicMock()]
    mock_chunk.parts[0].inline_data.data = b"gemini audio raw bytes"
    mock_chunk.parts[0].inline_data.mime_type = "audio/mpeg"
    
    mock_client.models.generate_content_stream.return_value = [mock_chunk]
    
    provider = GeminiTTSProvider(api_key="mock-api-key")
    output_file = tmp_path / "test_gemini.mp3"
    
    res = provider.synthesize_segment(
        text="Hello world",
        voice_id="Orus",
        output_path=output_file,
        rate=0,
        volume=0,
        pitch=0
    )
    
    assert res == output_file
    assert output_file.exists()
    assert output_file.read_bytes() == b"gemini audio raw bytes"

def test_tts_provider_factory():
    """Kiểm tra TTSProviderFactory khởi tạo đúng các provider tương ứng."""
    from core.use_cases.tts_factory import TTSProviderFactory
    from infrastructure.providers.tts.edge_tts_provider import EdgeTTSProvider
    from infrastructure.providers.tts.gemini_tts_provider import GeminiTTSProvider

    edge_provider = TTSProviderFactory.get_provider("edge-tts")
    assert isinstance(edge_provider, EdgeTTSProvider)

    gemini_provider = TTSProviderFactory.get_provider("gemini-tts", api_key="test")
    assert isinstance(gemini_provider, GeminiTTSProvider)

    with pytest.raises(ValueError) as excinfo:
        TTSProviderFactory.get_provider("unknown-provider")
    assert "không được hỗ trợ" in str(excinfo.value)
