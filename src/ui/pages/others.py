"""Eklentiler, Ayarlar, Whitelist & Ban, Bakım, Harita sayfaları."""
import os
import threading

from PySide6.QtCore import QTime, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLineEdit,
    QListWidget, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableWidgetItem, QTimeEdit, QVBoxLayout,
    QWidget,
)

from core import N_, ServerError, modrinth as M
from core.config import detect_version
from core.files import read_name_list
from ..i18n import t
from ..widgets import Card, Page, button, color, fill_table, human_size, label, row, segmented, table


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ---------------------------------------------------------------- Eklentiler
class PluginsPage(Page):
    title = "Eklentiler"
    upd_done = Signal(object, object)       # (iş, sonuç) / hata

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        card = self.card = Card("Yüklü Eklentiler", "Devre dışı bırakılan eklentiler .jar.disabled olarak saklanır")
        self.btn_add = button("Eklenti Ekle", "primary", self.add)
        card.header_actions.addWidget(self.btn_add)
        for txt, v, fn in ((N_("Klasörü Aç"), "ghost", lambda: open_folder(self.app.plugins.folder)),
                           (N_("Yenile"), "ghost", self.on_show)):
            card.header_actions.addWidget(button(txt, v, fn))
        self.table = table(["Eklenti", "Boyut", "Durum"], stretch_col=0)
        self.table.itemSelectionChanged.connect(self._sel)
        card.add(self.table, 1)
        self.btn_toggle = button("Etkinleştir / Devre Dışı", "ghost", self.toggle)
        self.btn_delete = button("Sil", "danger", self.delete)
        self.hint = label("", "Muted")
        card.add(row(self.btn_toggle, self.btn_delete, None, self.hint, stretch_end=False))
        self.btn_upd = button("Güncellemeleri denetle", "ghost", self.check_updates)
        self.btn_upd_all = button("Tümünü güncelle", "primary", self.apply_updates)
        self.btn_upd_all.setVisible(False)
        card.add(row(self.btn_upd, self.btn_upd_all, None, stretch_end=False))
        self._updates = []
        self._upd_busy = False
        self.upd_done.connect(self._upd_done)
        from PySide6.QtWidgets import QStackedWidget
        self.tabs = segmented([N_("Yüklü"), N_("Modrinth"), N_("Kaynak Paketi")], self._tab)
        self.root.addWidget(self.tabs, 0, Qt.AlignLeft)
        self.stack = QStackedWidget()
        self.stack.addWidget(card)
        self.root.addWidget(self.stack, 1)
        self.browser = self.packs = None
        self.items = []
        self._sel()

    def _tab(self, i):
        from ..modrinth_view import ModrinthBrowser, ResourcePackView
        if i == 1 and self.browser is None:
            self.browser = ModrinthBrowser(self)
            self.browser.changed.connect(self.on_show)
            self.stack.addWidget(self.browser)
        if i == 2 and self.packs is None:
            self.packs = ResourcePackView(self)
            self.stack.addWidget(self.packs)
        w = {0: self.card, 1: self.browser, 2: self.packs}[i]
        self.stack.setCurrentWidget(w)
        if i == 1:
            self.browser.prepare()
        elif i == 2:
            self.packs.prepare()

    def page_title(self):
        return t("Modlar") if self.app.plugins.modded else t("Eklentiler")

    def on_show(self):
        mods = self.mods = self.app.plugins.modded
        # Fabric/Forge/NeoForge sunucularında aynı sayfa mods/ klasörünü yönetir
        self.card.title_lbl.setText(t("Yüklü Modlar") if mods else t("Yüklü Eklentiler"))
        if self.card.subtitle_lbl:
            self.card.subtitle_lbl.setText(
                t("Devre dışı bırakılan modlar .jar.disabled olarak saklanır. Oyuncuların da aynı modları kurması gerekebilir.")
                if mods else t("Devre dışı bırakılan eklentiler .jar.disabled olarak saklanır"))
        self.btn_add.setText(t("Mod Ekle") if mods else t("Eklenti Ekle"))
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem(t("Mod") if mods else t("Eklenti")))
        self.items = self.app.plugins.list()
        fill_table(self.table, [
            (n.replace(".disabled", ""), human_size(s), t("Etkin") if on else t("Devre dışı"))
            for n, s, on in self.items], align_center=(1, 2))
        for r, (_, _, on) in enumerate(self.items):
            self.table.item(r, 2).setForeground(QColor(color("accent") if on else color("text_muted")))
        n, on = len(self.items), sum(on for *_, on in self.items)
        self.hint.setText(t("{n} mod · {on} etkin", n=n, on=on) if mods else t("{n} eklenti · {on} etkin", n=n, on=on))
        self._sel()

    def check_updates(self):
        if self._upd_busy:
            return
        mc, soft = detect_version(self.app.config.server_path)
        _, loaders = M.context(soft, mc, self.app.plugins.modded)
        folder = self.app.plugins.folder
        self._upd_busy = True
        self.hint.setText(t("Güncellemeler denetleniyor…"))

        def work():
            try:
                self.upd_done.emit(("check", M.check_updates(folder, loaders, mc)), None)
            except Exception as e:
                self.upd_done.emit(("check", None), e)
        threading.Thread(target=work, daemon=True).start()

    def apply_updates(self):
        if self._upd_busy or not self._updates or self._blocked():
            return
        items, folder = list(self._updates), self.app.plugins.folder
        self._upd_busy = True
        self.hint.setText(t("Güncelleniyor…"))

        def work():
            errs, done = [], 0
            for it in items:
                try:
                    M.apply_update(it, folder)
                    done += 1
                except Exception as e:
                    errs.append(f"{it['name']}: {e}")
            self.upd_done.emit(("apply", (done, errs)), None)
        threading.Thread(target=work, daemon=True).start()

    def _upd_done(self, res, err):
        from ..modrinth_view import err_msg
        self._upd_busy = False
        if err is not None:
            self.hint.setText("")
            self.warn(err_msg(err), t("Güncelleme"))
            return
        job, data = res
        if job == "check":
            self._updates = data
            self.btn_upd_all.setVisible(bool(data))
            self.hint.setText("")
            if not data:
                self.info(t("Tüm dosyalar güncel ya da Modrinth'te bulunamadı."), t("Güncelleme"))
                return
            lines = "\n".join(f"{u['name']}: {u['current']} → {u['latest']}" for u in data)
            self.info(t("{n} güncelleme var:", n=len(data)) + "\n" + lines, t("Güncelleme"))
        else:
            done, errs = data
            self._updates = []
            self.btn_upd_all.setVisible(False)
            self.on_show()
            if errs:
                self.warn(t("Bazı güncellemeler kurulamadı:") + "\n" + "\n".join(errs), t("Güncelleme"))
            else:
                self.info(t("{n} dosya güncellendi. Değişiklik sunucu yeniden başlatılınca geçerli olur.", n=done), t("Güncelleme"))

    def _selected(self):
        r = self.table.currentRow()
        return self.items[r][0] if 0 <= r < len(self.items) and self.table.selectedItems() else None

    def _sel(self):
        has = self._selected() is not None
        self.btn_toggle.setEnabled(has)
        self.btn_delete.setEnabled(has)

    def _blocked(self):
        if self.app.server.is_running:
            self.warn(N_("Sunucu çalışırken modlar değiştirilemez.") if getattr(self, "mods", False)
                      else N_("Sunucu çalışırken eklentiler değiştirilemez."), "İşlem Engellendi")
            return True
        return False

    def add(self):
        if self.read_only():
            return
        mods = getattr(self, "mods", False)
        paths, _ = QFileDialog.getOpenFileNames(self, t("Mod Seçin") if mods else t("Eklenti Seçin"), "",
                                                "Java Archive (*.jar)")
        if paths:
            self.app.plugins.add(paths)
            self.on_show()
            if self.app.server.is_running:
                self.info(N_("Mod eklendi. Yüklenmesi için sunucuyu yeniden başlatın.") if mods
                          else N_("Eklenti eklendi. Yüklenmesi için sunucuyu yeniden başlatın."))

    def toggle(self):
        if self.read_only():
            return
        name = self._selected()
        if name and not self._blocked():
            self.app.plugins.toggle(name)
            self.on_show()

    def delete(self):
        if self.read_only():
            return
        name = self._selected()
        if name and not self._blocked() and self.confirm(t("'{name}' silinsin mi?", name=name)):
            self.app.plugins.remove(name)
            self.on_show()


