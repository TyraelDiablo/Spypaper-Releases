"""Karşılama ekranı: güncelleme denetiminden sonra, ana pencerenin üstünde kısa bir açılış.

Büyük "Spypaper" yazısı solarak ve hafifçe yükselerek gelir, altında ince bir vurgu çizgisi uzar,
ardından günün saatine göre selamlama ("İyi günler") belirir; sonra katman solarak kaybolur ve
sunucular görünür. Tıklama ya da bir tuş atlatır. "Animasyonları azalt" açıkken ya da
"Açılış ekranını göster" kapalıyken hiç gösterilmez. Çizim QPainter ile yapılır (iç içe
QGraphicsEffect sorunları olmasın).
"""
from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QParallelAnimationGroup, QPropertyAnimation, QRectF,
    QSequentialAnimationGroup, Qt,
)
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from . import icons
from .theme import TOKENS


class IntroOverlay(QWidget):
    def __init__(self, window, greeting):
        super().__init__(window)
        self.win = window
        self.greeting = greeting
        self._t = self._g = self._line = 0.0
        self._all = 1.0
        self.logo = icons.logo(88)
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setGeometry(window.rect())
        window.installEventFilter(self)
        self.raise_()
        self.show()
        self.setFocus()
        self.anim = self._build()
        self.anim.finished.connect(self._done)
        self.anim.start()

    # --- canlandırılan değerler ---
    def _prop(name):
        def get(self):
            return getattr(self, name)

        def set_(self, v):
            setattr(self, name, v)
            self.update()
        return Property(float, get, set_)
    title = _prop("_t")
    greet = _prop("_g")
    line = _prop("_line")
    whole = _prop("_all")

    def _a(self, prop, start, end, ms, curve=QEasingCurve.OutCubic):
        a = QPropertyAnimation(self, prop)
        a.setStartValue(start)
        a.setEndValue(end)
        a.setDuration(ms)
        a.setEasingCurve(curve)
        return a

    def _build(self):
        seq = QSequentialAnimationGroup(self)
        seq.addPause(120)
        intro = QParallelAnimationGroup()
        intro.addAnimation(self._a(b"title", 0.0, 1.0, 650))
        line = QSequentialAnimationGroup()
        line.addPause(250)
        line.addAnimation(self._a(b"line", 0.0, 1.0, 550, QEasingCurve.InOutCubic))
        intro.addAnimation(line)
        seq.addAnimation(intro)
        seq.addAnimation(self._a(b"greet", 0.0, 1.0, 520))
        seq.addPause(750)
        seq.addAnimation(self._a(b"whole", 1.0, 0.0, 450, QEasingCurve.InOutCubic))
        return seq

    # --- atlama ---
    def skip(self):
        if self.anim.state() != QSequentialAnimationGroup.Running or self._all < 1.0:
            return
        self.anim.stop()
        self._t = self._g = self._line = 1.0
        out = self._a(b"whole", self._all, 0.0, 220, QEasingCurve.OutCubic)
        out.finished.connect(self._done)
        out.start(QPropertyAnimation.DeleteWhenStopped)
        self._out = out

    def mousePressEvent(self, _e):
        self.skip()

    def keyPressEvent(self, _e):
        self.skip()

    def eventFilter(self, obj, ev):
        if obj is self.win and ev.type() == QEvent.Resize:
            self.setGeometry(self.win.rect())
        return False

    def _done(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.win.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    # --- çizim ---
    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setOpacity(self._all)
        p.fillRect(self.rect(), QColor(TOKENS["bg"]))
        w, h = self.width(), self.height()
        cy = h / 2 - 20
        rise = (1.0 - self._t) * 18                         # yazı aşağıdan hafifçe yükselir

        # logo + başlık
        p.setOpacity(self._all * self._t)
        lp = self.logo
        lw = lp.width() / max(lp.devicePixelRatio(), 1)
        p.drawPixmap(int(w / 2 - lw / 2), int(cy - 150 + rise), lp)
        f = QFont(self.font())
        f.setPixelSize(max(48, min(96, int(w / 11))))
        f.setWeight(QFont.Black)
        f.setLetterSpacing(QFont.PercentageSpacing, 102)
        p.setFont(f)
        p.setPen(QColor(TOKENS["text"]))
        title_r = QRectF(0, cy - 50 + rise, w, 100)
        p.drawText(title_r, Qt.AlignCenter, "Spypaper")

        # vurgu çizgisi (ortadan iki yana uzar)
        p.setOpacity(self._all)
        lw2 = 220 * self._line
        if lw2 > 1:
            c = QColor(TOKENS["accent"])
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(w / 2 - lw2 / 2, cy + 74, lw2, 4), 2, 2)

        # selamlama
        g = QFont(self.font())
        g.setPixelSize(max(18, min(28, int(w / 40))))
        g.setWeight(QFont.Medium)
        p.setFont(g)
        p.setOpacity(self._all * self._g)
        p.setPen(QColor(TOKENS["text_muted"]))
        p.drawText(QRectF(0, cy + 94 + (1.0 - self._g) * 12, w, 50), Qt.AlignCenter, self.greeting)
        p.end()


def play(window, settings, greeting):
    """Ayarlar izin veriyorsa karşılamayı oynatır; katmanı döndürür (ya da None)."""
    if settings.get("reduce_motion") or not settings.get("show_intro"):
        return None
    return IntroOverlay(window, greeting)
