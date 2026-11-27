"""Botlar: AFK farmlar için panelden sahte oyuncu (core.bots)."""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QHeaderView, QLineEdit,
                               QSpinBox, QTableWidget, QTableWidgetItem)

from core import N_, bots as B
from core.config import detect_version, is_modded
from ..i18n import t
from ..widgets import Card, Page, button, label, row

DIMS = [("minecraft:overworld", N_("Overworld")), ("minecraft:the_nether", N_("Nether")),
        ("minecraft:the_end", N_("End"))]
ACTION_NAMES = {"none": N_("Sadece dursun (chunk'ları yüklü tutar)"), "attack": N_("Vursun (mob farmı)"),
                "use": N_("Sağ tıklasın (balık, ekin, sandık…)"), "sneak": N_("Eğilsin")}


class BotsPage(Page):
    title = "Botlar"
    install_done = Signal(object, object)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        intro = Card("Botlar", "Oyuncuların yerine AFK farmlarda duran sahte oyuncular; gece nöbetine gerek kalmaz")
        intro.add(label("Bot gerçek bir oyuncu gibi sunucuya girer, verdiğin yerde durur ve çevresindeki chunk'ları "
                        "yüklü tutar; istersen sürekli ya da aralıklı vurur veya sağ tıklar. Hile koruması ve bakım "
                        "modu botları atmaz, oyuncu sayılarında ve raporlarda ayrı tutulurlar.", "Muted", wrap=True))
        self.prov_lbl = label("", wrap=True)
        self.btn_install = button("Kur", "primary", lambda: self.install())
        intro.add(self.prov_lbl)
        intro.add(row(self.btn_install))
        self.root.addWidget(intro)

        form = Card("Bot Ekle / Düzenle")
        self.name = QLineEdit()
        self.name.setPlaceholderText(t("Bot adı, ör. FarmBot"))
        self.name.setMaxLength(16)
        self.name.setFixedWidth(200)
        self.auto = QCheckBox(t("Sunucu açılınca otomatik gelsin"))
        self.auto.setChecked(True)
        form.add(row(label("Ad"), self.name, self.auto))

        self.from_player = QComboBox()
        self.from_player.setMinimumWidth(180)
        self.dim = QComboBox()
        for d, n in DIMS:
            self.dim.addItem(t(n), d)
        self.x, self.y, self.z = (QDoubleSpinBox() for _ in range(3))
        for sp in (self.x, self.z):
            sp.setRange(-30_000_000, 30_000_000)
        self.y.setRange(-2048, 4096)
        self.yaw, self.pitch = QDoubleSpinBox(), QDoubleSpinBox()
        self.yaw.setRange(-180, 180)
        self.pitch.setRange(-90, 90)
        for sp in (self.x, self.y, self.z, self.yaw, self.pitch):
            sp.setDecimals(1)
            sp.setFixedWidth(110)
        form.add(row(label("Konum"), self.from_player, button("Bu oyuncunun yerini al", "ghost", self.take_pos), None))
        form.add(row(self.dim, label("X"), self.x, label("Y"), self.y, label("Z"), self.z,
                     label("Bakış (yaw / pitch)"), self.yaw, self.pitch))
        self.action = QComboBox()
        for k in B.ACTIONS:
            self.action.addItem(t(ACTION_NAMES[k]), k)
        self.interval = QSpinBox()
        self.interval.setRange(0, 72000)
        self.interval.setSuffix(" " + t("tick"))
        self.interval.setSpecialValueText(t("sürekli"))
        self.interval.setToolTip(t("0: sürekli. 20 tick = 1 saniye. Mob farmında kılıç için 12–20 tick iyi çalışır."))
        form.add(row(label("İş"), self.action, label("Aralık"), self.interval))
        form.add(label("İpucu: kendin farmın vuracağı noktada dur, bakışını hedefe çevir, sonra 'Bu oyuncunun yerini "
                       "al'a bas. Konum, oyuncu verisi kaydedilince güncellenir (Spypaper önce kaydettirir).",
                       "Muted", wrap=True))
        form.add(row(None, button("Listeye Kaydet", "ghost", self.save),
                     button("Kaydet ve Getir", "primary", self.save_spawn), stretch_end=False))
        self.root.addWidget(form)

        self.root.addWidget(self._ai_card())

        lst = Card("Bot Listesi", "Seçili botla işlem yap")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([t("Ad"), t("Konum"), t("İş"), t("Otomatik"), t("Durum")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self._pick)
        lst.add(self.table, 1)
        lst.add(row(button("Getir", "primary", self.spawn_sel), button("İşi Uygula", "ghost", self.act_sel),
                    button("Sunucudan Çıkar", "warn", self.remove_sel), None,
                    button("Listeden Sil", "danger", self.delete_sel), stretch_end=False))
        self.root.addWidget(lst, 1)
        self.install_done.connect(self._installed)

    # ------------------------------------------------------------ oyun içi yapay zeka
    def _ai_card(self):
        from core import ingame_ai as IA
        s = IA.settings_of(self.app.config)
        c = Card("Oyun İçi Yapay Zeka", "Oyuncular sohbetten Esplora'ya soru sorar, botlarla konuşur")
        c.add(label("Esplora'nın yapay zeka ayarlarını (☰ → Yapay Zeka Ayarları) kullanır. Her soru bir API çağrısıdır "
                    "ve ücretli olabilir; aşağıdaki sınırlar maliyeti tutar. Yapay zeka sunucuya komut gönderemez, "
                    "botlar yalnızca gel, dur, vur, sağ tıkla ve eğil işlerini yapabilir.", "Muted", wrap=True))
        self.ai_on = QCheckBox(t("Asistan: oyuncular sohbete şunu yazarak soru sorar:"))
        self.ai_on.setChecked(s["enabled"])
        self.ai_trig = QLineEdit(s["trigger"])
        self.ai_trig.setFixedWidth(140)
        c.add(row(self.ai_on, self.ai_trig, label("<soru>"), None))
        self.ai_bots = QCheckBox(t("Konuşan botlar: '@BotAdı mesaj' ya da 'BotAdı, mesaj' yazılınca bot cevap verir"))
        self.ai_bots.setChecked(s["bots"])
        self.ai_acts = QCheckBox(t("Botlar sohbetle iş değiştirebilsin (gel, dur, vur, sağ tıkla, eğil)"))
        self.ai_acts.setChecked(s["bot_actions"])
        c.add(self.ai_bots)
        c.add(self.ai_acts)
        self.ai_cool, self.ai_daily, self.ai_min = QSpinBox(), QSpinBox(), QSpinBox()
        self.ai_cool.setRange(0, 3600)
        self.ai_cool.setValue(int(s["cooldown"]))
        self.ai_cool.setSuffix(" " + t("sn"))
        self.ai_daily.setRange(1, 1000)
        self.ai_daily.setValue(int(s["daily"]))
        self.ai_min.setRange(1, 120)
        self.ai_min.setValue(int(s["per_minute"]))
        c.add(row(label("Oyuncu başına bekleme"), self.ai_cool, label("Oyuncu başına günlük"), self.ai_daily,
                  label("Sunucu geneli dakikada en çok"), self.ai_min, None))
        self.ai_warn = label("", "Muted", wrap=True)
        c.add(self.ai_warn)
        for w in (self.ai_on, self.ai_bots, self.ai_acts):
            w.toggled.connect(self._ai_save)
        for w in (self.ai_cool, self.ai_daily, self.ai_min):
            w.valueChanged.connect(self._ai_save)
        self.ai_trig.editingFinished.connect(self._ai_save)
        return c

    def _ai_save(self, *_):
        from core import ingame_ai as IA
        trig = self.ai_trig.text().strip().split()[0] if self.ai_trig.text().strip() else "@esplora"
        IA.save(self.app.config, enabled=self.ai_on.isChecked(), bots=self.ai_bots.isChecked(),
                bot_actions=self.ai_acts.isChecked(), trigger=trig[:24], cooldown=self.ai_cool.value(),
                daily=self.ai_daily.value(), per_minute=self.ai_min.value())
        self._ai_check()

    def _ai_check(self):
        from core import ai
        st = self.app.ingame_ai.settings
        need = (self.ai_on.isChecked() or self.ai_bots.isChecked()) and st is not None
        cfg = ai.get_cfg(st) if st is not None else None
        missing = need and cfg["provider"] in ("anthropic", "gemini") and not ai.api_key(cfg)
        self.ai_warn.setText(t("API anahtarı ayarlanmamış. ☰ menüsünden Yapay Zeka Ayarları'nı aç.") if missing else "")

    # ------------------------------------------------------------ yardımcılar
    def _soft(self):
        return detect_version(self.app.config.server_path)[:2]

    def _prov(self):
        return B.provider_for(self._soft()[1])

    def _level(self):
        from core.danger import level_name
        return level_name(self.app.properties)

    def on_show(self):
        prov = self._prov()
        if not prov:
            self.prov_lbl.setText(t("Bu sunucu türünde bot desteklenmiyor. Paper, Purpur ya da Fabric gerekir."))
            self.btn_install.hide()
        else:
            info = B.PROVIDERS[prov]
            ok = B.installed(self.app.config.server_path, prov)
            self.prov_lbl.setText(t("Bot altyapısı: {name} ({state})", name=info["name"],
                                    state=t("kurulu") if ok else t("kurulu değil")))
            self.btn_install.setVisible(not ok)
        online = self.app.real_players() if self.app.server.is_running else []
        names = sorted({p.name for p in self.app.players.list_players()} | set(online), key=str.lower)
        cur = self.from_player.currentText()
        self.from_player.clear()
        self.from_player.addItems(names)
        if cur in names:
            self.from_player.setCurrentText(cur)
        self._fill()
        self._ai_check()

    def _fill(self):
        online = {p.lower() for p in self.app.online_players()} if self.app.server.is_running else set()
        items = self.app.bots.entries()
        self.table.setRowCount(len(items))
        for r, b in enumerate(items):
            dim = dict(DIMS).get(b.get("dim"), b.get("dim", ""))
            pos = f"{t(dim)} · {b['x']:.0f} {b['y']:.0f} {b['z']:.0f}"
            act = t(ACTION_NAMES.get(b.get("action", "none"), "")).split(" (")[0]
            if b.get("action") in ("attack", "use"):
                act += " · " + (t("her {n} tick", n=b["interval"]) if b.get("interval") else t("sürekli"))
            vals = [b["name"], pos, act, "✓" if b.get("auto") else "",
                    t("Sunucuda") if b["name"].lower() in online else t("Yok")]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 4:
                    it.setForeground(Qt.green if v == t("Sunucuda") else Qt.gray)
                self.table.setItem(r, c, it)

    def _selected(self):
        r = self.table.currentRow()
        items = self.app.bots.entries()
        return items[r] if 0 <= r < len(items) else None

    def _pick(self):
        b = self._selected()
        if not b:
            return
        self.name.setText(b["name"])
        self.auto.setChecked(bool(b.get("auto")))
        self.dim.setCurrentIndex(max(0, self.dim.findData(b.get("dim", "minecraft:overworld"))))
        for sp, k in ((self.x, "x"), (self.y, "y"), (self.z, "z"), (self.yaw, "yaw"), (self.pitch, "pitch")):
            sp.setValue(float(b.get(k, 0)))
        self.action.setCurrentIndex(max(0, self.action.findData(b.get("action", "none"))))
        self.interval.setValue(int(b.get("interval", 0)))

    def _form(self):
        return {"name": self.name.text().strip(), "dim": self.dim.currentData(), "x": self.x.value(),
                "y": self.y.value(), "z": self.z.value(), "yaw": self.yaw.value(), "pitch": self.pitch.value(),
                "action": self.action.currentData(), "interval": self.interval.value(), "auto": self.auto.isChecked()}

    def _err(self, e):
        self.error(t(e.template, **e.kw) if hasattr(e, "template") else str(e))

    # ------------------------------------------------------------ işlemler
    def install(self, any_version=False):
        prov = self._prov()
        mc, soft = self._soft()
        sp = self.app.config.server_path
        self.btn_install.setEnabled(False)
        self.prov_lbl.setText(t("{name} indiriliyor…", name=B.PROVIDERS[prov]["name"]))

        def run():
            try:
                self.install_done.emit(B.install(sp, prov, soft, mc, is_modded(sp), any_version), None)
            except Exception as e:
                self.install_done.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    def _installed(self, name, err):
        self.btn_install.setEnabled(True)
        if err is not None and getattr(err, "no_version", False):
            from ..msgbox import ask
            if ask(self, t(err.template, **err.kw) + "\n\n" + t(
                    "Bu Minecraft sürümünü resmi olarak destekleyen bir sürüm henüz yok. En yeni sürümü yine de denemek "
                    "ister misin? Çalışmayabilir; çalışmazsa Eklentiler sayfasından kaldırabilirsin."), t("Onay")):
                self.install(any_version=True)
                return
            self.on_show()
            return
        if err:
            self._err(err)
        else:
            self.info(t("Kuruldu: {file}. Sunucuyu yeniden başlatınca botlar kullanılabilir.", file=name))
        self.on_show()

    def take_pos(self):
        name = self.from_player.currentText()
        if not name:
            return
        if self.app.server.is_running:
            try:
                self.app.server.send("save-all")
                import time
                time.sleep(1.5)
            except Exception:
                pass
        p = next((x for x in self.app.players.list_players() if x.name.lower() == name.lower()), None)
        d = self.app.players.details(p) if p else None
        if not d or not d.pos:
            self.error(t("{name} oyuncusunun konumu okunamadı.", name=name))
            return
        dim, x, y, z = d.pos
        self.dim.setCurrentIndex(max(0, self.dim.findData(dim)))
        self.x.setValue(x)
        self.y.setValue(y)
        self.z.setValue(z)
        self.yaw.setValue(d.rot[0])
        self.pitch.setValue(d.rot[1])

    def save(self):
        try:
            self.app.bots.upsert(self._form())
        except B.BotError as e:
            self._err(e)
            return False
        self._fill()
        return True

    def save_spawn(self):
        if self.save():
            self._spawn(self.app.bots.get(self.name.text().strip()))

    def _spawn(self, b):
        if not b:
            return
        if not self.app.server.is_running:
            self.info(t("Bot listeye kaydedildi; sunucu açılınca gelir."))
            return
        mc, soft = self._soft()
        try:
            self.app.bots.spawn(b, soft, self._level())
        except Exception as e:
            self._err(e)
            return
        self.info(t("{name} sunucuya getirildi.", name=b["name"]))
        self._fill_later()

    def spawn_sel(self):
        self._spawn(self._selected())

    def act_sel(self):
        b = self._selected()
        if b and self.app.server.is_running:
            try:
                self.app.bots.act(b, self._soft()[1])
            except Exception as e:
                self._err(e)

    def remove_sel(self):
        b = self._selected()
        if b and self.app.server.is_running:
            try:
                self.app.bots.remove(b["name"], self._soft()[1])
            except Exception as e:
                self._err(e)
            self._fill_later()

    def _fill_later(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2500, self._fill)   # giriş/çıkış satırı log'a düşünce durum yenilenir

    def delete_sel(self):
        b = self._selected()
        if not b:
            return
        if self.app.server.is_running:
            try:
                self.app.bots.remove(b["name"], self._soft()[1])
            except Exception:
                pass
        self.app.bots.delete(b["name"])
        self._fill()
