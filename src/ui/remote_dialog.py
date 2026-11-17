"""Spypaper Remote: masaüstü tarafı.

RemoteController web sunucusunu (core.remote) çalıştırır ve telefondan gelen başlat/durdur isteklerini
Qt'nin ana thread'ine taşır. RemoteDialog: aç/kapat, port, QR ile cihaz eşleme, eşli cihazlar.
"""
import io
import os
import threading
import time
from datetime import datetime

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from core import N_, remote as R
from core.gamefiles import status as gf_status
from . import i18n, icons
from .i18n import t
from .theme import TOKENS
from .widgets import button, label


class _Invoker(QObject):
    """Başka thread'den gelen işi ana thread'de çalıştırır ve sonucu bekletir."""
    run = Signal(object)

    def __init__(self):
        super().__init__()
        self.run.connect(self._run, Qt.QueuedConnection)

    def _run(self, job):
        fn, box, done = job
        try:
            box["result"] = fn()
        except Exception as e:                        # noqa: BLE001 — hata metni telefona döner
            box["error"] = e
        done.set()

    def call(self, fn, timeout=15):
        if threading.current_thread() is threading.main_thread():
            return fn()
        box, done = {}, threading.Event()
        self.run.emit((fn, box, done))
        if not done.wait(timeout):
            raise TimeoutError("timeout")
        if "error" in box:
            raise box["error"]
        return box.get("result")


def eula_accepted(server_path):
    try:
        with open(os.path.join(server_path, "eula.txt"), "r", encoding="utf-8", errors="ignore") as f:
            return any(ln.strip().lower().replace(" ", "") == "eula=true" for ln in f)
    except OSError:
        return False


class _Provider(R.Provider):
    def __init__(self, ctl, controller):
        self.ctl, self.c = ctl, controller

    def servers(self):
        return self.ctl.settings.servers()

    def app(self, sid):
        return self.ctl.apps.get(sid)

    def translate(self, text, **kw):
        return t(text, **kw)

    def language(self):
        return i18n.current(), i18n.is_rtl()

    def languages(self):
        return i18n.available()

    def table(self, lang):
        return i18n.table_for(lang)

    def is_rtl(self, lang):
        return lang in i18n.RTL

    def settings_get(self, sid):
        return self.c.invoker.call(lambda: self.c.settings_get(sid))

    def settings_save(self, sid, data):
        return self.c.invoker.call(lambda: self.c.settings_save(sid, data))

    def maintenance(self, sid, on):
        return self.c.invoker.call(lambda: self.c.maintenance(sid, on))

    def icons_dir(self):
        try:
            return gf_status()["icons_dir"]
        except Exception:
            return ""

    def save_remote(self, data):
        self.c.invoker.call(lambda: self.ctl.settings.set("remote", data))

    def on_change(self):
        self.c.changed.emit()

    def control(self, sid, action):
        return self.c.invoker.call(lambda: self.c.do_control(sid, action))


