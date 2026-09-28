from __future__ import annotations

import re
import time
import webbrowser
from urllib.parse import urlparse

from .brain import Decision
from .config import Settings


def execute(decision: Decision, settings: Settings) -> str:
    """Never execute generated code or arbitrary URLs with non-web schemes."""
    match decision.action:
        case "talk":
            return "Ответ готов"
        case "open_url":
            url = decision.details.strip()
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                return "Ссылка отклонена: нужен полный http(s) URL"
            if len(url) > 2048 or re.search(r"[\s\x00-\x1f]", url):
                return "Ссылка отклонена: неверные символы"
            return "Сайт открыт" if webbrowser.open(url) else "Не удалось открыть браузер"
        case "type_text":
            value = decision.details
            if not value or len(value) > 1000:
                return "Текст пустой или слишком длинный"
            import pyautogui
            import pyperclip
            previous = pyperclip.paste()
            try:
                pyperclip.copy(value)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.15)
            finally:
                pyperclip.copy(previous)
            return "Текст вставлен в активное окно"
        case "msi_turbo" | "msi_silent":
            if not settings.msi_enabled:
                return "MSI: настрой координаты и включи интеграцию в config.toml"
            point = settings.msi_turbo_xy if decision.action == "msi_turbo" else settings.msi_silent_xy
            if point == (0, 0):
                return "MSI: укажи координаты кнопки в config.toml"
            import pyautogui
            import ctypes
            import os
            if settings.msi_launch_uri:
                os.startfile(settings.msi_launch_uri)
                time.sleep(settings.msi_open_delay)
            foreground = ctypes.windll.user32.GetForegroundWindow()
            title = ctypes.create_unicode_buffer(512)
            ctypes.windll.user32.GetWindowTextW(foreground, title, len(title))
            if settings.msi_window_title.lower() not in title.value.lower():
                return f"MSI: открой {settings.msi_window_title} на переднем плане"
            pyautogui.click(*point)
            return "MSI: нажата кнопка Turbo" if decision.action == "msi_turbo" else "MSI: нажата кнопка Silent"
    raise ValueError("Неизвестное действие")
