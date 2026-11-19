"""Discord: sunucu olaylarını bir Discord kanalına webhook ile bildirir. İş mantığı core.discord'da."""
import threading

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout

from core import discord as dc
from .. import icons
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, button, label, row

HELP_URL = "https://support.discord.com/hc/articles/228383668"


class DiscordPage(Page):
    title = "Discord"
    test_done = Signal(str)                 # boş: başarılı, değilse hata metni

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.dc = app.discord
        top = QHBoxLayout()
        top.setSpacing(14)

        # --- bağlantı ---
        conn = Card("Discord Bildirimleri",
                    "Sunucu açıldı, kapandı, çöktü ya da oyuncu girdi gibi olaylar seçtiğin Discord kanalına gider. "
                    "Bot ya da hesap gerekmez: kanalın webhook adresini buraya yapıştırman yeterli.")
        self.enabled = QCheckBox(t("Discord bildirimlerini aç"))
        self.enabled.setCursor(Qt.PointingHandCursor)
        conn.add(self.enabled)
        conn.add(label("Webhook adresi", "CardTitle"))
        self.url = QLineEdit()
        self.url.setEchoMode(QLineEdit.Password)
        self.url.setClearButtonEnabled(True)
        self.url.textChanged.connect(self._url_changed)
        self.show_btn = button("Göster", "ghost", self._toggle_show)
        conn.add(row(self.url, self.show_btn, stretch_end=False))
        self.url_state = label("", "Muted", wrap=True)
        conn.add(self.url_state)
        steps = label(
            t("Nasıl alınır: Discord'da kanalın ayarları → Entegrasyonlar → Webhook'lar → Yeni Webhook → "
              "Webhook URL'sini Kopyala. Adresi bilen herkes o kanala yazabilir; kimseyle paylaşma. "
              "Spypaper adresi bu bilgisayarda şifreli saklar."), "Muted", wrap=True, raw=True)
        conn.add(steps)
        help_btn = button("Discord yardım sayfası", "flat", lambda: QDesktopServices.openUrl(QUrl(HELP_URL)))
        help_btn.setIcon(icons.icon("external-link", None, 16))
        self.test_btn = button("Test Mesajı Gönder", "ghost", self.test)
        self.save_btn = button("Kaydet", "primary", self.save)
        conn.add(row(help_btn, None, self.test_btn, self.save_btn, stretch_end=False))
        self.status = label("", "Muted", wrap=True)
        conn.add(self.status)
        conn.end()
        top.addWidget(conn, 3)

        # --- olaylar ---
        ev = Card("Bildirilecek Olaylar", "Her olay ayrı bir mesaj olarak gönderilir.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        self.boxes = {}
        for i, (key, (name, _)) in enumerate(dc.EVENTS.items()):
            cb = QCheckBox(t(name))
            cb.setCursor(Qt.PointingHandCursor)
            self.boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        ev.add(grid)
        ev.add(label("Oyuncu olayları ve sohbet sunucunun konsolundan okunur; yalnızca Spypaper'ın başlattığı "
                     "sunucularda çalışır. Sohbet mesajları Discord'a gönderilir, oyuncularını bilgilendir. "
                     "Mesajlarda @everyone ve etiketler çalışmaz.", "Muted", wrap=True))
        ev.end()
        side = QVBoxLayout()
        side.addWidget(ev)
        side.addStretch(1)
        top.addLayout(side, 2)
        self.root.addLayout(top)
        self.root.addStretch(1)

        self.test_done.connect(self._on_test)
        self._shown = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._status)

    # ------------------------------------------------------------------ durum
    def on_show(self):
        s = self.dc.settings
        self.enabled.setChecked(s["enabled"])
        for k, cb in self.boxes.items():
            cb.setChecked(s["events"].get(k, False))
        self.url.blockSignals(True)
        self.url.clear()
        self.url.blockSignals(False)
        self.url.setPlaceholderText(t("Kayıtlı (değiştirmek için yeni adresi yapıştır)") if s["url"]
                                    else "https://discord.com/api/webhooks/…")
        self._url_changed(self.url.text())
        self._status()
        self.timer.start(3000)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def _toggle_show(self):
        self._shown = not self._shown
        self.url.setEchoMode(QLineEdit.Normal if self._shown else QLineEdit.Password)
        self.show_btn.setText(t("Gizle") if self._shown else t("Göster"))

    def _url_changed(self, text):
        text = text.strip()
        if not text:
            self.url_state.setText(t("Webhook adresi kayıtlı.") if self.dc.settings["url"] else
                                   t("Henüz webhook adresi yok."))
            self.url_state.setStyleSheet("")
        elif dc.valid_url(text):
            self.url_state.setText(t("Geçerli bir Discord webhook adresi."))
            self.url_state.setStyleSheet(f"color:{TOKENS['accent']}")
        else:
            self.url_state.setText(t("Bu bir Discord webhook adresine benzemiyor (https://discord.com/api/webhooks/… olmalı)."))
            self.url_state.setStyleSheet(f"color:{TOKENS['danger']}")

    def _status(self):
        if self.dc.last_error:
            self.status.setText(t("Son gönderim başarısız: {error}", error=self.dc.last_error))
            self.status.setStyleSheet(f"color:{TOKENS['danger']}")
        elif self.dc.last_sent:
            self.status.setText(t("Son mesaj gönderildi: {time}", time=f"{self.dc.last_sent:%H:%M:%S}"))
            self.status.setStyleSheet("")
        else:
            self.status.setText("")

    # ------------------------------------------------------------------ işlemler
    def _events(self):
        return {k: cb.isChecked() for k, cb in self.boxes.items()}

    def save(self, quiet=False):
        if self.read_only():
            return False
        new = self.url.text().strip()
        if new and not dc.valid_url(new):
            self.warn("Bu bir Discord webhook adresine benzemiyor (https://discord.com/api/webhooks/… olmalı).")
            return False
        if self.enabled.isChecked() and not (new or self.dc.settings["url"]):
            self.warn("Bildirimleri açmak için önce bir webhook adresi yapıştır.")
            return False
        try:
            self.dc.save(self.enabled.isChecked(), self._events(), new or None)
        except dc.DiscordError as e:
            self.error(t(e.template, **e.kw))
            return False
        self.on_show()
        if not quiet:
            self.info("Discord ayarları kaydedildi.")
        return True

    def test(self):
        url = self.url.text().strip() or self.dc.url()
        if not url:
            self.warn("Önce bir webhook adresi yapıştır.")
            return
        if not dc.valid_url(url):
            self.warn("Bu bir Discord webhook adresine benzemiyor (https://discord.com/api/webhooks/… olmalı).")
            return
        self.test_btn.setEnabled(False)
        self.status.setStyleSheet("")
        self.status.setText(t("Gönderiliyor…"))

        def work():
            try:
                self.dc.test(url)
                self.test_done.emit("")
            except dc.DiscordError as e:
                self.test_done.emit(t(e.template, **e.kw))
            except Exception as e:
                self.test_done.emit(str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_test(self, err):
        self.test_btn.setEnabled(True)
        if err:
            self.status.setText(t("Test başarısız: {error}", error=err))
            self.status.setStyleSheet(f"color:{TOKENS['danger']}")
            return
        self.status.setText(t("Test mesajı gönderildi. Discord kanalını kontrol et."))
        self.status.setStyleSheet(f"color:{TOKENS['accent']}")
        if self.url.text().strip() and self.url.text().strip() != self.dc.url():
            self.status.setText(self.status.text() + " " + t("Adresi saklamak için Kaydet'e bas."))
