"""Synthesis and timed word reveal. Network work and playback run off the Qt thread."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterable

from .config import Settings

LOG = logging.getLogger(__name__)
WordProgress = Callable[[int], None]
Timeline = list[float]  # Speech start of each word in seconds.


def speak(text: str, settings: Settings, on_word: WordProgress | None = None) -> str:
    """Generate audio, then reveal text as words play. Fish → Edge → Windows."""
    audio: bytes | None = None
    timeline: Timeline = []
    provider = ""
    if os.getenv("FISH_API_KEY") and settings.fish_voice_id:
        try:
            audio, timeline = _fish_with_timestamps(text, settings)
            provider = "Fish Audio"
        except Exception as exc:
            LOG.warning("Fish Audio недоступен: %s", exc)
    if audio is None:
        try:
            audio, timeline = asyncio.run(_edge_with_timestamps(text))
            provider = "Edge TTS"
        except Exception as exc:
            LOG.warning("Edge TTS недоступен: %s", exc)
    if audio:
        try:
            _play_mp3(audio, timeline, text, on_word, provider)
            return provider
        except Exception as exc:
            LOG.warning("Воспроизведение MP3 недоступно: %s", exc)
    if on_word:
        on_word(len(text.split()))  # SAPI does not expose timings in this adapter.
    _windows_sapi(text)
    return "Windows SAPI"


def _parse_fish_events(lines: Iterable[str | bytes]) -> tuple[bytes, Timeline]:
    pieces: list[bytes] = []
    aligned: dict[int, tuple[float, list[dict]]] = {}
    size = 0
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw or raw == "[DONE]":
            continue
        event = json.loads(raw)
        part = base64.b64decode(event.get("audio_base64", ""), validate=True)
        size += len(part)
        if size > 15_000_000:
            raise ValueError("Слишком большой аудиоответ")
        pieces.append(part)
        alignment = event.get("alignment")
        if alignment is not None:
            aligned[int(event["chunk_seq"])] = (
                float(event["chunk_audio_offset_sec"]), alignment.get("segments", []))
    timeline: Timeline = []
    for _, (offset, segments) in sorted(aligned.items()):
        timeline.extend(offset + float(segment["start"]) for segment in segments)
    return b"".join(pieces), sorted(timeline)


def _fish_with_timestamps(text: str, settings: Settings) -> tuple[bytes, Timeline]:
    import requests
    with requests.post(
        "https://api.fish.audio/v1/tts/stream/with-timestamp",
        headers={"Authorization": f"Bearer {os.environ['FISH_API_KEY']}",
                 "Content-Type": "application/json", "model": settings.fish_model},
        json={"text": text, "reference_id": settings.fish_voice_id,
              "format": "mp3", "latency": "balanced"},
        timeout=(5, 35), stream=True,
    ) as response:
        response.raise_for_status()
        audio, timeline = _parse_fish_events(response.iter_lines(decode_unicode=True))
    if not audio:
        raise ValueError("Fish Audio не вернул аудио")
    return audio, timeline


async def _edge_with_timestamps(text: str) -> tuple[bytes, Timeline]:
    import edge_tts
    async def collect() -> tuple[bytes, Timeline]:
        pieces: list[bytes] = []
        starts: Timeline = []
        async for part in edge_tts.Communicate(
            text, "ru-RU-DmitryNeural", boundary="WordBoundary"
        ).stream():
            if part["type"] == "audio":
                pieces.append(part["data"])
            elif part["type"] == "WordBoundary":
                starts.append(float(part["offset"]) / 10_000_000)
        audio = b"".join(pieces)
        if not audio or len(audio) > 15_000_000:
            raise ValueError("Некорректное аудио Edge")
        return audio, sorted(starts)
    return await asyncio.wait_for(collect(), timeout=30)


def _play_mp3(audio: bytes, timeline: Timeline, text: str,
              on_word: WordProgress | None, provider: str) -> None:
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    stream = io.BytesIO(audio)
    pygame.mixer.music.load(stream, "mp3")
    words = len(re.findall(r"\S+", text))
    next_mark = 0
    last_count = 0
    pygame.mixer.music.play()
    started = time.monotonic()
    try:
        while pygame.mixer.music.get_busy():
            elapsed = pygame.mixer.music.get_pos() / 1000
            if elapsed < 0:
                elapsed = time.monotonic() - started
            if timeline:
                # Fish/Edge metadata may tokenize numerals and punctuation differently.
                while next_mark < len(timeline) and timeline[next_mark] <= elapsed + .04:
                    next_mark += 1
                count = round(next_mark / len(timeline) * words)
            else:
                # Approximation only when a provider returns no word timestamps.
                bitrate = 128_000 if provider == "Fish Audio" else 48_000
                estimate = max(1.4, len(audio) * 8 / bitrate)
                count = min(words, int(words * elapsed / estimate))
            if on_word and count > last_count:
                on_word(count)
                last_count = count
            time.sleep(.035)
    finally:
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
    if on_word and last_count < words:
        on_word(words)


def _windows_sapi(text: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Офлайн голос Windows доступен только на Windows")
    script = ("Add-Type -AssemblyName System.Speech; "
              "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              "$s.Speak([Console]::In.ReadToEnd())")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   input=text, text=True, timeout=45, check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
