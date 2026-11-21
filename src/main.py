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
    from ui import wheelguard
    wheelguard.install(qt)              # kaydırırken açılır liste / sayı kutuları değişmesin
    if sys.platform == "win32":          # görev çubuğunda python ikonu yerine Spypaper ikonu
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TyraelDiablo.Spypaper")
        except Exception:
            pass
    from ui.icons import app_icon
    qt.setWindowIcon(app_icon())
    settings = Settings(config_path)
    from ui import i18n, theme, splash
    i18n.load(settings.get("language"))               # açılış ekranı da panel dilinde ve temasında
    theme.apply(settings.get("theme"), settings.get("high_contrast"), settings.get("font_scale"))
    qt.setStyleSheet(theme.stylesheet())
    if splash.run(settings):                          # güncelleme kuruldu: yeni exe başladı
        sys.exit(0)
    from ui import motion
    qt._fader = motion.DialogFader()                # diyaloglar solarak açılır
    qt.installEventFilter(qt._fader)
    win = MainWindow(settings)          # dil ve tema burada yüklenir
    win.animated_quit = True            # kapanışta "Have fun with your Minecraft server"
    win.show()
    from ui.foreground import bring_to_front
    bring_to_front(win)                 # Windows'ta arkada açılmasın
    from ui import intro
    from ui.home import HomeScreen
    win.intro = intro.play(win, settings, HomeScreen._greeting())   # karşılama, sonra sunucular
    sys.exit(qt.exec())


if __name__ == "__main__":
    main()
