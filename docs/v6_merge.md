"Bạn là một Senior Media Engineer. Dựa trên context.md và kiến trúc SPA hiện tại, hãy hiện thực hóa Feature 6: Hợp nhất Video & Audio (Module merger_view).

Mục tiêu: Hợp nhất file Video đã tắt tiếng (từ v2) với file Audio lồng tiếng (từ v5). Đặc biệt, hỗ trợ người dùng chèn thêm Intro (đầu video) và Outro (cuối video) mà không làm ảnh hưởng đến đồng bộ của video chính.

Yêu cầu kỹ thuật và giao diện chi tiết:

1. Kiến trúc Backend & Logic Xử lý (FFmpeg Pipeline):

    Kiến trúc: - Core logic: utils/video_merger.py.

        Service: app/services/merger_service.py (Single-job execution).

    Logic Hợp nhất (Timeline Assembly):

        Thành phần: Intro (Video/Image) + Main Video (Muted) + Outro (Video/Image).

        Xử lý Thời gian: - Video gốc phải đợi Intro chạy xong mới bắt đầu (Shift start time).

            Audio lồng tiếng cũng phải được dịch chuyển (delay) một khoảng bằng đúng thời lượng của Intro.

        Kỹ thuật: Sử dụng ffmpeg với filter concat để ghép nối các phân đoạn video và amix hoặc map audio để đè phần lồng tiếng vào video chính sau Intro.

    Tương thích: Đọc và kế thừa các đường dẫn file từ resources/layer/process/ để gợi ý file tự động.

2. Thành phần Giao diện (UI Components - Dark Mode):

    Input Selection Card (Video & Audio chính):

        Chọn Main Video (Muted).

        Chọn Main Audio (Speech từ v5).

    Branding Card (Intro & Outro):

        Ô chọn file Intro (Optional): Hỗ trợ video hoặc ảnh.

        Ô chọn file Outro (Optional): Hỗ trợ video hoặc ảnh.

        Lưu ý: Sử dụng native dialog (zenity/PySide6) để chọn file.

    Output Card: Chọn thư mục lưu và tên file thành phẩm (Mặc định: final_video.mp4).

    Action Button: Nút "Bắt đầu Gộp" với hiệu ứng Loading.

    Progress Card: Hiển thị stage: Đang kiểm tra định dạng -> Đang tính toán timeline -> Đang render video final (FFmpeg) -> Hoàn tất.

3. Quản lý Trạng thái & Đồng bộ (SPA State):

    Lưu state qua tab: input paths (video, audio, intro, outro), output path, progress state.

    Sử dụng _sync_controls() và page.schedule_update() để đảm bảo UI realtime khi chuyển tab.

    Hiển thị thông báo Success Toast kèm nút "Mở thư mục" khi hoàn thành.

4. Ràng buộc Kỹ thuật:

    File thực thi phải gọi ffmpeg và ffprobe từ hệ thống.

    Phải xử lý trường hợp Intro/Outro có độ phân giải hoặc tỷ lệ khung hình khác với Video chính (cần scale/pad để tránh lỗi FFmpeg concat).

Hãy viết mã nguồn Python hoàn chỉnh, chia tách file theo đúng cấu trúc dự án. Đảm bảo UI thống nhất với phong cách chuyên nghiệp của các version trước đó."