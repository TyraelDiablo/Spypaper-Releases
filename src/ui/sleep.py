"""Uyku modu ve kapanış ekranı.

Uyku modu: Spypaper'ın üstüne koyu bir kilit katmanı gelir; sunucular çalışmaya devam eder. Katmanda saat ve
sunucuların durumu (çalışıyor mu, kaç oyuncu, TPS) görünür; panele dönmek için PIN gerekir. Uyku açıkken
klavye kısayolları ve pencereyi kapatma da PIN ister. PIN Spypaper ayarlarında (sleep_pin_hash) tutulur; ilk
uykuda belirlenir.

Kapanış ekranı: "Have fun with your Minecraft server" yazar; "Have fun with your" kaybolur, "Minecraft server"
parlar, sonra o da solar ve Spypaper tamamen kapanır. Sunucular bu sırada düzgünce durdurulur; hepsi durmadan
son solma başlamaz.
"""
import time
from datetime import datetime

from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPropertyAnimation, QRectF,
    QSequentialAnimationGroup, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget

from . import icons
from .i18n import t
from .theme import TOKENS


def _prop(name):
    def get(self):
        return getattr(self, name)

    def set_(self, v):
        setattr(self, name, v)
        self.update()
    return Property(float, get, set_)


def _anim(obj, prop, a, b, ms, curve=QEasingCurve.OutCubic):
    x = QPropertyAnimation(obj, prop)
    x.setStartValue(a)
    x.setEndValue(b)
    x.setDuration(ms)
    x.setEasingCurve(curve)
    return x


class _Follow(QObject):
    """Katmanı pencereyle birlikte boyutlandırır."""

    def __init__(self, overlay, win):
        super().__init__(overlay)
        self.o, self.w = overlay, win
        win.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self.o.setGeometry(self.w.rect())
        return False


# ============================================================== uyku
class SleepOverlay(QWidget):
    woke = Signal()

    def __init__(self, win, rows_fn):
        super().__init__(win)
        self.win, self.rows_fn = win, rows_fn
        self.rows = []
        self._op = 0.0
        self.setGeometry(win.rect())
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        _Follow(self, win)
        self.logo = icons.logo(56)
        self.timer = QTimer(self, interval=2000, timeout=self._refresh)
        self._refresh()
        self.timer.start()
        self.raise_()
        self.show()
        self.setFocus()
        from . import motion
        if motion.REDUCED:
            self._op = 1.0
        else:
            self._a = _anim(self, b"op", 0.0, 1.0, 380)
            self._a.start()

    op = _prop("_op")

    def _refresh(self):
        try:
            self.rows = self.rows_fn()
        except Exception:
            self.rows = []
        self.update()

    def mousePressEvent(self, _e):
        self.woke.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space, Qt.Key_Escape):
            self.woke.emit()

    def close_overlay(self):
        self.timer.stop()
        a = _anim(self, b"op", self._op, 0.0, 260)
        a.finished.connect(self.deleteLater)
        a.start(QPropertyAnimation.DeleteWhenStopped)
        self._out = a

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setOpacity(self._op)
        bg = QColor(TOKENS["bg"]).darker(135)
        p.fillRect(self.rect(), bg)
        w, h = self.width(), self.height()
        top = max(40, h * 0.16)
        # saat
        f = QFont(self.font())
        f.setPixelSize(max(56, min(110, int(w / 10))))
        f.setWeight(QFont.Light)
        p.setFont(f)
        p.setPen(QColor(TOKENS["text"]))
        p.drawText(QRectF(0, top, w, f.pixelSize() * 1.3), Qt.AlignCenter, datetime.now().strftime("%H:%M"))
        y = top + f.pixelSize() * 1.35
        g = QFont(self.font())
        g.setPixelSize(15)
        p.setFont(g)
        p.setPen(QColor(TOKENS["text_muted"]))
        p.drawText(QRectF(0, y, w, 24), Qt.AlignCenter, t("Uyku modu · Sunucular çalışmaya devam ediyor"))
        y += 52
        # sunucular
        rw = min(560, w - 48)
        x0 = (w - rw) / 2
        name_f = QFont(self.font())
        name_f.setPixelSize(15)
        name_f.setWeight(QFont.DemiBold)
        small = QFont(self.font())
        small.setPixelSize(13)
        for r in self.rows[:8]:
            box = QRectF(x0, y, rw, 52)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(TOKENS["surface"]))
            p.drawRoundedRect(box, 10, 10)
            on = r.get("running")
            p.setBrush(QColor(TOKENS["accent"] if on else TOKENS["text_muted"]))
            p.drawEllipse(QRectF(x0 + 16, y + 21, 10, 10))
            p.setFont(name_f)
            p.setPen(QColor(TOKENS["text"]))
            p.drawText(QRectF(x0 + 36, y, rw * 0.5, 52), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetricsF(name_f).elidedText(r.get("name", ""), Qt.ElideRight, rw * 0.5))
            p.setFont(small)
            p.setPen(QColor(TOKENS["text_muted"]))
            p.drawText(QRectF(x0, y, rw - 16, 52), Qt.AlignVCenter | Qt.AlignRight, r.get("detail", ""))
            y += 60
        if not self.rows:
            p.drawText(QRectF(0, y, w, 24), Qt.AlignCenter, t("Sunucu yok"))
        # ipucu
        p.setFont(g)
        p.setPen(QColor(TOKENS["text_muted"]))
        hint = t("Panele dönmek için tıkla (PIN gerekir)")
        p.drawText(QRectF(0, h - 64, w, 24), Qt.AlignCenter, hint)
        lp = self.logo
        lw = lp.width() / max(lp.devicePixelRatio(), 1)
        p.setOpacity(self._op * 0.5)
        p.drawPixmap(int(w / 2 - lw / 2), int(h - 64 - lw - 12), lp)
        p.end()


