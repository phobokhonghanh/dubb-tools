import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.ports.tts import BaseTTSProvider
from infrastructure.providers.tts.capcut_provider import CapCutTTSProvider
from core.use_cases.tts_factory import TTSProviderFactory


def test_capcut_provider_inheritance():
    """Kiểm tra CapCutTTSProvider kế thừa đúng BaseTTSProvider."""
    provider = CapCutTTSProvider(api_key=json.dumps({"cookie": "test-cookie", "workspace_id": "123"}))
    assert isinstance(provider, BaseTTSProvider)


def test_capcut_provider_api_key_parsing():
    """Kiểm tra việc parse api_key định dạng JSON và fallback."""
    # JSON format
    provider = CapCutTTSProvider(api_key=json.dumps({"cookie": "my-cookie", "workspace_id": "999"}))
    assert provider.cookie == "my-cookie"
    assert provider.workspace_id == "999"

    # colon format
    provider2 = CapCutTTSProvider(api_key="888:other-cookie")
    assert provider2.workspace_id == "888"
    assert provider2.cookie == "other-cookie"

    # raw cookie format
    provider3 = CapCutTTSProvider(api_key="raw-cookie")
    assert provider3.cookie == "raw-cookie"
    assert provider3.workspace_id == ""


def test_capcut_provider_list_voices():
    """Kiểm tra hàm list_voices của CapCutTTSProvider."""
    provider = CapCutTTSProvider()
    voices = provider.list_voices()
    assert len(voices) >= 12
    assert voices[0].provider == "capcut"

    # Filtered language
    filtered = provider.list_voices("vi")
    assert len(filtered) >= 12


@patch("requests.post")
@patch("requests.get")
@patch("time.sleep", return_value=None)
def test_capcut_provider_synthesize_success(mock_sleep, mock_get, mock_post, tmp_path):
    """Kiểm tra CapCutTTSProvider tạo audio thành công."""
    api_key = json.dumps({"cookie": "valid-cookie", "workspace_id": "123456"})
    provider = CapCutTTSProvider(api_key=api_key)
    output_file = tmp_path / "test_capcut.mp3"

    # Mock Create Task response
    mock_create_response = MagicMock()
    mock_create_response.json.return_value = {
        "ret": 0,
        "errmsg": "success",
        "data": {
            "task_id": "task-uuid-111"
        }
    }
    
    # Mock Query Task response (status 2 = complete)
    mock_query_response = MagicMock()
    mock_query_response.json.return_value = {
        "ret": 0,
        "errmsg": "success",
        "data": {
            "status": 2,
            "task_detail": [
                {
                    "transcode_audio_info": [
                        {"url": "https://test-host.com/audio.mp3"}
                    ]
                }
            ]
        }
    }

    mock_post.side_effect = [mock_create_response, mock_query_response]

    # Mock Audio Download response
    mock_audio_response = MagicMock()
    mock_audio_response.content = b"capcut audio dummy bytes"
    mock_get.return_value = mock_audio_response

    res = provider.synthesize_segment(
        text="Xin chào",
        voice_id="7491607775621943824",
        output_path=output_file,
        rate=0,
        volume=0,
        pitch=0
    )

    assert res == output_file
    assert output_file.exists()
    assert output_file.read_bytes() == b"capcut audio dummy bytes"
    assert mock_post.call_count == 2
    mock_get.assert_called_once_with("https://test-host.com/audio.mp3", proxies=None, timeout=30)


@patch("requests.post")
@patch("time.sleep", return_value=None)
def test_capcut_provider_create_error(mock_sleep, mock_post, tmp_path):
    """Kiểm tra lỗi trả về khi gửi yêu cầu tạo task thất bại."""
    api_key = json.dumps({"cookie": "valid-cookie", "workspace_id": "123456"})
    provider = CapCutTTSProvider(api_key=api_key)
    output_file = tmp_path / "test_capcut_err.mp3"

    # Mock Create Task response with error
    mock_create_response = MagicMock()
    mock_create_response.json.return_value = {
        "ret": 1001,
        "errmsg": "Invalid cookie",
        "data": {}
    }
    mock_post.return_value = mock_create_response

    with pytest.raises(RuntimeError) as excinfo:
        provider.synthesize_segment(
            text="Xin chào",
            voice_id="7491607775621943824",
            output_path=output_file,
            rate=0,
            volume=0,
            pitch=0
        )
    assert "CapCut API Error (create)" in str(excinfo.value)
    assert "Invalid cookie" in str(excinfo.value)


