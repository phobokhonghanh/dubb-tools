"Bạn là một Senior Software Architect. Dựa trên kiến trúc SPA hiện tại và context.md, hãy hiện thực hóa Feature 5: Công cụ Lồng tiếng AI (Module tts_view).

Mục tiêu: Nhận input là file phụ đề đã dịch (file .srt từ v4), sử dụng công nghệ TTS (Text-to-Speech) để tạo ra các file âm thanh giọng đọc tương ứng, đảm bảo khớp mốc thời gian (Timing) và có thể gộp thành một file audio duy nhất.

Yêu cầu kỹ thuật và giao diện chi tiết:

1. Kiến trúc Backend & Logic TTS (Extensible Strategy Pattern):

    Core Logic (utils/tts/):

        Áp dụng Strategy Pattern: BaseTTS định nghĩa khung, EdgeTTS (miễn phí, chất lượng cao) hoặc OpenAITTS thực thi cụ thể.

    Xử lý file .srt:

        Parse file .srt để lấy nội dung text và mốc thời gian (start/end).

        Logic khớp thời gian: Tính toán thời lượng của đoạn text (đọc) so với thời lượng thực tế của segment trong phụ đề. Nếu text quá dài, cần có cơ chế tăng tốc độ đọc (Rate) để tránh đè sang segment sau. tính toán: thời_gian_đoạn_phụ_đề / thời_gian_audio_tạo_ra. Nếu tỉ lệ < 1.0, AI cần tăng thông số rate khi gọi TTS cho segment đó.

    Service (app/services/tts_service.py): Điều phối việc tạo từng segment audio và gộp chúng lại bằng pydub hoặc ffmpeg. Quản lý theo cơ chế Single-job execution.

2. Quản lý Model & Giọng đọc (Voice Selection):

    Lưu trữ cấu hình: Sử dụng cơ chế lưu config cục bộ (giống v4) để lưu provider, voice_id, rate, pitch và API Key (nếu có).

    Đa dạng Model: Hỗ trợ danh sách giọng đọc (Voice) theo ngôn ngữ đã chọn. (Người dùng có thể chọn giọng nam hoặc nữ)

3. Thành phần Giao diện (UI Components - Dark Mode):

    TTS Config Card:

        Dropdown chọn TTS Provider (Edge-TTS, v.v.).

        Dropdown chọn Giọng đọc (Voice): Tự động filter theo ngôn ngữ.

        Slider điều chỉnh Tốc độ (Rate) và Âm lượng (Volume).

    File Selection Card: Dùng native dialog chọn file .srt đã dịch và thư mục output.

    Action Button: Nút "Bắt đầu Lồng tiếng" lớn, nổi bật.

    Progress Card: Hiển thị stage: Đang khởi tạo -> Đang tạo audio segment (real-time progress) -> Đang gộp file -> Hoàn tất.

4. Quản lý Trạng thái & Đồng bộ (SPA State):

    Lưu state qua tab (giống v1-v4): input/output path, voice đã chọn, tiến trình xử lý.

    Sử dụng _sync_controls() và page.schedule_update() để cập nhật UI mượt mà khi chuyển đổi giữa các Feature.

5. Xuất bản:

    Đầu ra:

        Một file audio tổng hợp: [Tên_File_Gốc]_speech.mp3.

        (Optional) Folder chứa các segment lẻ nếu người dùng cần.

Hãy viết mã nguồn Python hoàn chỉnh, tổ chức code sạch sẽ theo cấu trúc: utils/tts/ cho core, app/services/ cho service và app/features/ cho UI. Đảm bảo kế thừa BaseView và tuân thủ các quy tắc Flet version trong context.md."