class ShortcutBlocker(QObject):
    """Uyku açıkken pencerenin kısayollarını yutar (PIN diyaloğu dışında)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Shortcut, QEvent.ShortcutOverride):
            w = obj if isinstance(obj, QWidget) else None
            if w is not None and w.window() is self.win:
                return True
        return False


# ============================================================== kapanış
class OutroOverlay(QWidget):
    """"Have fun with your Minecraft server" kapanış animasyonu. finished_all: son solma bitince."""
    finished_all = Signal()
    LEAD = "Have fun with your "
    TAIL = "Minecraft server"

    def __init__(self, win, ready_fn):
        super().__init__(win)
        self.win, self.ready_fn = win, ready_fn
        self._bg = self._lead = self._tail = self._glow = self._shift = 0.0
        self._all = 1.0
        self.status = ""
        self.setGeometry(win.rect())
        _Follow(self, win)
        self.raise_()
        self.show()
        seq = QSequentialAnimationGroup(self)
        intro = QParallelAnimationGroup()
        intro.addAnimation(_anim(self, b"bg", 0.0, 1.0, 350))
        intro.addAnimation(_anim(self, b"lead", 0.0, 1.0, 600))
        intro.addAnimation(_anim(self, b"tail", 0.0, 1.0, 600))
        seq.addAnimation(intro)
        seq.addPause(650)
        seq.addAnimation(_anim(self, b"lead", 1.0, 0.0, 450, QEasingCurve.InOutCubic))   # önce baş kısım kaybolur
        mid = QParallelAnimationGroup()                                                    # sonra kuyruk ortalanıp parlar
        mid.addAnimation(_anim(self, b"shift", 0.0, 1.0, 650, QEasingCurve.InOutCubic))
        mid.addAnimation(_anim(self, b"glow", 0.0, 1.0, 750, QEasingCurve.OutQuad))
        seq.addAnimation(mid)
        seq.addPause(500)
        self.seq = seq
        seq.finished.connect(self._wait_ready)
        seq.start()

    bg = _prop("_bg")
    lead = _prop("_lead")
    tail = _prop("_tail")
    glow = _prop("_glow")
    shift = _prop("_shift")
    whole = _prop("_all")

    def _wait_ready(self):
        self._t0 = time.time()
        self._poll = QTimer(self, interval=150, timeout=self._check)
        self._poll.start()
        self._check()

    def _check(self):
        if not self.ready_fn():
            if time.time() - self._t0 > 0.8:
                self.status = t("Sunucular kapatılıyor…")
                self.update()
            return
        self._poll.stop()
        self.status = ""
        out = _anim(self, b"whole", 1.0, 0.0, 550, QEasingCurve.InOutCubic)
        out.finished.connect(self.finished_all.emit)
        out.start(QPropertyAnimation.DeleteWhenStopped)
        self._out = out

    def mousePressEvent(self, e):
        e.accept()                                          # arkadaki panele tıklanmasın

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        p.setOpacity(self._bg)                              # arka plan opak kalır; son solmada yalnızca yazı kaybolur
        p.fillRect(self.rect(), QColor(TOKENS["bg"]))
        f = QFont(self.font())
        f.setPixelSize(max(28, min(56, int(w / 22))))
        f.setWeight(QFont.DemiBold)
        fm = QFontMetricsF(f)
        lw, tw = fm.horizontalAdvance(self.LEAD), fm.horizontalAdvance(self.TAIL)
        x_full = (w - lw - tw) / 2                          # tüm cümle ortada
        x_tail = x_full + lw + ((w - tw) / 2 - (x_full + lw)) * self._shift   # kuyruk ortaya kayar
        y = h / 2 - fm.height() / 2
        p.setFont(f)
        if self._lead > 0:
            p.setOpacity(self._lead * self._all)
            p.setPen(QColor(TOKENS["text_muted"]))
            p.drawText(QRectF(x_full, y, lw + 4, fm.height()), Qt.AlignLeft | Qt.AlignVCenter, self.LEAD)
        acc = QColor(TOKENS["accent"])
        if self._glow > 0:                                  # parlama: yazının çevresinde yumuşak hale
            for i, (r, a) in enumerate(((10, 0.10), (6, 0.16), (3, 0.24))):
                p.setOpacity(self._glow * a * self._all)
                p.setPen(acc)
                for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r), (-r * .7, -r * .7), (r * .7, r * .7),
                               (-r * .7, r * .7), (r * .7, -r * .7)):
                    p.drawText(QRectF(x_tail + dx, y + dy, tw + 4, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                               self.TAIL)
        p.setOpacity(self._tail * self._all)
        c = QColor(TOKENS["text"])
        mix = self._glow
        c = QColor(int(c.red() + (acc.red() - c.red()) * mix), int(c.green() + (acc.green() - c.green()) * mix),
                   int(c.blue() + (acc.blue() - c.blue()) * mix))
        p.setPen(c)
        p.drawText(QRectF(x_tail, y, tw + 4, fm.height()), Qt.AlignLeft | Qt.AlignVCenter, self.TAIL)
        if self.status:
            g = QFont(self.font())
            g.setPixelSize(14)
            p.setFont(g)
            p.setOpacity(0.8 * self._all)
            p.setPen(QColor(TOKENS["text_muted"]))
            p.drawText(QRectF(0, y + fm.height() + 24, w, 24), Qt.AlignCenter, self.status)
        p.end()
