"""Velocity proxy sayfası: proxy ayarları, bağlı sunucular ve Spypaper'daki sunucuları tek tıkla ağa ekleme."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHeaderView, QInputDialog, QLineEdit, QMessageBox,
                               QTableWidget, QTableWidgetItem, QAbstractItemView)

from core import N_, velocity as V
from core.config import is_proxy
from ..i18n import t
from ..widgets import Card, Page, button, label, row


class VelocityPage(Page):
    title = N_("Velocity Ağı")

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.missing = label("", "Muted", wrap=True)
        self.root.addWidget(self.missing)

        self.cfg = Card("Proxy Ayarları", "velocity.toml içindeki temel ayarlar. Değişiklikler proxy yeniden başlayınca geçerli olur.")
        self.bind = QLineEdit()
        self.bind.setObjectName("Mono")
        self.motd = QLineEdit()
        self.online = QCheckBox(t("Yalnızca Minecraft hesabı olanlar girebilsin (online-mode)"))
        self.fwd = QComboBox()
        for k, n in (("modern", N_("Modern (önerilen, Paper 1.13+)")), ("legacy", N_("Eski (BungeeCord uyumlu)")),
                     ("bungeeguard", "BungeeGuard"), ("none", N_("Kapalı"))):
            self.fwd.addItem(t(n), k)
        self.cfg.add(row(label("Adres:port"), self.bind, label("MOTD"), self.motd, stretch_end=False))
        self.cfg.add(row(label("Oyuncu bilgisi aktarımı"), self.fwd, self.online))
        self.root.addWidget(self.cfg)

        self.net = Card("Bağlı Sunucular", "Oyuncular ilk sıradaki sunucuya bağlanır; o kapalıysa sıradakine geçer. "
                                           "Arka uç sunucuların portu dışarı açılmamalı, yalnızca proxy portu açılmalı.")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([t("Ad"), t("Adres"), t("Giriş sırası")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.net.add(self.table, 1)
        self.net.add(row(button("Spypaper Sunucusu Ekle…", "primary", self.add_profile),
                         button("Adres Ekle…", "ghost", self.add_manual),
                         button("Yukarı", "ghost", lambda: self.move_row(-1)),
                         button("Aşağı", "ghost", lambda: self.move_row(1)),
                         button("Kaldır", "ghost", self.remove), None,
                         button("Kaydet", "primary", self.save), stretch_end=False))
        self.state = label("", "Muted", wrap=True)
        self.net.add(self.state)
        self.root.addWidget(self.net, 1)

    # ------------------------------------------------------------------
    @property
    def path(self):
        return self.app.config.server_path

    def on_show(self):
        applied = False
        try:
            applied = V.apply_pending(self.path)
        except Exception:
            pass
        try:
            d = V.load(self.path)
        except Exception as e:
            self.missing.setText(t(e.template, **e.kw) if hasattr(e, "template") else str(e))
            self.missing.show()
            self.cfg.setEnabled(False)
            self.net.setEnabled(False)
            return
        self.missing.hide()
        self.cfg.setEnabled(True)
        self.net.setEnabled(True)
        self.bind.setText(d["bind"])
        self.motd.setText(d["motd"])
        self.online.setChecked(d["online_mode"])
        i = self.fwd.findData(d["forwarding"])
        self.fwd.setCurrentIndex(max(i, 0))
        order = [n for n in d["try"] if n in d["servers"]] + [n for n in d["servers"] if n not in d["try"]]
        self.table.setRowCount(0)
        for n in order:
            self._add_row(n, d["servers"][n], n in d["try"])
        self.state.setText(t("Oluştururken seçtiğin port ve MOTD velocity.toml'a yazıldı. Proxy'yi yeniden başlat.")
                           if applied else "")

    def _add_row(self, name, addr, in_try=True):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(addr))
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(Qt.Checked if in_try else Qt.Unchecked)
        self.table.setItem(r, 2, it)

    def _names(self):
        return [self.table.item(r, 0).text().strip() for r in range(self.table.rowCount())]

    def add_manual(self):
        name, ok = QInputDialog.getText(self, t("Adres Ekle"), t("Sunucu adı (ör. lobi):"))
        if not ok or not name.strip():
            return
        addr, ok = QInputDialog.getText(self, t("Adres Ekle"), t("Adres (ör. 127.0.0.1:25566):"), text="127.0.0.1:25566")
        if ok and addr.strip():
            self._add_row(V.unique_name(name, self._names()), addr.strip())

    def add_profile(self):
        win = self.window()
        here = os.path.normcase(os.path.abspath(self.path))
        profs = [p for p in win.settings.servers()
                 if os.path.normcase(os.path.abspath(p.server_path)) != here and not is_proxy(p.server_path)]
        if not profs:
            QMessageBox.information(self, t("Velocity Ağı"), t("Eklenecek başka sunucu yok. Önce bir Paper sunucusu oluştur."))
            return
        names = [f"{p.name}  ({p.server_path})" for p in profs]
        pick, ok = QInputDialog.getItem(self, t("Spypaper Sunucusu Ekle"), t("Ağa eklenecek sunucu:"), names, 0, False)
        if not ok:
            return
        prof = profs[names.index(pick)]
        if QMessageBox.question(self, t("Spypaper Sunucusu Ekle"), t(
                "{name} proxy'ye bağlansın mı?\n\nSunucunun paper-global.yml dosyasında Velocity desteği açılır, gizli anahtar "
                "yazılır ve server.properties'te online-mode=false yapılır (hesap doğrulamasını proxy üstlenir). "
                "Değişiklikler sunucu yeniden başlayınca geçerli olur.", name=prof.name)) != QMessageBox.Yes:
            return
        try:
            V.link_backend(self.path, prof.server_path)
        except Exception as e:
            QMessageBox.warning(self, t("Velocity Ağı"), t(e.template, **e.kw) if hasattr(e, "template") else str(e))
            return
        self._add_row(V.unique_name(prof.name, self._names()), f"127.0.0.1:{V.backend_port(prof.server_path)}")
        i = self.fwd.findData("modern")
        self.fwd.setCurrentIndex(i)
        self.state.setText(t("{name} bağlandı. Kaydet'e basmayı unutma.", name=prof.name))

    def move_row(self, d):
        r = self.table.currentRow()
        n = r + d
        if r < 0 or not 0 <= n < self.table.rowCount():
            return
        vals = [[self.table.item(x, c).text() if c < 2 else self.table.item(x, c).checkState() for c in range(3)]
                for x in (r, n)]
        for x, v in zip((n, r), vals):
            self.table.item(x, 0).setText(v[0])
            self.table.item(x, 1).setText(v[1])
            self.table.item(x, 2).setCheckState(v[2])
        self.table.setCurrentCell(n, 0)

    def remove(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def save(self):
        servers, tries = {}, []
        for r in range(self.table.rowCount()):
            n, a = self.table.item(r, 0).text().strip(), self.table.item(r, 1).text().strip()
            if not n or not a:
                continue
            servers[n] = a
            if self.table.item(r, 2).checkState() == Qt.Checked:
                tries.append(n)
        try:
            V.save(self.path, bind=self.bind.text().strip() or "0.0.0.0:25577", motd=self.motd.text(),
                   online_mode=self.online.isChecked(), forwarding=self.fwd.currentData(), servers=servers,
                   try_order=tries)
            if self.fwd.currentData() == "modern":
                V.secret(self.path)
        except Exception as e:
            self.state.setText(t("Kaydedilemedi: {e}", e=e))
            return
        self.state.setText(t("Kaydedildi. Proxy'yi yeniden başlatınca geçerli olur."))
