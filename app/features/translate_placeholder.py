from __future__ import annotations

import flet as ft

from app.features.base import BaseFeatureView


class TranslatePlaceholderView(BaseFeatureView):
    feature_id = "translate"
    title = "Dịch"
    icon = ft.Icons.TRANSLATE

    def build(self, page: ft.Page) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(self.icon, size=48, color=ft.Colors.BLUE_GREY_300),
                    ft.Text(
                        "Dịch sẽ được bổ sung ở phase tiếp theo.",
                        size=18,
                        color=ft.Colors.BLUE_GREY_100,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
            ),
        )
