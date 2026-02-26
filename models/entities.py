from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SitePayload:
    client_name: str | None
    domain: str
    provider: str | None
    tags: str | None
    notes: str | None
    hosting_panel: str | None
    hosting_login_url: str | None
    hosting_username: str | None
    hosting_password: str | None
    hosting_notes: str | None
    ftp_protocol: str | None
    ftp_host: str | None
    ftp_port: int | None
    ftp_username: str | None
    ftp_password: str | None
    ftp_root_path: str | None
    ftp_notes: str | None
    db_host: str | None
    db_port: int | None
    db_name: str | None
    db_username: str | None
    db_password: str | None
    expiry_date: str | None = None
