"""Optional local Vosk speaker signature. Never uploaded with user requests."""

from __future__ import annotations

import json
import math
import queue
import time
from pathlib import Path

from .config import Settings, load_settings


def distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return float("inf")
    product = sum(a * b for a, b in zip(left, right))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return 1.0 - product / norm if norm else float("inf")


def load_profile(settings: Settings) -> list[float]:
    signature = json.loads(settings.voiceprint_path.read_text(encoding="utf-8"))
    values = signature["spk"]
    if not isinstance(values, list) or len(values) < 16 or not all(
        isinstance(value, (float, int)) and math.isfinite(value) for value in values
    ):
        raise ValueError("Профиль голоса повреждён. Запиши его ещё раз")
    return [float(value) for value in values]


def allowed(result: dict, profile: list[float], threshold: float) -> bool:
    vector = result.get("spk")
    # Missing x-vector must never silently bypass an enabled voice lock.
    return isinstance(vector, list) and distance(profile, vector) <= threshold


def enroll(settings: Settings) -> None:
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel, SpkModel

    if not settings.model_path.is_dir() or not settings.speaker_model_path.is_dir():
        raise FileNotFoundError("Нужны обычная модель Vosk и models/vosk-model-spk-0.4")
    SetLogLevel(-1)
    model = Model(str(settings.model_path))
    speaker = SpkModel(str(settings.speaker_model_path))
    recognizer = KaldiRecognizer(model, 16000, speaker)
    frames: queue.Queue[bytes] = queue.Queue(maxsize=30)

    def callback(indata, count, time_info, status) -> None:
        try:
            frames.put_nowait(bytes(indata))
        except queue.Full:
            pass

    print("Говори в свой обычный микрофон непрерывно 10 секунд разными фразами.", flush=True)
    print("На время записи выключи телевизор: его голос попадёт в образец.", flush=True)
    print("Запись начинается через 2 секунды...", flush=True)
    time.sleep(2)
    best: dict = {}
    with sd.RawInputStream(samplerate=16000, blocksize=800, channels=1,
                           dtype="int16", device=settings.input_device, callback=callback):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            try:
                chunk = frames.get(timeout=0.3)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(chunk):
                result = json.loads(recognizer.Result())
                if int(result.get("spk_frames", 0)) > int(best.get("spk_frames", 0)):
                    best = result
    result = json.loads(recognizer.FinalResult())
    if int(best.get("spk_frames", 0)) > int(result.get("spk_frames", 0)):
        result = best
    vector = result.get("spk")
    if not isinstance(vector, list) or int(result.get("spk_frames", 0)) < 250:
        raise RuntimeError("Недостаточно непрерывной речи. Повтори запись, говори 6–10 секунд без пауз")
    settings.voiceprint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.voiceprint_path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"spk": vector}), encoding="utf-8")
    temporary.replace(settings.voiceprint_path)
    print(f"Профиль записан: {settings.voiceprint_path}")
    print("Теперь поставь audio.voice_lock = true в config.toml")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["enroll"]:
        raise SystemExit("Использование: python -m orbit.voiceprint enroll")
    enroll(load_settings())
