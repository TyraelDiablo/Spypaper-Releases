"""Yapılandırma: sunucunun ayar dosyalarını (YAML, TOML, JSON, properties…) panelin içinde düzenler.
Satır numaraları, sözdizimi renklendirme, yazarken biçim denetimi, kaydetmeden önce yedek. İş mantığı
core.configedit'te."""
import os
import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget,
)

from core import configedit as ce
from .. import icons
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, button, label, row


# ------------------------------------------------------------------ renklendirme
class Highlighter(QSyntaxHighlighter):
    def __init__(self, doc, kind):
        super().__init__(doc)
        self.kind = kind

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            f.setFontItalic(italic)
            return f
        self.f_comment = fmt(TOKENS["text_muted"], italic=True)
        self.f_key = fmt(TOKENS["info"])
        self.f_str = fmt(TOKENS["warn"])
        self.f_num = fmt(TOKENS["purple"])
        self.f_bool = fmt(TOKENS["accent"], bold=True)
        self.f_section = fmt(TOKENS["accent"], bold=True)
        self.rules = [
            (re.compile(r"\b-?\d+(?:\.\d+)?\b"), self.f_num),
            (re.compile(r"\b(?:true|false|yes|no|on|off|null|default)\b", re.I), self.f_bool),
            (re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'"), self.f_str),
        ]
        if kind == "json":
            self.rules.append((re.compile(r"\"(?:[^\"\\]|\\.)*\"(?=\s*:)"), self.f_key))
        elif kind == "toml":
            self.rules += [(re.compile(r"^\s*\[\[?[^\]]+\]\]?"), self.f_section),
                           (re.compile(r"^\s*[\w.\-\"']+(?=\s*=)"), self.f_key)]
        elif kind == "properties":
            self.rules.append((re.compile(r"^\s*[^#!=:\s][^=:]*(?=[=:])"), self.f_key))
        else:                                                  # yaml ve diğerleri
            self.rules.append((re.compile(r"^\s*(?:- )?[^#:\s\"'][^#:]*?(?=:(?:\s|$))"), self.f_key))
        self.comment = None if kind == "json" else re.compile(r"(?:^|\s)([#!;].*)$" if kind in ("properties", "text")
                                                              else r"(?:^|\s)(#.*)$")

    def highlightBlock(self, text):
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)
        if self.comment:
            m = self.comment.search(text)
            if m and not self._in_string(text, m.start(1)):
                self.setFormat(m.start(1), len(text) - m.start(1), self.f_comment)

    @staticmethod
    def _in_string(text, pos):
        q = None
        for i, ch in enumerate(text[:pos]):
            if ch in "\"'" and (q is None or q == ch) and (i == 0 or text[i - 1] != "\\"):
                q = None if q else ch
        return q is not None


# ------------------------------------------------------------------ satır numaralı editör
class _Gutter(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, e):
        self.editor.paint_gutter(e)


