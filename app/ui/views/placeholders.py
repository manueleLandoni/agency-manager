from __future__ import annotations

import flet as ft


def simple_placeholder(title: str, desc: str) -> ft.Control:
    return ft.Container(
        padding=20,
        content=ft.Column(
            controls=[
                ft.Text(title, size=24, weight=ft.FontWeight.BOLD),
                ft.Text(desc, color=ft.Colors.BLUE_GREY_600),
            ]
        ),
    )
