"""Small, quiet island UI. The window is absent until the wake word is heard."""
from __future__ import annotations

import math
from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QScrollArea, QWidget

INK = QColor(10, 10, 12, 250)
WHITE = QColor(249, 249, 251)
SUBTLE = QColor(166, 166, 174)


def text_at_time(text: str, word_count: int) -> str:
    """Keep original punctuation and spacing while revealing spoken words."""
    import re
    spans = list(re.finditer(r"\S+", text))
    if word_count <= 0:
        return ""
    if word_count >= len(spans):
        return text
    return text[:spans[word_count - 1].end()]


class Wave(QWidget):
    """Low-cost meter driven by real PCM measurements from recognition.py."""
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.raw = [0.0] * 29
        self.current = [0.0] * 29
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self._step)
        self.hide()

    def start(self) -> None:
        self.timer.start()
        self.show()

    def stop(self) -> None:
        self.timer.stop()
        self.raw[:] = [0.0] * 29
        self.current[:] = [0.0] * 29
        self.hide()

    def set_samples(self, levels: tuple[float, ...]) -> None:
        if self.timer.isActive() and len(levels) == 29:
            self.raw[:] = levels

    def _step(self) -> None:
        for i, value in enumerate(self.raw):
            previous = self.current[i]
            self.current[i] += (value - previous) * (.53 if value >= previous else .3)
            self.raw[i] *= .75
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap, middle = self.width() / 29, self.height() / 2
        p.setPen(QPen(QColor(232, 232, 237), max(1.25, min(2, gap * .52)),
                      Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, level in enumerate(self.current):
            h = 2 + math.sqrt(max(0.0, min(1.0, level))) * (self.height() - 3)
            x = round((i + .5) * gap)
            p.drawLine(x, round(middle - h / 2), x, round(middle + h / 2))


class Island(QWidget):
    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.side = settings.position in {"LEFT", "RIGHT"}
        self.state = "hidden"
        self.status = ""
        self.reply = ""
        self.visible_reply = ""
        self.details = ""
        self.action = "talk"
        self.phase = 0.0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(414, 564) if self.side else self.resize(308, 62)
        self.wave = Wave(self)
        self.tick = QTimer(self)
        self.tick.setInterval(40)
        self.tick.timeout.connect(self._tick)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)
        if self.side:
            self.query_label = self._label(12, WHITE)
            self.detail_label = self._label(12, WHITE)
            self.sensors = self._label(10, SUBTLE)
            self.scroll = QScrollArea(self)
            self.scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.scroll.setWidgetResizable(True)
            self.scroll.setStyleSheet(
                "QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;border:0;}"
                "QScrollBar:vertical {background:transparent;width:5px;}"
                "QScrollBar::handle:vertical {background:#64646c;border-radius:2px;}"
            )
            self.scroll.setWidget(self.detail_label)
            self.query_label.setGeometry(30, 143, 354, 64)
            self.scroll.setGeometry(29, 278, 354, 214)
            self.sensors.setGeometry(30, 522, 355, 20)
            self.sensor_timer = QTimer(self)
            self.sensor_timer.timeout.connect(self._read_sensors)
        self.hide()

    def _label(self, size: int, color: QColor) -> QLabel:
        label = QLabel(self)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setFont(QFont("Segoe UI", size))
        label.setStyleSheet(f"background: transparent; color: {color.name()};")
        return label

    def resizeEvent(self, event) -> None:
        if self.side:
            self.wave.setGeometry(260, 42, 112, 26)
        else:
            self.wave.setGeometry(self.width() - 112, (self.height() - 26) // 2, 68, 26)
        super().resizeEvent(event)

    def _target(self, width: int, height: int) -> QRect:
        area = QApplication.primaryScreen().availableGeometry()
        position = self.settings.position
        if position == "TOP":
            return QRect(area.center().x() - width // 2, area.top() + 8, width, height)
        if position == "BOTTOM":
            return QRect(area.center().x() - width // 2, area.bottom() - height - 8, width, height)
        if position == "LEFT":
            return QRect(area.left() + 16, area.center().y() - height // 2, width, height)
        return QRect(area.right() - width - 16, area.center().y() - height // 2, width, height)

    def _seed(self, rect: QRect) -> QRect:
        if self.side:
            direction = -1 if self.settings.position == "LEFT" else 1
            return rect.translated(direction * (rect.width() + 20), 0)
        area = QApplication.primaryScreen().availableGeometry()
        y = area.top() - 9 if self.settings.position == "TOP" else area.bottom() - 8
        return QRect(area.center().x() - 9, y, 18, 18)

    def _motion(self, destination: QRect, *, intro: bool = False, outro: bool = False) -> None:
        if hasattr(self, "motion"):
            self.motion.stop()
            self.motion.deleteLater()
        self.motion = QPropertyAnimation(self, b"geometry", self)
        self.motion.setStartValue(self.geometry())
        self.motion.setEndValue(destination)
        self.motion.setDuration(560 if intro else 260 if outro else 310)
        self.motion.setEasingCurve(QEasingCurve.Type.OutBack if intro else
                                   QEasingCurve.Type.InCubic if outro else
                                   QEasingCurve.Type.OutCubic)
        if outro:
            self.motion.finished.connect(self.hide)
        self.motion.start()

    def _show_state(self, width: int, height: int) -> None:
        destination = self._target(width, height)
        if not self.isVisible():
            self.setGeometry(self._seed(destination))
            self.show()
            self._motion(destination, intro=True)
        else:
            if self.geometry() != destination:
                self._motion(destination)
            self.update()

    def listen(self) -> None:
        self.dismiss_timer.stop()
        self.state = "listening"
        self.status = "Слушаю"
        self.visible_reply = ""
        self.wave.start()
        self.tick.start()
        self._side_update("Слушаю", "Ожидаю команду...", "")
        self._show_state(414 if self.side else 308, 564 if self.side else 62)

    def think(self, query: str) -> None:
        self.dismiss_timer.stop()
        self.state = "thinking"
        self.status = "Думаю"
        self.wave.stop()
        self.tick.start()
        self._side_update("Думаю", query, "Готовлю ответ...")
        self._show_state(414 if self.side else 182, 564 if self.side else 54)

    def begin_answer(self, reply: str, query: str, details: str, action: str) -> None:
        self.dismiss_timer.stop()
        self.reply, self.visible_reply, self.details, self.action = reply, "", details, action
        self.state = "speaking"
        self.status = "Готовлю голос"
        self.wave.stop()
        self.tick.start()
        self._side_update("Готовлю голос", query, details)
        self._show_state(414 if self.side else 224, 564 if self.side else 62)

    def spoken(self, count: int) -> None:
        if self.state != "speaking":
            return
        self.visible_reply = text_at_time(self.reply, count)
        self.status = "Отвечаю"
        if self.side:
            self._side_update("Отвечаю", self.query_label.text(),
                              f"{self.visible_reply}\n\n{self.details}")
        else:
            self._fit_answer()
        self.update()

    def finish_answer(self) -> None:
        if self.state != "speaking":
            return
        self.visible_reply = self.reply
        self.status = "Готово"
        self.tick.stop()
        if self.side:
            self._side_update("Готово", self.query_label.text(),
                              f"{self.reply}\n\n{self.details}")
        else:
            self._fit_answer()
        self.update()
        self.dismiss_timer.start(3400 if self.side else 2700)

    def show_error(self, message: str) -> None:
        self.reply, self.visible_reply = message, message
        self.state, self.status, self.action = "error", "Ошибка", "error"
        self.wave.stop()
        self.tick.stop()
        self._side_update("Ошибка", "", message)
        self._show_state(414 if self.side else 420, 564 if self.side else 70)
        self.dismiss_timer.start(7500)

    def _fit_answer(self) -> None:
        area = QApplication.primaryScreen().availableGeometry()
        font = QFont("Segoe UI", 13, QFont.Weight.DemiBold)
        fm = QFontMetrics(font)
        words = self.visible_reply or "Готовлю голос"
        width = max(224, min(min(670, area.width() - 40), fm.horizontalAdvance(words) + 128))
        width = ((width + 9) // 10) * 10
        lines = fm.horizontalAdvance(words) > width - 116
        height = 94 if lines else 62
        target = self._target(width, height)
        if abs(target.width() - self.width()) >= 10 or height != self.height():
            self._motion(target)

    def set_waveform(self, levels: tuple[float, ...]) -> None:
        self.wave.set_samples(levels)

    def _side_update(self, status: str, query: str, details: str) -> None:
        if not self.side:
            return
        self.status = status
        self.query_label.setText(query or "—")
        self.detail_label.setText(details or "—")
        self._read_sensors()
        self.sensor_timer.start(2000)

    def _read_sensors(self) -> None:
        import psutil
        battery = psutil.sensors_battery()
        suffix = f"  ·  заряд {battery.percent:.0f}%" if battery else ""
        self.sensors.setText(f"CPU {psutil.cpu_percent():.0f}%  ·  RAM {psutil.virtual_memory().percent:.0f}%{suffix}")

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self.wave.stop()
        self.tick.stop()
        if self.side:
            self.sensor_timer.stop()
        self._motion(self._seed(self.geometry()), outro=True)

    def _tick(self) -> None:
        self.phase += .13
        self.update()

    def _sparkle(self, p: QPainter, cx: float, cy: float, scale: float = 1) -> None:
        spin = math.sin(self.phase)
        p.save()
        p.translate(cx, cy)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(WHITE)
        def star(x: float, y: float, radius: float, inner: float) -> None:
            path = QPainterPath()
            path.moveTo(x, y-radius)
            path.quadTo(x+inner, y-inner, x+radius, y)
            path.quadTo(x+inner, y+inner, x, y+radius)
            path.quadTo(x-inner, y+inner, x-radius, y)
            path.quadTo(x-inner, y-inner, x, y-radius)
            p.drawPath(path)
        s = 1 + (.10 * spin if self.state == "thinking" else 0)
        star(-4, 1, 10*s, 1.9*s)
        star(9, -8, 4.8*(1-.08*spin), 1.1)
        star(11, 8, 2.8, .7)
        p.restore()

    def _action_icon(self, p: QPainter, cx: int, cy: int) -> None:
        kind = self.action
        if kind in {"talk", "error"}:
            return
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(QColor(228, 228, 233), 1.7, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "open_url":
            p.drawEllipse(QRectF(-9, -9, 18, 18))
            p.drawLine(-9, 0, 9, 0)
            p.drawArc(QRectF(-5, -9, 10, 18), 90*16, 180*16)
        elif kind == "type_text":
            p.drawRoundedRect(QRectF(-11, -7, 22, 15), 3, 3)
            for x in (-6, -1, 4):
                p.drawLine(x, -2, x+1, -2)
            p.drawLine(-5, 4, 5, 4)
        elif kind == "msi_turbo":
            p.drawArc(QRectF(-10, -10, 20, 20), 0, 180*16)
            p.drawLine(0, 2, 6, -5)
            p.drawEllipse(QRectF(-1, 1, 2, 2))
        elif kind == "msi_silent":
            p.setBrush(QColor(228, 228, 233))
            p.drawEllipse(QRectF(-8, -9, 18, 18))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(INK)
            p.drawEllipse(QRectF(-2, -12, 17, 17))
        p.restore()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        if rect.width() < 4 or rect.height() < 4:
            return
        radius = 26 if self.side else min(rect.width(), rect.height()) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 26))
        p.drawRoundedRect(rect.translated(0, 2), radius, radius)
        p.setBrush(INK)
        p.drawRoundedRect(rect, radius, radius)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 24), 1))
        p.drawRoundedRect(rect.adjusted(.5, .5, -.5, -.5), radius, radius)
        # A small seed stays a dot, without trying to paint text inside it.
        if self.width() < 95 or self.height() < 42:
            return
        if self.side:
            self._paint_side(p)
        else:
            self._paint_island(p)

    def _paint_island(self, p: QPainter) -> None:
        mid = self.height() / 2
        self._sparkle(p, 35, mid)
        p.setPen(WHITE)
        p.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        if self.state == "listening":
            p.drawText(QRectF(62, mid-17, 115, 34), Qt.AlignmentFlag.AlignVCenter, "Слушаю")
        elif self.state == "thinking":
            p.drawText(QRectF(62, mid-17, 90, 34), Qt.AlignmentFlag.AlignVCenter, "Думаю")
        else:
            display = self.visible_reply or ("Готовлю голос" if self.state == "speaking" else self.reply)
            if self.height() <= 67:
                display = QFontMetrics(p.font()).elidedText(
                    display, Qt.TextElideMode.ElideRight, self.width() - 112)
            else:
                words = display.split()
                if len(words) > 14:
                    display = "… " + " ".join(words[-14:])
            flags = int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.TextFlag.TextWordWrap)
            p.drawText(QRectF(62, 10, self.width() - 112, self.height() - 20),
                       flags, display)
            self._action_icon(p, self.width() - 35, round(mid))

    def _paint_side(self, p: QPainter) -> None:
        self._sparkle(p, 37, 48)
        p.setPen(WHITE)
        p.setFont(QFont("Segoe UI", 15, QFont.Weight.DemiBold))
        p.drawText(65, 55, "Ассистент")
        self._action_icon(p, 372, 48)
        p.setPen(SUBTLE)
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(30, 111, "ЗАПРОС")
        p.drawText(30, 249, "ОТВЕТ")
        p.drawText(30, 512, "СИСТЕМА")
        p.setPen(QPen(QColor(255, 255, 255, 21), 1))
        p.drawLine(29, 84, 385, 84)
        p.drawLine(29, 218, 385, 218)
        p.drawLine(29, 501, 385, 501)
