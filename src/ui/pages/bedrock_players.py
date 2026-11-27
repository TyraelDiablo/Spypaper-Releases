"""Bedrock sunucuları için Oyuncular sayfası: Java'daki sayfayla aynı düzen (liste + özet + işlemler + envanter).
Veri dünya veritabanından (LevelDB) okunur; izin listesi ve yetkiler de buradan yönetilir."""
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QTableWidgetItem, QVBoxLayout)

from core import N_, bedrock_players as BPL
from .. import heads
from ..i18n import t
from ..msgbox import get_item
from ..widgets import Card, Page, button, color, err_text, fill_table, label, row, segmented, table

VIEWS = [N_("Envanter"), N_("Zırh"), N_("Ender Sandığı"), N_("2. El")]
ARMOR_SLOTS = [N_("Kask"), N_("Göğüslük"), N_("Pantolon"), N_("Bot"), N_("Gövde")]


def _q(name):
    return '"' + name.replace('"', "") + '"'        # Bedrock adlarında boşluk olabilir


class BedrockPlayersPage(Page):
    title = N_("Oyuncular")
    loaded = Signal(object, object)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.loaded.connect(self._loaded)
        self.players, self.current, self.view, self.busy = [], None, 0, False

        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        # --- sol: liste ---
        left = Card("Oyuncular")
        left.setFixedWidth(250)
        left.header_actions.addWidget(button("Yenile", "ghost", self.on_show))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(t("Ara…"))
        self.filter.textChanged.connect(self.populate)
        self.list = QListWidget()
        self.list.setIconSize(QSize(24, 24))
        self.list.currentItemChanged.connect(self.on_select)
        left.add(self.filter)
        left.add(self.list, 1)
        left.add(button("Oyuncu Ekle (izin listesi)…", "primary", self.add))
        self.count_lbl = left.add(label("", "Muted"))
        body.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)

        # --- özet ---
        head = Card()
        self.name_lbl = label("Oyuncu seçin", "BigValue")
        self.status_lbl = label("", "Muted")
        self.status_lbl.setTextFormat(Qt.RichText)
        from ..hud import HudWidget
        self.hud = HudWidget()
        self.hud.setFixedSize(self.hud.sizeHint())
        self.hud_text = label("", "Muted")
        stats = QHBoxLayout()
        stats.setSpacing(16)
        stats.addWidget(self.hud)
        stats.addWidget(self.hud_text, 0, Qt.AlignBottom)
        stats.addStretch(1)
        self.face = QLabel()
        self.face.setFixedSize(48, 48)
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_col.addWidget(self.name_lbl)
        name_col.addWidget(self.status_lbl)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(self.face, 0, Qt.AlignTop)
        top.addLayout(name_col, 1)
        head.add(top)
        head.add(stats)
        right.addWidget(head)

        # --- işlemler ---
        acts = Card("İşlemler", "Sunucu açıkken seçili oyuncuya uygulanır")
        grid = QGridLayout()
        grid.setSpacing(6)
        actions = [
            (N_("Can Ver"), "primary", lambda: self.cmd('effect {p} instant_health 1 255 true')),
            (N_("Tokluk Ver"), "warn", lambda: self.cmd('effect {p} saturation 1 255 true')),
            (N_("Acıktır"), "ghost", lambda: self.cmd('effect {p} hunger 30 255 true')),
            (N_("Eşya Ver"), "purple", self.give_item),
            (N_("Öldür"), "danger", self.kill),
            (N_("Rastgele Işınla"), "info", lambda: self.cmd('spreadplayers 0 0 0 5000 {p}')),
            (N_("Oyuncuya Işınla"), "purple", self.tp_player),
            (N_("Oyun Modu…"), "ghost", self.gamemode),
        ]
        self.action_buttons = []
        for i, (txt, v, fn) in enumerate(actions):
            b = button(txt, v, fn)
            grid.addWidget(b, i // 4, i % 4)
            self.action_buttons.append(b)
        acts.add(grid)
        self.perm = QComboBox()
        for k in BPL.PERMS:
            self.perm.addItem(t(BPL.PERM_NAMES[k]), k)
        self.b_perm = button("Yetkiyi Uygula", "ghost", self.apply_perm)
        self.b_allow = button("İzin Listesine Ekle / Çıkar", "ghost", self.toggle_allow)
        acts.add(row(label("Yetki"), self.perm, self.b_perm, self.b_allow, None, stretch_end=False))
        right.addWidget(acts)

        # --- envanter ---
        data = Card()
        data.add(row(segmented(VIEWS, self.set_view)))
        self.table = table(["Slot", "Eşya", "Miktar", "Özellikler"], stretch_col=3)
        self.table.setIconSize(QSize(28, 28))
        self.table.verticalHeader().setDefaultSectionSize(36)
        data.add(self.table, 1)
        self.state = label("", "Muted", wrap=True)
        data.add(self.state)
        right.addWidget(data, 1)
        bridge.state.connect(lambda s: self._update_actions())
        self._update_actions()

    @property
    def path(self):
        return self.app.config.server_path

    # ------------------------------------------------------------------ veri
    def on_show(self):
        if self.busy:
            return
        self.busy = True
        self.state.setText(t("Oyuncu verileri okunuyor…"))
        path, server = self.path, self.app.server

        def work():
            try:
                self.loaded.emit(BPL.load(path, server), None)
            except Exception as e:
                self.loaded.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _online(self):
        try:
            return {n.lower() for n in self.app.online_players()}
        except Exception:
            return set()

    def _loaded(self, res, err):
        self.busy = False
        if err is not None:
            self.state.setText(err_text(err))
            return
        on = self._online()
        for p in res:
            p["online"] = p["name"].lower() in on
        self.players = sorted(res, key=lambda p: (not p["online"], p["name"].lower()))
        self.state.setText("" if res else t("Henüz oyuncu yok. Bir oyuncu sunucuya girip çıkınca burada görünür."))
        keep = self.current["name"] if self.current else None
        self.populate()
        if keep:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole)["name"] == keep:
                    self.list.setCurrentRow(i)

    def populate(self):
        q = self.filter.text().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.players:
            if q and q not in p["name"].lower():
                continue
            it = QListWidgetItem(p["name"])
            it.setIcon(QIcon(heads.pixmap(p.get("xuid") or p["name"], p["name"], 24, p["online"])))
            it.setForeground(QColor(color("text") if p["online"] else color("text_muted")))
            it.setData(Qt.UserRole, p)
            self.list.addItem(it)
        self.list.blockSignals(False)
        self.count_lbl.setText(t("{n} oyuncu · {on} çevrimiçi", n=len(self.players),
                                 on=sum(p["online"] for p in self.players)))

    def on_select(self, item, _prev=None):
        if not item:
            return
        p = self.current = item.data(Qt.UserRole)
        self.name_lbl.setText(p["name"])
        st = (f'<span style="color:{color("accent")}">● {t("Çevrimiçi")}</span>' if p["online"]
              else f'<span style="color:{color("text_muted")}">○ {t("Çevrimdışı")}</span>')
        gm = BPL.GAMEMODES.get(p.get("gamemode")) if p.get("has_data") else None
        perm = t(BPL.PERM_NAMES.get(p["perm"], p["perm"]))
        allowed = t("İzin listesinde") if p["allowed"] else t("İzin listesinde değil")
        extra = f'  ·  <span style="color:{color("info")}; font-weight:600">{t(gm)}</span>' if gm else ""
        xu = f'  ·  <span style="color:{color("text_muted")}">xuid {p["xuid"]}</span>' if p.get("xuid") else ""
        self.status_lbl.setText(f"{st}{extra}  ·  {perm}  ·  {allowed}{xu}")
        self.face.setPixmap(heads.pixmap(p.get("xuid") or p["name"], p["name"], 48))
        self.perm.setCurrentIndex(max(0, self.perm.findData(p["perm"])))
        if p.get("has_data"):
            hp = p.get("health") or 0
            food = int(p.get("hunger") or 0)
            hidden = p.get("gamemode") in (1, 6)
            self.hud.set_values(int(round(hp)), food, 0, float(p.get("absorption") or 0), p.get("level", 0),
                                p.get("progress", 0.0), hidden)
            pos = "{:.0f}, {:.0f}, {:.0f}".format(*p["pos"])
            self.hud_text.setText(t("Can {hp}/20 · Açlık {food}/20 · Seviye {lvl}", hp=f"{hp:.0f}", food=food,
                                    lvl=p.get("level", 0)) + "  ·  " +
                                  t("Konum: {pos} ({dim})", pos=pos, dim=t(BPL.DIMENSIONS.get(p["dim"], "?"))))
        else:
            self.hud.clear()
            self.hud_text.setText(t("Bu oyuncu sunucuya henüz girmemiş."))
        self._update_actions()
        self.show_view()

    def set_view(self, i):
        self.view = i
        self.show_view()

    def _icon(self, item_id):
        from core.players import icon_path
        cache = self.__dict__.setdefault("_icons", {})
        if item_id not in cache:
            icon = None
            p = icon_path(item_id, self.path)
            if p:
                pm = QPixmap(p)
                if not pm.isNull():
                    side = min(pm.width(), pm.height())
                    icon = QIcon(pm.copy(0, 0, side, side).scaled(28, 28, Qt.KeepAspectRatio, Qt.FastTransformation))
            cache[item_id] = icon
        return cache[item_id]

    def show_view(self):
        p = self.current
        if not p:
            return
        if not p.get("has_data"):
            fill_table(self.table, [("–", t("Veri yok"), "–", "")], align_center=(0, 2))
            return
        items = {0: p["inventory"], 1: p["armor"], 2: p["ender"], 3: p["offhand"]}[self.view]
        empty = {0: N_("(Envanter boş)"), 1: N_("(Zırh yok)"), 2: N_("(Ender sandığı boş)"), 3: N_("(2. el boş)")}
        if not items:
            fill_table(self.table, [("–", t(empty[self.view]), "–", "")], align_center=(0, 2))
            return
        tr = self.app.players.translations
        self.table.setRowCount(0)
        for n, it in enumerate(items):
            if self.view == 1:
                slot = t(ARMOR_SLOTS[n]) if n < len(ARMOR_SLOTS) else str(n)
            else:
                slot = str(it["slot"]) if it["slot"] >= 0 else "–"
            name = tr.item_name(it["id"])
            if it.get("custom"):
                name = f'{it["custom"]}  ({name})'
            props = []
            if it.get("ench"):
                props.append(t("{n} büyü", n=it["ench"]))
            if it.get("damage"):
                props.append(t("Hasar: {n}", n=it["damage"]))
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((slot, name, f'{it["count"]}×', " · ".join(props))):
                cell = QTableWidgetItem(v)
                if c in (0, 2):
                    cell.setTextAlignment(Qt.AlignCenter)
                cell.setToolTip(f'minecraft:{it["id"]}')
                self.table.setItem(r, c, cell)
            ic = self._icon(it["id"])
            if ic:
                self.table.item(r, 1).setIcon(ic)
            if it.get("ench"):
                self.table.item(r, 1).setForeground(QColor(color("info")))

    # ------------------------------------------------------------------ işlemler
    def _running(self):
        return self.app.server.is_running

    def _update_actions(self):
        on = self._running() and self.current is not None
        for b in self.action_buttons:
            b.setEnabled(on)
        self.b_perm.setEnabled(bool(self.current and self.current.get("xuid")))
        self.b_allow.setEnabled(self.current is not None)

    def cmd(self, template):
        if self.current:
            self.send(template.format(p=_q(self.current["name"])))

    def kill(self):
        if self.current and self.confirm(t("{name} öldürülsün mü?", name=self.current["name"])):
            self.cmd("kill {p}")

    def give_item(self):
        if not self.current:
            return
        from .players import GiveItemDialog
        dlg = GiveItemDialog(self.app.players.translations, self)
        if dlg.exec():
            iid, n = dlg.result_item()
            if iid:
                self.cmd(f"give {{p}} {iid} {n}")

    def tp_player(self):
        if not self.current:
            return
        names = [p["name"] for p in self.players if p["name"] != self.current["name"] and p["online"]]
        if not names:
            self.info(t("Işınlanacak çevrimiçi başka oyuncu yok."))
            return
        target, ok = get_item(self, t("Oyuncuya Işınla"), t("{name} kimin yanına ışınlansın?",
                                                             name=self.current["name"]), names, 0, False)
        if ok and target:
            self.cmd(f"tp {{p}} {_q(target)}")

    def gamemode(self):
        if not self.current:
            return
        modes = [("survival", N_("Hayatta Kalma")), ("creative", N_("Yaratıcı")), ("adventure", N_("Macera")),
                 ("spectator", N_("İzleyici")), ("default", N_("Varsayılan"))]
        pick, ok = get_item(self, t("Oyun Modu…"), t("{name} için oyun modu:", name=self.current["name"]),
                            [t(n) for _, n in modes], 0, False)
        if ok:
            key = next(k for k, n in modes if t(n) == pick)
            self.cmd(f"gamemode {key} {{p}}")

    def apply_perm(self):
        p = self.current
        if not p or not p.get("xuid"):
            return
        level = self.perm.currentData()
        BPL.set_permission(self.path, p["xuid"], level)
        if self._running() and p.get("online"):         # op/deop yalnızca oyundaki oyuncuda çalışır
            if level == "operator":
                self.app.server.try_send(f"op {_q(p['name'])}")
            elif p["perm"] == "operator":
                self.app.server.try_send(f"deop {_q(p['name'])}")
        if self._running():
            self.app.server.try_send("permission reload")
        self.on_show()

    def toggle_allow(self):
        p = self.current
        if p:
            self._allow(p["name"], p.get("xuid", ""), not p["allowed"])

    def add(self):
        import re
        name, ok = QInputDialog.getText(self, t("İzin listesine ekle"), t("Oyuncunun Xbox oyuncu etiketi (gamertag):"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if not re.fullmatch(r"[A-Za-z0-9 _]{1,32}", name):
            self.error(t("Geçersiz oyuncu etiketi."))
            return
        self._allow(name, "", True)

    def _allow(self, name, xuid, on):
        if self._running():
            self.app.server.try_send(f'allowlist {"add" if on else "remove"} {_q(name)}')
        else:
            BPL.set_allowed(self.path, name, xuid, on)
        self.on_show()
