from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Callable
from urllib.parse import quote_plus

import flet as ft

from app.ui import theme as ui_theme
from db.repository import AppointmentRepository, ClientRepository, ContactRepository

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TYPE_OPTIONS = [
    'VISITA',
    'RICONTATTO',
    'CONSEGNA',
    'PERSONALI',
]
TYPE_COLORS = {
    'VISITA': ft.Colors.GREEN_700,
    'RICONTATTO': ft.Colors.LIGHT_BLUE_700,
    'CONSEGNA': ft.Colors.ORANGE_700,
    'PERSONALI': ft.Colors.BLUE_GREY_600,
}
TYPE_TEXT_COLORS = {
    'VISITA': ft.Colors.WHITE,
    'RICONTATTO': ft.Colors.WHITE,
    'CONSEGNA': ft.Colors.WHITE,
    'PERSONALI': ft.Colors.WHITE,
}


def _time_options() -> list[str]:
    values: list[str] = []
    minutes = 7 * 60
    end = 21 * 60
    while minutes <= end:
        h = minutes // 60
        m = minutes % 60
        values.append(f'{h:02d}:{m:02d}')
        minutes += 30
    return values


TIME_OPTIONS = _time_options()


def _style_text_field(ctrl: ft.TextField) -> ft.TextField:
    ctrl.color = ft.Colors.WHITE
    ctrl.label_style = ft.TextStyle(color=ft.Colors.WHITE70)
    ctrl.hint_style = ft.TextStyle(color=ft.Colors.WHITE54)
    ctrl.border_color = ui_theme.BORDER
    ctrl.focused_border_color = ft.Colors.WHITE70
    return ctrl


def _style_dropdown(ctrl: ft.Dropdown) -> ft.Dropdown:
    ctrl.color = ft.Colors.WHITE
    ctrl.text_style = ft.TextStyle(color=ft.Colors.WHITE)
    ctrl.label_style = ft.TextStyle(color=ft.Colors.WHITE70)
    ctrl.border_color = ui_theme.BORDER
    ctrl.focused_border_color = ft.Colors.WHITE70
    return ctrl


