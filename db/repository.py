from __future__ import annotations

import sqlite3
import hashlib
from typing import Any

from core.crypto import decrypt_field, encrypt_field
from db.connection import get_connection
from models.entities import SitePayload


def log_audit(user_id: int, action: str, entity_type: str, entity_id: int | None, details: str = '') -> None:
    with get_connection() as conn:
        conn.execute(
            'INSERT INTO audit_logs(user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)',
            (user_id, action, entity_type, entity_id, details),
        )


def _get_or_create_client(conn: sqlite3.Connection, name: str | None, created_by: int) -> int | None:
    if not name:
        return None
    existing = conn.execute('SELECT id FROM clients WHERE lower(name) = lower(?)', (name.strip(),)).fetchone()
    if existing:
        return int(existing['id'])
    cur = conn.execute('INSERT INTO clients(name, created_by) VALUES (?, ?)', (name.strip(), created_by))
    return int(cur.lastrowid)


def _upsert_email_profiles(conn: sqlite3.Connection, site_id: int, email_data: dict[str, str] | None, data_key: bytes) -> None:
    if email_data is None:
        return
    slots = [
        ('mailbox_1', 'mailbox_1_user', 'mailbox_1_pass', None),
        ('mailbox_2', 'mailbox_2_user', 'mailbox_2_pass', None),
        ('mailbox_3', 'mailbox_3_user', 'mailbox_3_pass', None),
        ('mailbox_4', 'mailbox_4_user', 'mailbox_4_pass', None),
        ('phpmailer_form', 'phpmailer_user', 'phpmailer_pass', 'phpmailer_note'),
    ]
    for domain_key, user_key, pass_key, note_key in slots:
        user_val = (email_data.get(user_key) or '').strip()
        pass_val = (email_data.get(pass_key) or '').strip()
        note_val = (email_data.get(note_key) or '').strip() if note_key else ''

        existing = conn.execute(
            'SELECT id FROM email_accounts WHERE site_id = ? AND domain = ?',
            (site_id, domain_key),
        ).fetchone()

        if not user_val and not pass_val and not note_val:
            if existing:
                conn.execute('DELETE FROM email_accounts WHERE id = ?', (existing['id'],))
            continue

        user_enc = encrypt_field(user_val, data_key)
        pass_enc = encrypt_field(pass_val, data_key)
        if existing:
            conn.execute(
                """
                UPDATE email_accounts
                SET email_user_enc = ?, email_password_enc = ?, notes = ?
                WHERE id = ?
                """,
                (user_enc, pass_enc, note_val, existing['id']),
            )
        else:
            conn.execute(
                """
                INSERT INTO email_accounts(site_id, domain, email_user_enc, email_password_enc, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (site_id, domain_key, user_enc, pass_enc, note_val),
            )


PEOPLE_COLUMNS = [
    'name',
    'company',
    'email',
    'phone',
    'landline_phone',
    'city',
    'municipality',
    'region',
    'province',
    'address',
    'contact_role',
    'client_type',
    'sector',
    'project_type',
    'fiscal_code',
    'vat_number',
    'notes',
]


class SiteRepository:
    def create_site(
        self,
        payload: SitePayload,
        user_id: int,
        data_key: bytes,
        email_data: dict[str, str] | None = None,
    ) -> int:
        with get_connection() as conn:
            client_id = _get_or_create_client(conn, payload.client_name, user_id)
            cur = conn.execute(
                """
                INSERT INTO sites(client_id, domain, provider, tags, notes, expiry_date, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    payload.domain.strip().lower(),
                    payload.provider,
                    payload.tags,
                    payload.notes,
                    payload.expiry_date,
                    user_id,
                ),
            )
            site_id = int(cur.lastrowid)

            conn.execute(
                """
                INSERT INTO hosting_credentials(site_id, panel, login_url, username_enc, password_enc, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    site_id,
                    payload.hosting_panel,
                    payload.hosting_login_url,
                    encrypt_field(payload.hosting_username, data_key),
                    encrypt_field(payload.hosting_password, data_key),
                    payload.hosting_notes,
                ),
            )
            conn.execute(
                """
                INSERT INTO ftp_credentials(site_id, protocol, host, port, username_enc, password_enc, root_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    site_id,
                    payload.ftp_protocol or 'sftp',
                    payload.ftp_host,
                    payload.ftp_port,
                    encrypt_field(payload.ftp_username, data_key),
                    encrypt_field(payload.ftp_password, data_key),
                    payload.ftp_root_path,
                    payload.ftp_notes,
                ),
            )
            conn.execute(
                """
                INSERT INTO database_credentials(site_id, host, port, dbname, username_enc, password_enc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    site_id,
                    payload.db_host,
                    payload.db_port,
                    payload.db_name,
                    encrypt_field(payload.db_username, data_key),
                    encrypt_field(payload.db_password, data_key),
                ),
            )
            _upsert_email_profiles(conn, site_id, email_data, data_key)

        log_audit(user_id, 'create', 'site', site_id, payload.domain)
        return site_id

    def update_site(
        self,
        site_id: int,
        payload: SitePayload,
        user_id: int,
        data_key: bytes,
        preserve_sensitive: bool = False,
        email_data: dict[str, str] | None = None,
    ) -> None:
        with get_connection() as conn:
            client_id = _get_or_create_client(conn, payload.client_name, user_id)
            conn.execute(
                """
                UPDATE sites
                SET client_id=?, domain=?, provider=?, tags=?, notes=?, expiry_date=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    client_id,
                    payload.domain.strip().lower(),
                    payload.provider,
                    payload.tags,
                    payload.notes,
                    payload.expiry_date,
                    site_id,
                ),
            )

            if preserve_sensitive:
                conn.execute(
                    'UPDATE hosting_credentials SET panel=?, login_url=?, notes=? WHERE site_id=?',
                    (payload.hosting_panel, payload.hosting_login_url, payload.hosting_notes, site_id),
                )
                conn.execute(
                    'UPDATE ftp_credentials SET protocol=?, host=?, port=?, root_path=?, notes=? WHERE site_id=?',
                    (payload.ftp_protocol or 'sftp', payload.ftp_host, payload.ftp_port, payload.ftp_root_path, payload.ftp_notes, site_id),
                )
                conn.execute(
                    'UPDATE database_credentials SET host=?, port=?, dbname=? WHERE site_id=?',
                    (payload.db_host, payload.db_port, payload.db_name, site_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE hosting_credentials
                    SET panel=?, login_url=?, username_enc=?, password_enc=?, notes=?
                    WHERE site_id=?
                    """,
                    (
                        payload.hosting_panel,
                        payload.hosting_login_url,
                        encrypt_field(payload.hosting_username, data_key),
                        encrypt_field(payload.hosting_password, data_key),
                        payload.hosting_notes,
                        site_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE ftp_credentials
                    SET protocol=?, host=?, port=?, username_enc=?, password_enc=?, root_path=?, notes=?
                    WHERE site_id=?
                    """,
                    (
                        payload.ftp_protocol or 'sftp',
                        payload.ftp_host,
                        payload.ftp_port,
                        encrypt_field(payload.ftp_username, data_key),
                        encrypt_field(payload.ftp_password, data_key),
                        payload.ftp_root_path,
                        payload.ftp_notes,
                        site_id,
                    ),
                )
                conn.execute(
                    """
                    UPDATE database_credentials
                    SET host=?, port=?, dbname=?, username_enc=?, password_enc=?
                    WHERE site_id=?
                    """,
                    (
                        payload.db_host,
                        payload.db_port,
                        payload.db_name,
                        encrypt_field(payload.db_username, data_key),
                        encrypt_field(payload.db_password, data_key),
                        site_id,
                    ),
                )
            _upsert_email_profiles(conn, site_id, email_data, data_key)

        log_audit(user_id, 'update', 'site', site_id)

    def delete_site(self, site_id: int, user_id: int) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM sites WHERE id=?', (site_id,))
        log_audit(user_id, 'delete', 'site', site_id)

    def get_site(self, site_id: int, data_key: bytes, include_sensitive: bool = True) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT s.*, c.name as client_name,
                       hc.panel, hc.login_url, hc.username_enc as h_user, hc.password_enc as h_pass, hc.notes as h_notes,
                       fc.protocol, fc.host as ftp_host, fc.port as ftp_port, fc.username_enc as ftp_user, fc.password_enc as ftp_pass, fc.root_path, fc.notes as ftp_notes,
                       dc.host as db_host, dc.port as db_port, dc.dbname, dc.username_enc as db_user, dc.password_enc as db_pass
                FROM sites s
                LEFT JOIN clients c ON c.id = s.client_id
                LEFT JOIN hosting_credentials hc ON hc.site_id = s.id
                LEFT JOIN ftp_credentials fc ON fc.site_id = s.id
                LEFT JOIN database_credentials dc ON dc.site_id = s.id
                WHERE s.id = ?
                """,
                (site_id,),
            ).fetchone()
            if row is None:
                return None

        def _v(cipher):
            if not include_sensitive:
                return ''
            return decrypt_field(cipher, data_key)

        email_defaults = {
            'mailbox_1_user': '',
            'mailbox_1_pass': '',
            'mailbox_2_user': '',
            'mailbox_2_pass': '',
            'mailbox_3_user': '',
            'mailbox_3_pass': '',
            'mailbox_4_user': '',
            'mailbox_4_pass': '',
            'phpmailer_user': '',
            'phpmailer_pass': '',
            'phpmailer_note': '',
        }
        domain_map = {
            'mailbox_1': ('mailbox_1_user', 'mailbox_1_pass'),
            'mailbox_2': ('mailbox_2_user', 'mailbox_2_pass'),
            'mailbox_3': ('mailbox_3_user', 'mailbox_3_pass'),
            'mailbox_4': ('mailbox_4_user', 'mailbox_4_pass'),
            'phpmailer_form': ('phpmailer_user', 'phpmailer_pass'),
        }
        with get_connection() as conn:
            mail_rows = conn.execute(
                'SELECT domain, email_user_enc, email_password_enc, notes FROM email_accounts WHERE site_id = ?',
                (site_id,),
            ).fetchall()
        for m in mail_rows:
            key_pair = domain_map.get(m['domain'])
            if not key_pair:
                continue
            email_defaults[key_pair[0]] = _v(m['email_user_enc'])
            email_defaults[key_pair[1]] = _v(m['email_password_enc'])
            if m['domain'] == 'phpmailer_form':
                email_defaults['phpmailer_note'] = m['notes'] or ''

        result = {
            'id': row['id'],
            'client_name': row['client_name'] or '',
            'domain': row['domain'],
            'provider': row['provider'] or '',
            'tags': row['tags'] or '',
            'notes': row['notes'] or '',
            'expiry_date': row['expiry_date'] or '',
            'hosting_panel': row['panel'] or '',
            'hosting_login_url': row['login_url'] or '',
            'hosting_username': _v(row['h_user']),
            'hosting_password': _v(row['h_pass']),
            'hosting_notes': row['h_notes'] or '',
            'ftp_protocol': row['protocol'] or 'sftp',
            'ftp_host': row['ftp_host'] or '',
            'ftp_port': row['ftp_port'] or 22,
            'ftp_username': _v(row['ftp_user']),
            'ftp_password': _v(row['ftp_pass']),
            'ftp_root_path': row['root_path'] or '',
            'ftp_notes': row['ftp_notes'] or '',
            'db_host': row['db_host'] or '',
            'db_port': row['db_port'] or 3306,
            'db_name': row['dbname'] or '',
            'db_username': _v(row['db_user']),
            'db_password': _v(row['db_pass']),
        }
        result.update(email_defaults)
        return result

    def list_sites(
        self,
        query: str = '',
        provider: str = '',
        page: int = 1,
        page_size: int = 50,
        sort_key: str = 'expiry_asc',
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []

        if query:
            where.append('(s.domain LIKE ? OR c.name LIKE ? OR s.provider LIKE ?)')
            q = f'%{query}%'
            params.extend([q, q, q])
        if provider:
            where.append('s.provider = ?')
            params.append(provider)

        clause = f"WHERE {' AND '.join(where)}" if where else ''
        offset = (page - 1) * page_size
        order_clause = self._site_order_clause(sort_key)

        with get_connection() as conn:
            total_row = conn.execute(
                f'SELECT COUNT(*) as c FROM sites s LEFT JOIN clients c ON c.id = s.client_id {clause}',
                tuple(params),
            ).fetchone()
            rows = conn.execute(
                f"""
                SELECT
                    s.id,
                    s.domain,
                    s.provider,
                    s.expiry_date,
                    CAST(julianday(date(s.expiry_date)) - julianday(date('now')) AS INT) AS days_left,
                    s.updated_at,
                    c.name as client_name
                FROM sites s
                LEFT JOIN clients c ON c.id = s.client_id
                {clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                tuple(params + [page_size, offset]),
            ).fetchall()

        return [dict(row) for row in rows], int(total_row['c'])

    def _site_order_clause(self, sort_key: str) -> str:
        mapping = {
            'expiry_asc': "CASE WHEN s.expiry_date IS NULL OR s.expiry_date = '' THEN 1 ELSE 0 END, date(s.expiry_date) ASC, s.domain ASC",
            'expiry_desc': "CASE WHEN s.expiry_date IS NULL OR s.expiry_date = '' THEN 1 ELSE 0 END, date(s.expiry_date) DESC, s.domain ASC",
            'domain_asc': "s.domain COLLATE NOCASE ASC",
            'domain_desc': "s.domain COLLATE NOCASE DESC",
            'client_asc': "COALESCE(c.name, '') COLLATE NOCASE ASC, s.domain ASC",
            'client_desc': "COALESCE(c.name, '') COLLATE NOCASE DESC, s.domain ASC",
            'provider_asc': "COALESCE(s.provider, '') COLLATE NOCASE ASC, s.domain ASC",
            'provider_desc': "COALESCE(s.provider, '') COLLATE NOCASE DESC, s.domain ASC",
            'status_asc': """
                CASE
                    WHEN s.expiry_date IS NULL OR s.expiry_date = '' THEN 3
                    WHEN date(s.expiry_date) < date('now') THEN 0
                    WHEN (julianday(date(s.expiry_date)) - julianday(date('now'))) <= 30 THEN 1
                    ELSE 2
                END ASC, date(s.expiry_date) ASC
            """,
            'status_desc': """
                CASE
                    WHEN s.expiry_date IS NULL OR s.expiry_date = '' THEN 3
                    WHEN date(s.expiry_date) < date('now') THEN 0
                    WHEN (julianday(date(s.expiry_date)) - julianday(date('now'))) <= 30 THEN 1
                    ELSE 2
                END DESC, date(s.expiry_date) ASC
            """,
            'updated_asc': "datetime(s.updated_at) ASC, s.domain ASC",
            'updated_desc': "datetime(s.updated_at) DESC, s.domain ASC",
        }
        return mapping.get(sort_key, mapping['expiry_asc'])

    def list_providers(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT provider FROM sites WHERE provider IS NOT NULL AND provider <> '' ORDER BY provider"
            ).fetchall()
            return [row['provider'] for row in rows]

    def list_site_options(self) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute('SELECT id, domain FROM sites ORDER BY domain').fetchall()
            return [dict(row) for row in rows]


class ClientRepository:
    def list_client_choices(self, query: str = '', limit: int = 10) -> list[dict[str, Any]]:
        with get_connection() as conn:
            if query.strip():
                rows = conn.execute(
                    """
                    SELECT name, company, updated_at
                    FROM clients
                    WHERE name LIKE ? OR company LIKE ?
                    ORDER BY datetime(updated_at) DESC, name ASC
                    LIMIT ?
                    """,
                    (f'%{query.strip()}%', f'%{query.strip()}%', limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT name, company, updated_at
                    FROM clients
                    ORDER BY datetime(updated_at) DESC, name ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def find_client_by_name(self, name: str) -> dict[str, Any] | None:
        clean = (name or '').strip()
        if not clean:
            return None
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM clients
                WHERE lower(name) = lower(?)
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT 1
                """,
                (clean,),
            ).fetchone()
        return dict(row) if row else None

    def list_clients(
        self,
        query: str = '',
        region: str = '',
        province: str = '',
        page: int = 1,
        page_size: int = 50,
        sort_key: str = 'name_asc',
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append(
                '(c.name LIKE ? OR c.company LIKE ? OR c.email LIKE ? OR c.city LIKE ? OR c.municipality LIKE ? OR c.province LIKE ? OR c.region LIKE ? OR c.address LIKE ? OR c.contact_role LIKE ? OR c.client_type LIKE ? OR c.sector LIKE ? OR c.project_type LIKE ? OR c.fiscal_code LIKE ? OR c.vat_number LIKE ? OR c.phone LIKE ? OR c.landline_phone LIKE ?)'
            )
            q = f'%{query}%'
            params.extend([q, q, q, q, q, q, q, q, q, q, q, q, q, q, q, q])
        if region:
            where.append('c.region = ?')
            params.append(region)
        if province:
            where.append('c.province = ?')
            params.append(province)

        clause = f"WHERE {' AND '.join(where)}" if where else ''
        offset = (page - 1) * page_size
        order_clause = self._client_order_clause(sort_key)
        with get_connection() as conn:
            total = conn.execute(f'SELECT COUNT(*) AS c FROM clients c {clause}', tuple(params)).fetchone()['c']
            rows = conn.execute(
                f"""
                SELECT c.*, (SELECT COUNT(*) FROM sites s WHERE s.client_id = c.id) AS sites_count
                FROM clients c
                {clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                tuple(params + [page_size, offset]),
            ).fetchall()
        return [dict(r) for r in rows], int(total)

    def _client_order_clause(self, sort_key: str) -> str:
        mapping = {
            'name_asc': "COALESCE(c.name, '') COLLATE NOCASE ASC",
            'name_desc': "COALESCE(c.name, '') COLLATE NOCASE DESC",
            'type_asc': "COALESCE(c.client_type, '') COLLATE NOCASE ASC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'type_desc': "COALESCE(c.client_type, '') COLLATE NOCASE DESC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'company_asc': "COALESCE(c.company, '') COLLATE NOCASE ASC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'company_desc': "COALESCE(c.company, '') COLLATE NOCASE DESC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'email_asc': "COALESCE(c.email, '') COLLATE NOCASE ASC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'email_desc': "COALESCE(c.email, '') COLLATE NOCASE DESC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'region_asc': "COALESCE(c.region, '') COLLATE NOCASE ASC, COALESCE(c.province, '') COLLATE NOCASE ASC",
            'region_desc': "COALESCE(c.region, '') COLLATE NOCASE DESC, COALESCE(c.province, '') COLLATE NOCASE ASC",
            'province_asc': "COALESCE(c.province, '') COLLATE NOCASE ASC, COALESCE(c.city, '') COLLATE NOCASE ASC",
            'province_desc': "COALESCE(c.province, '') COLLATE NOCASE DESC, COALESCE(c.city, '') COLLATE NOCASE ASC",
            'sites_desc': "sites_count DESC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'sites_asc': "sites_count ASC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'updated_desc': "datetime(c.updated_at) DESC, COALESCE(c.name, '') COLLATE NOCASE ASC",
            'updated_asc': "datetime(c.updated_at) ASC, COALESCE(c.name, '') COLLATE NOCASE ASC",
        }
        return mapping.get(sort_key, mapping['name_asc'])

    def list_provinces(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT province FROM clients WHERE province IS NOT NULL AND province <> '' ORDER BY province"
            ).fetchall()
        return [r['province'] for r in rows]

    def get_client(self, client_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
            return dict(row) if row else None

    def create_client(self, payload: dict[str, Any], user_id: int) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO clients(name, company, email, phone, landline_phone, city, municipality, region, province, address, contact_role, client_type, sector, project_type, fiscal_code, vat_number, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get('name', '').strip(),
                    payload.get('company'),
                    payload.get('email'),
                    payload.get('phone'),
                    payload.get('landline_phone'),
                    payload.get('city'),
                    payload.get('municipality'),
                    payload.get('region'),
                    payload.get('province'),
                    payload.get('address'),
                    payload.get('contact_role'),
                    payload.get('client_type'),
                    payload.get('sector'),
                    payload.get('project_type'),
                    payload.get('fiscal_code'),
                    payload.get('vat_number'),
                    payload.get('notes'),
                    user_id,
                ),
            )
            cid = int(cur.lastrowid)
        log_audit(user_id, 'create', 'client', cid, payload.get('name', ''))
        return cid

    def update_client(self, client_id: int, payload: dict[str, Any], user_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE clients
                SET name=?, company=?, email=?, phone=?, landline_phone=?, city=?, municipality=?, region=?, province=?, address=?, contact_role=?, client_type=?, sector=?, project_type=?, fiscal_code=?, vat_number=?, notes=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    payload.get('name', '').strip(),
                    payload.get('company'),
                    payload.get('email'),
                    payload.get('phone'),
                    payload.get('landline_phone'),
                    payload.get('city'),
                    payload.get('municipality'),
                    payload.get('region'),
                    payload.get('province'),
                    payload.get('address'),
                    payload.get('contact_role'),
                    payload.get('client_type'),
                    payload.get('sector'),
                    payload.get('project_type'),
                    payload.get('fiscal_code'),
                    payload.get('vat_number'),
                    payload.get('notes'),
                    client_id,
                ),
            )
        log_audit(user_id, 'update', 'client', client_id)

    def delete_client(self, client_id: int, user_id: int) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM clients WHERE id=?', (client_id,))
        log_audit(user_id, 'delete', 'client', client_id)

    def move_to_contacts(self, client_id: int, user_id: int) -> int:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
            if row is None:
                raise ValueError('Cliente non trovato')
            values = [row[col] for col in PEOPLE_COLUMNS]
            cur = conn.execute(
                f"INSERT INTO contacts({', '.join(PEOPLE_COLUMNS)}, created_by) VALUES ({', '.join(['?'] * len(PEOPLE_COLUMNS))}, ?)",
                tuple(values + [user_id]),
            )
            new_id = int(cur.lastrowid)
            conn.execute('DELETE FROM clients WHERE id = ?', (client_id,))
        log_audit(user_id, 'move', 'client', client_id, f'to_contact#{new_id}')
        return new_id


class ContactRepository:
    def list_contact_choices(self, query: str = '', limit: int = 10) -> list[dict[str, Any]]:
        with get_connection() as conn:
            if query.strip():
                rows = conn.execute(
                    """
                    SELECT name, company, updated_at
                    FROM contacts
                    WHERE name LIKE ? OR company LIKE ?
                    ORDER BY datetime(updated_at) DESC, name ASC
                    LIMIT ?
                    """,
                    (f'%{query.strip()}%', f'%{query.strip()}%', limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT name, company, updated_at
                    FROM contacts
                    ORDER BY datetime(updated_at) DESC, name ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def find_contact_by_name(self, name: str) -> dict[str, Any] | None:
        clean = (name or '').strip()
        if not clean:
            return None
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM contacts
                WHERE lower(name) = lower(?)
                ORDER BY datetime(updated_at) DESC, id DESC
                LIMIT 1
                """,
                (clean,),
            ).fetchone()
        return dict(row) if row else None

    def list_contacts(
        self,
        query: str = '',
        region: str = '',
        province: str = '',
        page: int = 1,
        page_size: int = 50,
        sort_key: str = 'name_asc',
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append(
                '(c.name LIKE ? OR c.company LIKE ? OR c.email LIKE ? OR c.city LIKE ? OR c.municipality LIKE ? OR c.province LIKE ? OR c.region LIKE ? OR c.address LIKE ? OR c.contact_role LIKE ? OR c.client_type LIKE ? OR c.sector LIKE ? OR c.project_type LIKE ? OR c.fiscal_code LIKE ? OR c.vat_number LIKE ? OR c.phone LIKE ? OR c.landline_phone LIKE ?)'
            )
            q = f'%{query}%'
            params.extend([q, q, q, q, q, q, q, q, q, q, q, q, q, q, q, q])
        if region:
            where.append('c.region = ?')
            params.append(region)
        if province:
            where.append('c.province = ?')
            params.append(province)

        clause = f"WHERE {' AND '.join(where)}" if where else ''
        offset = (page - 1) * page_size
        order_clause = ClientRepository()._client_order_clause(sort_key)
        with get_connection() as conn:
            total = conn.execute(f'SELECT COUNT(*) AS c FROM contacts c {clause}', tuple(params)).fetchone()['c']
            rows = conn.execute(
                f"""
                SELECT c.*, 0 AS sites_count
                FROM contacts c
                {clause}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?
                """,
                tuple(params + [page_size, offset]),
            ).fetchall()
        return [dict(r) for r in rows], int(total)

    def list_provinces(self) -> list[str]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT province FROM contacts WHERE province IS NOT NULL AND province <> '' ORDER BY province"
            ).fetchall()
        return [r['province'] for r in rows]

    def get_contact(self, contact_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM contacts WHERE id = ?', (contact_id,)).fetchone()
            return dict(row) if row else None

    def create_contact(self, payload: dict[str, Any], user_id: int) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO contacts(name, company, email, phone, landline_phone, city, municipality, region, province, address, contact_role, client_type, sector, project_type, fiscal_code, vat_number, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get('name', '').strip(),
                    payload.get('company'),
                    payload.get('email'),
                    payload.get('phone'),
                    payload.get('landline_phone'),
                    payload.get('city'),
                    payload.get('municipality'),
                    payload.get('region'),
                    payload.get('province'),
                    payload.get('address'),
                    payload.get('contact_role'),
                    payload.get('client_type'),
                    payload.get('sector'),
                    payload.get('project_type'),
                    payload.get('fiscal_code'),
                    payload.get('vat_number'),
                    payload.get('notes'),
                    user_id,
                ),
            )
            cid = int(cur.lastrowid)
        log_audit(user_id, 'create', 'contact', cid, payload.get('name', ''))
        return cid

    def update_contact(self, contact_id: int, payload: dict[str, Any], user_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE contacts
                SET name=?, company=?, email=?, phone=?, landline_phone=?, city=?, municipality=?, region=?, province=?, address=?, contact_role=?, client_type=?, sector=?, project_type=?, fiscal_code=?, vat_number=?, notes=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    payload.get('name', '').strip(),
                    payload.get('company'),
                    payload.get('email'),
                    payload.get('phone'),
                    payload.get('landline_phone'),
                    payload.get('city'),
                    payload.get('municipality'),
                    payload.get('region'),
                    payload.get('province'),
                    payload.get('address'),
                    payload.get('contact_role'),
                    payload.get('client_type'),
                    payload.get('sector'),
                    payload.get('project_type'),
                    payload.get('fiscal_code'),
                    payload.get('vat_number'),
                    payload.get('notes'),
                    contact_id,
                ),
            )
        log_audit(user_id, 'update', 'contact', contact_id)

    def delete_contact(self, contact_id: int, user_id: int) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM contacts WHERE id=?', (contact_id,))
        log_audit(user_id, 'delete', 'contact', contact_id)

    def move_to_clients(self, contact_id: int, user_id: int) -> int:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM contacts WHERE id = ?', (contact_id,)).fetchone()
            if row is None:
                raise ValueError('Contatto non trovato')
            values = [row[col] for col in PEOPLE_COLUMNS]
            cur = conn.execute(
                f"INSERT INTO clients({', '.join(PEOPLE_COLUMNS)}, created_by) VALUES ({', '.join(['?'] * len(PEOPLE_COLUMNS))}, ?)",
                tuple(values + [user_id]),
            )
            new_id = int(cur.lastrowid)
            conn.execute('DELETE FROM contacts WHERE id = ?', (contact_id,))
        log_audit(user_id, 'move', 'contact', contact_id, f'to_client#{new_id}')
        return new_id


class CompanySearchRepository:
    def list_results(
        self,
        query: str = '',
        province: str = '',
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        where: list[str] = []
        params: list[Any] = []
        if query:
            where.append(
                '(r.search_term LIKE ? OR r.company LIKE ? OR r.phone LIKE ? OR r.contact_name LIKE ? OR r.address LIKE ? OR r.city LIKE ? OR r.municipality LIKE ?)'
            )
            q = f'%{query}%'
            params.extend([q, q, q, q, q, q, q])
        if province:
            where.append('r.province = ?')
            params.append(province)

        clause = f"WHERE {' AND '.join(where)}" if where else ''
        offset = (page - 1) * page_size
        with get_connection() as conn:
            total = conn.execute(f'SELECT COUNT(*) AS c FROM company_search_results r {clause}', tuple(params)).fetchone()['c']
            rows = conn.execute(
                f"""
                SELECT r.*
                FROM company_search_results r
                {clause}
                ORDER BY
                    CASE WHEN r.distance_km IS NULL THEN 1 ELSE 0 END ASC,
                    r.distance_km ASC,
                    datetime(r.updated_at) ASC,
                    r.id ASC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [page_size, offset]),
            ).fetchall()
        return [dict(r) for r in rows], int(total)

    def save_many(self, rows: list[dict[str, Any]], user_id: int) -> int:
        if not rows:
            return 0
        saved = 0
        with get_connection() as conn:
            for row in rows:
                fingerprint = self._fingerprint(
                    row.get('search_term'),
                    row.get('company'),
                    row.get('phone'),
                    row.get('address'),
                    row.get('province'),
                )
                cur = conn.execute(
                    """
                    INSERT INTO company_search_results(
                        search_term, region, province, city, municipality,
                        company, phone, contact_name, address, distance_km,
                        source_name, source_url, fingerprint, created_by
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        search_term=excluded.search_term,
                        region=excluded.region,
                        province=excluded.province,
                        city=excluded.city,
                        municipality=excluded.municipality,
                        company=excluded.company,
                        phone=excluded.phone,
                        contact_name=excluded.contact_name,
                        address=excluded.address,
                        distance_km=excluded.distance_km,
                        source_name=excluded.source_name,
                        source_url=excluded.source_url,
                        updated_at=datetime('now')
                    """,
                    (
                        (row.get('search_term') or '').strip(),
                        (row.get('region') or '').strip() or 'Lombardia',
                        (row.get('province') or '').strip() or 'Milano',
                        (row.get('city') or '').strip(),
                        (row.get('municipality') or '').strip(),
                        (row.get('company') or '').strip(),
                        (row.get('phone') or '').strip(),
                        (row.get('contact_name') or '').strip(),
                        (row.get('address') or '').strip(),
                        row.get('distance_km'),
                        (row.get('source_name') or '').strip(),
                        (row.get('source_url') or '').strip(),
                        fingerprint,
                        user_id,
                    ),
                )
                saved += int(cur.rowcount > 0)
        log_audit(user_id, 'create', 'company_search_results', None, f'rows={saved}')
        return saved

    def clear_all(self, user_id: int) -> int:
        with get_connection() as conn:
            total = int(conn.execute('SELECT COUNT(*) AS c FROM company_search_results').fetchone()['c'])
            conn.execute('DELETE FROM company_search_results')
        log_audit(user_id, 'delete', 'company_search_results', None, f'rows={total}')
        return total

    def count_all(self) -> int:
        with get_connection() as conn:
            return int(conn.execute('SELECT COUNT(*) AS c FROM company_search_results').fetchone()['c'])

    def get_result(self, result_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM company_search_results WHERE id = ?', (result_id,)).fetchone()
            return dict(row) if row else None

    def delete_result(self, result_id: int, user_id: int) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM company_search_results WHERE id = ?', (result_id,))
        log_audit(user_id, 'delete', 'company_search_results', result_id)

    def move_to_contacts(self, result_id: int, user_id: int) -> int:
        row = self.get_result(result_id)
        if row is None:
            raise ValueError('Risultato non trovato')

        contact_name = (row.get('contact_name') or '').strip()
        company_name = (row.get('company') or '').strip()
        payload = {
            'name': contact_name or company_name or 'Contatto da ricerca',
            'company': company_name,
            'email': '',
            'phone': row.get('phone') or '',
            'landline_phone': '',
            'city': row.get('city') or '',
            'municipality': row.get('municipality') or '',
            'region': row.get('region') or '',
            'province': row.get('province') or '',
            'address': row.get('address') or '',
            'contact_role': '',
            'client_type': 'Azienda',
            'sector': '',
            'project_type': '',
            'fiscal_code': '',
            'vat_number': '',
            'notes': f"Importato da Ricerca Aziende | ricerca: {(row.get('search_term') or '').strip()} | fonte: {(row.get('source_name') or '').strip()}",
        }
        new_contact_id = ContactRepository().create_contact(payload, user_id)
        self.delete_result(result_id, user_id)
        log_audit(user_id, 'move', 'company_search_results', result_id, f'to_contact#{new_contact_id}')
        return new_contact_id

    def _fingerprint(
        self,
        search_term: str | None,
        company: str | None,
        phone: str | None,
        address: str | None,
        province: str | None,
    ) -> str:
        raw = '|'.join(
            [
                (search_term or '').strip().lower(),
                (company or '').strip().lower(),
                (phone or '').strip().lower(),
                (address or '').strip().lower(),
                (province or '').strip().lower(),
            ]
        )
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class AppointmentRepository:
    def list_by_date(self, appointment_date: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM appointments
                WHERE appointment_date = ?
                ORDER BY start_time ASC, id ASC
                """,
                (appointment_date,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_appointment(self, appointment_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute('SELECT * FROM appointments WHERE id = ?', (appointment_id,)).fetchone()
            return dict(row) if row else None

    def create_appointment(self, payload: dict[str, Any], user_id: int) -> int:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO appointments(subject_type, subject_id, subject_name, appointment_date, start_time, end_time, appointment_type, outcome, notes, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get('subject_type'),
                    payload.get('subject_id'),
                    payload.get('subject_name'),
                    payload.get('appointment_date'),
                    payload.get('start_time'),
                    payload.get('end_time'),
                    payload.get('appointment_type'),
                    payload.get('outcome'),
                    payload.get('notes'),
                    user_id,
                ),
            )
            aid = int(cur.lastrowid)
        log_audit(user_id, 'create', 'appointment', aid, payload.get('subject_name', ''))
        return aid

    def update_appointment(self, appointment_id: int, payload: dict[str, Any], user_id: int) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE appointments
                SET subject_type=?, subject_id=?, subject_name=?, appointment_date=?, start_time=?, end_time=?, appointment_type=?, outcome=?, notes=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (
                    payload.get('subject_type'),
                    payload.get('subject_id'),
                    payload.get('subject_name'),
                    payload.get('appointment_date'),
                    payload.get('start_time'),
                    payload.get('end_time'),
                    payload.get('appointment_type'),
                    payload.get('outcome'),
                    payload.get('notes'),
                    appointment_id,
                ),
            )
        log_audit(user_id, 'update', 'appointment', appointment_id)

    def delete_appointment(self, appointment_id: int, user_id: int) -> None:
        with get_connection() as conn:
            conn.execute('DELETE FROM appointments WHERE id=?', (appointment_id,))
        log_audit(user_id, 'delete', 'appointment', appointment_id)


class AuditRepository:
    def list_logs(self, page: int = 1, page_size: int = 50) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * page_size
        with get_connection() as conn:
            total = conn.execute('SELECT COUNT(*) as c FROM audit_logs').fetchone()['c']
            rows = conn.execute(
                """
                SELECT a.*, u.username
                FROM audit_logs a
                LEFT JOIN users u ON u.id = a.user_id
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT ? OFFSET ?
                """,
                (page_size, offset),
            ).fetchall()
        return [dict(r) for r in rows], int(total)
