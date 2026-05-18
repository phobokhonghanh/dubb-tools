"Bạn là một Senior Software Architect. Dựa trên context.md và kiến trúc SPA hiện tại, hãy hiện thực hóa Feature 4: Tool Dịch thuật AI Đa nền tảng (Module translate_view).

Mục tiêu: Dịch file .srt sang ngôn ngữ đích bằng LLM và cung cấp bộ công cụ hậu kỳ (Post-editing) để người dùng tinh chỉnh kết quả thủ công trước khi xuất file.

Yêu cầu kỹ thuật và giao diện chi tiết:

1. Kiến trúc Backend & Xử lý AI:

    Core Logic (utils/translator/): Áp dụng Strategy Pattern với BaseTranslator và GeminiTranslator. Dễ dàng mở rộng thêm các Model khác sau này.

    Context-aware Translation: Parse .srt, tạo context_summary (Full Text + Tổng thời gian) gửi kèm vào System Prompt để AI hiểu bối cảnh xưng hô và nội dung toàn văn.

    Content Safety (Optional): Nếu người dùng tick chọn, thêm yêu cầu vào Prompt để AI chủ động giảm tránh từ ngữ nhạy cảm (ví dụ: 'giết' -> 'hạ gục').

    Service: Điều phối single-job, quản lý và lưu trữ API Key theo từng Model vào file cấu hình cục bộ (JSON/Config).

2. Thành phần Giao diện (UI Components - Dark Mode):

    Model & Safety Card: Dropdown chọn Model, TextField nhập/cập nhật API Key, và Checkbox "Content Safety".

    File Selection Card: Dùng native dialog chọn file .srt input và thư mục output.

    Live Preview Area: - ListView: Hiển thị real-time các dòng đã dịch xong kèm mốc thời gian và Badge tổng số dòng.

    Post-Editing Tools (Tính năng thay thế sau khi dịch):

        Vùng này chỉ hoạt động hoặc phát huy tác dụng sau khi AI đã hoàn thành bản dịch.

        Gồm 2 TextField: "Tìm từ ngữ" và "Thay thế bằng".

        Nút "Replace All": Khi bấm, hệ thống sẽ quét toàn bộ danh sách kết quả đang hiển thị trong ListView và thực hiện thay thế chuỗi (String Replacement) ngay lập tức mà không cần gọi lại AI. Điều này giúp người dùng tự tay điều chỉnh cách xưng hô hoặc thuật ngữ sai sót.

3. Quản lý Trạng thái & Đồng bộ (SPA State):

    Sử dụng _sync_controls() và page.schedule_update() để bảo toàn API Key, danh sách kết quả dịch (đã hoặc đang replace) khi người dùng chuyển đổi qua lại giữa các Tab.

    Xử lý lỗi API (Key sai, hết hạn) hiển thị qua Toast hoặc thông báo đỏ trong Progress Card thay vì treo app.

4. Xuất bản:

    Nút "Lưu file .srt": Xuất kết quả cuối cùng (bao gồm cả các thay đổi từ bộ lọc Replace) ra file .srt mới: [Tên_File_Gốc]_[Lang].srt.

Hãy viết mã nguồn Python hoàn chỉnh, tổ chức code sạch sẽ theo cấu trúc: utils/translator/ cho core, app/services/ cho service và app/features/ cho UI. Đảm bảo logic Replace tác động trực tiếp vào State của danh sách kết quả đang hiển thị."