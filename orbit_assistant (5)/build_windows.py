"""Build two standalone Windows applications from the current Python installation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parent


def build(name: str, entry: str, *, assistant: bool) -> None:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", name, "--distpath", str(PROJECT / "dist"),
        "--workpath", str(PROJECT / "build"),
        "--specpath", str(PROJECT / "build"),
        "--paths", str(PROJECT),
        "--icon", str(PROJECT / "icon.ico"),
        "--add-data", f"{PROJECT / 'icon.ico'};.",
        "--add-data", f"{PROJECT / 'config.toml'};.",
        "--collect-all", "vosk",
        "--collect-all", "edge_tts", "--collect-data", "certifi",
    ]
    if assistant:
        model = PROJECT / "models" / "vosk-model-small-ru-0.22"
        command.extend(["--add-data", f"{model};models/vosk-model-small-ru-0.22"])
    command.append(str(PROJECT / entry))
    print("Собираю", name, flush=True)
    subprocess.run(command, cwd=PROJECT, check=True)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Файлы .exe необходимо собирать на Windows")
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        raise SystemExit("Установи сборщик: python -m pip install --user pyinstaller") from exc
    # Both ensurepip and PyInstaller's module discovery need to launch another
    # python.exe. Detect Windows access denial before the multi-minute build.
    try:
        subprocess.run([sys.executable, "-I", "-c", "pass"], cwd=PROJECT,
                       stdin=subprocess.DEVNULL, check=True, timeout=15)
    except PermissionError as exc:
        raise SystemExit(
            "Windows запретила запуск дочернего python.exe (WinError 5). "
            "Это системный запрет запуска процесса, а не ошибка пакетов Orbit. "
            "Проверь «Безопасность Windows → Журнал защиты»; "
            "для сборки без локального Python используй .github/workflows/build-windows.yml."
        ) from exc
    from orbit.models import install
    if not (PROJECT / "models" / "vosk-model-small-ru-0.22" / "conf").is_dir():
        print("Загружаю маленькую русскую модель с официального сайта Vosk…", flush=True)
        install("speech")
    try:
        build("Orbit Assistant", "assistant_app.py", assistant=True)
        build("Orbit Settings", "settings_app.py", assistant=False)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "PyInstaller остановился. Если выше в журнале есть WinError 5 "
            "на subprocess.Popen / CreateProcess, Windows заблокировала дочерний процесс. "
            "Посмотри «Безопасность Windows → Журнал защиты» либо запусти "
            "готовую сборку GitHub Actions из .github/workflows/build-windows.yml."
        ) from exc
    print("Готово: dist\\Orbit Assistant.exe и dist\\Orbit Settings.exe", flush=True)


if __name__ == "__main__":
    main()
