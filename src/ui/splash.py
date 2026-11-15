"""Açılış ekranı: logo + dönen halka + "Güncellemeler denetleniyor…".

Güncelleme denetimi arka planda yapılır; en fazla birkaç saniye beklenir, internet yoksa ya da
GitHub'a ulaşılamazsa uygulama sessizce açılır. Yeni sürüm varsa sorulur; kabul edilirse exe
indirilip değiştirilir ve Spypaper yeniden başlar.
"""
import re
import threading
import time
import webbrowser

from PySide6.QtCore import QEventLoop, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QVBoxLayout, QWidget

from core import appupdate
from core.updater import VERSION
from . import icons
from .i18n import t
from .theme import TOKENS

CHECK_TIMEOUT = 6        # sn
MIN_SHOW = 0.9           # animasyon bir an görünüp kaybolmasın


class Spinner(QWidget):
    def __init__(self, animate=True):
        super().__init__()
        self.setFixedSize(34, 34)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)
        if animate:
            self.timer.start(16)

    def _step(self):
        self.angle = (self.angle + 6) % 360
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, self.width() - 6, self.height() - 6)
        p.setPen(QPen(QColor(TOKENS["surface_3"]), 3.5))
        p.drawEllipse(r)
        pen = QPen(QColor(TOKENS["accent"]), 3.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, int(-self.angle * 16), int(100 * 16))
        p.end()


class Splash(QWidget):
    checked = Signal(object, object)         # bilgi, hata
    progress = Signal(int, int)
    downloaded = Signal(str, object)         # yol, hata

    def __init__(self, animate=True):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(380, 300)
        box = QWidget(self)
        box.setObjectName("SplashBox")
        box.setGeometry(0, 0, 380, 300)
        box.setStyleSheet(f"#SplashBox {{ background:{TOKENS['surface']}; border:1px solid {TOKENS['border']};"
                          f" border-radius:18px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(28, 30, 28, 24)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignHCenter)
        logo = QLabel()
        logo.setPixmap(icons.logo(76))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        name = QLabel("Spypaper")
        name.setAlignment(Qt.AlignCenter)
        name.setStyleSheet(f"color:{TOKENS['text']}; font-size:22px; font-weight:700; background:transparent;")
        v.addWidget(name)
        ver = QLabel(f"v{VERSION}")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet(f"color:{TOKENS['text_muted']}; background:transparent;")
        v.addWidget(ver)
        v.addStretch(1)
        self.spin = Spinner(animate)
        v.addWidget(self.spin, 0, Qt.AlignHCenter)
        self.text = QLabel(t("Güncellemeler denetleniyor…"))
        self.text.setAlignment(Qt.AlignCenter)
        self.text.setWordWrap(True)
        self.text.setStyleSheet(f"color:{TOKENS['text_muted']}; background:transparent;")
        v.addWidget(self.text)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.hide()
        v.addWidget(self.bar)
        self.progress.connect(self._on_progress)
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def _on_progress(self, got, total):
        self.bar.show()
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(got)
        if total:
            self.text.setText(t("İndiriliyor… %{n}", n=int(got * 100 / total)))

    def wait(self, signal, timeout):
        """signal gelene ya da süre dolana kadar arayüzü canlı tutarak bekler. Sonucu döndürür."""
        box = {}
        loop = QEventLoop()

        def done(*args):
            box["r"] = args
            loop.quit()
        signal.connect(done)
        if timeout:
            QTimer.singleShot(int(timeout * 1000), loop.quit)
        loop.exec()
        try:
            signal.disconnect(done)
        except (RuntimeError, TypeError):
            pass
        return box.get("r")


def run(settings):
    """Açılışta güncelleme denetimi. Uygulama yeniden başlatılacaksa True döner (çağıran çıkmalı)."""
    appupdate.cleanup()
    if not settings.get("check_updates"):
        return False
    splash = Splash(animate=not settings.get("reduce_motion"))
    splash.show()
    QApplication.processEvents()
    started = time.time()

    def work():
        try:
            splash.checked.emit(appupdate.check(timeout=CHECK_TIMEOUT), None)
        except Exception as e:
            splash.checked.emit(None, e)
    threading.Thread(target=work, daemon=True).start()
    res = splash.wait(splash.checked, CHECK_TIMEOUT + 1)
    left = MIN_SHOW - (time.time() - started)
    if left > 0:
        loop = QEventLoop()
        QTimer.singleShot(int(left * 1000), loop.quit)
        loop.exec()
    info, err = res if res else (None, None)
    if err is not None:
        print(f"[güncelleme] {err}")
    if not info or not appupdate.is_newer(info["version"]) or info["version"] == settings.get("skip_version"):
        splash.close()
        return False
    restart = offer(None, settings, info, splash)
    splash.close()
    return restart


def offer(parent, settings, info, splash=None):
    """Yeni sürümü sorar; kabul edilirse indirip kurar. Yeniden başlatılacaksa True."""
    from .msgbox import choose
    notes = info.get("notes", "").replace("\r", "")
    notes = re.sub(r"^#{1,6}\s*", "", notes, flags=re.M)                  # Markdown başlıkları
    notes = re.sub(r"\*\*(.+?)\*\*|`(.+?)`", lambda m: m.group(1) or m.group(2), notes)
    notes = re.sub(r"^\s*[-*]\s+", "• ", notes, flags=re.M)
    notes = re.sub(r"^-{3,}\s*$", "", notes, flags=re.M)
    notes = re.sub(r"\n{3,}", "\n\n", notes).strip()
    text = t("Spypaper {new} yayınlandı (şu an {cur}).", new=info["version"], cur=VERSION)
    if notes:
        text += "\n\n" + (notes if len(notes) < 900 else notes[:900] + "…")
    if splash:
        splash.hide()
    pick = choose(parent, "info", t("Güncelleme var"), text,
                  [(t("Bu sürümü atla"), "ghost"), (t("Sonra"), "ghost"), (t("Şimdi Güncelle"), "primary")],
                  default=2, cancel=1)
    if pick == 0:
        settings.set("skip_version", info["version"])
        return False
    if pick != 2:
        return False
    if not appupdate.frozen() or not info.get("url"):
        webbrowser.open(info.get("page") or appupdate.PAGE)
        return False
    own = splash is None
    if own:
        splash = Splash(animate=not settings.get("reduce_motion"))
    splash.text.setText(t("İndiriliyor…"))
    splash.show()

    def work():
        try:
            splash.downloaded.emit(appupdate.download(info, lambda a, b: splash.progress.emit(a, b)), None)
        except Exception as e:
            splash.downloaded.emit("", e)
    threading.Thread(target=work, daemon=True).start()
    res = splash.wait(splash.downloaded, 0) or ("", Exception("?"))
    path, err = res
    if err is None:
        splash.text.setText(t("Kuruluyor…"))
        QApplication.processEvents()
        try:
            appupdate.apply_and_restart(path)
            return True
        except Exception as e:
            err = e
    splash.hide()
    from .msgbox import error
    msg = t(err.template, **err.kw) if hasattr(err, "template") else str(err)
    error(parent, t("Güncelleme"), msg)
    if own:
        splash.close()
    return False
