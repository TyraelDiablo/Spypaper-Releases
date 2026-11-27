"""Bedrock sunucuları için Oyuncular sayfası: dünya veritabanından oyuncu bilgisi, izin listesi ve yetkiler."""
import re
import threading

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QInputDialog

from core import N_, bedrock_players as BPL
from ..i18n import t
from ..widgets import Card, Page, button, color, err_text, fill_table, label, row, table

NAME_OK = re.compile(r"^[A-Za-z0-9 _]{1,32}$")      # Xbox oyuncu etiketi (boşluk olabilir)


def _items(items):
    return ", ".join(f"{i['count']}× {i.get('custom') or i['id']}" + (" ✦" if i.get("ench") else "") for i in items) or "—"


class BedrockPlayersPage(Page):
    title = N_("Oyuncular")
    loaded = Signal(object, object)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.loaded.connect(self._loaded)
        c = Card("Bedrock Oyuncuları", "Sunucuya en az bir kez girmiş oyuncular ve izin listesindekiler. "
                                       "Bilgiler dünya veritabanından okunur; sunucu açıkken kısa bir an kayıt bekletilir.")
        c.header_actions.addWidget(button("Oyuncu Ekle (izin listesi)…", "primary", self.add))
        c.header_actions.addWidget(button("Yenile", "ghost", self.on_show))
        self.tbl = table(["Oyuncu", "Boyut", "Konum", "Oyun modu", "Seviye", "Yetki", "İzin listesi"], stretch_col=0)
        self.tbl.itemSelectionChanged.connect(self._sel)
        c.add(self.tbl, 1)
        self.perm = QComboBox()
        for k in BPL.PERMS:
            self.perm.addItem(t(BPL.PERM_NAMES[k]), k)
        self.b_perm = button("Yetkiyi Uygula", "ghost", self.apply_perm)
        self.b_allow = button("İzin Listesine Ekle / Çıkar", "ghost", self.toggle_allow)
        c.add(row(label("Yetki"), self.perm, self.b_perm, self.b_allow, None, stretch_end=False))
        self.state = label("", "Muted", wrap=True)
        c.add(self.state)
        self.root.addWidget(c, 3)
        d = Card("Ayrıntılar", "")
        self.detail = label("", wrap=True)
        self.detail.setTextInteractionFlags(self.detail.textInteractionFlags())
        d.add(self.detail)
        self.root.addWidget(d, 2)
        self.players, self.busy = [], False
        self._sel()

    @property
    def path(self):
        return self.app.config.server_path

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

    def _loaded(self, res, err):
        self.busy = False
        if err is not None:
            self.state.setText(err_text(err))
            return
        self.players = res
        rows = []
        for p in res:
            pos = "{:.0f}, {:.0f}, {:.0f}".format(*p["pos"]) if p.get("has_data") else "—"
            rows.append((p["name"], t(BPL.DIMENSIONS.get(p.get("dim"), "?")) if p.get("has_data") else "—", pos,
                         t(BPL.GAMEMODES.get(p.get("gamemode"), "?")) if p.get("has_data") else "—",
                         p.get("level", "—") if p.get("has_data") else "—",
                         t(BPL.PERM_NAMES.get(p["perm"], p["perm"])), t("Evet") if p["allowed"] else t("Hayır")))
        fill_table(self.tbl, rows, align_center=(1, 3, 4, 5, 6))
        for r, p in enumerate(res):
            if p["perm"] == "operator":
                self.tbl.item(r, 5).setForeground(QColor(color("accent")))
        self.state.setText(t("{n} oyuncu", n=len(res)) if res else
                           t("Henüz oyuncu yok. Bir oyuncu sunucuya girip çıkınca burada görünür."))
        self._sel()

    def _cur(self):
        r = self.tbl.currentRow()
        return self.players[r] if 0 <= r < len(self.players) and self.tbl.selectedItems() else None

    def _sel(self):
        p = self._cur()
        self.b_perm.setEnabled(bool(p and p.get("xuid")))
        self.b_allow.setEnabled(bool(p))
        if not p:
            self.detail.setText(t("Bir oyuncu seç."))
            return
        self.perm.setCurrentIndex(max(0, self.perm.findData(p["perm"])))
        lines = [f"<b>{p['name']}</b>" + (f"  ·  xuid {p['xuid']}" if p.get("xuid") else "")]
        if not p.get("has_data"):
            lines.append(t("Bu oyuncu sunucuya henüz girmemiş."))
        else:
            hp = p.get("health")
            lines.append(t("Can: {hp} · Açlık: {hu} · Seviye: {lv}",
                           hp=f"{hp:.0f}" if isinstance(hp, (int, float)) else "?",
                           hu=f"{p['hunger']:.0f}" if isinstance(p.get("hunger"), (int, float)) else "?",
                           lv=p.get("level", 0)))
            lines.append(t("Konum: {pos} ({dim})", pos="{:.1f}, {:.1f}, {:.1f}".format(*p["pos"]),
                           dim=t(BPL.DIMENSIONS.get(p["dim"], "?"))))
            lines.append("<br><b>" + t("Envanter") + "</b>: " + _items(p["inventory"]))
            lines.append("<b>" + t("Zırh") + "</b>: " + _items(p["armor"]) + "  ·  <b>" + t("Sol el") + "</b>: "
                         + _items(p["offhand"]))
            lines.append("<b>" + t("Ender sandığı") + "</b>: " + _items(p["ender"]))
        self.detail.setText("<br>".join(lines))

    # ------------------------------------------------------------------ işlemler
    def _running(self):
        return self.app.server.is_running

    def apply_perm(self):
        p = self._cur()
        if not p or not p.get("xuid"):
            return
        level = self.perm.currentData()
        BPL.set_permission(self.path, p["xuid"], level)
        if self._running():
            if level == "operator":
                self.app.server.try_send(f'op "{p["name"]}"')
            elif p["perm"] == "operator":
                self.app.server.try_send(f'deop "{p["name"]}"')
            self.app.server.try_send("permission reload")
        self.on_show()

    def toggle_allow(self):
        p = self._cur()
        if p:
            self._allow(p["name"], p.get("xuid", ""), not p["allowed"])

    def add(self):
        name, ok = QInputDialog.getText(self, t("İzin listesine ekle"), t("Oyuncunun Xbox oyuncu etiketi (gamertag):"))
        name = (name or "").strip()
        if not ok or not name:
            return
        if not NAME_OK.match(name):
            self.error(t("Geçersiz oyuncu etiketi."))
            return
        self._allow(name, "", True)

    def _allow(self, name, xuid, on):
        if self._running():                     # sunucu dosyayı kendisi yazar ve xuid'i ilk girişte doldurur
            self.app.server.try_send(f'allowlist {"add" if on else "remove"} "{name}"')
        else:
            BPL.set_allowed(self.path, name, xuid, on)
        self.on_show()
