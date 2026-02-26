from __future__ import annotations

import asyncio
from datetime import date
import os
from pathlib import Path

import flet as ft

from app.ui.components.layout import app_shell
from app.ui import theme as ui_theme
from app.ui.views.appointments_view import AppointmentsView
from app.ui.views.company_search_view import CompanySearchView
from app.ui.views.clients_view import ClientsView
from app.ui.views.contacts_view import ContactsView
from app.ui.views.dashboard_view import dashboard_view
from app.ui.views.login_view import login_view
from app.ui.views.sites_view import SitesView
from core.auth import (
    AuthService,
    SessionUser,
    clear_remember_token_file,
    load_remember_token,
    save_remember_token,
)
from core.backup import auto_backup, export_encrypted_backup, import_encrypted_backup
from core.inactivity import InactivityTracker
from core.settings import SettingsService
from db.connection import get_connection
from db.migration import run_migrations
from db.repository import AuditRepository


class AppController:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._install_session_safe_guards()
        self.auth = AuthService()
        self.settings = SettingsService()
        self.audit_repo = AuditRepository()
        self.user: SessionUser | None = None
        self.remember_token: str | None = None
        self.global_search = ''
        self.sites_view: SitesView | None = None
        self.clients_view: ClientsView | None = None
        self.contacts_view: ContactsView | None = None
        self.appointments_view: AppointmentsView | None = None
        self.company_search_view: CompanySearchView | None = None
        self.file_picker: ft.FilePicker | None = None
        # Use safe default at bootstrap; DB migrations run in start().
        self.tracker = InactivityTracker(minutes=10)
        self.is_locked = False
        self._dialog: ft.AlertDialog | None = None

        self.page.title = 'Agency Manager'
        self.page.theme_mode = ft.ThemeMode.DARK
        app_theme = ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=ui_theme.ACCENT,
                secondary=ui_theme.ACCENT,
                on_primary=ft.Colors.WHITE,
                surface=ui_theme.BG,
                on_surface=ft.Colors.WHITE,
                on_surface_variant=ft.Colors.WHITE,
                outline=ui_theme.BORDER,
            ),
            dropdown_theme=ft.DropdownTheme(
                text_style=ft.TextStyle(color=ft.Colors.WHITE),
            ),
            text_theme=ft.TextTheme(
                body_large=ft.TextStyle(color=ft.Colors.WHITE),
                body_medium=ft.TextStyle(color=ft.Colors.WHITE),
                body_small=ft.TextStyle(color=ft.Colors.WHITE),
                title_large=ft.TextStyle(color=ft.Colors.WHITE),
                title_medium=ft.TextStyle(color=ft.Colors.WHITE),
                title_small=ft.TextStyle(color=ft.Colors.WHITE),
                label_large=ft.TextStyle(color=ft.Colors.WHITE),
                label_medium=ft.TextStyle(color=ft.Colors.WHITE),
                label_small=ft.TextStyle(color=ft.Colors.WHITE),
                headline_large=ft.TextStyle(color=ft.Colors.WHITE),
                headline_medium=ft.TextStyle(color=ft.Colors.WHITE),
                headline_small=ft.TextStyle(color=ft.Colors.WHITE),
                display_large=ft.TextStyle(color=ft.Colors.WHITE),
                display_medium=ft.TextStyle(color=ft.Colors.WHITE),
                display_small=ft.TextStyle(color=ft.Colors.WHITE),
            ),
            icon_theme=ft.IconTheme(color=ft.Colors.WHITE),
            data_table_theme=ft.DataTableTheme(
                data_text_style=ft.TextStyle(color=ft.Colors.WHITE),
                heading_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                heading_row_color={ft.ControlState.DEFAULT: ui_theme.TABLE_HEADER_BG},
                data_row_color={ft.ControlState.DEFAULT: ui_theme.BG},
            ),
            dialog_theme=ft.DialogTheme(
                bgcolor=ui_theme.CARD_BG,
                shadow_color=ft.Colors.BLACK54,
                barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
                title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
            ),
            snackbar_theme=ft.SnackBarTheme(
                bgcolor=ui_theme.CARD_BG,
                content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
                action_text_color=ft.Colors.WHITE,
                close_icon_color=ft.Colors.WHITE,
                behavior=ft.SnackBarBehavior.FLOATING,
            ),
            outlined_button_theme=ft.OutlinedButtonTheme(
                style=ft.ButtonStyle(
                    color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                    icon_color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                    side={ft.ControlState.DEFAULT: ft.BorderSide(1, ui_theme.BORDER)},
                )
            ),
            text_button_theme=ft.TextButtonTheme(
                style=ft.ButtonStyle(
                    color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                    icon_color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                )
            ),
            icon_button_theme=ft.IconButtonTheme(
                style=ft.ButtonStyle(
                    icon_color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                )
            ),
            filled_button_theme=ft.FilledButtonTheme(
                style=ft.ButtonStyle(
                    color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                    bgcolor={ft.ControlState.DEFAULT: ui_theme.SURFACE_BG},
                )
            ),
            button_theme=ft.ButtonTheme(
                style=ft.ButtonStyle(
                    color={ft.ControlState.DEFAULT: ft.Colors.WHITE},
                )
            ),
            scaffold_bgcolor=ui_theme.BG,
            card_bgcolor=ui_theme.CARD_BG,
            divider_color=ui_theme.BORDER,
            hint_color=ft.Colors.with_opacity(0.75, ft.Colors.WHITE),
            unselected_control_color=ft.Colors.WHITE70,
            disabled_color=ft.Colors.WHITE54,
        )
        self.page.theme = app_theme
        self.page.dark_theme = app_theme
        self.page.bgcolor = ui_theme.BG
        self.page.padding = 0
        self.page.window.icon = str(Path('assets/favicon.ico').resolve())
        self.page.window.bgcolor = ui_theme.BG
        self.page.window.title_bar_hidden = True
        self.page.window.title_bar_buttons_hidden = True
        self.page.window.frameless = True
        self.page.window.shadow = False
        self.page.window_width = 1400
        self.page.window_height = 900
        self.page.window_min_width = 1024
        self.page.window_min_height = 700

        self.page.on_route_change = self._on_route_change
        self.page.on_keyboard_event = lambda _: self._touch()

    def _is_session_closed_error(self, exc: Exception) -> bool:
        return isinstance(exc, RuntimeError) and 'Session closed' in str(exc)

    def _install_session_safe_guards(self) -> None:
        raw_update = self.page.update
        raw_show_dialog = self.page.show_dialog
        raw_pop_dialog = self.page.pop_dialog
        raw_clean = self.page.clean
        raw_add = self.page.add
        raw_go = self.page.go
        raw_launch_url = self.page.launch_url

        def safe_update(*args, **kwargs):
            try:
                return raw_update(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        def safe_show_dialog(*args, **kwargs):
            try:
                return raw_show_dialog(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        def safe_pop_dialog(*args, **kwargs):
            try:
                return raw_pop_dialog(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        def safe_clean(*args, **kwargs):
            try:
                return raw_clean(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        def safe_add(*args, **kwargs):
            try:
                return raw_add(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        def safe_go(*args, **kwargs):
            try:
                return raw_go(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        async def safe_launch_url(*args, **kwargs):
            try:
                return await raw_launch_url(*args, **kwargs)
            except Exception as exc:
                if self._is_session_closed_error(exc):
                    return None
                raise

        self.page.update = safe_update
        self.page.show_dialog = safe_show_dialog
        self.page.pop_dialog = safe_pop_dialog
        self.page.clean = safe_clean
        self.page.add = safe_add
        self.page.go = safe_go
        self.page.launch_url = safe_launch_url

    def start(self) -> None:
        run_migrations()
        self.tracker.reset(self.settings.get_inactivity_minutes())
        self.auth.ensure_default_admin()
        # Re-apply desktop window metadata on startup to avoid native fallback title/icon.
        self.page.title = 'Agency Manager'
        self.page.window.icon = str(Path('assets/favicon.ico').resolve())
        self._init_file_picker()
        auto_backup(rotation=10)
        self._try_auto_login()
        self.page.run_task(self._inactivity_loop)
        self.page.go('/dashboard' if self.user else '/login')

    def _init_file_picker(self) -> None:
        if self.file_picker is not None:
            return
        try:
            picker = ft.FilePicker()
            registered = False
            # Register service using public API when available.
            if hasattr(self.page, 'services'):
                current = list(self.page.services or [])
                if all(service is not picker for service in current):
                    current.append(picker)
                    self.page.services = current
                registered = True
            elif hasattr(self.page, '_services') and hasattr(self.page._services, 'register_service'):
                self.page._services.register_service(picker)
                registered = True
            # Fallback for older clients where FilePicker is still used as control in overlay.
            elif hasattr(self.page, 'overlay'):
                self.page.overlay.append(picker)
                registered = True
            self.file_picker = picker
            if registered:
                self.page.update()
        except Exception:
            self.file_picker = None

    async def _inactivity_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            if self.user and not self.is_locked and self.tracker.is_expired():
                self.is_locked = True
                self._show_lock_dialog()

    def _touch(self) -> None:
        self.tracker.touch()

    def _try_auto_login(self) -> None:
        token = load_remember_token()
        if not token:
            return
        user = self.auth.login_from_remember_token(token)
        if user:
            self.user = user
            self.remember_token = token
            self.tracker.reset(self.settings.get_inactivity_minutes())
        else:
            clear_remember_token_file()

    def _on_route_change(self, _: ft.RouteChangeEvent) -> None:
        try:
            if not self.user and self.page.route != '/login':
                self.page.go('/login')
                return

            if self.page.route == '/login':
                self.page.clean()
                self.page.add(login_view(self._handle_login))
                self.page.update()
                return

            self._touch()
            body = self._build_body(self.page.route)
            shell = app_shell(
                self.page,
                self._title(self.page.route),
                body,
                search_cb=self._on_search,
                nav_cb=self._on_nav,
                on_logout=self._logout,
                on_toggle_maximize=self._toggle_window_maximize,
                on_minimize_window=self._minimize_window,
                on_close_window=self._close_window,
            )
            self.page.clean()
            self.page.add(shell)
            self.page.update()
        except Exception as exc:
            self.page.clean()
            self.page.add(
                ft.Container(
                    expand=True,
                    alignment=ft.Alignment(0, 0),
                    content=ft.Text(f'Errore rendering: {exc}', color=ft.Colors.RED_700),
                )
            )
            self.page.update()

    def _on_search(self, value: str) -> None:
        self.global_search = value
        if self.sites_view and self.page.route == '/sites':
            self.sites_view.set_search(value)
        if self.clients_view and self.page.route == '/clients':
            self.clients_view.set_search(value)
        if self.contacts_view and self.page.route == '/contacts':
            self.contacts_view.set_search(value)
        if self.appointments_view and self.page.route == '/appointments':
            self.appointments_view.set_search(value)
        if self.company_search_view and self.page.route == '/company-search':
            self.company_search_view.set_search(value)

    def _on_nav(self, index: int) -> None:
        routes = ['/dashboard', '/company-search', '/clients', '/contacts', '/sites', '/appointments', '/settings', '/backup']
        self.page.go(routes[index])

    def _title(self, route: str) -> str:
        return {
            '/dashboard': 'Dashboard',
            '/company-search': 'Ricerca Aziende',
            '/clients': 'Clienti',
            '/contacts': 'Contatti',
            '/sites': 'Siti',
            '/appointments': 'Appuntamenti',
            '/settings': 'Impostazioni',
            '/backup': 'Backup',
        }.get(route, 'Agency Manager')

    def _build_body(self, route: str) -> ft.Control:
        if route == '/dashboard':
            data = self._dashboard_data()
            return dashboard_view(
                username=self.user.username if self.user else '',
                stats=data['stats'],
                today_appointments=data['today_appointments'],
                hosting_expiry=data['hosting_expiry'],
                latest_contacts=data['latest_contacts'],
                latest_searches=data['latest_searches'],
                open_company_search=lambda: self.page.go('/company-search'),
            )
        if route == '/company-search':
            self.company_search_view = CompanySearchView(self.page, self.user, self._notify)
            self.company_search_view.set_search(self.global_search)
            return self.company_search_view.build()
        if route == '/clients':
            self.clients_view = ClientsView(self.page, self.user, self._notify)
            self.clients_view.set_search(self.global_search)
            return self.clients_view.build()
        if route == '/contacts':
            self.contacts_view = ContactsView(self.page, self.user, self._notify)
            self.contacts_view.set_search(self.global_search)
            return self.contacts_view.build()
        if route == '/sites':
            self.sites_view = SitesView(self.page, self.user, self._notify)
            self.sites_view.set_search(self.global_search)
            return self.sites_view.build()
        if route == '/appointments':
            self.appointments_view = AppointmentsView(self.page, self.user, self._notify)
            self.appointments_view.set_search(self.global_search)
            return self.appointments_view.build()
        if route == '/settings':
            return self._settings_view()
        if route == '/backup':
            return self._backup_view()
        return ft.Text('Route non trovata')

    def _dashboard_data(self) -> dict:
        today = date.today().strftime('%Y-%m-%d')
        with get_connection() as conn:
            stats = {
                'Siti': int(conn.execute('SELECT COUNT(*) as c FROM sites').fetchone()['c']),
                'Clienti': int(conn.execute('SELECT COUNT(*) as c FROM clients').fetchone()['c']),
                'Contatti': int(conn.execute('SELECT COUNT(*) as c FROM contacts').fetchone()['c']),
                'App. Oggi': int(
                    conn.execute('SELECT COUNT(*) as c FROM appointments WHERE appointment_date = ?', (today,)).fetchone()['c']
                ),
                'App. Totali': int(conn.execute('SELECT COUNT(*) as c FROM appointments').fetchone()['c']),
                'Ricerca Aziende': int(conn.execute('SELECT COUNT(*) as c FROM company_search_results').fetchone()['c']),
            }
            rows = conn.execute(
                """
                SELECT id, subject_name, start_time, end_time, appointment_type
                FROM appointments
                WHERE appointment_date = ?
                ORDER BY start_time ASC, id ASC
                """,
                (today,),
            ).fetchall()
            hosting_expiry = conn.execute(
                """
                SELECT
                    s.domain,
                    COALESCE(c.name, '') AS client_name,
                    s.expiry_date,
                    CAST(julianday(date(s.expiry_date)) - julianday(date('now')) AS INT) AS days_left
                FROM sites s
                LEFT JOIN clients c ON c.id = s.client_id
                WHERE s.expiry_date IS NOT NULL AND s.expiry_date <> ''
                ORDER BY date(s.expiry_date) ASC, s.domain ASC
                LIMIT 10
                """
            ).fetchall()
            latest_contacts = conn.execute(
                """
                SELECT name, company, phone, updated_at
                FROM contacts
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT 10
                """
            ).fetchall()
            latest_searches = conn.execute(
                """
                SELECT company, phone, province, updated_at
                FROM company_search_results
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT 10
                """
            ).fetchall()
        return {
            'stats': stats,
            'today_appointments': [dict(r) for r in rows],
            'hosting_expiry': [dict(r) for r in hosting_expiry],
            'latest_contacts': [dict(r) for r in latest_contacts],
            'latest_searches': [dict(r) for r in latest_searches],
        }

    def _settings_view(self) -> ft.Control:
        inactivity = ft.TextField(label='Auto-lock minuti inattività', value=str(self.settings.get_inactivity_minutes()), width=220)
        self._style_text_field(inactivity)

        def save_settings(_):
            if not (inactivity.value or '').isdigit():
                self._notify('Valore inattività non valido')
                return
            self.settings.set_inactivity_minutes(int(inactivity.value))
            self.tracker.reset(self.settings.get_inactivity_minutes())
            self._notify('Impostazioni salvate')

        controls: list[ft.Control] = [
            ft.Container(
                padding=12,
                border=ft.border.all(1, ui_theme.BORDER),
                border_radius=10,
                content=ft.Column(controls=[inactivity, ft.OutlinedButton('Salva', on_click=save_settings)]),
            )
        ]

        if self.user and self.user.role == 'admin':
            users_list = ft.Column(spacing=8)

            def refresh_users():
                users = self.auth.list_users()
                users_list.controls = [
                    ft.Container(
                        border=ft.border.all(1, ui_theme.BORDER),
                        border_radius=8,
                        padding=10,
                        content=ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    f"{u['username']}  |  ruolo: {u['role']}  |  pwd: {'si' if u['can_view_passwords'] else 'no'}  |  attivo: {'si' if u['is_active'] else 'no'}",
                                    color=ft.Colors.WHITE,
                                ),
                                ft.IconButton(icon=ft.Icons.EDIT, icon_color=ft.Colors.WHITE, on_click=lambda _, user=u: open_user_dialog(user)),
                            ],
                        ),
                    )
                    for u in users
                ]

            def open_user_dialog(current: dict | None = None):
                username = ft.TextField(label='Username', value=(current or {}).get('username', ''), disabled=bool(current))
                password = ft.TextField(label='Password', password=True, can_reveal_password=True)
                role = ft.Dropdown(
                    label='Ruolo',
                    options=[ft.dropdown.Option('admin'), ft.dropdown.Option('operator')],
                    value=(current or {}).get('role', 'operator'),
                )
                self._style_text_field(username)
                self._style_text_field(password)
                self._style_dropdown(role)
                can_view = ft.Checkbox(label='Può vedere password', value=bool((current or {}).get('can_view_passwords', False)))
                active = ft.Checkbox(label='Attivo', value=bool((current or {}).get('is_active', True)))

                def save_user(_):
                    if current:
                        if current['id'] == self.user.id and not active.value:
                            self._notify('Non puoi disattivare l\'utente corrente')
                            return
                        self.auth.update_user_flags(current['id'], role.value, bool(can_view.value), bool(active.value))
                        self._notify('Utente aggiornato')
                    else:
                        if not (username.value or '').strip() or not (password.value or '').strip():
                            self._notify('Username e password obbligatori')
                            return
                        try:
                            self.auth.create_user_with_data_key(
                                username=username.value.strip(),
                                password=password.value,
                                role=role.value,
                                can_view_passwords=bool(can_view.value),
                                data_key=self.user.data_key,
                            )
                        except Exception as exc:
                            self._notify(f'Errore creazione utente: {exc}')
                            return
                        self._notify('Utente creato')
                    self._close_dialog()
                    refresh_users()
                    self.page.update()

                self._dialog = ft.AlertDialog(
                    bgcolor=ui_theme.CARD_BG,
                    barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
                    title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
                    content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
                    modal=True,
                    title=ft.Text('Modifica utente' if current else 'Nuovo utente'),
                    content=ft.Container(width=520, content=ft.Column(tight=True, controls=[username, password, role, can_view, active])),
                    actions=[ft.TextButton('Chiudi', on_click=lambda _: self._close_dialog()), ft.ElevatedButton('Salva', on_click=save_user)],
                )
                self.page.show_dialog(self._dialog)

            refresh_users()

            controls.append(
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=10,
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                controls=[
                                    ft.Text('Utenti locali', weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                                    ft.OutlinedButton('Nuovo utente', icon=ft.Icons.PERSON_ADD, on_click=lambda _: open_user_dialog()),
                                ],
                            ),
                            ft.Column(scroll=ft.ScrollMode.AUTO, height=240, controls=[users_list]),
                        ]
                    ),
                )
            )

        logs, _ = self.audit_repo.list_logs(page=1, page_size=30)
        audit_list = ft.Column(
            spacing=6,
            controls=[
                ft.Container(
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=8,
                    padding=10,
                    content=ft.Text(
                        f"{l['created_at']} | {l.get('username') or '-'} | {l['action']} | {l['entity_type']}#{l.get('entity_id') or '-'} | {l.get('details') or '-'}",
                        color=ft.Colors.WHITE,
                    ),
                )
                for l in logs
            ],
        )
        controls.append(
            ft.Container(
                padding=12,
                border=ft.border.all(1, ui_theme.BORDER),
                border_radius=10,
                content=ft.Column(
                    controls=[
                        ft.Text('Audit log locale (ultimi 30)', weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        ft.Column(height=260, scroll=ft.ScrollMode.AUTO, controls=[audit_list]),
                    ]
                ),
            )
        )

        return ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=controls)

    def _backup_view(self) -> ft.Control:
        password = ft.TextField(label='Password backup', password=True, can_reveal_password=True, width=260)
        backup_dir = ft.TextField(label='Cartella backup', value=self._default_backup_directory(), width=700, read_only=False)
        export_filename = ft.TextField(label='Nome file backup', value='backup.ambak', width=260)
        import_file = ft.TextField(label='File backup cifrato da importare', width=700, read_only=False)
        status_text = ft.Text('Stato backup: pronto', color=ui_theme.TEXT_MUTED, size=12)
        self._style_text_field(password)
        self._style_text_field(backup_dir)
        self._style_text_field(export_filename)
        self._style_text_field(import_file)
        picker = self.file_picker

        def set_status(message: str, ok: bool | None = None) -> None:
            status_text.value = message
            if ok is True:
                status_text.color = ft.Colors.GREEN_300
            elif ok is False:
                status_text.color = ft.Colors.RED_300
            else:
                status_text.color = ui_theme.TEXT_MUTED
            self.page.update()

        def _native_pick_directory(initial_dir: str | None = None) -> str | None:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                selected = filedialog.askdirectory(
                    title='Seleziona cartella backup',
                    initialdir=initial_dir or '',
                    parent=root,
                )
                root.destroy()
                return selected or None
            except Exception:
                return None

        def _native_pick_file(initial_dir: str | None = None) -> str | None:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                selected = filedialog.askopenfilename(
                    title='Seleziona backup cifrato',
                    initialdir=initial_dir or '',
                    filetypes=[('Encrypted backup', '*.ambak *.json'), ('All files', '*.*')],
                    parent=root,
                )
                root.destroy()
                return selected or None
            except Exception:
                return None

        async def choose_backup_dir_async(_: ft.ControlEvent):
            initial_dir = (backup_dir.value or '').strip() or None
            native_selected = _native_pick_directory(initial_dir)
            if native_selected:
                backup_dir.value = native_selected
                set_status(f'Cartella selezionata: {native_selected}', True)
                self.page.update()
                return

            if picker is None:
                self._notify('File picker non disponibile su questa versione')
                return
            try:
                selected = await picker.get_directory_path(
                    dialog_title='Seleziona cartella backup',
                    initial_directory=initial_dir,
                )
                if selected:
                    backup_dir.value = selected
                    set_status(f'Cartella selezionata: {selected}', True)
                    self.page.update()
            except Exception as exc:
                set_status(f'Errore selezione cartella: {exc}', False)
                self._notify(f'Errore selezione cartella: {exc}')

        async def choose_import_file_async(_: ft.ControlEvent):
            initial_dir = (backup_dir.value or '').strip() or None
            native_selected = _native_pick_file(initial_dir)
            if native_selected:
                import_file.value = native_selected
                set_status(f'File selezionato: {native_selected}', True)
                self.page.update()
                return

            if picker is None:
                self._notify('File picker non disponibile su questa versione')
                return
            try:
                files = await picker.pick_files(
                    dialog_title='Seleziona backup cifrato',
                    file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=['ambak', 'json'],
                    allow_multiple=False,
                    initial_directory=initial_dir,
                )
                if files:
                    import_file.value = files[0].path or files[0].name
                    set_status(f'File selezionato: {import_file.value}', True)
                    self.page.update()
            except Exception as exc:
                set_status(f'Errore selezione file: {exc}', False)
                self._notify(f'Errore selezione file: {exc}')

        def do_export(_):
            if not password.value:
                set_status('Export fallito: password backup mancante', False)
                self._notify('Inserisci password backup')
                return
            folder = Path((backup_dir.value or '').strip() or '.')
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                set_status(f'Export fallito: cartella non valida ({exc})', False)
                self._notify(f'Cartella backup non valida: {exc}')
                return
            file_name = (export_filename.value or 'backup.ambak').strip() or 'backup.ambak'
            if not file_name.lower().endswith('.ambak'):
                file_name = f'{file_name}.ambak'
            path = folder / file_name
            try:
                export_encrypted_backup(path, password.value)
            except Exception as exc:
                set_status(f'Export fallito: {exc}', False)
                self._notify(f'Errore export backup: {exc}')
                return
            if not path.exists() or path.stat().st_size <= 0:
                set_status('Export fallito: file non creato o vuoto', False)
                self._notify('Errore export backup: file non creato correttamente')
                return
            set_status(f'Export OK: {path} ({path.stat().st_size} bytes)', True)
            self._notify(f'Backup esportato: {path}')

        def do_import(_):
            if not password.value:
                set_status('Import fallito: password backup mancante', False)
                self._notify('Inserisci password backup')
                return
            raw = (import_file.value or '').strip()
            if not raw:
                set_status('Import fallito: file backup non selezionato', False)
                self._notify('Seleziona prima un file backup')
                return
            path = Path(raw)
            if not path.exists() or not path.is_file():
                set_status(f'Import fallito: file non trovato ({raw})', False)
                self._notify('File backup non trovato')
                return
            try:
                import_encrypted_backup(path, password.value)
            except Exception as exc:
                set_status(f'Import fallito: {exc}', False)
                self._notify(f'Errore import backup: {exc}')
                return
            try:
                # Ensure imported DB is aligned with current app schema.
                run_migrations()
            except Exception as exc:
                set_status(f'Import parziale: migrazione fallita ({exc})', False)
                self._notify(f'Backup importato, ma migrazione fallita: {exc}')
                return

            # Force fresh authentication/data-key loading after DB replacement.
            self.auth.clear_cached_data_key()
            clear_remember_token_file()
            self.user = None
            self.remember_token = None
            self.is_locked = False
            set_status('Import OK: backup caricato. Reindirizzo al login...', True)
            self._notify('Backup importato con successo. Effettua nuovamente il login.')

            async def go_login_later():
                await asyncio.sleep(1.2)
                self.page.go('/login')

            self.page.run_task(go_login_later)

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=10,
                    content=ft.Column(
                        controls=[
                            ft.Text('Backup automatico locale attivo (rotazione ultimi 10).', color=ft.Colors.WHITE),
                            backup_dir,
                            ft.Text('Puoi anche inserire manualmente il percorso cartella.', color=ui_theme.TEXT_MUTED, size=12),
                            ft.Row(
                                controls=[
                                    ft.OutlinedButton(
                                        'Seleziona cartella backup',
                                        icon=ft.Icons.FOLDER_OPEN,
                                        on_click=choose_backup_dir_async,
                                    ),
                                    export_filename,
                                ]
                            ),
                            password,
                            ft.Row([ft.ElevatedButton('Export cifrato', on_click=do_export)]),
                            status_text,
                        ]
                    ),
                ),
                ft.Container(
                    padding=12,
                    border=ft.border.all(1, ui_theme.BORDER),
                    border_radius=10,
                    content=ft.Column(
                        controls=[
                            ft.Text('Import backup cifrato', weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            import_file,
                            ft.Text('Puoi anche incollare il percorso completo del file .ambak', color=ui_theme.TEXT_MUTED, size=12),
                            ft.Row(
                                controls=[
                                    ft.OutlinedButton(
                                        'Seleziona file backup',
                                        icon=ft.Icons.UPLOAD_FILE,
                                        on_click=choose_import_file_async,
                                    ),
                                    ft.ElevatedButton('Import backup', icon=ft.Icons.BACKUP, on_click=do_import),
                                ]
                            ),
                        ]
                    ),
                ),
            ],
        )

    def _default_backup_directory(self) -> str:
        one_drive = (
            os.getenv('OneDrive')
            or os.getenv('OneDriveConsumer')
            or os.getenv('OneDriveCommercial')
        )
        if not one_drive:
            return str(Path.cwd())
        target = Path(one_drive) / 'Agency Manager' / 'backups'
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    def _handle_login(self, username: str, password: str, remember: bool) -> tuple[bool, str]:
        user = self.auth.login(username.strip(), password)
        if not user:
            return False, 'Credenziali non valide'

        self.user = user
        self.tracker.reset(self.settings.get_inactivity_minutes())

        if remember:
            token = self.auth.issue_remember_token(user.id)
            save_remember_token(token)
            self.auth.cache_data_key(user.username, user.data_key)
            self.remember_token = token
        else:
            clear_remember_token_file()
            self.auth.clear_cached_data_key()

        self.page.go('/dashboard')
        return True, ''

    def _show_lock_dialog(self) -> None:
        password = ft.TextField(label='Password per sbloccare', password=True, can_reveal_password=True)
        self._style_text_field(password)

        def unlock(_):
            if not self.user:
                return
            check = self.auth.login(self.user.username, password.value or '')
            if not check:
                self._notify('Password errata')
                return
            self.user = check
            self.is_locked = False
            self.tracker.reset(self.settings.get_inactivity_minutes())
            self._close_dialog()
            self.page.update()

        self._dialog = ft.AlertDialog(
            bgcolor=ui_theme.CARD_BG,
            barrier_color=ft.Colors.with_opacity(0.55, ft.Colors.BLACK),
            title_text_style=ft.TextStyle(color=ft.Colors.WHITE, weight=ft.FontWeight.W_600),
            content_text_style=ft.TextStyle(color=ft.Colors.WHITE),
            modal=True,
            title=ft.Text('Sessione bloccata per inattività'),
            content=password,
            actions=[ft.ElevatedButton('Sblocca', on_click=unlock), ft.TextButton('Logout', on_click=lambda _: self._logout())],
        )
        self.page.show_dialog(self._dialog)

    def _close_dialog(self) -> None:
        if self._dialog:
            self.page.pop_dialog()
            self._dialog = None
            self.page.update()

    def _logout(self) -> None:
        if self.remember_token:
            self.auth.revoke_remember_token(self.remember_token)
        clear_remember_token_file()
        self.auth.clear_cached_data_key()
        self.user = None
        self.remember_token = None
        self.is_locked = False
        self.page.go('/login')

    def _toggle_window_maximize(self) -> None:
        self.page.window.maximized = not bool(self.page.window.maximized)
        self.page.update()

    def _minimize_window(self) -> None:
        self.page.window.minimized = True
        self.page.update()

    def _close_window(self) -> None:
        async def close_async():
            try:
                await self.page.window.close()
                return
            except RuntimeError as exc:
                if 'Session closed' in str(exc):
                    return
            except Exception:
                pass

            try:
                await self.page.window.destroy()
            except RuntimeError as exc:
                if 'Session closed' in str(exc):
                    return
            except Exception:
                pass

        self.page.run_task(close_async)

    def _notify(self, text: str) -> None:
        try:
            self.page.snack_bar = ft.SnackBar(ft.Text(text), open=True)
            self.page.update()
        except RuntimeError as exc:
            if 'Session closed' in str(exc):
                return
            raise

    def _style_text_field(self, field: ft.TextField) -> None:
        field.color = ft.Colors.WHITE
        field.label_style = ft.TextStyle(color=ft.Colors.WHITE70)
        field.hint_style = ft.TextStyle(color=ft.Colors.WHITE54)
        field.border_color = ui_theme.BORDER
        field.focused_border_color = ft.Colors.WHITE70

    def _style_dropdown(self, field: ft.Dropdown) -> None:
        field.color = ft.Colors.WHITE
        field.text_style = ft.TextStyle(color=ft.Colors.WHITE)
        field.label_style = ft.TextStyle(color=ft.Colors.WHITE70)
        field.border_color = ui_theme.BORDER
        field.focused_border_color = ft.Colors.WHITE70


def app_main(page: ft.Page) -> None:
    AppController(page).start()
