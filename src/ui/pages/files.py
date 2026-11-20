"""Dosyalar: sunucu klasörünün tamamı ağaç halinde. Çift tıklayınca dosya seçili düzenleyicide açılır
(VS Code, Notepad++, Not Defteri ya da varsayılan program). İş mantığı core.explorer'da."""
import os

from PySide6.QtCore import QDir, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileSystemModel, QHeaderView, QLineEdit, QMenu, QTreeView,
)

from core import explorer
from .. import icons
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, button, human_size, label, row

HEADERS = ("Ad", "Boyut", "Tür", "Değiştirilme")


class _Model(QFileSystemModel):
    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and section < len(HEADERS):
            return t(HEADERS[section])
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.column() == 1:      # boyut: Windows dilinden bağımsız
            return "" if self.isDir(index) else human_size(self.size(index))
        return super().data(index, role)


class _Filter(QSortFilterProxyModel):
    """Ad süzgeci: eşleşen dosyalar ve onları içeren (açılmış) klasörler görünür."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.root = ""

    def set_text(self, text):
        self.text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, r, parent):
        if not self.text:
            return True
        m = self.sourceModel()
        idx = m.index(r, 0, parent)
        path = m.filePath(idx)
        if not explorer.inside(self.root, path):      # kök ve üstündeki klasörler hep görünür
            return True
        if self.text in m.fileName(idx).lower():
            return True
        if m.isDir(idx):                               # yüklenmiş alt öğelerden biri eşleşiyorsa
            return any(self.filterAcceptsRow(i, idx) for i in range(m.rowCount(idx)))
        return False

    def lessThan(self, a, b):                         # klasörler önce
        m = self.sourceModel()
        da, db = m.isDir(a), m.isDir(b)
        if da != db:
            return da if self.sortOrder() == Qt.AscendingOrder else db
        return super().lessThan(a, b)


class FilesPage(Page):
    title = "Dosyalar"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.settings = app.config.settings
        self.editors = {}

        card = Card("Sunucu Dosyaları",
                    "Sunucu klasöründeki tüm dosyalar. Çift tıklayınca dosya seçtiğin düzenleyicide açılır; "
                    "jar, dünya ve oyuncu verisi gibi metin olmayan dosyalar Gezgin'de gösterilir.")
        self.editor = QComboBox()
        self.editor.setToolTip(t("Dosyaların açılacağı program"))
        self.editor.activated.connect(self._editor_changed)
        b_refresh = button("Yenile", "ghost", self.on_show)
        b_refresh.setIcon(icons.icon("rotate-ccw", None, 16))
        b_folder = button("Klasörü Aç", "ghost", lambda: explorer.open_path(self._root()))
        b_folder.setIcon(icons.icon("folder-open", None, 16))
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Dosya adında ara (açık klasörlerde)…"))
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=200)
        self._search_timer.timeout.connect(lambda: self.proxy.set_text(self.search.text()))
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        bar = row(label("Düzenleyici:", "Muted"), self.editor, b_refresh, b_folder, stretch_end=False)
        bar.insertWidget(0, self.search, 1)
        bar.insertSpacing(1, 8)
        card.add(bar)

        self.model = _Model(self)
        self.model.setReadOnly(True)
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden | QDir.System)
        self.proxy = _Filter(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setRecursiveFilteringEnabled(False)

        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.doubleClicked.connect(self._activated)
        hh = self.tree.header()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.setColumnHidden(2, True)           # Qt'nin tür açıklamaları yalnızca İngilizce; uzantı yeterli
        card.add(self.tree, 1)

        self.note = label("", "Muted", wrap=True)
        card.add(self.note)
        self.root.addWidget(card, 1)

        bridge.state.connect(lambda _s: self._note())
        self._loaded_root = None

    # ------------------------------------------------------------------ yardımcılar
    def _root(self):
        return self.app.config.server_path

    def _path(self, proxy_index):
        return self.model.filePath(self.proxy.mapToSource(proxy_index))

    def _fill_editors(self):
        self.editors = explorer.find_editors()
        self.editor.clear()
        for key in ["auto"] + [k for k in ("vscode", "notepadpp", "notepad", "system") if k in self.editors]:
            name = explorer.EDITORS[key]
            if key == "auto":
                name = t(name) + " (" + self._editor_name(explorer.resolve("auto", self.editors)) + ")"
            else:
                name = self._editor_name(key)
            self.editor.addItem(name, key)
        cur = self.settings.get("file_editor") or "auto"
        i = self.editor.findData(cur)
        self.editor.setCurrentIndex(i if i >= 0 else 0)

    @staticmethod
    def _editor_name(key):
        return t(explorer.EDITORS[key])

    def _editor_changed(self, _i):
        self.settings.set("file_editor", self.editor.currentData())

    def _note(self, text=None):
        if text is None:
            text = t("Sunucu açık: yapılandırma dosyalarındaki değişiklikler sunucu yeniden başlatılınca geçerli olur.") \
                if self.app.server.is_running else ""
        self.note.setText(text)

    # ------------------------------------------------------------------ sayfa
    def on_show(self):
        self._fill_editors()
        root = self._root()
        if not os.path.isdir(root):
            self._note(t("Sunucu klasörü bulunamadı:\n{path}", path=root))
            return
        if self._loaded_root != root:
            self.proxy.root = root
            src = self.model.setRootPath(root)
            self.tree.setRootIndex(self.proxy.mapFromSource(src))
            self._loaded_root = root
        self._note()

    def _activated(self, index):
        path = self._path(index)
        if os.path.isdir(path):
            return                                   # klasör: QTreeView kendisi açar/kapar
        self.open(path)

    def open(self, path, choice=None):
        try:
            res = explorer.open_file(path, choice or self.settings.get("file_editor") or "auto", self._root())
        except explorer.ExplorerError as e:
            self.error(t(e.template, **e.kw))
            return
        except OSError as e:
            self.error(t("Dosya açılamadı: {error}", error=str(e)))
            return
        name = os.path.basename(path)
        if res == "revealed":
            self._note(t("'{name}' metin dosyası değil; Gezgin'de gösterildi.", name=name))
        elif res == "editor" and self.app.server.is_running and explorer.is_config(path):
            self._note()

    # ------------------------------------------------------------------ sağ tık
    def _menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        path = self._path(index)
        is_dir = os.path.isdir(path)
        m = QMenu(self)
        if is_dir:
            m.addAction(icons.icon("folder-open", None, 16), t("Aç"), lambda: explorer.open_path(path))
        else:
            m.addAction(icons.icon("external-link", None, 16), t("Aç"), lambda: self.open(path))
            from core import configedit
            if configedit.kind_of(path) and explorer.inside(self._root(), path):
                m.addAction(icons.icon("settings", None, 16), t("Spypaper'da düzenle"), lambda: self.edit_inside(path))
            if explorer.is_text(path):
                sub = m.addMenu(t("Birlikte aç"))
                for key in ("vscode", "notepadpp", "notepad", "system"):
                    if key in self.editors:
                        sub.addAction(self._editor_name(key), lambda k=key: self.open(path, k))
            m.addAction(icons.icon("folder-open", None, 16), t("Klasörde göster"), lambda: explorer.reveal(path))
        m.addAction(icons.icon("copy", None, 16), t("Yolu kopyala"),
                    lambda: QApplication.clipboard().setText(os.path.normpath(path)))
        m.addSeparator()
        a = m.addAction(icons.icon("x", TOKENS["danger"], 16), t("Geri Dönüşüm Kutusu'na taşı"),
                        lambda: self._recycle(path))
        a.setEnabled(explorer.inside(self._root(), path))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def edit_inside(self, path):
        """Dosyayı Yapılandırma sekmesinde açar."""
        w = self.parentWidget()
        while w is not None and not (hasattr(w, "pages") and hasattr(w, "go")):
            w = w.parentWidget()
        if w is None:
            return
        from .configs import ConfigsPage
        page = next((p for p in w.pages if isinstance(p, ConfigsPage)), None)
        if page:
            w.go(w.pages.index(page))
            page.select_file(os.path.relpath(path, self._root()).replace(os.sep, "/"))

    def _recycle(self, path):
        if self.read_only():
            return
        if self.app.server.is_running:
            self.warn("Sunucu çalışırken dosya silinemez. Önce sunucuyu durdur.")
            return
        name = os.path.basename(path)
        if not self.confirm(t("'{name}' Geri Dönüşüm Kutusu'na taşınsın mı?", name=name)):
            return
        try:
            explorer.recycle(self._root(), path)
        except explorer.ExplorerError as e:
            self.error(t(e.template, **e.kw))
        except OSError as e:
            self.error(t("Silinemedi: {error}", error=str(e)))
