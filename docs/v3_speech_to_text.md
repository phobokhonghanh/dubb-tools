"Bạn là một Senior Desktop Developer. Dựa trên kiến trúc hiện tại của dự án (Flet SPA, Service-based, Single-job), hãy hiện thực hóa Feature 3: Tool Chuyển đổi Giọng nói thành Văn bản (Module stt_view).

Mục tiêu: Nhận input là file âm thanh (ưu tiên file vocals từ v2), sử dụng AI để trích xuất nội dung (Transcription) kèm mốc thời gian, hiển thị lên UI và cung cấp các công cụ xử lý text nâng cao.

Yêu cầu kỹ thuật và giao diện chi tiết:

1. Cấu trúc và Logic Backend:

    Kiến trúc: - Core logic: utils/stt_processor.py.

        Service: app/services/stt_service.py (Kế thừa cơ chế Lock/Event/Single-job).

        UI: app/features/stt_view.py (Kế thừa base.py).

    Engine nhận diện: Sử dụng công nghệ có sẵn trong dự án (ưu tiên whisper hoặc các model ONNX trong vendor/ nếu có).

    Phân loại Case: - Hiện tại chỉ xử lý case '1 người nói'.

        Nếu người dùng chọn case '2 người nói' hoặc 'Nhiều người nói', hiển thị thông báo: "Chức năng sắp ra mắt".

    Kết quả trả về: Một danh sách các Object chứa: start_time, end_time, content.

2. Thành phần Giao diện (UI Components - Dark Mode Style):

    File Selection: - Input: Chọn file âm thanh (Dùng native dialog qua zenity hoặc PySide6).

        Output: Chọn thư mục lưu file kết quả (.txt hoặc .srt).

    Options (Chế độ nhận diện): Một Dropdown hoặc RadioGroup để chọn số lượng người nói.

    Main Result Area: - Một ListView hiển thị các dòng kết quả theo định dạng: [00:00 - 00:05] Nội dung văn bản....

        Một Badge/Text hiển thị: Tổng số dòng: {count}.

    Advanced Tools Section (Vùng xử lý phụ): - Gộp dòng: Một TextField để nhập số dòng muốn gộp (ví dụ: gộp 5 dòng thành 1) và nút "Gộp". (xử lý cộng dồn thời gian (ví dụ gộp dòng 1-5 thì mốc thời gian mới sẽ lấy start của dòng 1 và end của dòng 5).)

        Chuẩn hóa Text: Nút "Chuẩn hóa" để tự động sửa lỗi chính tả, dấu câu (Dùng logic regex hoặc thư viện xử lý ngôn ngữ nhẹ).

    Progress Card: Hiển thị stage xử lý (Đang tải model -> Đang nhận diện -> Hoàn tất) kèm Progress Bar.

3. Quản lý Trạng thái & Đồng bộ (State Management):

    Phải lưu cache state qua tab (giống v1, v2): Lưu đường dẫn file input/output, danh sách kết quả đã trích xuất, trạng thái các nút bấm.

    Sử dụng _sync_controls() và page.schedule_update() để đảm bảo UI không bị đứng và cập nhật realtime khi chuyển đổi giữa các feature trong SPA Shell.

4. Xuất dữ liệu:

    Cho phép người dùng nhấn nút "Lưu kết quả" để xuất toàn bộ nội dung trong ListView ra file tại thư mục Output đã chọn.

Hãy viết mã nguồn Python hoàn chỉnh, tổ chức code sạch sẽ, chia file đúng theo cấu trúc thư mục của dự án và có chú thích tiếng Việt chi tiết."