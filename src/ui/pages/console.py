import html
from PySide6.QtGui import QTextCursor
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit

from core import classify_log_line, commands
from ..theme import TOKENS, log_colors
from ..i18n import t
from ..widgets import Page, button, row



class HistoryLineEdit(QLineEdit):
    nav = Signal(int)          # öneri listesi açıkken ↑ ↓
    accept_suggestion = Signal()
    dismiss = Signal()

    def __init__(self):
        super().__init__()
        self.history, self.index = [], -1
        self.popup_open = lambda: False
        self.popup_chosen = lambda: False

    def push(self, text):
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.index = -1

    def event(self, e):
        # Tab odak değiştirmesin; öneriyi kabul etsin
        if e.type() == e.Type.KeyPress and e.key() == Qt.Key_Tab and self.popup_open():
            self.accept_suggestion.emit()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if self.popup_open():
            if e.key() in (Qt.Key_Up, Qt.Key_Down):
                self.nav.emit(-1 if e.key() == Qt.Key_Up else 1)
                return
            if e.key() == Qt.Key_Escape:
                self.dismiss.emit()
                return
            if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.popup_chosen():
                self.accept_suggestion.emit()
                return
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
        self.out.setContextMenuPolicy(Qt.CustomContextMenu)
        self.out.customContextMenuRequested.connect(self._menu)
        self.root.addWidget(self.out, 1)

        self.sugg = QListWidget()
        self.sugg.setObjectName("Suggest")
        self.sugg.setFocusPolicy(Qt.NoFocus)
        self.sugg.setUniformItemSizes(True)
        self.sugg.setStyleSheet(f"QListWidget#Suggest {{ background:{TOKENS['surface_2']}; border:1px solid {TOKENS['border']};"
                                f" border-radius:8px; padding:2px; }} QListWidget#Suggest::item {{ padding:3px 8px; }}")
        self.sugg.itemClicked.connect(lambda it: self._apply(it))
        self.sugg.hide()
        self.root.addWidget(self.sugg)
        self.hint = QLabel()
        self.hint.setTextFormat(Qt.RichText)
        self.hint.setStyleSheet(f"color:{TOKENS['text_muted']}; font-family: Consolas, 'Cascadia Mono', monospace;")
        self.hint.hide()
        self.root.addWidget(self.hint)

        self.input = HistoryLineEdit()
        self.input.setPlaceholderText(t("Komut yaz (örn. say merhaba, time set day)  —  Tab: öneriyi al · ↑ ↓ geçmiş"))
        self.input.returnPressed.connect(self.submit)
        self.input.textEdited.connect(self.update_suggestions)
        self.input.nav.connect(self._nav)
        self.input.accept_suggestion.connect(lambda: self._apply(self.sugg.currentItem() or self.sugg.item(0)))
        self.input.dismiss.connect(self._hide_sugg)
        self.input.popup_open = lambda: self.sugg.isVisible() and self.sugg.count() > 0
        self.input.popup_chosen = lambda: self._chosen
        self._chosen = False
        self._ctx_cache = None
        self.root.addLayout(row(
            self.input,
            button("Gönder", "primary", self.submit),
            button("Temizle", "ghost", self.clear_console),
            stretch_end=False,
        ))
        for line in list(app.server.history):   # arayüz yeniden kurulduysa geçmişi geri yükle
            self.append(line)
        bridge.line.connect(self.append)

    _STAMP = re.compile(r"^\[[^\]]*\]\s*(?:\[[^\]]*\]\s*)*:?\s*")
    _NUM = re.compile(r"-?\d+")

    def _repeat_key(self, text):
        """Aynı mesaj (yalnızca saat ve sayıları farklı) art arda gelirse tek satırda sayılır."""
        return self._NUM.sub("#", self._STAMP.sub("", text, count=1)).strip()

    def append(self, text):
        kind = classify_log_line(text)
        if self.app.config.settings.get("translate_logs"):
            text = self.app.logtrans.line(text)
        key = self._repeat_key(text)
        last = getattr(self, "_last", None)
        body = f'<span style="color:{log_colors()[kind]}; white-space:pre-wrap">{html.escape(text)}</span>'
        if last and key and last[0] == key and self.out.document().blockCount() == last[2] and self.out.toPlainText():
            n = last[1] + 1
            c = self.out.textCursor()
            c.movePosition(QTextCursor.End)
            c.select(QTextCursor.BlockUnderCursor)
            c.removeSelectedText()
            self.out.appendHtml(body + f'<span style="color:{TOKENS["text_muted"]}">  (×{n})</span>')
        else:
            n = 1
            self.out.appendHtml(body)
        self._last = (key, n, self.out.document().blockCount())

    def _menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = self.out.createStandardContextMenu()
        sel = self.out.textCursor().selectedText().replace("\u2029", "\n").strip()
        if not sel:                                          # seçim yoksa tıklanan satır ve çevresi
            c = self.out.cursorForPosition(pos)
            blk = c.block()
            lines = [blk.text()]
            nxt = blk.next()
            while nxt.isValid() and len(lines) < 30 and (nxt.text().startswith(("\tat ", "Caused by", "\t...", " "))
                                                          or "Exception" in nxt.text()):
                lines.append(nxt.text())
                nxt = nxt.next()
            sel = "\n".join(lines).strip()
        menu.addSeparator()
        act = menu.addAction(t("Esplora'ya sor"))
        act.setEnabled(bool(sel))
        act.triggered.connect(lambda: self.ask_esplora(sel))
        menu.exec(self.out.mapToGlobal(pos))
        del QMenu

    def ask_esplora(self, text):
        """Seçilen konsol satırlarını Esplora'ya açıklatır."""
        from .esplora import EsploraPage
        win = self.parentWidget()
        while win is not None and not (hasattr(win, "pages") and hasattr(win, "go")):
            win = win.parentWidget()
        pages = getattr(win, "pages", [])
        for i, p in enumerate(pages):
            if isinstance(p, EsploraPage):
                win.go(i)
                text = text[:4000]
                p.ask(t("Konsoldaki bu satırları sade bir dille açıkla: ne oluyor, sorun mu, düzeltmek için ne yapmalıyım?")
                      + "\n\n```\n" + text + "\n```", label="🖥️ " + t("Konsoldan: {line}", line=text.splitlines()[0][:80]))
                return

    def clear_console(self):
        self.out.clear()
        self._last = None

    # --- öneriler ---
    def _ctx(self):
        if self._ctx_cache is None:
            players = []
            try:
                players = [p.name for p in self.app.players.list_players() if not p.name.startswith("Bilinmeyen")]
            except Exception:
                pass
            try:
                items = ["minecraft:" + iid for iid, _ in self.app.players.translations.search_items("", limit=3000)]
            except Exception:
                items = []
            self._ctx_cache = {"players": players, "items": items}
        return self._ctx_cache

    def on_show(self):
        self._ctx_cache = None                       # oyuncu listesi değişmiş olabilir

    def update_suggestions(self, text=None):
        text = self.input.text() if text is None else text
        self._chosen = False
        if not text.strip():
            self._hide_sugg()
            return
        res = commands.suggest(text, self._ctx(), t)
        self.sugg.clear()
        for full, shown, desc in res["items"]:
            it = QListWidgetItem(f"{shown}    —  {desc}")
            it.setData(Qt.UserRole, full)
            self.sugg.addItem(it)
        if self.sugg.count():
            self.sugg.setCurrentRow(0)
            rows = min(self.sugg.count(), commands.MAX)
            self.sugg.setFixedHeight(rows * self.sugg.sizeHintForRow(0) + 8)
        self.sugg.setVisible(self.sugg.count() > 0)
        if res["hint"]:
            usage, spans = res["hint"]
            out, last = [], 0
            for a, b in spans:
                out.append(html.escape(usage[last:a]))
                out.append(f'<b style="color:{TOKENS["accent"]}">{html.escape(usage[a:b])}</b>')
                last = b
            out.append(html.escape(usage[last:]))
            self.hint.setText("".join(out))
            self.hint.show()
        else:
            self.hint.hide()

    def _hide_sugg(self):
        self.sugg.hide()
        self._chosen = False

    def _nav(self, step):
        n = self.sugg.count()
        if n:
            self.sugg.setCurrentRow((self.sugg.currentRow() + step) % n)
            self._chosen = True

    def _apply(self, item):
        if not item:
            return
        self.input.setText(item.data(Qt.UserRole))
        self.input.setFocus()
        self.update_suggestions()

    def submit(self):
        text = self.input.text().strip()
        if not text:
            return
        if self.send(text):
            self.input.push(text)
            self.input.clear()
            self._hide_sugg()
            self.hint.hide()
