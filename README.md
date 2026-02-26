# Agency Manager (Desktop, Python + Flet)

Gestionale locale per agenzia hosting con UI desktop (Flet), SQLite locale e cifratura per-field dei campi sensibili.

## Funzionalita incluse (versione corrente)
- Login locale con username/password (Argon2).
- Opzione `Ricordami` con token revocabile su logout.
- Chiave dati app cifrata per utente (wrapping con chiave derivata da password + salt Argon2).
- Cifratura per-field (`encrypt_field()` / `decrypt_field()`) su credenziali hosting/FTP/DB.
- Auto-lock per inattivita configurabile (default 10 min).
- Sezione `Siti` completa:
  - tabella con ricerca, filtro provider, paginazione (50 righe)
  - CRUD (nuovo, modifica, visualizza, duplica, elimina)
  - validazioni base (dominio, porte)
  - copy username/password con pulizia clipboard dopo 20 secondi
- Sezione `Clienti` completa (CRUD + ricerca + paginazione).
- Scadenza direttamente nei `Siti`:
  - campo data scadenza nel form sito
  - giorni rimanenti e badge stato in tabella siti
- Gestione utenti locale (solo Admin):
  - creazione utenti Admin/Operatore
  - policy `can_view_passwords`
  - attivazione/disattivazione account
- Audit log locale base (create/update/delete sito).
- Viewer audit log in `Impostazioni` (ultimi eventi).
- Migrazioni SQLite con `schema_version` e indici su campi di ricerca principali.
- Backup locale automatico (rotazione ultimi 10) + export/import backup cifrato con password.
- Test unitari per crittografia e repository.

## Struttura progetto
- `app/` UI Flet (views, componenti, routing)
- `core/` auth, crypto, settings, backup, clipboard, inactivity
- `db/` connessione, migrazioni, repository, seed
- `models/` dataclass dei payload
- `tests/` test crittografia/repository
- `main.py` entrypoint

## Requisiti
- Python 3.11+

## Setup rapido
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Avvio
```powershell
python main.py
```

Credenziali primo avvio demo:
- username: `admin`
- password: `admin123!`

## Test
```powershell
python -m unittest discover -s tests
```

## Backup / Export / Import
- Backup automatico: creato all'avvio in `backups/` (mantiene ultimi 10 file).
- Export cifrato: sezione `Backup`, imposta file (es. `backup.ambak`) + password.
- Import cifrato: stessa sezione, stesso file + password.
- Import CSV con mapping colonne via UI: sezione `Backup` -> `Import CSV con mapping colonne`.

## CSV Import
Nel modulo `core/csv_tools.py` sono disponibili:
- `load_csv_headers(...)`
- `import_sites_csv(...)`

Esempio mapping:
```python
mapping = {
    'client_name': 'Cliente',
    'domain': 'Dominio',
    'provider': 'Provider',
    'hosting_username': 'HostingUser',
    'hosting_password': 'HostingPass',
}
```

## Build desktop (opzionale)
Con Flet CLI:
```powershell
flet pack main.py --name "Agency Manager"
```

## Note sicurezza
- Nessuna password utente in chiaro: solo hash Argon2.
- Campi sensibili cifrati singolarmente nel DB.
- Token `Ricordami` revocato su logout.
- Clipboard password pulita dopo 20 secondi.

## Limiti e prossime estensioni consigliate
- CRUD UI completo per Email account e Servizi/Abbonamenti ancora da aggiungere.
- Audit log avanzato con filtri, export e ricerca full-text.
