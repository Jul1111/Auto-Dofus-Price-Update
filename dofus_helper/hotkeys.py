"""Raccourcis globaux lus dans l'état réel du clavier (Windows)."""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from .base import IS_WINDOWS, log_line


# --------------------------------------------------------------------------
# Raccourcis globaux lus dans l'état RÉEL du clavier (Windows)
# --------------------------------------------------------------------------
# Le module `keyboard` reçoit les touches par un « hook » Windows et traite les raccourcis
# dans un fil d'exécution sans aucune protection : une erreur dans ce fil, ou un hook que
# Windows retire en silence (programme jugé trop lent à répondre), et plus AUCUN raccourci ne
# marche jusqu'au redémarrage (vu après un Ctrl+F3 arrêté, ou une pause). Ici, l'état des
# touches est demandé à Windows ~60 fois par seconde : rien ne peut « mourir » en silence,
# et une touche dont un relâchement a été manqué ne bloque plus rien.
HOTKEY_POLL = 0.015    # s entre deux lectures du clavier

_MOD_NAMES = {
    "ctrl": "ctrl", "control": "ctrl", "left ctrl": "ctrl", "right ctrl": "ctrl",
    "alt": "alt", "left alt": "alt", "right alt": "alt", "alt gr": "alt",
    "shift": "shift", "left shift": "shift", "right shift": "shift",
    "windows": "win", "win": "win", "left windows": "win", "right windows": "win",
}
# Touche générique ET touches gauche/droite : certains claviers ou logiciels de clavier ne
# mettent à jour que l'une des deux.
_MOD_VKS = {"ctrl": (0x11, 0xA2, 0xA3), "alt": (0x12, 0xA4, 0xA5), "shift": (0x10, 0xA0, 0xA1),
            "win": (0x5B, 0x5C)}
_NAMED_VKS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "pause": 0x13, "caps lock": 0x14, "esc": 0x1B,
    "escape": 0x1B, "space": 0x20, "page up": 0x21, "page down": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "print screen": 0x2C, "insert": 0x2D,
    "delete": 0x2E, "num lock": 0x90, "scroll lock": 0x91,
}
_NAMED_VKS.update({f"f{i}": 0x6F + i for i in range(1, 25)})


def key_vk(name: str) -> Optional[int]:
    """Nom de touche (comme `keyboard` les écrit) -> code de touche virtuelle Windows."""
    name = name.strip().lower()
    if name in _NAMED_VKS:
        return _NAMED_VKS[name]
    if not IS_WINDOWS:
        return None
    import ctypes
    user32 = ctypes.windll.user32
    if len(name) == 1:
        r = user32.VkKeyScanW(ord(name))   # selon la disposition du clavier (AZERTY…)
        if r != -1 and (r & 0xFF) != 0xFF:
            return r & 0xFF
    try:
        import keyboard
        for sc in keyboard.key_to_scan_codes(name):
            vk = user32.MapVirtualKeyW(sc, 1)
            if vk:
                return vk
    except Exception:
        pass
    return None