class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName("Console")
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabChangesFocus(False)
        self.gutter = _Gutter(self)
        self.error_line = 0
        self.indent = "  "
        self.blockCountChanged.connect(lambda _n: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self.mark_lines)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def gutter_width(self):
        digits = max(3, len(str(self.blockCount())))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e):
        p = QPainter(self.gutter)
        p.fillRect(e.rect(), QColor(TOKENS["surface_2"]))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                c = TOKENS["danger"] if n + 1 == self.error_line else TOKENS["text"] if n == cur else TOKENS["text_muted"]
                p.setPen(QColor(c))
                p.drawText(0, top, self.gutter.width() - 6, self.fontMetrics().height(), Qt.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1

    def mark_lines(self):
        sels = []
        cur = QTextEdit.ExtraSelection()
        bg = QColor(TOKENS["surface_2"])
        cur.format.setBackground(bg)
        cur.format.setProperty(QTextFormat.FullWidthSelection, True)
        cur.cursor = self.textCursor()
        cur.cursor.clearSelection()
        sels.append(cur)
        if self.error_line:
            block = self.document().findBlockByNumber(self.error_line - 1)
            if block.isValid():
                err = QTextEdit.ExtraSelection()
                c = QColor(TOKENS["danger"])
                c.setAlpha(55)
                err.format.setBackground(c)
                err.format.setProperty(QTextFormat.FullWidthSelection, True)
                from PySide6.QtGui import QTextCursor
                err.cursor = QTextCursor(block)
                sels.append(err)
        self.setExtraSelections(sels)
        self.gutter.update()

    def keyPressEvent(self, e):
        # Tab -> boşluk (YAML sekme kabul etmez); Enter -> önceki satırın girintisi korunur
        if e.key() == Qt.Key_Tab and not e.modifiers():
            self.insertPlainText(self.indent)
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not e.modifiers():
            line = self.textCursor().block().text()
            ind = line[:len(line) - len(line.lstrip(" "))]
            if line.rstrip().endswith(":") and self.indent:
                ind += self.indent
            super().keyPressEvent(e)
            self.insertPlainText(ind)
            return
        super().keyPressEvent(e)

    def go_to_line(self, line, col=1):
        block = self.document().findBlockByNumber(max(0, line - 1))
        if not block.isValid():
            return
        cur = self.textCursor()
        cur.setPosition(block.position() + max(0, min(col - 1, block.length() - 1)))
        self.setTextCursor(cur)
        self.centerCursor()
        self.setFocus()


# ------------------------------------------------------------------ sayfa
class ConfigsPage(Page):
    title = "Yapılandırma"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.rel, self.fmt, self.mtime, self.kind = None, {}, None, None
        self.saved_text = ""
        self.problem = None
        self._loading = False

        h = QHBoxLayout()
        h.setSpacing(14)
        left = Card("Ayar Dosyaları", "Sunucu klasöründeki YAML, TOML, JSON ve properties dosyaları")
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Dosya ara…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        left.add(self.search)
        self.files = QListWidget()
        self.files.currentItemChanged.connect(self._picked)
        left.add(self.files, 1)
        b_ref = button("Yenile", "ghost", self.reload_list)
        b_ref.setIcon(icons.icon("rotate-ccw", None, 16))
        left.add(row(b_ref))
        left.setFixedWidth(330)
        h.addWidget(left)

        right = Card()
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        self.path_lbl = label("", "CardTitle", raw=True)
        self.state_lbl = label("", "Muted", wrap=True)
        self.state_lbl.setTextFormat(Qt.RichText)
        self.state_lbl.linkActivated.connect(lambda _l: self.problem and self.editor.go_to_line(self.problem["line"], self.problem["col"]))
        col.addWidget(self.path_lbl)
        col.addWidget(self.state_lbl)
        head.addLayout(col, 1)
        self.b_revert = button("Geri Al", "ghost", self.revert, tooltip="Kaydedilmemiş değişiklikleri at ve dosyayı yeniden yükle")
        self.b_backups = button("Yedekler", "ghost", self.show_backups, tooltip="Bu dosyanın önceki hallerinden birini geri yükle")
        self.b_ext = button("Dışarıda Aç", "ghost", self.open_external, tooltip="Dosyayı Dosyalar sekmesinde seçili düzenleyicide aç")
        self.b_ext.setIcon(icons.icon("external-link", None, 16))
        self.b_save = button("Kaydet", "primary", self.save, tooltip="Ctrl+S")
        for b in (self.b_revert, self.b_backups, self.b_ext, self.b_save):
            head.addWidget(b)
        right.add(head)
        self.editor = CodeEditor()
        self.editor.textChanged.connect(self._changed)
        right.add(self.editor, 1)
        self.note = label("", "Muted", wrap=True)
        right.add(self.note)
        h.addWidget(right, 1)
        self.root.addLayout(h, 1)

        QShortcut(QKeySequence.Save, self, activated=self.save)
        self.check_timer = QTimer(self, singleShot=True, interval=350)
        self.check_timer.timeout.connect(self.check)
        bridge.state.connect(lambda _s: self._note())
        self._all = []
        self._set_enabled(False)
        self._listed_root = None

    # ------------------------------------------------------------------ liste
    def on_show(self):
        if self._listed_root != self.app.config.server_path:
            self.reload_list()
        self._note()

    def reload_list(self):
        root = self.app.config.server_path
        self._listed_root = root
        self._all = ce.list_configs(root) if os.path.isdir(root) else []
        self._filter()

    def _filter(self):
        q = self.search.text().strip().lower()
        self.files.blockSignals(True)
        self.files.clear()
        sel = None
        for rel in self._all:
            if q and q not in rel.lower():
                continue
            folder, _, name = rel.rpartition("/")
            it = QListWidgetItem(name + (f"   ·  {folder}" if folder else ""))
            it.setData(Qt.UserRole, rel)
            it.setToolTip(rel)
            self.files.addItem(it)
            if rel == self.rel:
                sel = it
        if sel:
            self.files.setCurrentItem(sel)
        self.files.blockSignals(False)
        if not self._all:
            self.path_lbl.setText(t("Ayar dosyası bulunamadı."))

    def _picked(self, cur, prev):
        if not cur:
            return
        rel = cur.data(Qt.UserRole)
        if rel == self.rel:
            return
        if self.dirty and not self._confirm_discard():
            self.files.blockSignals(True)
            self.files.setCurrentItem(prev)
            self.files.blockSignals(False)
            return
        self.open(rel)

    # ------------------------------------------------------------------ dosya
    @property
    def dirty(self):
        return self.rel is not None and self.editor.toPlainText() != self.saved_text

    def _confirm_discard(self):
        from ..msgbox import choose
        res = choose(self, "question", t("Kaydedilmemiş değişiklikler"),
                     t("'{name}' dosyasında kaydedilmemiş değişiklikler var.", name=self.rel),
                     [(t("İptal"), "ghost"), (t("Kaydetme"), "ghost"), (t("Kaydet"), "primary")], default=2, cancel=0)
        if res == 2:
            return self.save()
        return res == 1

    def open(self, rel):
        try:
            text, fmt, mtime = ce.read(self.app.config.server_path, rel)
        except ce.ConfigError as e:
            self.error(t(e.template, **e.kw))
            return
        self.rel, self.fmt, self.mtime, self.kind = rel, fmt, mtime, ce.kind_of(rel)
        self.saved_text = text
        self.editor.indent = "    " if self.kind == "json" else "  "
        self._loading = True
        if getattr(self, "highlighter", None):              # tek renklendirici: eskisini belgeden ayır
            self.highlighter.setDocument(None)
        self.highlighter = Highlighter(self.editor.document(), self.kind)
        self.editor.setPlainText(text)
        self._loading = False
        self.path_lbl.setText(rel)
        self._set_enabled(True)
        self.check()
        self._note()

    def _set_enabled(self, on):
        for w in (self.editor, self.b_save, self.b_revert, self.b_ext, self.b_backups):
            w.setEnabled(on)

    def _changed(self):
        if self._loading:
            return
        self.check_timer.start()
        self._state()

    def check(self):
        if self.rel is None:
            return
        self.problem = ce.validate(self.kind, self.editor.toPlainText())
        self.editor.error_line = self.problem["line"] if self.problem else 0
        self.editor.mark_lines()
        self._state()

    def _state(self):
        if self.rel is None:
            return
        parts = []
        if self.dirty:
            parts.append(f'<span style="color:{TOKENS["warn"]}">● {t("Kaydedilmedi")}</span>')
        p = self.problem
        if p:
            where = t("Satır {line}, sütun {col}", line=p["line"], col=p["col"]) if p["line"] else ""
            hint = t(p["hint"], **p.get("hint_kw", {})) if p.get("hint") else ""
            text = " — ".join(x for x in (hint, p["message"]) if x)
            link = f'<a href="go" style="color:{TOKENS["danger"]}">{where}</a>: ' if where else ""
            parts.append(f'<span style="color:{TOKENS["danger"]}">✖ {link}{_esc(text)}</span>')
        elif self.kind in ("yaml", "toml", "json"):
            parts.append(f'<span style="color:{TOKENS["accent"]}">✔ {t("Biçim geçerli ({kind})", kind=self.kind.upper())}</span>')
        else:
            parts.append(t("Bu dosya türünün biçimi denetlenmez."))
        self.state_lbl.setText("   ".join(parts))

    def _note(self):
        self.note.setText(t("Sunucu açık: yapılandırma dosyalarındaki değişiklikler sunucu yeniden başlatılınca geçerli olur.")
                          if self.app.server.is_running and self.rel else
                          t("Kaydetmeden önce dosyanın eski hali backups/configs klasörüne kopyalanır."))

    # ------------------------------------------------------------------ işlemler
    def save(self):
        if self.rel is None or self.read_only():
            return False
        if self.problem and not self.confirm(
                t("Dosyada biçim hatası var; sunucu ya da eklenti bu dosyayı okuyamayabilir. Yine de kaydedilsin mi?")):
            return False
        try:
            self.mtime = ce.save(self.app.config.server_path, self.rel, self.editor.toPlainText(), self.fmt, self.mtime)
        except ce.Conflict as e:
            from ..msgbox import choose
            res = choose(self, "warning", t("Dosya değişti"), t(e.template) + "\n\n" +
                         t("Senin değişikliklerinle üzerine yazılsın mı, yoksa dosyanın yeni hali mi yüklensin?"),
                         [(t("İptal"), "ghost"), (t("Yeni Hali Yükle"), "ghost"), (t("Üzerine Yaz"), "danger")],
                         default=0, cancel=0)
            if res == 1:
                self.open_force(self.rel)
            elif res == 2:
                self.mtime = None
                return self.save()
            return False
        except ce.ConfigError as e:
            self.error(t(e.template, **e.kw))
            return False
        self.saved_text = self.editor.toPlainText()
        self._state()
        self.note.setText(t("Kaydedildi. Eski hali backups/configs klasöründe."))
        return True

    def open_force(self, rel):
        self.rel = None
        self.open(rel)

    def revert(self):
        if self.rel and (not self.dirty or self.confirm("Kaydedilmemiş değişiklikler atılsın mı?")):
            self.open_force(self.rel)

    def open_external(self):
        if not self.rel:
            return
        from core import explorer
        path = os.path.join(self.app.config.server_path, self.rel)
        try:
            explorer.open_file(path, self.app.config.settings.get("file_editor") or "auto", self.app.config.server_path)
        except explorer.ExplorerError as e:
            self.error(t(e.template, **e.kw))

    def show_backups(self):
        if not self.rel:
            return
        from PySide6.QtWidgets import QMenu
        items = ce.backups_of(self.app.config.server_path, self.rel)
        m = QMenu(self)
        if not items:
            a = m.addAction(t("Bu dosyanın yedeği yok."))
            a.setEnabled(False)
        for stamp, path in items[:20]:
            try:
                when = f"{stamp[6:8]}.{stamp[4:6]}.{stamp[:4]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"
            except IndexError:
                when = stamp
            m.addAction(icons.icon("rotate-ccw", None, 16), when, lambda p=path: self._load_backup(p))
        m.exec(self.b_backups.mapToGlobal(self.b_backups.rect().bottomLeft()))

    def _load_backup(self, path):
        """Yedeği editöre yükler; kaydedene kadar dosyaya yazılmaz."""
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read().replace("\r\n", "\n")
        except OSError as e:
            self.error(t("Dosya açılamadı: {error}", error=str(e)))
            return
        self.editor.setPlainText(text)
        self.note.setText(t("Yedek editöre yüklendi. Geri yüklemek için Kaydet'e bas."))

    def select_file(self, rel):
        """Dosyalar sekmesinden 'Spypaper'da düzenle' ile gelinir."""
        if self._listed_root != self.app.config.server_path or rel not in self._all:
            self.reload_list()
            if rel not in self._all:
                self._all.append(rel)
                self._filter()
        self.search.clear()
        for i in range(self.files.count()):
            if self.files.item(i).data(Qt.UserRole) == rel:
                self.files.setCurrentRow(i)
                return


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
