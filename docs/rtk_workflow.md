# RTK Workflow cho V1 Download App

## Mục tiêu
- Chuẩn hóa thao tác shell để giảm token khi debug/test.
- Tránh lệnh raw không có tiền tố `rtk`.

## Quy tắc bắt buộc
- Luôn dùng `rtk <command>` thay vì gọi command trực tiếp.
- Ngoại lệ duy nhất: xử lý khẩn cấp khi `rtk` không khả dụng.

## Bộ lệnh chuẩn
- Cài dependency:
  - `rtk ./venb/bin/python -m pip install -r requirements.txt`
- Chạy CLI downloader:
  - `rtk ./venb/bin/python download.py -u <url>`
- Chạy UI Flet:
  - `rtk ./venb/bin/flet run main.py`
- Tìm kiếm code:
  - `rtk rg --files`
  - `rtk rg "download\\(" -n`

## Theo dõi hiệu quả token
- Tổng quan:
  - `rtk gain`
- Lịch sử:
  - `rtk gain --history`
- Rà lệnh bỏ sót:
  - `rtk discover`

## Do / Don't
- Do:
  - Dùng `rtk` cho mọi lệnh đọc log, test, tìm kiếm, chạy app.
  - Chạy `rtk discover` trước khi chốt đợt thay đổi lớn.
- Don't:
  - Không dùng `python`, `rg`, `git`, `ls` trực tiếp khi có thể dùng `rtk`.

## Checklist trước commit
- [ ] Tất cả command trong notes/script nội bộ có prefix `rtk`.
- [ ] Đã chạy `rtk discover` và không còn missed opportunities quan trọng.
- [ ] Đã chạy test chính bằng command có `rtk`.
