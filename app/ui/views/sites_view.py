from __future__ import annotations

import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import flet as ft

from app.ui import theme as ui_theme
from core.clipboard_manager import ClipboardManager
from core.csv_tools import export_sites_csv, import_sites_csv_standard
from core.settings import SettingsService
from db.repository import ClientRepository, SiteRepository
from models.entities import SitePayload

DOMAIN_RE = re.compile(r"^(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$")
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
ALL_PROVIDERS_KEY = '__all__'
SORT_OPTIONS = {
    'expiry_asc',
    'expiry_desc',
    'domain_asc',
    'domain_desc',
    'client_asc',
    'client_desc',
    'provider_asc',
    'provider_desc',
    'status_asc',
    'status_desc',
    'updated_desc',
    'updated_asc',
}


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


class SitesView:
    def __init__(
        self,
        page: ft.Page,
        session_user,
        notify: Callable[[str], None],
    ) -> None:
        self.page = page
        self.session_user = session_user
        self.notify = notify
        self.repo = SiteRepository()
        self.client_repo = ClientRepository()
        self.clipboard = ClipboardManager()
        self.settings = SettingsService()
        self.current_page = 1
        self.page_size = self.settings.get_int_value('sites_page_size', default=10, min_value=5, max_value=50)
        self.current_query = ''
        self.current_provider = self.settings.get_value('sites_provider_filter', ALL_PROVIDERS_KEY)
        saved_sort = self.settings.get_value('sites_sort', 'expiry_asc')
        self.current_sort = saved_sort if saved_sort in SORT_OPTIONS else 'expiry_asc'
        self.total_items = 0

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text('Dominio', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Cliente', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Provider', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Scadenza', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Stato', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Aggiornato', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Azioni', color=ft.Colors.WHITE)),
            ],
            rows=[],
            expand=True,
            heading_row_color=ui_theme.TABLE_HEADER_BG,
        )

        self.page_label = ft.Text('Pag. 1/1', color=ft.Colors.WHITE)
        self.provider_filter = _style_dropdown(ft.Dropdown(label='Provider', options=[], width=220, on_select=self._on_provider_change))
        self.sort_selector = _style_dropdown(ft.Dropdown(
            label='Ordina per',
            width=260,
            value=self.current_sort,
            options=[
                ft.dropdown.Option('expiry_asc', 'Scadenza (vicina -> lontana)'),
                ft.dropdown.Option('expiry_desc', 'Scadenza (lontana -> vicina)'),
                ft.dropdown.Option('domain_asc', 'Dominio (A-Z)'),
                ft.dropdown.Option('domain_desc', 'Dominio (Z-A)'),
                ft.dropdown.Option('client_asc', 'Cliente (A-Z)'),
                ft.dropdown.Option('client_desc', 'Cliente (Z-A)'),
                ft.dropdown.Option('provider_asc', 'Provider (A-Z)'),
                ft.dropdown.Option('provider_desc', 'Provider (Z-A)'),
                ft.dropdown.Option('status_asc', 'Stato (Scaduto -> Attivo)'),
                ft.dropdown.Option('status_desc', 'Stato (Attivo -> Scaduto)'),
                ft.dropdown.Option('updated_desc', 'Aggiornato (piu recente)'),
                ft.dropdown.Option('updated_asc', 'Aggiornato (piu vecchio)'),
            ],
            on_select=self._on_sort_change,
        ))
        self.page_size_selector = _style_dropdown(ft.Dropdown(
            label='Righe pagina',
            width=150,
            value=str(self._normalize_page_size(self.page_size)),
            options=[ft.dropdown.Option(str(i)) for i in range(5, 51, 5)],
            on_select=self._on_page_size_change,
        ))
        self.page_size = int(self.page_size_selector.value or '10')
        self._dialog: ft.AlertDialog | None = None

    def build(self) -> ft.Control:
        self._load_provider_options()
        self._reload_table()

        return ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(controls=[self.provider_filter, self.sort_selector, self.page_size_selector]),
                    ],
                ),
                ft.Row(
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    controls=[
                        ft.Container(
                            expand=True,
                            border=ft.border.all(1, ui_theme.BORDER),
                            border_radius=8,
                            padding=8,
                            content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[self.table]),
                        ),
                        ft.Container(
                            padding=ft.padding.only(left=8),
                            content=ft.Column(
                                spacing=8,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.IconButton(icon=ft.Icons.ADD, icon_color=ft.Colors.WHITE, tooltip='Nuovo sito', on_click=lambda _: self.open_site_dialog()),
                                    ft.IconButton(icon=ft.Icons.UPLOAD_FILE, icon_color=ft.Colors.WHITE, tooltip='Import CSV siti', on_click=self._open_import_csv_dialog),
                                    ft.IconButton(icon=ft.Icons.DOWNLOAD, icon_color=ft.Colors.WHITE, tooltip='Export CSV siti', on_click=self._open_export_csv_dialog),
                                ],
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_color=ft.Colors.WHITE, on_click=self._prev_page),
                        self.page_label,
                        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color=ft.Colors.WHITE, on_click=self._next_page),
                    ],
                ),
            ],
        )

    def set_search(self, query: str) -> None:
        self.current_query = query.strip()
        self.current_page = 1
        self._reload_table()
        self.page.update()

    def _on_provider_change(self, e: ft.ControlEvent) -> None:
        self.current_provider = e.control.value or ALL_PROVIDERS_KEY
        self.settings.set_value('sites_provider_filter', self.current_provider)
        self.current_page = 1
        self._reload_table()
        self.page.update()

    def _on_sort_change(self, e: ft.ControlEvent) -> None:
        self.current_sort = e.control.value or 'expiry_asc'
        self.settings.set_value('sites_sort', self.current_sort)
        self.current_page = 1
        self._reload_table()
        self.page.update()

    def _on_page_size_change(self, e: ft.ControlEvent) -> None:
        raw = e.control.value or '10'
        self.page_size = self._normalize_page_size(int(raw) if raw.isdigit() else 10)
        self.settings.set_value('sites_page_size', str(self.page_size))
        self.current_page = 1
        self._reload_table()
        self.page.update()

    def _load_provider_options(self) -> None:
        providers = self.repo.list_providers()
        self.provider_filter.options = [ft.dropdown.Option(ALL_PROVIDERS_KEY, 'Tutti')] + [ft.dropdown.Option(p) for p in providers]
        provider_keys = {ALL_PROVIDERS_KEY, *providers}
        if self.current_provider not in provider_keys:
            self.current_provider = ALL_PROVIDERS_KEY
            self.settings.set_value('sites_provider_filter', self.current_provider)
        self.provider_filter.value = self.current_provider

    def _reload_table(self) -> None:
        provider_value = '' if self.current_provider == ALL_PROVIDERS_KEY else self.current_provider
        rows, total = self.repo.list_sites(
            query=self.current_query,
            provider=provider_value,
            page=self.current_page,
            page_size=self.page_size,
            sort_key=self.current_sort,
        )
        self.total_items = total

        table_rows: list[ft.DataRow] = []
        for row in rows:
            site_id = row['id']
            table_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(row['domain'], color=ft.Colors.WHITE)),
                        ft.DataCell(ft.Text(row.get('client_name') or '-', color=ft.Colors.WHITE)),
                        ft.DataCell(ft.Text(row.get('provider') or '-', color=ft.Colors.WHITE)),
                        ft.DataCell(ft.Text(_days_left_label(row.get('days_left'), row.get('expiry_date')), color=ft.Colors.WHITE)),
                        ft.DataCell(_expiry_badge(row.get('days_left'))),
                        ft.DataCell(ft.Text(row['updated_at'], color=ft.Colors.WHITE)),
                        ft.DataCell(
                            ft.Row(
                                spacing=0,
                                controls=[
                                    ft.IconButton(icon=ft.Icons.VISIBILITY, icon_color=ft.Colors.WHITE, tooltip='Dettagli', on_click=lambda _, sid=site_id: self.open_site_dialog(sid, read_only=True)),
                                    ft.IconButton(icon=ft.Icons.EDIT, icon_color=ft.Colors.WHITE, tooltip='Modifica', on_click=lambda _, sid=site_id: self.open_site_dialog(sid, read_only=False)),
                                    ft.IconButton(icon=ft.Icons.COPY, icon_color=ft.Colors.WHITE, tooltip='Duplica', on_click=lambda _, sid=site_id: self._duplicate_site(sid)),
                                    ft.IconButton(icon=ft.Icons.DELETE, icon_color=ft.Colors.WHITE, tooltip='Elimina', on_click=lambda _, sid=site_id: self._confirm_delete(sid)),
                                ],
                            )
                        ),
                    ]
                )
            )

        self.table.rows = table_rows
        max_page = max(1, math.ceil(total / self.page_size))
        if self.current_page > max_page:
            self.current_page = max_page
        self.page_label.value = f'Pag. {self.current_page}/{max_page} - {total} record'

    def _normalize_page_size(self, value: int) -> int:
        if value < 5:
            return 5
        if value > 50:
            return 50
        # round to nearest step of 5
        return max(5, min(50, int(round(value / 5) * 5)))

    def _prev_page(self, _):
        if self.current_page > 1:
            self.current_page -= 1
            self._reload_table()
            self.page.update()

    def _next_page(self, _):
        max_page = max(1, math.ceil(self.total_items / self.page_size))
        if self.current_page < max_page:
            self.current_page += 1
            self._reload_table()
            self.page.update()

    def _duplicate_site(self, site_id: int) -> None:
        data = self.repo.get_site(site_id, self.session_user.data_key)
        if not data:
            return
        data['domain'] = f"copy-{data['domain']}"
        payload = SitePayload(**{k: data.get(k) for k in SitePayload.__dataclass_fields__.keys()})
        self.repo.create_site(payload, self.session_user.id, self.session_user.data_key)
        self.notify('Sito duplicato')
        self._load_provider_options()
        self._reload_table()
        self.page.update()

    def _confirm_delete(self, site_id: int) -> None:
        def do_delete(_):
            self.repo.delete_site(site_id, self.session_user.id)
            self._close_dialog()
            self.notify('Sito eliminato')
            self._reload_table()
            self.page.update()

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Conferma eliminazione'),
            content=ft.Text('Vuoi eliminare definitivamente questo sito?'),
            actions=[
                ft.TextButton('Annulla', on_click=lambda _: self._close_dialog()),
                ft.ElevatedButton('Elimina', on_click=do_delete),
            ],
        )
        self.page.show_dialog(self._dialog)

    def _close_dialog(self):
        if self._dialog:
            self.page.pop_dialog()
            self._dialog = None
            self.page.update()

    def _open_export_csv_dialog(self, _):
        path_field = _style_text_field(ft.TextField(label='Percorso file CSV export', value='exports/sites_export.csv', width=560))
        include_sensitive = ft.Checkbox(
            label='Includi credenziali sensibili (solo se autorizzato)',
            value=bool(self.session_user.role == 'admin' or self.session_user.can_view_passwords),
        )

        def do_export(_):
            target = Path((path_field.value or '').strip())
            if not str(target):
                self.notify('Percorso file non valido')
                return
            can_sensitive = bool(self.session_user.role == 'admin' or self.session_user.can_view_passwords)
            count = export_sites_csv(target, self.session_user.data_key, include_sensitive=bool(include_sensitive.value and can_sensitive))
            self._close_dialog()
            self.notify(f'Export siti completato: {count} record in {target}')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Export CSV siti'),
            content=ft.Container(width=700, content=ft.Column(tight=True, controls=[path_field, include_sensitive])),
            actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close_dialog()), ft.ElevatedButton('Esporta', on_click=do_export)],
        )
        self.page.show_dialog(self._dialog)

    def _open_import_csv_dialog(self, _):
        path_field = _style_text_field(ft.TextField(label='Percorso file CSV import', value='exports/sites_export.csv', width=560))

        def do_import(_):
            source = Path((path_field.value or '').strip())
            if not source.exists():
                self.notify('File CSV non trovato')
                return
            count = import_sites_csv_standard(source, self.session_user.id, self.session_user.data_key)
            self._close_dialog()
            self._load_provider_options()
            self._reload_table()
            self.page.update()
            self.notify(f'Import siti completato: {count} record')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Import CSV siti'),
            content=ft.Container(width=700, content=ft.Column(tight=True, controls=[path_field])),
            actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close_dialog()), ft.ElevatedButton('Importa', on_click=do_import)],
        )
        self.page.show_dialog(self._dialog)

    def open_site_dialog(self, site_id: int | None = None, read_only: bool = False) -> None:
        can_view_sensitive = bool(self.session_user.role == 'admin' or self.session_user.can_view_passwords)
        initial = self.repo.get_site(site_id, self.session_user.data_key, include_sensitive=can_view_sensitive) if site_id else {}

        fields = {
            'domain': ft.TextField(label='Dominio *', value=initial.get('domain', '')),
            'provider': ft.TextField(label='Provider', value=initial.get('provider', '')),
            'expiry_date': ft.TextField(label='Data scadenza', hint_text='YYYY-MM-DD', value=initial.get('expiry_date', '')),
            'notes': ft.TextField(label='Note', multiline=True, min_lines=4, max_lines=8, value=initial.get('notes', '')),
            'hosting_panel': ft.TextField(label='Hosting panel', value=initial.get('hosting_panel', '')),
            'hosting_username': ft.TextField(label='Hosting username', value=initial.get('hosting_username', '')),
            'hosting_password': ft.TextField(label='Hosting password', password=True, can_reveal_password=True, value=initial.get('hosting_password', '')),
            'ftp_protocol': ft.Dropdown(label='Protocollo', options=[ft.dropdown.Option('sftp'), ft.dropdown.Option('ftp')], value=initial.get('ftp_protocol', 'sftp')),
            'ftp_host': ft.TextField(label='FTP host', value=initial.get('ftp_host', '')),
            'ftp_port': ft.TextField(label='FTP porta', value=str(initial.get('ftp_port', 22))),
            'ftp_username': ft.TextField(label='FTP username', value=initial.get('ftp_username', '')),
            'ftp_password': ft.TextField(label='FTP password', password=True, can_reveal_password=True, value=initial.get('ftp_password', '')),
            'mailbox_1_user': ft.TextField(label='Email aziendale 1', value=initial.get('mailbox_1_user', '')),
            'mailbox_1_pass': ft.TextField(label='Password 1', password=True, can_reveal_password=True, value=initial.get('mailbox_1_pass', '')),
            'mailbox_2_user': ft.TextField(label='Email aziendale 2', value=initial.get('mailbox_2_user', '')),
            'mailbox_2_pass': ft.TextField(label='Password 2', password=True, can_reveal_password=True, value=initial.get('mailbox_2_pass', '')),
            'mailbox_3_user': ft.TextField(label='Email aziendale 3', value=initial.get('mailbox_3_user', '')),
            'mailbox_3_pass': ft.TextField(label='Password 3', password=True, can_reveal_password=True, value=initial.get('mailbox_3_pass', '')),
            'mailbox_4_user': ft.TextField(label='Email aziendale 4', value=initial.get('mailbox_4_user', '')),
            'mailbox_4_pass': ft.TextField(label='Password 4', password=True, can_reveal_password=True, value=initial.get('mailbox_4_pass', '')),
            'phpmailer_user': ft.TextField(label='Email PHPMailer form', value=initial.get('phpmailer_user', '')),
            'phpmailer_pass': ft.TextField(label='Password PHPMailer form', password=True, can_reveal_password=True, value=initial.get('phpmailer_pass', '')),
            'phpmailer_note': ft.TextField(label='Note PHPMailer', value=initial.get('phpmailer_note', '')),
        }
        for field in fields.values():
            if isinstance(field, ft.TextField):
                _style_text_field(field)
            elif isinstance(field, ft.Dropdown):
                _style_dropdown(field)
        client_search = _style_text_field(ft.TextField(label='Cerca cliente', hint_text='Cerca cliente esistente...', height=56))
        client_dropdown = _style_dropdown(ft.Dropdown(label='Cliente (seleziona)', options=[], expand=True, height=56))
        validation_text = ft.Text('', color=ft.Colors.RED_700, visible=False)
        date_picker = ft.DatePicker(
            first_date=datetime(2000, 1, 1),
            last_date=datetime(2100, 12, 31),
        )

        def set_expiry_date(new_date: date) -> None:
            fields['expiry_date'].value = new_date.strftime('%Y-%m-%d')
            self.page.update()

        def on_date_change(e: ft.ControlEvent) -> None:
            selected = e.control.value
            if selected is None:
                return
            if isinstance(selected, datetime):
                set_expiry_date(selected.date())
                return
            if isinstance(selected, date):
                set_expiry_date(selected)

        def open_date_picker(_: ft.ControlEvent) -> None:
            date_picker.open = True
            self.page.update()

        date_picker.on_change = on_date_change
        self.page.overlay.append(date_picker)
        initial_expiry = (fields['expiry_date'].value or '').strip()
        if initial_expiry:
            parsed_expiry = _parse_iso_date(initial_expiry)
            if parsed_expiry:
                date_picker.value = datetime(parsed_expiry.year, parsed_expiry.month, parsed_expiry.day)

        expiry_row = ft.Row(
            tight=True,
            controls=[
                ft.Container(expand=True, content=fields['expiry_date']),
                ft.IconButton(
                    icon=ft.Icons.CALENDAR_MONTH,
                    icon_color=ft.Colors.WHITE,
                    tooltip='Seleziona data scadenza',
                    disabled=read_only,
                    on_click=open_date_picker,
                ),
            ],
        )

        def load_client_options(query: str = '') -> None:
            choices = self.client_repo.list_client_choices(query=query, limit=10)
            options = [ft.dropdown.Option('')]
            for c in choices:
                company = (c.get('company') or '').strip()
                company_label = f" | {company}" if company else ""
                label = f"{c['name']}{company_label}  (mod. {c['updated_at']})"
                options.append(ft.dropdown.Option(key=c['name'], text=label))
            current = initial.get('client_name', '')
            if current and all((o.key or '') != current for o in options if hasattr(o, 'key')):
                options.append(ft.dropdown.Option(key=current, text=current))
            client_dropdown.options = options
            if initial.get('client_name'):
                client_dropdown.value = initial.get('client_name')
            try:
                self.page.update()
            except Exception:
                pass

        client_search.on_change = lambda e: load_client_options((e.control.value or '').strip())
        load_client_options()

        if read_only:
            for c in fields.values():
                c.disabled = True
            client_search.disabled = True
            client_dropdown.disabled = True
        elif not can_view_sensitive:
            for key in [
                'hosting_username',
                'hosting_password',
                'ftp_username',
                'ftp_password',
                'mailbox_1_user',
                'mailbox_1_pass',
                'mailbox_2_user',
                'mailbox_2_pass',
                'mailbox_3_user',
                'mailbox_3_pass',
                'mailbox_4_user',
                'mailbox_4_pass',
                'phpmailer_user',
                'phpmailer_pass',
            ]:
                fields[key].value = ''
                fields[key].disabled = True
                fields[key].hint_text = 'Non visibile per il tuo ruolo'

        def copy_value(key: str):
            value = fields[key].value or ''
            if value:
                self.clipboard.copy_temporarily(self.page, value, 20)
                self.notify('Copiato negli appunti (20s)')

        credential_controls: list[ft.Control] = []
        if can_view_sensitive:
            credential_controls = [
                ft.OutlinedButton('Copia hosting user', on_click=lambda _: copy_value('hosting_username')),
                ft.OutlinedButton('Copia hosting password', on_click=lambda _: copy_value('hosting_password')),
                ft.OutlinedButton('Copia FTP user', on_click=lambda _: copy_value('ftp_username')),
                ft.OutlinedButton('Copia FTP password', on_click=lambda _: copy_value('ftp_password')),
            ]
        credential_tools = ft.Row(controls=credential_controls)

        content = ft.Container(
            width=880,
            height=620,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Text('Dati generali', weight=ft.FontWeight.BOLD),
                    validation_text,
                    ft.ResponsiveRow(
                        [
                            ft.Container(col=4, content=client_search),
                            ft.Container(col=8, content=client_dropdown),
                        ]
                    ),
                    ft.ResponsiveRow(
                        [
                            ft.Container(col=4, content=fields['domain']),
                            ft.Container(col=4, content=fields['provider']),
                            ft.Container(col=4, content=expiry_row),
                        ]
                    ),
                    ft.Divider(),
                    ft.Text('Hosting', weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow([ft.Container(col=12, content=fields['hosting_panel'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['hosting_username']), ft.Container(col=6, content=fields['hosting_password'])]),
                    ft.Divider(),
                    ft.Text('FTP/SFTP', weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow([ft.Container(col=4, content=fields['ftp_protocol']), ft.Container(col=4, content=fields['ftp_host']), ft.Container(col=4, content=fields['ftp_port'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['ftp_username']), ft.Container(col=6, content=fields['ftp_password'])]),
                    ft.Divider(),
                    ft.Text('Email aziendali', weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['mailbox_1_user']), ft.Container(col=6, content=fields['mailbox_1_pass'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['mailbox_2_user']), ft.Container(col=6, content=fields['mailbox_2_pass'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['mailbox_3_user']), ft.Container(col=6, content=fields['mailbox_3_pass'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['mailbox_4_user']), ft.Container(col=6, content=fields['mailbox_4_pass'])]),
                    ft.ResponsiveRow([ft.Container(col=6, content=fields['phpmailer_user']), ft.Container(col=6, content=fields['phpmailer_pass'])]),
                    ft.ResponsiveRow([ft.Container(col=12, content=fields['phpmailer_note'])]),
                    ft.Divider(),
                    ft.Text('Note', weight=ft.FontWeight.BOLD),
                    ft.ResponsiveRow([ft.Container(col=12, content=fields['notes'])]),
                    credential_tools,
                ],
            ),
        )

        def save(_):
            fields['domain'].error_text = None
            fields['ftp_port'].error_text = None
            fields['expiry_date'].error_text = None
            validation_text.visible = False
            validation_text.value = ''

            raw_domain = (fields['domain'].value or '').strip()
            domain = _normalize_domain(raw_domain)
            if not domain or not DOMAIN_RE.match(domain):
                fields['domain'].error_text = 'Dominio non valido'
                validation_text.value = 'Dominio non valido. Inserisci dominio o URL valido.'
                validation_text.visible = True
                self.notify('Errore validazione: dominio non valido')
                return
            if not (fields['ftp_port'].value or '').isdigit():
                fields['ftp_port'].error_text = 'Porta FTP non valida'
                validation_text.value = 'La porta FTP deve essere numerica.'
                validation_text.visible = True
                self.notify('Errore validazione: porta FTP non valida')
                return

            expiry_date = (fields['expiry_date'].value or '').strip()
            if expiry_date and (not DATE_RE.match(expiry_date) or _parse_iso_date(expiry_date) is None):
                fields['expiry_date'].error_text = 'Data non valida'
                validation_text.value = 'La data scadenza deve essere nel formato YYYY-MM-DD.'
                validation_text.visible = True
                self.notify('Errore validazione: data scadenza non valida')
                return

            payload = SitePayload(
                client_name=client_dropdown.value,
                domain=domain,
                provider=fields['provider'].value,
                tags=None,
                notes=fields['notes'].value,
                hosting_panel=fields['hosting_panel'].value,
                hosting_login_url=None,
                hosting_username=fields['hosting_username'].value,
                hosting_password=fields['hosting_password'].value,
                hosting_notes=None,
                ftp_protocol=fields['ftp_protocol'].value,
                ftp_host=fields['ftp_host'].value,
                ftp_port=int(fields['ftp_port'].value),
                ftp_username=fields['ftp_username'].value,
                ftp_password=fields['ftp_password'].value,
                ftp_root_path=None,
                ftp_notes=None,
                db_host=None,
                db_port=None,
                db_name=None,
                db_username=None,
                db_password=None,
                expiry_date=expiry_date or None,
            )
            email_data = {
                'mailbox_1_user': fields['mailbox_1_user'].value or '',
                'mailbox_1_pass': fields['mailbox_1_pass'].value or '',
                'mailbox_2_user': fields['mailbox_2_user'].value or '',
                'mailbox_2_pass': fields['mailbox_2_pass'].value or '',
                'mailbox_3_user': fields['mailbox_3_user'].value or '',
                'mailbox_3_pass': fields['mailbox_3_pass'].value or '',
                'mailbox_4_user': fields['mailbox_4_user'].value or '',
                'mailbox_4_pass': fields['mailbox_4_pass'].value or '',
                'phpmailer_user': fields['phpmailer_user'].value or '',
                'phpmailer_pass': fields['phpmailer_pass'].value or '',
                'phpmailer_note': fields['phpmailer_note'].value or '',
            }

            if site_id:
                self.repo.update_site(
                    site_id,
                    payload,
                    self.session_user.id,
                    self.session_user.data_key,
                    preserve_sensitive=not can_view_sensitive,
                    email_data=email_data,
                )
                self.notify('Sito aggiornato')
            else:
                self.repo.create_site(payload, self.session_user.id, self.session_user.data_key, email_data=email_data)
                self.notify('Sito creato')

            self._close_dialog()
            self._load_provider_options()
            self._reload_table()
            self.page.update()

        actions = [ft.TextButton('Chiudi', on_click=lambda _: self._close_dialog())]
        if not read_only:
            actions.append(ft.ElevatedButton('Salva', on_click=save))

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), modal=True, title=ft.Text('Sito' if site_id else 'Nuovo sito'), content=content, actions=actions)
        self.page.show_dialog(self._dialog)


def _normalize_domain(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ''
    if '://' in raw:
        parsed = urlparse(raw)
        host = parsed.netloc or parsed.path
    else:
        host = raw.split('/')[0]
    host = host.strip().lower()
    if ':' in host:
        host = host.split(':', 1)[0]
    return host


def _parse_iso_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def _days_left_label(days_left: int | None, expiry_date: str | None) -> str:
    if not expiry_date:
        return '-'
    if days_left is None:
        return expiry_date
    days = int(days_left)
    if days < 0:
        return f'Scaduto da {abs(days)} giorni'
    if days == 0:
        return 'Scade oggi'
    if days == 1:
        return '1 giorno'
    return f'{days} giorni'


def _expiry_badge(days_left: int | None) -> ft.Control:
    if days_left is None:
        return ft.Container(
            bgcolor=ui_theme.SURFACE_BG,
            border_radius=12,
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            content=ft.Text('N/D', size=12),
        )

    days = int(days_left)
    if days < 0:
        text = 'Scaduto'
        color = ft.Colors.RED_300
    elif days > 30:
        text = 'Attivo'
        color = ft.Colors.GREEN_300
    else:
        text = 'In scadenza'
        color = ft.Colors.ORANGE_300

    return ft.Container(
        bgcolor=color,
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=8, vertical=4),
        content=ft.Text(text, size=12),
    )




