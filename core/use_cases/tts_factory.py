from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.ports.tts import BaseTTSProvider

class TTSProviderFactory:
    @staticmethod
    def get_provider(provider_id: str, api_key: str | None = None) -> BaseTTSProvider:
        """
        Khởi tạo và trả về đúng thực thể TTS Provider dựa trên provider_id.
        """
        if provider_id == "edge-tts":
            from infrastructure.providers.tts.edge_tts_provider import EdgeTTSProvider
            return EdgeTTSProvider()
        elif provider_id == "gemini-tts":
            from infrastructure.providers.tts.gemini_tts_provider import GeminiTTSProvider
            return GeminiTTSProvider(api_key=api_key)
        else:
            raise ValueError(f"Nhà cung cấp TTS không được hỗ trợ: {provider_id}")
