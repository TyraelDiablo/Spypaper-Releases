from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QInputDialog, QLineEdit,
    QListWidget, QListWidgetItem, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from core.players import (
    PLAYER_COMMANDS, build_command, give_command, parse_list_output,
    tp_death_command, tp_to_player_command,
)
from core import N_
from ..i18n import t
from ..widgets import Card, Page, button, color, fill_table, label, row, segmented, table


class GiveItemDialog(QDialog):
    def __init__(self, translations, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("Eşya Ver"))
        self.resize(420, 520)
        self.tr = translations
        lay = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Eşya ara (ad ya da ID)…"))
        self.search.textChanged.connect(self.update_list)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.accept)
        self.amount = QSpinBox()
        self.amount.setRange(1, 6400)
        self.amount.setValue(1)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(t("Ver"))
        btns.button(QDialogButtonBox.Cancel).setText(t("İptal"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(self.search)
        lay.addWidget(self.list, 1)
        lay.addLayout(row(label("Miktar:"), self.amount))
        lay.addWidget(btns)
        self.update_list()

    def update_list(self):
        self.list.clear()
        for iid, name in self.tr.search_items(self.search.text()):
            it = QListWidgetItem(f"{name}    ·  {iid}")
            it.setData(Qt.UserRole, iid)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def result_item(self):
        it = self.list.currentItem()
        return (it.data(Qt.UserRole), self.amount.value()) if it else (None, 0)


class PlayersPage(Page):
    title = "Oyuncular"
    VIEWS = [N_("Envanter"), N_("Zırh"), N_("Ender Sandığı"), N_("2. El"), N_("İstatistikler")]

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.players = []
        self.current = None
        self.details = None
        self.online_names = None
        self.view = 0

        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        # --- sol: oyuncu listesi ---
        left = Card("Oyuncular")
        left.setFixedWidth(250)
        self.btn_refresh = button("Yenile", "ghost", self.refresh)
        left.header_actions.addWidget(self.btn_refresh)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("Ara…"))
        self.filter.textChanged.connect(self.populate)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self.on_select)
        left.add(self.filter)
        left.add(self.list, 1)
        self.count_lbl = left.add(label("", "Muted"))
        body.addWidget(left)

        # --- sağ ---
        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)

        # özet kartı
        head = Card()
        self.name_lbl = label("Oyuncu seçin", "BigValue")
        self.status_lbl = label("", "Muted")
        self.status_lbl.setTextFormat(Qt.RichText)
        stats = QHBoxLayout()
        stats.setSpacing(28)
        self.stat_vals = {}
        for key, title in (("xp", N_("XP Seviyesi")), ("hp", N_("Can")), ("food", N_("Açlık"))):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(title, "Muted"))
            v = label("–", "CardTitle")
            col.addWidget(v)
            self.stat_vals[key] = v
            stats.addLayout(col)
        stats.addStretch(1)
        top = QHBoxLayout()
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_col.addWidget(self.name_lbl)
        name_col.addWidget(self.status_lbl)
        top.addLayout(name_col, 1)
        top.addLayout(stats)
        head.add(top)
        right.addWidget(head)

        # aksiyonlar
        acts = Card("İşlemler", "Sunucu açıkken seçili oyuncuya uygulanır")
        grid = QGridLayout()
        grid.setSpacing(6)
        actions = [
            (N_("Can Ver"), "primary", lambda: self.cmd("heal")),
            (N_("Tokluk Ver"), "warn", lambda: self.cmd("feed")),
            (N_("Acıktır"), "ghost", lambda: self.cmd("starve")),
            (N_("Eşya Ver"), "purple", self.give_item),
            (N_("Öldür"), "danger", self.kill),
            (N_("Spawn'a Işınla"), "info", lambda: self.cmd("spawn")),
            (N_("Son Ölüm Noktası"), "info", self.tp_death),
            (N_("Rastgele Işınla"), "info", lambda: self.cmd("random_tp")),
            (N_("Oyuncuya Işınla"), "purple", self.tp_player),
        ]
        self.action_buttons = []
        for i, (txt, v, fn) in enumerate(actions):
            b = button(txt, v, fn)
            grid.addWidget(b, i // 5, i % 5)
            self.action_buttons.append(b)
        acts.add(grid)
        right.addWidget(acts)

        # veri tablosu
        data = Card()
        data.add(row(segmented(self.VIEWS, self.set_view)))
        self.table = table(["Slot", "Eşya", "Miktar", "Özellikler"], stretch_col=3)
        self.table.setIconSize(QSize(28, 28))
        self.table.verticalHeader().setDefaultSectionSize(36)
        data.add(self.table, 1)
        self.lang_lbl = label("", "Muted", wrap=True)
        data.add(self.lang_lbl)
        right.addWidget(data, 1)

        bridge.line.connect(self._watch_list)
        bridge.state.connect(lambda s: self._update_actions())
        self._update_actions()
        self._loaded = False

    # --- yaşam döngüsü ---
    def on_show(self):
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def on_server_path_changed(self):
        self._loaded = False
        self.current = None
        self.on_show()

    def _watch_list(self, line):
        names = parse_list_output(line)
        if names is not None:
            self.online_names = names

    def refresh(self):
        """Sunucu açıksa önce save-all flush + list, 2 sn sonra diskten oku."""
        if self.app.server.is_running:
            self.app.server.try_send("save-all flush")
            self.app.server.try_send("list")
            self.btn_refresh.setEnabled(False)
            self.btn_refresh.setText(t("Bekleniyor…"))
            QTimer.singleShot(2000, self._load)
        else:
            self.online_names = set()
            self._load()

    def _load(self):
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText(t("Yenile"))
        keep = self.current.name if self.current else None
        self.players = self.app.players.list_players(self.online_names)
        self.populate()
        if keep:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole).name == keep:
                    self.list.setCurrentRow(i)
                    break

    def populate(self):
        q = self.filter.text().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.players:
            if q and q not in p.name.lower():
                continue
            it = QListWidgetItem(("●  " if p.online else "○  ") + p.name)
            it.setForeground(QColor(color("text") if p.online else color("text_muted")))
            it.setData(Qt.UserRole, p)
            self.list.addItem(it)
        self.list.blockSignals(False)
        online = sum(p.online for p in self.players)
        self.count_lbl.setText(t("{n} oyuncu · {on} çevrimiçi", n=len(self.players), on=online))
        if not self.players:
            self.table.setRowCount(0)

    def on_select(self, item, _prev=None):
        if not item:
            return
        self.current = item.data(Qt.UserRole)
        self.details = self.app.players.details(self.current)
        p = self.current
        self.name_lbl.setText(p.name)
        st = (f'<span style="color:{color("accent")}">● {t("Çevrimiçi")}</span>' if p.online
              else f'<span style="color:{color("text_muted")}">○ {t("Çevrimdışı")}</span>')
        self.status_lbl.setText(f'{st}  ·  <span style="color:{color("text_muted")}">{p.uuid}</span>')
        d = self.details
        self.stat_vals["xp"].setText(str(d.xp_level) if d else "–")
        self.stat_vals["hp"].setText(f"{d.health:.0f} / 20" if d else "–")
        self.stat_vals["food"].setText(f"{d.food} / 20" if d else "–")
        self._update_actions()
        self.show_view()

    def set_view(self, i):
        self.view = i
        self.show_view()

    def show_view(self):
        d = self.details
        if not self.current:
            return
        if self.view == 4:
            self.table.setHorizontalHeaderLabels(["", t("İstatistik"), t("Değer"), ""])
            s = self.app.players.stats(self.current)
            if not s:
                rows = [("–", t("İstatistik bulunamadı"), "–", "")]
            else:
                h, m = divmod(s["play_time_sec"] // 60, 60)
                rows = [
                    ("⏱", t("Oynama Süresi"), t("{h} sa {m} dk", h=h, m=m)),
                    ("☠", t("Ölüm"), s["deaths"]),
                    ("⚔", t("Öldürülen Mob"), s["mob_kills"]),
                    ("🗡", t("Öldürülen Oyuncu"), s["player_kills"]),
                    ("↑", t("Zıplama"), s["jumps"]),
                    ("→", t("Yürünen Mesafe"), f"{s['walk_cm'] / 100000:.1f} km"),
                ]
            fill_table(self.table, rows, align_center=(0, 2))
            return

        self.table.setHorizontalHeaderLabels([t("Slot"), t("Eşya"), t("Miktar"), t("Özellikler")])
        self._lang_status()
        if not d:
            fill_table(self.table, [("–", t("Veri dosyası okunamadı"), "–", "")])
            return
        items = {0: d.inventory, 1: d.armor, 2: d.ender, 3: [d.offhand] if d.offhand else []}[self.view]
        empty = {0: N_("(Envanter boş)"), 2: N_("(Ender sandığı boş)"), 3: N_("(2. el boş)")}
        if not items:
            fill_table(self.table, [("–", t(empty[self.view]), "–", "")], align_center=(0, 2))
            return
        self.table.setRowCount(0)
        for r in items:
            self._add_item_row(r)

    # --- eşya satırı: ikon + özellikler ---
    def _icon(self, item_id):
        from core.players import icon_path
        if not item_id:
            return None
        cache = self.__dict__.setdefault("_icons", {})
        if item_id not in cache:
            p = icon_path(item_id, self.app.config.server_path)
            icon = None
            if p:
                pm = QPixmap(p)
                if not pm.isNull():
                    side = min(pm.width(), pm.height())          # animasyonlu dokular: ilk kare
                    pm = pm.copy(0, 0, side, side).scaled(28, 28, Qt.KeepAspectRatio, Qt.FastTransformation)
                    icon = QIcon(pm)
            cache[item_id] = icon
        return cache[item_id]

    def _props(self, r):
        tr = self.app.players.translations
        from core.players import max_durability
        parts, tip = [], []
        if r.enchants:
            names = [tr.ench_name(e, l) for e, l in r.enchants]
            parts.append(", ".join(names))
            tip += names
        if r.stored:
            names = [tr.ench_name(e, l) for e, l in r.stored]
            parts.append("📖 " + ", ".join(names))
            tip += names
        if r.trim:
            tt = tr.trim_text(*r.trim)
            parts.append("✦ " + tt)
            tip.append(t("Kaplama: {trim}", trim=tt))
        mx = max_durability(r.item_id)
        if r.damage and mx:
            parts.append(t("Dayanıklılık {left}/{max}", left=max(0, mx - r.damage), max=mx))
        elif r.damage:
            parts.append(t("Hasar: {n}", n=r.damage))
        if r.color is not None:
            parts.append(f"#{r.color & 0xFFFFFF:06X}")
        if r.unbreakable:
            parts.append(t("Kırılmaz"))
        return " · ".join(parts), tip

    def _add_item_row(self, r):
        from ..theme import TOKENS
        tb = self.table
        i = tb.rowCount()
        tb.insertRow(i)
        props, tip = self._props(r)
        name = f"{r.custom_name}  ({t(r.name)})" if r.custom_name else t(r.name)
        cells = [t(r.slot), name, f"{r.count}×" if r.count else "–", props]
        for c, v in enumerate(cells):
            it = QTableWidgetItem(v)
            if c in (0, 2):
                it.setTextAlignment(Qt.AlignCenter)
            tb.setItem(i, c, it)
        name_it = tb.item(i, 1)
        icon = self._icon(r.item_id)
        if icon:
            name_it.setIcon(icon)
        if r.enchants or r.stored:
            name_it.setForeground(QColor(TOKENS["info"]))       # oyundaki büyülü eşya rengi gibi
        tooltip = "\n".join([name, f"minecraft:{r.item_id}"] + tip) if r.item_id else name
        for c in range(4):
            tb.item(i, c).setToolTip(tooltip)

    def _lang_status(self):
        tr = self.app.players.translations
        import os
        if tr.status == "ok":
            self.lang_lbl.setText(t("Eşya adları: {file}", file=os.path.basename(tr.file)))
        elif tr.status == "fallback":
            self.lang_lbl.setText(t("{file} bulunamadı, eşya adları İngilizce gösteriliyor. mc_dilleri_cikar.bat ile oyunun dil dosyalarını çıkarabilirsin.",
                                    file=tr.lang + ".json"))
        else:
            self.lang_lbl.setText(t("Minecraft dil dosyası bulunamadı; eşya adları ID'den üretiliyor. mc_dilleri_cikar.bat ile oyunun dil dosyalarını çıkarabilirsin."))

    # --- aksiyonlar ---
    def _update_actions(self):
        ok = self.current is not None and self.app.server.is_running
        for b in self.action_buttons:
            b.setEnabled(ok)

    def cmd(self, key):
        if self.current:
            self.send(build_command(PLAYER_COMMANDS[key], self.current.name))

    def kill(self):
        if self.current and self.confirm(t("{name} öldürülsün mü?", name=self.current.name)):
            self.cmd("kill")

    def give_item(self):
        if not self.current:
            return
        dlg = GiveItemDialog(self.app.players.translations, self)
        if dlg.exec():
            iid, n = dlg.result_item()
            if iid:
                self.send(give_command(self.current.name, iid, n))

    def tp_death(self):
        if not self.current:
            return
        if self.app.server.is_running:
            self.app.server.try_send("save-all flush")
        d = self.app.players.details(self.current)
        if d and d.last_death:
            self.send(tp_death_command(self.current.name, d.last_death))
        else:
            self.info("Son ölüm noktası verisi bulunamadı.")

    def tp_player(self):
        if not self.current:
            return
        names = [p.name for p in self.players if p.name != self.current.name]
        online_first = sorted(names, key=lambda n: n not in (self.online_names or set()))
        target, ok = QInputDialog.getItem(
            self, t("Oyuncuya Işınla"), t("{name} kimin yanına ışınlansın?", name=self.current.name),
            online_first, 0, True)
        if ok and target:
            self.send(tp_to_player_command(self.current.name, target))
