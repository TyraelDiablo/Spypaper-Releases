"""Ayarlar → Spypaper'ı kaldır: ayarları saklama seçeneği, isteğe bağlı GitHub geri bildirimi, kaldırma."""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QVBoxLayout

from core import autostart, uninstall
from core.config import get_base_dir
from . import VERSION, i18n
from .i18n import t
from .msgbox import error, warning
from .widgets import button, color, label, row


class UninstallDialog(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setWindowTitle(t("Spypaper'ı kaldır"))
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Spypaper'ı kaldır", "PageTitle"))
        v.addWidget(label("Spypaper kapanır ve bu klasördeki kendi dosyaları silinir. Sunucu klasörlerine, "
                          "dünyalara ve yedeklere dokunulmaz.", "Muted", wrap=True))
        v.addWidget(label(get_base_dir(), "Muted", raw=True))
        self.keep = QCheckBox(t("Ayarlarımı sakla (config.json, sohbet geçmişi ve dil dosyaları)"))
        self.keep.setChecked(True)
        self.keep.setCursor(Qt.PointingHandCursor)
        v.addWidget(self.keep)
        v.addWidget(label("İleride Spypaper'ı aynı klasöre koyarsan sunucuların ve ayarların geri gelir. "
                          "İşareti kaldırırsan API anahtarları dahil tüm ayarlar silinir.", "Muted", wrap=True))
        fb = QLabel(f'<a href="#" style="color:{color("accent")}; text-decoration:none;">'
                    f'{t("Bir sorun mu yaşadın? GitHub’da bize yaz.")}</a>')
        fb.setTextFormat(Qt.RichText)
        fb.setCursor(Qt.PointingHandCursor)
        fb.linkActivated.connect(self._feedback)
        v.addWidget(fb)
        v.addSpacing(6)
        self.go = button("Kaldır", "danger", self._uninstall)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), self.go))

    def _feedback(self, _href=""):
        webbrowser.open(uninstall.issue_url(VERSION, i18n.current()))

    def _uninstall(self):
        if not uninstall.supported():
            warning(self, t("Spypaper'ı kaldır"),
                    t("Kaldırma yalnızca Windows'ta Spypaper.exe ile çalışır. Kaynak koddan çalışırken klasörü elle sil."))
            return
        running = [a.config.name for a in self.ctl.apps.values() if a.server.is_running]
        if running:
            warning(self, t("Spypaper'ı kaldır"),
                    t("Önce çalışan sunucuları durdur: {names}", names=", ".join(running)))
            return
        try:
            if autostart.enabled():
                autostart.set_enabled(False)      # Windows açılışındaki kayıt silinen exe'yi göstermesin
            uninstall.launch(self.keep.isChecked())
        except Exception as e:
            error(self, t("Spypaper'ı kaldır"), t("Kaldırma başlatılamadı: {e}", e=e))
            return
        self.accept()
        self.ctl.close()
        QApplication.quit()
