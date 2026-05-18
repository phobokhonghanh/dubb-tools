from __future__ import annotations

import flet as ft

from app.features.base import BaseFeatureView
from app.features.download_view import DownloadView
from app.features.merger_view import MergerView
from app.features.pipeline_view import PipelineView
from app.features.stt_view import SttView
from app.features.translate_view import TranslateView
from app.features.tts_view import TtsView
from app.features.video_splitter_view import VideoSplitterView


BG = "#121212"
SIDEBAR_BG = "#171717"
ACCENT = "#00D4FF"


class AppShell:
    def __init__(self) -> None:
        self.features: list[BaseFeatureView] = [
            DownloadView(),
            VideoSplitterView(),
            SttView(),
            TranslateView(),
            TtsView(),
            MergerView(),
            PipelineView(),
        ]
        self.active_id = self.features[0].feature_id

    def _get_active(self) -> BaseFeatureView:
        for feature in self.features:
            if feature.feature_id == self.active_id:
                return feature
        return self.features[0]

    def build(self, page: ft.Page) -> ft.Control:
        content_holder = ft.Container(expand=True, animate_opacity=220)

        def render_content() -> None:
            active = self._get_active()
            content_holder.opacity = 0.2
            content_holder.content = active.build(page)
            content_holder.opacity = 1
            page.update()

        nav = ft.NavigationRail(
            selected_index=0,
            bgcolor=SIDEBAR_BG,
            indicator_color=ACCENT,
            extended=True,
            min_extended_width=220,
            destinations=[
                ft.NavigationRailDestination(icon=f.icon, label=f.title) for f in self.features
            ],
            on_change=lambda e: on_nav_change(int(e.control.selected_index)),
        )

        def on_nav_change(index: int) -> None:
            self.active_id = self.features[index].feature_id
            render_content()

        render_content()
        return ft.Container(
            expand=True,
            bgcolor=BG,
            content=ft.Row(
                expand=True,
                controls=[
                    ft.Container(
                        width=260,
                        bgcolor=SIDEBAR_BG,
                        padding=ft.Padding(top=12, right=0, bottom=0, left=0),
                        content=ft.Column(
                            controls=[
                                ft.Container(
                                    padding=16,
                                    content=ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.DATA_OBJECT, color=ACCENT, size=22),
                                            ft.Text("Dubb App", size=18, weight=ft.FontWeight.BOLD),
                                        ]
                                    ),
                                ),
                                ft.Container(expand=True, content=nav),
                            ],
                        ),
                    ),
                    ft.VerticalDivider(width=1, color="#252525"),
                    content_holder,
                ],
            ),
        )
