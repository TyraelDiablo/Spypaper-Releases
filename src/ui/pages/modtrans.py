"""Mod Dil Dosyaları — mod ve eklenti jar'larındaki İngilizce dil dosyalarını yan yana gösterir, çeviri elle yapılır."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit, QTableWidget,
    QTableWidgetItem,
)

from core import N_, modtrans
from core.players import mc_lang_code
from ..i18n import current, t
from ..theme import TOKENS
from ..widgets import Card, Page, ask, button, fill_table, label, row, segmented, table

LANGS = ["tr_tr", "de_de", "fr_fr", "es_es", "pt_br", "it_it", "nl_nl", "pl_pl", "ru_ru", "uk_ua",
         "az_az", "ja_jp", "ko_kr", "zh_cn", "ar_sa"]
FILTERS = [N_("Tümü"), N_("Eksik"), N_("Hatalı")]


class ModTransPage(Page):
    title = "Mod Dil Dosyaları"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.mods, self.mod, self.idx = [], None, 0
        self.en, self.tr, self.dirty = {}, {}, False
        self.filter = 0
        self._filling = False

        top = Card("Mod Dil Dosyaları", "Mod ve eklenti jar'larındaki İngilizce dil dosyalarını (JSON, YAML) bulur; çeviriyi sen yazarsın. "
                                       "Kaydedince jar'ın içine hedef dil dosyası olarak yazılır, orijinal jar yedeklenir. "
                                       "Birden çok klasörü ; ile ayırabilirsin.")
        self.folder = QLineEdit()
        self.folder.setObjectName("Mono")
        self.folder.editingFinished.connect(self._save_folder)
        self.lang = QComboBox()
        for c in LANGS:
            self.lang.addItem(c, c)
        self.lang.currentIndexChanged.connect(lambda _: self.scan())
        top.add(row(label("Klasör"), self.folder, button("Gözat", "ghost", self.browse), button("Tara", "ghost", self.scan),
                    label("Hedef dil"), self.lang, stretch_end=False))
        self.root.addWidget(top)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        left = Card("Modlar ve Eklentiler")
        left.setFixedWidth(330)
        self.mod_table = table(["Mod", "Eksik"], stretch_col=0)
        self.mod_table.itemSelectionChanged.connect(self._mod_selected)
        left.add(self.mod_table, 1)
        self.mods_lbl = left.add(label("", "Muted", wrap=True))
        body.addWidget(left)

        right = Card()
        self.title_lbl = label("Bir mod seçin", "CardTitle")
        self.ns = QComboBox()
        self.ns.currentIndexChanged.connect(self._ns_changed)
        right.add(row(self.title_lbl, None, self.ns, stretch_end=False))
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Anahtar ya da metin ara…"))
        self.search.textChanged.connect(self._apply_filter)
        self.seg = segmented(FILTERS, self._set_filter)
        right.add(row(self.seg, None, self.search, stretch_end=False))

        self.grid = QTableWidget(0, 3)
        self.grid.setHorizontalHeaderLabels([t("Anahtar"), t("İngilizce"), t("Çeviri")])
        self.grid.verticalHeader().setVisible(False)
        self.grid.setAlternatingRowColors(True)
        self.grid.setShowGrid(False)
        self.grid.setWordWrap(True)
        self.grid.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.grid.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
                                  QAbstractItemView.AnyKeyPressed)
        hh = self.grid.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.grid.setColumnWidth(0, 220)
        self.grid.itemChanged.connect(self._edited)
        right.add(self.grid, 1)

        self.stat = label("", "Muted")
        self.btn_save = button("Kaydet", "primary", self.save_jar)
        right.add(self.stat)
        right.add(row(None,
                      button("Orijinali Geri Yükle", "ghost", self.restore),
                      button("İçe Aktar", "ghost", self.import_file),
                      button("Dışa Aktar", "ghost", self.export),
                      button("İngilizceyi Kopyala", "ghost", self.copy_english,
                             tooltip="Boş satırlara İngilizce metni kopyalar (çeviriye başlangıç noktası)"),
                      self.btn_save, stretch_end=False))
        body.addWidget(right, 1)
        self._update_buttons()

    # --- klasör / tarama ---
    def _defaults(self):
        sp = self.app.config.server_path
        return [self.app.config.get("mods_folder") or os.path.join(sp, "mods"), os.path.join(sp, "plugins")]

    def default_folder(self):
        """Var olan mods/ ve plugins/ klasörleri (ikisi de yoksa ikisi birden gösterilir)."""
        d = self._defaults()
        return "; ".join([f for f in d if os.path.isdir(f)] or d)

    def _folders(self):
        return [f.strip() for f in self.folder.text().split(";") if f.strip()]

    def on_show(self):
        if not self.folder.text():
            self.folder.setText(self.default_folder())
            code = mc_lang_code(current())
            self.lang.blockSignals(True)
            self.lang.setCurrentIndex(max(0, self.lang.findData(code)))
            self.lang.blockSignals(False)
            self.scan()

    def _save_folder(self):
        # yalnızca tek ve varsayılandan farklı bir mod klasörü seçildiyse profile kaydedilir
        fs = self._folders()
        sp = self.app.config.server_path
        custom = [f for f in fs if os.path.normpath(f) not in (os.path.normpath(os.path.join(sp, "mods")),
                                                                os.path.normpath(os.path.join(sp, "plugins")))]
        self.app.config.set("mods_folder", custom[0] if len(custom) == 1 else "")
        self.scan()

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, t("Mod klasörünü seçin"), (self._folders() or [""])[0])
        if d:
            self.folder.setText(os.path.normpath(d))
            self._save_folder()

    def _confirm_discard(self):
        return not self.dirty or ask(self, t("Kaydedilmemiş değişiklikler var. Vazgeçilsin mi?"), t("Onay"))

    def scan(self, keep=None):
        if not self._confirm_discard():
            return
        folders = self._folders()
        existing = [f for f in folders if os.path.isdir(f)]
        self.mods = modtrans.scan(existing, self.lang.currentData())
        self.mod_table.blockSignals(True)
        fill_table(self.mod_table, [(m.name, "!" if m.error else m.missing) for m in self.mods], align_center=(1,))
        for r, m in enumerate(self.mods):
            it = self.mod_table.item(r, 1)
            it.setForeground(QColor(TOKENS["danger"] if m.error else TOKENS["accent"] if not m.missing else TOKENS["warn"]))
            self.mod_table.item(r, 0).setToolTip(m.error or m.jar)
        self.mod_table.blockSignals(False)
        if not existing:
            self.mods_lbl.setText(t("Klasör bulunamadı: {path}", path="; ".join(folders)))
        else:
            done = sum(1 for m in self.mods if not m.missing and not m.error)
            self.mods_lbl.setText(t("{n} mod/eklentide dil dosyası var · {done} tamamen çevrilmiş", n=len(self.mods), done=done))
        self.mod, self.dirty = None, False
        self.grid.setRowCount(0)
        self.title_lbl.setText(t("Bir mod seçin"))
        self.ns.clear()
        if keep:
            for r, m in enumerate(self.mods):
                if m.path == keep:
                    self.mod_table.selectRow(r)
        self._update_buttons()

    # --- mod seçimi ---
    def _mod_selected(self):
        r = self.mod_table.currentRow()
        if not (0 <= r < len(self.mods)) or (self.mod and self.mods[r].path == self.mod.path):
            return
        if not self._confirm_discard():
            return
        self.mod, self.dirty = self.mods[r], False
        self.title_lbl.setText(f"{self.mod.name}  ·  {self.mod.jar}")
        self.ns.blockSignals(True)
        self.ns.clear()
        for lf in self.mod.files:
            self.ns.addItem(lf.label)
        self.ns.setVisible(len(self.mod.files) > 1)
        self.ns.blockSignals(False)
        self.idx = 0
        self._load()

    def _ns_changed(self, i):
        if i < 0 or not self.mod or i == self.idx:
            return
        if not self._confirm_discard():
            self.ns.blockSignals(True)
            self.ns.setCurrentIndex(self.idx)
            self.ns.blockSignals(False)
            return
        self.idx = i
        self._load()

    def _load(self):
        if self.mod.error:
            self.error(self.mod.error)
            return
        self.en, self.tr = modtrans.load(self.mod, self.idx)
        self.dirty = False
        self._fill()

    # --- tablo ---
    def _fill(self):
        self._filling = True
        g = self.grid
        g.setRowCount(0)
        g.setRowCount(len(self.en))
        for r, (k, en) in enumerate(self.en.items()):
            ki = QTableWidgetItem(k)
            ki.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            ki.setForeground(QColor(TOKENS["text_muted"]))
            ei = QTableWidgetItem(en)
            ei.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            ti = QTableWidgetItem(self.tr.get(k, ""))
            ti.setData(Qt.UserRole, k)
            g.setItem(r, 0, ki)
            g.setItem(r, 1, ei)
            g.setItem(r, 2, ti)
            self._mark(r)
        g.resizeRowsToContents()
        self._filling = False
        self._apply_filter()
        self._stats()
        self._update_buttons()

    def _mark(self, r):
        k = self.grid.item(r, 0).text()
        ti = self.grid.item(r, 2)
        val = ti.text()
        if val and not modtrans.tokens_ok(self.en[k], val):
            ti.setBackground(QColor(TOKENS["danger"]).darker(250))
            ti.setToolTip(t("Biçim kodları İngilizce metinle aynı değil (%s, %player%, §a, &c, <red>, {0}…)."))
        else:
            ti.setBackground(QColor(0, 0, 0, 0))
            ti.setToolTip("")

    def _edited(self, item):
        if self._filling or item.column() != 2:
            return
        k = item.data(Qt.UserRole)
        self.tr[k] = item.text()
        self.dirty = True
        self._mark(item.row())
        self._stats()
        self._update_buttons()

    def _set_filter(self, i):
        self.filter = i
        self._apply_filter()
        from .. import motion
        motion.soft(self.grid)

    def _apply_filter(self):
        q = self.search.text().lower()
        for r in range(self.grid.rowCount()):
            k = self.grid.item(r, 0).text()
            en, tr = self.en.get(k, ""), self.tr.get(k, "")
            vis = True
            if self.filter == 1:
                vis = not tr and bool(en)
            elif self.filter == 2:
                vis = bool(tr) and not modtrans.tokens_ok(en, tr)
            if vis and q:
                vis = q in k.lower() or q in en.lower() or q in tr.lower()
            self.grid.setRowHidden(r, not vis)

    def _stats(self):
        done = sum(1 for k, v in self.en.items() if self.tr.get(k) or not v)
        bad = sum(1 for k in self.en if self.tr.get(k) and not modtrans.tokens_ok(self.en[k], self.tr[k]))
        txt = t("{done}/{total} çevrildi", done=done, total=len(self.en))
        if bad:
            txt += " · " + t("{n} hatalı", n=bad)
        if self.dirty:
            txt += " · " + t("kaydedilmedi")
        self.stat.setText(txt)

    def _update_buttons(self):
        self.btn_save.setEnabled(bool(self.mod) and self.dirty)

    # --- işlemler ---
    def copy_english(self):
        if not self.mod:
            return
        for k, v in self.en.items():
            if not self.tr.get(k):
                self.tr[k] = v
        self.dirty = True
        self._fill()

    def save_jar(self):
        if not self.mod or self.read_only():
            return
        bad = sum(1 for k in self.en if self.tr.get(k) and not modtrans.tokens_ok(self.en[k], self.tr[k]))
        if bad and not ask(self, t("{n} satırda biçim kodları uyuşmuyor; oyunda hata verebilir. Yine de kaydedilsin mi?", n=bad), t("Onay")):
            return
        if self.app.server.is_running and not ask(self, t("Sunucu çalışıyor. Değişiklik yeniden başlatınca geçerli olur. Kaydedilsin mi?"), t("Onay")):
            return
        try:
            n = modtrans.save(self.mod, self.idx, self.tr, self.en)
        except Exception as e:
            self.error(str(e))
            return
        self.dirty = False
        msg = t("{n} satır {file} içine kaydedildi.", n=n, file=self.mod.files[self.idx].tgt.rsplit("/", 1)[1])
        copy = modtrans.data_copy_path(self.mod, self.idx)
        if copy:
            msg += "\n" + t("Eklentinin kullandığı kopya da güncellendi: {path}", path=copy)
        self.info(msg)
        self.scan(keep=self.mod.path)

    def export(self):
        if not self.mod:
            return
        d = QFileDialog.getExistingDirectory(self, t("Dışa aktarılacak klasörü seçin"), os.path.expanduser("~"))
        if d:
            out = modtrans.export(self.mod, self.idx, d, self.lang.currentData())
            self.info(t("Dosyalar dışa aktarıldı:\n{path}\n\nÇeviriyi bitirince İçe Aktar ile geri yükle.", path=out))

    def import_file(self):
        if not self.mod:
            return
        p, _ = QFileDialog.getOpenFileName(self, t("Çeviri dosyasını seçin"), "", "JSON / YAML (*.json *.yml *.yaml)")
        if not p:
            return
        try:
            data = modtrans.read_translation_file(p)
        except Exception as e:
            self.error(str(e))
            return
        n = 0
        for k, v in data.items():
            if k in self.en and v:
                self.tr[k] = v
                n += 1
        self.dirty = True
        self._fill()
        self.info(t("{n} satır içe aktarıldı. Jar'a yazmak için Kaydet'e bas.", n=n))

    def restore(self):
        if not self.mod or self.read_only():
            return
        if ask(self, t("'{name}' çeviri öncesi orijinal hâline döndürülsün mü?", name=self.mod.name), t("Onay")):
            self.dirty = False
            if modtrans.restore_original(self.mod):
                self.scan(keep=self.mod.path)
            else:
                self.info("Bu mod için yedek yok; daha önce panelden değiştirilmemiş.")
