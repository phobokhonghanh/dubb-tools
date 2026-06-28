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

        # Import output dir utilities
        from constants import DEFAULT_OUTPUT_DIR, save_user_output_dir

        path_text = ft.Text(
            value=str(DEFAULT_OUTPUT_DIR),
            size=12,
            color="#888888",
            overflow=ft.TextOverflow.ELLIPSIS,
            weight=ft.FontWeight.NORMAL,
        )

        def pick_directory(e) -> None:
            from app.features.stt_view import pick_directory_native
            from constants import DEFAULT_OUTPUT_DIR
            picked = pick_directory_native(str(DEFAULT_OUTPUT_DIR))
            if picked:
                save_user_output_dir(picked)
                path_text.value = picked
                path_text.update()
                
                # Sync output directories in all features
                for feature in self.features:
                    if hasattr(feature, "_output_dir"):
                        feature._output_dir = picked
                    elif hasattr(feature, "output_dir"):
                        feature.output_dir = picked
                    
                    # Update active controls if present
                    if hasattr(feature, "controls") and isinstance(feature.controls, dict):
                        field = feature.controls.get("output_dir_field")
                        if field:
                            try:
                                field.value = picked
                                field.update()
                            except Exception:
                                pass
                render_content()

        def on_hover(e) -> None:
            is_hovered = e.data == "true"
            path_text.weight = ft.FontWeight.BOLD if is_hovered else ft.FontWeight.NORMAL
            path_text.color = ft.Colors.WHITE if is_hovered else "#888888"
            path_text.update()

        output_dir_container = ft.Container(
            padding=ft.Padding(left=16, right=16, top=8, bottom=16),
            content=ft.Column(
                spacing=4,
                controls=[
                    ft.Text("Thư mục lưu:", size=11, color="#555555", weight=ft.FontWeight.BOLD),
                    ft.GestureDetector(
                        on_tap=pick_directory,
                        mouse_cursor="click",
                        content=ft.Container(
                            content=path_text,
                            on_hover=on_hover,
                        )
                    )
                ]
            )
        )

        def render_content() -> None:
            active = self._get_active()
            content_holder.opacity = 0.2
            
            # Sync value before rendering
            from constants import DEFAULT_OUTPUT_DIR
            if hasattr(active, "_output_dir"):
                active._output_dir = str(DEFAULT_OUTPUT_DIR)
            elif hasattr(active, "output_dir"):
                active.output_dir = str(DEFAULT_OUTPUT_DIR)

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
            prev_active = self._get_active()
            if hasattr(prev_active, "dispose"):
                try:
                    prev_active.dispose()
                except Exception:
                    pass
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
                                output_dir_container,
                            ],
                        ),
                    ),
                    ft.VerticalDivider(width=1, color="#252525"),
                    content_holder,
                ],
            ),
        )
