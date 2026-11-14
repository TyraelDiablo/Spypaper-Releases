import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QTableWidgetItem

from core import N_
from core.logwatch import KINDS, parse_file
from .dashboard import kind_color, event_text
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, button, label, row, segmented, table

FILTERS = [
    (N_("Tümü"), None),
    (N_("Giriş/Çıkış"), {"join", "leave", "start", "stop"}),
    (N_("Sohbet"), {"chat"}),
    (N_("Ölüm"), {"death"}),
    (N_("Başarım"), {"adv"}),
    (N_("Komut"), {"cmd"}),
    (N_("Uyarı/Hata"), {"warn", "error", "lag"}),
]
MAX_ROWS = 3000


class LogsPage(Page):
    title = "Günlük"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.kinds = None
        self.source = None          # None = canlı latest.log, yoksa arşiv yolu
        self.archive_events = []
        self._gen = None
        self._shown = 0

        card = Card()
        self.files = QComboBox()
        self.files.setMinimumWidth(220)
        self.files.currentIndexChanged.connect(self.on_file)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Oyuncu ya da metin ara…"))
        self.search.setFixedWidth(240)
        self.search.textChanged.connect(self.rebuild)
        self.seg = segmented([n for n, _ in FILTERS], self.on_filter)
        card.add(row(self.files, None, self.search, stretch_end=False))
        card.add(row(self.seg))

        self.table = table(["Saat", "Tür", "Oyuncu", "Mesaj"], stretch_col=3)
        self.table.setWordWrap(False)
        self.table.cellDoubleClicked.connect(self.copy_raw)
        card.add(self.table, 1)
        self.info_lbl = label("", "Muted")
        self.follow = button(t("Canlı takip: {state}", state=t("açık")), "ghost", self.toggle_follow)
        self.following = True
        card.add(row(self.info_lbl, None, self.follow, stretch_end=False))
        self.root.addWidget(card, 1)

        bridge.events.connect(self.on_events)

    # --- kaynak ---
    def on_show(self):
        self.fill_files()
        self.rebuild()

    def on_server_path_changed(self):
        self.source = None
        self.on_show()

    def fill_files(self):
        self.files.blockSignals(True)
        cur = self.source
        self.files.clear()
        self.files.addItem("● " + t("Canlı (latest.log)"), None)
        for path, d in self.app.logs.archives():
            self.files.addItem(f"{d:%d.%m.%Y}  ·  {os.path.basename(path)}", path)
        idx = max(0, self.files.findData(cur)) if cur else 0
        self.files.setCurrentIndex(idx)
        self.files.blockSignals(False)

    def on_file(self, i):
        self.source = self.files.itemData(i)
        self.archive_events = parse_file(self.source) if self.source else []
        self.follow.setVisible(self.source is None)
        self.rebuild()

    def on_filter(self, i):
        self.kinds = FILTERS[i][1]
        self.rebuild()

    def toggle_follow(self):
        self.following = not self.following
        self.follow.setText(t("Canlı takip: {state}", state=t("açık") if self.following else t("kapalı")))
        if self.following:
            self.table.scrollToBottom()

    # --- tablo ---
    def _events(self):
        return self.app.logs.events if self.source is None else self.archive_events

    def _match(self, e):
        if self.kinds is not None and e.kind not in self.kinds:
            return False
        if self.kinds is None and e.kind == "info":
            return False   # "Tümü" gürültüyü (sıradan INFO) göstermez
        q = self.search.text().strip().lower()
        return not q or q in e.player.lower() or q in e.text.lower()

    def _append(self, events):
        tb = self.table
        tb.setUpdatesEnabled(False)
        for e in events:
            r = tb.rowCount()
            tb.insertRow(r)
            vals = (f"{e.time:%H:%M:%S}", t(KINDS[e.kind]), e.player, event_text(e, self.app))
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 1:
                    it.setForeground(QColor(kind_color(e.kind)))
                if c == 0:
                    it.setData(Qt.UserRole, e.raw)
                    it.setForeground(QColor(TOKENS["text_muted"]))
                tb.setItem(r, c, it)
        while tb.rowCount() > MAX_ROWS:
            tb.removeRow(0)
        tb.setUpdatesEnabled(True)
        if self.following and self.source is None:
            tb.scrollToBottom()

    def rebuild(self):
        evs = self._events()
        self._gen = self.app.logs.generation
        self._shown = len(self.app.logs.events)
        self.table.setRowCount(0)
        rows = [e for e in evs if self._match(e)]
        self._append(rows[-MAX_ROWS:])
        self._info(len(rows), len(evs))
        if self.source is not None:
            self.table.scrollToTop()

    def _info(self, shown, total):
        src = "latest.log" if self.source is None else os.path.basename(self.source)
        self.info_lbl.setText(t("{src} · {shown} olay gösteriliyor · toplam {total} satır  —  çift tıkla: ham satırı kopyala",
                                src=src, shown=shown, total=total))

    def on_events(self, new):
        if self.source is not None or not self.isVisible():
            return
        if self._gen != self.app.logs.generation:
            self.rebuild()
            return
        evs = self.app.logs.events
        fresh = [e for e in evs[self._shown:] if self._match(e)]
        self._shown = len(evs)
        if fresh:
            self._append(fresh)
        self._info(self.table.rowCount(), len(evs))

    def copy_raw(self, r, _c):
        it = self.table.item(r, 0)
        if it:
            QApplication.clipboard().setText(it.data(Qt.UserRole) or "")
