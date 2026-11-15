"""Canlı Harita: BlueMap'i panelin içinde gösterir; yoksa Modrinth'ten kurar ve ayarlarını yapar."""
import threading
import webbrowser

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import QLineEdit, QProgressBar, QStackedWidget, QVBoxLayout, QWidget

from core import N_, bluemap, software
from core.config import detect_version
from ..i18n import t
from ..widgets import Card, Page, ask, button, label, row

try:                                          # derlemede WebEngine yoksa tarayıcıya düşer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEB = True
except Exception:
    HAS_WEB = False

DEFAULT_URL = "http://localhost:8100"


class MapPage(Page):
    title = "Canlı Harita"
    probed = Signal(bool, str)
    found = Signal(dict, bool, str)
    progress = Signal(int, int)
    installed = Signal(str, str)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.root.setContentsMargins(16, 12, 16, 16)
        self.root.setSpacing(10)
        self.st = {}
        self.loaded_url = ""

        # üst çubuk: durum + adres + işlemler
        self.state = label("", "CardTitle")
        self.addr = QLineEdit()
        self.addr.setObjectName("Mono")
        self.addr.setPlaceholderText(DEFAULT_URL)
        self.addr.returnPressed.connect(self._addr_changed)
        self.addr.setMaximumWidth(280)
        self.btn_reload = button("Yenile", "ghost", self.refresh)
        self.btn_browser = button("Tarayıcıda Aç", "ghost", lambda: webbrowser.open(self.url()))
        self.root.addLayout(row(self.state, None, self.addr, self.btn_reload, self.btn_browser, stretch_end=False))

        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)

        # 0: bilgi / kurulum kartı
        info = QWidget()
        iv = QVBoxLayout(info)
        iv.addStretch(1)
        card = Card()
        card.setMaximumWidth(620)
        self.info_title = label("", "BigValue")
        self.info_title.setAlignment(Qt.AlignCenter)
        self.info_text = label("", "Muted", wrap=True)
        self.info_text.setAlignment(Qt.AlignCenter)
        self.bar = QProgressBar()
        self.bar.hide()
        self.btn_install = button("BlueMap'i Kur", "primary", self.install)
        self.btn_accept = button("Doku indirmeye izin ver", "primary", self.accept)
        self.btn_start = button("Sunucuyu Başlat", "primary", self._start_server)
        card.add(self.info_title)
        card.add(self.info_text)
        card.add(self.bar)
        for b in (self.btn_install, self.btn_accept, self.btn_start):
            b.hide()                      # durum belli olana kadar hiçbiri görünmesin
        card.add(row(None, self.btn_install, self.btn_accept, self.btn_start, stretch_end=True))
        iv.addLayout(row(None, card, stretch_end=True))
        iv.addStretch(2)
        self.stack.addWidget(info)

        # 1: gömülü harita
        if HAS_WEB:
            self.web = QWebEngineView()
            self.web.loadFinished.connect(self._load_finished)
            self.stack.addWidget(self.web)
        else:
            self.web = None

        self.probed.connect(self._on_probe)
        self.found.connect(self._on_found)
        self.progress.connect(lambda a, b: (self.bar.setMaximum(max(b, 1)), self.bar.setValue(a)))
        self.installed.connect(self._on_installed)
        # sunucu açılınca BlueMap'in web sunucusu birkaç saniye sonra hazır olur: kısa aralıklarla tekrar dene
        self.retry = QTimer(self)
        self.retry.setInterval(5000)
        self.retry.timeout.connect(self._probe)

    # ---------------------------------------------------------------- durum
    def _modded(self):
        return self.app.plugins.modded

    def url(self):
        u = (self.app.config.get("bluemap_url") or "").strip()
        if not u or u == DEFAULT_URL:
            return f"http://localhost:{self.st.get('port', 8100)}"
        return u

    def _addr_changed(self):
        u = self.addr.text().strip()
        self.app.config.set("bluemap_url", u or DEFAULT_URL)
        self.loaded_url = ""
        self.refresh()

    def on_show(self):
        self.refresh()

    def hideEvent(self, e):
        self.retry.stop()
        super().hideEvent(e)

    def refresh(self):
        self.st = bluemap.status(self.app.config.server_path, self._modded())
        self.addr.setText(self.url())
        self.addr.setCursorPosition(0)
        if not self.st["installed"] and not self._custom_url():
            self._show_info(N_("BlueMap kurulu değil"),
                            t("BlueMap, dünyanın 3D haritasını tarayıcıda gösteren ücretsiz bir eklentidir. "
                              "Spypaper bu sunucunun yazılımına ve Minecraft sürümüne uygun sürümü Modrinth'ten indirip kurabilir."),
                            install=True)
            return
        if self.st["config"] and self.st["accepted"] is False:
            self._show_info(N_("Bir adım kaldı"),
                            t("BlueMap haritayı çizebilmek için Minecraft'ın doku dosyalarını Mojang'dan indirmek istiyor. "
                              "Bunun için BlueMap ayarlarında izin verilmesi gerekiyor."), accept=True)
            return
        if self.st["installed"] and not self.st["config"]:
            self._show_info(N_("BlueMap kuruldu"),
                            t("Ayar dosyalarının oluşması için sunucuyu bir kez başlat. Ardından bu sayfaya dön."),
                            start=not self.app.server.is_running)
            return
        if not self.st["web_enabled"] and not self._custom_url():
            self._show_info(N_("Web sunucusu kapalı"),
                            t("BlueMap'in webserver.conf dosyasında web sunucusu kapatılmış (enabled: false)."))
            return
        # bağlantı denenirken kart boş kalmasın; harita zaten yüklüyse onu göstermeye devam et
        if self.stack.currentIndex() == 0 or not self.loaded_url:
            self._show_info(N_("Bağlanılıyor…"), t("{url} adresindeki haritaya bağlanılıyor.", url=self.url()))
        else:
            self.state.setText(t("Bağlanılıyor…"))
        self._probe()

    def _custom_url(self):
        u = (self.app.config.get("bluemap_url") or "").strip()
        return bool(u) and u != DEFAULT_URL

    def _show_info(self, title, text, install=False, accept=False, start=False):
        self.retry.stop()
        self.state.setText(t(title))
        self.info_title.setText(t(title))
        self.info_text.setText(text)
        self.btn_install.setVisible(install)
        self.btn_accept.setVisible(accept)
        self.btn_start.setVisible(start)
        self.stack.setCurrentIndex(0)

    def _probe(self):
        url = self.url()

        def work():
            self.probed.emit(bluemap.reachable(url), url)
        threading.Thread(target=work, daemon=True).start()

    def _on_probe(self, ok, url):
        if url != self.url():
            return
        if not ok:
            running = self.app.server.is_running or self.app.server.state in ("starting", "running")
            self._show_info(N_("Harita yanıt vermiyor"),
                            t("{url} adresine ulaşılamadı.", url=url) + " " +
                            (t("Sunucu yeni açıldıysa BlueMap birkaç saniye içinde hazır olur; otomatik tekrar deneniyor.")
                             if running else t("Harita, sunucu çalışırken açılır.")),
                            start=not running)
            if running:
                self.retry.start()
            return
        self.retry.stop()
        if not self.web:
            self._show_info(N_("Harita hazır"),
                            t("Bu derlemede gömülü tarayıcı yok; haritayı Tarayıcıda Aç ile açabilirsin."))
            return
        self.state.setText(t("BlueMap · {url}", url=url))
        self.stack.setCurrentIndex(1)
        if self.loaded_url != url:
            self.loaded_url = url
            self.web.setUrl(QUrl(url))

    def _load_finished(self, ok):
        if not ok:
            self.loaded_url = ""
            self.state.setText(t("Harita yüklenemedi"))

    # ---------------------------------------------------------------- işlemler
    def _start_server(self):
        p = self.window()
        panel = getattr(p, "current_panel", lambda: None)()
        if panel:
            panel.start()
        QTimer.singleShot(4000, self.refresh)

    def accept(self):
        if self.read_only():
            return
        if not ask(self, t("BlueMap, Minecraft istemcisinin doku dosyalarını Mojang'ın sunucularından indirecek. "
                           "Bu dosyalar Mojang'a aittir ve Minecraft EULA'sına tabidir.\n\nİzin verilsin mi?"), t("Onay")):
            return
        if not bluemap.accept_download(self.app.config.server_path):
            self.error("BlueMap ayar dosyası (core.conf) güncellenemedi.")
            return
        if self.app.server.is_running:
            self.send("bluemap reload", confirmed=True)
        self.info("İzin verildi. BlueMap dokuları indirip haritayı çizmeye başlayacak; ilk çizim birkaç dakika sürebilir.")
        self.refresh()

    def install(self):
        if self.read_only():
            return
        key, ver, _ = software.current(self.app.config.server_path, self.app.config.get("jar_name"))
        ver = ver or detect_version(self.app.config.server_path)[0]
        self.btn_install.setEnabled(False)
        self.state.setText(t("Modrinth'te aranıyor…"))
        contact = self.app.config.settings.get("update_contact")

        def work():
            try:
                info, exact = bluemap.find_release(key, ver, contact)
                self.found.emit(info, exact, "")
            except Exception as e:
                self.found.emit({}, False, t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_found(self, info, exact, err):
        self.btn_install.setEnabled(True)
        if err:
            self.state.setText(t("Kurulamadı"))
            self.error(err)
            return
        msg = t("BlueMap {v} indirilecek ({file}).", v=info["version"], file=info["name"])
        if not exact:
            msg += "\n\n" + t("Bu Minecraft sürümü için listelenmiş bir sürüm yok; en yeni sürüm ({games}) çalışmayabilir.",
                              games=", ".join(info["game_versions"][-3:]))
        if self.app.server.is_running:
            msg += "\n\n" + t("Sunucu çalışıyor; BlueMap yeniden başlatınca yüklenir.")
        if not ask(self, msg + "\n\n" + t("Devam edilsin mi?"), t("Onay")):
            return
        self.btn_install.setEnabled(False)
        self.bar.show()
        sp, modded = self.app.config.server_path, self._modded()
        contact = self.app.config.settings.get("update_contact")

        def work():
            try:
                self.installed.emit(bluemap.install(info, sp, modded, contact,
                                                    progress=lambda a, b: self.progress.emit(a, b)), "")
            except Exception as e:
                self.installed.emit("", t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        threading.Thread(target=work, daemon=True).start()

    def _on_installed(self, name, err):
        self.bar.hide()
        self.btn_install.setEnabled(True)
        if err:
            self.error(err)
            return
        self.info(t("BlueMap kuruldu: {file}", file=name) + "\n\n" +
                  t("Sunucuyu (yeniden) başlattığında BlueMap ayar dosyalarını oluşturur; sonra bu sayfadan doku indirme iznini verebilirsin."))
        self.refresh()
