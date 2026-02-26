from __future__ import annotations

from db.repository import SiteRepository
from models.entities import SitePayload


def seed_demo(user_id: int, data_key: bytes) -> None:
    repo = SiteRepository()
    payload = SitePayload(
        client_name='Acme SRL',
        domain='acme-demo.it',
        provider='SiteGround',
        tags='demo,wordpress',
        notes='Record demo',
        hosting_panel='SiteTools',
        hosting_login_url='https://my.siteground.com',
        hosting_username='demo-host-user',
        hosting_password='demo-host-pass',
        hosting_notes='',
        ftp_protocol='sftp',
        ftp_host='sftp.acme-demo.it',
        ftp_port=22,
        ftp_username='demo-ftp-user',
        ftp_password='demo-ftp-pass',
        ftp_root_path='/home/acme/public_html',
        ftp_notes='',
        db_host='127.0.0.1',
        db_port=3306,
        db_name='acme_wp',
        db_username='demo-db-user',
        db_password='demo-db-pass',
    )
    repo.create_site(payload, user_id, data_key)
