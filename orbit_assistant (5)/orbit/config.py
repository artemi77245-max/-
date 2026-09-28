from __future__ import annotations

import os
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FROZEN = bool(getattr(sys, "frozen", False))
DATA_ROOT = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "OrbitAssistant") if FROZEN else ROOT
CONFIG_PATH = DATA_ROOT / "config.toml"
KEYS_PATH = DATA_ROOT / ".env"


def prepare_storage() -> None:
    if FROZEN and not CONFIG_PATH.exists():
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_bytes((ROOT / "config.toml").read_bytes())


def read_config() -> dict:
    prepare_storage()
    return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def write_config(data: dict) -> None:
    """Persist known TOML tables atomically; preserve settings outside the editor."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, options in data.items():
        if not isinstance(options, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in options.items():
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            elif isinstance(value, str):
                encoded = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, (int, float)):
                encoded = str(value)
            elif isinstance(value, list):
                encoded = "[" + ", ".join(json.dumps(v, ensure_ascii=False) if isinstance(v, str) else str(v) for v in value) + "]"
            else:
                raise ValueError(f"Некорректная опция {section}.{key}")
            lines.append(f"{key} = {encoded}")
        lines.append("")
    content = "\n".join(lines)
    tomllib.loads(content)  # Validate before replacing the working configuration.
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def read_keys() -> dict[str, str]:
    if not KEYS_PATH.exists():
        return {}
    result: dict[str, str] = {}
    for line in KEYS_PATH.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            if key.strip() in {"GEMINI_API_KEY", "OPENAI_API_KEY", "FISH_API_KEY"}:
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def write_keys(keys: dict[str, str]) -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for value in keys.values():
        if "\n" in value or "\r" in value:
            raise ValueError("API-ключ не может содержать перенос строки")
    tmp = DATA_ROOT / ".env.tmp"
    tmp.write_text("".join(f"{key}={keys.get(key, '').strip()}\n" for key in
                           ("GEMINI_API_KEY", "OPENAI_API_KEY", "FISH_API_KEY")), encoding="utf-8")
    tmp.replace(KEYS_PATH)


@dataclass(frozen=True)
class Settings:
    position: str
    model_path: Path
    input_device: int | None
    noise_reduction: bool
    voice_lock: bool
    speaker_model_path: Path
    voiceprint_path: Path
    voice_threshold: float
    games: frozenset[str]
    provider: str
    gemini_model: str
    openai_model: str
    fish_model: str
    fish_voice_id: str
    msi_enabled: bool
    msi_turbo_xy: tuple[int, int]
    msi_silent_xy: tuple[int, int]
    msi_open_delay: float
    msi_launch_uri: str
    msi_window_title: str


def load_settings(path: Path | None = None) -> Settings:
    prepare_storage()
    path = path or CONFIG_PATH
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    ui, audio, ai, fish, games, msi = (data.get(k, {}) for k in
        ("ui", "audio", "ai", "fish", "games", "msi"))
    position = str(ui.get("position", "TOP")).upper()
    provider = str(ai.get("provider", "gemini")).lower()
    if position not in {"TOP", "BOTTOM", "LEFT", "RIGHT"}:
        raise ValueError("ui.position: TOP, BOTTOM, LEFT или RIGHT")
    if provider not in {"gemini", "openai"}:
        raise ValueError("ai.provider: gemini или openai")
    model = Path(str(audio.get("model_path", "models/vosk-model-small-ru-0.22")))
    if not model.is_absolute():
        bundled = ROOT / model
        model = DATA_ROOT / model if (DATA_ROOT / model).is_dir() else bundled
    speaker_model = Path(str(audio.get("speaker_model_path", "models/vosk-model-spk-0.4")))
    if not speaker_model.is_absolute():
        speaker_model = DATA_ROOT / speaker_model
    voiceprint = Path(str(audio.get("voiceprint_path", "voiceprint.json")))
    if not voiceprint.is_absolute():
        voiceprint = DATA_ROOT / voiceprint
    threshold = float(audio.get("voice_threshold", 0.38))
    if not 0 < threshold < 1:
        raise ValueError("audio.voice_threshold должен быть между 0 и 1")
    device = audio.get("input_device")
    return Settings(
        position=position, model_path=model, input_device=int(device) if device is not None else None,
        noise_reduction=bool(audio.get("noise_reduction", True)),
        voice_lock=bool(audio.get("voice_lock", False)),
        speaker_model_path=speaker_model, voiceprint_path=voiceprint, voice_threshold=threshold,
        games=frozenset(str(n).lower() for n in games.get("executables", ["cs2.exe"])),
        provider=provider, gemini_model=str(ai.get("gemini_model", "gemini-2.5-flash")),
        openai_model=str(ai.get("openai_model", "gpt-4.1-mini")),
        fish_model=str(fish.get("model", "s2.1-pro")),
        fish_voice_id=str(fish.get("voice_id", "")),
        msi_enabled=bool(msi.get("enabled", False)),
        msi_turbo_xy=_point(msi.get("turbo_xy", [0, 0])),
        msi_silent_xy=_point(msi.get("silent_xy", [0, 0])),
        msi_open_delay=float(msi.get("open_delay", 3.0)),
        msi_launch_uri=str(msi.get("launch_uri", "")),
        msi_window_title=str(msi.get("window_title", "MSI Center")),
    )


def _point(value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Координаты MSI должны быть парой [x, y]")
    return int(value[0]), int(value[1])


def load_env() -> None:
    """Use per-user keys, keeping the executable directory read-only."""
    for key, value in read_keys().items():
        if value:
            os.environ.setdefault(key, value)
