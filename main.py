from __future__ import annotations

import flet as ft

from app.shell import AppShell
from utils.vendor_bootstrap import ensure_pyvideotrans_vendor, format_vendor_error


def main(page: ft.Page) -> None:
    page.title = "Dubb App"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.spacing = 0
    page.window_min_width = 1024
    page.window_min_height = 700
    page.bgcolor = "#121212"
    page.theme = ft.Theme(font_family="Segoe UI")

    status_text = ft.Text(
        "Ứng dụng đang khởi động...",
        size=20,
        weight=ft.FontWeight.W_600,
        color="#F5F5F5",
    )
    detail_text = ft.Text(
        "Đang chuẩn bị pyvideotrans. Lần đầu chạy cần có kết nối mạng để tải vendor.",
        size=13,
        color="#BDBDBD",
        text_align=ft.TextAlign.CENTER,
    )
    progress = ft.ProgressRing(width=34, height=34, stroke_width=3, color="#4FC3F7")
    retry_button = ft.OutlinedButton("Thử lại", icon=ft.Icons.REFRESH, visible=False)

    loading_view = ft.Container(
        expand=True,
        alignment=ft.alignment.center,
        bgcolor="#121212",
        content=ft.Column(
            width=560,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                progress,
                status_text,
                detail_text,
                retry_button,
            ],
        ),
    )
    page.add(loading_view)

    def request_refresh() -> None:
        if hasattr(page, "schedule_update"):
            page.schedule_update()
        else:
            page.update()

    def set_boot_message(message: str) -> None:
        detail_text.value = message
        request_refresh()

    def show_app() -> None:
        page.controls.clear()
        shell = AppShell()
        page.add(shell.build(page))
        request_refresh()

    def show_error(message: str) -> None:
        progress.visible = False
        retry_button.visible = True
        status_text.value = "Không thể khởi động ứng dụng"
        detail_text.value = message
        request_refresh()

    def bootstrap() -> None:
        progress.visible = True
        retry_button.visible = False
        status_text.value = "Ứng dụng đang khởi động..."
        detail_text.value = "Đang chuẩn bị pyvideotrans. Vui lòng giữ kết nối mạng trong lần chạy đầu tiên."
        request_refresh()
        try:
            status = ensure_pyvideotrans_vendor(on_progress=set_boot_message)
            if not status.ready:
                show_error(format_vendor_error(status))
                return
            show_app()
        except Exception as exc:
            show_error(f"Lỗi khi chuẩn bị pyvideotrans: {exc}")

    retry_button.on_click = lambda _: page.run_thread(bootstrap)
    page.run_thread(bootstrap)


if __name__ == "__main__":
    ft.run(main)
