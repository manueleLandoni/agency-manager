from __future__ import annotations

from datetime import date

import flet as ft

from app.ui import theme as ui_theme


def dashboard_view(
    username: str,
    stats: dict[str, int],
    today_appointments: list[dict],
    hosting_expiry: list[dict],
    latest_contacts: list[dict],
    latest_searches: list[dict],
    open_company_search,
) -> ft.Control:
    stat_cards = [_metric(label, str(value), '#1A2436') for label, value in stats.items()]
    return ft.Column(
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Text(f'Benvenuto in Dashboard, {username}', size=22, weight=ft.FontWeight.W_700, color=ft.Colors.WHITE),
            ft.Text('Usa la sidebar per gestire dati e credenziali.', color=ui_theme.TEXT_MUTED),
            ft.ResponsiveRow([ft.Container(col={'sm': 6, 'md': 4, 'xl': 2}, content=card) for card in stat_cards]),
            ft.Container(
                padding=12,
                border=ft.border.all(1, ui_theme.BORDER),
                border_radius=10,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text('Nuovo: ricerca aziende da web scraping', weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        ft.OutlinedButton('Apri Ricerca Aziende', icon=ft.Icons.TRAVEL_EXPLORE, on_click=lambda _: open_company_search()),
                    ],
                ),
            ),
            ft.Container(
                padding=12,
                border=ft.border.all(1, ui_theme.BORDER),
                border_radius=10,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                f"Timeline Orizzontale Appuntamenti ({date.today().strftime('%Y-%m-%d')})",
                                weight=ft.FontWeight.W_600,
                                color=ft.Colors.WHITE,
                            ),
                            _horizontal_timeline(today_appointments),
                        ],
                    ),
                ),
            ft.ResponsiveRow(
                controls=[
                    ft.Container(
                        col={'sm': 12, 'md': 4},
                        content=_simple_table_card(
                            'Hosting in scadenza',
                            ['Dominio', 'Cliente', 'Scadenza'],
                            [[r.get('domain') or '-', r.get('client_name') or '-', _expiry_label(r)] for r in hosting_expiry],
                        ),
                    ),
                    ft.Container(
                        col={'sm': 12, 'md': 4},
                        content=_simple_table_card(
                            'Ultimi contatti salvati',
                            ['Nome', 'Azienda', 'Telefono'],
                            [[r.get('name') or '-', r.get('company') or '-', r.get('phone') or '-'] for r in latest_contacts],
                        ),
                    ),
                    ft.Container(
                        col={'sm': 12, 'md': 4},
                        content=_simple_table_card(
                            'Ultime ricerche aziende',
                            ['Azienda', 'Telefono', 'Provincia'],
                            [[r.get('company') or '-', r.get('phone') or '-', r.get('province') or '-'] for r in latest_searches],
                        ),
                    ),
                ],
            ),
        ],
    )


