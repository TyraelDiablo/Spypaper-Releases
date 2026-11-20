"""Arayüz animasyonları: sayfa geçişi (solarak + hafif kayarak gelir) ve seçili sekmenin altında /
yanında kayan gösterge çubuğu. "Animasyonları azalt" açıkken hepsi anında olur."""
from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRect, Qt, QTimer,
)
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect

from .theme import TOKENS

REDUCED = False          # MainWindow ayarlardan günceller
PAGE_MS = 260
BAR_MS = 240


def fade_in(widget, dy=10, ms=PAGE_MS):
    """Yeni gösterilen sayfayı solarak ve aşağıdan hafifçe kayarak getirir."""
    if REDUCED or widget is None or getattr(widget, "no_fade", False):
        return
    inner = getattr(widget, "stack", None)            # sunucu paneli: içindeki sayfa harita ise solma yok
    if inner is not None and hasattr(inner, "currentWidget") and getattr(inner.currentWidget(), "no_fade", False):
        return
    eff = QGraphicsOpacityEffect(widget)
    eff.setOpacity(0.0)
    widget.setGraphicsEffect(eff)
    end = widget.pos()
    grp = QParallelAnimationGroup(widget)
    a = QPropertyAnimation(eff, b"opacity", grp)
    a.setDuration(ms)
    a.setStartValue(0.0)
    a.setEndValue(1.0)
    a.setEasingCurve(QEasingCurve.OutCubic)
    grp.addAnimation(a)
    if dy:
        b = QPropertyAnimation(widget, b"pos", grp)
        b.setDuration(ms)
        b.setStartValue(end + QPoint(0, dy))
        b.setEndValue(end)
        b.setEasingCurve(QEasingCurve.OutCubic)
        grp.addAnimation(b)

    def done():
        widget.setGraphicsEffect(None)                 # efekt kalırsa çizim yavaşlar
        widget.move(end)
    grp.finished.connect(done)
    grp.start(QParallelAnimationGroup.DeleteWhenStopped)


TAB_MS = 220


def auto_fade(stack, dy=6, ms=TAB_MS):
    """Sekme/alt sayfa değişince (QStackedWidget) yeni sayfa hafifçe solarak gelir."""
    stack.currentChanged.connect(lambda _i: fade_in(stack.currentWidget(), dy=dy, ms=ms))
    return stack


def soft(widget, ms=TAB_MS):
    """Yerinde değişen içerik (süzgeç, görünüm) için kaymasız kısa solma."""
    fade_in(widget, dy=0, ms=ms)


def stagger(widgets, step=35, dy=12, ms=PAGE_MS, max_delay=420):
    """Liste/ızgara öğeleri sırayla (kademeli) solarak gelir."""
    if REDUCED:
        return
    for i, w in enumerate(widgets):
        if w is None:
            continue
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)
        QTimer.singleShot(min(i * step, max_delay), lambda w=w: fade_in(w, dy=dy, ms=ms))


def fade_opacity(widget, start, end, ms=PAGE_MS, done=None):
    """Bir widget'ın saydamlığını canlandırır (ör. çekmecenin arkasındaki karartma)."""
    if REDUCED:
        widget.setGraphicsEffect(None)
        if done:
            done()
        return None
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    eff.setOpacity(start)
    a = QPropertyAnimation(eff, b"opacity", widget)
    a.setDuration(ms)
    a.setStartValue(start)
    a.setEndValue(end)
    a.setEasingCurve(QEasingCurve.OutCubic)
    if done:
        a.finished.connect(done)
    a.start(QPropertyAnimation.DeleteWhenStopped)
    return a


class DialogFader(QObject):
    """Uygulamadaki her pencere/diyalog açılırken kısa bir solma ile gelir (uygulama genelinde olay süzgeci)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and not REDUCED and obj.isWindow() and not getattr(obj, "_faded", False):
            from PySide6.QtWidgets import QDialog, QMessageBox
            if isinstance(obj, (QDialog, QMessageBox)):
                obj._faded = True
                obj.setWindowOpacity(0.0)
                a = QPropertyAnimation(obj, b"windowOpacity", obj)
                a.setDuration(180)
                a.setStartValue(0.0)
                a.setEndValue(1.0)
                a.setEasingCurve(QEasingCurve.OutCubic)
                a.start(QPropertyAnimation.DeleteWhenStopped)
        return False


class SlideBar(QObject):
    """Bir düğme grubunda seçili düğmeyi izleyen kayan çubuk.

    mode="left":  düğmenin solunda dikey çubuk (kenar çubuğu)
    mode="under": düğmenin altında yatay çubuk (sekmeler)
    """

    def __init__(self, group, container, mode="under", thickness=3):
        super().__init__(container)
        self.group, self.container, self.mode, self.th = group, container, mode, thickness
        self.bar = QFrame(container)
        self.bar.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.bar.setStyleSheet(f"background:{TOKENS['accent']}; border-radius:{thickness // 2 + 1}px;")
        self.bar.hide()
        self.anim = QPropertyAnimation(self.bar, b"geometry", self)
        self.anim.setDuration(BAR_MS)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        group.buttonToggled.connect(lambda b, on: on and self.move(b))
        container.installEventFilter(self)
        for b in group.buttons():
            b.installEventFilter(self)
        QTimer.singleShot(0, lambda: self.move(group.checkedButton(), animate=False))

    def _target(self, b):
        g = b.geometry()
        p = b.parentWidget().mapTo(self.container, g.topLeft()) if b.parentWidget() is not self.container else g.topLeft()
        if self.mode == "left":
            pad = max(6, g.height() // 4)
            return QRect(p.x() + 2, p.y() + pad, self.th, g.height() - 2 * pad)
        pad = max(8, g.width() // 5)
        return QRect(p.x() + pad, p.y() + g.height() - self.th - 1, g.width() - 2 * pad, self.th)

    def move(self, b, animate=True):
        if b is None or not b.isVisible():
            self.bar.hide()
            return
        target = self._target(b)
        self.bar.show()
        self.bar.raise_()
        if REDUCED or not animate or not self.bar.geometry().isValid() or self.bar.geometry().isEmpty():
            self.anim.stop()
            self.bar.setGeometry(target)
            return
        self.anim.stop()
        self.anim.setStartValue(self.bar.geometry())
        self.anim.setEndValue(target)
        self.anim.start()

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Resize, QEvent.Move, QEvent.Show, QEvent.LayoutRequest):
            b = self.group.checkedButton()
            if b is not None and self.anim.state() != QPropertyAnimation.Running:
                QTimer.singleShot(0, lambda: self.move(b, animate=False))
        return False
