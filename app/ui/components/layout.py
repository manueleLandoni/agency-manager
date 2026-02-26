from __future__ import annotations

import flet as ft

from app.ui import theme as ui_theme


def app_shell(page: ft.Page, title: str, body: ft.Control, search_cb, nav_cb, on_logout, on_toggle_maximize, on_minimize_window, on_close_window) -> ft.Control:
    def _dest(icon_name: str, selected_icon_name: str, label: str) -> ft.NavigationRailDestination:
        return ft.NavigationRailDestination(
            icon=ft.Icon(icon_name, color=ui_theme.ICON_ACCENT),
            selected_icon=ft.Icon(selected_icon_name, color=ui_theme.ICON_ACCENT),
            label=label,
        )

    search = ft.TextField(
        hint_text='Ricerca globale...',
        prefix_icon=ft.Icons.SEARCH,
        color=ft.Colors.WHITE,
        hint_style=ft.TextStyle(color=ft.Colors.WHITE),
        dense=True,
        on_change=lambda e: search_cb(e.control.value),
        width=380,
    )

    rail = ft.NavigationRail(
        bgcolor=ui_theme.BG,
        selected_index=_selected_index(page.route),
        label_type=ft.NavigationRailLabelType.ALL,
        selected_label_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
        unselected_label_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_500),
        indicator_color=ft.Colors.with_opacity(0.14, ft.Colors.WHITE),
        leading=ft.Container(
            padding=ft.padding.only(top=8, bottom=14),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[ft.Image(src='logo.png', width=110)],
            ),
        ),
        destinations=[
            _dest(ft.Icons.DASHBOARD_OUTLINED, ft.Icons.DASHBOARD, 'Dashboard'),
            _dest(ft.Icons.TRAVEL_EXPLORE_OUTLINED, ft.Icons.TRAVEL_EXPLORE, 'Ricerca Aziende'),
            _dest(ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE, 'Clienti'),
            _dest(ft.Icons.CONTACT_PAGE_OUTLINED, ft.Icons.CONTACT_PAGE, 'Contatti'),
            _dest(ft.Icons.PUBLIC_OUTLINED, ft.Icons.PUBLIC, 'Siti'),
            _dest(ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH, 'Appuntamenti'),
            _dest(ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, 'Impostazioni'),
            _dest(ft.Icons.BACKUP_OUTLINED, ft.Icons.BACKUP, 'Backup'),
        ],
        on_change=lambda e: nav_cb(e.control.selected_index),
    )

    topbar = ft.Container(
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
        bgcolor=ui_theme.TOPBAR_BG,
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.WindowDragArea(
                    maximizable=True,
                    content=ft.Container(
                        expand=True,
                        content=ft.Text(title, size=24, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                    ),
                ),
                ft.Row(
                    controls=[
                        search,
                        ft.IconButton(icon=ft.Icons.LOGOUT, icon_color=ft.Colors.WHITE, tooltip='Logout', on_click=lambda _: on_logout()),
                        ft.IconButton(
                            icon=ft.Icons.OPEN_IN_FULL,
                            icon_color=ft.Colors.WHITE,
                            tooltip='Ingrandisci/Ripristina',
                            on_click=lambda _: on_toggle_maximize(),
                        ),
                        ft.IconButton(
                            icon=ft.Icons.MINIMIZE,
                            icon_color=ft.Colors.WHITE,
                            tooltip='Riduci a icona',
                            on_click=lambda _: on_minimize_window(),
                        ),
                        ft.IconButton(icon=ft.Icons.CLOSE, icon_color=ft.Colors.WHITE, tooltip='Chiudi', on_click=lambda _: on_close_window()),
                    ]
                ),
            ],
        ),
    )

    return ft.Container(
        expand=True,
        bgcolor=ui_theme.BG,
        content=ft.Row(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(
                    content=rail,
                    bgcolor=ui_theme.BG,
                    border=ft.border.only(right=ft.BorderSide(1, ui_theme.BORDER)),
                    width=220,
                    padding=10,
                ),
                ft.Container(width=1, bgcolor=ui_theme.BORDER),
                ft.Column(
                    expand=True,
                    spacing=0,
                    controls=[
                        topbar,
                        ft.Divider(height=1),
                        ft.Container(content=body, expand=True, padding=16, bgcolor=ui_theme.BG),
                    ],
                ),
            ],
        ),
    )


def _selected_index(route: str) -> int:
    mapping = {
        '/dashboard': 0,
        '/company-search': 1,
        '/clients': 2,
        '/contacts': 3,
        '/sites': 4,
        '/appointments': 5,
        '/settings': 6,
        '/backup': 7,
    }
    return mapping.get(route, 0)
