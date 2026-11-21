"""Pencereyi öne getirir. Windows, başka bir pencere odaktayken yeni açılan pencerenin öne geçmesini engeller
(güncelleme ekranı kapandıktan sonra Spypaper arkada kalıyordu); odaktaki pencerenin iş parçacığına geçici olarak
bağlanıp SetForegroundWindow çağırmak bu engeli aşmanın bilinen yoludur."""
import os

from PySide6.QtCore import Qt, QTimer


def _win32(hwnd):
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.GetWindowThreadProcessId.restype = wintypes.DWORD
    fg = u.GetForegroundWindow()
    cur = k.GetCurrentThreadId()
    other = u.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != cur and u.AttachThreadInput(other, cur, True))
    try:
        u.ShowWindow(hwnd, 9 if u.IsIconic(hwnd) else 5)       # SW_RESTORE / SW_SHOW
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        u.SetActiveWindow(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(other, cur, False)


def bring_to_front(win):
    def go():
        win.setWindowState((win.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        win.raise_()
        win.activateWindow()
        if os.name == "nt":
            try:
                _win32(int(win.winId()))
            except Exception:
                pass
    go()
    QTimer.singleShot(250, go)          # pencere yöneticisi ilk denemeyi yutarsa bir kez daha
