from __future__ import annotations

import threading


class ClipboardManager:
    def __init__(self) -> None:
        self._timer: threading.Timer | None = None

    def copy_temporarily(self, page, value: str, seconds: int = 20) -> None:
        page.set_clipboard(value)
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(seconds, lambda: page.set_clipboard(''))
        self._timer.daemon = True
        self._timer.start()
