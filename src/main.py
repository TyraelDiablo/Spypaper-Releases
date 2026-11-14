import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from core import Settings
from ui.window import MainWindow


def main(config_path=None):
    # gömülü harita (Qt WebEngine) için QApplication'dan önce ayarlanmalı
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    qt = QApplication(sys.argv)
    qt.setApplicationName("Spypaper")
    qt.setStyle("Fusion")
    if sys.platform == "win32":          # görev çubuğunda python ikonu yerine Spypaper ikonu
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TyraelDiablo.Spypaper")
        except Exception:
            pass
    from ui.icons import app_icon
    qt.setWindowIcon(app_icon())
    settings = Settings(config_path)
    win = MainWindow(settings)          # dil ve tema burada yüklenir
    win.show()
    sys.exit(qt.exec())


if __name__ == "__main__":
    main()
