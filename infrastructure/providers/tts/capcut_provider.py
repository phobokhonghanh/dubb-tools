from __future__ import annotations

import json
import random
import time
import hashlib
import secrets
import base64
import uuid
from pathlib import Path
from urllib.parse import urlencode
import requests

from core.ports.tts import BaseTTSProvider
from infrastructure.providers.tts.models import TtsVoice, TTSAudioDownloadError



TTS_SIGN_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAmTd34Lw4b7IuldSXh/zY
CMla+ITdGG5TeWz6ad+OySd4r+IrY45AoqrYUxhQ2dl+7z+i7r/5vEa8rr39BYfB
8AGMQLmZA8HmgpWBsqrn/V6daUALkKnkLb70Fn32CJigIuGXAYqxUdGuI340aC+0
v5Es3puJsHyzf01/AelE4Cdc6bZhQrASJLBh8R3BQToYClmDVSDUQk28o8sl/guA
Z4n303Vj+6Siv1HayPCdV6kpVVnMBAG4+umUbwGmn132N3fgpzLarFF3XyWmS1zh
D/J07iM/rP8GDO9IskHNHd2phrO0G6KzrcFAnTBHjVv+hCBEfzN/no3FNA9AuC36
mwIDAQAB
-----END PUBLIC KEY-----"""


# Helper functions for RSA and signing (V1 API)
def compact_json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def make_x_ss_stub(body_text):
    return hashlib.md5(body_text.encode("utf-8")).hexdigest()


def _der_len(data, pos):
    first = data[pos]
    pos += 1
    if first < 0x80:
        return first, pos
    nbytes = first & 0x7F
    return int.from_bytes(data[pos : pos + nbytes], "big"), pos + nbytes


def _der_value(data, pos, tag):
    if data[pos] != tag:
        raise ValueError(f"bad DER tag: expected 0x{tag:02x}, got 0x{data[pos]:02x}")
    length, pos = _der_len(data, pos + 1)
    return data[pos : pos + length], pos + length


def _der_int(data, pos):
    raw, pos = _der_value(data, pos, 0x02)
    return int.from_bytes(raw.lstrip(b"\x00"), "big"), pos


def rsa_public_numbers_from_pem(pem):
    b64 = "".join(line for line in pem.splitlines() if not line.startswith("-----"))
    der = base64.b64decode(b64)
    outer, pos = _der_value(der, 0, 0x30)
    if pos != len(der):
        raise ValueError("trailing data in public key")
    _, pos = _der_value(outer, 0, 0x30)  # AlgorithmIdentifier
    bit_string, pos = _der_value(outer, pos, 0x03)
    if pos != len(outer) or not bit_string or bit_string[0] != 0:
        raise ValueError("bad subjectPublicKeyInfo")
    rsa_seq, pos = _der_value(bit_string[1:], 0, 0x30)
    if pos != len(bit_string[1:]):
        raise ValueError("trailing data in RSA public key")
    modulus, pos = _der_int(rsa_seq, 0)
    exponent, pos = _der_int(rsa_seq, pos)
    if pos != len(rsa_seq):
        raise ValueError("trailing integer data in RSA public key")
    return modulus, exponent


def rsa_encrypt_pkcs1v15(message, pem=TTS_SIGN_PUBLIC_KEY_PEM):
    modulus, exponent = rsa_public_numbers_from_pem(pem)
    key_len = (modulus.bit_length() + 7) // 8
    msg = message.encode("utf-8") if isinstance(message, str) else bytes(message)
    if len(msg) > key_len - 11:
        raise ValueError("message too long for RSA PKCS#1 v1.5")
    ps_len = key_len - len(msg) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        chunk = secrets.token_bytes(ps_len - len(ps))
        ps.extend(b for b in chunk if b != 0)
    encoded = b"\x00\x02" + bytes(ps[:ps_len]) + b"\x00" + msg
    encrypted = pow(int.from_bytes(encoded, "big"), exponent, modulus).to_bytes(key_len, "big")
    return base64.b64encode(encrypted).decode("ascii")


def make_tts_payload_sign(ssml, extra_info, device_id, app_id):
    ssml_md5 = hashlib.md5(ssml.encode("utf-8")).hexdigest()
    sign_input = f"appid:{app_id}&did:{device_id}&creditDisable:false&ssml:{ssml_md5}"
    if extra_info is not None:
        sign_input += f"&extraInfo:{extra_info}"
    return rsa_encrypt_pkcs1v15(sign_input)


def make_sign_header(url, appvr, device_time, tdid):
    path = url.split("?", 1)[0]
    sign_str = f"9e2c|{path[-7:]}|3|{appvr}|{device_time}|{tdid}|11ac"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


def make_trace_id():
    seed = uuid.uuid4().hex[:32]
    return f"00-{seed}-{seed[:16]}-01"


def common_query(device, babi_param=None, include_region=True):
    q = {
        "app_name": device["app_name"],
        "device_type": device["device_type"],
        "os_version": device["os_version"],
        "channel": device["channel"],
        "version_name": device["version_name"],
        "device_brand": device["device_brand"],
        "device_id": device["device_id"],
        "iid": device["iid"],
        "version_code": device["version_code"],
        "device_platform": device["device_platform"],
        "aid": device["aid"],
    }
    if include_region:
        q["region"] = device["region"]
    if babi_param is not None:
        q["babi_param"] = compact_json(babi_param)
    return q


def base_headers(device, body_text, appid=False):
    now = str(int(time.time()))
    headers = {
        "content-type": "application/json",
        "appvr": device["appvr"],
        "ch": device["channel"],
        "device-time": now,
        "lan": device["lan"],
        "loc": device["loc"],
        "pf": device["pf"],
        "sign-ver": "1",
        "tdid": device["tdid"],
        "x-ss-stub": make_x_ss_stub(body_text),
        "x-ss-dp": device["aid"],
        "x-khronos": now,
        "x-tt-trace-id": make_trace_id(),
        "user-agent": "Cronet/TTNetVersion:1d7cc3b1 2025-07-16 QuicVersion:52c2b40d 2025-04-03",
        "accept-encoding": "gzip, deflate",
        "store-country-code": device["loc"].lower(),
        "store-country-code-src": "did",
        "is-dispatch-us-ttp": "0",
        "is-app-region-us-ttp": "0",
    }
    if appid:
        headers["app-sdk-version"] = device["appvr"]
        headers["appid"] = device["aid"]
    return headers


def escape_xml(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_proxy_url(proxy_str: str) -> str:
    proxy_str = proxy_str.strip()
    if not proxy_str:
        return ""
    
    prefix = "http://"
    if proxy_str.startswith("http://"):
        proxy_str = proxy_str[7:]
    elif proxy_str.startswith("https://"):
        proxy_str = proxy_str[8:]
        prefix = "https://"
        
    if proxy_str.endswith("/"):
        proxy_str = proxy_str[:-1]
        
    parts = [p.strip() for p in proxy_str.split(":")]
    if len(parts) == 4:
        if parts[1].isdigit():
            host, port, user, password = parts[0], parts[1], parts[2], parts[3]
        else:
            user, password, host, port = parts[0], parts[1], parts[2], parts[3]
        return f"{prefix}{user}:{password}@{host}:{port}"
    elif len(parts) == 2:
        return f"{prefix}{parts[0]}:{parts[1]}"
    
    if not proxy_str.startswith(("http://", "https://")):
        return f"http://{proxy_str}"
    return proxy_str


class CapCutTTSProvider(BaseTTSProvider):
    provider_id = "capcut"

    def __init__(self, api_key: str | None = None) -> None:
        self.version = "v2"  # Mặc định là v2 (cũ)
        self.cookie = ""
        self.workspace_id = ""
        self.device_id = ""
        self.proxy = ""

        if api_key:
            try:
                data = json.loads(api_key)
                self.version = data.get("version", "v2")
                self.cookie = data.get("cookie", "")
                self.workspace_id = data.get("workspace_id", "")
                self.device_id = data.get("device_id", "")
                self.proxy = format_proxy_url(data.get("proxy", ""))
            except Exception:
                if ":" in api_key:
                    parts = api_key.split(":", 1)
                    self.workspace_id = parts[0]
                    self.cookie = parts[1]
                else:
                    self.cookie = api_key


    def _load_voices_config(self) -> tuple[list[TtsVoice], dict]:
        voices_path = Path("config/capcut_voices.json")
        if not voices_path.exists():
            voices_path = Path(__file__).resolve().parents[3] / "config" / "capcut_voices.json"

        if not voices_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file cấu hình giọng nói tại {voices_path}")

        with open(voices_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            voices = []
            mapping = {}
            for item in data:
                voices.append(
                    TtsVoice(
                        id=item["id"],
                        name=item["name"],
                        locale=item["locale"],
                        gender=item.get("gender", "Female"),
                        provider="capcut",
                    )
                )
                mapping[item["id"]] = {
                    "speaker": item["speaker"],
                    "speaker_name": item["name"],
                    "resource_id": item["id"],
                }
            return voices, mapping

    def _load_device_config(self) -> dict:
        device_path = Path("config/capcut_device.json")
        if not device_path.exists():
            device_path = Path(__file__).resolve().parents[3] / "config" / "capcut_device.json"

        if not device_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file cấu hình thiết bị tại {device_path}")

        with open(device_path, "r", encoding="utf-8") as f:
            device = json.load(f)
            # Ghi đè device_id và tdid nếu được truyền từ bên ngoài
            if self.device_id:
                device["device_id"] = self.device_id
                device["tdid"] = self.device_id
            return device

    def list_voices(self, language: str | None = None) -> list[TtsVoice]:
        voices, _ = self._load_voices_config()
        if not language:
            return voices
        prefix = language.lower()
        filtered = [v for v in voices if v.locale.lower().startswith(prefix)]
        return filtered or voices

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
        voices, mapping = self._load_voices_config()
        info = mapping.get(voice_id) or mapping.get("7102355709945188865")
        if not info:
            raise ValueError(f"Không tìm thấy giọng nói có ID: {voice_id}")

        speaker = info["speaker"]
        speaker_name = info["speaker_name"]
        resource_id = info["resource_id"]

        proxies = None
        if self.proxy:
            proxies = {"http": self.proxy, "https": self.proxy}

        # ----------------------------------------------------
        # LUỒNG API V1 (Common Task)
        # ----------------------------------------------------
        if self.version == "v1":
            device = self._load_device_config()

            rate_float = 1.0 + (rate / 100.0)
            rate_str = f"{rate_float:.2f}"

            babi = {
                "feature_entrance": "editor",
                "feature_entrance_detail": "editor-feature-text_to_speech",
                "feature_key": "text_to_speech",
                "scenario": "video_editor",
            }

            voice_block = (
                f'    <voice name="{speaker}" mock_tone_info="" platform="sami" '
                f'resource_id="{resource_id}" emotion="" emotion_scale="0" style="" role="" '
                f'moyin_emotion="" is_clone_tone="false" need_subtitle_timestamp="false">\n'
                f'        <prosody rate="{rate_str}">{escape_xml(text)}</prosody>\n'
                f'    </voice>'
            )
            ssml = (
                '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">\n'
                + voice_block
                + "\n</speak>"
            )

            extra_info = compact_json({"benefit_info": {}})
            payload_data = {
                "audio_format": "mp3",
                "babi_param": compact_json(babi),
                "credit_disable": False,
                "extra_info": extra_info,
                "need_merge_voice": False,
                "need_subtitle_timestamp": False,
                "scene": "text_to_speech",
                "ssml": ssml,
            }
            payload_data["sign"] = make_tts_payload_sign(ssml, extra_info, device["device_id"], device["aid"])

            body = {
                "bind_id": str(uuid.uuid4()),
                "can_queue": True,
                "enter_from": "text_to_speech",
                "tasks": [
                    {
                        "context": str(uuid.uuid4()),
                        "payload": compact_json(payload_data),
                        "req_key": "sami_text_to_speech",
                        "task_version": "v3",
                    }
                ],
            }

            body_text = compact_json(body)
            query = common_query(device, babi, include_region=True)
            create_url = "https://editor-api-sg.capcutapi.com/lv/v1/common_task/new?" + urlencode(query)
            headers = base_headers(device, body_text, appid=True)

            lower_headers = {k.lower(): v for k, v in headers.items()}
            if "sign" not in lower_headers:
                headers["sign"] = make_sign_header(create_url, device["appvr"], lower_headers["device-time"], device["tdid"])

            res = requests.post(create_url, headers=headers, data=body_text.encode("utf-8"), proxies=proxies, timeout=60)
            res.raise_for_status()
            res_data = res.json()

            if str(res_data.get("ret")) != "0":
                raise RuntimeError(f"CapCut API Error (create): {res_data.get('errmsg')} (code {res_data.get('ret')})")

            tasks = res_data.get("data", {}).get("tasks", [])
            if not tasks:
                raise RuntimeError(f"CapCut V1: Không nhận được thông tin task từ kết quả tạo: {res_data}")

            task_id = tasks[0]["id"]
            token = tasks[0]["token"]
            bind_id = body["bind_id"]

            max_attempts = 10
            audio_url = None

            query_body_data = {
                "tasks": [
                    {
                        "bind_id": bind_id,
                        "id": task_id,
                        "req_key": "sami_text_to_speech",
                        "task_version": "v3",
                        "token": token,
                    }
                ]
            }
            query_body_text = compact_json(query_body_data)
            query_params = common_query(device, None, include_region=False)
            query_url = "https://editor-api-sg.capcutapi.com/lv/v1/common_task/query?" + urlencode(query_params)

            for attempt in range(1, max_attempts + 1):
                sleep_time = random.uniform(3.0, 5.0)
                time.sleep(sleep_time)

                q_headers = base_headers(device, query_body_text, appid=True)
                q_lower_headers = {k.lower(): v for k, v in q_headers.items()}
                if "sign" not in q_lower_headers:
                    q_headers["sign"] = make_sign_header(query_url, device["appvr"], q_lower_headers["device-time"], device["tdid"])

                qres = requests.post(query_url, headers=q_headers, data=query_body_text.encode("utf-8"), proxies=proxies, timeout=60)
                qres.raise_for_status()
                qres_data = qres.json()

                if str(qres_data.get("ret")) != "0":
                    raise RuntimeError(f"CapCut API Error (query): {qres_data.get('errmsg')} (code {qres_data.get('ret')})")

                tasks_list = qres_data.get("data", {}).get("tasks", [])
                if not tasks_list:
                    continue

                task_info = tasks_list[0]
                status = task_info.get("status")

                if status == "succeed":
                    payload_str = task_info.get("payload", "")
                    if payload_str:
                        payload_json = json.loads(payload_str)
                        audio_subtitles = payload_json.get("audio_subtitles", [])
                        if audio_subtitles:
                            audio_url = audio_subtitles[0].get("speech_url")
                    break
                elif status in ("queueing", "processing"):
                    continue
                else:
                    raise RuntimeError(f"CapCut task failed with status: {status}")

            if not audio_url:
                raise RuntimeError(f"CapCut TTS failed: Audio URL not found after {max_attempts} attempts.")

            try:
                audio_res = requests.get(audio_url, proxies=proxies, timeout=30)
                audio_res.raise_for_status()
            except Exception as exc:
                raise TTSAudioDownloadError(f"Lỗi tải file audio từ CDN: {exc}", audio_url) from exc

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_res.content)
            return output_path

        # ----------------------------------------------------
        # LUỒNG API V2 (Intelligence Web Edit - Cũ)
        # ----------------------------------------------------
        else:
            if not self.cookie or not self.workspace_id:
                raise ValueError("Vui lòng cung cấp Cookie và Workspace ID hợp lệ cho CapCut TTS V2.")

            create_url = "https://web-edit.us.capcut.com/lv/v2/intelligence/create?babi_param=%7B%22scenario%22%3A%22video_editor%22%2C%22feature_key%22%3A%22text_to_speech%22%2C%22feature_entrance%22%3A%22tool%22%2C%22feature_entrance_detail%22%3A%22tool-feature-text_to_speech%22%7D&aid=348188&device_platform=web&region=US&web_id=7655527138921317908"
            query_url = "https://web-edit.us.capcut.com/lv/v2/intelligence/query?babi_param=%7B%22scenario%22%3A%22video_editor%22%2C%22feature_key%22%3A%22text_to_speech%22%2C%22feature_entrance%22%3A%22tool%22%2C%22feature_entrance_detail%22%3A%22tool-feature-text_to_speech%22%7D&aid=348188&device_platform=web&region=US&web_id=7655527138921317908"

            base_headers_v2 = {
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

            create_headers = base_headers_v2.copy()
            create_headers.update({
                "sign": "ab68f2fa1b6dbcb4fbf731550f53e7d2",
                "device-time": "1782453753",
            })

            query_headers = base_headers_v2.copy()
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

            res = requests.post(create_url, headers=create_headers, json=payload, proxies=proxies, timeout=30)
            res.raise_for_status()
            res_data = res.json()

            if str(res_data.get("ret")) != "0":
                raise RuntimeError(f"CapCut API Error (create): {res_data.get('errmsg')} (code {res_data.get('ret')})")

            task_id = res_data["data"]["task_id"]

            max_attempts = 10
            audio_url = None
            for attempt in range(1, max_attempts + 1):
                sleep_time = random.uniform(3.0, 5.0)
                time.sleep(sleep_time)
                query_payload = {
                    "task_id": task_id,
                    "workspace_id": self.workspace_id,
                    "smart_tool_type": 39,
                }
                qres = requests.post(query_url, headers=query_headers, json=query_payload, proxies=proxies, timeout=30)
                qres.raise_for_status()
                qres_data = qres.json()

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

            try:
                audio_res = requests.get(audio_url, proxies=proxies, timeout=30)
                audio_res.raise_for_status()
            except Exception as exc:
                raise TTSAudioDownloadError(f"Lỗi tải file audio từ CDN: {exc}", audio_url) from exc

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_res.content)
            return output_path
