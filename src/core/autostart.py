"""Windows açılınca Spypaper'ı başlatma (HKCU\\...\\Run). Yalnızca Windows'ta ve exe olarak çalışırken."""
import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Spypaper"


def supported():
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def enabled():
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            val, _ = winreg.QueryValueEx(k, NAME)
        return sys.executable.lower() in str(val).lower()
    except OSError:
        return False


def set_enabled(on):
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        print(f"[autostart] {e}")
        return False
