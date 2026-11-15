"""Kaydırırken ayarların kazara değişmesini engeller.

Fare tekerleği, imlecin altındaki açılır liste / sayı kutusu / kaydırıcıya giderse o değeri değiştirir
ve sayfa kaymaz. Bu süzgeç, odakta olmayan böyle bir denetime gelen tekerlek olayını yutmayıp
bulunduğu kaydırma alanına iletir: sayfa kayar, değer değişmez. Denetime tıklayıp odaklayınca
tekerlek yine çalışır.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QScrollBar


class WheelGuard(QObject):
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Polish and isinstance(obj, (QComboBox, QAbstractSpinBox, QAbstractSlider)) \
                and not isinstance(obj, QScrollBar) and obj.focusPolicy() == Qt.WheelFocus:
            obj.setFocusPolicy(Qt.StrongFocus)    # tekerlek odak vermesin (yoksa süzgeç işe yaramaz)
            return False
        if ev.type() == QEvent.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox, QAbstractSlider)) \
                and not isinstance(obj, QScrollBar) and not obj.hasFocus():
            if isinstance(obj, QComboBox) and obj.view().isVisible():
                return False                       # açık listede kaydırma normal çalışsın
            p = obj.parentWidget()
            while p is not None and not isinstance(p, QAbstractScrollArea):
                p = p.parentWidget()
            if p is not None:
                QApplication.sendEvent(p.viewport(), ev)
            return True
        return False


def install(app):
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    app._wheel_guard = guard
    return guard


def no_wheel_focus(widget):
    """Tekerlekle odaklanmasın (Qt.WheelFocus yerine StrongFocus)."""
    widget.setFocusPolicy(Qt.StrongFocus)
