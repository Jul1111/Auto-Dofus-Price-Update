"""Sons : notes douces au lieu des bips du haut-parleur."""
from __future__ import annotations

import math
import threading
from typing import TYPE_CHECKING, Dict

from .base import IS_WINDOWS

if TYPE_CHECKING:
    from .config import Config


# Sons : notes douces (sinus + harmonique légère, attaque et extinction progressives) au lieu
# des bips du haut-parleur. (fréquence Hz, durée ms) ; "done" = fin d'un long parcours.
SOUND_NOTES = {
    "ok": ((880, 70), (1175, 120)),
    "warn": ((622, 110), (587, 170)),
    "error": ((392, 130), (294, 240)),
    "done": ((659, 90), (880, 90), (1319, 220)),
}
_sound_cache: Dict[tuple, bytes] = {}


def tone_wav(notes, volume: float = 0.5, rate: int = 22050) -> bytes:
    """Fichier WAV (16 bits mono, en mémoire) qui joue `notes` à ce volume (0..1)."""
    import io
    import math
    import struct
    import wave
    volume = max(0.0, min(1.0, float(volume)))
    amp = 0.55 * volume * volume * 32767          # volume perçu ~ quadratique
    frames = []
    for freq, ms in notes:
        n = int(rate * ms / 1000)
        attack = max(1, int(rate * 0.006))
        for i in range(n):
            env = min(1.0, i / attack) * math.exp(-3.2 * i / n)
            t = i / rate
            v = math.sin(2 * math.pi * freq * t) + 0.18 * math.sin(4 * math.pi * freq * t)
            frames.append(int(max(-32767, min(32767, amp * env * v / 1.18))))
        frames.extend([0] * int(rate * 0.012))     # petit silence entre les notes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(frames)}h", *frames))
    return buf.getvalue()


def sound_data(kind: str, volume: float) -> bytes:
    key = (kind, round(volume, 2))
    if key not in _sound_cache:
        _sound_cache[key] = tone_wav(SOUND_NOTES.get(kind, SOUND_NOTES["ok"]), volume)
    return _sound_cache[key]


def beep(kind: str, cfg: Config, force: bool = False) -> None:
    """Son d'un résultat ("ok", "warn", "error") ou de fin de parcours ("done").
    force : joue même si les sons sont coupés (bouton « Tester »)."""
    if not (cfg.sound or force) or not IS_WINDOWS or cfg.sound_volume <= 0:
        return
    import winsound
    data = sound_data(kind, cfg.sound_volume)
    # SND_MEMORY ne marche pas en asynchrone : lecture dans un thread
    threading.Thread(target=winsound.PlaySound, args=(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT),
                     daemon=True).start()

