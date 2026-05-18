from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from utils.stt_processor import stt_result_to_legacy_dict, transcribe_audio as transcribe_audio_core


def transcribe_audio(audio_path, model_size="base", language=None):
    """
    Chuyển đổi âm thanh thành văn bản bằng Faster Whisper.
    Giữ nguyên shape dữ liệu cũ để pipeline_executor.py không cần thay đổi.
    """
    result = transcribe_audio_core(audio_path, model_size=model_size, language=language)
    if not result.ok:
        raise RuntimeError(result.error_message or "Chuyển đổi âm thanh thành văn bản thất bại.")
    return stt_result_to_legacy_dict(result, audio_path)


def main():
    parser = argparse.ArgumentParser(description="Chuyển đổi file âm thanh sang văn bản")
    parser.add_argument("--audio", "-a", required=True, help="Đường dẫn file âm thanh")
    parser.add_argument("--language", "-l", help="Mã ngôn ngữ (vi, en, zh...). Bỏ trống để tự nhận diện.", default=None)
    parser.add_argument("--model-size", "-m", help="Kích thước mô hình (tiny, base, small, medium, large-v3)", default="base")
    parser.add_argument("--out", "-o", help="File JSONL để ghi kết quả (mặc định: transcript.jsonl)", default="transcript.jsonl")
    args = parser.parse_args()

    audio_path = args.audio
    if not os.path.exists(audio_path):
        print(f"Lỗi: Không tìm thấy file {audio_path}")
        return

    print(f"--- Đang tải mô hình Whisper ({args.model_size})... ---")
    result_data = transcribe_audio(audio_path, model_size=args.model_size, language=args.language)
    print(f"Đã phát hiện ngôn ngữ: '{result_data['info']['language']}'")
    for item in result_data["batch"]:
        print(f"[{item['start']:.2f}s -> {item['end']:.2f}s] {item['text']}")

    output_path = Path(args.out)
    with output_path.open("a", encoding="utf-8") as f:
        json_line = json.dumps(result_data, ensure_ascii=False)
        f.write(json_line + "\n")

    print(f"Đã ghi kết quả vào: {output_path}")


if __name__ == "__main__":
    main()
