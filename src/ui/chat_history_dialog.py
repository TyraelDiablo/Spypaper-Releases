"""Esplora → Geçmiş: kayıtlı sohbetleri aç, sil. Çekirdek: core/esplora_chats.py."""
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .i18n import t
from .msgbox import ask
from .widgets import button, label


def _when(iso):
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    if d.date() == datetime.now().date():
        return t("Bugün {time}", time=d.strftime("%H:%M"))
    return d.strftime("%d.%m.%Y %H:%M")


class ChatHistoryDialog(QDialog):
    """Seçilen sohbetin kimliği self.chosen'da döner (Aç'a basılırsa)."""

    def __init__(self, store, settings, current_id=None, parent=None):
        super().__init__(parent)
        self.store, self.settings, self.current_id = store, settings, current_id
        self.chosen = None
        self.setWindowTitle(t("Sohbet Geçmişi"))
        self.resize(620, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Sohbet Geçmişi", "PageTitle"))
        v.addWidget(label("Sohbetler bu sunucu için bu bilgisayarda saklanır. Görseller kaydedilmez. "
                          "Bir sohbeti açınca kaldığın yerden devam edersin.", "Muted", wrap=True))
        self.save_cb = QCheckBox(t("Sohbetleri bu bilgisayarda kaydet"))
        self.save_cb.setChecked(bool(settings.get("esplora_save_chats")))
        self.save_cb.toggled.connect(lambda on: settings.set("esplora_save_chats", bool(on)))
        v.addWidget(self.save_cb)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Başlıkta ara…"))
        self.search.textChanged.connect(self.fill)
        v.addWidget(self.search)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(False)
        self.list.itemDoubleClicked.connect(lambda _i: self.open())
        self.list.currentRowChanged.connect(lambda _r: self._buttons())
        v.addWidget(self.list, 1)
        self.empty = label("Kayıtlı sohbet yok.", "Muted")
        v.addWidget(self.empty)
        h = QHBoxLayout()
        self.del_all_btn = button("Tümünü sil", "ghost", self.delete_all)
        h.addWidget(self.del_all_btn)
        h.addStretch(1)
        self.del_btn = button("Sil", "ghost", self.delete)
        h.addWidget(self.del_btn)
        h.addWidget(button("Kapat", "ghost", self.reject))
        self.open_btn = button("Aç", "primary", self.open)
        h.addWidget(self.open_btn)
        v.addLayout(h)
        self.fill()

    def fill(self, *_):
        q = self.search.text().strip().lower()
        chats = self.store.list()
        self.list.clear()
        for c in chats:
            if q and q not in (c["title"] or "").lower():
                continue
            mark = "  · " + t("şu an açık") if c["id"] == self.current_id else ""
            text = (c["title"] or t("(başlıksız)")) + "\n" + _when(c["updated"]) + "  · " + \
                t("{n} soru", n=c["count"]) + mark
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, c["id"])
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.empty.setVisible(not chats)
        self.del_all_btn.setEnabled(bool(chats))
        self._buttons()

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _buttons(self):
        on = self._selected() is not None
        self.open_btn.setEnabled(on)
        self.del_btn.setEnabled(on)

    def open(self):
        cid = self._selected()
        if cid:
            self.chosen = cid
            self.accept()

    def delete(self):
        cid = self._selected()
        if cid and ask(self, t("Bu sohbet silinsin mi?"), t("Sohbet Geçmişi"), yes=t("Sil"), danger=True):
            self.store.delete(cid)
            self.fill()

    def delete_all(self):
        if ask(self, t("Bu sunucunun bütün kayıtlı sohbetleri silinsin mi? Bu geri alınamaz."), t("Sohbet Geçmişi"),
               yes=t("Tümünü sil"), danger=True):
            self.store.delete_all()
            self.fill()
