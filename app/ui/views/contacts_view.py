from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable

import flet as ft

from app.ui import theme as ui_theme
from core.csv_tools import export_contacts_csv, import_contacts_csv_standard
from core.italy_geo import (
    is_valid_province_for_region,
    is_valid_region,
    list_provinces_for_region,
    list_regions_north_to_south,
)
from core.settings import SettingsService
from db.repository import ContactRepository

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
ALL_REGIONS_KEY = '__all_regions__'
ALL_PROVINCES_KEY = '__all__'
CLIENT_SORT_OPTIONS = {
    'name_asc',
    'name_desc',
    'type_asc',
    'type_desc',
    'company_asc',
    'company_desc',
    'email_asc',
    'email_desc',
    'region_asc',
    'region_desc',
    'province_asc',
    'province_desc',
    'sites_desc',
    'sites_asc',
    'updated_desc',
    'updated_asc',
}
SECTOR_OPTIONS = [
    'Agricoltura e allevamento',
    'Industria e manifattura',
    'Edilizia e immobiliare',
    'Commercio & distribuzione',
    'Trasporti e logistica',
    'Turismo e ristorazione',
    'Servizi alle imprese',
    'Servizi alla persona',
    'Finanza assicurazioni e professionisti',
    'Altro',
]
PROJECT_TYPE_OPTIONS = [
    'Sito web aziendale',
    'Sito web personale',
    'E-commerce e vendite online',
    'Landing page promozionale',
    'Blog e contenuti online',
    'Restyling sito web',
    'Manutenzione e assistenza siti web',
    'SEO e ottimizzazione visibilita',
    'Social media management',
    'Social media marketing',
    'Pubblicita online (Google e social)',
    'Branding e identita visiva',
    'Grafica digitale e materiali promozionali',
    'Software gestionale personalizzato',
    'Web app e applicazioni online',
    'CRM e gestione clienti',
    'Dashboard e pannelli di controllo',
    'Progetto digitale integrato',
    'Gestione digitale continuativa',
    'Soluzione digitale completa',
    'Multiprogetto',
]


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


