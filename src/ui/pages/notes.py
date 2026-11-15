"""Notlar: her sunucu için kullanıcının kendi notları (config.json'da, düz metin)."""
from datetime import datetime

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPlainTextEdit

from ..i18n import t
from ..widgets import Card, Page, label


class NotesPage(Page):
    title = "Notlar"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        card = Card("Sunucu Notları", "Yazdıkların kendiliğinden kaydedilir. Parola yazma: config.json'da düz metin durur.")
        self.state = label("", "Muted")
        card.header_actions.addWidget(self.state)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(t("Örn. eklenti ayarları, yapılacaklar, oyuncularla ilgili notlar…"))
        self.edit.textChanged.connect(self._changed)
        card.add(self.edit, 1)
        self.root.addWidget(card, 1)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(800)
        self.save_timer.timeout.connect(self.save)
        self._loading = False

    def on_show(self):
        self._loading = True
        self.edit.setPlainText(self.app.config.get("notes") or "")
        self._loading = False
        self.state.setText("")

    def _changed(self):
        if self._loading:
            return
        self.state.setText(t("Yazılıyor…"))
        self.save_timer.start()

    def save(self):
        self.app.config.set("notes", self.edit.toPlainText()[:100000])
        self.state.setText(t("Kaydedildi · {time}", time=datetime.now().strftime("%H:%M")))

    def hideEvent(self, e):
        if self.save_timer.isActive():
            self.save_timer.stop()
            self.save()
        super().hideEvent(e)
