from __future__ import annotations

import flet as ft

from app.shell import AppShell


def main(page: ft.Page) -> None:
    page.title = "Dubb App"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.spacing = 0
    page.window_min_width = 1024
    page.window_min_height = 700
    page.bgcolor = "#121212"
    page.theme = ft.Theme(font_family="Segoe UI")

    shell = AppShell()
    page.add(shell.build(page))


if __name__ == "__main__":
    ft.run(main)
