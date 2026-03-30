import ctypes
import ctypes.wintypes

import win32gui

FLASHW_ALL      = 3
FLASHW_STOP     = 0
FLASHW_TIMERNOFG = 12

class FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize",    ctypes.wintypes.UINT),
        ("hwnd",      ctypes.wintypes.HWND),
        ("dwFlags",   ctypes.wintypes.DWORD),
        ("uCount",    ctypes.wintypes.UINT),
        ("dwTimeout", ctypes.wintypes.DWORD),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def get_my_hwnd() -> int:
    """Return the HWND of the current window. Run it at the start of a script to get the console window HWND."""
    return user32.GetForegroundWindow()


def get_hwnd_from_title(title: str) -> int:
    """Return the HWND of a window, given its title. Return 0 if it doesn't exist."""
    return win32gui.FindWindowEx(0, 0, None, title)


def flash_window(hwnd: int, count: int = 8, timeout_ms: int = 400):
    """Flash the title of the given window."""
    # print(f"hwnd: {hwnd}")

    fwi = FLASHWINFO(
        cbSize    = ctypes.sizeof(FLASHWINFO),
        hwnd      = hwnd,
        dwFlags   = FLASHW_ALL | FLASHW_TIMERNOFG,
        uCount    = count,
        dwTimeout = timeout_ms,
    )
    ctypes.windll.user32.FlashWindowEx(ctypes.byref(fwi))