class ContactsView:
    def __init__(self, page: ft.Page, session_user, notify: Callable[[str], None]) -> None:
        self.page = page
        self.user = session_user
        self.notify = notify
        self.repo = ContactRepository()
        self.settings = SettingsService()
        self.current_query = ''
        self.current_page = 1
        self.page_size = self.settings.get_int_value('contacts_page_size', default=10, min_value=5, max_value=50)
        self.current_region = self.settings.get_value('contacts_region_filter', ALL_REGIONS_KEY)
        self.current_province = self.settings.get_value('contacts_province_filter', ALL_PROVINCES_KEY)
        saved_sort = self.settings.get_value('contacts_sort', 'name_asc')
        self.current_sort = saved_sort if saved_sort in CLIENT_SORT_OPTIONS else 'name_asc'
        self.total_items = 0

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text('Nome', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Tipo', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Azienda', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Email', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Localita', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Siti', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Azioni', color=ft.Colors.WHITE)),
            ],
            rows=[],
            expand=True,
            heading_row_color=ui_theme.TABLE_HEADER_BG,
        )
        self.page_label = ft.Text('Pag. 1/1', color=ft.Colors.WHITE)
        self.region_filter = _style_dropdown(ft.Dropdown(label='Regione', options=[], width=240, on_select=self._on_region_change))
        self.province_filter = _style_dropdown(ft.Dropdown(label='Provincia', options=[], width=220, on_select=self._on_province_change))
        self.sort_selector = _style_dropdown(ft.Dropdown(
            label='Ordina per',
            width=260,
            value=self.current_sort,
            options=[
                ft.dropdown.Option('name_asc', 'Nome (A-Z)'),
                ft.dropdown.Option('name_desc', 'Nome (Z-A)'),
                ft.dropdown.Option('type_asc', 'Tipo (A-Z)'),
                ft.dropdown.Option('type_desc', 'Tipo (Z-A)'),
                ft.dropdown.Option('company_asc', 'Azienda (A-Z)'),
                ft.dropdown.Option('company_desc', 'Azienda (Z-A)'),
                ft.dropdown.Option('email_asc', 'Email (A-Z)'),
                ft.dropdown.Option('email_desc', 'Email (Z-A)'),
                ft.dropdown.Option('region_asc', 'Regione (A-Z)'),
                ft.dropdown.Option('region_desc', 'Regione (Z-A)'),
                ft.dropdown.Option('province_asc', 'Provincia (A-Z)'),
                ft.dropdown.Option('province_desc', 'Provincia (Z-A)'),
                ft.dropdown.Option('sites_desc', 'Siti (piu -> meno)'),
                ft.dropdown.Option('sites_asc', 'Siti (meno -> piu)'),
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
        self._load_region_options()
        self._load_province_options()
        self._reload()
        return ft.Column(
            expand=True,
            controls=[
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Row(controls=[self.region_filter, self.province_filter, self.sort_selector, self.page_size_selector]),
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
                                    ft.IconButton(icon=ft.Icons.ADD, icon_color=ft.Colors.WHITE, tooltip='Nuovo contatto', on_click=lambda _: self.open_dialog()),
                                    ft.IconButton(icon=ft.Icons.UPLOAD_FILE, icon_color=ft.Colors.WHITE, tooltip='Import CSV contatti', on_click=self._open_import_csv_dialog),
                                    ft.IconButton(icon=ft.Icons.DOWNLOAD, icon_color=ft.Colors.WHITE, tooltip='Export CSV contatti', on_click=self._open_export_csv_dialog),
                                ],
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.END,
                    controls=[
                        ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_color=ft.Colors.WHITE, on_click=self._prev),
                        self.page_label,
                        ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_color=ft.Colors.WHITE, on_click=self._next),
                    ],
                ),
            ],
        )

    def set_search(self, value: str) -> None:
        self.current_query = value.strip()
        self.current_page = 1
        self._reload()
        self.page.update()

    def _on_region_change(self, e: ft.ControlEvent) -> None:
        self.current_region = e.control.value or ALL_REGIONS_KEY
        self.settings.set_value('contacts_region_filter', self.current_region)
        self.current_province = ALL_PROVINCES_KEY
        self.settings.set_value('contacts_province_filter', self.current_province)
        self._load_province_options()
        self.current_page = 1
        self._reload()
        self.page.update()

    def _on_province_change(self, e: ft.ControlEvent) -> None:
        self.current_province = e.control.value or ALL_PROVINCES_KEY
        self.settings.set_value('contacts_province_filter', self.current_province)
        self.current_page = 1
        self._reload()
        self.page.update()

    def _on_sort_change(self, e: ft.ControlEvent) -> None:
        self.current_sort = e.control.value or 'name_asc'
        self.settings.set_value('contacts_sort', self.current_sort)
        self.current_page = 1
        self._reload()
        self.page.update()

    def _on_page_size_change(self, e: ft.ControlEvent) -> None:
        raw = e.control.value or '10'
        self.page_size = self._normalize_page_size(int(raw) if raw.isdigit() else 10)
        self.settings.set_value('contacts_page_size', str(self.page_size))
        self.current_page = 1
        self._reload()
        self.page.update()

    def _load_region_options(self) -> None:
        regions = list_regions_north_to_south()
        self.region_filter.options = [ft.dropdown.Option(ALL_REGIONS_KEY, 'Tutte le regioni')] + [ft.dropdown.Option(r) for r in regions]
        allowed = {ALL_REGIONS_KEY, *regions}
        if self.current_region not in allowed:
            self.current_region = ALL_REGIONS_KEY
            self.settings.set_value('contacts_region_filter', self.current_region)
        self.region_filter.value = self.current_region

    def _load_province_options(self) -> None:
        if self.current_region == ALL_REGIONS_KEY:
            provinces: list[str] = []
            self.province_filter.disabled = True
        else:
            provinces = list_provinces_for_region(self.current_region)
            self.province_filter.disabled = False
        self.province_filter.options = [ft.dropdown.Option(ALL_PROVINCES_KEY, 'Tutte le province')] + [ft.dropdown.Option(p) for p in provinces]
        province_keys = {ALL_PROVINCES_KEY, *provinces}
        if self.current_province not in province_keys:
            self.current_province = ALL_PROVINCES_KEY
            self.settings.set_value('contacts_province_filter', self.current_province)
        self.province_filter.value = self.current_province

    def _reload(self) -> None:
        region_value = '' if self.current_region == ALL_REGIONS_KEY else self.current_region
        province_value = '' if self.current_province == ALL_PROVINCES_KEY else self.current_province
        rows, total = self.repo.list_contacts(
            query=self.current_query,
            region=region_value,
            province=province_value,
            page=self.current_page,
            page_size=self.page_size,
            sort_key=self.current_sort,
        )
        self.total_items = total
        self.table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(r['name'], color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(r.get('client_type') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(r.get('company') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(r.get('email') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(self._location_text(r), color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(str(r.get('sites_count', 0)), color=ft.Colors.WHITE)),
                    ft.DataCell(
                        ft.Row(
                            spacing=0,
                            controls=[
                                ft.IconButton(icon=ft.Icons.VISIBILITY, icon_color=ft.Colors.WHITE, on_click=lambda _, cid=r['id']: self.open_dialog(cid, True)),
                                ft.IconButton(icon=ft.Icons.EDIT, icon_color=ft.Colors.WHITE, on_click=lambda _, cid=r['id']: self.open_dialog(cid, False)),
                                ft.IconButton(icon=ft.Icons.SWAP_HORIZ, icon_color=ft.Colors.WHITE, tooltip='Sposta in Clienti', on_click=lambda _, cid=r['id']: self._confirm_move_to_clients(cid)),
                                ft.IconButton(icon=ft.Icons.DELETE, icon_color=ft.Colors.WHITE, on_click=lambda _, cid=r['id']: self._confirm_delete(cid)),
                            ],
                        )
                    ),
                ]
            )
            for r in rows
        ]
        max_page = max(1, math.ceil(total / self.page_size))
        if self.current_page > max_page:
            self.current_page = max_page
        self.page_label.value = f'Pag. {self.current_page}/{max_page} - {total} record'

    def _normalize_page_size(self, value: int) -> int:
        if value < 5:
            return 5
        if value > 50:
            return 50
        return max(5, min(50, int(round(value / 5) * 5)))

    def _location_text(self, row: dict) -> str:
        city = (row.get('city') or '').strip()
        municipality = (row.get('municipality') or '').strip()
        province = (row.get('province') or '').strip()
        region = (row.get('region') or '').strip()
        address = (row.get('address') or '').strip()
        parts = [p for p in [address, municipality, province, city, region] if p]
        return ' | '.join(parts) if parts else '-'

    def _prev(self, _):
        if self.current_page > 1:
            self.current_page -= 1
            self._reload()
            self.page.update()

    def _next(self, _):
        max_page = max(1, math.ceil(self.total_items / self.page_size))
        if self.current_page < max_page:
            self.current_page += 1
            self._reload()
            self.page.update()

    def _confirm_delete(self, contact_id: int) -> None:
        def do_delete(_):
            self.repo.delete_contact(contact_id, self.user.id)
            self._close()
            self._reload()
            self.page.update()
            self.notify('Contatto eliminato')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Elimina Contatto'),
            content=ft.Text('Confermi eliminazione Contatto?'),
            actions=[ft.TextButton('Annulla', on_click=lambda _: self._close()), ft.ElevatedButton('Elimina', on_click=do_delete)],
        )
        self.page.show_dialog(self._dialog)

    def _confirm_move_to_clients(self, contact_id: int) -> None:
        def do_move(_):
            try:
                self.repo.move_to_clients(contact_id, self.user.id)
            except ValueError as exc:
                self._close()
                self.notify(str(exc))
                return
            self._close()
            self._reload()
            self.page.update()
            self.notify('Contatto spostato in Clienti')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Sposta in Clienti'),
            content=ft.Text('Confermi lo spostamento del Contatto nella sezione Clienti?'),
            actions=[ft.TextButton('Annulla', on_click=lambda _: self._close()), ft.ElevatedButton('Sposta', on_click=do_move)],
        )
        self.page.show_dialog(self._dialog)

    def _close(self):
        if self._dialog:
            self.page.pop_dialog()
            self._dialog = None
            self.page.update()

    def _open_export_csv_dialog(self, _):
        path_field = _style_text_field(ft.TextField(label='Percorso file CSV export', value='exports/contacts_export.csv', width=560))

        def do_export(_):
            target = Path((path_field.value or '').strip())
            if not str(target):
                self.notify('Percorso file non valido')
                return
            count = export_contacts_csv(target)
            self._close()
            self.notify(f'Export contatti completato: {count} record in {target}')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Export CSV contatti'),
            content=ft.Container(width=700, content=ft.Column(tight=True, controls=[path_field])),
            actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close()), ft.ElevatedButton('Esporta', on_click=do_export)],
        )
        self.page.show_dialog(self._dialog)

    def _open_import_csv_dialog(self, _):
        path_field = _style_text_field(ft.TextField(label='Percorso file CSV import', value='exports/contacts_export.csv', width=560))

        def do_import(_):
            source = Path((path_field.value or '').strip())
            if not source.exists():
                self.notify('File CSV non trovato')
                return
            count = import_contacts_csv_standard(source, self.user.id)
            self._close()
            self._load_region_options()
            self._load_province_options()
            self._reload()
            self.page.update()
            self.notify(f'Import contatti completato: {count} record')

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Import CSV contatti'),
            content=ft.Container(width=700, content=ft.Column(tight=True, controls=[path_field])),
            actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close()), ft.ElevatedButton('Importa', on_click=do_import)],
        )
        self.page.show_dialog(self._dialog)

    def open_dialog(self, contact_id: int | None = None, read_only: bool = False) -> None:
        initial = self.repo.get_contact(contact_id) if contact_id else {}
        initial_region_raw = (initial or {}).get('region', '')
        selected_region = initial_region_raw if is_valid_region(initial_region_raw) else 'Lombardia'
        region_options = [ft.dropdown.Option(r) for r in list_regions_north_to_south()]
        province_values = list_provinces_for_region(selected_region)
        initial_province_raw = (initial or {}).get('province', '')
        if initial_province_raw and is_valid_province_for_region(selected_region, initial_province_raw):
            selected_province = initial_province_raw
        elif selected_region == 'Lombardia' and 'Milano' in province_values:
            selected_province = 'Milano'
        else:
            selected_province = province_values[0] if province_values else ''
        province_options = [ft.dropdown.Option(p) for p in province_values]

        fields = {
            'name': ft.TextField(label='Nome *', value=(initial or {}).get('name', '')),
            'client_type': ft.Dropdown(
                label='Tipo cliente *',
                options=[
                    ft.dropdown.Option('Privato'),
                    ft.dropdown.Option('Azienda'),
                    ft.dropdown.Option('Professionista'),
                ],
                value=(initial or {}).get('client_type') or 'Privato',
                expand=True,
            ),
            'company': ft.TextField(label='Azienda', value=(initial or {}).get('company', '')),
            'contact_role': ft.TextField(label='Ruolo contatto', value=(initial or {}).get('contact_role', '')),
            'sector': ft.Dropdown(
                label='Settore',
                options=[ft.dropdown.Option(s) for s in SECTOR_OPTIONS],
                value=(initial or {}).get('sector') or 'Commercio & distribuzione',
                expand=True,
            ),
            'project_type': ft.Dropdown(
                label='Tipo progetto',
                options=[ft.dropdown.Option(p) for p in PROJECT_TYPE_OPTIONS],
                value=(initial or {}).get('project_type') or 'Sito web aziendale',
                expand=True,
            ),
            'email': ft.TextField(label='Email', value=(initial or {}).get('email', '')),
            'phone': ft.TextField(label='Telefono', value=(initial or {}).get('phone', '')),
            'landline_phone': ft.TextField(label='Telefono fisso', value=(initial or {}).get('landline_phone', '')),
            'city': ft.TextField(label='Citta', value=(initial or {}).get('city', '')),
            'municipality': ft.TextField(label='Comune', value=(initial or {}).get('municipality', '')),
            'region': ft.Dropdown(label='Regione', options=region_options, value=selected_region, expand=True),
            'province': ft.Dropdown(label='Provincia', options=province_options, value=selected_province, expand=True),
            'address': ft.TextField(label='Indirizzo', value=(initial or {}).get('address', '')),
            'fiscal_code': ft.TextField(label='Codice Fiscale', value=(initial or {}).get('fiscal_code', '')),
            'vat_number': ft.TextField(label='Partita IVA', value=(initial or {}).get('vat_number', '')),
            'notes': ft.TextField(
                label='Note',
                multiline=True,
                min_lines=5,
                max_lines=8,
                width=900,
                value=(initial or {}).get('notes', ''),
            ),
        }
        for field in fields.values():
            if isinstance(field, ft.TextField):
                _style_text_field(field)
            elif isinstance(field, ft.Dropdown):
                _style_dropdown(field)
        validation_text = ft.Text('', color=ft.Colors.RED_700, visible=False)

        def reload_provinces_for_dialog() -> None:
            selected_region = fields['region'].value or ''
            if selected_region and is_valid_region(selected_region):
                provinces = list_provinces_for_region(selected_region)
                options = [ft.dropdown.Option(p) for p in provinces]
                fields['province'].disabled = False
                if not fields['province'].value or fields['province'].value not in {o.key for o in options if o.key is not None}:
                    if selected_region == 'Lombardia' and 'Milano' in provinces:
                        fields['province'].value = 'Milano'
                    elif provinces:
                        fields['province'].value = provinces[0]
            else:
                fields['province'].disabled = True
                fields['province'].value = ''
                options = []
            fields['province'].options = options
            try:
                self.page.update()
            except Exception:
                pass

        fields['region'].on_select = lambda _: reload_provinces_for_dialog()
        reload_provinces_for_dialog()

        if read_only:
            for f in fields.values():
                f.disabled = True

        def save(_):
            fields['name'].error_text = None
            fields['email'].error_text = None
            fields['client_type'].error_text = None
            fields['region'].error_text = None
            fields['province'].error_text = None
            validation_text.visible = False
            validation_text.value = ''
            if not (fields['name'].value or '').strip():
                fields['name'].error_text = 'Nome obbligatorio'
                validation_text.value = 'Compila il campo nome.'
                validation_text.visible = True
                self.notify('Errore validazione: nome obbligatorio')
                self.page.update()
                return
            if not (fields['client_type'].value or '').strip():
                fields['client_type'].error_text = 'Seleziona il Tipo cliente'
                validation_text.value = 'Tipo cliente obbligatorio.'
                validation_text.visible = True
                self.notify('Errore validazione: Tipo cliente obbligatorio')
                self.page.update()
                return
            email = (fields['email'].value or '').strip()
            if email and not EMAIL_RE.match(email):
                fields['email'].error_text = 'Email non valida (es. nome@dominio.it)'
                validation_text.value = 'Email non valida (usa formato nome@dominio.it).'
                validation_text.visible = True
                self.notify('Errore validazione: email non valida')
                self.page.update()
                return
            region_value = (fields['region'].value or '').strip()
            province_value = (fields['province'].value or '').strip()
            if region_value and not is_valid_region(region_value):
                fields['region'].error_text = 'Regione non valida'
                validation_text.value = 'Seleziona una regione valida.'
                validation_text.visible = True
                self.notify('Errore validazione: regione non valida')
                self.page.update()
                return
            if region_value and not province_value:
                fields['province'].error_text = 'Provincia obbligatoria'
                validation_text.value = 'Se selezioni una regione, seleziona anche la provincia.'
                validation_text.visible = True
                self.notify('Errore validazione: provincia obbligatoria')
                self.page.update()
                return
            if province_value and not region_value:
                fields['region'].error_text = 'Regione obbligatoria'
                validation_text.value = 'Per la provincia selezionata devi indicare la regione.'
                validation_text.visible = True
                self.notify('Errore validazione: regione obbligatoria')
                self.page.update()
                return
            if region_value and province_value and not is_valid_province_for_region(region_value, province_value):
                fields['province'].error_text = 'Provincia non coerente'
                validation_text.value = 'La provincia non appartiene alla regione selezionata.'
                validation_text.visible = True
                self.notify('Errore validazione: provincia/regione non coerenti')
                self.page.update()
                return
            payload = {}
            for k, v in fields.items():
                payload[k] = v.value if hasattr(v, 'value') else None
            if contact_id:
                self.repo.update_contact(contact_id, payload, self.user.id)
                self.notify('Contatto aggiornato')
            else:
                self.repo.create_contact(payload, self.user.id)
                self.notify('Contatto creato')
            self._close()
            self._reload()
            self.page.update()

        actions = [ft.TextButton('Chiudi', on_click=lambda _: self._close())]
        if not read_only:
            actions.append(ft.ElevatedButton('Salva', on_click=save))

        grid = ft.Column(
            tight=True,
            spacing=10,
            controls=[
                ft.Row([ft.Container(expand=True, content=fields['name']), ft.Container(expand=True, content=fields['client_type'])]),
                ft.Row([ft.Container(expand=True, content=fields['company']), ft.Container(expand=True, content=fields['contact_role'])]),
                ft.Row([ft.Container(expand=True, content=fields['sector']), ft.Container(expand=True, content=fields['project_type'])]),
                ft.Row([ft.Container(expand=True, content=fields['email']), ft.Container(expand=True, content=fields['phone'])]),
                ft.Row([ft.Container(expand=True, content=fields['landline_phone']), ft.Container(expand=True, content=fields['fiscal_code'])]),
                ft.Row([ft.Container(expand=True, content=fields['region']), ft.Container(expand=True, content=fields['province'])]),
                ft.Row([ft.Container(expand=True, content=fields['city']), ft.Container(expand=True, content=fields['municipality'])]),
                ft.Row([ft.Container(expand=True, content=fields['address']), ft.Container(expand=True, content=fields['vat_number'])]),
            ],
        )

        self._dialog = ft.AlertDialog(bgcolor=ui_theme.CARD_BG, barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK), title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600), content_text_style=ft.TextStyle(color=ft.Colors.WHITE), 
            modal=True,
            title=ft.Text('Contatto' if contact_id else 'Nuovo contatto'),
            content=ft.Container(
                width=900,
                content=ft.Column(
                    tight=True,
                    controls=[
                        validation_text,
                        grid,
                        fields['notes'],
                    ],
                ),
            ),
            actions=actions,
        )
        self.page.show_dialog(self._dialog)






