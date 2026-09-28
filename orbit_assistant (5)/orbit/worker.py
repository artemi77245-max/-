from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from .actions import execute
from .brain import ask
from .config import ROOT, load_env, load_settings
from .recognition import Listener, measure_pcm
from .audio_filter import MicrophoneFilter
from .speech import speak
from .ui import Island

LOG = logging.getLogger(__name__)


class Events(QObject):
    wake = pyqtSignal()
    level = pyqtSignal(object)
    thinking = pyqtSignal(str)
    result = pyqtSignal(str, str, str, str)
    word = pyqtSignal(int)
    error = pyqtSignal(str)
    finished_audio = pyqtSignal()


def main() -> None:
    parser = argparse.ArgumentParser(description="Orbit UI worker")
    parser.add_argument("--demo", action="store_true", help="Show a sample overlay without microphone/API")
    parser.add_argument("--text", help="Send text directly to the AI without microphone")
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_env()
    settings = load_settings()
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(str(ROOT / "icon.ico")))
    app.setQuitOnLastWindowClosed(False)
    overlay = Island(settings)
    events = Events()
    listener = None
    events.wake.connect(overlay.listen)
    events.level.connect(overlay.set_waveform)
    events.thinking.connect(overlay.think)
    events.result.connect(overlay.begin_answer)
    events.word.connect(overlay.spoken)
    events.error.connect(overlay.show_error)
    events.finished_audio.connect(overlay.finish_answer)

    if options.demo:
        overlay.listen()
        from PyQt6.QtCore import QTimer
        def preview_microphone() -> None:
            try:
                import sounddevice as sd
                frames: queue.Queue[bytes] = queue.Queue(maxsize=6)
                audio_filter = MicrophoneFilter() if settings.noise_reduction else None

                def callback(indata, count, time_info, status) -> None:
                    try:
                        frames.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

                with sd.RawInputStream(samplerate=16000, blocksize=800, channels=1,
                                       dtype="int16", device=settings.input_device,
                                       callback=callback):
                    until = time.monotonic() + 4
                    while time.monotonic() < until:
                        try:
                            data = frames.get(timeout=.1)
                            if audio_filter:
                                data = audio_filter.process(data)
                            events.level.emit(measure_pcm(data)[0])
                        except queue.Empty:
                            pass
            except Exception as exc:
                LOG.warning("Демо: микрофон недоступен: %s", exc)
                events.error.emit(f"Микрофон недоступен: {exc}")

        threading.Thread(target=preview_microphone, daemon=True, name="Demo mic").start()
        sample = "Привет! Готов помочь с настройками и ответить на вопросы."
        QTimer.singleShot(4600, lambda: overlay.think("Джарвис, как дела?"))
        QTimer.singleShot(5700, lambda: overlay.begin_answer(sample, "Джарвис, как дела?",
                                                               sample, "talk"))
        for index in range(1, len(sample.split()) + 1):
            QTimer.singleShot(6300 + index * 300, lambda n=index: overlay.spoken(n))
        QTimer.singleShot(9700, overlay.finish_answer)
        QTimer.singleShot(11600, lambda: overlay.begin_answer("Режим Турбо активирован",
                                                               "Включи Турбо", "MSI: режим Турбо", "msi_turbo"))
        QTimer.singleShot(12100, lambda: overlay.spoken(3))
        QTimer.singleShot(13800, overlay.finish_answer)
        QTimer.singleShot(17400, app.quit)
    else:
        def process(query: str) -> None:
            events.thinking.emit(query)
            try:
                decision = ask(query, settings)
                outcome = execute(decision, settings)
                details = f"{outcome}\n\n{decision.details}" if settings.position in {"LEFT", "RIGHT"} else outcome
                failed_action = (
                    decision.action == "msi_turbo" and "нажата кнопка" not in outcome
                    or decision.action == "msi_silent" and "нажата кнопка" not in outcome
                    or decision.action == "open_url" and outcome != "Сайт открыт"
                    or decision.action == "type_text" and outcome != "Текст вставлен в активное окно"
                )
                reply = outcome if failed_action else decision.reply
                events.result.emit(reply, query, details, decision.action)
                try:
                    speak(reply, settings, lambda n: events.word.emit(n))
                except Exception as exc:
                    LOG.warning("Озвучка недоступна: %s", exc)
            except Exception as exc:
                LOG.exception("Ошибка команды")
                events.error.emit(str(exc))
            finally:
                events.finished_audio.emit()

        def on_command(query: str) -> None:
            assert listener is not None
            listener.paused.set()  # Prevent speaker feedback and overlapping requests.
            threading.Thread(target=process, args=(query,), daemon=True, name="AI + TTS").start()

        listener = Listener(settings, on_command, lambda: events.wake.emit(),
                            lambda levels: events.level.emit(levels), lambda message: events.error.emit(message))
        events.finished_audio.connect(lambda: listener.paused.clear())
        if options.text:
            from PyQt6.QtCore import QTimer
            events.finished_audio.connect(lambda: QTimer.singleShot(4800, app.quit))
            threading.Thread(target=process, args=(options.text,), daemon=True).start()
        else:
            listener.start()
    app.aboutToQuit.connect(lambda: listener.stop() if listener else None)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
