from __future__ import annotations

import json
import logging
import math
import queue
import re
import threading
import time
from collections.abc import Callable

from .config import Settings
from .audio_filter import MicrophoneFilter
from .voiceprint import allowed, load_profile

LOG = logging.getLogger(__name__)
WAKE = re.compile(r"\b(?:джарвис|жарвис|компьютер)\b", re.IGNORECASE)


def measure_pcm(audio: bytes, bins: int = 29) -> tuple[tuple[float, ...], float]:
    """Return true short-time RMS over successive 16-bit mono PCM slices.

    No fabricated/random levels: visual columns move with the microphone signal.
    """
    samples = memoryview(audio).cast("h")
    if not samples:
        return (0.0,) * bins, 0.0
    levels: list[float] = []
    total = 0
    for i in range(bins):
        section = samples[i * len(samples) // bins:(i + 1) * len(samples) // bins]
        power = sum(int(value) * int(value) for value in section)
        total += power
        rms = math.sqrt(power / max(1, len(section)))
        levels.append(min(1.0, rms / 7000))
    return tuple(levels), min(1.0, math.sqrt(total / len(samples)) / 7000)


class Listener:
    """Wake grammar and unrestricted command decoding share one Vosk model."""

    def __init__(self, settings: Settings, on_command: Callable[[str], None],
                 on_wake: Callable[[], None], on_level: Callable[[tuple[float, ...]], None],
                 on_error: Callable[[str], None]) -> None:
        self.settings = settings
        self.on_command, self.on_wake = on_command, on_wake
        self.on_level, self.on_error = on_level, on_error
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = threading.Thread(target=self._run, name="Vosk microphone", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _run(self) -> None:
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer, SetLogLevel, SpkModel
            if not self.settings.model_path.is_dir():
                raise FileNotFoundError(f"Скачай модель Vosk в {self.settings.model_path}")
            SetLogLevel(-1)
            model = Model(str(self.settings.model_path))
            speaker = None
            profile = None
            if self.settings.voice_lock:
                if not self.settings.speaker_model_path.is_dir() or not self.settings.voiceprint_path.is_file():
                    raise FileNotFoundError("Для voice_lock скачай модель говорящего и запиши голос через python -m orbit.voiceprint enroll")
                speaker = SpkModel(str(self.settings.speaker_model_path))
                profile = load_profile(self.settings)
            rate = 16000
            wake = KaldiRecognizer(model, rate,
                                   json.dumps(["джарвис", "жарвис", "компьютер", "[unk]"]))
            def command_recognizer():
                return KaldiRecognizer(model, rate, speaker) if speaker else KaldiRecognizer(model, rate)

            command = command_recognizer()
            audio_filter = MicrophoneFilter() if self.settings.noise_reduction else None
            samples: queue.Queue[bytes] = queue.Queue(maxsize=24)

            def callback(indata, frames, time_info, status) -> None:
                if status:
                    LOG.debug("Микрофон: %s", status)
                if not self.paused.is_set():
                    try:
                        samples.put_nowait(bytes(indata))
                    except queue.Full:
                        pass

            with sd.RawInputStream(samplerate=rate, blocksize=800, dtype="int16",
                                   channels=1, device=self.settings.input_device,
                                   callback=callback):
                active = False
                started = last_voice = 0.0
                while not self.stop_event.is_set():
                    if self.paused.is_set():
                        wake.Reset()
                        command.Reset()
                        active = False
                        if audio_filter:
                            audio_filter = MicrophoneFilter()
                        while not samples.empty():
                            try:
                                samples.get_nowait()
                            except queue.Empty:
                                break
                        self.stop_event.wait(0.1)
                        continue
                    try:
                        audio = samples.get(timeout=0.25)
                    except queue.Empty:
                        continue
                    if audio_filter:
                        audio = audio_filter.process(audio)
                    if active:
                        now = time.monotonic()
                        waveform, level = measure_pcm(audio)
                        self.on_level(waveform)
                        voice_floor = max(0.014, audio_filter.noise_floor * 2 / 7000) if audio_filter else 0.035
                        if level > voice_floor:
                            last_voice = now
                        if command.AcceptWaveform(audio):
                            result = json.loads(command.Result())
                            phrase = result.get("text", "").strip()
                            if phrase:
                                if profile is None or allowed(result, profile, self.settings.voice_threshold):
                                    self.on_command(phrase)
                                else:
                                    self.on_error("Голос не совпал. Повтори команду чуть длиннее")
                                active = False
                                wake.Reset()
                        elif now - started > 10 or (now - last_voice > 1.4 and now - started > 1):
                            result = json.loads(command.FinalResult())
                            phrase = result.get("text", "").strip()
                            if phrase:
                                if profile is None or allowed(result, profile, self.settings.voice_threshold):
                                    self.on_command(phrase)
                                else:
                                    self.on_error("Голос не совпал. Повтори команду чуть длиннее")
                            active = False
                            wake.Reset()
                            command = command_recognizer()
                    else:
                        heard = ""
                        if wake.AcceptWaveform(audio):
                            heard = json.loads(wake.Result()).get("text", "")
                        else:
                            heard = json.loads(wake.PartialResult()).get("partial", "")
                        if WAKE.search(heard):
                            active = True
                            started = last_voice = time.monotonic()
                            command = command_recognizer()
                            wake.Reset()
                            self.on_wake()
        except Exception as exc:
            LOG.exception("Распознавание недоступно")
            self.on_error(str(exc))