class RemoteController(QObject):
    changed = Signal()            # cihaz listesi / durum değişti

    def __init__(self, ctl):
        super().__init__(ctl)
        self.ctl = ctl
        self.invoker = _Invoker()
        self.server = R.RemoteServer(_Provider(ctl, self), ctl.settings.get("remote") or {})
        self._restart = {}        # sid -> zaman aşımı

    # --- yaşam döngüsü ---
    def autostart(self):
        if self.server.data.get("enabled"):
            self.server.start()

    def set_enabled(self, on):
        self.server.set_option("enabled", bool(on))
        if on:
            ok = self.server.start()
        else:
            self.server.stop()
            ok = True
        self.changed.emit()
        return ok

    def set_port(self, port):
        if int(port) == self.server.port:
            return True
        self.server.set_option("port", int(port))
        if self.server.running:
            self.server.stop()
            ok = self.server.start()
            self.changed.emit()
            return ok
        return True

    def shutdown(self):
        self.server.stop()
        self.server._persist(notify=False)          # son bağlantı zamanları kaydedilsin

    # --- telefondan gelen kontrol (ana thread) ---
    def do_control(self, sid, action):
        prof = self.ctl.settings.server(sid)
        if not prof or not prof.exists:
            return t("Sunucu klasörü bulunamadı.")
        app = self.ctl.app_for(sid)
        from core import ServerError
        from .widgets import err_text
        try:
            if action == "start":
                if app.server.is_running:
                    return t("Sunucu zaten çalışıyor!")
                if not eula_accepted(prof.server_path):
                    return t("Minecraft EULA kabul edilmemiş. Sunucuyu bir kez masaüstündeki Spypaper'dan başlat.")
                app.server.start()
            elif action == "stop":
                if not app.server.is_running:
                    return t("Sunucu kapalı iken komut gönderilemez!")
                app.server.stop()
            elif action == "restart":
                if not app.server.is_running:
                    return t("Sunucu kapalı iken komut gönderilemez!")
                app.server.stop()
                self._restart[sid] = time.time() + 180
                QTimer.singleShot(1000, lambda: self._restart_tick(sid))
        except ServerError as e:
            return err_text(e)
        self.ctl.server_state_changed()
        return None

    # --- telefondan ayarlar ve bakım (ana thread) ---
    def settings_get(self, sid):
        prof = self.ctl.settings.server(sid)
        if not prof or not prof.exists:
            return {}
        app = self.ctl.app_for(sid)
        return {"ram_min": prof.get("ram_min"), "ram_max": prof.get("ram_max"),
                "java": prof.get("java_path"), "jar": prof.get("jar_name"),
                "schedule": app.maintenance.schedule, "props": app.properties.load(),
                "running": app.server.is_running}

    def settings_save(self, sid, data):
        prof = self.ctl.settings.server(sid)
        if not prof or not prof.exists:
            return t("Sunucu klasörü bulunamadı.")
        app = self.ctl.app_for(sid)
        if "ram" in data:
            prof.data["ram_min"], prof.data["ram_max"] = data["ram"]["min"], data["ram"]["max"]
            prof.save()
        if "schedule" in data:
            app.maintenance.set_schedule(data["schedule"])
        if data.get("props"):
            try:
                app.properties.save(data["props"])
            except Exception as e:
                return t(str(e))
        self.ctl.remote_changed(sid)
        return None

    def maintenance(self, sid, on):
        prof = self.ctl.settings.server(sid)
        if not prof or not prof.exists:
            return t("Sunucu klasörü bulunamadı.")
        m = self.ctl.app_for(sid).maintenance
        if on and not m.active:
            m.enable(wait=False)
        elif not on and m.active:
            m.disable()
        self.ctl.remote_changed(sid)
        return None

    def _restart_tick(self, sid):
        until = self._restart.get(sid)
        app = self.ctl.apps.get(sid)
        if not until or not app:
            return
        if app.server.is_running:
            if time.time() < until:
                QTimer.singleShot(1000, lambda: self._restart_tick(sid))
            else:
                self._restart.pop(sid, None)
            return
        self._restart.pop(sid, None)
        try:
            app.server.start()
        except Exception as e:
            print(f"[remote] yeniden başlatılamadı: {e}")
        self.ctl.server_state_changed()


def qr_pixmap(text, size=232):
    """QR kodu (segno ile). segno yoksa None."""
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=1, border=3, dark="#000000", light="#ffffff")
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(buf.getvalue())
    dpr = 2
    px = QPixmap(size * dpr, size * dpr)
    px.fill(QColor("#ffffff"))
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, False)
    r.render(p, QRectF(0, 0, px.width(), px.height()))
    p.end()
    px.setDevicePixelRatio(dpr)
    return px


def _ago(iso):
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return "—"
    return d.strftime("%d.%m.%Y %H:%M")


