from __future__ import annotations

from pathlib import Path
import unittest

from core.auth import AuthService
from db.connection import DB_FILE
from db.migration import run_migrations
from db.repository import SiteRepository
from models.entities import SitePayload


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        if DB_FILE.exists():
            DB_FILE.unlink()
        run_migrations()
        self.auth = AuthService()
        self.auth.ensure_default_admin()
        self.user = self.auth.login('admin', 'admin123!')
        self.repo = SiteRepository()

    def test_site_crud_roundtrip(self):
        payload = SitePayload(
            client_name='Cliente Test',
            domain='example.com',
            provider='ProviderX',
            tags='wp,critical',
            notes='note',
            hosting_panel='cPanel',
            hosting_login_url='https://example.com:2083',
            hosting_username='host_user',
            hosting_password='host_pass',
            hosting_notes='h-note',
            ftp_protocol='sftp',
            ftp_host='ftp.example.com',
            ftp_port=22,
            ftp_username='ftp_user',
            ftp_password='ftp_pass',
            ftp_root_path='/public_html',
            ftp_notes='f-note',
            db_host='localhost',
            db_port=3306,
            db_name='db1',
            db_username='db_user',
            db_password='db_pass',
        )

        site_id = self.repo.create_site(payload, self.user.id, self.user.data_key)
        loaded = self.repo.get_site(site_id, self.user.data_key)

        self.assertEqual(loaded['domain'], 'example.com')
        self.assertEqual(loaded['hosting_password'], 'host_pass')
        self.assertEqual(loaded['ftp_password'], 'ftp_pass')
        self.assertEqual(loaded['db_password'], 'db_pass')


if __name__ == '__main__':
    unittest.main()
