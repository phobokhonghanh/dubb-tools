from __future__ import annotations

import json
import random
import time
from pathlib import Path
import requests

from core.ports.tts import BaseTTSProvider
from infrastructure.providers.tts.models import TtsVoice

CAPCUT_VOICES = [
    TtsVoice(id="7491607775621943824", name="Trung Caha", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7493478233703191041", name="Nam Trầm", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7491608014181372417", name="Ly Nam", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7491608109043945985", name="Duy Bắc", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7491607926562361857", name="Hà Nữ", locale="vi-VN", gender="Female", provider="capcut"),
    TtsVoice(id="7491607853086544400", name="Sài Nữ", locale="vi-VN", gender="Female", provider="capcut"),
    TtsVoice(id="7483736167565758992", name="Anh Dũng", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7483736254694035984", name="Chí Mai", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7264854897953083905", name="Giọng nữ phổ thông", locale="vi-VN", gender="Female", provider="capcut"),
    TtsVoice(id="7252594014782755330", name="Sweet Little Girl", locale="vi-VN", gender="Female", provider="capcut"),
    TtsVoice(id="7102355803792740865", name="Confident Male", locale="vi-VN", gender="Male", provider="capcut"),
    TtsVoice(id="7102355709945188865", name="Cute Female", locale="vi-VN", gender="Female", provider="capcut"),
]

VOICE_MAPPING = {
    "7491607775621943824": {"speaker": "ueSxRO0nLF1bj93J2hVt", "speaker_name": "Trung Caha", "resource_id": "7491607775621943824"},
    "7493478233703191041": {"speaker": "9EE00wK5qV6tPtpQIxvy", "speaker_name": "Nam Trầm", "resource_id": "7493478233703191041"},
    "7491608014181372417": {"speaker": "7hsfEc7irDn6E8br0qfw", "speaker_name": "Ly Nam", "resource_id": "7491608014181372417"},
    "7491608109043945985": {"speaker": "1d5Bb0SMBPB10Gx6iQeu", "speaker_name": "Duy Bắc", "resource_id": "7491608109043945985"},
    "7491607926562361857": {"speaker": "pGapy9MNHCukzJtjavF0", "speaker_name": "Hà Nữ", "resource_id": "7491607926562361857"},
    "7491607853086544400": {"speaker": "xPEfmymXC4WdBxGMznS7", "speaker_name": "Sài Nữ", "resource_id": "7491607853086544400"},
    "7483736167565758992": {"speaker": "BV560_streaming", "speaker_name": "Anh Dũng", "resource_id": "7483736167565758992"},
    "7483736254694035984": {"speaker": "BV562_streaming", "speaker_name": "Chí Mai", "resource_id": "7483736254694035984"},
    "7264854897953083905": {"speaker": "vi_female_huong", "speaker_name": "Giọng nữ phổ thông", "resource_id": "7264854897953083905"},
    "7252594014782755330": {"speaker": "BV421_vivn_streaming", "speaker_name": "Sweet Little Girl", "resource_id": "7252594014782755330"},
    "7102355803792740865": {"speaker": "BV075_streaming", "speaker_name": "Confident Male", "resource_id": "7102355803792740865"},
    "7102355709945188865": {"speaker": "BV074_streaming", "speaker_name": "Cute Female", "resource_id": "7102355709945188865"},
}