def parse_combo(combo: str) -> Tuple[frozenset, int]:
    """« ctrl+alt+f12 » -> ({"ctrl", "alt"}, VK de F12). Lève ValueError si inconnu."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("raccourci vide")
    mods = set()
    for p in parts[:-1]:
        if p not in _MOD_NAMES:
            raise ValueError(f"« {p} » n'est pas Ctrl, Alt, Maj ou Windows")
        mods.add(_MOD_NAMES[p])
    main = parts[-1]
    if main in _MOD_NAMES:
        raise ValueError("il manque la touche principale (Ctrl, Alt, Maj seuls ne suffisent pas)")
    vk = key_vk(main)
    if vk is None:
        raise ValueError(f"touche inconnue « {main} »")
    return frozenset(mods), vk


def _vk_state_windows(vk: int) -> int:
    import ctypes
    return ctypes.windll.user32.GetAsyncKeyState(vk) & 0xFFFF


class ModifierHook:
    """Deuxième source pour Ctrl/Alt/Maj/Windows : un hook clavier bas niveau minimal qui
    note chaque appui/relâchement PHYSIQUE (il ne bloque rien, ne fait aucun calcul).
    Vu en jeu : après un Ctrl+F3, Windows peut ne plus voir Ctrl dans l'état du clavier
    (GetAsyncKeyState = 0) alors qu'il est tenu ; ce hook le voit quand même.
    Une touche tenue se répète (~30 fois/s) : un « enfoncé » vieux de plus de FRESH s sans
    répétition est ignoré, au cas où un relâchement aurait été manqué."""
    FRESH = 1.2
    VKS = {0x10: "shift", 0xA0: "shift", 0xA1: "shift", 0x11: "ctrl", 0xA2: "ctrl", 0xA3: "ctrl",
           0x12: "alt", 0xA4: "alt", 0xA5: "alt", 0x5B: "win", 0x5C: "win"}

    def __init__(self):
        self._last: Dict[int, Tuple[bool, float]] = {}
        self._thread: Optional[threading.Thread] = None
        self.ok = False

    def event(self, vk: int, down: bool, t: Optional[float] = None) -> None:
        if vk in self.VKS:
            self._last[vk] = (down, time.monotonic() if t is None else t)

    def mods(self, now: Optional[float] = None) -> set:
        now = time.monotonic() if now is None else now
        return {self.VKS[vk] for vk, (down, t) in list(self._last.items()) if down and now - t < self.FRESH}

    def start(self) -> None:
        if IS_WINDOWS and (self._thread is None or not self._thread.is_alive()):
            self._thread = threading.Thread(target=self._run, daemon=True, name="hook-modificateurs")
            self._thread.start()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t

        class KBD(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = LRESULT
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def proc(n, w, l):
            if n == 0:
                try:
                    k = ctypes.cast(l, ctypes.POINTER(KBD)).contents
                    self.event(k.vkCode, w in (0x100, 0x104))   # WM_KEYDOWN, WM_SYSKEYDOWN
                except Exception:
                    pass
            return user32.CallNextHookEx(None, n, w, l)

        self._proc = HOOKPROC(proc)   # garder une référence : sinon libéré, et plantage
        hook = user32.SetWindowsHookExW(13, self._proc, kernel32.GetModuleHandleW(None), 0)  # WH_KEYBOARD_LL
        if not hook:
            log_line(f"[Hotkeys] Hook des modificateurs impossible (erreur {ctypes.get_last_error()}).", "WARN")
            return
        self.ok = True
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


class HotkeyPoller:
    """Raccourcis globaux : action au moment où la touche principale s'enfonce, avec
    EXACTEMENT les modificateurs demandés (Ctrl+F3 ne déclenche pas F3, ni l'inverse).
    Les actions sont appelées dans le fil de lecture : elles doivent être courtes
    (mettre une tâche en file d'attente), une erreur est notée sans rien arrêter."""

    def __init__(self, state=None, interval: float = HOTKEY_POLL, hook: Optional["ModifierHook"] = None):
        self._state = state or _vk_state_windows
        self._hook = hook
        self.interval = interval
        self._bindings: List[Tuple[str, frozenset, int, Callable]] = []
        self._down: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self.errors: List[str] = []

    def add(self, combo: str, callback: Callable) -> None:
        mods, vk = parse_combo(combo)
        with self._lock:
            self._bindings.append((combo, mods, vk, callback))
            self._down[combo] = True      # touche déjà enfoncée au moment de l'ajout : pas d'action
        self.start()

    def clear(self) -> None:
        with self._lock:
            self._bindings = []
            self._down = {}

    def _is_down(self, vk: int) -> bool:
        return bool(self._state(vk) & 0x8000)

    def poll_once(self) -> None:
        with self._lock:
            bindings = list(self._bindings)
        if not bindings:
            return
        mods_async = {m for m, vks in _MOD_VKS.items() if any(self._is_down(v) for v in vks)}
        mods_hook = self._hook.mods() if self._hook is not None else set()
        mods_now = mods_async | mods_hook
        main_now = {vk: self._is_down(vk) for vk in {b[2] for b in bindings}}
        fire = []
        with self._lock:
            for combo, mods, vk, cb in bindings:
                down = main_now[vk]
                if down and not self._down.get(combo, False) and mods == mods_now:
                    fire.append((combo, cb))
                self._down[combo] = down
        for combo, cb in fire:
            vk = next(b[2] for b in bindings if b[0] == combo)
            if sum(b[2] == vk for b in bindings) > 1:   # ex. F3 / Ctrl+F3 : noter ce qui a été vu
                raw = " ".join(f"{v:02X}={self._state(v) & 0xFFFF:04X}" for v in (0x11, 0xA2, 0xA3, 0x12, 0x10))
                log_line(f"[Hotkeys] {combo} (modificateurs vus : {'+'.join(sorted(mods_now)) or 'aucun'} ; "
                         f"état {'+'.join(sorted(mods_async)) or 'aucun'}, hook "
                         f"{'+'.join(sorted(mods_hook)) or 'aucun'} ; {raw})")
            try:
                cb()
            except Exception as e:      # une action en erreur ne coupe jamais les raccourcis
                self.errors.append(f"{combo} : {e}")
                log_line(f"Raccourci {combo} : erreur {e!r}", "ERROR")

    def _run(self) -> None:
        while True:
            try:
                self.poll_once()
            except Exception as e:
                log_line(f"Lecture du clavier : erreur {e!r}", "ERROR")
            time.sleep(self.interval)

    def start(self) -> None:
        if self._hook is not None:
            self._hook.start()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True, name="raccourcis")
            self._thread.start()

    def wait(self, combo: str) -> None:
        """Bloque jusqu'à l'appui sur `combo` (ligne de commande : touche pour quitter)."""
        done = threading.Event()
        self.add(combo, done.set)
        done.wait()


class _KeyboardHotkeys:
    """Hors Windows : le module `keyboard`, comme avant."""

    def add(self, combo: str, callback: Callable) -> None:
        import keyboard
        keyboard.add_hotkey(combo, callback)

    def clear(self) -> None:
        import keyboard
        keyboard.unhook_all_hotkeys()

    def wait(self, combo: str) -> None:
        import keyboard
        keyboard.wait(combo)


HOTKEYS = HotkeyPoller(hook=ModifierHook()) if IS_WINDOWS else _KeyboardHotkeys()

