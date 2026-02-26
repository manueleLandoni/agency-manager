from __future__ import annotations

import math
import webbrowser
from typing import Callable
from urllib.parse import quote_plus

import flet as ft

from app.ui import theme as ui_theme
from core.company_scraper import CompanyScraperService
from core.italy_geo import list_provinces_for_region, list_regions_north_to_south
from core.settings import SettingsService
from db.repository import CompanySearchRepository


class CompanySearchView:
    def __init__(self, page: ft.Page, session_user, notify: Callable[[str], None]) -> None:
        self.page = page
        self.user = session_user
        self.notify = notify
        self.repo = CompanySearchRepository()
        self.scraper = CompanyScraperService()
        self.settings = SettingsService()
        self.current_query = ''
        self.current_page = 1
        self.page_size = self._normalize_page_size(
            self.settings.get_int_value('company_search_page_size', default=20, min_value=10, max_value=100)
        )
        self.total_items = 0

        regions = list_regions_north_to_south()
        default_region = 'Lombardia' if 'Lombardia' in regions else (regions[0] if regions else '')
        default_provinces = list_provinces_for_region(default_region)
        default_province = 'Milano' if 'Milano' in default_provinces else (default_provinces[0] if default_provinces else '')

        self.search_field = ft.TextField(
            label='Ricerca *',
            hint_text='es. ristorante, parrucchiere',
            expand=True,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            hint_style=ft.TextStyle(color=ft.Colors.WHITE54),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.region_field = ft.Dropdown(
            label='Regione',
            value=default_region,
            options=[ft.dropdown.Option(r) for r in regions],
            width=220,
            on_select=self._on_region_change,
            color=ft.Colors.WHITE,
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.province_field = ft.Dropdown(
            label='Provincia',
            value=default_province,
            options=[ft.dropdown.Option(p) for p in default_provinces],
            width=240,
            color=ft.Colors.WHITE,
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.city_field = ft.TextField(
            label='Citta (opzionale)',
            width=230,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            hint_style=ft.TextStyle(color=ft.Colors.WHITE54),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.municipality_field = ft.TextField(
            label='Comune (opzionale)',
            width=230,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            hint_style=ft.TextStyle(color=ft.Colors.WHITE54),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.max_results_field = ft.TextField(
            label='Max risultati',
            value='50',
            width=130,
            color=ft.Colors.WHITE,
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            hint_style=ft.TextStyle(color=ft.Colors.WHITE54),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.page_size_selector = ft.Dropdown(
            label='Righe pagina',
            value=str(self.page_size),
            width=140,
            options=[
                ft.dropdown.Option('10'),
                ft.dropdown.Option('20'),
                ft.dropdown.Option('50'),
                ft.dropdown.Option('100'),
            ],
            on_select=self._on_page_size_change,
            color=ft.Colors.WHITE,
            text_style=ft.TextStyle(color=ft.Colors.WHITE),
            label_style=ft.TextStyle(color=ft.Colors.WHITE70),
            border_color=ui_theme.BORDER,
            focused_border_color=ft.Colors.WHITE70,
        )
        self.page_label = ft.Text('Pag. 1/1', color=ft.Colors.WHITE)
        self._dialog: ft.AlertDialog | None = None

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text('Azienda', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Numero', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Indirizzo', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Distanza', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Localita', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Fonte', color=ft.Colors.WHITE)),
                ft.DataColumn(ft.Text('Azioni', color=ft.Colors.WHITE)),
            ],
            rows=[],
            heading_row_color=ui_theme.TABLE_HEADER_BG,
            expand=True,
        )
        self._load_province_options()

    def build(self) -> ft.Control:
        self._reload_table()
        return ft.Column(
            expand=True,
            controls=[
                ft.Container(
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=8,
                    padding=12,
                    content=ft.Column(
                        controls=[
                            ft.Text('Ricerca aziende tramite web scraping', weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Row(
                                controls=[
                                    self.search_field,
                                    self.region_field,
                                    self.province_field,
                                ]
                            ),
                            ft.Row(
                                controls=[
                                    self.city_field,
                                    self.municipality_field,
                                    self.max_results_field,
                                    self.page_size_selector,
                                    ft.OutlinedButton(
                                        'Cerca e salva',
                                        icon=ft.Icons.SEARCH,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, icon_color=ft.Colors.WHITE),
                                        on_click=self._run_search,
                                    ),
                                    ft.OutlinedButton(
                                        'Cancella tutto',
                                        icon=ft.Icons.DELETE_SWEEP,
                                        style=ft.ButtonStyle(color=ft.Colors.WHITE, icon_color=ft.Colors.WHITE),
                                        on_click=self._confirm_clear_all,
                                    ),
                                ]
                            ),
                        ]
                    ),
                ),
                ft.Container(
                    expand=True,
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=8,
                    padding=8,
                    content=ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[self.table]),
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
        self._reload_table()
        self.page.update()

    def _run_search(self, _) -> None:
        search_term = (self.search_field.value or '').strip()

        max_results_raw = (self.max_results_field.value or '50').strip()
        if not max_results_raw.isdigit():
            self.notify('max_results deve essere un intero')
            return

        max_results = min(max(1, int(max_results_raw)), 200)
        region = (self.region_field.value or '').strip()
        province = (self.province_field.value or '').strip()
        if not region:
            self.notify('Seleziona una regione')
            return
        if not province:
            self.notify('Seleziona una provincia')
            return

        city = (self.city_field.value or '').strip()
        municipality = (self.municipality_field.value or '').strip()

        try:
            scraped = self.scraper.search(
                search_term=search_term,
                region=region,
                province=province,
                city=city,
                municipality=municipality,
                max_results=max_results,
            )
        except Exception as exc:
            self.notify(f'Errore scraping: {exc}')
            return

        if not scraped:
            self.notify('Nessun risultato trovato')
            return

        try:
            saved = self.repo.save_many(scraped, self.user.id)
        except Exception as exc:
            self.notify(f'Errore salvataggio risultati: {exc}')
            return

        self.current_page = 1
        self._reload_table()
        if self.total_items == 0 and self.current_query:
            self.current_query = ''
            self._reload_table()
            self.notify('Risultati salvati: rimossa la ricerca globale che stava filtrando la tabella')

        self.page.update()
        self.notify(f'Ricerca completata: trovati {len(scraped)}, salvati/aggiornati {saved}, visibili {len(self.table.rows)}')

    def _reload_table(self) -> None:
        rows, total = self.repo.list_results(
            query=self.current_query,
            province='',
            page=self.current_page,
            page_size=self.page_size,
        )
        self.total_items = total
        self.table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(r.get('company') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(r.get('phone') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(r.get('address') or '-', color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(self._format_distance(r.get('distance_km')), color=ft.Colors.WHITE)),
                    ft.DataCell(ft.Text(self._location_text(r), color=ft.Colors.WHITE)),
                    ft.DataCell(self._source_cell(r.get('source_name') or '-', r.get('source_url') or '')),
                    ft.DataCell(
                        ft.Row(
                            spacing=0,
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.GPS_FIXED,
                                    icon_color=ft.Colors.WHITE,
                                    tooltip='Apri su Google Maps',
                                    on_click=self._maps_click_handler(self._maps_query_for_row(r)),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.SWAP_HORIZ,
                                    icon_color=ft.Colors.WHITE,
                                    tooltip='Sposta in Contatti',
                                    on_click=lambda _, rid=r['id']: self._confirm_move_to_contacts(rid),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.DELETE,
                                    icon_color=ft.Colors.WHITE,
                                    tooltip='Elimina risultato',
                                    on_click=lambda _, rid=r['id']: self._confirm_delete_one(rid),
                                ),
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

    def _location_text(self, row: dict) -> str:
        municipality = (row.get('municipality') or '').strip()
        city = (row.get('city') or '').strip()
        province = (row.get('province') or '').strip()
        region = (row.get('region') or '').strip()
        parts = [p for p in [municipality, city, province, region] if p]
        return ' | '.join(parts) if parts else '-'

    def _format_distance(self, distance_km) -> str:
        if distance_km is None:
            return '-'
        try:
            value = float(distance_km)
        except (TypeError, ValueError):
            return '-'
        return f'{value:.1f} km'

    def _source_cell(self, source_name: str, source_url: str) -> ft.Control:
        if source_url.startswith('http'):
            def open_source(_: ft.ControlEvent) -> None:
                webbrowser.open_new_tab(source_url)

            return ft.TextButton(source_name, style=ft.ButtonStyle(color=ft.Colors.WHITE), on_click=open_source)
        return ft.Text(source_name, color=ft.Colors.WHITE)

    def _open_maps(self, address: str) -> None:
        query = (address or '').strip()
        if not query or query == '-':
            self.notify('Indirizzo non disponibile')
            return
        maps_url = f'https://www.google.com/maps/search/?api=1&query={quote_plus(query)}'
        webbrowser.open_new_tab(maps_url)

    def _maps_click_handler(self, query: str):
        def open_maps(_: ft.ControlEvent) -> None:
            self._open_maps(query)

        return open_maps

    def _maps_query_for_row(self, row: dict) -> str:
        parts = [
            (row.get('company') or '').strip(),
            (row.get('address') or '').strip(),
            (row.get('municipality') or '').strip(),
            (row.get('city') or '').strip(),
            (row.get('province') or '').strip(),
            (row.get('region') or '').strip(),
        ]
        clean_parts = [p for p in parts if p and p != '-']
        return ', '.join(clean_parts)

    def _on_region_change(self, _: ft.ControlEvent) -> None:
        self._load_province_options()
        self.page.update()

    def _load_province_options(self) -> None:
        selected_region = (self.region_field.value or '').strip()
        provinces = list_provinces_for_region(selected_region)
        self.province_field.options = [ft.dropdown.Option(p) for p in provinces]
        if self.province_field.value not in set(provinces):
            self.province_field.value = provinces[0] if provinces else ''
        self.province_field.disabled = len(provinces) == 0

    def _prev(self, _) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._reload_table()
            self.page.update()

    def _on_page_size_change(self, e: ft.ControlEvent) -> None:
        raw = (e.control.value or '20').strip()
        value = int(raw) if raw.isdigit() else 20
        self.page_size = self._normalize_page_size(value)
        self.page_size_selector.value = str(self.page_size)
        self.settings.set_value('company_search_page_size', str(self.page_size))
        self.current_page = 1
        self._reload_table()
        self.page.update()

    def _normalize_page_size(self, value: int) -> int:
        allowed = [10, 20, 50, 100]
        if value in allowed:
            return value
        if value < allowed[0]:
            return allowed[0]
        if value > allowed[-1]:
            return allowed[-1]
        return min(allowed, key=lambda candidate: abs(candidate - value))

    def _next(self, _) -> None:
        max_page = max(1, math.ceil(self.total_items / self.page_size))
        if self.current_page < max_page:
            self.current_page += 1
            self._reload_table()
            self.page.update()

    def _confirm_clear_all(self, _) -> None:
        def do_clear(_):
            deleted = self.repo.clear_all(self.user.id)
            self._close()
            self.current_page = 1
            self._reload_table()
            self.page.update()
            self.notify(f'Archivio risultati svuotato ({deleted} record)')

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text('Cancella tutto'),
            content=ft.Text('Confermi la cancellazione di tutti i risultati salvati?'),
            actions=[
                ft.TextButton('Annulla', on_click=lambda _: self._close()),
                ft.ElevatedButton('Cancella tutto', on_click=do_clear),
            ],
        )
        self.page.show_dialog(self._dialog)

    def _confirm_delete_one(self, result_id: int) -> None:
        def do_delete(_):
            self.repo.delete_result(result_id, self.user.id)
            self._close()
            self.current_page = 1
            self._reload_table()
            self.page.update()
            self.notify('Risultato eliminato')

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text('Elimina risultato'),
            content=ft.Text('Confermi l\'eliminazione di questo record?'),
            actions=[
                ft.TextButton('Annulla', on_click=lambda _: self._close()),
                ft.ElevatedButton('Elimina', on_click=do_delete),
            ],
        )
        self.page.show_dialog(self._dialog)

    def _confirm_move_to_contacts(self, result_id: int) -> None:
        def do_move(_):
            try:
                self.repo.move_to_contacts(result_id, self.user.id)
            except Exception as exc:
                self._close()
                self.notify(f'Errore spostamento: {exc}')
                return
            self._close()
            self.current_page = 1
            self._reload_table()
            self.page.update()
            self.notify('Record spostato in Contatti')

        self._dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text('Sposta in Contatti'),
            content=ft.Text('Confermi lo spostamento di questo record in Contatti?'),
            actions=[
                ft.TextButton('Annulla', on_click=lambda _: self._close()),
                ft.ElevatedButton('Sposta', on_click=do_move),
            ],
        )
        self.page.show_dialog(self._dialog)

    def _close(self) -> None:
        if self._dialog:
            self.page.pop_dialog()
            self._dialog = None
            self.page.update()
