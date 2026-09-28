"""Small, streaming microphone filter; no resident ML dependency."""

from __future__ import annotations

import math
from array import array


class MicrophoneFilter:
    """Speech band + slowly learned noise floor + soft gate for 16 kHz PCM.

    Reduces steady hum and quiet background sounds. It cannot separate speakers.
    Kept in the microphone consumer thread, never in the PortAudio callback.
    """

    def __init__(self) -> None:
        self.hp_in = self.hp_out = self.lp = 0.0
        self.noise_floor = 100.0  # PCM units, intentionally conservative at startup
        self.gain = 1.0

    def process(self, audio: bytes) -> bytes:
        source = memoryview(audio).cast("h")
        if not source:
            return audio
        filtered = array("h")
        energy = 0.0
        # One-pole high-pass ~110 Hz and low-pass ~3900 Hz at 16 kHz.
        for sample in source:
            hp = 0.9586 * (self.hp_out + sample - self.hp_in)
            self.hp_in, self.hp_out = float(sample), hp
            self.lp += 0.78 * (hp - self.lp)
            value = self.lp
            energy += value * value
            filtered.append(max(-32768, min(32767, round(value))))
        rms = math.sqrt(energy / len(source))
        # Learn only from quiet frames, so sustained speech does not teach the
        # gate to remove its own speaker. Adapt down faster than up.
        if rms < self.noise_floor * 1.65:
            speed = 0.025 if rms > self.noise_floor else 0.14
            self.noise_floor = max(55.0, (1 - speed) * self.noise_floor + speed * rms)
        ratio = rms / max(80.0, self.noise_floor)
        target = max(0.10, min(1.0, (ratio - 1.25) / 1.35))
        # Fast attack, gentle release; apply a ramp across the frame to avoid clicks.
        next_gain = self.gain + (target - self.gain) * (0.92 if target > self.gain else 0.32)
        start_gain = self.gain
        self.gain = next_gain
        for i in range(len(filtered)):
            gain = start_gain + (next_gain - start_gain) * (i + 1) / len(filtered)
            filtered[i] = round(filtered[i] * gain)
        return filtered.tobytes()
