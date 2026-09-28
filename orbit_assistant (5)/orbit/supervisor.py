from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

from .config import DATA_ROOT, load_settings

LOG = logging.getLogger(__name__)


def game_running(names: frozenset[str]) -> bool:
    import psutil
    for process in psutil.process_iter(attrs=["name"]):
        try:
            if (process.info["name"] or "").lower() in names:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False


def stop_worker(worker: subprocess.Popen) -> None:
    """PyInstaller one-file may spawn a bootloader child: stop the whole tree."""
    import psutil
    try:
        parent = psutil.Process(worker.pid)
        children = parent.children(recursive=True)
        for process in reversed(children):
            process.terminate()
        parent.terminate()
        _, alive = psutil.wait_procs(children + [parent], timeout=4)
        for process in alive:
            process.kill()
    except psutil.NoSuchProcess:
        pass
    try:
        worker.wait(timeout=2)
    except subprocess.TimeoutExpired:
        worker.kill()
        worker.wait()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    mutex = None
    if sys.platform == "win32":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_bool
        mutex = kernel.CreateMutexW(None, False, "Local\\OrbitAssistantSupervisor")
        if not mutex:
            raise OSError("Не удалось создать блокировку помощника")
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            kernel.CloseHandle(mutex)
            return
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    stop_flag = DATA_ROOT / "stop.flag"
    pid_file = DATA_ROOT / "assistant.pid"
    stop_flag.unlink(missing_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="ascii")
    worker: subprocess.Popen | None = None
    try:
        while not stop_flag.exists():
            settings = load_settings()  # Saved changes take effect at the next 5-second check.
            gaming = game_running(settings.games)
            if gaming and worker:
                LOG.info("Игра запущена: выгружаю голос и интерфейс")
                stop_worker(worker)
                worker = None
            elif not gaming and (worker is None or worker.poll() is not None):
                LOG.info("Запускаю голос и интерфейс")
                command = ([sys.executable, "--worker"] if getattr(sys, "frozen", False)
                           else [sys.executable, "-m", "orbit.worker"])
                worker = subprocess.Popen(command,
                                          stdin=subprocess.DEVNULL)
            time.sleep(5)
    except KeyboardInterrupt:
        LOG.info("Завершение")
    finally:
        if worker and worker.poll() is None:
            stop_worker(worker)
        stop_flag.unlink(missing_ok=True)
        pid_file.unlink(missing_ok=True)
        if mutex:
            kernel.CloseHandle(mutex)


if __name__ == "__main__":
    main()
