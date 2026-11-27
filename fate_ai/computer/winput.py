"""Mouse, keyboard and window control via the Win32 API (ctypes, no extra dependencies)."""
from __future__ import annotations

import ctypes
import sys
import time

from ..core.exceptions import FateError

IS_WIN = sys.platform == "win32"


class Failsafe(FateError):
    """Raised when the user slams the mouse into the top-left corner to stop the AI."""


def _need_windows():
    if not IS_WIN:
        raise FateError("Mouse, keyboard and window control are only available on Windows.")


if IS_WIN:
    from ctypes import wintypes as wt
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", _U)]

    def _send(*inputs):
        arr = (INPUT * len(inputs))(*inputs)
        user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

MOUSE_MOVE, MOUSE_ABS = 0x0001, 0x8000
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
WHEEL = 0x0800
KEY_UP, KEY_UNICODE = 0x0002, 0x0004

VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B, "enter": 0x0D,
      "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
      "del": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
      "left": 0x25, "right": 0x27, "insert": 0x2D, "capslock": 0x14, "printscreen": 0x2C,
      **{f"f{i}": 0x6F + i for i in range(1, 13)}}


def parse_keys(combo: str) -> list[int]:
    """'ctrl+shift+s' -> virtual-key codes."""
    codes = []
    for part in combo.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in VK:
            codes.append(VK[part])
        elif len(part) == 1 and part.isalnum():
            codes.append(ord(part.upper()))
        else:
            raise FateError(f"Unknown key: {part}")
    if not codes:
        raise FateError("No keys given")
    return codes


def screen_size() -> tuple[int, int]:
    _need_windows()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def cursor() -> tuple[int, int]:
    _need_windows()
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def check_failsafe() -> None:
    if IS_WIN:
        x, y = cursor()
        if x <= 1 and y <= 1:
            raise Failsafe("Stopped: mouse moved to the top-left corner (failsafe).")


def move(x: int, y: int) -> None:
    _need_windows()
    w, h = screen_size()
    ax, ay = int(x * 65535 / max(1, w - 1)), int(y * 65535 / max(1, h - 1))
    _send(INPUT(0, _U(mi=MOUSEINPUT(ax, ay, 0, MOUSE_MOVE | MOUSE_ABS, 0, 0))))


def click(x: int, y: int, button: str = "left", double: bool = False) -> None:
    check_failsafe()
    move(x, y)
    time.sleep(0.05)
    down, up = BUTTONS.get(button, BUTTONS["left"])
    for _ in range(2 if double else 1):
        _send(INPUT(0, _U(mi=MOUSEINPUT(0, 0, 0, down, 0, 0))), INPUT(0, _U(mi=MOUSEINPUT(0, 0, 0, up, 0, 0))))
        time.sleep(0.06)


def scroll(amount: int) -> None:
    check_failsafe()
    _send(INPUT(0, _U(mi=MOUSEINPUT(0, 0, ctypes.c_ulong(int(amount) * 120).value, WHEEL, 0, 0))))


def type_text(text: str) -> None:
    check_failsafe()
    _need_windows()
    for ch in text:
        if ch == "\n":
            press("enter")
            continue
        code = ord(ch)
        units = [code] if code < 0x10000 else [0xD800 + ((code - 0x10000) >> 10), 0xDC00 + ((code - 0x10000) & 0x3FF)]
        for u in units:
            _send(INPUT(1, _U(ki=KEYBDINPUT(0, u, KEY_UNICODE, 0, 0))),
                  INPUT(1, _U(ki=KEYBDINPUT(0, u, KEY_UNICODE | KEY_UP, 0, 0))))
        time.sleep(0.004)


def press(combo: str) -> None:
    check_failsafe()
    _need_windows()
    codes = parse_keys(combo)
    downs = [INPUT(1, _U(ki=KEYBDINPUT(c, 0, 0, 0, 0))) for c in codes]
    ups = [INPUT(1, _U(ki=KEYBDINPUT(c, 0, KEY_UP, 0, 0))) for c in reversed(codes)]
    _send(*downs, *ups)


def windows() -> list[tuple[int, str]]:
    _need_windows()
    out = []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value.strip():
                    out.append((int(hwnd), buf.value))
        return True
    user32.EnumWindows(proc(cb), 0)
    return out


def focus(title_part: str) -> str:
    for hwnd, title in windows():
        if title_part.lower() in title.lower():
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return title
    raise FateError(f"No open window matches '{title_part}'.")
