"""Spypaper Language Wizard penceresi: üstte kaynak metin, altta çevirisi."""
import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar, QVBoxLayout)

from core import langwizard as LW
from .i18n import t
from .msgbox import ask, warning
from .theme import TOKENS
from .widgets import button, label, row, segmented


class LanguageWizard(QDialog):
    ai_step = Signal(object, int, int)
    ai_done = Signal(object)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Spypaper Language Wizard")
        self.resize(1100, 720)
        self.src = LW.source()
        self.en = dict(self.src)
        self.data, self.code, self.dirty = {}, "", False
        self._stop = False
        self._cur = None

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Spypaper Language Wizard", "PageTitle"))
        v.addWidget(label("Spypaper'ı kendi diline çevir. Çeviriler panelin yanındaki Languages klasörüne dil_ÜLKE.json "
                          "olarak kaydedilir (ör. de_AT.json); istersen dosyayı VS Code'da da düzenleyebilirsin. Kaydedince "
                          "dil, ☰ menüsündeki dil listesinde görünür.", "Muted", wrap=True))

        # dil seçimi
        self.lang = QComboBox()
        self.lang.setMinimumWidth(240)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("de_AT")
        self.code_edit.setMaximumWidth(110)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(t("Dilin kendi adı, ör. Deutsch (Österreich)"))
        self._fill_langs()
        self.lang.currentIndexChanged.connect(self._pick_lang)
        v.addLayout(row(label("Dil"), self.lang, label("Kod"), self.code_edit, label("Ad"), self.name_edit,
                        stretch_end=False))
        v.addLayout(row(button("Kaydet", "primary", self.save), button("Klasörü Aç", "ghost", self.open_folder),
                        button("VS Code'da Aç", "ghost", self.open_vscode),
                        button("Minecraft Dil Dosyasını Çıkar…", "ghost", self.mc_lang), None,
                        button("Yapay Zeka Ayarları", "ghost", self.ai_settings)))

        # liste + düzenleyici
        body = QHBoxLayout()
        left = QVBoxLayout()
        self.filter = segmented(["Eksikler", "Tümü"], self._refill)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Ara…"))
        self.search.textChanged.connect(lambda _: self._refill())
        self.list = QListWidget()
        self.list.setMinimumWidth(360)
        self.list.currentItemChanged.connect(self._select)
        left.addWidget(self.filter)
        left.addWidget(self.search)
        left.addWidget(self.list, 1)
        self.count_lbl = label("", "Muted")
        left.addWidget(self.count_lbl)
        body.addLayout(left, 2)

        right = QVBoxLayout()
        right.addWidget(label("Kaynak metin (İngilizce)", "CardTitle"))
        self.source_box = QPlainTextEdit()
        self.source_box.setReadOnly(True)
        right.addWidget(self.source_box, 1)
        self.tr_lbl = label("", "Muted", wrap=True)
        self.tr_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right.addWidget(self.tr_lbl)
        right.addWidget(label("Çeviri", "CardTitle"))
        self.edit = QPlainTextEdit()
        self.edit.textChanged.connect(self._edited)
        right.addWidget(self.edit, 1)
        self.warn_lbl = label("", "Muted", wrap=True)
        self.warn_lbl.setStyleSheet(f"color:{TOKENS['danger']};")
        right.addWidget(self.warn_lbl)
        right.addLayout(row(button("◀ Önceki", "ghost", lambda: self.step(-1)),
                            button("Kaynağı Kopyala", "ghost", self.copy_source),
                            button("Bunu Yapay Zekâyla Çevir", "ghost", self.ai_one), None,
                            button("Sonraki ▶", "primary", lambda: self.step(1)), stretch_end=False))
        right.addWidget(label("Ctrl+Enter: kaydet ve sonraki · Ctrl+S: dosyayı kaydet", "Muted"))
        body.addLayout(right, 3)
        v.addLayout(body, 1)

        # toplu yapay zekâ
        self.bar = QProgressBar()
        self.bar.hide()
        self.btn_ai_all = button("Eksiklerin Hepsini Yapay Zekâyla Çevir", "ghost", self.ai_all)
        self.btn_ai_stop = button("Durdur", "ghost", self._ai_stop)
        self.btn_ai_stop.hide()
        v.addLayout(row(self.btn_ai_all, self.btn_ai_stop, self.bar, stretch_end=False))
        v.addWidget(label("Yapay zekâ Esplora'nın API anahtarını kullanır; metinler seçtiğin dile sorgusuz çevrilir. "
                          "Yer tutucusu bozulan çeviriler alınmaz. Gözden geçirmeyi unutma.", "Muted", wrap=True))

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self.step(1))
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)
        self.ai_step.connect(self._ai_step)
        self.ai_done.connect(self._ai_done)
        self._pick_lang()

    # ------------------------------------------------------------ dil
    def _fill_langs(self):
        self.lang.blockSignals(True)
        self.lang.clear()
        for code, name in LW.user_languages():
            self.lang.addItem(f"{name} ({code})", ("user", code, name, name))
        mine = {c for c, _ in LW.user_languages()}
        for code, name, eng in LW.SUGGESTED:
            if code not in mine:
                self.lang.addItem(t("Yeni: {name}", name=f"{name} ({code})"), ("new", code, name, eng))
        self.lang.addItem(t("Başka bir dil (kodu kendin yaz)"), ("new", "", "", ""))
        self.lang.blockSignals(False)

    def _pick_lang(self, *_):
        if self.dirty and self.code and ask(self, t("Değişiklikler kaydedilsin mi?"), t("Kaydet")):
            self.save()
        kind, code, name, _eng = self.lang.currentData() or ("new", "", "", "")
        self.code_edit.setText(code)
        self.code_edit.setReadOnly(kind == "user")
        try:
            self.data = LW.load(code) if kind == "user" else {}
        except LW.WizardError as e:
            warning(self, t("Uyarı"), t(e.template, **e.kw))
            self.data = {}
        self.name_edit.setText(self.data.get("_name", name))
        self.code = code
        self.dirty = False
        self._refill()

    def _lang_name(self):
        _k, _c, _n, eng = self.lang.currentData() or ("", "", "", "")
        return eng or self.name_edit.text().strip() or self.code_edit.text().strip()

    # ------------------------------------------------------------ liste
    def _missing(self):
        return self.filter.group.checkedId() != 1

    def _refill(self, *_):
        missing_only = self._missing()
        q = self.search.text().strip().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for k, en in self.src:
            if missing_only and self.data.get(k):
                continue
            if q and q not in en.lower() and q not in k.lower() and q not in (self.data.get(k) or "").lower():
                continue
            it = QListWidgetItem(("✓ " if self.data.get(k) else "• ") + en.replace("\n", " ")[:90])
            it.setData(Qt.UserRole, k)
            self.list.addItem(it)
        self.list.blockSignals(False)
        done, total = LW.progress(self.data)
        self.count_lbl.setText(t("{done} / {total} metin çevrildi", done=done, total=total))
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self._cur = None
            self.source_box.setPlainText("")
            self.edit.blockSignals(True)
            self.edit.setPlainText("")
            self.edit.blockSignals(False)

    def _select(self, item, _prev=None):
        if item is None:
            return
        self._cur = item.data(Qt.UserRole)
        self.source_box.setPlainText(self.en[self._cur])
        self.tr_lbl.setText(t("Türkçe kaynak: {src}", src=self._cur.replace("\n", " ")) if self._cur != self.en[self._cur] else "")
        self.edit.blockSignals(True)
        self.edit.setPlainText(self.data.get(self._cur, ""))
        self.edit.blockSignals(False)
        self._check()

    def _edited(self):
        if self._cur is None:
            return
        self.data[self._cur] = self.edit.toPlainText()
        self.dirty = True
        self._check()

    def _check(self):
        p = LW.problem(self.en.get(self._cur, ""), self.edit.toPlainText()) if self._cur else ""
        self.warn_lbl.setText(t(p) if p else "")

    def step(self, d):
        r = self.list.currentRow()
        if self._missing() and d > 0 and self._cur and self.data.get(self._cur):
            it = self.list.currentItem()           # eksikler görünümünde çevrilen satır listeden düşer
            it.setText("✓ " + it.text()[2:])
        n = max(0, min(self.list.count() - 1, r + d))
        self.list.setCurrentRow(n)
        self.edit.setFocus()

    def copy_source(self):
        if self._cur:
            self.edit.setPlainText(self.en[self._cur])

    # ------------------------------------------------------------ dosya
    def save(self):
        code = self.code_edit.text().strip()
        try:
            path = LW.save(code, self.name_edit.text().strip(), self.data)
        except LW.WizardError as e:
            warning(self, t("Uyarı"), t(e.template, **e.kw))
            return False
        self.code, self.dirty = code, False
        self.count_lbl.setText(self.count_lbl.text() + "  ·  " + t("Kaydedildi: {file}", file=os.path.basename(path)))
        return True

    def open_folder(self):
        from core import explorer
        os.makedirs(LW.folder(), exist_ok=True)
        explorer.open_path(LW.folder())

    def open_vscode(self):
        from core import explorer
        if not self.save():
            return
        try:
            explorer.open_file(LW.path_for(self.code), "vscode", root=LW.folder())
        except Exception as e:
            warning(self, t("Uyarı"), str(e))

    def mc_lang(self):
        from .gamefiles_dialog import GameFilesDialog
        code = self.code_edit.text().strip()
        GameFilesDialog(self, only_lang=LW.mc_code(code) if code else "").exec()

    def ai_settings(self):
        from .ai_dialog import AIDialog
        AIDialog(self.settings, self).exec()

    # ------------------------------------------------------------ yapay zekâ
    def ai_one(self):
        if self._cur:
            self._run_ai([(self._cur, self.en[self._cur])])

    def ai_all(self):
        items = [(k, en) for k, en in self.src if not self.data.get(k)]
        if not items:
            return
        if not ask(self, t("{n} metin yapay zekâyla {lang} diline çevrilecek. Devam edilsin mi?", n=len(items),
                           lang=self._lang_name()), t("Onay")):
            return
        self._run_ai(items)

    def _run_ai(self, items):
        if not self.code_edit.text().strip():
            warning(self, t("Uyarı"), t("Önce dil kodunu yaz, ör. de_AT."))
            return
        self._stop = False
        self.btn_ai_all.setEnabled(False)
        self.btn_ai_stop.show()
        self.bar.show()
        self.bar.setRange(0, len(items))
        self.bar.setValue(0)
        lang = self._lang_name()

        def work():
            try:
                for got, done, total in LW.ai_translate(self.settings, lang, items):
                    self.ai_step.emit(dict(got), done, total)
                    if self._stop:
                        break
                self.ai_done.emit(None)
            except Exception as e:
                self.ai_done.emit(e)
        threading.Thread(target=work, daemon=True).start()

    def _ai_stop(self):
        self._stop = True

    def _ai_step(self, got, done, total):
        self.data.update(got)
        self.dirty = True
        self.bar.setValue(done)

    def _ai_done(self, err):
        self.btn_ai_all.setEnabled(True)
        self.btn_ai_stop.hide()
        self.bar.hide()
        if err is not None:
            warning(self, t("Uyarı"), t(err.template, **err.kw) if hasattr(err, "template") else str(err))
        if self.dirty:
            self.save()
        cur = self._cur
        self._refill()
        if cur and not self._missing():
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == cur:
                    self.list.setCurrentRow(i)

    def closeEvent(self, e):
        if self.dirty and self.code_edit.text().strip() and ask(self, t("Değişiklikler kaydedilsin mi?"), t("Kaydet")):
            self.save()
        self._stop = True
        super().closeEvent(e)
