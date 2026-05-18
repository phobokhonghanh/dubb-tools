from __future__ import annotations

from abc import ABC, abstractmethod

import flet as ft


class BaseFeatureView(ABC):
    feature_id: str = ""
    title: str = ""
    icon: str = ft.Icons.WIDGETS

    @abstractmethod
    def build(self, page: ft.Page) -> ft.Control:
        raise NotImplementedError
