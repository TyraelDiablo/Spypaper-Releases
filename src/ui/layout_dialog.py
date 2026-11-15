"""Panel Düzeni: sunucu panelindeki sekmelerin sırası/görünürlüğü ve gösterge panelinin kartları."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout,
)

from .i18n import t
from .widgets import button, label


class LayoutDialog(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        from .window import PAGES, page_order
        from .pages.dashboard import DASH_CARDS
        self.ctl, self.PAGES, self.DASH = ctl, PAGES, DASH_CARDS
        self.setWindowTitle(t("Panel Düzeni"))
        self.setMinimumWidth(620)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Panel Düzeni", "PageTitle"))

        cols = QHBoxLayout()
        cols.setSpacing(18)
        left = QVBoxLayout()
        left.addWidget(label("Sekmeler", "CardTitle"))
        left.addWidget(label("Sürükleyerek sırala, işareti kaldırarak gizle. İlk görünen sekme sunucu açılınca gelir.",
                             "Muted", wrap=True))
        self.pages = QListWidget()
        self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setDefaultDropAction(Qt.MoveAction)
        self.pages.setMinimumHeight(330)
        left.addWidget(self.pages, 1)
        cols.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(label("Gösterge paneli kartları", "CardTitle"))
        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        self.cards = {}
        for i, (key, title) in enumerate(DASH_CARDS):
            cb = QCheckBox(t(title))
            cb.setCursor(Qt.PointingHandCursor)
            self.cards[key] = cb
            grid.addWidget(cb, i, 0)
        right.addLayout(grid)
        right.addStretch(1)
        cols.addLayout(right, 1)
        v.addLayout(cols, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(button("Varsayılana Dön", "ghost", self.defaults))
        bottom.addStretch(1)
        bottom.addWidget(button("İptal", "ghost", self.reject))
        bottom.addWidget(button("Kaydet", "primary", self.save))
        v.addLayout(bottom)

        order, hidden = page_order(ctl.settings)
        self._fill(order, hidden, set(ctl.settings.get("dashboard_hidden") or []))

    def _fill(self, order, hidden, dash_hidden):
        self.pages.clear()
        for i in order:
            cls = self.PAGES[i]
            it = QListWidgetItem("  ⋮⋮   " + t(cls.title))
            it.setData(Qt.UserRole, cls.__name__)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Unchecked if i in hidden else Qt.Checked)
            self.pages.addItem(it)
        for key, cb in self.cards.items():
            cb.setChecked(key not in dash_hidden)

    def defaults(self):
        self._fill(list(range(len(self.PAGES))), set(), set())

    def save(self):
        items = [self.pages.item(i) for i in range(self.pages.count())]
        order = [it.data(Qt.UserRole) for it in items]
        hidden = [it.data(Qt.UserRole) for it in items if it.checkState() != Qt.Checked]
        if len(hidden) == len(order):
            from .msgbox import warning
            warning(self, t("Uyarı"), t("En az bir sekme görünür kalmalı."))
            return
        s = self.ctl.settings
        default = [c.__name__ for c in self.PAGES]
        s.set("page_order", [] if order == default else order)
        s.set("hidden_pages", hidden)
        s.set("dashboard_hidden", [k for k, cb in self.cards.items() if not cb.isChecked()])
        self.accept()
        self.ctl.rebuild_later()
