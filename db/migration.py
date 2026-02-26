from __future__ import annotations

from db.connection import get_connection

SCHEMA_VERSION = 10

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'operator')),
            can_view_passwords INTEGER NOT NULL DEFAULT 1,
            crypto_salt BLOB NOT NULL,
            wrapped_data_key BLOB NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS remember_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT,
            email TEXT,
            phone TEXT,
            tags TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            domain TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            provider TEXT,
            tags TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS hosting_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL UNIQUE,
            panel TEXT,
            login_url TEXT,
            username_enc BLOB,
            password_enc BLOB,
            notes TEXT,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS ftp_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL UNIQUE,
            protocol TEXT DEFAULT 'sftp',
            host TEXT,
            port INTEGER,
            username_enc BLOB,
            password_enc BLOB,
            root_path TEXT,
            notes TEXT,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS database_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL UNIQUE,
            host TEXT,
            port INTEGER,
            dbname TEXT,
            username_enc BLOB,
            password_enc BLOB,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS email_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            domain TEXT,
            email_user_enc BLOB,
            email_password_enc BLOB,
            smtp_host TEXT,
            smtp_port INTEGER,
            smtp_ssl INTEGER DEFAULT 1,
            imap_host TEXT,
            imap_port INTEGER,
            imap_ssl INTEGER DEFAULT 1,
            pop_host TEXT,
            pop_port INTEGER,
            pop_ssl INTEGER DEFAULT 1,
            notes TEXT,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            type TEXT NOT NULL,
            account_ref TEXT,
            username_enc BLOB,
            password_enc BLOB,
            expires_at TEXT,
            cost REAL,
            notes TEXT,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            details TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_sites_domain ON sites(domain);",
        "CREATE INDEX IF NOT EXISTS idx_sites_provider ON sites(provider);",
        "CREATE INDEX IF NOT EXISTS idx_sites_client ON sites(client_id);",
        "CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(name);",
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);",
    ],
    2: [
        "ALTER TABLE clients ADD COLUMN city TEXT;",
        "ALTER TABLE clients ADD COLUMN municipality TEXT;",
        "ALTER TABLE clients ADD COLUMN address TEXT;",
    ],
    3: [
        "ALTER TABLE clients ADD COLUMN contact_role TEXT;",
        "ALTER TABLE clients ADD COLUMN client_type TEXT;",
        "ALTER TABLE clients ADD COLUMN fiscal_code TEXT;",
        "ALTER TABLE clients ADD COLUMN vat_number TEXT;",
        "ALTER TABLE clients ADD COLUMN landline_phone TEXT;",
    ],
    4: [
        "ALTER TABLE sites ADD COLUMN expiry_date TEXT;",
        "CREATE INDEX IF NOT EXISTS idx_sites_expiry_date ON sites(expiry_date);",
        "DROP INDEX IF EXISTS idx_expirations_due_date;",
        "DROP TABLE IF EXISTS expirations;",
    ],
    5: [
        "ALTER TABLE clients ADD COLUMN region TEXT;",
        "ALTER TABLE clients ADD COLUMN province TEXT;",
        "CREATE INDEX IF NOT EXISTS idx_clients_region ON clients(region);",
        "CREATE INDEX IF NOT EXISTS idx_clients_province ON clients(province);",
    ],
    6: [
        "ALTER TABLE clients ADD COLUMN sector TEXT;",
        "ALTER TABLE clients ADD COLUMN project_type TEXT;",
    ],
    7: [
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company TEXT,
            email TEXT,
            phone TEXT,
            tags TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            city TEXT,
            municipality TEXT,
            address TEXT,
            contact_role TEXT,
            client_type TEXT,
            fiscal_code TEXT,
            vat_number TEXT,
            landline_phone TEXT,
            region TEXT,
            province TEXT,
            sector TEXT,
            project_type TEXT,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);",
        "CREATE INDEX IF NOT EXISTS idx_contacts_region ON contacts(region);",
        "CREATE INDEX IF NOT EXISTS idx_contacts_province ON contacts(province);",
    ],
    8: [
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_type TEXT NOT NULL CHECK(subject_type IN ('client', 'contact')),
            subject_id INTEGER,
            subject_name TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            appointment_type TEXT NOT NULL,
            outcome TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(appointment_date);",
        "CREATE INDEX IF NOT EXISTS idx_appointments_start_time ON appointments(start_time);",
    ],
    9: [
        """
        CREATE TABLE IF NOT EXISTS company_search_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_term TEXT NOT NULL,
            region TEXT NOT NULL,
            province TEXT NOT NULL,
            city TEXT,
            municipality TEXT,
            company TEXT NOT NULL,
            phone TEXT,
            contact_name TEXT,
            address TEXT,
            source_name TEXT,
            source_url TEXT,
            fingerprint TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(created_by) REFERENCES users(id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_company_search_results_term ON company_search_results(search_term);",
        "CREATE INDEX IF NOT EXISTS idx_company_search_results_province ON company_search_results(province);",
        "CREATE INDEX IF NOT EXISTS idx_company_search_results_created_at ON company_search_results(created_at DESC);",
    ],
    10: [
        "ALTER TABLE company_search_results ADD COLUMN distance_km REAL;",
        "CREATE INDEX IF NOT EXISTS idx_company_search_results_distance ON company_search_results(distance_km);",
    ],
}


def run_migrations() -> None:
    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')));"
        )
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"] if row and row["v"] is not None else 0

        for version in sorted(MIGRATIONS):
            if version <= current:
                continue
            for statement in MIGRATIONS[version]:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))

        conn.execute(
            "INSERT OR IGNORE INTO app_settings(key, value) VALUES ('inactivity_minutes', '10')"
        )
