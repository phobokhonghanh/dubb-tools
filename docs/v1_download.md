"Bạn là một chuyên gia Kiến trúc Phần mềm kiêm UX/UI và Senior Desktop Developer. Tôi muốn bạn xây dựng một ứng dụng Desktop bằng Python sử dụng thư viện Flet (hoặc PyQt6 với phong cách thiết kế Fluent Design/Material UI). Mục tiêu tối thượng là ứng dụng phải chạy mượt mà như một Web Single-Page Application (SPA) và có cấu trúc Module/Plugin để dễ dàng mở rộng, thêm bớt nhiều tính năng (Features) khác nhau sau này (ví dụ: Tool dịch thuật, Tool cấu hình hệ thống, v.v.). Hiện tại, tính năng đầu tiên cần hiện thực hóa là Tool Tải File từ URL.

Hãy thiết kế và viết mã nguồn ứng dụng với các tiêu chuẩn nghiêm ngặt sau:

1. Cấu trúc Source Code & Khả năng Mở rộng (Modular Architecture):

    Cấu trúc dự án phải tách biệt rõ ràng: main.py (Quản lý ứng dụng & Shell UI), thư mục views/ hoặc features/ chứa các component riêng biệt của từng tính năng.

    Mỗi Feature (như Tool Tải File, Tool Dịch) phải là một Class hoặc một Module độc lập kế thừa từ một Base Component chung, nhận diện qua một ID hoặc Route nhất định.

    Hệ thống điều hướng (Router/Navigation Manager) quản lý việc chuyển đổi giữa các View trong vùng nội dung chính một cách mượt mà mà không làm load lại toàn bộ ứng dụng.

2. Phong cách Thiết kế UI/UX & Khung Layout Tổng thể (SPA Shell):

    Bố cục tổng thể (Main Layout): Chia làm 2 phần chính:

        Sidebar (Thanh điều hướng bên trái): Nhỏ gọn, chứa logo ứng dụng và danh sách các Icon + Text của từng Feature (Hiện tại gồm: "Bộ tải File" và một Selector mẫu cho "Công cụ Dịch" để chờ sẵn). Có trạng thái Active rõ rệt cho tính năng đang chọn.

        Main Content Area (Vùng nội dung chính bên phải): Chiếm phần lớn diện tích, tự động thay đổi giao diện tương ứng với Feature được click từ Sidebar.

    Theme: Dark Mode sang trọng làm chủ đạo (Background dạng mờ hoặc xám tối #121212), font chữ hiện đại (Roboto hoặc Inter).

    Layout các Feature: Bố cục dạng Card (Thẻ) bo tròn góc lớn (border-radius: 12px hoặc hơn), có hiệu ứng bóng đổ (Drop Shadow) tinh tế.

    Hiệu ứng (Animations): Nút bấm có hiệu ứng Hover đổi màu mượt mà, chuyển đổi giữa các Feature có hiệu ứng chuyển cảnh (Fade hoặc Slide nhẹ).

3. Hiện thực hóa Feature 1: Tool Tải File từ URL (Module download_view):

    UI Components:

        Header: Tiêu đề ứng dụng kèm một icon công nghệ tối giản.

        URL Input Section: Ô nhập Link rộng rãi, có placeholder mờ hướng dẫn người dùng, khi focus vào sẽ đổi màu viền (Border highlight).

        Control Button: Nút "Download" lớn, nổi bật (Accent color như Xanh neon hoặc Tím công nghệ). Khi đang tải, nút này sẽ chuyển sang trạng thái Loading Spinner (Vòng xoay chờ) và text đổi thành "Downloading...".

        Progress Card (Chỉ hiện khi bắt đầu tải): Một chiếc thẻ (Card) riêng biệt xuất hiện mềm mại (Fade-in), chứa: Tên file rút gọn kèm icon định dạng | Progress Bar chạy mượt theo % thực tế | Grid thông số nhỏ phía dưới (Tốc độ MB/s, Đã tải/Tổng dung lượng, ETA).

    Trạng thái kết thúc: Success Toast màu xanh kèm nút "Mở thư mục" ở góc screen; hoặc hiển thị lỗi tinh tế dạng text đỏ trong Card nếu thất bại.

4. Xử lý Logic & Đa luồng (Backend):

    Chạy các hàm xử lý nặng (như download hoặc gọi API dịch thuật sau này) trên luồng riêng (Background Thread) để UI luôn mượt mà ở tốc độ 60fps, không bao giờ bị đơ (Freeze).

    Sử dụng cơ chế Streaming/Chunking để tối ưu bộ nhớ RAM cho hệ thống.

    Thiết kế tinh gọn cho việc xử lý tuần tự từng job một tại một thời điểm (Single-job execution).

Hãy viết mã nguồn Python hoàn chỉnh, tổ chức code theo cấu trúc thư mục/file rõ ràng (giả định cấu trúc module), code sạch sẽ theo Class/Component và có chú thích tiếng Việt đầy đủ để tôi dễ dàng copy-paste và phát triển thêm các module tính năng sau này."