class AppointmentsView:
    def __init__(self, page: ft.Page, session_user, notify: Callable[[str], None]) -> None:
        self.page = page
        self.user = session_user
        self.notify = notify
        self.repo = AppointmentRepository()
        self.client_repo = ClientRepository()
        self.contact_repo = ContactRepository()
        self.current_date = date.today().strftime('%Y-%m-%d')
        self._dialog: ft.AlertDialog | None = None

        self.date_field = _style_text_field(ft.TextField(label='Data', value=self.current_date, width=180, read_only=True))
        self.timeline_host = ft.Container(
            expand=True,
            border=ft.border.all(1, ui_theme.BORDER),
            border_radius=8,
            padding=8,
        )

    def build(self) -> ft.Control:
        self._reload()
        return ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(
                            controls=[
                                ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_color=ft.Colors.WHITE, tooltip='Giorno precedente', on_click=lambda _: self._move_day(-1)),
                                self.date_field,
                                ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color=ft.Colors.WHITE, tooltip='Giorno successivo', on_click=lambda _: self._move_day(1)),
                                ft.IconButton(icon=ft.Icons.CHAT, icon_color=ft.Colors.WHITE, tooltip='Invia agenda su WhatsApp', on_click=self._share_schedule_whatsapp),
                            ]
                        ),
                        ft.IconButton(icon=ft.Icons.ADD, icon_color=ft.Colors.WHITE, tooltip='Nuovo appuntamento', on_click=lambda _: self.open_dialog()),
                    ],
                ),
                ft.Text('Timeline giorno selezionato', weight=ft.FontWeight.W_600),
                self.timeline_host,
            ],
        )

    def set_search(self, _value: str) -> None:
        # Appuntamenti non usa ricerca globale: mostra sempre il giorno selezionato.
        return

    def _move_day(self, delta_days: int) -> None:
        base = datetime.strptime(self.current_date, '%Y-%m-%d').date()
        self.current_date = (base + timedelta(days=delta_days)).strftime('%Y-%m-%d')
        self.date_field.value = self.current_date
        self._reload()
        self.page.update()

    def _reload(self) -> None:
        rows = self.repo.list_by_date(self.current_date)
        self.timeline_host.content = self._build_timeline(rows)

    def _build_maps_query(self, row: dict) -> str:
        subject_name = (row.get('subject_name') or '').strip()
        details = (
            self.contact_repo.find_contact_by_name(subject_name)
            if row.get('subject_type') == 'contact'
            else self.client_repo.find_client_by_name(subject_name)
        ) or {}
        parts = [
            subject_name,
            (details.get('company') or '').strip(),
            (details.get('address') or '').strip(),
            (details.get('municipality') or '').strip(),
            (details.get('city') or '').strip(),
            (details.get('province') or '').strip(),
            (details.get('region') or '').strip(),
        ]
        return ', '.join([part for part in parts if part and part != '-'])

    def _build_subject_label(self, row: dict) -> str:
        subject_name = (row.get('subject_name') or '-').strip() or '-'
        details = (
            self.contact_repo.find_contact_by_name(subject_name)
            if row.get('subject_type') == 'contact'
            else self.client_repo.find_client_by_name(subject_name)
        ) or {}
        company = (details.get('company') or '').strip()
        if company and company.lower() != subject_name.lower():
            return f'{subject_name} | {company}'
        return subject_name

    def _build_share_message(self, rows: list[dict]) -> str:
        if not rows:
            return f'Agenda {self.current_date}\nNessun appuntamento.'

        lines = [f'Agenda {self.current_date}']
        for row in rows:
            start = (row.get('start_time') or '').strip()
            end = (row.get('end_time') or '').strip()
            appointment_type = (str(row.get('appointment_type') or '').strip().upper() or 'PERSONALI')
            subject_name = self._build_subject_label(row)
            maps_query = self._build_maps_query(row)
            maps_url = f'https://www.google.com/maps/search/?api=1&query={quote_plus(maps_query)}' if maps_query else ''

            lines.append(f'- {start} - {end} | {appointment_type} | {subject_name}')
            if maps_url:
                lines.append(f'  Maps: {maps_url}')

        return '\n'.join(lines)

    async def _share_schedule_whatsapp(self, _: ft.ControlEvent) -> None:
        rows = self.repo.list_by_date(self.current_date)
        if not rows:
            self.notify('Nessun appuntamento da inviare')
            return
        message = self._build_share_message(rows)
        whatsapp_url = f'https://wa.me/?text={quote_plus(message)}'
        await self.page.launch_url(whatsapp_url)

    def _normalize_phone_for_wa(self, raw_phone: str) -> str:
        digits = ''.join(ch for ch in (raw_phone or '') if ch.isdigit())
        if digits.startswith('00'):
            digits = digits[2:]
        # Default country prefix for local Italian numbers.
        if digits and not digits.startswith('39'):
            digits = f'39{digits}'
        return digits

    async def _send_single_appointment_whatsapp(self, row: dict) -> None:
        subject_name = (row.get('subject_name') or '').strip()
        subject_type = (row.get('subject_type') or '').strip()
        details = {}
        if subject_type == 'contact':
            details = self.contact_repo.find_contact_by_name(subject_name) or {}
        elif subject_type == 'client':
            details = self.client_repo.find_client_by_name(subject_name) or {}

        if not details:
            # Fallback on opposite repository in case old data has wrong subject_type.
            details = self.contact_repo.find_contact_by_name(subject_name) or self.client_repo.find_client_by_name(subject_name) or {}

        phone = self._normalize_phone_for_wa((details.get('phone') or details.get('landline_phone') or '').strip())
        if not phone:
            self.notify('Numero telefono non disponibile per questo appuntamento')
            return

        app_date = (row.get('appointment_date') or self.current_date).strip()
        start_time = (row.get('start_time') or '').strip()
        end_time = (row.get('end_time') or '').strip()
        text = (
            "fastudioagencyadv.it\n\n"
            f"Gentile {subject_name},\n"
            "Le ricordiamo l'appuntamento programmato.\n"
            f"Data: {app_date}\n"
            f"Orario: {start_time} - {end_time}\n\n"
            "Cordiali saluti."
        )
        url = f'https://wa.me/{phone}?text={quote_plus(text)}'
        await self.page.launch_url(url)

    def _appointment_whatsapp_handler(self, row: dict):
        def send(_: ft.ControlEvent) -> None:
            self.page.run_task(self._send_single_appointment_whatsapp, dict(row))

        return send

    def _build_timeline(self, rows: list[dict]) -> ft.Control:
        start_minutes = 7 * 60
        end_minutes = 21 * 60
        slot_height = 52
        total_height = int(((end_minutes - start_minutes) / 60) * slot_height)
        bottom_padding = 28
        controls: list[ft.Control] = []
        layout_map = self._compute_overlap_layout(rows)

        # Hour marks every 60 minutes.
        for minutes in range(start_minutes, end_minutes + 1, 60):
            top = int(((minutes - start_minutes) / 60) * slot_height)
            label = f'{minutes // 60:02d}:00'
            controls.append(
                ft.Container(
                    left=0,
                    right=0,
                    top=top,
                    height=1,
                    bgcolor=ft.Colors.BLUE_GREY_200,
                )
            )
            controls.append(
                ft.Container(
                    left=6,
                    top=max(0, top - 10),
                    bgcolor=ui_theme.CARD_BG,
                    padding=ft.padding.symmetric(horizontal=4, vertical=2),
                    content=ft.Text(label, size=11, color=ui_theme.TEXT_MUTED),
                )
            )

        for idx, row in enumerate(rows):
            start = self._time_to_minutes(row.get('start_time') or '')
            end = self._time_to_minutes(row.get('end_time') or '')
            if start is None or end is None:
                continue
            if end <= start:
                continue
            start = max(start_minutes, min(end_minutes, start))
            end = max(start_minutes, min(end_minutes, end))
            if end <= start:
                continue

            top = ((start - start_minutes) / 60) * slot_height
            height = max(52, ((end - start) / 60) * slot_height)
            layout = layout_map.get(idx, {'column': 0, 'total_columns': 1})
            column = layout['column']
            total_columns = max(1, layout['total_columns'])
            appointment_type = (str(row.get('appointment_type') or '').strip().upper() or 'PERSONALI')
            badge_text = appointment_type
            block_color = TYPE_COLORS.get(appointment_type, ft.Colors.BLUE_GREY_600)
            text_color = TYPE_TEXT_COLORS.get(appointment_type, ft.Colors.WHITE)
            appointment_id = row.get('id')
            card = ft.Container(
                expand=True,
                border_radius=8,
                bgcolor=block_color,
                padding=8,
                content=ft.Column(
                    spacing=2,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(f"{row.get('start_time')} - {row.get('end_time')}", size=11, color=text_color),
                                ft.Row(
                                    spacing=0,
                                    controls=[
                                        ft.IconButton(
                                            icon=ft.Icons.NOTIFICATIONS_ACTIVE,
                                            icon_color=text_color,
                                            icon_size=16,
                                            tooltip='Promemoria WhatsApp',
                                            on_click=self._appointment_whatsapp_handler(dict(row)),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.EDIT,
                                            icon_color=text_color,
                                            icon_size=16,
                                            tooltip='Modifica',
                                            on_click=lambda _, aid=appointment_id: self.open_dialog(aid),
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.DELETE,
                                            icon_color=text_color,
                                            icon_size=16,
                                            tooltip='Elimina',
                                            on_click=lambda _, aid=appointment_id: self._confirm_delete(aid),
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        ft.Text(badge_text, size=11, weight=ft.FontWeight.W_600, color=text_color),
                        ft.Text(row.get('subject_name') or '-', max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=text_color),
                    ],
                ),
            )
            row_columns: list[ft.Control] = []
            for col_idx in range(total_columns):
                if col_idx == column:
                    row_columns.append(card)
                else:
                    row_columns.append(ft.Container(expand=True))

            controls.append(
                ft.Container(
                    left=82,
                    right=10,
                    top=top + 2,
                    height=height - 4,
                    content=ft.Row(expand=True, spacing=6, controls=row_columns),
                )
            )

        stack = ft.Stack(
            controls=[
                ft.Container(
                    left=76,
                    top=0,
                    bottom=0,
                    width=1,
                    bgcolor=ft.Colors.BLUE_GREY_300,
                ),
                *controls,
            ],
            width=None,
            height=total_height + bottom_padding,
        )
        return ft.Column(scroll=ft.ScrollMode.AUTO, controls=[stack])

    def _compute_overlap_layout(self, rows: list[dict]) -> dict[int, dict[str, int]]:
        events: list[dict] = []
        for idx, row in enumerate(rows):
            start = self._time_to_minutes(row.get('start_time') or '')
            end = self._time_to_minutes(row.get('end_time') or '')
            if start is None or end is None or end <= start:
                continue
            events.append({'idx': idx, 'start': start, 'end': end})

        if not events:
            return {}

        events.sort(key=lambda event: (event['start'], event['end'], event['idx']))
        groups: list[list[dict]] = []
        current_group: list[dict] = []
        current_group_end = -1

        for event in events:
            if not current_group or event['start'] < current_group_end:
                current_group.append(event)
                current_group_end = max(current_group_end, event['end'])
                continue
            groups.append(current_group)
            current_group = [event]
            current_group_end = event['end']

        if current_group:
            groups.append(current_group)

        layout: dict[int, dict[str, int]] = {}
        for group in groups:
            active: list[tuple[int, int]] = []
            assigned: dict[int, int] = {}
            max_columns = 1

            for event in group:
                active = [entry for entry in active if entry[0] > event['start']]
                used_columns = {entry[1] for entry in active}
                column = 0
                while column in used_columns:
                    column += 1
                assigned[event['idx']] = column
                active.append((event['end'], column))
                max_columns = max(max_columns, len(active))

            for event in group:
                layout[event['idx']] = {'column': assigned[event['idx']], 'total_columns': max_columns}

        return layout

    def _time_to_minutes(self, value: str) -> int | None:
        parts = (value or '').split(':')
        if len(parts) != 2:
            return None
        if not (parts[0].isdigit() and parts[1].isdigit()):
            return None
        h = int(parts[0])
        m = int(parts[1])
        if h < 0 or h > 23 or m < 0 or m > 59:
            return None
        return (h * 60) + m

    def _confirm_delete(self, appointment_id: int) -> None:
        def do_delete(_):
            self.repo.delete_appointment(appointment_id, self.user.id)
            self._close_dialog()
            self._reload()
            self.page.update()
            self.notify('Appuntamento eliminato')

        self._dialog = ft.AlertDialog(
            bgcolor=ui_theme.CARD_BG,
            barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
            title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
            content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
            modal=True,
            title=ft.Text('Elimina appuntamento'),
            content=ft.Text('Confermi eliminazione appuntamento?'),
            actions=[ft.TextButton('Annulla', on_click=lambda _: self._close_dialog()), ft.ElevatedButton('Elimina', on_click=do_delete)],
        )
        self.page.show_dialog(self._dialog)

    def _close_dialog(self) -> None:
        if self._dialog:
            self.page.pop_dialog()
            self._dialog = None
            self.page.update()

    def open_dialog(self, appointment_id: int | None = None) -> None:
        initial = self.repo.get_appointment(appointment_id) if appointment_id else {}
        subject_type = ft.Switch(label='Usa Contatti (disattivo = Clienti)', value=(initial.get('subject_type') == 'contact'))
        search_field = _style_text_field(ft.TextField(label='Cerca', hint_text='Cerca clienti/contatti (ultimi 10)', width=520))
        subject_dropdown = _style_dropdown(ft.Dropdown(label='Seleziona soggetto', options=[], width=520))
        pin_date_switch = ft.Switch(label='Fissa data del giorno selezionato', value=True)
        appointment_date = _style_text_field(ft.TextField(label='Data (YYYY-MM-DD)', value=self.current_date, width=220, read_only=True))
        start_time = _style_dropdown(ft.Dropdown(label='Ora inizio', width=180, options=[ft.dropdown.Option(t) for t in TIME_OPTIONS], value=initial.get('start_time', '09:00')))
        end_time = _style_dropdown(ft.Dropdown(label='Ora fine', width=180, options=[ft.dropdown.Option(t) for t in TIME_OPTIONS], value=initial.get('end_time', '09:30')))
        app_type = _style_dropdown(ft.Dropdown(
            label='Tipologia appuntamento',
            width=320,
            options=[ft.dropdown.Option(t) for t in TYPE_OPTIONS],
            value=((str(initial.get('appointment_type') or '').strip().upper()) if (str(initial.get('appointment_type') or '').strip().upper()) in TYPE_OPTIONS else TYPE_OPTIONS[0]),
        ))
        outcome = _style_text_field(ft.TextField(label='Esito', value=initial.get('outcome', ''), width=520))
        notes = _style_text_field(ft.TextField(label='Note', multiline=True, min_lines=3, max_lines=6, value=initial.get('notes', ''), width=520))
        validation = ft.Text('', color=ft.Colors.RED_700, visible=False)

        def load_subject_options(query: str = '') -> None:
            if subject_type.value:
                choices = self.contact_repo.list_contact_choices(query=query, limit=10)
            else:
                choices = self.client_repo.list_client_choices(query=query, limit=10)
            options = []
            for c in choices:
                company = (c.get('company') or '').strip()
                label = f"{c['name']} | {company}" if company else c['name']
                options.append(ft.dropdown.Option(key=c['name'], text=label))
            subject_dropdown.options = options
            if initial.get('subject_name') and not subject_dropdown.value:
                subject_dropdown.value = initial.get('subject_name')
            self.page.update()

        def on_subject_type_change(_):
            load_subject_options((search_field.value or '').strip())

        subject_type.on_change = on_subject_type_change
        search_field.on_change = lambda e: load_subject_options((e.control.value or '').strip())

        def on_pin_date_change(_):
            appointment_date.read_only = bool(pin_date_switch.value)
            if pin_date_switch.value:
                appointment_date.value = self.current_date
            self.page.update()

        pin_date_switch.on_change = on_pin_date_change
        if initial:
            appointment_date.value = initial.get('appointment_date') or self.current_date
            subject_dropdown.value = initial.get('subject_name') or ''
            pin_date_switch.value = appointment_date.value == self.current_date
            subject_type.value = (initial.get('subject_type') == 'contact')
        on_pin_date_change(None)
        load_subject_options()

        def save(_):
            validation.visible = False
            validation.value = ''
            subj_name = (subject_dropdown.value or '').strip()
            date_value = (appointment_date.value or '').strip()
            if not subj_name:
                validation.value = 'Seleziona cliente/contatto'
                validation.visible = True
                self.page.update()
                return
            if not DATE_RE.match(date_value):
                validation.value = 'Data non valida (YYYY-MM-DD)'
                validation.visible = True
                self.page.update()
                return
            if (start_time.value or '') not in TIME_OPTIONS or (end_time.value or '') not in TIME_OPTIONS:
                validation.value = 'Orario non valido'
                validation.visible = True
                self.page.update()
                return
            if TIME_OPTIONS.index(end_time.value) <= TIME_OPTIONS.index(start_time.value):
                validation.value = 'Ora fine deve essere dopo ora inizio'
                validation.visible = True
                self.page.update()
                return

            payload = {
                'subject_type': 'contact' if subject_type.value else 'client',
                'subject_id': None,
                'subject_name': subj_name,
                'appointment_date': date_value,
                'start_time': start_time.value,
                'end_time': end_time.value,
                'appointment_type': (app_type.value or TYPE_OPTIONS[0]).upper(),
                'outcome': (outcome.value or '').strip(),
                'notes': (notes.value or '').strip(),
            }
            if appointment_id:
                self.repo.update_appointment(appointment_id, payload, self.user.id)
                self.notify('Appuntamento aggiornato')
            else:
                self.repo.create_appointment(payload, self.user.id)
                self.notify('Appuntamento creato')

            self._close_dialog()
            self._reload()
            self.page.update()

        self._dialog = ft.AlertDialog(
            bgcolor=ui_theme.CARD_BG,
            barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
            title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
            content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
            modal=True,
            title=ft.Text('Appuntamento' if appointment_id else 'Nuovo appuntamento'),
            content=ft.Container(
                width=760,
                content=ft.Column(
                    tight=True,
                    controls=[
                        validation,
                        subject_type,
                        search_field,
                        subject_dropdown,
                        pin_date_switch,
                        appointment_date,
                        ft.Row([start_time, end_time]),
                        app_type,
                        outcome,
                        notes,
                    ],
                ),
            ),
            actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close_dialog()), ft.ElevatedButton('Salva', on_click=save)],
        )
        self.page.show_dialog(self._dialog)
