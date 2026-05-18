# Dubb Tools

<p align="left">
  <a href="#"><img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"></a>
  <a href="#"><img alt="UI" src="https://img.shields.io/badge/UI-Flet-00A3FF"></a>
  <a href="#"><img alt="Pipeline" src="https://img.shields.io/badge/Pipeline-Download%E2%86%92Split%E2%86%92STT%E2%86%92Translate%E2%86%92TTS%E2%86%92Merge-4CAF50"></a>
</p>

Desktop app cho quy trình lồng tiếng video end-to-end, từ tải video đến xuất video final đã lồng tiếng:
`Download -> Split -> STT -> Translate -> TTS -> Merge`

## Table of Contents

- [Why Dubb Tools](#why-dubb-tools)
- [Core Features](#core-features)
- [Quick Start](#quick-start)
- [How Startup Bootstrap Works](#how-startup-bootstrap-works)
- [Project Architecture](#project-architecture)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Why Dubb Tools

- Một UI duy nhất để vận hành full workflow.
- Có thể chạy từng bước riêng hoặc chạy full pipeline tự động.
- Tối ưu cho vận hành lặp đi lặp lại: state, config local, output có cấu trúc.
- Thiết kế để người dùng cuối sử dụng được mà không cần thao tác CLI phức tạp.

## Core Features

- `Bộ Tải File`: tải URL theo streaming, progress realtime.
- `Bộ Tách Video`: xuất `*_muted.mp4`, `*_vocals.wav`, `*_background.wav`.
- `Giọng Nói Thành Văn Bản`: STT với `faster-whisper`, hỗ trợ chọn language/model.
- `Dịch Phụ Đề`: dịch SRT theo chunk, preview + replace trước khi lưu.
- `Lồng Tiếng AI`: TTS theo timeline subtitle (`Edge-TTS`, `Gemini TTS`).
- `Gộp Video`: gộp video + speech + background, tinh chỉnh volume.
- `Tự Động Hóa Quy Trình`: orchestration nhiều bước trong một job.

## Quick Start

### 1) System dependencies

```bash
sudo apt update && sudo apt install ffmpeg
```

### 2) Create virtual environment

```bash
python3 -m venv venb
./venb/bin/python -m pip install -r requirements.txt
```

### 3) Run app

```bash
./venb/bin/python main.py
```

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
- Gemini key:
  - nhập trực tiếp trong UI, hoặc
  - dùng env `GEMINI_API_KEY`.

## Troubleshooting

`App kẹt ở màn hình khởi động`
- Kiểm tra kết nối mạng.
- Kiểm tra quyền ghi thư mục project.

`Không chạy được bước merge/tts`
- Kiểm tra `ffmpeg -version` và `ffprobe -version`.

`Gemini lỗi xác thực`
- Kiểm tra API key trong UI hoặc biến môi trường.

## Roadmap

- Cải thiện progress realtime chi tiết hơn cho các tác vụ nặng.
- Mở rộng provider cho Translate/TTS theo strategy hiện có.
- Bổ sung test coverage tự động cho pipeline end-to-end.

## Contributing

Issues và PR đều được hoan nghênh.

Khi mở PR:
1. Mô tả rõ vấn đề và giải pháp.
2. Giữ thay đổi tập trung, tránh refactor không liên quan.
3. Chạy compile/smoke test trước khi gửi.

## License

Repository hiện chưa khai báo license chính thức.
