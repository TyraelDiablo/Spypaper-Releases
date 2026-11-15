"""Tehlikeli Bölge: PIN ile açılan, geri alınamayan işlemler.

Sunucuda PIN varsa o sorulur; yoksa yalnızca bu bölge için ayrı bir PIN belirlenir (paneli açarken
sorulmaz). Kilit, sayfadan çıkınca ya da 5 dakika sonra yeniden kapanır. Her işlem için sunucu kapalı
olmalı ve sunucunun adı elle yazılarak onaylanmalı. Telefondan (Remote) bu bölgeye erişilemez.
"""
import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QProgressBar, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from core import N_, danger
from core.safemode import hash_pin, verify_pin
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
        w.add(row(*dims))
        w.add(label("Vanilla, Fabric ve Forge'da Nether ve End dünya klasörünün içindedir; Overworld silinince "
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

        # yedekten geri yükle
        r = danger_card("Yedekten Geri Yükle", "Şu anki dünya silinir ve seçilen yedek yerine konur")
        self.backup_box = QComboBox()
        self.backup_box.setMinimumWidth(320)
        r.add(row(self.backup_box))
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
                                     "işlemler burada. Bu sunucuda PIN yok; Tehlikeli Bölge için bir PIN belirle. "
                                     "Bu PIN yalnızca burada sorulur."))
            self.btn_unlock.setText(t("PIN Belirle"))

    def unlock(self):
        stored = self._pin()
        if not stored:
            p1, ok = get_text(self, t("PIN Belirle"), t("Yeni PIN (4-12 rakam)"), password=True)
            if not ok:
                return
            if not (p1.isdigit() and 4 <= len(p1) <= 12):
                self.warn("PIN 4-12 rakamdan oluşmalı.")
                return
            p2, ok = get_text(self, t("PIN Belirle"), t("PIN tekrar"), password=True)
            if not ok:
                return
            if p1 != p2:
                self.warn("PIN'ler eşleşmiyor.")
                return
            self.app.config.set("danger_pin_hash", hash_pin(p1))
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
        self._sync()

    def _sync(self):
        running = self.app.server.is_running
        self.run_lbl.setText(t("Sunucu çalışıyor: bu işlemler için önce sunucuyu durdur.") if running else "")
        self.run_lbl.setVisible(running)
        ok = not running and not self.busy
        for b in (self.btn_reset, self.btn_players, self.btn_delete):
            b.setEnabled(ok)
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

    def restore(self):
        name = self.backup_box.currentData()
        if not name:
            return
        if not self._confirm_name(t("Şu anki dünya silinip '{file}' geri yüklenecek.", file=name)):
            return
        safety = self.restore_safety.isChecked()
        self._bg("restore", lambda: danger.restore_backup(self.app, name, safety))

    def reset_players(self):
        if self._confirm_name(t("Tüm oyuncuların envanteri, konumu, istatistikleri ve ilerlemeleri silinecek.")):
            self._bg("players", lambda: danger.reset_players(self.app))

    def delete_server(self):
        path = self.app.config.server_path
        if self._confirm_name(t("'{path}' klasörü Geri Dönüşüm Kutusu'na taşınacak ve sunucu listeden kaldırılacak.",
                                path=path)):
            self._bg("delete", lambda: danger.delete_server(self.app))
