import os
import sys

if getattr(sys, "frozen", False):
    # Tek dosyalı exe, açıldığı geçici klasörü (_MEI…) ortam değişkenleriyle alt süreçlere de bildirir. Spypaper'ın
    # başlattığı bir program (ör. yeniden başlatılan Gezgin) bunları miras alırsa, oradan açılan yeni Spypaper silinmiş
    # bir _MEI klasörünü kullanmaya çalışıp çöker. Alt süreçlere temiz ortam bırak.
    for _k in [k for k in os.environ if k.startswith("_PYI_") or k == "_MEIPASS2"]:
        os.environ.pop(_k, None)
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication

from core import Settings
from ui.window import MainWindow


def _single_instance(qt):
    """Bu kullanıcıda yalnızca bir Spypaper açık olabilir (exe ve kaynak sürüm dahil). Güncellemeden sonra yeni exe
    açılırken eskisi kapanıyor olabilir: birkaç saniye beklenir."""
    import tempfile
    from PySide6.QtCore import QLockFile
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "spypaper-instance.lock"))
    lock.setStaleLockTime(0)                         # çöken Spypaper'ın kilidi PID'den anlaşılır
    if lock.tryLock(4000):
        qt._instance_lock = lock                     # süreç boyunca tutulur
        return True
    from ui.i18n import t
    from ui.msgbox import warning
    warning(None, "Spypaper", t("Spypaper zaten açık. Aynı sunucuları iki panelden yönetmek zamanlanmış görevlerin, "
                                "yedeklerin ve uyarıların iki kez çalışmasına yol açar; açık olan pencereyi kullan."))
    return False


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
    if not _single_instance(qt):                     # ikinci Spypaper aynı sunucuları yönetmesin
        sys.exit(0)
    if splash.run(settings):                          # güncelleme kuruldu: yeni exe başladı
        sys.exit(0)
    from core import auth
    if auth.enabled(settings) and auth.cfg(settings)["on_start"]:
        from ui.auth_dialog import verify
        if not verify(None, settings):              # doğrulanmadan panel açılmaz
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
