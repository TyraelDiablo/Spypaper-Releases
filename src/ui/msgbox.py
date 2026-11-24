"""Panele özel mesaj kutuları (Windows'un standart kutuları yerine).

Temaya uyan, çerçevesiz, sürüklenebilir bir kart: renkli ikon, başlık, metin ve düğmeler.
install() çağrılınca QMessageBox.information / warning / critical / question / about da buraya yönlenir,
böylece kodun her yerindeki eski çağrılar otomatik olarak yeni görünümü kullanır.

    from .msgbox import info, warning, error, ask, choose
    if ask(self, "Silinsin mi?", "Onay"): ...
    i = choose(self, "warning", "Başlık", "Metin", [("Kabul Ediyorum", "primary"), ("İptal", "ghost")])
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout,
)

from . import icons
from .i18n import is_rtl, t
from .theme import TOKENS, rgba

KINDS = {
    "info": ("info", "info"),
    "warning": ("triangle-alert", "warn"),
    "error": ("circle-x", "danger"),
    "question": ("circle-help", "accent"),
    "success": ("circle-check", "accent"),
    "lock": ("lock", "accent"),
    "about": ("info", "accent"),
}


class MessageDialog(QDialog):
    def __init__(self, parent, kind, title, text, buttons, default=0, cancel=None, rich=False, field=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowTitle(title or "Spypaper")
        if is_rtl():
            self.setLayoutDirection(Qt.RightToLeft)
        self.result_index = cancel if cancel is not None else len(buttons) - 1
        self.cancel = self.result_index
        self._drag = None
        icon_name, token = KINDS.get(kind, KINDS["info"])
        c = TOKENS.get(token, TOKENS["accent"])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)            # gölge payı
        card = QFrame()
        card.setObjectName("MsgCard")
        card.setStyleSheet(
            f"QFrame#MsgCard {{ background:{TOKENS['surface']}; border:1px solid {TOKENS['border']};"
            f" border-top:3px solid {c}; border-radius:{TOKENS.get('radius', '12px')}; }}")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 150))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)
        v = QVBoxLayout(card)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        badge = QLabel()
        badge.setFixedSize(38, 38)
        badge.setAlignment(Qt.AlignCenter)
        if kind == "about":
            badge.setFixedSize(44, 44)
            badge.setPixmap(icons.logo(44))
            badge.setStyleSheet("background: transparent;")
        else:
            badge.setPixmap(icons.pixmap(icon_name, c, 22))
            badge.setStyleSheet(f"background:{rgba(c, 38)}; border-radius:19px;")
        head.addWidget(badge, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        if title:
            tl = QLabel(title)
            tl.setObjectName("CardTitle")
            tl.setStyleSheet("font-size: 11.5pt; background: transparent;")
            col.addWidget(tl)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText if rich else Qt.PlainText)
        body.setOpenExternalLinks(True)
        body.setTextInteractionFlags(Qt.TextBrowserInteraction if rich else Qt.TextSelectableByMouse)
        body.setStyleSheet(f"color:{TOKENS['text']}; background: transparent;")
        body.setMinimumWidth(320)
        body.setMaximumWidth(520)
        col.addWidget(body)
        self.field = field
        if field is not None:
            col.addSpacing(4)
            col.addWidget(field)
        head.addLayout(col, 1)
        v.addLayout(head)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.buttons = []
        for i, (label, variant) in enumerate(buttons):
            b = QPushButton(label)
            b.setProperty("variant", variant)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(90)
            b.clicked.connect(lambda _=False, i=i: self._pick(i))
            row.addWidget(b)
            self.buttons.append(b)
        v.addLayout(row)
        if self.buttons:
            self.buttons[default].setDefault(True)
            self.buttons[default].setFocus()
        if field is not None:
            field.setFocus()
            if isinstance(field, QLineEdit):
                field.returnPressed.connect(lambda: self._pick(default))
        self.adjustSize()

    def _pick(self, i):
        self.result_index = i
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.result_index = self.cancel
            self.reject()
            return
        super().keyPressEvent(e)

    # çerçevesiz pencereyi sürükleyerek taşıma
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def showEvent(self, e):
        super().showEvent(e)
        p = self.parentWidget()
        win = p.window() if p else QApplication.activeWindow()
        if win:
            g = win.frameGeometry()
            self.move(g.center() - QPoint(self.width() // 2, self.height() // 2))


def choose(parent, kind, title, text, buttons, default=0, cancel=None, rich=False):
    """Düğme listesinden seçilenin sırasını döndürür. buttons: [(metin, "primary"|"ghost"|"danger"), …]"""
    d = MessageDialog(parent, kind, title, text, buttons, default, cancel, rich)
    d.exec()
    return d.result_index


def get_text(parent, title, text, password=False, value=""):
    """Tek satırlık metin sorar: (metin, tamam_mı)."""
    f = QLineEdit(value)
    if password:
        f.setEchoMode(QLineEdit.Password)
    d = MessageDialog(parent, "info" if not password else "lock", title, text,
                      [(t("İptal"), "ghost"), (t("Tamam"), "primary")], 1, 0, field=f)
    d.exec()
    return f.text(), d.result_index == 1


def get_item(parent, title, text, items, current=0, editable=False):
    """Listeden seçim: (seçilen, tamam_mı)."""
    f = QComboBox()
    f.setEditable(editable)
    f.addItems(list(items))
    if items:
        f.setCurrentIndex(max(0, min(current, len(items) - 1)))
    d = MessageDialog(parent, "question", title, text, [(t("İptal"), "ghost"), (t("Tamam"), "primary")], 1, 0,
                      field=f)
    d.exec()
    return f.currentText(), d.result_index == 1


def info(parent, title, text, rich=False):
    choose(parent, "info", title, text, [(t("Tamam"), "primary")], rich=rich)


def warning(parent, title, text, rich=False):
    choose(parent, "warning", title, text, [(t("Tamam"), "primary")], rich=rich)


def error(parent, title, text, rich=False):
    choose(parent, "error", title, text, [(t("Tamam"), "primary")], rich=rich)


def ask(parent, text, title="", yes=None, no=None, kind="question", danger=False):
    """Evet/Hayır sorusu; Evet ise True."""
    i = choose(parent, kind, title, text,
               [(no or t("Hayır"), "ghost"), (yes or t("Evet"), "danger" if danger else "primary")],
               default=1, cancel=0)
    return i == 1


# ------------------------------------------------------------------ eski QMessageBox çağrılarını yönlendirme
def _looks_rich(text):
    import re
    return bool(re.search(r"<(a|b|i|br|p|ul|li|span|div|code)[\s/>]", str(text or ""), re.I))


def _std(kind):
    def f(parent, title, text, *args, **kw):
        buttons = args[0] if args else kw.get("buttons")
        if buttons is not None and (buttons & QMessageBox.Yes):     # Evet/Hayır istenmiş: soru gibi davran
            return QMessageBox.Yes if ask(parent, text, title) else QMessageBox.No
        choose(parent, kind, title, text, [(t("Tamam"), "primary")], rich=_looks_rich(text))
        return QMessageBox.Ok
    return staticmethod(f)


def _question(parent, title, text, *args, **kw):
    return QMessageBox.Yes if ask(parent, text, title) else QMessageBox.No


def install():
    QMessageBox.information = _std("info")
    QMessageBox.warning = _std("warning")
    QMessageBox.critical = _std("error")
    QMessageBox.about = _std("info")
    QMessageBox.question = staticmethod(_question)
