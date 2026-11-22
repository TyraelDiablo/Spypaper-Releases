"""Yeni Sunucu → Dünya: normal dünya oluşumu (seed, tür, yapılar) ya da hazır harita taslağı."""
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget,
)

from core import maps
from . import i18n, icons, motion
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row, segmented

CARD = QSize(232, 130)


class WorldPicker(QWidget):
    loaded = Signal(object, str)
    image_ready = Signal(str, str)

    def __init__(self, contact="", parent=None):
        super().__init__(parent)
        self.contact = contact
        self.maps = None
        self.server_version = ""
        self._loading = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        self.tabs = segmented(["Normal dünya", "Taslak"], self._mode)
        v.addWidget(self.tabs)
        self.stack = QStackedWidget()
        motion.auto_fade(self.stack, dy=0)
        v.addWidget(self.stack)

        # --- normal dünya
        nw = QWidget()
        f = QFormLayout(nw)
        f.setContentsMargins(0, 0, 0, 0)
        f.setSpacing(8)
        self.seed = QLineEdit()
        self.seed.setPlaceholderText(t("Boş bırakırsan oyun rastgele seçer"))
        self.seed.setMaxLength(64)
        f.addRow(t("Seed"), row(self.seed, button("Rastgele", "ghost", self._random), stretch_end=False))
        self.ltype = QComboBox()
        for k, n in maps.LEVEL_TYPES:
            self.ltype.addItem(t(n), k)
        self.structures = QCheckBox(t("Yapılar oluşsun (köy, kale, tapınak…)"))
        self.structures.setChecked(True)
        f.addRow(t("Dünya türü"), row(self.ltype, None))
        f.addRow("", self.structures)
        self.stack.addWidget(nw)

        # --- taslak
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(6)
        self.state = label("", "Muted", wrap=True, raw=True)
        self.retry = button("Yeniden dene", "ghost", self.load)
        self.retry.hide()
        tv.addLayout(row(self.state, None, self.retry, stretch_end=False))
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(CARD)
        self.list.setGridSize(QSize(CARD.width() + 16, CARD.height() + 44))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setWordWrap(True)
        self.list.setMinimumHeight(CARD.height() + 60)
        self.list.currentItemChanged.connect(self._selected)
        tv.addWidget(self.list)
        self.desc = label("", wrap=True, raw=True)
        tv.addWidget(self.desc)
        tv.addLayout(row(button("Zip'ten İçe Aktar…", "ghost", self._import_zip),
                         button("Klasörden İçe Aktar…", "ghost", self._import_dir), None))
        self.stack.addWidget(tw)

        self.loaded.connect(self._on_loaded)
        self.image_ready.connect(self._on_image)

    # --- normal dünya ---
    def _random(self):
        self.seed.setText(maps.random_seed())

    def _mode(self, i):
        self.stack.setCurrentIndex(i)
        if i == 1 and self.maps is None:
            self.load()

    def is_template(self):
        return self.stack.currentIndex() == 1

    def world_options(self):
        return {"seed": self.seed.text().strip(), "level_type": self.ltype.currentData(),
                "structures": self.structures.isChecked()}

    # --- taslaklar ---
    def load(self):
        if self._loading:
            return
        self._loading = True
        self.retry.hide()
        self.state.setText(t("Haritalar alınıyor…"))

        def work():
            try:
                self.loaded.emit(maps.fetch_manifest(self.contact), "")
            except Exception as e:
                self.loaded.emit(None, t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, items, err):
        self._loading = False
        if err:
            self.state.setText(t("Harita listesi alınamadı: {e}", e=err))
            self.retry.show()
            return
        imported = [m for m in (self.maps or []) if m["id"] == "import"]
        self.maps = items or []
        self.list.clear()
        lang = i18n.current()
        blank = QPixmap(CARD)
        blank.fill(Qt.transparent)
        for m in self.maps:
            it = QListWidgetItem(QIcon(blank), maps.text(m.get("name"), lang))
            it.setData(Qt.UserRole, m["id"])
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.list.addItem(it)
            threading.Thread(target=lambda m=m: self.image_ready.emit(m["id"], maps.image_path(m, self.contact) or ""),
                             daemon=True).start()
        self.state.setText(t("{n} harita", n=len(self.maps)) if self.maps else t("Henüz harita yok."))
        if imported:                                       # liste gelmeden içe aktarılan harita korunur
            self._add_import(imported[0]["_import"])
        elif self.maps:
            self.list.setCurrentRow(0)

    def _on_image(self, mid, path):
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            return
        pm = pm.scaled(CARD, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x, y = (pm.width() - CARD.width()) // 2, (pm.height() - CARD.height()) // 2
        pm = pm.copy(x, y, CARD.width(), CARD.height())
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == mid:
                it.setIcon(QIcon(pm))

    # --- kendi haritanı içe aktar ---
    def _import_zip(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, t("Harita zip dosyasını seç"), "", "Zip (*.zip *.mcworld)")
        if path:
            self._add_import(path)

    def _import_dir(self):
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, t("Dünya klasörünü seç (içinde level.dat olan)"))
        if path:
            self._add_import(path)

    def _add_import(self, path):
        try:
            m = maps.local_map(path)
        except maps.MapError as e:
            self.state.setText(t(e.template, **e.kw))
            return
        m["desc"] = t("İçe aktarılan harita: {path}", path=path)
        self.maps = [x for x in (self.maps or []) if x["id"] != "import"]
        self.maps.insert(0, m)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == "import":
                self.list.takeItem(i)
                break
        it = QListWidgetItem(QIcon(icons.icon("folder-open", None, 64).pixmap(CARD)), m["name"])
        it.setData(Qt.UserRole, "import")
        it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.list.insertItem(0, it)
        self.list.setCurrentRow(0)
        self.state.setText(t("{n} harita", n=len(self.maps)))

    def template(self):
        it = self.list.currentItem()
        if not it or not self.maps:
            return None
        return next((m for m in self.maps if m["id"] == it.data(Qt.UserRole)), None)

    def set_server_version(self, v):
        self.server_version = v or ""
        self._selected()

    def _selected(self, *_):
        m = self.template()
        if not m:
            self.desc.setText("")
            return
        lang = i18n.current()
        parts = [f"<b>{maps.text(m.get('name'), lang)}</b>", maps.text(m.get("desc"), lang)]
        meta = t("Minecraft {v} ve sonrası", v=m.get("mc") or "?")
        if m.get("size"):
            meta += f" · {m['size'] / 1048576:.1f} MB"
        parts.append(f"<span style='opacity:.7'>{meta}</span>")
        if not maps.compatible(m, self.server_version):
            parts.append(f"<span style='color:{TOKENS['danger']}'>" + t("Bu harita Minecraft {v} ile yapıldı; seçili sürümde "
                         "açılmaz. Sürümü {v} ya da daha yeni yap.", v=m.get("mc")) + "</span>")
        self.desc.setText("<br>".join(p for p in parts if p))

    def validate(self):
        """Hata metni ya da boş."""
        if not self.is_template():
            s = self.seed.text().strip()
            return t("Seed boşluk içeremez.") if " " in s else ""
        m = self.template()
        if not m:
            return t("Bir harita seç.")
        if not maps.compatible(m, self.server_version):
            return t("Bu harita Minecraft {v} ile yapıldı; seçili sürümde açılmaz. Sürümü {v} ya da daha yeni yap.",
                     v=m.get("mc"))
        return ""
