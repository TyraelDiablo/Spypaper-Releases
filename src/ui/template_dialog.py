"""Tehlikeli Bölge → Dünyayı Taslakla Değiştir: harita seçimi."""
from PySide6.QtWidgets import QDialog, QVBoxLayout

from .i18n import t
from .widgets import button, label, row
from .world_picker import WorldPicker


class TemplateDialog(QDialog):
    def __init__(self, contact, server_version, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Dünyayı Taslakla Değiştir"))
        self.setMinimumSize(640, 520)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Dünyayı Taslakla Değiştir", "PageTitle"))
        v.addWidget(label("Şu anki dünya silinmez; adının sonuna \"-yedek-tarih\" eklenerek sunucu klasöründe saklanır.",
                          "Muted", wrap=True))
        self.picker = WorldPicker(contact)
        self.picker.tabs.hide()
        self.picker.stack.setCurrentIndex(1)
        self.picker.set_server_version(server_version)
        self.picker.load()
        v.addWidget(self.picker, 1)
        self.err = label("", "Muted", wrap=True, raw=True)
        v.addWidget(self.err)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), button("Devam", "danger", self._ok), stretch_end=False))

    def _ok(self):
        e = self.picker.validate()
        if e:
            self.err.setText(e)
            return
        self.accept()

    def chosen(self):
        return self.picker.template()