def test_capcut_provider_factory():
    """Kiểm tra factory khởi tạo đúng CapCutTTSProvider."""
    capcut_provider = TTSProviderFactory.get_provider("capcut", api_key="dummy")
    assert isinstance(capcut_provider, CapCutTTSProvider)


@patch("requests.post")
@patch("requests.get")
@patch("time.sleep", return_value=None)
def test_capcut_v1_synthesize_success(mock_sleep, mock_get, mock_post, tmp_path):
    """Kiểm tra CapCutTTSProvider phiên bản V1 tạo audio thành công."""
    api_key = json.dumps({
        "version": "v1",
        "device_id": "test-device-123",
        "proxy": "http://127.0.0.1:8888"
    })
    provider = CapCutTTSProvider(api_key=api_key)
    output_file = tmp_path / "test_capcut_v1.mp3"

    # Mock Create response
    mock_create_response = MagicMock()
    mock_create_response.json.return_value = {
        "ret": 0,
        "errmsg": "success",
        "data": {
          "tasks": [
            {
              "id": "task-v1-id",
              "token": "task-v1-token"
            }
          ]
        }
    }

    # Mock Query response
    mock_query_response = MagicMock()
    mock_query_response.json.return_value = {
        "ret": 0,
        "errmsg": "success",
        "data": {
            "tasks": [
                {
                    "status": "succeed",
                    "payload": json.dumps({
                        "audio_subtitles": [
                            {"speech_url": "https://test-host.com/audio-v1.mp3"}
                        ]
                    })
                }
            ]
        }
    }

    mock_post.side_effect = [mock_create_response, mock_query_response]

    # Mock Audio Download response
    mock_audio_response = MagicMock()
    mock_audio_response.content = b"capcut v1 audio bytes"
    mock_get.return_value = mock_audio_response

    res = provider.synthesize_segment(
        text="Xin chào",
        voice_id="7102355709945188865",
        output_path=output_file,
        rate=0,
        volume=0,
        pitch=0
    )

    assert res == output_file
    assert output_file.exists()
    assert output_file.read_bytes() == b"capcut v1 audio bytes"
    assert mock_post.call_count == 2
    
    # Verify proxy was passed to post and get
    for call in mock_post.call_args_list:
        assert call.kwargs.get("proxies") == {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
    
    mock_get.assert_called_once_with(
        "https://test-host.com/audio-v1.mp3",
        proxies={"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"},
        timeout=30
    )


def test_capcut_voices_load():
    """Kiểm tra hàm load_voices_config nạp đúng giọng đọc từ JSON config."""
    provider = CapCutTTSProvider()
    voices = provider.list_voices()
    assert len(voices) > 0
    # verify at least the Cute Female or Nhỏ Ngọt Ngào exists in loaded voices
    assert any("Cute Female" in v.name or "Cô Gái Hoạt Ngôn" in v.name or "Nhỏ Ngọt Ngào" in v.name for v in voices)


def test_capcut_proxy_formatting():
    """Kiểm tra logic phân tích và chuẩn hóa cấu hình Proxy."""
    # 1. Format: host:port:username:password
    p1 = CapCutTTSProvider(api_key=json.dumps({"proxy": "1.2.3.4:8080:user123:pass123"}))
    assert p1.proxy == "http://user123:pass123@1.2.3.4:8080"

    # 2. Format: username:password:host:port
    p2 = CapCutTTSProvider(api_key=json.dumps({"proxy": "user123:pass123:1.2.3.4:8080"}))
    assert p2.proxy == "http://user123:pass123@1.2.3.4:8080"

    # 3. Format: host:port
    p3 = CapCutTTSProvider(api_key=json.dumps({"proxy": "1.2.3.4:8080"}))
    assert p3.proxy == "http://1.2.3.4:8080"

    # 4. Format: http://username:password@host:port (standard)
    p4 = CapCutTTSProvider(api_key=json.dumps({"proxy": "http://user123:pass123@1.2.3.4:8080"}))
    assert p4.proxy == "http://user123:pass123@1.2.3.4:8080"

    # 5. Format: https://host:port
    p5 = CapCutTTSProvider(api_key=json.dumps({"proxy": "https://1.2.3.4:8080"}))
    assert p5.proxy == "https://1.2.3.4:8080"


