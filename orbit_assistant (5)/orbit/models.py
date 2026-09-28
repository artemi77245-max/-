"""Install official Vosk models into the per-user data directory."""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path

from .config import DATA_ROOT

MODEL_NAMES = {"speech": "vosk-model-small-ru-0.22", "speaker": "vosk-model-spk-0.4"}
BASE_URL = "https://alphacephei.com/vosk/models/"


def install(kind: str) -> Path:
    name = MODEL_NAMES[kind]
    target = DATA_ROOT / "models" / name
    marker = Path("conf") if kind == "speech" else Path("mfcc.conf")
    if (target / marker).exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    zip_path = target.parent / f".{name}.zip"
    staging = target.parent / f".{name}.partial"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with urllib.request.urlopen(BASE_URL + name + ".zip", timeout=35) as response, zip_path.open("wb") as output:
            shutil.copyfileobj(response, output, length=256 * 1024)
        staging.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            for item in archive.infolist():
                relative = Path(item.filename)
                if not relative.parts or relative.parts[0] != name or ".." in relative.parts:
                    raise ValueError("Некорректная структура архива модели")
                if item.is_dir():
                    continue
                destination = staging.joinpath(*relative.parts[1:])
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output, length=256 * 1024)
        if not (staging / marker).exists():
            raise ValueError(f"В архиве нет {marker}")
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
        return target
    finally:
        zip_path.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