def _horizontal_timeline(rows: list[dict]) -> ft.Control:
    start_minutes = 7 * 60
    end_minutes = 21 * 60
    px_per_minute = 1.9
    left_axis = 70
    top_axis = 28
    lane_height = 76
    right_pad = 24

    events: list[dict] = []
    for row in rows:
        start = _time_to_minutes(row.get('start_time') or '')
        end = _time_to_minutes(row.get('end_time') or '')
        if start is None or end is None or end <= start:
            continue
        start = max(start_minutes, min(end_minutes, start))
        end = max(start_minutes, min(end_minutes, end))
        if end <= start:
            continue
        events.append({'row': row, 'start': start, 'end': end})

    if not events:
        return ft.Container(padding=ft.padding.symmetric(vertical=8), content=ft.Text('Nessun appuntamento per oggi.'))

    events.sort(key=lambda event: (event['start'], event['end']))
    active: list[tuple[int, int]] = []
    max_lane = 0
    for event in events:
        active = [entry for entry in active if entry[0] > event['start']]
        used = {entry[1] for entry in active}
        lane = 0
        while lane in used:
            lane += 1
        event['lane'] = lane
        active.append((event['end'], lane))
        max_lane = max(max_lane, lane)

    track_width = int((end_minutes - start_minutes) * px_per_minute) + left_axis + right_pad
    track_height = top_axis + ((max_lane + 1) * lane_height) + 20
    controls: list[ft.Control] = []

    for minutes in range(start_minutes, end_minutes + 1, 60):
        x = left_axis + int((minutes - start_minutes) * px_per_minute)
        controls.append(ft.Container(left=x, top=top_axis, bottom=0, width=1, bgcolor=ui_theme.BORDER))
        controls.append(
            ft.Container(
                left=max(0, x - 16),
                top=4,
                content=ft.Text(f'{minutes // 60:02d}:00', size=10, color=ui_theme.TEXT_MUTED),
            )
        )

    card_colors = {
        'VISITA': ft.Colors.GREEN_700,
        'RICONTATTO': ft.Colors.LIGHT_BLUE_700,
        'CONSEGNA': ft.Colors.ORANGE_700,
        'PERSONALI': ft.Colors.BLUE_GREY_600,
    }
    for event in events:
        row = event['row']
        kind = (str(row.get('appointment_type') or '').strip().upper() or 'PERSONALI')
        left = left_axis + int((event['start'] - start_minutes) * px_per_minute)
        width = max(120, int((event['end'] - event['start']) * px_per_minute) - 4)
        top = top_axis + (event['lane'] * lane_height) + 6
        controls.append(
            ft.Container(
                left=left,
                top=top,
                width=width,
                height=64,
                bgcolor=card_colors.get(kind, ft.Colors.BLUE_GREY_600),
                border_radius=8,
                padding=8,
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Text(f"{row.get('start_time')} - {row.get('end_time')}", size=11, color=ft.Colors.WHITE),
                        ft.Text(kind, size=11, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        ft.Text(row.get('subject_name') or '-', size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.WHITE),
                    ],
                ),
            )
        )

    track = ft.Stack(width=track_width, height=track_height, controls=controls)
    return ft.Row(scroll=ft.ScrollMode.AUTO, controls=[track])


def _time_to_minutes(value: str) -> int | None:
    parts = (value or '').split(':')
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    h = int(parts[0])
    m = int(parts[1])
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return (h * 60) + m


def _metric(label: str, value: str, color: str) -> ft.Control:
    return ft.Container(
        height=104,
        padding=16,
        border_radius=12,
        bgcolor=color,
        border=ft.border.all(1, ui_theme.BORDER),
        content=ft.Column(
            [
                ft.Text(label, color=ft.Colors.WHITE),
                ft.Text(value, size=28, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
            ]
        ),
    )


def _expiry_label(row: dict) -> str:
    expiry = (row.get('expiry_date') or '').strip() or '-'
    days_left = row.get('days_left')
    if days_left is None:
        return expiry
    try:
        d = int(days_left)
    except (TypeError, ValueError):
        return expiry
    if d < 0:
        return f'{expiry} ({abs(d)}g fa)'
    if d == 0:
        return f'{expiry} (oggi)'
    return f'{expiry} ({d}g)'


def _simple_table_card(title: str, headers: list[str], rows: list[list[str]]) -> ft.Control:
    table = ft.DataTable(
        columns=[ft.DataColumn(ft.Text(h, size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE)) for h in headers],
        rows=[
            ft.DataRow(
                cells=[ft.DataCell(ft.Text(v, size=11, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=ft.Colors.WHITE)) for v in row_values]
            )
            for row_values in rows[:10]
        ],
        heading_row_height=38,
        data_row_min_height=34,
        data_row_max_height=42,
        heading_row_color=ui_theme.TABLE_HEADER_BG,
        column_spacing=14,
    )
    return ft.Container(
        padding=10,
        border=ft.border.all(1, ui_theme.BORDER),
        border_radius=10,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Text(title, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                ft.Container(height=290, content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[table])),
            ],
        ),
    )
