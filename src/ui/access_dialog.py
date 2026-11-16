"""Esplora Veri İzinleri penceresi (sunucu profilinde "esplora_access"). Çekirdek: core/esplora_access.py."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from core import esplora_access as EA

from .i18n import t
from .widgets import button, label

MIXED = "mixed"
ROW_H = 40


class AccessDialog(QDialog):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle(t("Veri İzinleri"))
        self.resize(760, 620)
        self.levels = EA.levels(profile)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Esplora hangi verilere ulaşabilir?", "PageTitle"))
        v.addWidget(label("Erişim yok: hiç verilmez. Onaylı: Esplora isteyince sohbette sana sorulur. Onaysız: sormadan "
                          "verilir. Verilen her şey seçtiğin yapay zeka sağlayıcısına gönderilir. Ayar değiştirme ve "
                          "komut önerme her zaman düğmeyle onaylanır.", "Muted", wrap=True))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([t("Veri"), t("İzin")])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionMode(QTreeWidget.NoSelection)
        self.tree.setFocusPolicy(Qt.NoFocus)
        hh = self.tree.header()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 170)
        self.combos, self.cat_combos = {}, {}
        for cat, cname, items in EA.TREE:
            top = QTreeWidgetItem([t(cname), ""])
            top.setSizeHint(0, QSize(0, ROW_H))
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            cc = self._combo(write=all(kind == "write" for _k, _n, kind, _d, _a in items), mixed=True)
            cc.activated.connect(lambda _i, c=cat, box=cc: self._set_category(c, box.currentData()))
            self.tree.setItemWidget(top, 1, cc)
            self.cat_combos[cat] = (cc, items)
            for key, name, kind, _d, _a in items:
                it = QTreeWidgetItem([t(name), ""])
                it.setSizeHint(0, QSize(0, ROW_H))
                it.setToolTip(0, key)
                top.addChild(it)
                cb = self._combo(write=(kind == "write"))
                cb.setCurrentIndex(max(0, cb.findData(self.levels[key])))
                cb.currentIndexChanged.connect(lambda _i, k=key, box=cb: self._set(k, box.currentData()))
                self.tree.setItemWidget(it, 1, cb)
                self.combos[key] = cb
            top.setExpanded(True)
            self._sync_category(cat)
        v.addWidget(self.tree, 1)
        h = QHBoxLayout()
        h.addWidget(button("Varsayılanlara dön", "ghost", self.defaults))
        h.addStretch(1)
        h.addWidget(button("İptal", "ghost", self.reject))
        h.addWidget(button("Kaydet", "primary", self.save))
        v.addLayout(h)

    def _combo(self, write=False, mixed=False):
        cb = QComboBox()
        for lv in EA.LEVELS:
            if write and lv == "allow":
                continue
            cb.addItem(t(EA.LEVEL_NAMES[lv]), lv)
        if mixed:
            cb.addItem(t("Karışık"), MIXED)
        cb.setFocusPolicy(Qt.StrongFocus)
        return cb

    def _set(self, key, lv):
        self.levels[key] = lv
        for cat, (_cc, items) in self.cat_combos.items():
            if any(k == key for k, *_r in items):
                self._sync_category(cat)

    def _set_category(self, cat, lv):
        if lv == MIXED:
            self._sync_category(cat)
            return
        _cc, items = self.cat_combos[cat]
        for key, _n, kind, _d, _a in items:
            val = "ask" if kind == "write" and lv == "allow" else lv
            cb = self.combos[key]
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(val)))
            cb.blockSignals(False)
            self.levels[key] = val
        self._sync_category(cat)

    def _sync_category(self, cat):
        cc, items = self.cat_combos[cat]
        vals = {self.levels[k] for k, *_r in items}
        cc.blockSignals(True)
        cc.setCurrentIndex(cc.findData(vals.pop() if len(vals) == 1 else MIXED))
        cc.blockSignals(False)

    def defaults(self):
        for key, (_n, _kind, default, _a) in EA.ITEMS.items():
            cb = self.combos[key]
            cb.blockSignals(True)
            cb.setCurrentIndex(max(0, cb.findData(default)))
            cb.blockSignals(False)
            self.levels[key] = default
        for cat in self.cat_combos:
            self._sync_category(cat)

    def save(self):
        for key, lv in self.levels.items():
            EA.set_level(self.profile, key, lv)
        self.accept()
