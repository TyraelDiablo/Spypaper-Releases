"""Yapay zeka ayarları: sağlayıcı, model, API anahtarı, çevirmen."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout

from core import ai
from core.secrets import mask, unprotect
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row


class AIDialog(QDialog):
    tested = Signal(str, bool)
    models_ready = Signal(list, str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        cfg = ai.get_cfg(settings)
        self.setWindowTitle(t("Yapay Zeka Ayarları"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Yapay Zeka Ayarları", "PageTitle"))
        v.addWidget(label("Esplora bu ayarları kullanır. Anahtar bu bilgisayarda Windows hesabına bağlı olarak şifrelenir.", "Muted", wrap=True))
        v.addWidget(label("Spypaper bir yapay zeka sağlayıcısı değildir. Sağlayıcıya ve modele kendi hesabınızdan, kendi "
                          "ücretinizle bağlanırsınız; Spypaper yalnızca bu bağlantıyı kolaylaştırır.", "Muted", wrap=True))

        form = QFormLayout()
        form.setSpacing(9)
        self.provider = QComboBox()
        for k, p in ai.PROVIDERS.items():
            self.provider.addItem(p["name"], k)
        self.provider.setCurrentIndex(max(0, self.provider.findData(cfg["provider"])))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.NoInsert)
        self.model.setCurrentText(cfg["model"])
        self.base = QLineEdit(cfg["base_url"])
        self.base.setPlaceholderText("https://api.openai.com/v1  ·  http://localhost:11434/v1 (Ollama)")
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        old = unprotect(cfg["key"])
        self.key.setPlaceholderText(t("Kayıtlı: {k}", k=mask(old)) if old else "sk-…")
        form.addRow(t("Sağlayıcı"), self.provider)
        form.addRow(t("Model"), row(self.model, button("Modelleri Getir", "ghost", self.fetch_models,
                                                       tooltip="Bu anahtarla kullanılabilen modelleri listeler"),
                                    stretch_end=False))
        self.model.setMinimumWidth(260)
        form.addRow(t("Sunucu adresi"), self.base)
        form.addRow(t("API anahtarı"), self.key)
        v.addLayout(form)
        self.status = label("", "Muted", wrap=True)
        v.addWidget(self.status)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText(t("Kaydet"))
        btns.button(QDialogButtonBox.Cancel).setText(t("İptal"))
        btns.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        btns.button(QDialogButtonBox.Cancel).setProperty("variant", "ghost")
        btns.accepted.connect(self.save)
        btns.rejected.connect(self.reject)
        v.addLayout(row(button("Bağlantıyı Test Et", "ghost", self.test), None, btns, stretch_end=False))
        self.tested.connect(self._on_test)
        self.models_ready.connect(self._on_models)
        self._provider_changed()

    def _provider_changed(self, *_):
        is_openai = self.provider.currentData() == "openai"
        self.base.setEnabled(is_openai)
        cur = self.model.currentText().strip()
        if not cur or cur in [p["model"] for p in ai.PROVIDERS.values()] or "gemini-2.5" in cur:
            self.model.clear()
            self.model.setCurrentText(ai.PROVIDERS[self.provider.currentData()]["model"])

    def _write(self):
        ai.save_cfg(self.settings, self.provider.currentData(), self.model.currentText(), self.base.text(),
                    api_key=self.key.text() or None)

    def save(self):
        self._write()
        self.accept()

    def test(self):
        self._write()
        self.status.setText(t("Test ediliyor…"))
        def work():
            try:
                new = ai.test(self.settings)
                msg = t("Bağlantı başarılı.")
                if new:
                    msg += " " + t("Eski model kapatılmış; {model} modeline geçildi.", model=new)
                self.tested.emit(msg, True)
            except Exception as e:
                self.tested.emit(t(e.template, **e.kw) if hasattr(e, "template") else str(e), False)
        threading.Thread(target=work, daemon=True).start()

    def fetch_models(self):
        self._write()
        self.status.setText(t("Modeller alınıyor…"))
        cfg = ai.get_cfg(self.settings)

        def work():
            try:
                self.models_ready.emit(ai.list_models(cfg), "")
            except Exception as e:
                self.models_ready.emit([], t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_models(self, models, err):
        if err:
            self._status(err, False)
            return
        cur = self.model.currentText()
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(cur if cur in models else (models[0] if models else cur))
        self._status(t("{n} model bulundu.", n=len(models)), True)

    def _on_test(self, msg, ok):
        if ok:
            self.model.setCurrentText(ai.get_cfg(self.settings)["model"])   # otomatik geçildiyse göster
        self._status(msg, ok)

    def _status(self, msg, ok):
        self.status.setText(msg)
        self.status.setStyleSheet(f"color:{TOKENS['accent'] if ok else TOKENS['danger']}")
