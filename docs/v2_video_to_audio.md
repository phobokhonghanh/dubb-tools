Hãy hiện thực hóa Feature thứ hai: Tool Tách Video và Tách Nguồn Âm Thanh (Module `video_splitter_view`).

Mục tiêu của module này là tiếp nhận 1 file Video đầu vào, xử lý tách thành 3 file đầu ra riêng biệt:

    File Video gốc đã loại bỏ hoàn toàn âm thanh (Muted Video).

    File Âm thanh chỉ chứa giọng nói/lời thoại (Vocals/Speech Audio).

    File Âm thanh nền/nhạc nền đã loại bỏ giọng nói (Background Music/BGM Audio).

Yêu cầu kỹ thuật và giao diện chi tiết như sau:

1. Tích hợp Logic Xử lý (Backend):

    Sử dụng hoặc dựa trên logic xử lý có sẵn từ file `extract_audio.py` (dùng `moviepy` để tách video/audio), và bổ sung bước tách nguồn âm thanh thành 2 stem: `vocals` và `background`.

    Gợi ý engine tách nguồn (chọn 1, ưu tiên thứ tự):
    - Ưu tiên: dùng `sherpa-onnx` (đã có trong `requirements.txt`) theo hướng spleeter/UVR (CPU).
    - Hoặc: demucs/spleeter (nếu bạn đã cấu hình sẵn trong môi trường và chấp nhận thêm dependency).

    Yêu cầu quan trọng về model (nếu dùng sherpa-onnx spleeter):
    - Cần có 2 file model ONNX: `vocals.fp16.onnx` và `accompaniment.fp16.onnx`.
    - Nếu thiếu model, UI phải báo lỗi rõ ràng trong Progress Card.

    Quan trọng: Toàn bộ quá trình xử lý tách file nặng này phải được chạy trên một Background Thread độc lập. Tuyệt đối không làm nghẽn Main Thread để giữ UI luôn mượt mà ở tốc độ 60fps, cho phép người dùng bấm chuyển sang Feature khác (như Tool Tải File) trong lúc hệ thống đang xử lý ngầm.

    Áp dụng cơ chế xử lý tuần tự (Single-job), tại một thời điểm chỉ xử lý một video đầu vào.

    Khuyến nghị kiến trúc theo project hiện tại:
    - Core logic đặt trong `utils/video_splitter.py` (tương tự cách `utils/download.py` đang làm).
    - Service single-job đặt trong `app/services/video_splitter_service.py` (tương tự `app/services/download_service.py`), cung cấp callback stage/progress cho UI.
    - UI view đặt trong `app/features/video_splitter_view.py` kế thừa `app/features/base.py`.

2. Thành phần Giao diện (UI Components - Thống nhất Style Dark Mode):

    Header: Tiêu đề "Bộ Tách Video & Âm Thanh" kèm icon media/wave tối giản.

    File Selection Card (Vùng chọn file/thư mục):

        Ô Input Video:
        - Dùng nút "Chọn File" để mở dialog native của hệ điều hành nhằm chọn video.
        - Ưu tiên dialog OS thật qua `zenity` hoặc `PySide6 QFileDialog`.
        - Nếu môi trường không hỗ trợ dialog native thì mới fallback sang nhập path thủ công.
        - Chỉ chấp nhận các định dạng phổ biến: `.mp4`, `.mkv`, `.avi`, `.mov`.

        Ô Output Folder:
        - Dùng nút "Chọn Thư Mục" để mở dialog native của hệ điều hành nhằm chọn nơi lưu kết quả.
        - Hiển thị path đã chọn trên UI để người dùng kiểm tra lại.
        - Có nút "Mặc định" để reset về thư mục mặc định của project (ví dụ `resources/layer/process/` hoặc thư mục bạn chọn cho v2).

    Action Button: Nút "Bắt đầu Tách" lớn, nổi bật (Accent color thống nhất với hệ thống). Khi bấm, nút chuyển sang trạng thái Loading kèm hiệu ứng Spinner và đổi text thành "Processing...".

    Progress Card (Hiển thị tiến trình): Thẻ xuất hiện mềm mại (Fade-in) khi quá trình bắt đầu, bao gồm:

        Tên file đang xử lý.

        Thanh Progress Bar:
        - Ưu tiên chạy dạng vô định (Indeterminate) vì backend tách nguồn thường không có % chính xác.
        - Nếu backend có % thì hiển thị dạng xác định.

        Dòng text trạng thái cập nhật theo stage:
        - "Đang trích xuất audio..."
        - "Đang tách giọng nói & nhạc nền..."
        - "Đang xuất video không âm thanh..."
        - "Hoàn thành"

3. Trạng thái kết thúc & Đặt tên file đầu ra:

    Quy tắc đặt tên 3 file Output (lưu tại Output Folder đã chọn):

        [Tên_File_Gốc]_muted.mp4

        [Tên_File_Gốc]_vocals.mp3 (hoặc .wav)

        [Tên_File_Gốc]_background.mp3 (hoặc .wav)

    Thành công: Hiển thị Banner thông báo màu xanh (Success Toast) ở góc ứng dụng kèm nút "Mở thư mục lưu".

    Thất bại: Hiển thị thông báo lỗi tinh tế bằng text màu đỏ ngay trong Progress Card nếu định dạng file không hỗ trợ hoặc lỗi thư viện xử lý.

Hãy viết mã nguồn Python hoàn chỉnh cho riêng module `video_splitter_view` dưới dạng một Class/Component độc lập, và chỉ rõ cách export/import để:
- `app/shell.py` đăng ký feature mới vào sidebar (SPA navigation).
- View hiển thị trong Main Content Area khi người dùng click chọn từ Sidebar.
