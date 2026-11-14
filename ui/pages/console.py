import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

from core import classify_log_line
from ..theme import log_colors
from ..i18n import t
from ..widgets import Page, button, row



class HistoryLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.history, self.index = [], -1

    def push(self, text):
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.index = -1

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up and self.history:
            self.index = min(self.index + 1, len(self.history) - 1)
            self.setText(self.history[-1 - self.index])
        elif e.key() == Qt.Key_Down and self.history:
            self.index -= 1
            self.setText(self.history[-1 - self.index] if self.index >= 0 else "")
            self.index = max(self.index, -1)
        else:
            super().keyPressEvent(e)


class ConsolePage(Page):
    title = "Canlı Konsol"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.out = QPlainTextEdit()
        self.out.setObjectName("Console")
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(int(app.config.settings.get("console_max_lines")))
        self.root.addWidget(self.out, 1)

        self.input = HistoryLineEdit()
        self.input.setPlaceholderText(t("Komut yaz (örn. say merhaba, time set day)  —  ↑ ↓ geçmiş"))
        self.input.returnPressed.connect(self.submit)
        self.root.addLayout(row(
            self.input,
            button("Gönder", "primary", self.submit),
            button("Temizle", "ghost", self.out.clear),
            stretch_end=False,
        ))
        for line in list(app.server.history):   # arayüz yeniden kurulduysa geçmişi geri yükle
            self.append(line)
        bridge.line.connect(self.append)

    def append(self, text):
        kind = classify_log_line(text)
        if self.app.config.settings.get("translate_logs"):
            text = self.app.logtrans.line(text)
        self.out.appendHtml(
            f'<span style="color:{log_colors()[kind]}; white-space:pre-wrap">{html.escape(text)}</span>'
        )

    def submit(self):
        text = self.input.text().strip()
        if not text:
            return
        if self.send(text):
            self.input.push(text)
            self.input.clear()
