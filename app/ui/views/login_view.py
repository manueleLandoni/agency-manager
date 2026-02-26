from __future__ import annotations

import flet as ft

from app.ui import theme as ui_theme


def login_view(on_login):
    username = ft.TextField(label='Username', autofocus=True)
    password = ft.TextField(label='Password', password=True, can_reveal_password=True)
    remember = ft.Checkbox(label='Ricordami (auto-login)')
    error_text = ft.Text('', color=ft.Colors.RED_600)

    def submit(_):
        ok, msg = on_login(username.value or '', password.value or '', bool(remember.value))
        error_text.value = '' if ok else msg
        username.update()
        password.update()
        remember.update()
        error_text.update()

    card = ft.Container(
        width=420,
        padding=30,
        border_radius=16,
        bgcolor=ui_theme.CARD_BG,
        border=ft.border.all(1, ui_theme.BORDER),
        shadow=ft.BoxShadow(blur_radius=24, color=ft.Colors.with_opacity(0.12, ft.Colors.BLACK26)),
        content=ft.Column(
            tight=True,
            spacing=14,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[ft.Image(src='logo.png', width=220)],
                ),
                ft.Text('Login locale sicuro', color=ui_theme.TEXT_MUTED),
                username,
                password,
                remember,
                ft.ElevatedButton('Accedi', on_click=submit),
                error_text,
                ft.Text('Primo avvio demo: admin / admin123!', size=12, color=ui_theme.TEXT_MUTED),
            ],
        ),
    )

    return ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            colors=[ui_theme.BG_GRADIENT_TOP, ui_theme.BG_GRADIENT_BOTTOM],
            begin=ft.Alignment(-1, -1),
            end=ft.Alignment(1, 1),
        ),
        content=ft.Row(alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[card]),
    )
