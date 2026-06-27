import sys
import argparse
import json
from pathlib import Path

# Thêm thư mục gốc vào sys.path để import các module của dự án
sys.path.insert(0, str(Path(__file__).resolve().parent))

from infrastructure.providers.tts.capcut_provider import CapCutTTSProvider

def main():
    parser = argparse.ArgumentParser(description="CLI test CapCut V1 TTS Provider")
    parser.add_argument(
        "--text", 
        type=str, 
        default="Xin chào, đây là bản thử nghiệm lồng tiếng phiên bản mới CapCut V1.",
        help="Nội dung văn bản cần lồng tiếng"
    )
    parser.add_argument(
        "--voice", 
        type=str, 
        default="7102355709945188865",
        help="ID giọng đọc (ví dụ: Cô Gái Hoạt Ngôn / Cute Female)"
    )
    parser.add_argument(
        "--device-id", 
        type=str, 
        default="178252110997059322",
        help="CapCut Device ID dùng cho phiên bản V1"
    )
    parser.add_argument(
        "--proxy", 
        type=str, 
        default="",
        help="Proxy URL (hỗ trợ dạng host:port:username:password hoặc http://username:password@host:port)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="output_v1_cli.mp3",
        help="Đường dẫn lưu file audio kết quả"
    )

    args = parser.parse_args()

    # Đóng gói API key cấu hình cho provider
    config_data = {
        "version": "v1",
        "device_id": args.device_id,
        "proxy": args.proxy
    }
    api_key_json = json.dumps(config_data)

    print("--- Khởi tạo CapCutTTSProvider (V1) ---")
    print(f"Device ID: {args.device_id}")
    print(f"Proxy    : {args.proxy or 'Không sử dụng'}")
    print(f"Voice ID : {args.voice}")
    print(f"Text     : {args.text}")
    print("---------------------------------------")

    try:
        provider = CapCutTTSProvider(api_key=api_key_json)
        output_path = Path(args.output).resolve()
        
        print("Đang gửi yêu cầu tạo audio và truy vấn trạng thái...")
        provider.synthesize_segment(
            text=args.text,
            voice_id=args.voice,
            output_path=output_path,
            rate=0,
            volume=0,
            pitch=0
        )
        
        print(f"\n[Thành công] File audio đã được lưu tại: {output_path}")
        print(f"Kích thước file: {output_path.stat().st_size} bytes")
        
    except Exception as e:
        print(f"\n[Lỗi] Không thể lồng tiếng: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
