"""Oyuncu kafası pikselleri: skin'den yüz + şapka katmanı; yoksa baş harfli yer tutucu.
İndirme arka planda yapılır; hazır olunca HeadLoader.ready(uuid) yayınlanır."""
import threading

from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap

from core import skins
from core.players import account_type
from .theme import TOKENS

_FACES = {}          # uuid -> QImage 8x8 (None: yok)


def _face(path):
    img = QImage(path)
    if img.isNull() or img.width() < 64:
        return None
    face = img.copy(QRect(8, 8, 8, 8)).convertToFormat(QImage.Format_ARGB32)
    hat = img.copy(QRect(40, 8, 8, 8)).convertToFormat(QImage.Format_ARGB32)
    p = QPainter(face)
    p.drawImage(0, 0, hat)
    p.end()
    return face


def placeholder(name, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    hue = sum(map(ord, name or "?")) * 37 % 360
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor.fromHsl(hue, 90, 70))
    p.drawRoundedRect(0, 0, size, size, size * 0.18, size * 0.18)
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(size * 0.55))
    p.setFont(f)
    p.setPen(QColor(TOKENS["text"]))
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, (name or "?")[:1].upper())
    p.end()
    return pm


def pixmap(uuid, name, size, online=None):
    """Kafa (varsa) ya da yer tutucu. online True/False ise köşeye durum noktası çizer."""
    face = _FACES.get(uuid)
    if face is None and uuid not in _FACES:
        path = skins.cached(uuid)
        if path:
            face = _FACES[uuid] = _face(path)
    if face is not None:
        pm = QPixmap.fromImage(face.scaled(size, size, Qt.IgnoreAspectRatio, Qt.FastTransformation))
    else:
        pm = placeholder(name, size)
    if online is not None:
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r = max(5, size // 3)
        p.setPen(QColor(TOKENS["surface"]))
        p.setBrush(QColor(TOKENS["accent"] if online else TOKENS["text_muted"]))
        p.drawEllipse(size - r, size - r, r - 1, r - 1)
        p.end()
    return pm


class HeadLoader(QObject):
    ready = Signal(str)

    def __init__(self, enabled=lambda: True, parent=None):
        super().__init__(parent)
        self.enabled = enabled
        self._busy = set()

    def request(self, players):
        """[(uuid, name)] için eksik kafaları arka planda indirir."""
        if not self.enabled():
            return
        todo = [(u, n) for u, n in players if u and u not in self._busy and not skins.cached(u)]
        if not todo:
            return
        self._busy.update(u for u, _ in todo)

        def work():
            for u, n in todo:
                try:
                    if skins.skin_file(u, n, account_type(u)):
                        _FACES.pop(u, None)
                        self.ready.emit(u)
                finally:
                    self._busy.discard(u)
        threading.Thread(target=work, daemon=True).start()
