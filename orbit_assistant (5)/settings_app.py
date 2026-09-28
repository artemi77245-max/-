"""Orbit Settings: a separate, full GUI for the Windows assistant."""

from __future__ import annotations

import math
import os
import subprocess
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from orbit.config import DATA_ROOT, FROZEN, ROOT, read_config, read_keys, write_config, write_keys


STYLE = """
QWidget { background: #101115; color: #f4f4f6; font: 12px 'Segoe UI'; }
QLabel { background: transparent; }
QMainWindow { background: #101115; }
QFrame#sidebar { background: #17181e; border-right: 1px solid #282a31; }
QFrame#card { background: #1c1e25; border: 1px solid #30323a; border-radius: 20px; }
QLabel#overline { color: #82858f; font-size: 10px; font-weight: 700; letter-spacing: 1.5px; }
QLabel#title { color: #f6f6f8; font-size: 29px; font-weight: 700; }
QLabel#cardTitle { color: #f3f4f7; font-size: 16px; font-weight: 650; }
QLabel#subtle { color: #a3a6b1; line-height: 140%; }
QLabel#success { color: #a6e1bc; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #292b34; color: #f8f8fb; border: 1px solid #393c46;
    border-radius: 10px; padding: 9px 11px; min-height: 19px;
    selection-background-color: #696cf5;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #a7a8ff; }
QComboBox::drop-down { border: 0; width: 26px; }
QComboBox QAbstractItemView { background: #24262e; color: #f7f7fa; selection-background-color: #444757; }
QCheckBox { spacing: 12px; background: transparent; padding: 4px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #595b65; border-radius: 5px; background: #292b34; }
QCheckBox::indicator:checked { border-color: #a4a5fb; background: #797bf0; }
QPushButton { background: #292b34; border: 1px solid #3b3d46; border-radius: 11px;
    min-height: 20px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #343641; }
QPushButton#primary { color: #101116; background: #d8d8ff; border-color: #d8d8ff; }
QPushButton#primary:hover { background: #f1f0ff; }
QPushButton#nav { text-align: left; padding: 11px 14px; margin: 1px 9px; border: 0; background: transparent; color: #adb0bb; }
QPushButton#nav:hover { background: #292b32; color: white; }
QPushButton#nav:checked { background: #32343e; color: white; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #42444e; border-radius: 4px; min-height: 35px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class Spark(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#ebeaff"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(16, 3, 16, 29)
        p.drawLine(3, 16, 29, 16)
        p.drawLine(7, 7, 25, 25)
        p.drawLine(25, 7, 7, 25)


class Preview(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.position = "TOP"
        self.setMinimumHeight(196)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        p.setPen(QPen(QColor("#343744"), 1))
        p.setBrush(QColor("#14161c"))
        p.drawRoundedRect(r, 16, 16)
        p.setPen(QPen(QColor("#31343d"), 1))
        p.setBrush(QColor("#22252d"))
        screen = r.adjusted(35, 26, -35, -26)
        p.drawRoundedRect(screen, 13, 13)
        island_w, island_h = (142, 29) if self.position in {"TOP", "BOTTOM"} else (65, 108)
        x = screen.center().x() - island_w // 2
        y = screen.top() + 7 if self.position == "TOP" else (screen.bottom() - island_h - 7 if self.position == "BOTTOM" else screen.center().y() - island_h // 2)
        if self.position == "LEFT":
            x = screen.left() + 7
        elif self.position == "RIGHT":
            x = screen.right() - island_w - 7
        p.setBrush(QColor("#060609"))
        p.setPen(QPen(QColor("#373843"), 1))
        p.drawRoundedRect(x, y, island_w, island_h, 14, 14)
        if island_w > 100:
            p.setPen(QPen(QColor("#e7e5fa"), 1.5))
            p.drawLine(x + 17, y + 9, x + 17, y + 20)
            p.drawLine(x + 11, y + 14, x + 23, y + 14)
            p.setPen(QColor("#ebebf3"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(x + 35, y + 19, "Слушаю")
            for i in range(9):
                h = 4 + int(8 * (0.5 + 0.5 * math.sin(i * 1.7)))
                p.drawLine(x + 105 + 3 * i, y + 14 - h // 2, x + 105 + 3 * i, y + 14 + h // 2)
        else:
            p.setPen(QColor("#d9d9e0"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(x + 10, y + 24, "ORBIT")


class Signals(QObject):
    done = pyqtSignal(str)
    error = pyqtSignal(str)


def label(text: str, *, subtle: bool = False, title: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setWordWrap(True)
    widget.setObjectName("cardTitle" if title else "subtle" if subtle else "")
    return widget


def field_caption(text: str) -> QLabel:
    caption = label(text, subtle=True)
    caption.setMinimumWidth(175)
    return caption


class SettingsWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = read_config()
        self.keys = read_keys()
        self.signals = Signals()
        self.signals.done.connect(self._background_done)
        self.signals.error.connect(self._background_error)
        self.setWindowTitle("Orbit · Настройки")
        self.setMinimumSize(910, 675)
        self.resize(1080, 760)
        self.setStyleSheet(STYLE)
        shell = QWidget()
        self.setCentralWidget(shell)
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(226)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(13, 28, 13, 23)
        brand = QHBoxLayout()
        brand.setSpacing(9)
        brand.addWidget(Spark())
        title = label("ORBIT", title=True)
        title.setStyleSheet("font-size: 19px; font-weight: 700; letter-spacing: 2px;")
        brand.addWidget(title)
        brand.addStretch()
        side.addLayout(brand)
        subtitle = label("НАСТРОЙКИ ПОМОЩНИКА", subtle=True)
        subtitle.setStyleSheet("color: #888b99; font-size: 9px; letter-spacing: 1px; padding-left: 6px;")
        side.addWidget(subtitle)
        side.addSpacing(40)
        self.stack = QStackedWidget()
        self.nav: list[QPushButton] = []
        for index, (name, build) in enumerate((
            ("Обзор", self._overview), ("Микрофон", self._voice),
            ("ИИ и голос", self._ai), ("Действия", self._actions),
            ("Игровой режим", self._games),
        )):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked, i=index: self._navigate(i))
            side.addWidget(button)
            self.nav.append(button)
            self.stack.addWidget(self._page(build))
        self._navigate(0)
        side.addStretch()
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: #30313a;")
        side.addWidget(line)
        side.addSpacing(12)
        self.start_button = QPushButton("▶  Запустить помощника")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_assistant)
        side.addWidget(self.start_button)
        stop = QPushButton("Остановить помощника")
        stop.clicked.connect(self.stop_assistant)
        side.addWidget(stop)
        log_button = QPushButton("Открыть журнал ошибок")
        log_button.clicked.connect(self.open_log)
        side.addWidget(log_button)
        side.addSpacing(8)
        side.addWidget(label("Фоновый помощник закрывается во время игры.", subtle=True))
        layout.addWidget(sidebar)

        content = QWidget()
        c = QVBoxLayout(content)
        c.setContentsMargins(38, 31, 38, 24)
        c.setSpacing(17)
        c.addWidget(self.stack, 1)
        foot = QHBoxLayout()
        self.notice = label("Настройки сохраняются на этом компьютере.", subtle=True)
        foot.addWidget(self.notice, 1)
        save = QPushButton("Сохранить изменения")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        foot.addWidget(save)
        c.addLayout(foot)
        layout.addWidget(content, 1)

    def _navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self.nav):
            button.setChecked(i == index)

    def _page(self, build) -> QWidget:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 2, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(2, 0, 10, 10)
        body_layout.setSpacing(16)
        build(body_layout)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        container_layout.addWidget(scroll)
        return container

    def _heading(self, parent: QVBoxLayout, overline: str, name: str, description: str) -> None:
        eyebrow = label(overline)
        eyebrow.setObjectName("overline")
        parent.addWidget(eyebrow)
        title = label(name)
        title.setObjectName("title")
        parent.addWidget(title)
        parent.addWidget(label(description, subtle=True))
        parent.addSpacing(9)

    def _card(self, parent: QVBoxLayout, name: str, description: str = "") -> QVBoxLayout:
        frame = QFrame()
        frame.setObjectName("card")
        card = QVBoxLayout(frame)
        card.setContentsMargins(23, 22, 23, 22)
        card.setSpacing(15)
        card.addWidget(label(name, title=True))
        if description:
            card.addWidget(label(description, subtle=True))
        parent.addWidget(frame)
        return card

    def _row(self, parent: QVBoxLayout, name: str, widget: QWidget) -> None:
        row = QHBoxLayout()
        row.addWidget(field_caption(name))
        row.addWidget(widget, 1)
        parent.addLayout(row)

    def _edit(self, section: str, key: str, placeholder: str = "") -> QLineEdit:
        value = QLineEdit(str(self.config.get(section, {}).get(key, "")))
        value.setPlaceholderText(placeholder)
        return value

    def _overview(self, root: QVBoxLayout) -> None:
        self._heading(root, "ORBIT  /  01", "Твой помощник", "Компактный интерфейс, который появляется, только когда ты к нему обращаешься.")
        card = self._card(root, "Островок", "Положение интерфейса на основном экране")
        self.preview = Preview()
        card.addWidget(self.preview)
        self.position = QComboBox()
        for name, value in (("Сверху", "TOP"), ("Снизу", "BOTTOM"), ("Слева", "LEFT"), ("Справа", "RIGHT")):
            self.position.addItem(name, value)
        index = self.position.findData(self.config.get("ui", {}).get("position", "TOP"))
        self.position.setCurrentIndex(max(0, index))
        self.preview.position = self.position.currentData()
        self.position.currentIndexChanged.connect(lambda: (setattr(self.preview, "position", self.position.currentData()), self.preview.update()))
        self._row(card, "Положение", self.position)
        demo = QPushButton("Посмотреть анимацию")
        demo.clicked.connect(self.launch_demo)
        card.addWidget(demo)
        card.addWidget(label("Демо использует микрофон, но не отправляет запросы и не выполняет макросы.", subtle=True))

    def _voice(self, root: QVBoxLayout) -> None:
        self._heading(root, "ORBIT  /  02", "Микрофон", "Распознавание работает на устройстве. Голосовой образец хранится локально.")
        card = self._card(root, "Звук и устройства")
        self.device = QComboBox()
        self.device.addItem("Системный микрофон", None)
        try:
            import sounddevice as sd
            for index, info in enumerate(sd.query_devices()):
                if info["max_input_channels"] > 0:
                    self.device.addItem(f"{index} · {info['name']}", index)
        except Exception:
            self.device.addItem("Устройства недоступны — будет использован системный", None)
        selected = self.device.findData(self.config.get("audio", {}).get("input_device"))
        self.device.setCurrentIndex(max(0, selected))
        self._row(card, "Микрофон", self.device)
        self.noise = QCheckBox("Убирать тихие фоновые звуки")
        self.noise.setChecked(self.config.get("audio", {}).get("noise_reduction", True))
        card.addWidget(self.noise)
        card.addWidget(label("Один микрофон не отделит твою речь от громкого телевизора, если вы говорите одновременно.", subtle=True))
        lock = self._card(root, "Только мой голос", "Проверка говорящего с отдельной моделью Vosk. Короткие команды иногда отклоняются.")
        self.voice_lock = QCheckBox("Проверять голос перед выполнением команды")
        self.voice_lock.setChecked(self.config.get("audio", {}).get("voice_lock", False))
        lock.addWidget(self.voice_lock)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.05, .90)
        self.threshold.setSingleStep(.02)
        self.threshold.setDecimals(2)
        self.threshold.setValue(float(self.config.get("audio", {}).get("voice_threshold", .38)))
        self._row(lock, "Порог совпадения", self.threshold)
        enroll_button = QPushButton("Скачать модели и записать мой голос")
        enroll_button.clicked.connect(self.enroll_voice)
        lock.addWidget(enroll_button)
        lock.addWidget(label("Перед записью выключи телевизор и говори непрерывно 10 секунд. Загрузка моделей может занять несколько минут.", subtle=True))

    def _ai(self, root: QVBoxLayout) -> None:
        self._heading(root, "ORBIT  /  03", "ИИ и голос", "Подключи одного провайдера для ответов. Ключи хранятся локально без шифрования.")
        card = self._card(root, "Нейросеть")
        self.provider = QComboBox()
        self.provider.addItem("Google Gemini", "gemini")
        self.provider.addItem("OpenAI", "openai")
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.config.get("ai", {}).get("provider", "gemini"))))
        self._row(card, "Провайдер", self.provider)
        self.gemini_model = self._edit("ai", "gemini_model")
        self.openai_model = self._edit("ai", "openai_model")
        self._row(card, "Модель Gemini", self.gemini_model)
        self._row(card, "Модель OpenAI", self.openai_model)
        self.gemini_key = self._key("GEMINI_API_KEY")
        self.openai_key = self._key("OPENAI_API_KEY")
        self._row(card, "Ключ Gemini", self.gemini_key)
        self._row(card, "Ключ OpenAI", self.openai_key)
        voice = self._card(root, "Озвучка", "Fish Audio → Edge TTS → системный голос Windows")
        self.fish_key = self._key("FISH_API_KEY")
        self._row(voice, "Ключ Fish Audio", self.fish_key)
        self.fish_voice = self._edit("fish", "voice_id", "reference_id голоса")
        self._row(voice, "ID голоса Fish", self.fish_voice)

    def _key(self, name: str) -> QLineEdit:
        edit = QLineEdit(self.keys.get(name, ""))
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("Вставь API-ключ")
        return edit

    def _actions(self, root: QVBoxLayout) -> None:
        self._heading(root, "ORBIT  /  04", "Действия", "Сайты, вставка текста и переключение профилей MSI Center.")
        card = self._card(root, "MSI Center", "Разрешай клики после того, как укажешь координаты на своём экране.")
        self.msi_enabled = QCheckBox("Разрешить управление MSI Center")
        self.msi_enabled.setChecked(self.config.get("msi", {}).get("enabled", False))
        card.addWidget(self.msi_enabled)
        self.points: dict[str, tuple[QSpinBox, QSpinBox]] = {}
        for action, caption in (("turbo_xy", "Турбо (X / Y)"), ("silent_xy", "Тихий (X / Y)")):
            row = QHBoxLayout()
            row.addWidget(field_caption(caption))
            values = self.config.get("msi", {}).get(action, [0, 0])
            coords = []
            for value in values:
                spin = QSpinBox()
                spin.setRange(0, 16384)
                spin.setValue(int(value))
                row.addWidget(spin, 1)
                coords.append(spin)
            card.addLayout(row)
            self.points[action] = (coords[0], coords[1])
        self.msi_uri = self._edit("msi", "launch_uri", "Необязательно")
        self.msi_title = self._edit("msi", "window_title", "MSI Center")
        self._row(card, "Путь запуска", self.msi_uri)
        self._row(card, "Заголовок окна", self.msi_title)
        card.addWidget(label("Клик выполняется только если открыто окно с нужным заголовком. Профиль в MSI Center проверь после команды.", subtle=True))

    def _games(self, root: QVBoxLayout) -> None:
        self._heading(root, "ORBIT  /  05", "Игровой режим", "Пока игра запущена, распознавание и островок выгружаются из памяти.")
        card = self._card(root, "Список игр", "Впиши точные имена процессов с расширением .exe, через запятую.")
        current = self.config.get("games", {}).get("executables", [])
        self.games = QLineEdit(", ".join(current))
        self.games.setPlaceholderText("cs2.exe, valorant-win64-shipping.exe")
        card.addWidget(self.games)
        card.addWidget(label("Процессы проверяются раз в 5 секунд. Помощник автоматически запустится вновь после выхода из игры.", subtle=True))

    def save(self) -> bool:
        try:
            values = self.config
            values.setdefault("ui", {})["position"] = self.position.currentData()
            audio = values.setdefault("audio", {})
            if self.device.currentData() is None:
                audio.pop("input_device", None)
            else:
                audio["input_device"] = self.device.currentData()
            audio["noise_reduction"] = self.noise.isChecked()
            audio["voice_lock"] = self.voice_lock.isChecked()
            audio["voice_threshold"] = self.threshold.value()
            values.setdefault("ai", {}).update(provider=self.provider.currentData(),
                                                  gemini_model=self.gemini_model.text().strip(),
                                                  openai_model=self.openai_model.text().strip())
            values.setdefault("fish", {})["voice_id"] = self.fish_voice.text().strip()
            msi = values.setdefault("msi", {})
            msi["enabled"] = self.msi_enabled.isChecked()
            for name, coords in self.points.items():
                msi[name] = [field.value() for field in coords]
            msi["launch_uri"] = self.msi_uri.text().strip()
            msi["window_title"] = self.msi_title.text().strip()
            values.setdefault("games", {})["executables"] = [part.strip().lower() for part in self.games.text().split(",") if part.strip()]
            if any(not game.endswith(".exe") for game in values["games"]["executables"]):
                raise ValueError("Имена игровых процессов должны заканчиваться на .exe")
            if msi["enabled"] and (msi["turbo_xy"] == [0, 0] or msi["silent_xy"] == [0, 0]):
                raise ValueError("Для MSI Center укажи координаты обеих кнопок")
            if audio["voice_lock"] and not (DATA_ROOT / audio.get("voiceprint_path", "voiceprint.json")).is_file():
                raise ValueError("Сначала запиши голос, затем включи проверку говорящего")
            keys = {"GEMINI_API_KEY": self.gemini_key.text().strip(),
                    "OPENAI_API_KEY": self.openai_key.text().strip(), "FISH_API_KEY": self.fish_key.text().strip()}
            if self.provider.currentData() == "gemini" and not keys["GEMINI_API_KEY"]:
                self.notice.setText("Демо работает без ключа. Для ответов добавь ключ Gemini.")
            elif self.provider.currentData() == "openai" and not keys["OPENAI_API_KEY"]:
                self.notice.setText("Демо работает без ключа. Для ответов добавь ключ OpenAI.")
            else:
                self.notice.setText("Сохранено. Перезапусти помощника для применения настроек.")
            write_config(values)
            write_keys(keys)
            return True
        except Exception as exc:
            QMessageBox.warning(self, "Настройки не сохранены", str(exc))
            return False

    def _assistant_command(self, demo: bool = False) -> list[str]:
        if FROZEN:
            executable = Path(sys.executable).with_name("Orbit Assistant.exe")
            if not executable.is_file():
                raise FileNotFoundError("Рядом с конфигуратором не найден Orbit Assistant.exe")
            return [str(executable), "--demo"] if demo else [str(executable)]
        path = Path(__file__).with_name("assistant_app.py")
        return [sys.executable, str(path), "--demo"] if demo else [sys.executable, str(path)]

    def launch_demo(self) -> None:
        if self.save():
            try:
                subprocess.Popen(self._assistant_command(demo=True), cwd=str(DATA_ROOT))
            except Exception as exc:
                QMessageBox.warning(self, "Не удалось открыть демо", str(exc))

    def start_assistant(self) -> None:
        if not self.save():
            return
        try:
            pid_file = DATA_ROOT / "assistant.pid"
            if pid_file.is_file():
                import psutil
                pid = int(pid_file.read_text(encoding="ascii"))
                if psutil.pid_exists(pid):
                    existing = psutil.Process(pid)
                    command_line = existing.cmdline()
                    if (FROZEN and Path(existing.exe()) == Path(self._assistant_command()[0])) or (
                        not FROZEN and any("assistant_app.py" in item for item in command_line)
                    ):
                        QMessageBox.information(self, "Orbit", "Помощник уже запущен")
                        return
            command = self._assistant_command()
            (DATA_ROOT / "stop.flag").unlink(missing_ok=True)
            flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
            subprocess.Popen(command, cwd=str(DATA_ROOT), creationflags=flags,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notice.setText("Помощник запущен. Скажи «Джарвис» или «Компьютер».")
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось запустить", str(exc))

    def stop_assistant(self) -> None:
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        (DATA_ROOT / "stop.flag").touch()
        self.notice.setText("Останавливаю помощника — обычно это занимает до 5 секунд.")

    def open_log(self) -> None:
        path = DATA_ROOT / "orbit.log"
        if path.exists() and os.name == "nt":
            os.startfile(path)
        else:
            QMessageBox.information(self, "Orbit", f"Журнала пока нет: {path}")

    def enroll_voice(self) -> None:
        self.notice.setText("Загружаю модели. Затем 10 секунд говори без пауз в микрофон…")

        def job() -> None:
            try:
                from orbit.models import install
                from orbit.voiceprint import enroll
                from orbit.config import load_settings
                install("speech")
                install("speaker")
                enroll(load_settings())
                self.signals.done.emit("Голос записан. Теперь включи проверку говорящего и сохрани настройки.")
            except Exception as exc:
                self.signals.error.emit(str(exc))

        threading.Thread(target=job, daemon=True, name="Voice enrollment").start()

    def _background_done(self, message: str) -> None:
        self.notice.setText(message)
        QMessageBox.information(self, "Orbit", message)

    def _background_error(self, message: str) -> None:
        self.notice.setText("Не удалось записать голос")
        QMessageBox.warning(self, "Ошибка записи", message)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Orbit Settings")
    app.setWindowIcon(QIcon(str(ROOT / "icon.ico")))
    window = SettingsWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
