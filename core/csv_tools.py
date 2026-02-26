from __future__ import annotations

import csv
from pathlib import Path

from db.connection import get_connection
from db.repository import ClientRepository
from db.repository import SiteRepository
from models.entities import SitePayload


def load_csv_headers(file_path: Path) -> list[str]:
    with file_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or []


def import_sites_csv(file_path: Path, column_map: dict[str, str], user_id: int, data_key: bytes) -> int:
    repo = SiteRepository()
    imported = 0
    with file_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ftp_port_raw = row.get(column_map.get('ftp_port', ''), '22') or '22'
            db_port_raw = row.get(column_map.get('db_port', ''), '3306') or '3306'
            payload = SitePayload(
                client_name=row.get(column_map.get('client_name', ''), ''),
                domain=row.get(column_map.get('domain', ''), '').strip().lower(),
                provider=row.get(column_map.get('provider', ''), ''),
                tags=row.get(column_map.get('tags', ''), ''),
                notes=row.get(column_map.get('notes', ''), ''),
                hosting_panel=row.get(column_map.get('hosting_panel', ''), ''),
                hosting_login_url=row.get(column_map.get('hosting_login_url', ''), ''),
                hosting_username=row.get(column_map.get('hosting_username', ''), ''),
                hosting_password=row.get(column_map.get('hosting_password', ''), ''),
                hosting_notes=row.get(column_map.get('hosting_notes', ''), ''),
                ftp_protocol=row.get(column_map.get('ftp_protocol', ''), 'sftp'),
                ftp_host=row.get(column_map.get('ftp_host', ''), ''),
                ftp_port=int(ftp_port_raw) if str(ftp_port_raw).isdigit() else 22,
                ftp_username=row.get(column_map.get('ftp_username', ''), ''),
                ftp_password=row.get(column_map.get('ftp_password', ''), ''),
                ftp_root_path=row.get(column_map.get('ftp_root_path', ''), ''),
                ftp_notes=row.get(column_map.get('ftp_notes', ''), ''),
                db_host=row.get(column_map.get('db_host', ''), ''),
                db_port=int(db_port_raw) if str(db_port_raw).isdigit() else 3306,
                db_name=row.get(column_map.get('db_name', ''), ''),
                db_username=row.get(column_map.get('db_username', ''), ''),
                db_password=row.get(column_map.get('db_password', ''), ''),
                expiry_date=row.get(column_map.get('expiry_date', ''), ''),
            )
            if payload.domain:
                repo.create_site(payload, user_id, data_key)
                imported += 1
    return imported


def export_sites_csv(file_path: Path, data_key: bytes, include_sensitive: bool = False) -> int:
    repo = SiteRepository()
    rows, _ = repo.list_sites(page=1, page_size=100000, sort_key='domain_asc')
    fieldnames = [
        'client_name',
        'domain',
        'provider',
        'expiry_date',
        'tags',
        'notes',
        'hosting_panel',
        'hosting_login_url',
        'hosting_username',
        'hosting_password',
        'hosting_notes',
        'ftp_protocol',
        'ftp_host',
        'ftp_port',
        'ftp_username',
        'ftp_password',
        'ftp_root_path',
        'ftp_notes',
        'db_host',
        'db_port',
        'db_name',
        'db_username',
        'db_password',
    ]
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            full = repo.get_site(row['id'], data_key, include_sensitive=include_sensitive)
            if not full:
                continue
            writer.writerow({k: full.get(k, '') for k in fieldnames})
    return len(rows)


def import_sites_csv_standard(file_path: Path, user_id: int, data_key: bytes) -> int:
    column_map = {
        'client_name': 'client_name',
        'domain': 'domain',
        'provider': 'provider',
        'expiry_date': 'expiry_date',
        'tags': 'tags',
        'notes': 'notes',
        'hosting_panel': 'hosting_panel',
        'hosting_login_url': 'hosting_login_url',
        'hosting_username': 'hosting_username',
        'hosting_password': 'hosting_password',
        'hosting_notes': 'hosting_notes',
        'ftp_protocol': 'ftp_protocol',
        'ftp_host': 'ftp_host',
        'ftp_port': 'ftp_port',
        'ftp_username': 'ftp_username',
        'ftp_password': 'ftp_password',
        'ftp_root_path': 'ftp_root_path',
        'ftp_notes': 'ftp_notes',
        'db_host': 'db_host',
        'db_port': 'db_port',
        'db_name': 'db_name',
        'db_username': 'db_username',
        'db_password': 'db_password',
    }
    return import_sites_csv(file_path, column_map, user_id, data_key)


def export_clients_csv(file_path: Path) -> int:
    return _export_people_csv(file_path, 'clients')


def export_contacts_csv(file_path: Path) -> int:
    return _export_people_csv(file_path, 'contacts')


def _export_people_csv(file_path: Path, table: str) -> int:
    fieldnames = [
        'name',
        'client_type',
        'company',
        'contact_role',
        'sector',
        'project_type',
        'email',
        'phone',
        'landline_phone',
        'region',
        'province',
        'city',
        'municipality',
        'address',
        'fiscal_code',
        'vat_number',
        'notes',
    ]
    with get_connection() as conn:
        rows = conn.execute(f'SELECT * FROM {table} ORDER BY name').fetchall()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            data = dict(row)
            writer.writerow({k: data.get(k, '') for k in fieldnames})
    return len(rows)


def import_clients_csv_standard(file_path: Path, user_id: int) -> int:
    repo = ClientRepository()
    return _import_people_csv_standard(file_path, user_id, repo.create_client)


def import_contacts_csv_standard(file_path: Path, user_id: int) -> int:
    from db.repository import ContactRepository

    repo = ContactRepository()
    return _import_people_csv_standard(file_path, user_id, repo.create_contact)


def _import_people_csv_standard(file_path: Path, user_id: int, create_fn) -> int:
    imported = 0
    with file_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get('name') or '').strip()
            if not name:
                continue
            payload = {
                'name': name,
                'client_type': (row.get('client_type') or 'Privato').strip() or 'Privato',
                'company': (row.get('company') or '').strip(),
                'contact_role': (row.get('contact_role') or '').strip(),
                'sector': (row.get('sector') or 'Commercio & distribuzione').strip() or 'Commercio & distribuzione',
                'project_type': (row.get('project_type') or 'Sito web aziendale').strip() or 'Sito web aziendale',
                'email': (row.get('email') or '').strip(),
                'phone': (row.get('phone') or '').strip(),
                'landline_phone': (row.get('landline_phone') or '').strip(),
                'region': (row.get('region') or '').strip(),
                'province': (row.get('province') or '').strip(),
                'city': (row.get('city') or '').strip(),
                'municipality': (row.get('municipality') or '').strip(),
                'address': (row.get('address') or '').strip(),
                'fiscal_code': (row.get('fiscal_code') or '').strip(),
                'vat_number': (row.get('vat_number') or '').strip(),
                'notes': (row.get('notes') or '').strip(),
            }
            create_fn(payload, user_id)
            imported += 1
    return imported