# ---------------------------------------------------------------- Ayarlar
class SettingsPage(Page):
    title = "Sunucu Ayarları"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setObjectName("Page")
        self.col = QVBoxLayout(inner)
        self.col.setContentsMargins(0, 0, 6, 0)
        self.col.setSpacing(14)
        scroll.setWidget(inner)
        self.root.addWidget(scroll, 1)

        top = QHBoxLayout()
        top.setSpacing(14)

        # sunucu kimliği
        ident = Card("Görsel Kimlik", "Sunucu listesinde görünen logo (64×64 PNG)")
        self.icon = label()
        self.icon.setFixedSize(64, 64)
        self.icon.setStyleSheet(f"background:{color('surface_2')}; border-radius:8px;")
        self.icon.setAlignment(Qt.AlignCenter)
        ident.add(row(self.icon, button("Logo Değiştir", "ghost", self.change_icon)))
        ident.end()
        top.addWidget(ident, 1)

        # panel ayarları
        panel = Card("Panel Ayarları", "Sunucunun nasıl başlatılacağı")
        form = QFormLayout()
        form.setSpacing(8)
        self.java = QLineEdit()
        self.jar = QLineEdit()
        self.ram_min = QLineEdit()
        self.ram_max = QLineEdit()
        self.bluemap = QLineEdit()
        form.addRow(t("Java"), self.java)
        form.addRow(t("Jar dosyası"), self.jar)
        form.addRow(t("RAM (min / max)"), row(self.ram_min, self.ram_max, stretch_end=False))
        form.addRow(t("BlueMap adresi"), self.bluemap)
        self.keep = QSpinBox()
        self.keep.setRange(0, 999)
        self.keep.setSpecialValueText(t("Sınırsız"))
        self.keep.setToolTip(t("Yeni yedek alınınca en eski yedekler silinir"))
        form.addRow(t("Saklanacak yedek"), self.keep)
        panel.add(form)
        self.auto_restart = QCheckBox(t("Çökünce otomatik yeniden başlat"))
        self.auto_restart.setToolTip(t("Sunucu durdurulmadan kapanırsa 10 saniye sonra yeniden başlatılır. "
                                       "10 dakikada 3 kez çökerse durur."))
        self.auto_restart.setCursor(Qt.PointingHandCursor)
        panel.add(self.auto_restart)
        top.addWidget(panel, 2)
        self.col.addLayout(top)

        from ..borderbox import BorderCard
        self.border = BorderCard(self)
        self.col.addWidget(self.border)

        # server.properties
        props = Card("server.properties", "Değişikliklerin çoğu sunucu yeniden başlatılınca geçerli olur")
        self.search = QLineEdit()
        self.search.setPlaceholderText(t("Ayar ara…"))
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self._filter)
        props.header_actions.addWidget(self.search)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(4, 1)
        props.add(self.grid)
        self.col.addWidget(props)
        self.col.addStretch(1)

        self.root.addLayout(row(None, button("Kaydet", "primary", self.save), stretch_end=False))
        self.fields = {}

    def on_show(self):
        c = self.app.config
        self.java.setText(c.get("java_path"))
        self.jar.setText(c.get("jar_name"))
        self.ram_min.setText(c.get("ram_min"))
        self.ram_max.setText(c.get("ram_max"))
        self.bluemap.setText(c.get("bluemap_url"))
        self.keep.setValue(int(c.get("backup_keep") or 0))
        self.auto_restart.setChecked(bool(c.get("auto_restart")))
        self.border.load()

        ip = self.app.properties.icon_path
        if ip:
            self.icon.setPixmap(QPixmap(ip).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.icon.setText(t("yok"))

        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.fields.clear()
        props = self.app.properties.load()
        if not props:
            self.grid.addWidget(label("server.properties bulunamadı. Sunucuyu bir kez başlatın.", "Muted"), 0, 0)
            return
        for i, (k, v) in enumerate(props.items()):
            r, c0 = i // 2, (i % 2) * 3
            name = label(k, "Muted")
            name.setStyleSheet("font-family: Consolas;")
            if v.lower() in ("true", "false"):
                w = QCheckBox()
                w.setChecked(v.lower() == "true")
                w.setCursor(Qt.PointingHandCursor)
            else:
                w = QLineEdit(v)
            self.grid.addWidget(name, r, c0)
            self.grid.addWidget(w, r, c0 + 1)
            self.fields[k] = (name, w)
        self._filter()

    def _filter(self):
        q = self.search.text().lower()
        for k, (name, w) in self.fields.items():
            vis = q in k.lower()
            name.setVisible(vis)
            w.setVisible(vis)

    def change_icon(self):
        if self.read_only():
            return
        p, _ = QFileDialog.getOpenFileName(self, t("Sunucu Logosu (64×64 PNG)"), "", "PNG (*.png)")
        if not p:
            return
        if QPixmap(p).size().width() != 64 or QPixmap(p).size().height() != 64:
            self.warn("Minecraft yalnızca 64×64 boyutundaki logoları gösterir.")
            return
        self.app.properties.set_icon(p)
        self.on_show()

    def save(self):
        if self.read_only():
            return
        c = self.app.config
        for key, w in (("java_path", self.java), ("jar_name", self.jar), ("ram_min", self.ram_min),
                       ("ram_max", self.ram_max), ("bluemap_url", self.bluemap)):
            c.data[key] = w.text().strip()
        c.data["backup_keep"] = self.keep.value()
        c.data["auto_restart"] = self.auto_restart.isChecked()
        c.save()
        if self.fields:
            vals = {k: (w.isChecked() if isinstance(w, QCheckBox) else w.text()) for k, (_, w) in self.fields.items()}
            try:
                self.app.properties.save(vals)
            except Exception as e:
                self.error(str(e))
                return
        self.info("Ayarlar kaydedildi.")


# ---------------------------------------------------------------- Whitelist & Ban
class AdminPage(Page):
    title = "Whitelist & Ban"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        act = Card("Oyuncu İşlemi", "Komutlar sunucu açıkken gönderilir")
        self.name = QLineEdit()
        self.name.setPlaceholderText(t("Oyuncu adı"))
        self.name.setFixedWidth(260)
        act.add(row(
            self.name,
            button("Whitelist'e Ekle", "primary", lambda: self.run("whitelist add")),
            button("Whitelist'ten Çıkar", "warn", lambda: self.run("whitelist remove")),
            button("Banla", "danger", lambda: self.run("ban")),
            button("Banı Kaldır", "info", lambda: self.run("pardon")),
            button("OP Ver", "purple", lambda: self.run("op")),
            button("OP Al", "ghost", lambda: self.run("deop")),
        ))
        self.root.addWidget(act)

        lists = QHBoxLayout()
        lists.setSpacing(14)
        self.lists = {}
        for fn, title in (("whitelist.json", N_("Whitelist")), ("banned-players.json", N_("Banlılar")), ("ops.json", N_("Operatörler"))):
            c = Card(title)
            lw = QListWidget()
            lw.itemClicked.connect(lambda it: self.name.setText(it.text()))
            c.add(lw, 1)
            lists.addWidget(c, 1)
            self.lists[fn] = (c, lw)
        self.root.addLayout(lists, 1)
        bridge.line.connect(self._maybe_reload)

    def on_show(self):
        sp = self.app.config.server_path
        for fn, (_, lw) in self.lists.items():
            lw.clear()
            names = read_name_list(sp, fn)
            lw.addItems(names or [])
            if not names:
                lw.addItem(t("(boş)"))
                lw.item(0).setFlags(Qt.NoItemFlags)

    def _maybe_reload(self, line):
        if any(k in line for k in ("to the whitelist", "from the whitelist", "Banned", "Unbanned", "operator")):
            QTimer.singleShot(500, self.on_show)

    def run(self, action):
        n = self.name.text().strip()
        if not n:
            self.warn("Lütfen bir oyuncu adı girin.")
            return
        if action == "ban" and not self.confirm(t("{name} banlansın mı?", name=n)):
            return
        if self.send(f"{action} {n}"):
            self.name.clear()


# ---------------------------------------------------------------- Bakım
DAYS = [N_("Pzt"), N_("Sal"), N_("Çar"), N_("Per"), N_("Cum"), N_("Cmt"), N_("Paz")]


def fmt_left(td):
    s = int(td.total_seconds())
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    mi, s = divmod(s, 60)
    return t("{d} gün {time}", d=d, time=f"{h:02}:{mi:02}:{s:02}") if d else f"{h:02}:{mi:02}:{s:02}"


class MaintenancePage(Page):
    title = "Bakım & Yedek"
    backup_progress = Signal(int, int)
    backup_done = Signal(str, str)  # yol, hata

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        top = QHBoxLayout()
        top.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(14)

        st = Card("Durum")
        self.state_lbl = label("", "BigValue")
        self.timer_lbl = label("", "Muted", wrap=True)
        st.add(self.state_lbl)
        st.add(self.timer_lbl)
        self.btn_on = button("Bakım Modunu Başlat", "danger", self.enable)
        self.btn_off = button("Bakım Modunu Bitir", "primary", self.disable)
        st.add(row(self.btn_on, self.btn_off))
        st.add(label("Bakımda whitelist yedeklenip boşaltılır ve açılır; OP olmayan oyuncular atılır, MOTD değişir "
                     "ve yedek alınır. Bakım bitince whitelist ve eski ayarlar geri gelir.", "Muted", wrap=True))
        left.addWidget(st)

        plan = Card("Otomatik Bakım", "Seçili günlerde, belirlenen saatte başlar; süre dolunca kendiliğinden biter")
        self.plan_on = QCheckBox(t("Otomatik bakımı aç"))
        self.plan_on.setCursor(Qt.PointingHandCursor)
        plan.add(self.plan_on)
        self.day_btns = []
        days = QHBoxLayout()
        days.setSpacing(4)
        for name in DAYS:
            b = QPushButton(t(name))
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.day_btns.append(b)
            days.addWidget(b)
        days.addStretch(1)
        plan.add(days)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.duration = QSpinBox()
        self.duration.setRange(5, 24 * 60)
        self.duration.setSingleStep(5)
        self.duration.setSuffix(" " + t("dk"))
        form = QFormLayout()
        form.setSpacing(8)
        form.addRow(t("Başlangıç saati"), self.time)
        form.addRow(t("Süre"), self.duration)
        plan.add(form)
        self.plan_backup = QCheckBox(t("Bakım başlarken yedek al"))
        self.plan_backup.setCursor(Qt.PointingHandCursor)
        plan.add(self.plan_backup)
        plan.add(label("Oyunculara 10 dk, 5 dk, 1 dk ve 10 sn önce uyarı gönderilir. "
                       "Plan yalnızca Spypaper açıkken çalışır.", "Muted", wrap=True))
        plan.add(row(None, button("Planı Kaydet", "primary", self.save_plan), stretch_end=False))
        left.addWidget(plan)
        left.addStretch(1)
        top.addLayout(left, 1)

        bk = Card("Dünya Yedekleri", "world, world_nether ve world_the_end tek zip'te")
        self.btn_backup = button("Şimdi Yedek Al", "primary", self.backup)
        bk.header_actions.addWidget(button("Klasörü Aç", "ghost", lambda: open_folder(self.app.backups.folder)))
        bk.header_actions.addWidget(self.btn_backup)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        bk.add(self.progress)
        self.table = table(["Yedek", "Boyut", "Tarih"], stretch_col=0)
        bk.add(self.table, 1)
        top.addWidget(bk, 1)
        self.root.addLayout(top, 1)

        self.backup_progress.connect(self._on_progress)
        self.backup_done.connect(self._on_backup_done)
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._tick)       # yalnızca gösterim; bakımı pencerenin zamanlayıcısı yürütür
        self.tick.start(1000)
        self._load_plan()
        self._tick()

    def on_show(self):
        fill_table(self.table, [(n, human_size(s), f"{d:%d.%m.%Y %H:%M}") for n, s, d in self.app.backups.list()],
                   align_center=(1, 2))
        self._load_plan()
        self._tick()

    def _load_plan(self):
        s = self.app.maintenance.schedule
        self.plan_on.setChecked(s["enabled"])
        for i, b in enumerate(self.day_btns):
            b.setChecked(i in s["days"])
        h, m = (int(x) for x in s["time"].split(":"))
        self.time.setTime(QTime(h, m))
        self.duration.setValue(s["duration"])
        self.plan_backup.setChecked(s["backup"])

    def save_plan(self):
        if self.read_only():
            return
        days = [i for i, b in enumerate(self.day_btns) if b.isChecked()]
        if self.plan_on.isChecked() and not days:
            self.warn("En az bir gün seç.")
            return
        self.app.maintenance.set_schedule({
            "enabled": self.plan_on.isChecked(), "days": days, "time": self.time.time().toString("HH:mm"),
            "duration": self.duration.value(), "backup": self.plan_backup.isChecked()})
        self._tick()
        self.info("Plan kaydedildi.")

    def _tick(self):
        m = self.app.maintenance
        if m.active:
            self.state_lbl.setText(t("Bakım modu aktif"))
            self.state_lbl.setStyleSheet(f"color:{color('danger')}")
            until = m.until()
            self.timer_lbl.setText(t("Otomatik bitiş: {time}", time=f"{until:%d.%m %H:%M}") if until
                                   else t("Bakım elle bitirilene kadar sürer."))
        else:
            self.state_lbl.setText(t("Normal mod"))
            self.state_lbl.setStyleSheet(f"color:{color('accent')}")
            left, nxt = m.remaining(), m.next_start()
            self.timer_lbl.setText(t("Sonraki otomatik bakım: {when} ({left} kaldı)", when=f"{nxt:%d.%m %H:%M}",
                                     left=fmt_left(left)) if nxt else t("Otomatik bakım kapalı."))
        self.btn_on.setEnabled(not m.active)
        self.btn_off.setEnabled(m.active)

    def enable(self):
        if self.read_only():
            return
        if not self.confirm("Bakım modu başlatılsın mı?\nWhitelist boşaltılacak, OP olmayan oyuncular atılacak ve yedek alınacak."):
            return
        path = self.app.maintenance.enable()
        self._tick()
        self.on_show()
        self.info(t("Bakım modu aktif.") + "\n" + (t("Yedek: {file}", file=os.path.basename(path)) if path else t("Yedek alınamadı.")))

    def disable(self):
        if self.read_only():
            return
        self.app.maintenance.disable()
        self._tick()

    def backup(self):
        self.app.server.try_send("save-all flush")
        self.btn_backup.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        def work():
            try:
                p = self.app.backups.create(progress=lambda i, n: self.backup_progress.emit(i, n))
                self.backup_done.emit(p, "")
            except Exception as e:
                self.backup_done.emit("", str(e))
        QTimer.singleShot(1500, lambda: threading.Thread(target=work, daemon=True).start())

    def _on_progress(self, i, n):
        self.progress.setMaximum(n)
        self.progress.setValue(i)

    def _on_backup_done(self, path, err):
        self.btn_backup.setEnabled(True)
        self.progress.setVisible(False)
        if err:
            self.error(t("Yedek alınamadı: {err}", err=t(err)))
        self.on_show()
