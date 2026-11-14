import os

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QLineEdit, QMessageBox,
    QVBoxLayout,
)

from core import detect_jars, detect_version
from .i18n import t
from .widgets import ask, button, label, row


class ServerDialog(QDialog):
    """Sunucu ekle / düzenle."""

    def __init__(self, settings, profile=None, parent=None):
        super().__init__(parent)
        self.settings, self.profile = settings, profile
        self.setWindowTitle(t("Sunucuyu Düzenle") if profile else t("Sunucu Ekle"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)
        v.addWidget(label("Sunucuyu Düzenle" if profile else "Sunucu Ekle", "PageTitle"))
        v.addWidget(label("Sunucunun klasörünü seç: server.jar, Paper/Purpur/Fabric jar'ı ya da Forge/NeoForge kurulumu otomatik algılanır.", "Muted", wrap=True))

        form = QFormLayout()
        form.setSpacing(9)
        self.name = QLineEdit()
        self.name.setPlaceholderText(t("örn. Survival Sunucusu"))
        self.path = QLineEdit()
        self.path.setPlaceholderText("C:\\...\\Sunucu")
        self.path.textChanged.connect(self.on_path)
        self.jar = QComboBox()
        self.jar.setEditable(True)
        self.java = QLineEdit("java")
        self.ram_min = QLineEdit("2G")
        self.ram_max = QLineEdit("4G")
        self.detected = label("", "Muted")
        form.addRow(t("Ad"), self.name)
        form.addRow(t("Klasör"), row(self.path, button("Gözat", "ghost", self.browse), stretch_end=False))
        form.addRow("", self.detected)
        form.addRow(t("Jar dosyası"), self.jar)
        form.addRow(t("Java"), self.java)
        form.addRow(t("RAM (min / max)"), row(self.ram_min, self.ram_max, stretch_end=False))
        v.addLayout(form)

        # --- güvenlik ---
        from core.safemode import LEVEL_INFO, LEVELS
        sec = form
        sec.addRow(label("Güvenlik", "CardTitle"))
        self.safe = QComboBox()
        for i, n in enumerate(LEVELS):
            self.safe.addItem(f"{t(n)} — {t(LEVEL_INFO[i])}", i)
        self.pin_on = QCheckBox(t("Paneli açarken PIN iste"))
        self.pin1 = QLineEdit()
        self.pin2 = QLineEdit()
        for w in (self.pin1, self.pin2):
            w.setEchoMode(QLineEdit.Password)
            w.setMaxLength(12)
        self.pin1.setPlaceholderText(t("Yeni PIN (4-12 rakam)"))
        self.pin2.setPlaceholderText(t("PIN tekrar"))
        self.pin_on.toggled.connect(lambda on: (self.pin1.setEnabled(on), self.pin2.setEnabled(on)))
        sec.addRow(t("Güvenli mod"), self.safe)
        sec.addRow("", self.pin_on)
        sec.addRow(t("PIN"), row(self.pin1, self.pin2, stretch_end=False))
        self.pin_hint = label("", "Muted", wrap=True)
        sec.addRow("", self.pin_hint)
        self.pin_on.setChecked(False)
        self.pin1.setEnabled(False)
        self.pin2.setEnabled(False)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(t("Kaydet") if profile else t("Ekle"))
        btns.button(QDialogButtonBox.Ok).setProperty("variant", "primary")
        btns.button(QDialogButtonBox.Cancel).setText(t("İptal"))
        btns.button(QDialogButtonBox.Cancel).setProperty("variant", "ghost")
        btns.accepted.connect(self.validate)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

        if profile:
            self.name.setText(profile.name)
            self.path.setText(profile.server_path)
            self.jar.setCurrentText(profile.get("jar_name"))
            self.java.setText(profile.get("java_path"))
            self.ram_min.setText(profile.get("ram_min"))
            self.ram_max.setText(profile.get("ram_max"))
            self.safe.setCurrentIndex(int(profile.get("safe_mode") or 0))
            if profile.get("pin_hash"):
                self.pin_on.setChecked(True)
                self.pin_hint.setText(t("PIN ayarlı. Değiştirmek için yeni PIN yaz, aynı kalsın istiyorsan boş bırak."))

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, t("Minecraft Sunucu Klasörünü Seçin"), self.path.text())
        if d:
            self.path.setText(os.path.normpath(d))
            if not self.name.text().strip():
                self.name.setText(os.path.basename(d.rstrip("/\\")))

    def on_path(self, p):
        cur = self.jar.currentText()
        jars = detect_jars(p)
        self.jar.clear()
        self.jar.addItems(jars or ["server.jar"])
        if cur in jars:
            self.jar.setCurrentText(cur)
        ver, soft = detect_version(p)
        if not os.path.isdir(p):
            self.detected.setText(t("Klasör bulunamadı") if p else "")
        elif not jars:
            self.detected.setText(t("Bu klasörde .jar dosyası yok"))
        else:
            info = " ".join(x for x in (soft, ver) if x)
            self.detected.setText(t("Bulundu: {info}", info=info) if info else t("{n} jar dosyası bulundu", n=len(jars)))

    def validate(self):
        p = self.path.text().strip()
        if not os.path.isdir(p):
            QMessageBox.warning(self, t("Uyarı"), t("Geçerli bir klasör seçin."))
            return
        norm = os.path.normcase(os.path.abspath(p))
        for s in self.settings.servers():
            if s.server_path and os.path.normcase(os.path.abspath(s.server_path)) == norm and (
                    not self.profile or s.id != self.profile.id):
                QMessageBox.warning(self, t("Uyarı"), t("Bu klasör zaten '{name}' olarak kayıtlı.", name=s.name))
                return
        if self.pin_on.isChecked() and (self.pin1.text() or not (self.profile and self.profile.get("pin_hash"))):
            p1, p2 = self.pin1.text(), self.pin2.text()
            if not (p1.isdigit() and 4 <= len(p1) <= 12):
                QMessageBox.warning(self, t("Uyarı"), t("PIN 4-12 rakamdan oluşmalı."))
                return
            if p1 != p2:
                QMessageBox.warning(self, t("Uyarı"), t("PIN'ler eşleşmiyor."))
                return
        if not detect_jars(p) and not ask(self, t("Klasörde .jar dosyası bulunamadı. Yine de kaydedilsin mi?"), t("Onay")):
            return
        self.accept()

    def save(self):
        vals = {
            "name": self.name.text().strip() or os.path.basename(self.path.text().rstrip("/\\")),
            "jar_name": self.jar.currentText().strip() or "server.jar",
            "java_path": self.java.text().strip() or "java",
            "ram_min": self.ram_min.text().strip() or "2G",
            "ram_max": self.ram_max.text().strip() or "4G",
            "safe_mode": self.safe.currentData(),
        }
        from core.safemode import hash_pin
        if not self.pin_on.isChecked():
            vals["pin_hash"] = ""
        elif self.pin1.text():
            vals["pin_hash"] = hash_pin(self.pin1.text())
        path = self.path.text().strip()
        if self.profile:
            self.profile.data.update(vals, server_path=path)
            self.profile.save()
            return self.profile
        return self.settings.add_server(path, **vals)
