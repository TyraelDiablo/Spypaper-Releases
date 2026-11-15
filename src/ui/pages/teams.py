"""Takımlar: /team ile takım oluşturma, silme, üye ekleme/çıkarma ve takım ayarları."""
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)

from core import N_, teams as T
from core.danger import level_name
from ..i18n import t
from ..msgbox import get_text
from ..theme import TOKENS
from ..widgets import Card, Page, button, label, row


def swatch(hex_color, size=14):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(TOKENS["border"]))
    p.setBrush(QColor(hex_color) if hex_color else Qt.NoBrush)
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.end()
    return QIcon(pm)


class TeamsPage(Page):
    title = "Takımlar"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.teams = []
        self.current = None
        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        left = Card("Takımlar")
        left.setFixedWidth(270)
        self.btn_new = button("Yeni Takım", "primary", self.new_team)
        left.header_actions.addWidget(self.btn_new)
        self.list = QListWidget()
        self.list.setIconSize(QSize(14, 14))
        self.list.currentItemChanged.connect(self.on_select)
        left.add(self.list, 1)
        self.count_lbl = left.add(label("", "Muted", wrap=True))
        body.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)
        self.state_lbl = label("", "Muted", wrap=True)
        right.addWidget(self.state_lbl)

        cfg = Card("Takım Ayarları")
        self.title_lbl = label("", "BigValue", raw=True)
        cfg.add(self.title_lbl)
        form = QFormLayout()
        form.setSpacing(8)
        self.display = QLineEdit()
        self.color = QComboBox()
        for c in T.COLORS + ["reset"]:
            self.color.addItem(swatch(T.COLOR_HEX[c]), t(T.COLOR_NAMES[c]), c)
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText(t("ör. [Kırmızı]"))
        self.suffix = QLineEdit()
        self.ff = QCheckBox(t("Takım arkadaşları birbirine hasar verebilir"))
        self.inv = QCheckBox(t("Görünmez takım arkadaşları yarı saydam görünür"))
        for cb in (self.ff, self.inv):
            cb.setCursor(Qt.PointingHandCursor)
        self.nametag = self._combo(T.VISIBILITY, T.VISIBILITY_NAMES)
        self.death = self._combo(T.VISIBILITY, T.VISIBILITY_NAMES)
        self.collision = self._combo(T.COLLISION, T.COLLISION_NAMES)
        form.addRow(t("Görünen ad"), self.display)
        form.addRow(t("Renk"), self.color)
        form.addRow(t("Ad öneki / soneki"), row(self.prefix, self.suffix, stretch_end=False))
        form.addRow(t("İsim etiketi görünür"), self.nametag)
        form.addRow(t("Ölüm mesajları görünür"), self.death)
        form.addRow(t("Çarpışma (itme)"), self.collision)
        cfg.add(form)
        cfg.add(self.ff)
        cfg.add(self.inv)
        self.btn_save = button("Ayarları Uygula", "primary", self.apply)
        self.btn_empty = button("Takımı Boşalt", "warn", self.empty)
        self.btn_del = button("Takımı Sil", "danger", self.delete)
        cfg.add(row(self.btn_save, self.btn_empty, self.btn_del))
        right.addWidget(cfg)

        mem = Card("Üyeler")
        self.members = QListWidget()
        mem.add(self.members, 1)
        self.who = QComboBox()
        self.who.setEditable(True)
        self.who.setMinimumWidth(220)
        self.who.lineEdit().setPlaceholderText(t("Oyuncu adı"))
        self.btn_join = button("Takıma Ekle", "primary", self.join)
        self.btn_leave = button("Takımdan Çıkar", "ghost", self.leave)
        mem.add(row(self.who, self.btn_join, self.btn_leave))
        right.addWidget(mem, 1)

        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.timeout.connect(self.reload)
        bridge.state.connect(lambda s: self._sync())
        self._sync()

    def _combo(self, values, names):
        cb = QComboBox()
        for v in values:
            cb.addItem(t(names[v]), v)
        return cb

    # ------------------------------------------------------------ veri
    def on_show(self):
        self.reload()

    def reload(self):
        try:
            level = level_name(self.app.properties)
        except Exception:
            level = "world"
        self.teams = T.read_teams(self.app.config.server_path, level)
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        for tm in self.teams:
            it = QListWidgetItem(swatch(T.COLOR_HEX.get(tm["color"], "")),
                                 f"{tm['display']}  ({len(tm['players'])})")
            it.setData(Qt.UserRole, tm["name"])
            it.setToolTip(tm["name"])
            self.list.addItem(it)
        self.list.blockSignals(False)
        self.count_lbl.setText(t("{n} takım", n=len(self.teams)) if self.teams else
                               t("Henüz takım yok. Sunucu açıkken Yeni Takım ile oluştur."))
        names = sorted({p.name for p in self.app.players.list_players() if not p.name.startswith("Bilinmeyen")},
                       key=str.lower)
        cur = self.who.currentText()
        self.who.clear()
        self.who.addItems(names)
        self.who.setEditText(cur)
        idx = next((i for i, tm in enumerate(self.teams) if tm["name"] == keep), 0 if self.teams else -1)
        self.list.setCurrentRow(idx)
        if idx < 0:
            self.on_select(None)
        self._sync()

    def team(self):
        return next((tm for tm in self.teams if tm["name"] == self.current), None)

    def on_select(self, item, _prev=None):
        self.current = item.data(Qt.UserRole) if item else None
        tm = self.team()
        self.members.clear()
        if not tm:
            self.title_lbl.setText(t("Takım seçin"))
            self._sync()
            return
        self.title_lbl.setText(tm["name"])
        self.display.setText(tm["display"] if tm["display"] != tm["name"] else "")
        self._set(self.color, tm["color"] if tm["color"] in T.COLOR_HEX else "reset")
        self.prefix.setText(tm["prefix"])
        self.suffix.setText(tm["suffix"])
        self.ff.setChecked(tm["friendly_fire"])
        self.inv.setChecked(tm["see_invisible"])
        self._set(self.nametag, tm["nametag"])
        self._set(self.death, tm["death"])
        self._set(self.collision, tm["collision"])
        self.members.addItems(tm["players"] or [])
        if not tm["players"]:
            self.members.addItem(t("(boş)"))
        self._sync()

    @staticmethod
    def _set(combo, value):
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _sync(self):
        running = self.app.server.is_running
        has = self.team() is not None
        self.state_lbl.setText("" if running else t("Sunucu kapalı: takımlar yalnızca görüntülenir. Değiştirmek için sunucuyu başlat."))
        self.state_lbl.setVisible(not running)
        self.btn_new.setEnabled(running)
        for w in (self.btn_save, self.btn_empty, self.btn_del, self.btn_join, self.btn_leave):
            w.setEnabled(running and has)

    # ------------------------------------------------------------ komutlar
    def _run(self, cmds):
        if self.read_only():
            return False
        confirmed = False
        if int(self.app.config.get("safe_mode") or 0) == 2 and len(cmds) > 1:   # Orta: tek seferde onay
            if not self.confirm(t("Bu komut gönderilsin mi?") + "\n" + "\n".join(cmds)):
                return False
            confirmed = True
        for c in cmds:
            if not self.send(c, confirmed=confirmed):
                return False
        self.app.server.try_send("save-all")            # scoreboard.dat güncellensin
        self.reload_timer.start(1500)
        return True

    def new_team(self):
        name, ok = get_text(self, t("Yeni Takım"), t("Takım adı (boşluksuz; harf, rakam, _ . + -):"))
        if not ok or not name.strip():
            return
        name = name.strip()
        if any(tm["name"].lower() == name.lower() for tm in self.teams):
            self.warn(t("'{name}' adında bir takım zaten var.", name=name))
            return
        try:
            cmd = T.cmd_add(name)
        except ValueError as e:
            self.warn(t(str(e)))
            return
        if self._run([cmd]):
            self.current = name

    def apply(self):
        tm = self.team()
        if not tm:
            return
        after = {"display": self.display.text().strip() or tm["name"], "color": self.color.currentData(),
                 "prefix": self.prefix.text(), "suffix": self.suffix.text(), "friendly_fire": self.ff.isChecked(),
                 "see_invisible": self.inv.isChecked(), "nametag": self.nametag.currentData(),
                 "death": self.death.currentData(), "collision": self.collision.currentData()}
        try:
            cmds = T.cmd_modify(tm["name"], tm, after)
        except ValueError:
            return
        if cmds:
            self._run(cmds)

    def empty(self):
        tm = self.team()
        if tm and self.confirm(t("'{name}' takımındaki herkes çıkarılsın mı?", name=tm["display"])):
            self._run([T.cmd_empty(tm["name"])])

    def delete(self):
        tm = self.team()
        if tm and self.confirm(t("'{name}' takımı silinsin mi?", name=tm["display"])):
            self._run([T.cmd_remove(tm["name"])])

    def join(self):
        tm = self.team()
        who = self.who.currentText().strip()
        if not tm or not who:
            return
        try:
            cmd = T.cmd_join(tm["name"], who)
        except ValueError as e:
            self.warn(t(str(e), name=who))
            return
        self._run([cmd])

    def leave(self):
        it = self.members.currentItem()
        who = it.text() if it and it.text() != t("(boş)") else self.who.currentText().strip()
        if not who:
            return
        try:
            cmd = T.cmd_leave(who)
        except ValueError as e:
            self.warn(t(str(e), name=who))
            return
        self._run([cmd])


N_("Takımlar")