class RemoteDialog(QDialog):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.rc = ctl.remote
        self.code = ""
        self.code_until = 0
        self.setWindowTitle(t("Spypaper Remote"))
        self.setMinimumWidth(680)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)

        head = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(icons.logo(36))
        head.addWidget(lg)
        tl = QVBoxLayout()
        tl.setSpacing(2)
        tl.addWidget(label("Spypaper Remote", "PageTitle"))
        tl.addWidget(label("Sunucularını telefondan izle; izin verdiğin cihazlardan başlat, durdur, bakıma al ve ayarlarını değiştir.", "Muted", wrap=True))
        head.addLayout(tl, 1)
        v.addLayout(head)

        self.enabled = QCheckBox(t("Spypaper Remote'u aç"))
        self.enabled.setCursor(Qt.PointingHandCursor)
        self.enabled.setChecked(bool(self.rc.server.data.get("enabled")))
        self.enabled.toggled.connect(self.toggle)
        v.addWidget(self.enabled)
        self.status = label("", "Muted", wrap=True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.status)

        opts = QHBoxLayout()
        opts.setSpacing(8)
        opts.addWidget(label("Adres"))
        self.addr = QComboBox()
        for a in R.local_addresses():
            self.addr.addItem(a + ("  (Tailscale)" if R.is_tailscale(a) else ""), a)
        self.addr.currentIndexChanged.connect(lambda _=0: (self._status(), self._qr()))
        opts.addWidget(self.addr, 1)
        opts.addWidget(label("Port"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(self.rc.server.port)
        self.port.editingFinished.connect(self.port_changed)
        opts.addWidget(self.port)
        v.addLayout(opts)

        self.allow = QCheckBox(t("Telefonlardan değişiklik yapılabilsin"))
        self.allow.setChecked(bool(self.rc.server.data.get("allow_control", True)))
        self.allow.setToolTip(t("Kapalıyken bütün cihazlar yalnızca izler. Açıkken her cihaz, aşağıda ona verdiğin "
                                "izinler kadarını yapabilir. PIN'li sunucularda telefonda da PIN sorulur."))
        self.allow.toggled.connect(lambda on: (self.rc.server.set_option("allow_control", bool(on)), self._refresh()))
        v.addWidget(self.allow)

        # --- dış erişim (isteğe bağlı) ---
        ext = QFrame()
        ext.setObjectName("Card")
        ev = QVBoxLayout(ext)
        ev.setContentsMargins(14, 12, 14, 12)
        ev.setSpacing(8)
        ev.addWidget(label("Dış erişim (isteğe bağlı)", "CardTitle"))
        self.upnp = QCheckBox(t("Modemde portu otomatik aç (UPnP)"))
        self.upnp.setChecked(bool(self.rc.server.data.get("upnp")))
        self.upnp.setToolTip(t("Modem UPnP destekliyorsa panel portunu modemde açar. Kapatınca port kapanır."))
        self.upnp.toggled.connect(self._upnp_changed)
        ev.addWidget(self.upnp)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        trow.addWidget(label("Tünel sağlayıcısı"))
        self.tunnel = QComboBox()
        for k, name in R.tunnel_choices():
            self.tunnel.addItem(t(name), k)
        self.tunnel.setCurrentIndex(max(0, self.tunnel.findData(self.rc.server.data.get("tunnel") or "off")))
        self.tunnel.activated.connect(self._tunnel_changed)
        trow.addWidget(self.tunnel, 1)
        ev.addLayout(trow)
        prow = QHBoxLayout()
        prow.setSpacing(8)
        prow.addWidget(label("cloudflared yolu"))
        self.tpath = QLineEdit(self.rc.server.data.get("tunnel_path") or "")
        self.tpath.setPlaceholderText(t("Boş bırakırsan PATH'te aranır"))
        self.tpath.editingFinished.connect(self._tpath_changed)
        prow.addWidget(self.tpath, 1)
        prow.addWidget(button("Gözat", "ghost", self._browse))
        ev.addLayout(prow)
        self.exp_lbl = label("", "Muted", wrap=True, raw=True)
        ev.addWidget(self.exp_lbl)
        ev.addWidget(label("Modem portu açmak paneli şifresiz (HTTP) dışarı çıkarır. Dış erişimde tünel seçmeni öneririm: "
                           "tünel HTTPS kullanır. Tünel için cloudflared programını kendin kurman gerekir; "
                           "Spypaper onu indirmez.", "Muted", wrap=True))
        v.addWidget(ext)

        # --- QR ---
        qr_card = QFrame()
        qr_card.setObjectName("Card")
        qh = QHBoxLayout(qr_card)
        qh.setContentsMargins(14, 14, 14, 14)
        qh.setSpacing(16)
        self.qr = QLabel()
        self.qr.setFixedSize(232, 232)
        self.qr.setAlignment(Qt.AlignCenter)
        self.qr.setStyleSheet(f"background:{TOKENS['surface_2']}; border-radius:10px; color:{TOKENS['text_muted']};")
        self.qr.setWordWrap(True)
        qh.addWidget(self.qr)
        qv = QVBoxLayout()
        qv.setSpacing(8)
        qv.addWidget(label("Yeni Cihaz Eşle", "CardTitle"))
        qv.addWidget(label("1. Telefon bu bilgisayarla aynı Wi-Fi ağında olsun.\n"
                           "2. Yeni Cihaz Eşle'ye bas, telefonun kamerasıyla QR kodu okut.\n"
                           "3. Açılan sayfada Eşle'ye bas. Ana ekrana ekleyince uygulama gibi açılır.",
                           "Muted", wrap=True))
        self.url_lbl = label("", "Muted", wrap=True, raw=True)
        self.url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        qv.addWidget(self.url_lbl)
        self.count_lbl = label("", "Muted", raw=True)
        qv.addWidget(self.count_lbl)
        qv.addStretch(1)
        self.pair_btn = button("Yeni Cihaz Eşle", "primary", self.new_code)
        self.pair_btn.setIcon(icons.icon("smartphone", TOKENS["text_on_accent"], 16))
        qv.addWidget(self.pair_btn)
        qh.addLayout(qv, 1)
        v.addWidget(qr_card)

        # --- cihazlar ---
        v.addWidget(label("Eşli cihazlar", "CardTitle"))
        self.dev_box = QVBoxLayout()
        self.dev_box.setSpacing(6)
        dw = QWidget()
        dw.setLayout(self.dev_box)
        v.addWidget(dw)
        v.addWidget(label("Dışarıdan (mobil veriyle) erişmek için bilgisayara ve telefona Tailscale kur; "
                          "adres listesinde (Tailscale) yazanı seç. Modemde port açmana gerek kalmaz.", "Muted", wrap=True))

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(button("Kapat", "ghost", self.accept))
        v.addLayout(bottom)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self.rc.changed.connect(self._refresh)
        self._refresh()

    # --- olaylar ---
    def toggle(self, on):
        if not self.rc.set_enabled(on):
            self.enabled.blockSignals(True)
            self.enabled.setChecked(False)
            self.enabled.blockSignals(False)
            self.rc.server.set_option("enabled", False)
        self._refresh()

    def port_changed(self):
        self.rc.set_port(self.port.value())
        self.code = ""
        self._refresh()

    def _upnp_changed(self, on):
        self.rc.server.set_option("upnp", bool(on))
        self.rc.server.apply_exposure()
        self._refresh()

    def _tunnel_changed(self, _i=0):
        self.rc.server.set_option("tunnel", self.tunnel.currentData())
        self.rc.server.apply_exposure()
        self._refresh()

    def _tpath_changed(self):
        path = self.tpath.text().strip()
        if path == (self.rc.server.data.get("tunnel_path") or ""):
            return
        self.rc.server.set_option("tunnel_path", path)
        if self.tunnel.currentData() == "cloudflare":
            self.rc.server.apply_exposure()
        self._refresh()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, t("cloudflared programını seç"))
        if path:
            self.tpath.setText(path)
            self._tpath_changed()

    def _exposure_text(self):
        s = self.rc.server
        if not s.running:
            return ""
        e = s.exposure_state()
        parts = []
        if self.upnp.isChecked():
            if e["upnp"] == "ok":
                parts.append(t("Modem portu açıldı.") + (f" {t('Dış IP')}: {e['ext_ip']}" if e["ext_ip"] else ""))
            elif e["upnp"] == "fail":
                parts.append(t("Modem portu açılamadı: {e}", e=t(e["upnp_msg"])))
            else:
                parts.append(t("Modem portu açılıyor..."))
        if self.tunnel.currentData() == "cloudflare":
            if e["tunnel"] == "ok":
                parts.append(t("Tünel açık: {url}", url=e["tunnel_url"]))
            elif e["tunnel"] == "fail":
                parts.append(t("Tünel açılamadı: {e}", e=t(e["tunnel_msg"])))
            else:
                parts.append(t("Tünel açılıyor..."))
        return "\n".join(parts)

    def _tick_exposure(self):
        text = self._exposure_text()
        if text != self.exp_lbl.text():
            self.exp_lbl.setText(text)

    def new_code(self):
        if not self.rc.server.running:
            self.enabled.setChecked(True)
            if not self.rc.server.running:
                return
        self.code = self.rc.server.new_code()
        self.code_until = time.time() + R.CODE_TTL
        self._qr()
        self._tick()

    def _url(self, code=""):
        a = self.addr.currentData() or "127.0.0.1"
        base = f"http://{a}:{self.rc.server.port}"
        tu = self.rc.server.exposure_state().get("tunnel_url") if self.rc.server.running else ""
        if tu:
            base = tu.rstrip("/")
        return base + (f"/pair?code={code}" if code else "")

    def _qr(self):
        if not self.code or time.time() > self.code_until:
            self.qr.setPixmap(QPixmap())
            self.qr.setText(t("QR burada görünecek"))
            self.url_lbl.setText("")
            return
        url = self._url(self.code)
        px = qr_pixmap(url)
        if px is None:
            self.qr.setText(t("QR için 'segno' paketi gerekli. Adresi telefonda elle aç."))
        else:
            self.qr.setPixmap(px)
        self.url_lbl.setText(url)

    def _tick(self):
        self._tick_exposure()
        left = int(self.code_until - time.time()) if self.code else 0
        if self.code and left <= 0:
            self.code = ""
            self._qr()
            self.count_lbl.setText(t("Kodun süresi doldu. Yeni bir QR oluştur."))
        elif self.code:
            self.count_lbl.setText(t("Kod {n} saniye geçerli, bir kez kullanılabilir.", n=left))
        else:
            if not self.count_lbl.text():
                self.count_lbl.setText("")

    def _status(self):
        s = self.rc.server
        if s.running:
            self.status.setText(t("Çalışıyor: {url}", url=f"<b>{self._url()}</b>")
                                + f"<br><span style='color:{TOKENS['text_muted']}'>"
                                + t("Windows güvenlik duvarı izin isterse 'Özel ağlar'a izin ver.") + "</span>")
            self.status.setStyleSheet(f"color:{TOKENS['accent']};")
        elif s.error:
            self.status.setText(t("Başlatılamadı (port {port} kullanımda olabilir): {e}", port=s.port, e=s.error))
            self.status.setStyleSheet(f"color:{TOKENS['danger']};")
        else:
            self.status.setText(t("Kapalı. Açınca telefon bu bilgisayardaki Spypaper'a bağlanabilir."))
            self.status.setStyleSheet(f"color:{TOKENS['text_muted']};")

    def _refresh(self):
        self._status()
        on = self.rc.server.running
        self.pair_btn.setEnabled(on)
        self.addr.setEnabled(True)
        if not on:
            self.code = ""
        self._qr()
        while self.dev_box.count():
            w = self.dev_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        devs = self.rc.server.devices()
        if not devs:
            self.dev_box.addWidget(label("Henüz eşli cihaz yok.", "Muted"))
        for d in devs:
            row = QFrame()
            row.setObjectName("Card")
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 8, 8)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("smartphone", TOKENS["text_muted"], 18))
            h.addWidget(ic)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(d.get("name", ""), raw=True))
            col.addWidget(label(t("Eşlendi: {a} · Son bağlantı: {b}", a=_ago(d.get("created")),
                                  b=_ago(d.get("last_seen"))), "Muted", raw=True))
            perms = {**R.PERMS, **(d.get("perms") or {})}
            ph = QHBoxLayout()
            ph.setSpacing(14)
            for key, text, tip in (
                    ("control", N_("Başlat / durdur"), N_("Sunucuyu başlatma, durdurma ve yeniden başlatma")),
                    ("maintenance", N_("Bakım"), N_("Bakım modunu başlatma ve bitirme")),
                    ("settings", N_("Sunucu ayarları"), N_("RAM, otomatik bakım planı ve server.properties"))):
                cb = QCheckBox(t(text))
                cb.setToolTip(t(tip))
                cb.setCursor(Qt.PointingHandCursor)
                cb.setChecked(bool(perms.get(key)))
                cb.setEnabled(self.allow.isChecked())
                cb.toggled.connect(lambda on, i=d.get("id"), k=key: self.rc.server.set_perm(i, k, on))
                ph.addWidget(cb)
            ph.addStretch(1)
            col.addSpacing(4)
            col.addLayout(ph)
            h.addLayout(col, 1)
            rm = QPushButton(t("Kaldır"))
            rm.setProperty("variant", "danger")
            rm.setCursor(Qt.PointingHandCursor)
            rm.clicked.connect(lambda _=False, i=d.get("id"): self.rc.server.revoke(i))
            h.addWidget(rm)
            self.dev_box.addWidget(row)
        self.adjustSize()

    def done(self, r):
        self.timer.stop()
        try:
            self.rc.changed.disconnect(self._refresh)
        except (RuntimeError, TypeError):
            pass
        super().done(r)