class CapCutTTSProvider(BaseTTSProvider):
    provider_id = "capcut"

    def __init__(self, api_key: str | None = None) -> None:
        self.cookie = ""
        self.workspace_id = ""
        if api_key:
            try:
                data = json.loads(api_key)
                self.cookie = data.get("cookie", "")
                self.workspace_id = data.get("workspace_id", "")
            except Exception:
                if ":" in api_key:
                    parts = api_key.split(":", 1)
                    self.workspace_id = parts[0]
                    self.cookie = parts[1]
                else:
                    self.cookie = api_key

    def list_voices(self, language: str | None = None) -> list[TtsVoice]:
        if not language:
            return CAPCUT_VOICES
        prefix = language.lower()
        filtered = [v for v in CAPCUT_VOICES if v.locale.lower().startswith(prefix)]
        return filtered or CAPCUT_VOICES

    def synthesize_segment(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: int,
        volume: int,
        pitch: int,
    ) -> Path:
        if not self.cookie or not self.workspace_id:
            raise ValueError("Vui lòng cung cấp Cookie và Workspace ID hợp lệ cho CapCut TTS.")

        info = VOICE_MAPPING.get(voice_id) or VOICE_MAPPING["7102355709945188865"]
        speaker = info["speaker"]
        speaker_name = info["speaker_name"]
        resource_id = info["resource_id"]

        create_url = "https://web-edit.us.capcut.com/lv/v2/intelligence/create?babi_param=%7B%22scenario%22%3A%22video_editor%22%2C%22feature_key%22%3A%22text_to_speech%22%2C%22feature_entrance%22%3A%22tool%22%2C%22feature_entrance_detail%22%3A%22tool-feature-text_to_speech%22%7D&aid=348188&device_platform=web&region=US&web_id=7655527138921317908"
        query_url = "https://web-edit.us.capcut.com/lv/v2/intelligence/query?babi_param=%7B%22scenario%22%3A%22video_editor%22%2C%22feature_key%22%3A%22text_to_speech%22%2C%22feature_entrance%22%3A%22tool%22%2C%22feature_entrance_detail%22%3A%22tool-feature-text_to_speech%22%7D&aid=348188&device_platform=web&region=US&web_id=7655527138921317908"

        base_headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:152.0) Gecko/20100101 Firefox/152.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "Lan": "en",
            "tdid": "",
            "sign-ver": "1",
            "pf": "7",
            "appvr": "8.4.0",
            "appid": "348188",
            "did": "7655527138921317908",
            "store-country-code": "us",
            "store-country-code-src": "uid",
            "Origin": "https://www.capcut.com",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Referer": "https://www.capcut.com/",
            "Cookie": self.cookie,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

        create_headers = base_headers.copy()
        create_headers.update({
            "sign": "ab68f2fa1b6dbcb4fbf731550f53e7d2",
            "device-time": "1782453753",
        })

        query_headers = base_headers.copy()
        query_headers.update({
            "sign": "8aa799ab39809475216f7e991b4eb197",
            "device-time": "1782453755",
        })

        params_dict = {"text": text, "breaks": [], "platform": 1}
        req_json_dict = {
            "speaker": speaker,
            "audio_config": {"speech_rate": 0, "pitch_rate": 0},
            "disable_caption": False,
            "speaker_name": speaker_name,
            "commerce": {
                "resource_type": "material_artist",
                "benefit_type": "resource_export",
                "resource_id": resource_id,
            },
        }

        payload = {
            "workspace_id": self.workspace_id,
            "smart_tool_type": 39,
            "scene": 0,
            "params": json.dumps(params_dict, ensure_ascii=False),
            "req_json": json.dumps(req_json_dict, ensure_ascii=False),
        }

        # print(f"[CapCut TTS Debug] Gửi request tạo task cho văn bản: '{text[:60]}...'")
        # print(f"[CapCut TTS Debug] URL: {create_url}")
        # print(f"[CapCut TTS Debug] Payload: {json.dumps(payload, ensure_ascii=False)}")
        res = requests.post(create_url, headers=create_headers, json=payload, timeout=30)
        res.raise_for_status()
        res_data = res.json()
        # print(f"[CapCut TTS Debug] Kết quả tạo task: {json.dumps(res_data, ensure_ascii=False)}")

        if str(res_data.get("ret")) != "0":
            raise RuntimeError(f"CapCut API Error (create): {res_data.get('errmsg')} (code {res_data.get('ret')})")

        task_id = res_data["data"]["task_id"]

        max_attempts = 10
        audio_url = None
        for attempt in range(1, max_attempts + 1):
            sleep_time = random.uniform(3.0, 5.0)
            # print(f"[CapCut TTS Debug] Đợi {sleep_time:.2f}s trước khi query (Lần thử {attempt}/{max_attempts})...")
            time.sleep(sleep_time)
            query_payload = {
                "task_id": task_id,
                "workspace_id": self.workspace_id,
                "smart_tool_type": 39,
            }
            # print(f"[CapCut TTS Debug] Gửi query: {json.dumps(query_payload)}")
            qres = requests.post(query_url, headers=query_headers, json=query_payload, timeout=30)
            qres.raise_for_status()
            qres_data = qres.json()
            # print(f"[CapCut TTS Debug] Kết quả query: {json.dumps(qres_data, ensure_ascii=False)}")

            if str(qres_data.get("ret")) != "0":
                raise RuntimeError(f"CapCut API Error (query): {qres_data.get('errmsg')} (code {qres_data.get('ret')})")

            data_obj = qres_data.get("data", {})
            status = data_obj.get("status")
            if status == 2:
                task_details = data_obj.get("task_detail", [])
                if task_details:
                    detail = task_details[0]
                    audio_url = detail.get("url")
                    if not audio_url:
                        transcode_info = detail.get("transcode_audio_info", [])
                        if transcode_info:
                            audio_url = transcode_info[0].get("url")
                break
            elif status in (0, 1):
                continue
            else:
                raise RuntimeError(f"CapCut task failed with status: {status}")

        if not audio_url:
            raise RuntimeError(f"CapCut TTS failed: Audio URL not found after {max_attempts} attempts.")

        # print(f"[CapCut TTS Debug] Tải audio từ URL: {audio_url}")
        audio_res = requests.get(audio_url, timeout=30)
        audio_res.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_res.content)
        # print(f"[CapCut TTS Debug] Đã tải và lưu thành công segment tại: {output_path}")
        return output_path
