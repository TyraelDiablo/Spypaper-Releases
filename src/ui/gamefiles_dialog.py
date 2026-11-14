"""Oyun Dosyaları: Minecraft'ın dil dosyalarını ve eşya ikonlarını kullanıcının kendi bilgisayarında hazırlar.

Önce bilgisayardaki Minecraft kurulumundan çıkarmayı önerir; yoksa kullanıcının onayıyla
Mojang'ın resmî sunucularından indirir. Dosyalar exe'nin yanındaki Translation/ ve Icons/ klasörlerine yazılır.
"""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QProgressBar, QRadioButton, QVBoxLayout

from core import gamefiles
from .i18n import t
from .theme import TOKENS
from .widgets import ask, button, label, row


class GameFilesDialog(QDialog):
    progress = Signal(int, int)
    logged = Signal(str)
    finished_job = Signal(object, str)

    def __init__(self, parent=None, mc_version=""):
        super().__init__(parent)
        self.mc_version = mc_version
        self.setWindowTitle(t("Oyun Dosyaları"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Oyun Dosyaları", "PageTitle"))
        v.addWidget(label("Eşya adlarının seçili dilde ve eşyaların ikonlarıyla görünmesi için Minecraft'ın kendi dil "
                          "dosyaları ve dokuları gerekir. Bu dosyalar Mojang'a ait olduğu için Spypaper ile dağıtılmaz; "
                          "burada senin bilgisayarında hazırlanır.", "Muted", wrap=True))
        self.status_lbl = label("", "CardTitle", wrap=True)
        v.addWidget(self.status_lbl)

        self.mc = gamefiles.default_mc_dir()
        self.local = gamefiles.local_versions(self.mc) if self.mc else []
        self.rb_local = QRadioButton(t("Bu bilgisayardaki Minecraft kurulumundan çıkar"))
        self.rb_remote = QRadioButton(t("Mojang'ın resmî sunucularından indir"))
        self.ver_local = QComboBox()
        for name, *_ in self.local:
            self.ver_local.addItem(name)
        if mc_version and self.ver_local.findText(mc_version) >= 0:
            self.ver_local.setCurrentText(mc_version)
        v.addWidget(self.rb_local)
        v.addLayout(row(label(self.mc or t("Minecraft kurulumu bulunamadı"), "Muted"), None, self.ver_local,
                        stretch_end=False))
        v.addWidget(self.rb_remote)
        v.addWidget(label(t("Sürüm: {v} (sunucunun sürümü; Mojang listesinde yoksa en yeni sürüm)", v=mc_version or "?"),
                          "Muted", wrap=True))
        has_local = bool(self.local)
        self.rb_local.setEnabled(has_local)
        self.ver_local.setEnabled(has_local)
        (self.rb_local if has_local else self.rb_remote).setChecked(True)

        self.langs = QComboBox()
        self.langs.addItem(t("Panelin 16 dili"), "panel")
        self.langs.addItem(t("Minecraft'taki tüm diller"), "all")
        self.icons = QCheckBox(t("Eşya ve blok ikonlarını da al"))
        self.icons.setChecked(True)
        v.addLayout(row(label("Diller"), self.langs, None, self.icons, stretch_end=False))
        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.log_lbl = label("", "Muted", wrap=True)
        v.addWidget(self.log_lbl)
        self.btn = button("Dosyaları Hazırla", "primary", self.start)
        v.addLayout(row(None, button("Kapat", "ghost", self.reject), self.btn, stretch_end=False))

        self.progress.connect(lambda a, b: (self.bar.setMaximum(max(b, 1)), self.bar.setValue(a)))
        self.logged.connect(lambda s: self.log_lbl.setText(s[-160:]))
        self.finished_job.connect(self._done)
        self.changed = False
        self._show_status()

    def _show_status(self):
        st = gamefiles.status()
        if st["langs"] or st["icons"]:
            self.status_lbl.setText(t("Şu an: {n} dil dosyası, {i} ikon", n=len(st["langs"]), i=st["icons"]))
        else:
            self.status_lbl.setText(t("Şu an hiç dil dosyası ya da ikon yok."))

    def start(self):
        remote = self.rb_remote.isChecked()
        if remote and not ask(self, t("Minecraft istemcisi Mojang'ın sunucularından geçici olarak indirilecek; yalnızca dil "
                                      "dosyaları ve ikonlar ayrılıp jar silinecek. Bu dosyalar Mojang'a aittir ve Minecraft "
                                      "EULA'sına tabidir; yalnızca kendi kullanımın içindir.\n\nDevam edilsin mi?"), t("Onay")):
            return
        langs = None if self.langs.currentData() == "all" else gamefiles.PANEL_LANGS
        icons = self.icons.isChecked()
        ver_local = self.ver_local.currentText()
        contact = ""
        self.btn.setEnabled(False)
        self.bar.show()
        self.bar.setMaximum(0)

        def work():
            try:
                if remote:
                    res = gamefiles.download_mojang(self.mc_version, langs, icons, contact=contact,
                                                    progress=self.progress.emit, log=self.logged.emit)
                else:
                    res = gamefiles.extract_local(self.mc, ver_local, langs, icons, log=self.logged.emit)
                self.finished_job.emit(res, "")
            except Exception as e:
                self.finished_job.emit(None, t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, res, err):
        self.bar.hide()
        self.btn.setEnabled(True)
        if err:
            self.log_lbl.setText(err)
            self.log_lbl.setStyleSheet(f"color:{TOKENS['danger']}")
            return
        n, icons, missing, ver = res
        msg = t("Hazır: Minecraft {v} · {n} dil, {i} ikon.", v=ver, n=n, i=icons)
        if missing:
            msg += " " + t("Bu sürümde olmayan diller: {l}", l=", ".join(missing))
        self.log_lbl.setStyleSheet(f"color:{TOKENS['accent']}")
        self.log_lbl.setText(msg)
        self.changed = True
        self._show_status()
