"Bạn là một Senior Software Architect. Dựa trên dự án hiện tại và tài liệu context.md, hãy hiện thực hóa Feature 7: Bộ chạy tự động (Module pipeline_view).

Mục tiêu: Cho phép người dùng cấu hình tất cả các bước (từ Download đến Merge) trên một màn hình duy nhất và nhấn 'Start' để hệ thống tự động thực hiện tuần tự từ đầu đến cuối mà không cần can thiệp thủ công từng tab.

Yêu cầu kỹ thuật và giao diện chi tiết:

1. Kiến trúc Backend & Logic Điều phối (app/services/pipeline_executor_service.py):

    Kiến trúc: - Core logic: utils/pipeline_orchestrator.py.

        Service: app/services/pipeline_service.py (Kế thừa cơ chế Single-job).

    Quy trình thực hiện (Workflow):

        Download: Tải video từ URL (Nếu có URL).

        Split: Tách video thành muted.mp4, vocals.wav, background.wav.

        STT: Trích xuất lời thoại từ file vocals.wav ra .srt.

        Translate: Dịch file .srt sang ngôn ngữ đích bằng Gemini.

        TTS: Tạo file lồng tiếng speech.mp3 từ bản dịch.

        Merge: Hợp nhất video muted, audio lồng tiếng, nhạc nền và Intro/Outro (Nếu có) thành file Final.

    Cơ chế chuyển tiếp Data: Đầu ra của bước trước (Output Path) phải tự động trở thành đầu vào của bước sau (Input Path) dựa trên các pattern file đã quy định trong context.md.

2. Thành phần Giao diện (UI Components - Thống nhất Style):

    Sidebar Selection: Hiển thị các Checkbox cho phép người dùng chọn các bước muốn thực hiện (Ví dụ: Chỉ thực hiện từ bước STT đến Merge nếu đã có file video cục bộ).

    Global Config Card: Gồm các tab hoặc khu vực nhỏ để thiết lập nhanh:

        Download: Nhập URL.

        STT: Chọn Model và Ngôn ngữ gốc.

        Translate: Chọn Target Language và API Key (Tự động load từ translator_config.json).

        TTS: Chọn Provider (Edge-TTS/Gemini) và Voice.

        Merge: Chọn Intro/Outro Video (Optional).

    Execution Log Area: Một vùng văn bản (Terminal-style) hiển thị log chi tiết của từng bước đang chạy.

    Master Progress: Một thanh Progress Bar tổng thể (0/6 bước) và trạng thái chi tiết của bước hiện tại.

3. Quản lý Trạng thái & Đồng bộ (SPA State):

    Đảm bảo khi chạy Pipeline, các View đơn lẻ (như DownloadView, MergerView) vẫn cập nhật trạng thái nếu người dùng chuyển tab sang xem.

    Lưu cấu hình Pipeline gần nhất vào config/pipeline_config.json để người dùng không phải nhập lại.

    Dùng native dialog để chọn thư mục đầu ra tổng kho (Workspace).

4. Ràng buộc Kỹ thuật:

    Phải xử lý lỗi tại bất kỳ bước nào: Nếu bước 3 lỗi, Pipeline phải dừng lại và báo lỗi rõ ràng thay vì chạy tiếp bước 4.

    Đảm bảo các yêu cầu về ffmpeg, ffprobe và vendor/ model đều sẵn sàng trước khi chạy.
    
5. Đồng nhất dữ liệu: Việc tự động chuyển tiếp đường dẫn file (_muted.mp4, _vocals.wav,...) dựa trên tên của file và thời gian. để k bị lẫn lộn giữa các lần chạy khác

Hãy viết mã nguồn Python hoàn chỉnh, chia tách file theo cấu trúc dự án. Đảm bảo UI chuyên nghiệp, dễ sử dụng cho người dùng không am hiểu kỹ thuật."