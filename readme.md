# Dubb Tools

<p align="left">
  <a href="#"><img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img alt="UI" src="https://img.shields.io/badge/UI-Flet-00A3FF"></a>
  <a href="#"><img alt="Pipeline" src="https://img.shields.io/badge/Pipeline-Download%E2%86%92Split%E2%86%92STT%E2%86%92Translate%E2%86%92TTS%E2%86%92Merge-4CAF50"></a>
</p>

Desktop app cho quy trình lồng tiếng video end-to-end, từ tải video đến xuất video final đã lồng tiếng:
`Download -> Split -> STT -> Translate -> TTS -> Merge`

Dubb Tools ưu tiên workflow thực tế: có thể chạy từng bước để kiểm soát chất lượng, hoặc chạy full pipeline với retry/resume khi một bước lỗi.

## Table of Contents

- [Why Dubb Tools](#why-dubb-tools)
- [Core Features](#core-features)
- [Quick Start](#quick-start)
- [Full Pipeline](#full-pipeline)
- [How Startup Bootstrap Works](#how-startup-bootstrap-works)
- [Project Architecture](#project-architecture)
- [Configuration](#configuration)
- [RTK Workflow](#rtk-workflow)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Why Dubb Tools

- Một UI duy nhất để vận hành full workflow.
- Có thể chạy từng bước riêng hoặc chạy full pipeline tự động.
- Tối ưu cho vận hành lặp đi lặp lại: state, config local, output có cấu trúc.
- Giữ timing subtitle khi dịch/lồng tiếng: dịch theo batch nhưng không gộp mất khoảng nghỉ.
- Có cleanup nhiễu STT trước khi dịch/TTS để tránh các đoạn vô nghĩa bị đọc thành lời.
- Thiết kế để người dùng cuối sử dụng được mà không cần thao tác CLI phức tạp.

## Core Features

- `Bộ Tải File`: tải URL theo streaming, progress realtime.
- `Bộ Tách Video`: xuất `*_muted.mp4`, `*_vocals.wav`, `*_background.wav`.
- `Giọng Nói Thành Văn Bản`: STT với `faster-whisper`, hỗ trợ chọn language/model, chuẩn hóa text và lọc nhiễu.
- `Dịch Phụ Đề`: dịch SRT theo batch, luôn kèm full context, preview + replace trước khi lưu.
- `Lồng Tiếng AI`: TTS theo timeline subtitle (`Edge-TTS`, `Gemini TTS`), tự giữ khoảng nghỉ giữa subtitle.
- `Gộp Video`: gộp video + speech + background, tinh chỉnh volume.
- `Tự Động Hóa Quy Trình`: orchestration nhiều bước trong một job, hỗ trợ retry từ bước lỗi.

## Quick Start

### 1) System dependencies

```bash
sudo apt update && sudo apt install ffmpeg
```

### 2) Create virtual environment

```bash
rtk python3 -m venv venb
rtk ./venb/bin/python -m pip install -r requirements.txt
```

### 3) Run app

```bash
rtk ./venb/bin/python main.py
```

## Full Pipeline

`Tự Động Hóa Quy Trình` tạo một job folder riêng trong `resources/layer/pipeline/` cho mỗi lần chạy. Các output trung gian và video final nằm cùng job để dễ kiểm tra hoặc retry.

Pipeline hỗ trợ:
- Chạy từ URL hoặc file video local.
- Chọn từng bước cần chạy: Download, Split, STT, Translate, TTS, Merge.
- Retry từ bước lỗi trong cùng job folder sau khi chỉnh config.
- Khôi phục job gần nhất khi mở lại app nếu lần trước bị lỗi.

Translate/TTS timing:
- STT giữ từng segment/timestamp gốc.
- Translate dịch theo batch để giảm request, nhưng output vẫn giữ từng dòng riêng.
- Mỗi request dịch vẫn gửi full text làm context cho Gemini.
- TTS dùng timestamp riêng để chèn silence đúng giữa các đoạn thoại.

STT cleanup:
- Nút `Chuẩn hóa` và tùy chọn `Tự chuẩn hóa text` sẽ format text và loại nhiễu rõ ràng.
- Các đoạn như `A. O. S. H. I. D.` hoặc token lặp vô nghĩa sẽ bị bỏ trước Translate/TTS.
- Câu tự nhiên như `Tôi tên là Bằng`, `Ai đó?`, `Intro`, `Outro` vẫn được giữ.

## How Startup Bootstrap Works

Khi app mở lần đầu, màn hình `Ứng dụng đang khởi động...` sẽ xuất hiện.

Luồng khởi động:
1. Kiểm tra `vendor/pyvideotrans`.
2. Nếu thiếu, tự tải từ GitHub.
3. Nếu máy không có Git, fallback tải ZIP và giải nén.
4. Chỉ vào UI chính khi vendor đã sẵn sàng.

Điều này đảm bảo người dùng EXE không cần thao tác thủ công với script setup.

## Project Architecture

```text
app/
  features/      # Flet views cho từng chức năng
  services/      # background job + lock/single-job control
utils/           # business/core logic (download, stt, tts, merge, pipeline)
scripts/         # dev utilities (manual checks/tools)
resources/       # runtime outputs
```

Design principles:
- UI tách khỏi business logic.
- Service layer quản lý concurrency/callbacks.
- Core utilities tái sử dụng giữa feature đơn lẻ và full pipeline.

## Configuration

- Local runtime config: `config/*.json` (được ignore trong Git).
- Last pipeline run state: `config/pipeline_last_run.json` (được ignore trong Git).
- Gemini key:
  - nhập trực tiếp trong UI, hoặc
  - dùng env `GEMINI_API_KEY`.
- Runtime outputs: `resources/layer/` (được ignore trong Git).
- Vendor dependency: `vendor/pyvideotrans` (được bootstrap tự động, không commit).

## RTK Workflow

Repo dùng `rtk` cho các lệnh dev/test để giảm output nhiễu và tiết kiệm token khi vận hành với agent.

Common commands:

```bash
rtk ./venb/bin/python main.py
rtk ./venb/bin/python -m compileall app utils scripts main.py
rtk ./venb/bin/python scripts/ensure_vendor.py --check
rtk git status --short
```

## Troubleshooting

`App kẹt ở màn hình khởi động`
- Kiểm tra kết nối mạng.
- Kiểm tra quyền ghi thư mục project.

`Không chạy được bước merge/tts`
- Kiểm tra `ffmpeg -version` và `ffprobe -version`.

`Gemini lỗi xác thực`
- Kiểm tra API key trong UI hoặc biến môi trường.

`TTS đọc các đoạn không liên quan`
- Bật `Tự chuẩn hóa text` trong workflow hoặc bấm `Chuẩn hóa` ở tab STT để lọc nhiễu trước khi dịch/lồng tiếng.

`Pipeline lỗi giữa chừng`
- Chỉnh config tương ứng rồi bấm `Chạy lại từ bước lỗi`.
- Nếu đã đóng app, mở lại tab `Tự Động Hóa Quy Trình`; job gần nhất sẽ được khôi phục từ local state.

## Roadmap

- Mở rộng provider cho Translate/TTS theo strategy hiện có.
- Bổ sung test coverage tự động cho pipeline end-to-end.
- Tinh chỉnh heuristic cleanup STT theo từng loại nội dung/video.

## Contributing

Issues và PR đều được hoan nghênh.

Khi mở PR:
1. Mô tả rõ vấn đề và giải pháp.
2. Giữ thay đổi tập trung, tránh refactor không liên quan.
3. Chạy compile/smoke test trước khi gửi:

```bash
rtk ./venb/bin/python -m compileall app utils scripts main.py
```

## License

Repository hiện chưa khai báo license chính thức.
