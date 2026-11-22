"""Yeni Sunucu Oluştur penceresi: yazılım ve sürüm seç, temel ayarları gir, Spypaper indirip kursun."""
import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLineEdit, QProgressBar, QSpinBox, QVBoxLayout,
)

from core import N_, creator, software
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row


def default_parent():
    home = os.path.expanduser("~")
    for d in (os.path.join(home, "Documents"), os.path.join(home, "Belgeler"), home):
        if os.path.isdir(d):
            return os.path.join(d, "Minecraft Sunucuları")
    return os.path.join(home, "Minecraft Sunucuları")


class NewServerDialog(QDialog):
    versions_ready = Signal(str, list, str)
    progress = Signal(int, int)
    logged = Signal(str)
    done = Signal(str, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.profile = None
        self.setWindowTitle(t("Yeni Sunucu Oluştur"))
        self.setMinimumWidth(600)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Yeni Sunucu Oluştur", "PageTitle"))
        v.addWidget(label("Spypaper seçtiğin sunucu yazılımını resmî kaynağından indirir, klasörü ve temel ayarları hazırlar.",
                          "Muted", wrap=True))

        form = QFormLayout()
        form.setSpacing(8)
        self.name = QLineEdit(t("Yeni Sunucu"))
        self.name.textChanged.connect(self._update_path)
        self.parent_dir = default_parent()
        self.path = QLineEdit()
        self.path.setObjectName("Mono")
        self._update_path()
        form.addRow(t("Sunucu adı"), self.name)
        form.addRow(t("Klasör"), row(self.path, button("Gözat", "ghost", self._browse), stretch_end=False))

        self.sw = QComboBox()
        for key, info in software.SOFTWARE.items():
            self.sw.addItem(info["name"], key)
        self.sw.currentIndexChanged.connect(self._load_versions)
        self.ver = QComboBox()
        self.ver.setMinimumWidth(180)
        self.ver.currentTextChanged.connect(self._ver_changed)
        self.ver_lbl = label("Minecraft sürümü")
        form.addRow(t("Yazılım"), row(self.sw, self.ver_lbl, self.ver, stretch_end=True))
        self.java_lbl = label("", "Muted", wrap=True)
        form.addRow("", self.java_lbl)

        self.ram = QComboBox()
        for r in ("2G", "3G", "4G", "6G", "8G", "12G", "16G"):
            self.ram.addItem(r)
        self.ram.setCurrentText("4G")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(25565)
        self.players = QSpinBox()
        self.players.setRange(1, 1000)
        self.players.setValue(20)
        form.addRow(t("En fazla RAM"), row(self.ram, label("Port"), self.port, label("En fazla oyuncu"), self.players,
                                          stretch_end=True))
        self.motd = QLineEdit("A Minecraft Server")
        form.addRow(t("MOTD"), self.motd)
        self.mode = QComboBox()
        for k, n in zip(creator.GAMEMODES, (N_("Hayatta Kalma"), N_("Yaratıcı"), N_("Macera"))):
            self.mode.addItem(t(n), k)
        self.diff = QComboBox()
        for k, n in zip(creator.DIFFICULTIES, (N_("Barışçıl"), N_("Kolay"), N_("Normal"), N_("Zor"))):
            self.diff.addItem(t(n), k)
        self.diff.setCurrentIndex(2)
        self.mode_row = row(self.mode, label("Zorluk"), self.diff, stretch_end=True)
        form.addRow(t("Oyun modu"), self.mode_row)
        self.online = QCheckBox(t("Yalnızca Minecraft hesabı olanlar girebilsin (online-mode)"))
        self.online.setChecked(True)
        self.white = QCheckBox(t("Whitelist açık olsun (yalnızca izin verilen oyuncular)"))
        form.addRow("", self.online)
        form.addRow("", self.white)
        v.addLayout(form)
        from .world_picker import WorldPicker
        self.world_title = label("Dünya", "CardTitle")
        v.addWidget(self.world_title)
        self.world = WorldPicker(settings.get("update_contact") or "")
        v.addWidget(self.world)
        self.proxy_note = label("Velocity bir proxy'dir: dünyası yoktur, oyuncuları ağdaki Paper sunucularına yönlendirir. "
                                "Oluşturduktan sonra bir kez başlat, ardından Velocity Ağı sekmesinden sunucularını ekle.",
                                "Muted", wrap=True)
        self.proxy_note.hide()
        v.addWidget(self.proxy_note)
        self.form = form

        self.eula = QCheckBox(t("Minecraft EULA'sını okudum ve kabul ediyorum"))
        self.eula_link = label("", "Muted")
        self.eula_link.setText("<a href='https://aka.ms/MinecraftEULA' style='color:%s'>https://aka.ms/MinecraftEULA</a>"
                          % TOKENS["accent"])
        self.eula_link.setOpenExternalLinks(True)
        self.eula_link.setTextFormat(Qt.RichText)
        v.addLayout(row(self.eula, self.eula_link, stretch_end=True))

        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.status = label("", "Muted", wrap=True)
        v.addWidget(self.status)
        self.btn = button("Oluştur", "primary", self.create)
        self.btn.setEnabled(False)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), self.btn, stretch_end=False))

        self.versions_ready.connect(self._on_versions)
        self.progress.connect(lambda a, b: (self.bar.setMaximum(max(b, 1)), self.bar.setValue(a)))
        self.logged.connect(lambda s: self.status.setText(s[-160:]))
        self.done.connect(self._on_done)
        self._load_versions()

    # ------------------------------------------------------------------
    def _update_path(self, *_):
        self.path.setText(os.path.join(self.parent_dir, creator.safe_folder_name(self.name.text())))

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, t("Sunucunun oluşturulacağı klasörü seç"), self.parent_dir)
        if d:
            self.parent_dir = d
            self._update_path()

    def _proxy_ui(self, proxy):
        self.ver_lbl.setText(t("Sürüm") if proxy else t("Minecraft sürümü"))
        for w in (self.world_title, self.world, self.white, self.eula, self.eula_link):
            w.setVisible(not proxy)
        lbl = self.form.labelForField(self.mode_row)
        for i in range(self.mode_row.count()):
            it = self.mode_row.itemAt(i).widget()
            if it:
                it.setVisible(not proxy)
        if lbl:
            lbl.setVisible(not proxy)
        self.proxy_note.setVisible(proxy)
        if proxy and self.port.value() == 25565:
            self.port.setValue(25577)
        elif not proxy and self.port.value() == 25577:
            self.port.setValue(25565)

    def _load_versions(self, *_):
        key = self.sw.currentData()
        self._proxy_ui(software.is_proxy_key(key))
        self.ver.clear()
        self.btn.setEnabled(False)
        self.status.setText(t("{name} sürümleri alınıyor…", name=software.SOFTWARE[key]["name"]))
        contact = self.settings.get("update_contact")

        def work():
            try:
                self.versions_ready.emit(key, software.list_versions(key, contact), "")
            except Exception as e:
                self.versions_ready.emit(key, [], t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_versions(self, key, vers, err):
        if key != self.sw.currentData():
            return
        if err or not vers:
            self.status.setText(err or t("Bu yazılım için sürüm bulunamadı."))
            return
        self.ver.addItems(vers)
        self.status.setText("")
        self.btn.setEnabled(True)

    def _ver_changed(self, v):
        if hasattr(self, "world"):
            self.world.set_server_version(v)
        if v and software.is_proxy_key(self.sw.currentData()):
            self.java_lbl.setText(t("Velocity için en az Java {n} gerekir.", n=21))
        elif v:
            self.java_lbl.setText(t("Bu sürüm için en az Java {n} gerekir.", n=creator.java_hint(v)))

    def create(self):
        path = self.path.text().strip()
        if not self.name.text().strip() or not path:
            self.status.setText(t("Sunucu adı ve klasör gerekli."))
            return
        if os.path.isdir(path) and os.listdir(path):
            self.status.setText(t("Seçilen klasör boş değil: {path}", path=path))
            return
        proxy = software.is_proxy_key(self.sw.currentData())
        err = None if proxy else self.world.validate()
        if err:
            self.status.setText(err)
            return
        if not proxy and not self.eula.isChecked():
            self.status.setText(t("Sunucuyu çalıştırabilmek için Minecraft EULA'sını kabul etmen gerekiyor."))
            return
        for w in (self.btn, self.sw, self.ver):
            w.setEnabled(False)
        self.bar.show()
        opts = dict(motd=self.motd.text().strip() or "A Minecraft Server", port=self.port.value(),
                    max_players=self.players.value(), gamemode=self.mode.currentData(),
                    difficulty=self.diff.currentData(), online_mode=self.online.isChecked(),
                    whitelist=self.white.isChecked(), accept_eula=True,
                    java="java", contact=self.settings.get("update_contact"))
        if proxy:
            pass
        elif self.world.is_template():
            opts["template"] = self.world.template()
        else:
            opts["world"] = self.world.world_options()
        key, ver = self.sw.currentData(), self.ver.currentText()
        self.status.setText(t("İndiriliyor…"))

        def work():
            try:
                start = creator.create(path, key, ver, progress=self.progress.emit, log=self.logged.emit, **opts)
                self.done.emit(start, "")
            except Exception as e:
                self.done.emit("", t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_done(self, start, err):
        self.bar.hide()
        if err:
            self.status.setStyleSheet(f"color:{TOKENS['danger']}")
            self.status.setText(err)
            for w in (self.btn, self.sw, self.ver):
                w.setEnabled(True)
            return
        ram = self.ram.currentText()
        ram_min = "2G" if int(ram[:-1]) > 2 else "1G"
        self.profile = self.settings.add_server(self.path.text().strip(), self.name.text().strip(),
                                                jar_name=start, ram_max=ram, ram_min=ram_min)
        self.accept()
