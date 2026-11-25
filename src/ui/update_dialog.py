"""Sunucu yazılımı kurma / güncelleme penceresi (Paper, Purpur, Vanilla, Fabric, Forge, NeoForge)."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QProgressBar, QVBoxLayout

from core import software, switch, updater
from .i18n import t
from .theme import TOKENS
from .widgets import ask, button, label, row


def _err(e):
    return t(e.template, **e.kw) if hasattr(e, "template") else str(e)


class UpdateDialog(QDialog):
    versions_ready = Signal(list, str)
    build_ready = Signal(dict, str)
    progress = Signal(int, int)
    install_log = Signal(str)
    finished_dl = Signal(str, str)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.contact = app.config.settings.get("update_contact")
        self.info = None
        self.setWindowTitle(t("Sunucu Yazılımı"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Sunucu Yazılımı", "PageTitle"))

        jar = app.config.get("jar_name")
        self.cur_soft, self.cur_ver, self.cur_label = software.current(app.config.server_path, jar)
        name = software.SOFTWARE[self.cur_soft]["name"]
        cur = " ".join(x for x in (name, self.cur_ver, f"#{self.cur_label}" if self.cur_label else "") if x)
        v.addWidget(label(t("Şu anki: {jar}  ({cur})", jar=jar, cur=cur or t("bilinmiyor")), "Muted", wrap=True))

        self.sw = QComboBox()
        for key, info in software.SOFTWARE.items():
            self.sw.addItem(info["name"], key)
        self.sw.setCurrentIndex(max(0, self.sw.findData(self.cur_soft)))
        self.sw.currentIndexChanged.connect(self._load_versions)
        self.sw.setMinimumWidth(150)
        self.ver = QComboBox()
        self.ver.setMinimumWidth(130)
        self.ver.setEnabled(False)
        self.ver.currentTextChanged.connect(self.fetch_build)
        v.addLayout(row(label("Yazılım"), self.sw, None, label("Minecraft sürümü"), self.ver, stretch_end=False))
        self.status = label("", "CardTitle", wrap=True)
        v.addWidget(self.status)
        self.warn_lbl = label("", "Muted", wrap=True)
        self.warn_lbl.setStyleSheet(f"color:{TOKENS['warn']}")
        v.addWidget(self.warn_lbl)
        self.log_lbl = label("", "Muted", wrap=True)
        self.log_lbl.hide()
        v.addWidget(self.log_lbl)
        self.migrate = QCheckBox(t("Klasörü yeni yazılıma hazırla (uyumsuz eklenti/modları yedeğe taşı, dünyayı dönüştür)"))
        self.migrate.setChecked(True)
        self.migrate.hide()
        v.addWidget(self.migrate)
        self.trial = QCheckBox(t("Önce sunucunun bir kopyasında dene: kopya açılmazsa asıl sunucuya dokunulmaz"))
        self.trial.setToolTip(t("Sunucu klasörü (dünya dahil, yedekler hariç) geçici bir kopyaya alınır, yeni yazılım "
                                "orada kurulup açılır. Diskte sunucu kadar boş yer ve birkaç dakika gerekir."))
        v.addWidget(self.trial)
        self.backup = QCheckBox(t("Önce dünya yedeği al"))
        self.backup.setChecked(True)
        v.addWidget(self.backup)
        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.btn = button("Güncelle", "primary", self.start)
        self.btn.setEnabled(False)
        v.addLayout(row(None, button("Kapat", "ghost", self.reject), self.btn, stretch_end=False))

        self.versions_ready.connect(self._on_versions)
        self.build_ready.connect(self._on_build)
        self.progress.connect(lambda a, b: (self.bar.setMaximum(max(b, 1)), self.bar.setValue(a)))
        self.install_log.connect(lambda s: self.log_lbl.setText(s[-160:]))
        self.finished_dl.connect(self._on_done)
        self._load_versions()

    def _level(self):
        try:
            return self.app.properties.load().get("level-name") or "world"
        except Exception:
            return "world"

    def _key(self):
        return self.sw.currentData()

    def _bg(self, fn, on_err):
        def run():
            try:
                fn()
            except Exception as e:
                on_err(_err(e))
        threading.Thread(target=run, daemon=True).start()

    def _load_versions(self, *_):
        key = self._key()
        self.info = None
        self.ver.setEnabled(False)
        self.btn.setEnabled(False)
        self.warn_lbl.setText("")
        self.ver.blockSignals(True)
        self.ver.clear()
        self.ver.blockSignals(False)
        self.status.setText(t("{name} sürümleri alınıyor…", name=software.SOFTWARE[key]["name"]))
        self._bg(lambda: self.versions_ready.emit(software.list_versions(key, self.contact), ""),
                 lambda e: self.versions_ready.emit([], e))

    def _on_versions(self, vers, err):
        if err:
            self.status.setText(err)
            return
        if not vers:
            self.status.setText(t("Bu yazılım için sürüm bulunamadı."))
            return
        self.ver.blockSignals(True)
        self.ver.addItems(vers)
        self.ver.setCurrentText(self.cur_ver if self.cur_ver in vers else vers[0])
        self.ver.blockSignals(False)
        self.ver.setEnabled(True)
        self.fetch_build(self.ver.currentText())

    def fetch_build(self, v):
        if not v:
            return
        key = self._key()
        self.btn.setEnabled(False)
        self.status.setText(t("Kontrol ediliyor…"))
        self._bg(lambda: self.build_ready.emit(software.latest_build(key, v, self.contact), ""),
                 lambda e: self.build_ready.emit({}, e))

    def _on_build(self, info, err):
        if err:
            self.status.setText(err)
            return
        if info.get("software") != self._key() or info.get("version") != self.ver.currentText():
            return          # kullanıcı bu arada başka seçim yaptı
        self.info = info
        key = self._key()
        same_soft = key == self.cur_soft
        same = same_soft and info["version"] == self.cur_ver and info["label"] and info["label"] == self.cur_label
        tag = f" #{info['label']}" if info["label"] else ""
        self.status.setText(t("Zaten güncel ({v}{tag}).", v=info["version"], tag=tag) if same
                            else t("İndirilecek: {name} {v}{tag}", name=software.SOFTWARE[key]["name"],
                                   v=info["version"], tag=tag))
        warns = []
        self.steps = []
        self.migrate.setVisible(not same_soft)
        if not same_soft:
            try:
                self.steps = switch.plan(self.app.config.server_path, self._level(), self.cur_soft, key)
            except switch.SwitchError as e:
                self.warn_lbl.setText(_err(e))
                self.btn.setEnabled(False)
                return
            old_mod, new_mod = software.SOFTWARE[self.cur_soft]["modded"], software.SOFTWARE[key]["modded"]
            warns.append(t("Yazılım değiştiriliyor ({old} → {new}).",
                           old=software.SOFTWARE[self.cur_soft]["name"], new=software.SOFTWARE[key]["name"]))
            if self.steps:
                warns += ["• " + t(st["text"], **st["kw"]) for st in self.steps]
            elif old_mod != new_mod:
                warns.append(t("Eklenti (plugins) ve mod (mods) sistemleri birbirinin yerine geçmez; mevcut eklentiler ya da modlar çalışmaz."))
        if self.cur_ver and info["version"] != self.cur_ver:
            if updater._vkey(info["version"]) > updater._vkey(self.cur_ver):
                warns.append(t("Minecraft sürümü yükseltiliyor. Dünya yeni sürüme dönüştürülür ve geri alınamaz; eklentilerin uyumlu olduğundan emin ol."))
            else:
                warns.append(t("Eski bir Minecraft sürümüne geçmek dünyayı bozabilir. Önerilmez."))
        if info.get("installer"):
            warns.append(t("Kurulum programı indirilip Java ile çalıştırılacak; bu birkaç dakika sürebilir."))
        if info.get("beta"):
            warns.append(t("Bu Minecraft sürümü için yalnızca beta sürüm var."))
        self.warn_lbl.setText("\n".join(warns))
        self.trial.setChecked(not same_soft or bool(self.cur_ver and info["version"] != self.cur_ver))
        self.adjustSize()
        self.btn.setText(t("Yeniden indir") if same else t("Kur") if not same_soft else t("Güncelle"))
        self.btn.setEnabled(True)

    def start(self):
        if not self.info:
            return
        if self.app.server.is_running:
            self.status.setText(t("Önce sunucuyu durdur."))
            return
        if self.warn_lbl.text() and not ask(self, self.warn_lbl.text() + "\n\n" + t("Devam edilsin mi?"), t("Onay")):
            return
        for w in (self.btn, self.ver, self.sw):
            w.setEnabled(False)
        self.bar.show()
        info, do_backup = self.info, self.backup.isChecked()
        cfg = self.app.config
        do_migrate = self.migrate.isVisible() and self.migrate.isChecked()
        old_key, level = self.cur_soft, self._level()
        do_trial = self.trial.isChecked()

        def run():
            try:
                if do_trial:
                    from core import trial
                    prog = lambda a, b: self.progress.emit(a, b)
                    self.install_log.emit(t("Deneme için sunucunun kopyası alınıyor…"))
                    tp = trial.copy_server(cfg.server_path, progress=prog)
                    try:
                        self.install_log.emit(t("Kopyaya yeni yazılım kuruluyor…"))
                        if info.get("installer"):
                            tjar = software.install_with_installer(info, tp, cfg.get("java_path"), self.contact,
                                                                   progress=prog, log=self.install_log.emit)
                        else:
                            tjar = updater.download(info, tp, cfg.get("jar_name"), self.contact, progress=prog)
                        if do_migrate:
                            switch.apply(tp, level, old_key, info["software"])
                        trial.prepare_props(tp)
                        self.install_log.emit(t("Kopya açılıyor; sunucu hazır olana kadar bekleniyor…"))
                        self.progress.emit(0, 0)
                        ok, lines, sus = trial.run(cfg, tp, tjar, log=self.install_log.emit)
                    finally:
                        trial.cleanup(tp)
                    if not ok:
                        msg = t("Deneme başarısız: yeni yazılımla sunucu açılmadı. Asıl sunucuya dokunulmadı.")
                        if sus:
                            msg += "\n" + t("Olası sebep: {names}", names=", ".join(j for j, _n, _w in sus))
                        msg += "\n\n" + "\n".join(ln[-200:] for ln in lines[-6:])
                        self.finished_dl.emit("", msg)
                        return
                    self.install_log.emit(t("Deneme başarılı; asıl sunucu güncelleniyor…"))
                if do_backup:
                    self.app.backups.create(progress=lambda a, b: self.progress.emit(a, b))
                prog = lambda a, b: self.progress.emit(a, b)
                if info.get("installer"):
                    self.install_log.emit(t("İndiriliyor…"))
                    name = software.install_with_installer(info, cfg.server_path, cfg.get("java_path"),
                                                           self.contact, progress=prog, log=self.install_log.emit)
                else:
                    name = updater.download(info, cfg.server_path, cfg.get("jar_name"), self.contact, progress=prog)
                self.moved_to = ""
                if do_migrate:
                    self.install_log.emit(t("Klasör yeni yazılıma hazırlanıyor…"))
                    self.moved_to = switch.apply(cfg.server_path, level, old_key, info["software"])
                self.finished_dl.emit(name, "")
            except Exception as e:
                self.finished_dl.emit("", _err(e))
        self.status.setText(t("Yedek alınıyor…") if do_backup else
                            t("Kuruluyor…") if info.get("installer") else t("İndiriliyor…"))
        if info.get("installer") or do_trial:
            self.log_lbl.show()
        threading.Thread(target=run, daemon=True).start()

    def _on_done(self, name, err):
        self.bar.hide()
        self.sw.setEnabled(True)
        if err:
            self.status.setText(err)
            self.ver.setEnabled(True)
            self.btn.setEnabled(True)
            return
        old = self.app.config.get("jar_name")
        self.app.config.set("jar_name", name)
        self.log_lbl.hide()
        msg = t("Kuruldu: {jar}", jar=name)
        if not self.info.get("installer") and old and old != name:
            msg += "\n" + t("Eski jar backups/jars klasörüne taşındı.")
        if software.SOFTWARE[self.info["software"]]["modded"]:
            msg += "\n" + t("Modları Eklentiler sayfasından (mods klasörü) yönetebilirsin.")
        if getattr(self, "moved_to", ""):
            msg += "\n" + t("Eski eklenti/modlar ve boyut klasörleri şuraya taşındı: {path}", path=self.moved_to)
        self.cur_soft = self.info["software"]
        self.status.setText(msg)
        self.btn.hide()
