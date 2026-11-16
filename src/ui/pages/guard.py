"""Hile Koruması sayfası. Çekirdek: core/guard.py (panel kapalıyken de çalışır; bu sayfa yalnızca ayarlar)."""
import os
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QLineEdit, QListWidget, QScrollArea, QSpinBox, QWidget,
)

from core import N_, guard as G
from core.config import detect_version

from ..i18n import t
from ..widgets import Card, Page, button, label, row

ENGINES = [(1, N_("Hafif: gizli cevherleri taş gösterir")), (2, N_("Güçlü: her yere sahte cevher koyar"))]


class GuardPage(Page):
    title = "Hile Koruması"
    ev = Signal(object)
    job_done = Signal(object, object)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.ev.connect(self._on_event)
        self.job_done.connect(self._job_done)
        app.guard.on_event = self.ev.emit
        self._busy = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        host = QWidget()
        host.setObjectName("Page")
        lay = QGridLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        scroll.setWidget(host)
        self.root.addWidget(scroll, 1)

        # --- ana anahtar
        top = Card("Hile Koruması", "Spypaper sunucunun dışında çalışır: oyuncuların ağ paketlerini göremez, yalnızca "
                   "konsolu ve sunucu dosyalarını görür. Her modül yapabildiği kadarını yapar.")
        self.allow = QCheckBox(t("Bu sunucuda hilelere izin ver (tüm korumaları kapatır)"))
        self.allow.toggled.connect(self.set_allow)
        self.top_hint = label("", "Muted", wrap=True)
        top.add(self.allow)
        top.add(self.top_hint)
        lay.addWidget(top, 0, 0, 1, 2)

        # --- Cevher Gizleme
        x = Card("Cevher Gizleme", "X-Ray paketlerini işe yaramaz hâle getirir (Paper ve Purpur'un yerleşik anti-xray'i).")
        self.x_on = QCheckBox(t("Etkin"))
        self.x_engine = QComboBox()
        for v, text in ENGINES:
            self.x_engine.addItem(t(text), v)
        self.x_state = label("", "Muted", wrap=True)
        x.add(self.x_on)
        x.add(self.x_engine)
        x.add(row(button("Uygula", "primary", self.apply_xray), None))
        x.add(self.x_state)
        x.add(label("Fullbright ve kaynak paketinin kendisi oyuncunun bilgisayarında çalışır; hiçbir sunucu "
                    "bunları göremez.", "Muted", wrap=True))
        x.body.addStretch(1)
        self.m_xray = x
        lay.addWidget(x, 1, 0)

        # --- Yetki Koruması
        o = Card("Yetki Koruması (OP)", "İzinli listede olmayan biri OP olursa yetkisini geri alır ve oyuncuyu atar.")
        self.o_on = QCheckBox(t("Etkin"))
        self.o_on.toggled.connect(self.set_op)
        self.o_list = QListWidget()
        self.o_list.setMaximumHeight(130)
        self.o_name = QLineEdit()
        self.o_name.setPlaceholderText(t("Oyuncu adı"))
        self.o_name.returnPressed.connect(self.add_allowed)
        o.add(self.o_on)
        o.add(label("İzinli OP'lar", "Muted"))
        o.add(self.o_list)
        o.add(row(self.o_name, button("Ekle", "ghost", self.add_allowed),
                  button("Kaldır", "ghost", self.remove_allowed), button("Şu anki OP'ları ekle", "ghost", self.seed_ops),
                  stretch_end=False))
        o.add(label("Panelden (konsol, Oyuncular, telefon) verilen OP kendiliğinden izinli listeye girer. Oyun içinden "
                    "/op ile, eklentiyle ya da komut bloğuyla verilen yetki geri alınır.", "Muted", wrap=True))
        o.body.addStretch(1)
        self.m_op = o
        lay.addWidget(o, 1, 1)

        # --- Savaş Hilesi Denetimi
        c = Card("Savaş Hilesi Denetimi", "Killaura, uzaktan vurma, uçma ve hız hilelerini yakalar.")
        self.c_state = label("", "Muted", wrap=True)
        self.c_install = button("Kur (Modrinth: GrimAC)", "primary", self.install_anticheat)
        self.c_toggle = button("", "ghost", self.toggle_anticheat)
        c.add(self.c_state)
        c.add(row(self.c_install, self.c_toggle, None))
        c.add(label("Vuruş hızını ve açısını ölçmek için oyuncuların ağ paketlerini görmek gerekir; bunu sunucuya "
                    "kurulan açık kaynak bir anti-hile eklentisi (GrimAC, GPL-3.0) yapar. Spypaper yalnızca kurar, açar "
                    "ve kapatır. Yalnızca Paper, Purpur ve Spigot'ta çalışır; ayarları plugins/GrimAC klasöründedir.",
                    "Muted", wrap=True))
        c.body.addStretch(1)
        self.m_combat = c
        lay.addWidget(c, 2, 0)

        # --- Bot Doğrulaması
        b = Card("Bot Doğrulaması (Kaynak Paketi)", "Giren oyuncu sunucunun kaynak paketini gerçekten indirmezse atılır.")
        self.b_on = QCheckBox(t("Etkin"))
        self.b_on.toggled.connect(self.set_captcha)
        self.b_state = label("", "Muted", wrap=True)
        self.b_grace = QSpinBox()
        self.b_grace.setRange(5, 120)
        self.b_grace.setSuffix(" " + t("sn"))
        self.b_grace.valueChanged.connect(lambda v: G.save(self.app.config, captcha_grace=v))
        self.b_bedrock = QCheckBox(t("Bedrock (Geyser) oyuncularını denetleme"))
        self.b_bedrock.toggled.connect(lambda v: G.save(self.app.config, captcha_skip_bedrock=v))
        self.b_list = QListWidget()
        self.b_list.setMaximumHeight(130)
        self.b_name = QLineEdit()
        self.b_name.setPlaceholderText(t("Oyuncu adı"))
        b.add(self.b_on)
        b.add(self.b_state)
        b.add(row(label("Bekleme süresi"), self.b_grace, None))
        b.add(self.b_bedrock)
        b.add(label("Doğrulanan oyuncular (spypaper_guard/verified.json)", "Muted"))
        b.add(self.b_list)
        b.add(row(self.b_name, button("Elle doğrula", "ghost", self.manual_verify),
                  button("Doğrulamayı kaldır", "ghost", self.remove_verified), stretch_end=False))
        b.add(label("Yalnızca kaynak paketini Spypaper paylaşırken çalışır (İçerik Editörü → Paylaşım). Panel, giren "
                    "oyuncunun IP'sinden paketin tamamının indirilip indirilmediğine bakar; bir indirme yalnızca bir "
                    "girişi doğrular. Doğrulanan oyuncu bir daha denetlenmez. Proxy (Velocity/BungeeCord) arkasında "
                    "çalışmaz.", "Muted", wrap=True))
        b.body.addStretch(1)
        self.m_captcha = b
        lay.addWidget(b, 2, 1)

        # --- olay günlüğü
        e = Card("Olaylar", "spypaper_guard/guard.log")
        self.e_list = QListWidget()
        self.e_list.setMinimumHeight(140)
        e.add(self.e_list)
        lay.addWidget(e, 3, 0, 1, 2)
        lay.setRowStretch(4, 1)

    # ---------------------------------------------------------------- durum
    @property
    def g(self):
        return G.settings(self.app.config)

    def _software(self):
        mc, soft = detect_version(self.app.config.server_path)
        return mc, soft

    def on_show(self):
        g = self.g
        for w, v in ((self.allow, g["allow_cheats"]), (self.o_on, g["op"]), (self.b_on, g["captcha"]),
                     (self.b_bedrock, g["captcha_skip_bedrock"])):
            w.blockSignals(True)
            w.setChecked(bool(v))
            w.blockSignals(False)
        self.b_grace.blockSignals(True)
        self.b_grace.setValue(int(g["captcha_grace"]))
        self.b_grace.blockSignals(False)
        self.x_on.setChecked(bool(g["xray"]))
        i = self.x_engine.findData(int(g["xray_engine"]))
        self.x_engine.setCurrentIndex(max(0, i))
        self.refresh()

    def refresh(self):
        g, sp = self.g, self.app.config.server_path
        off = g["allow_cheats"]
        for m in (self.m_xray, self.m_op, self.m_combat, self.m_captcha):
            m.setEnabled(not off)
        self.top_hint.setText(t("Tüm korumalar kapalı. Anti-xray ve anti-hile eklentisi de kapatıldı.") if off else
                              t("Değişen ayar dosyaları sunucu yeniden başlatılınca geçerli olur."))
        # cevher gizleme
        st = G.xray_state(sp)
        if st is None:
            self.x_state.setText(t("Bu sunucuda yok: yalnızca Paper ve Purpur. Sunucu hiç başlatılmadıysa bir kez başlatıp kapat."))
        else:
            self.x_state.setText(t("Şu an ayar dosyasında: {state}", state=t("açık") if st[0] else t("kapalı")))
        # yetki
        self.o_list.clear()
        self.o_list.addItems(g["op_allowed"])
        # savaş
        ac = G.anticheat_file(self.app.plugins.folder) if not self.app.plugins.modded else None
        if self.app.plugins.modded:
            self.c_state.setText(t("Modlu sunucularda kullanılamaz (yalnızca Paper, Purpur ve Spigot)."))
            self.c_install.setEnabled(False)
            self.c_toggle.setVisible(False)
        elif not ac:
            self.c_state.setText(t("Kurulu değil."))
            self.c_install.setEnabled(not self._busy)
            self.c_toggle.setVisible(False)
        else:
            self.c_state.setText(t("Kurulu: {file} · {state}", file=ac[0], state=t("açık") if ac[1] else t("kapalı")))
            self.c_install.setEnabled(False)
            self.c_toggle.setVisible(True)
            self.c_toggle.setText(t("Kapat") if ac[1] else t("Aç"))
        # bot doğrulaması
        share = self.app.config.get("content_share") or {}
        rp = os.path.join(sp, "spypaper_resourcepack.zip")
        ready = bool(share.get("enabled")) and os.path.exists(rp)
        self.b_on.setEnabled(ready or g["captcha"])
        self.b_state.setText(t("Hazır: paket Spypaper tarafından paylaşılıyor.") if ready else
                             t("Önce İçerik Editörü'nde paketleri oluştur ve Paylaşım'ı aç."))
        self.b_list.clear()
        self.b_list.addItems(sorted(v.get("name", k) for k, v in self.app.guard.verified().items()))
        # olaylar
        self.e_list.clear()
        for ev in self._read_log():
            self.e_list.addItem(ev)
        self.e_list.scrollToBottom()

    def _read_log(self):
        p = os.path.join(G.guard_dir(self.app.config.server_path), "guard.log")
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().splitlines()[-200:]
        except OSError:
            return []

    def _on_event(self, ev):
        text = t(ev["text"], **ev.get("kw", {}))
        self.e_list.addItem(f"{ev['time']} [{ev['kind']}] {text}")
        self.e_list.scrollToBottom()
        if ev["kind"] == "captcha":
            self.b_list.clear()
            self.b_list.addItems(sorted(v.get("name", k) for k, v in self.app.guard.verified().items()))

    def _stopped(self):
        if self.app.server.is_running:
            self.warn("Bu değişiklik için önce sunucuyu durdur (Windows çalışan eklenti dosyasını kilitler).",
                      "İşlem Engellendi")
            return False
        return True

    # ---------------------------------------------------------------- ana anahtar
    def set_allow(self, on):
        if self.read_only():
            self.on_show()
            return
        g, sp, folder = self.g, self.app.config.server_path, self.app.plugins.folder
        ac = G.anticheat_file(folder) if not self.app.plugins.modded else None
        if ac and g["combat"] and not self._stopped():
            self.on_show()
            return
        try:
            if g["xray"] and G.xray_state(sp) is not None:
                G.set_xray(sp, not on, g["xray_engine"])
            if ac and g["combat"]:
                G.set_anticheat(folder, not on)
        except (G.GuardError, OSError) as e:
            self.error(self._err(e))
        G.save(self.app.config, allow_cheats=on)
        self.refresh()

    # ---------------------------------------------------------------- modüller
    def apply_xray(self):
        if self.read_only():
            return
        on, engine = self.x_on.isChecked(), self.x_engine.currentData()
        try:
            G.set_xray(self.app.config.server_path, on, engine)
        except (G.GuardError, OSError) as e:
            self.error(self._err(e))
            return
        G.save(self.app.config, xray=on, xray_engine=engine)
        self.refresh()
        self.info("Kaydedildi. Değişiklik sunucu yeniden başlatılınca geçerli olur.")

    def set_op(self, on):
        if on:
            names = self.app.guard.seed_allowed()
            G.save(self.app.config, op=True)
            if names:
                self.info(t("Şu anki OP'lar izinli listeye eklendi: {names}", names=", ".join(names)))
        else:
            G.save(self.app.config, op=False)
        self.refresh()

    def add_allowed(self):
        name = self.o_name.text().strip()
        if not G.NAME_RE.match(name):
            self.warn(t("Geçersiz oyuncu adı: {name}", name=name))
            return
        cur = [n for n in self.g["op_allowed"] if n.lower() != name.lower()] + [name]
        G.save(self.app.config, op_allowed=cur)
        self.o_name.clear()
        self.refresh()

    def remove_allowed(self):
        it = self.o_list.currentItem()
        if not it:
            return
        G.save(self.app.config, op_allowed=[n for n in self.g["op_allowed"] if n != it.text()])
        self.refresh()

    def seed_ops(self):
        self.app.guard.seed_allowed()
        self.refresh()

    def install_anticheat(self):
        if self._busy or self.read_only() or not self._stopped():
            return
        from core import modrinth as M
        mc, soft = self._software()
        _, loaders = M.context(soft, mc, self.app.plugins.modded)
        folder = self.app.plugins.folder
        self._busy = True
        self.c_install.setEnabled(False)
        self.c_state.setText(t("Modrinth'ten indiriliyor…"))

        def work():
            try:
                self.job_done.emit(("install", G.install_anticheat(folder, loaders, mc)), None)
            except Exception as e:
                self.job_done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _job_done(self, res, err):
        self._busy = False
        if err is not None:
            self.error(self._err(err))
        else:
            G.save(self.app.config, combat=True)
            self.info(t("Kuruldu: {files}", files=", ".join(res[1])) + "\n" +
                      t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))
        self.refresh()

    def toggle_anticheat(self):
        if self.read_only() or not self._stopped():
            return
        ac = G.anticheat_file(self.app.plugins.folder)
        if not ac:
            return
        try:
            G.set_anticheat(self.app.plugins.folder, not ac[1])
        except OSError as e:
            self.error(str(e))
            return
        G.save(self.app.config, combat=not ac[1])
        self.refresh()

    def set_captcha(self, on):
        sp = self.app.config.server_path
        rp = os.path.join(sp, "spypaper_resourcepack.zip")
        G.save(self.app.config, captcha=on)
        if on:
            try:
                G.stamp_pack(rp)                    # herkes paketi bir kez yeniden indirsin
            except Exception as e:
                G.save(self.app.config, captcha=False)
                self.error(self._err(e))
                self.on_show()
                return
        self._reshare()
        self.refresh()
        self.info("Kaydedildi. Değişiklik sunucu yeniden başlatılınca geçerli olur." if not on else
                  t("Bot doğrulaması açıldı. Kaynak paketi artık zorunlu ve paket yenilendi: her oyuncu bir kez "
                    "yeniden indirecek.") + "\n" + t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))

    def _reshare(self):
        """Paylaşımı yeni özet ve zorunluluk ayarıyla yeniden yayınlar (server.properties)."""
        from core import content as C, modrinth as M
        from core.packhost import HOST
        cfg = self.app.config.get("content_share") or {}
        rp = os.path.join(self.app.config.server_path, "spypaper_resourcepack.zip")
        if not cfg.get("enabled") or not os.path.exists(rp) or not cfg.get("address"):
            return
        try:
            HOST.start(int(cfg.get("port") or 8766))
        except OSError:
            return
        sha = C.sha1_file(rp)
        HOST.register(self.app.id, rp, sha)
        M.set_resource_pack(self.app.properties, HOST.url(cfg["address"], self.app.id, sha), sha,
                            bool(cfg.get("required")) or G.active(self.app.config, "captcha"))

    def manual_verify(self):
        name = self.b_name.text().strip()
        if not G.NAME_RE.match(name):
            self.warn(t("Geçersiz oyuncu adı: {name}", name=name))
            return
        self.app.guard.mark_verified(name, how="manual")
        self.app.guard.log("captcha", N_("Elle doğrulandı: {name}"), name=name)
        self.b_name.clear()
        self.refresh()

    def remove_verified(self):
        it = self.b_list.currentItem()
        if it:
            self.app.guard.unverify(it.text())
            self.refresh()

    @staticmethod
    def _err(e):
        tpl = getattr(e, "template", None)
        return t(tpl, **e.kw) if tpl else str(e)


N_("Hile Koruması")
N_("sn")
