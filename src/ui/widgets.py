"""Ortak bileşenler ve yardımcılar."""
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QButtonGroup,
)

from .i18n import t
from .theme import TOKENS


class ServerBridge(QObject):
    """core.ServerProcess callback'lerini Qt sinyallerine çevirir (thread-güvenli)."""
    line = Signal(str)
    state = Signal(str)
    events = Signal(list)   # LogWatcher'dan yeni olaylar

    def __init__(self, server):
        super().__init__()
        self.server = server
        server.on_line = self.line.emit
        server.on_state = self.state.emit

    def detach(self):
        if self.server.on_line == self.line.emit:
            self.server.on_line = None
            self.server.on_state = None


def button(text, variant="ghost", on_click=None, tooltip=None):
    """text otomatik çevrilir (t)."""
    b = QPushButton(t(text).replace("&", "&&"))
    b.setProperty("variant", variant)
    b.setCursor(Qt.PointingHandCursor)
    if on_click:
        b.clicked.connect(on_click)
    if tooltip:
        b.setToolTip(t(tooltip))
    return b


def label(text="", name=None, wrap=False, raw=False):
    """text otomatik çevrilir (t). raw=True: kullanıcı verisi (sunucu adı, yol…), çevrilmez."""
    lbl = QLabel(text if raw or not text else t(text))
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


class Card(QFrame):
    def __init__(self, title=None, subtitle=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 16)
        self.body.setSpacing(10)
        if title:
            head = QHBoxLayout()
            col = QVBoxLayout()
            col.setSpacing(2)
            self.title_lbl = col.addWidget(label(title, "CardTitle")) or col.itemAt(0).widget()
            self.subtitle_lbl = None
            if subtitle:
                self.subtitle_lbl = label(subtitle, "Muted", wrap=True)
                col.addWidget(self.subtitle_lbl)
            head.addLayout(col, 1)
            self.header_actions = QHBoxLayout()
            self.header_actions.setSpacing(6)
            head.addLayout(self.header_actions)
            self.body.addLayout(head)

    def end(self):
        self.body.addStretch(1)

    def add(self, w, stretch=0):
        if isinstance(w, QWidget):
            self.body.addWidget(w, stretch)
        else:
            self.body.addLayout(w, stretch)
        return w


def row(*widgets, spacing=8, stretch_end=True):
    h = QHBoxLayout()
    h.setSpacing(spacing)
    h.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        if w is None:
            h.addStretch(1)
        elif isinstance(w, QWidget):
            h.addWidget(w)
        else:
            h.addLayout(w)
    if stretch_end:
        h.addStretch(1)
    return h


class Page(QWidget):
    """Sayfa tabanı. title: üst barda gösterilir."""
    title = ""

    def __init__(self, app, bridge, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.app = app
        self.bridge = bridge
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 18, 22, 22)
        self.root.setSpacing(14)

    def on_show(self):
        """Sayfa açıldığında çağrılır."""

    def on_server_path_changed(self):
        self.on_show()

    # --- mesajlar ---
    # text/title çevrilir; yer tutuculu metinleri çağıran t(...) ile hazırlar.
    def info(self, text, title="Bilgi"):
        from . import msgbox
        msgbox.info(self, t(title), t(text))

    def warn(self, text, title="Uyarı"):
        from . import msgbox
        msgbox.warning(self, t(title), t(text))

    def error(self, text, title="Hata"):
        from . import msgbox
        msgbox.error(self, t(title), t(text))

    def confirm(self, text, title="Onay"):
        return ask(self, t(text), t(title))

    def send(self, cmd, confirmed=False):
        """Kullanıcı komutu gönderir: güvenli mod denetimi -> sunucu. Hata olursa gösterir."""
        return send_guarded(self, self.app, cmd, confirmed)

    def read_only(self):
        """Güvenli mod Yüksek ise uyarı gösterip True döner (değişiklik yapılmasın)."""
        if int(self.app.config.get("safe_mode") or 0) >= 3:
            self.warn("Güvenli mod (Yüksek) açık: değişiklik yapılamaz.", "Güvenli mod")
            return True
        return False


def send_guarded(parent, app, cmd, confirmed=False):
    from core import ServerError
    from core.safemode import check
    verdict, why = check(app.config.get("safe_mode"), cmd)
    if verdict == "block":
        QMessageBox.warning(parent, t("Güvenli mod"), t(why) + "\n\n" + cmd)
        return False
    if verdict == "confirm" and not confirmed:
        msg = (t(why) + "\n\n" if why else "") + t("Bu komut gönderilsin mi?") + "\n" + cmd
        if not ask(parent, msg, t("Güvenli mod")):
            return False
    try:
        app.server.send(cmd)
        return True
    except ServerError as e:
        QMessageBox.critical(parent, t("Hata"), err_text(e))
        return False


def err_text(e):
    """ServerError'u kullanıcının dilinde metne çevirir."""
    tpl = getattr(e, "template", None)
    return t(tpl, **e.kw) if tpl else t(str(e))


def ask(parent, text, title):
    from .msgbox import ask as _ask
    return _ask(parent, text, title)


def table(headers, stretch_col=1):
    tb = QTableWidget(0, len(headers))
    tb.setHorizontalHeaderLabels([t(h) for h in headers])
    tb.verticalHeader().setVisible(False)
    tb.setSelectionBehavior(QAbstractItemView.SelectRows)
    tb.setSelectionMode(QAbstractItemView.SingleSelection)
    tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tb.setAlternatingRowColors(True)
    tb.setShowGrid(False)
    tb.verticalHeader().setDefaultSectionSize(32)
    hh = tb.horizontalHeader()
    hh.setHighlightSections(False)
    for i in range(len(headers)):
        hh.setSectionResizeMode(i, QHeaderView.Stretch if i == stretch_col else QHeaderView.ResizeToContents)
    return tb


def fill_table(t, rows, align_center=()):
    t.setRowCount(0)
    for r, values in enumerate(rows):
        t.insertRow(r)
        for c, v in enumerate(values):
            it = QTableWidgetItem(str(v))
            if c in align_center:
                it.setTextAlignment(Qt.AlignCenter)
            t.setItem(r, c, it)


def segmented(names, on_change):
    """Yan yana seçilebilir butonlar. Seçilen indeks on_change'e gider."""
    box = QFrame()
    box.setObjectName("Card")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(4, 4, 4, 4)
    lay.setSpacing(2)
    group = QButtonGroup(box)
    group.setExclusive(True)
    for i, n in enumerate(names):
        b = QPushButton(t(n).replace("&", "&&"))
        b.setObjectName("Segment")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        group.addButton(b, i)
        lay.addWidget(b)
        if i == 0:
            b.setChecked(True)
    group.idClicked.connect(on_change)
    box.group = group
    from .motion import SlideBar
    box.slide = SlideBar(group, box, "under", 2)
    return box


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def dot(color):
    return f'<span style="color:{color}">●</span>'


def color(name):
    return TOKENS[name]
