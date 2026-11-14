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
    settings = Settings(config_path)
    win = MainWindow(settings)          # dil ve tema burada yüklenir
    win.show()
    sys.exit(qt.exec())


if __name__ == "__main__":
    main()
