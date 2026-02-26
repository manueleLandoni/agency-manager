from __future__ import annotations

from db.connection import get_connection


class SettingsService:
    def get_value(self, key: str, default: str = '') -> str:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return default
            return str(row['value'])

    def set_value(self, key: str, value: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO app_settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_int_value(self, key: str, default: int, min_value: int, max_value: int) -> int:
        raw = self.get_value(key, str(default))
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, min(value, max_value))

    def get_inactivity_minutes(self) -> int:
        return self.get_int_value('inactivity_minutes', default=10, min_value=1, max_value=240)

    def set_inactivity_minutes(self, minutes: int) -> None:
        safe = max(1, min(minutes, 240))
        self.set_value('inactivity_minutes', str(safe))
