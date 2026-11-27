"""Tehlikeli Bölge: PIN ile açılan, geri alınamayan işlemler.

Sunucuda PIN varsa o sorulur; yoksa sunucunun adı yazılarak girilir (PIN belirlemek zorunlu değil; paneli açarken
sorulmaz). Kilit, sayfadan çıkınca ya da 5 dakika sonra yeniden kapanır. Her işlem için sunucu kapalı
olmalı ve sunucunun adı elle yazılarak onaylanmalı. Telefondan (Remote) bu bölgeye erişilemez.
"""
import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QProgressBar, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout,
    QWidget,
)

from core import N_, danger
from core.safemode import verify_pin
from .. import icons
from ..i18n import t
from ..msgbox import get_text
from ..theme import TOKENS, rgba
from ..widgets import Card, Page, button, err_text, label, row

UNLOCK_MINUTES = 5


def danger_card(title, subtitle):
    c = Card(title, subtitle)
    c.setStyleSheet(f"#Card {{ border: 1px solid {rgba(TOKENS['danger'], 0.55)}; }}")
    return c


class DangerPage(Page):
    title = "Tehlikeli Bölge"
    finished = Signal(object, object, str)       # sonuç, hata, iş

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.stack = QStackedWidget()
        from .. import motion
        motion.auto_fade(self.stack)
        self.root.addWidget(self.stack, 1)

        # --- kilitli ---
        lock = QWidget()
        lv = QVBoxLayout(lock)
        lv.setAlignment(Qt.AlignCenter)
        lv.setSpacing(10)
        ic = label("", None)
        ic.setPixmap(icons.icon("triangle-alert", TOKENS["danger"], 56).pixmap(56, 56))
        ic.setAlignment(Qt.AlignCenter)
        lv.addWidget(ic)
        h = label("Tehlikeli Bölge", "PageTitle")
        h.setAlignment(Qt.AlignCenter)
        lv.addWidget(h)
        self.lock_text = label("", "Muted", wrap=True)
        self.lock_text.setAlignment(Qt.AlignCenter)
        self.lock_text.setMaximumWidth(520)
        lv.addWidget(self.lock_text, 0, Qt.AlignCenter)
        self.btn_unlock = button("Kilidi Aç", "danger", self.unlock)
        self.btn_unlock.setMinimumWidth(200)
        lv.addWidget(self.btn_unlock, 0, Qt.AlignCenter)
        self.stack.addWidget(lock)

        # --- açık ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(14)
        scroll.setWidget(inner)
        self.stack.addWidget(scroll)

        top = Card()
        self.warn_lbl = label("Buradaki işlemler geri alınamaz. Her işlemden önce sunucunun adını yazarak onaylaman istenir.",
                              None, wrap=True)
        self.warn_lbl.setStyleSheet(f"color:{TOKENS['danger']}; font-weight:600;")
        bar = QHBoxLayout()
        bar.addWidget(self.warn_lbl, 1)
        bar.addWidget(button("Kilitle", "ghost", self.lock), 0, Qt.AlignTop)
        top.add(bar)
        self.run_lbl = label("", "Muted", wrap=True)
        top.add(self.run_lbl)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        top.add(self.progress)
        col.addWidget(top)

        # dünyayı sıfırla
        w = danger_card("Dünyayı Sıfırla", "Seçilen boyutlar silinir; sunucu bir sonraki açılışta yenilerini oluşturur")
        self.dim = {}
        dims = []
        for key, text in (("overworld", N_("Overworld")), ("nether", N_("Nether")), ("end", N_("End"))):
            cb = QCheckBox(t(text))
            cb.setCursor(Qt.PointingHandCursor)
            self.dim[key] = cb
            dims.append(cb)
        self.dim["overworld"].setChecked(True)
        from core.bedrock import is_bedrock
        be = self._be = is_bedrock(app.config.server_path)
        if not be:
            w.add(row(*dims))
        w.add(label("Bedrock'ta Overworld, Nether, End ve oyuncu verileri tek dünya klasöründedir; hepsi birlikte silinir."
                    if be else "Vanilla, Fabric ve Forge'da Nether ve End dünya klasörünün içindedir; Overworld silinince "
                    "onlar ve oyuncuların envanterleri de gider.", "Muted", wrap=True))
        self.seed_mode = QComboBox()
        for v, text in (("random", N_("Rastgele seed")), ("keep", N_("Aynı seed")), ("custom", N_("Belirli seed"))):
            self.seed_mode.addItem(t(text), v)
        self.seed = QLineEdit()
        self.seed.setPlaceholderText(t("Seed"))
        self.seed.setEnabled(False)
        self.seed_mode.currentIndexChanged.connect(lambda _: self.seed.setEnabled(self.seed_mode.currentData() == "custom"))
        w.add(row(self.seed_mode, self.seed))
        self.reset_backup = QCheckBox(t("Silmeden önce yedek al"))
        self.reset_backup.setChecked(True)
        self.reset_backup.setCursor(Qt.PointingHandCursor)
        w.add(self.reset_backup)
        self.btn_reset = button("Dünyayı Sıfırla", "danger", self.reset_world)
        w.add(row(None, self.btn_reset, stretch_end=False))
        col.addWidget(w)

        # taslak harita
        tp = danger_card("Dünyayı Taslakla Değiştir", "Hazır bir harita (Skyblock, PvP arenası…) şu anki dünyanın yerine konur")
        self.btn_template = button("Harita Seç", "danger", self.replace_template)
        tp.add(row(None, self.btn_template, stretch_end=False))
        col.addWidget(tp)
        tp.setVisible(not be)                         # taslak haritalar Java dünyasıdır

        # yedekten geri yükle
        r = danger_card("Yedekten Geri Yükle", "Tüm dünyayı ya da yalnızca seçtiğin parçaları yedekten geri al")
        self.backup_box = QComboBox()
        self.backup_box.setMinimumWidth(320)
        self.backup_box.currentIndexChanged.connect(self._fill_backup_players)
        r.add(row(self.backup_box))
        self.restore_mode = QComboBox()
        for k, n in (("all", N_("Tüm dünya")), ("parts", N_("Seçilen parçalar")), ("area", N_("Yalnızca bir bölge"))):
            if be and k != "all":                     # Bedrock dünyası tek veritabanı: parça parça geri yüklenemez
                continue
            self.restore_mode.addItem(t(n), k)
        self.restore_mode.currentIndexChanged.connect(self._restore_mode_changed)
        r.add(row(label("Ne geri yüklensin?", "Muted"), self.restore_mode))
        self.parts_box = QWidget()
        pl = QHBoxLayout(self.parts_box)
        pl.setContentsMargins(0, 0, 0, 0)
        self.part_cb = {}
        for k, n in (("overworld", "Overworld"), ("nether", "Nether"), ("end", "End"), ("players", N_("Oyuncu verisi"))):
            cb = QCheckBox(t(n))
            cb.setCursor(Qt.PointingHandCursor)
            cb.toggled.connect(self._restore_mode_changed)
            self.part_cb[k] = cb
            pl.addWidget(cb)
        self.player_pick = QComboBox()
        self.player_pick.setMinimumWidth(180)
        pl.addWidget(self.player_pick)
        pl.addStretch(1)
        r.add(self.parts_box)
        self.area_box = QWidget()
        al = QHBoxLayout(self.area_box)
        al.setContentsMargins(0, 0, 0, 0)
        self.area_dim = QComboBox()
        for k, n in (("overworld", "Overworld"), ("nether", "Nether"), ("end", "End")):
            self.area_dim.addItem(n, k)
        self.area_x, self.area_z, self.area_r = QSpinBox(), QSpinBox(), QSpinBox()
        for sb in (self.area_x, self.area_z):
            sb.setRange(-30000000, 30000000)
        self.area_r.setRange(16, 20000)
        self.area_r.setValue(200)
        self.area_r.setSingleStep(50)
        for w in (self.area_dim, label("X"), self.area_x, label("Z"), self.area_z, label("Yarıçap"), self.area_r):
            al.addWidget(w)
        al.addStretch(1)
        r.add(self.area_box)
        self.restore_hint = label("", "Muted", wrap=True)
        r.add(self.restore_hint)
        self.restore_safety = QCheckBox(t("Önce şu anki dünyanın yedeğini al"))
        self.restore_safety.setChecked(True)
        self.restore_safety.setCursor(Qt.PointingHandCursor)
        r.add(self.restore_safety)
        self.btn_restore = button("Geri Yükle", "danger", self.restore)
        r.add(row(None, self.btn_restore, stretch_end=False))
        col.addWidget(r)

        # oyuncu verileri
        p = danger_card("Oyuncu Verilerini Sıfırla", "Envanterler, konumlar, istatistikler ve ilerlemeler silinir; dünya kalır")
        self.btn_players = button("Oyuncu Verilerini Sil", "danger", self.reset_players)
        p.add(row(None, self.btn_players, stretch_end=False))
        col.addWidget(p)
        p.setVisible(not be)

        # dünya temizliği
        tr = danger_card("Dünya Temizliği", "Oyuncuların neredeyse hiç kalmadığı chunk'lar silinir; dünya küçülür, "
                                            "o bölgeler gidildiğinde yeniden oluşur")
        self.trim_min, self.trim_keep = QSpinBox(), QSpinBox()
        self.trim_min.setRange(1, 600)
        self.trim_min.setValue(5)
        self.trim_min.setSuffix(" " + t("dk"))
        self.trim_keep.setRange(0, 100000)
        self.trim_keep.setSingleStep(250)
        self.trim_keep.setValue(500)
        tr.add(row(label("Oyuncuların toplam kaldığı süre bundan az olan chunk'lar:", "Muted"), self.trim_min))
        tr.add(row(label("Doğma noktası çevresinde korunacak yarıçap (blok):", "Muted"), self.trim_keep))
        self.trim_info = label("", "Muted", wrap=True)
        tr.add(self.trim_info)
        self.trim_safety = QCheckBox(t("Önce dünya yedeği al"))
        self.trim_safety.setChecked(True)
        tr.add(self.trim_safety)
        self.btn_trim_plan = button("Önizle", "ghost", self.trim_preview)
        self.btn_trim = button("Temizle", "danger", self.trim_apply)
        tr.add(row(None, self.btn_trim_plan, self.btn_trim, stretch_end=False))
        col.addWidget(tr)
        tr.setVisible(not be)                         # bölge dosyası (.mca) Java'ya özgü
        self._trim_plan = None

        # sunucuyu sil
        d = danger_card("Sunucuyu Sil", "Sunucu klasörü Geri Dönüşüm Kutusu'na taşınır ve sunucu listeden kaldırılır")
        self.btn_delete = button("Sunucuyu Sil", "danger", self.delete_server)
        d.add(row(None, self.btn_delete, stretch_end=False))
        col.addWidget(d)
        col.addStretch(1)

        self.relock = QTimer(self)
        self.relock.setSingleShot(True)
        self.relock.setInterval(UNLOCK_MINUTES * 60 * 1000)
        self.relock.timeout.connect(self.lock)
        self.finished.connect(self._done)
        bridge.state.connect(lambda s: self._sync())
        self.busy = False
        self.lock()

    # ------------------------------------------------------------ kilit
    def _pin(self):
        c = self.app.config
        return c.get("pin_hash") or c.get("danger_pin_hash") or ""

    def lock(self):
        self.stack.setCurrentIndex(0)
        self.relock.stop()
        if self._pin():
            self.lock_text.setText(t("Dünyayı sıfırlama, yedekten geri yükleme ve sunucuyu silme gibi geri alınamayan "
                                     "işlemler burada. Girmek için PIN gerekli."))
            self.btn_unlock.setText(t("Kilidi Aç"))
        else:
            self.lock_text.setText(t("Dünyayı sıfırlama, yedekten geri yükleme ve sunucuyu silme gibi geri alınamayan "
                                     "işlemler burada. Bu sunucuda PIN yok; girmek için sunucunun adını yaz."))
            self.btn_unlock.setText(t("Kilidi Aç"))

    def unlock(self):
        stored = self._pin()
        if not stored:
            name = self.app.config.name
            typed, ok = get_text(self, t("Kilidi Aç"), t("Girmek için sunucunun adını yaz: {name}", name=name))
            if not ok:
                return
            if typed.strip() != name:
                self.warn("Sunucu adı eşleşmiyor.")
                return
        else:
            for attempt in range(3):
                msg = t("Tehlikeli Bölge'ye girmek için PIN gerekli.")
                if attempt:
                    msg += "\n" + t("Yanlış PIN, tekrar dene ({n} hak kaldı).", n=3 - attempt)
                pin, ok = get_text(self, t("PIN gerekli"), msg, password=True)
                if not ok:
                    return
                if verify_pin(pin, stored):
                    break
            else:
                self.warn("3 kez yanlış PIN girildi.")
                return
        self.stack.setCurrentIndex(1)
        self.relock.start()
        self.on_show()

    def hideEvent(self, e):
        if not self.busy:
            self.lock()                          # sayfadan çıkınca kilitlenir
        super().hideEvent(e)

    # ------------------------------------------------------------ durum
    def on_show(self):
        self.backup_box.clear()
        for name, size, when in self.app.backups.list():
            self.backup_box.addItem(f"{name}  ·  {size / 1048576:.1f} MB  ·  {when:%d.%m.%Y %H:%M}", name)
        if not self.backup_box.count():
            self.backup_box.addItem(t("(yedek yok)"), "")
        self._fill_backup_players()
        self._restore_mode_changed()
        self._sync()

    def _sync(self):
        running = self.app.server.is_running
        self.run_lbl.setText(t("Sunucu çalışıyor: bu işlemler için önce sunucuyu durdur.") if running else "")
        self.run_lbl.setVisible(running)
        ok = not running and not self.busy
        for b in (self.btn_reset, self.btn_players, self.btn_delete, self.btn_template, self.btn_trim_plan):
            b.setEnabled(ok)
        self.btn_trim.setEnabled(ok and bool(self._trim_plan and self._trim_plan["chunks"]))
        self.btn_restore.setEnabled(ok and bool(self.backup_box.currentData()))

    def _confirm_name(self, what):
        """Kullanıcı sunucunun adını birebir yazmalı."""
        if self.read_only():
            return False
        self.relock.start()                      # işlem yapan kullanıcıyı ortada kilitleme
        name = self.app.config.name
        typed, ok = get_text(self, t("Onay"), what + "\n\n" +
                             t("Onaylamak için sunucunun adını yaz: {name}", name=name))
        if not ok:
            return False
        if typed.strip() != name.strip():
            self.warn("Yazdığın ad sunucunun adıyla aynı değil. İşlem yapılmadı.")
            return False
        return True

    def _bg(self, job, fn):
        self.busy = True
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._sync()

        def work():
            try:
                self.finished.emit(fn(), None, job)
            except Exception as e:
                self.finished.emit(None, e, job)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, res, err, job):
        self.busy = False
        self.progress.setVisible(False)
        self.on_show()
        if err is not None:
            msg = t(err.template, **err.kw) if isinstance(err, danger.DangerError) else err_text(err)
            self.error(msg)
            return
        if job == "reset":
            targets, bk = res
            self.info(t("Dünya sıfırlandı ({n} klasör silindi).", n=len(targets)) +
                      ("\n" + t("Yedek: {file}", file=os.path.basename(bk)) if bk else ""))
        elif job == "restore":
            tops, bk = res
            self.info(t("Yedek geri yüklendi: {dirs}", dirs=", ".join(tops)) +
                      ("\n" + t("Önceki dünyanın yedeği: {file}", file=os.path.basename(bk)) if bk else ""))
        elif job == "trim_plan":
            self._trim_plan = res
            if res["chunks"]:
                self.trim_info.setText(t("{n} / {total} chunk silinecek; yaklaşık {mb} MB yer açılır. Temizle'ye bas.",
                                         n=res["chunks"], total=res["total"], mb=f"{res['free'] / 1048576:.0f}"))
            else:
                self.trim_info.setText(t("Silinecek chunk yok ({total} chunk incelendi).", total=res["total"]))
            self._sync()
        elif job == "trim":
            saved, bk = res
            self._trim_plan = None
            self.trim_info.setText("")
            self.info(t("Dünya temizlendi; {mb} MB yer açıldı.", mb=f"{saved / 1048576:.0f}") +
                      ("\n" + t("Yedek: {file}", file=os.path.basename(bk)) if bk else ""))
        elif job == "restore_part":
            n, bk = res
            self.info(t("{n} dosya yedekten geri yüklendi.", n=n) +
                      ("\n" + t("Önceki dünyanın yedeği: {file}", file=os.path.basename(bk)) if bk else ""))
        elif job == "template":
            moved, applied = res
            msg = t("Harita kuruldu.")
            if moved:
                msg += "\n" + t("Önceki dünya: {dirs}", dirs=", ".join(moved))
            if applied:
                msg += "\n" + t("Değiştirilen ayarlar: {props}", props=", ".join(f"{k}={v}" for k, v in applied.items()))
            self.info(msg)
        elif job == "players":
            self.info(t("Oyuncu verileri silindi ({n} klasör).", n=len(res)))
        elif job == "delete":
            win = self.window()
            sid = self.app.id
            self.info(t("Sunucu klasörü Geri Dönüşüm Kutusu'na taşındı.") if res == "recycle" else
                      t("Sunucu silindi."))
            win.settings.remove_server(sid)
            win.show_home()
            QTimer.singleShot(0, lambda: win.forget_server(sid))

    # ------------------------------------------------------------ işlemler
    def replace_template(self):
        from core import maps
        from core.config import detect_version
        from ..template_dialog import TemplateDialog
        if self.read_only():
            return
        sp = self.app.config.server_path
        dlg = TemplateDialog(self.window().settings.get("update_contact") or "", detect_version(sp)[0], self)
        if not dlg.exec() or not dlg.chosen():
            return
        m = dlg.chosen()
        from .. import i18n
        from core.danger import level_name
        name = maps.text(m.get("name"), i18n.current())
        if not self._confirm_name(t("Dünya '{map}' haritasıyla değiştirilecek.", map=name)):
            return
        level = level_name(self.app.properties)
        contact = self.window().settings.get("update_contact") or ""
        self._bg("template", lambda: maps.install(m, sp, level, contact, replace=True))

    def reset_world(self):
        dims = {k for k, cb in self.dim.items() if cb.isChecked()}
        if not dims:
            self.warn("En az bir boyut seç.")
            return
        mode = self.seed_mode.currentData()
        if mode == "custom" and not self.seed.text().strip():
            self.warn("Seed yaz ya da Rastgele seed seç.")
            return
        names = ", ".join(t(n) for k, n in (("overworld", "Overworld"), ("nether", "Nether"), ("end", "End"))
                          if k in dims)
        if not self._confirm_name(t("Şu boyutlar silinecek: {dims}", dims=names)):
            return
        backup = self.reset_backup.isChecked()
        seed = self.seed.text()
        self._bg("reset", lambda: danger.reset_world(self.app, dims, mode, seed, backup))

    def _fill_backup_players(self, *_):
        self.player_pick.clear()
        self.player_pick.addItem(t("Tüm oyuncular"), None)
        name = self.backup_box.currentData()
        if not name:
            return
        try:
            uuids = danger.backup_players(os.path.join(self.app.backups.folder, name), danger.level_name(self.app.properties))
        except Exception:
            return
        try:
            self.app.players._load_name_cache()
            names = self.app.players.uuid_to_name
        except Exception:
            names = {}
        for u in uuids:
            self.player_pick.addItem(names.get(u, u[:8] + "…"), u)

    def _restore_mode_changed(self, *_):
        mode = self.restore_mode.currentData()
        self.parts_box.setVisible(mode == "parts")
        self.area_box.setVisible(mode == "area")
        self.player_pick.setEnabled(self.part_cb["players"].isChecked())
        self.restore_hint.setText({
            "all": t("Şu anki dünyanın tamamı silinir, yedekteki yerine konur."),
            "parts": t("Yalnızca işaretlediğin parçalar yedektekiyle değiştirilir; geri kalan her şey olduğu gibi kalır. "
                       "Oyuncu verisi: envanter, konum, ender sandığı, istatistik ve ilerlemeler."),
            "area": t("Seçilen noktanın çevresindeki bölge dosyaları (512×512 bloklık parçalar) yedektekiyle değiştirilir. "
                      "Yarıçap 512'ye yuvarlanır; çevredeki birkaç yüz blok da geri dönebilir."),
        }[mode])

    def restore(self):
        name = self.backup_box.currentData()
        if not name:
            return
        mode = self.restore_mode.currentData()
        safety = self.restore_safety.isChecked()
        if mode == "all":
            if not self._confirm_name(t("Şu anki dünya silinip '{file}' geri yüklenecek.", file=name)):
                return
            self._bg("restore", lambda: danger.restore_backup(self.app, name, safety))
            return
        if mode == "parts":
            parts = {k for k, cb in self.part_cb.items() if cb.isChecked()}
            if not parts:
                self.warn("En az bir parça seç.")
                return
            who = self.player_pick.currentData()
            players = [who] if ("players" in parts and who) else None
            what = ", ".join(cb.text() for cb in self.part_cb.values() if cb.isChecked())
            if "players" in parts and who:
                what += f" ({self.player_pick.currentText()})"
            area = None
        else:
            parts = {"area"}
            players = None
            area = (self.area_dim.currentData(), self.area_x.value(), self.area_z.value(), self.area_r.value())
            what = t("{dim} · X {x}, Z {z} çevresi ({r} blok)", dim=self.area_dim.currentText(),
                     x=area[1], z=area[2], r=area[3])
        if not self._confirm_name(t("'{file}' yedeğinden geri yüklenecek: {what}", file=name, what=what)):
            return
        self._bg("restore_part", lambda: danger.restore_partial(self.app, name, parts, players, area, safety))

    def _trim_args(self):
        lv = danger.level_name(self.app.properties)
        spawn = (0, 0)
        try:
            from core.players import _get, _val, read_nbt
            root = read_nbt(os.path.join(self.app.config.server_path, lv, "level.dat"))
            data = _get(root, "Data")
            sx, sz = _get(data, "SpawnX"), _get(data, "SpawnZ")
            if sx is not None:
                spawn = (int(_val(sx)), int(_val(sz)))
        except Exception:
            pass
        return [lv, lv + "_nether", lv + "_the_end"], (spawn[0], spawn[1], self.trim_keep.value())

    def trim_preview(self):
        from core import trim
        levels, keep = self._trim_args()
        mins = self.trim_min.value()
        self._trim_plan = None
        self._bg("trim_plan", lambda: trim.plan(self.app.config.server_path, levels, mins, keep))

    def trim_apply(self):
        from core import trim
        p = self._trim_plan
        if not p or not p["chunks"]:
            return
        if not self._confirm_name(t("{n} chunk silinecek (yaklaşık {mb} MB).", n=p["chunks"], mb=f"{p['free'] / 1048576:.0f}")):
            return
        safety = self.trim_safety.isChecked()

        def job():
            bk = self.app.backups.create(prefix="before_trim") if safety else None
            return trim.apply(self.app.server, p), bk
        self._bg("trim", job)

    def reset_players(self):
        if self._confirm_name(t("Tüm oyuncuların envanteri, konumu, istatistikleri ve ilerlemeleri silinecek.")):
            self._bg("players", lambda: danger.reset_players(self.app))

    def delete_server(self):
        path = self.app.config.server_path
        if self._confirm_name(t("'{path}' klasörü Geri Dönüşüm Kutusu'na taşınacak ve sunucu listeden kaldırılacak.",
                                path=path)):
            self._bg("delete", lambda: danger.delete_server(self.app))
