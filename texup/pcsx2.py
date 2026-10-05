"""PCSX2-specific helpers: locating the textures folder and poking the emulator to reload."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Virtual-key codes for the hotkeys people realistically bind in PCSX2.
_VK = {f"F{i}": 0x6F + i for i in range(1, 25)}
_VK.update({
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "PAUSE": 0x13, "SCROLLLOCK": 0x91, "NUMPAD0": 0x60, "NUMPAD1": 0x61, "NUMPAD2": 0x62,
    "NUMPAD3": 0x63, "NUMPAD4": 0x64, "NUMPAD5": 0x65, "NUMPAD6": 0x66, "NUMPAD7": 0x67,
    "NUMPAD8": 0x68, "NUMPAD9": 0x69,
})
_VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
_VK.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})


def default_textures_dir() -> str:
    """Best guess for PCSX2's textures root on Windows (Documents\\PCSX2\\textures or portable)."""
    candidates: list[Path] = []
    if sys.platform == "win32":
        docs = Path(os.environ.get("USERPROFILE", "")) / "Documents" / "PCSX2" / "textures"
        candidates.append(docs)
        one_drive = Path(os.environ.get("OneDrive", "")) / "Documents" / "PCSX2" / "textures"
        candidates.append(one_drive)
    candidates.append(Path.home() / "Documents" / "PCSX2" / "textures")
    candidates.append(Path.home() / ".config" / "PCSX2" / "textures")
    for c in candidates:
        if c.is_dir():
            return str(c)
    return ""


def parse_hotkey(name: str) -> int | None:
    key = (name or "").strip().upper().replace(" ", "")
    return _VK.get(key)


def find_pcsx2_window() -> int:
    """Return HWND of a top-level window whose title contains 'PCSX2' (Windows only), else 0."""
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "PCSX2" in buf.value.upper():
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(enum_proc, 0)
    return found[0] if found else 0


def send_reload_hotkey(hotkey: str) -> bool:
    """Send the configured 'Reload Texture Replacements' hotkey to PCSX2.

    Only fires when PCSX2 is the foreground window (so we never type into another app).
    Returns True if the key was sent.
    """
    if sys.platform != "win32":
        return False
    vk = parse_hotkey(hotkey)
    if vk is None:
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = find_pcsx2_window()
    if not hwnd or user32.GetForegroundWindow() != hwnd:
        return False
    KEYEVENTF_KEYUP = 0x0002
    scan = user32.MapVirtualKeyW(vk, 0)
    user32.keybd_event(vk, scan, 0, 0)
    user32.keybd_event(vk, scan, KEYEVENTF_KEYUP, 0)
    return True
