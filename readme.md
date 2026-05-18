# Vietsub Tool

## Thiết lập môi trường

Cài FFmpeg:

```bash
sudo apt update && sudo apt install ffmpeg
```

Bootstrap vendor `pyvideotrans` khi clone project trên máy mới:

```bash
rtk ./venb/bin/python scripts/ensure_vendor.py
```

Kiểm tra vendor đã sẵn sàng:

```bash
rtk ./venb/bin/python scripts/ensure_vendor.py --check
```

`vendor/` là dependency local và không commit vào Git.
