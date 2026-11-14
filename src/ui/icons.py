"""Arayüz ikonları: Lucide (ISC lisansı, ui/icons/LICENSE.txt) SVG'leri, tema rengine boyanarak.

    from .icons import icon
    btn.setIcon(icon("shield"))                  # metin rengi
    btn.setIcon(icon("play", "#ffffff", 16))     # belirli renk ve boyut

Tema değişince arayüz yeniden kurulduğu için renk, çağrıldığı andaki temadan alınır.
"""
import os

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from core import resource_dir
from .theme import TOKENS

_DIRS = (os.path.join(resource_dir(), "ui", "icons"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons"))
_svg_cache, _icon_cache = {}, {}


def _svg(name):
    if name not in _svg_cache:
        data = b""
        for d in _DIRS:
            p = os.path.join(d, f"{name}.svg")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    data = f.read()
                break
        _svg_cache[name] = data
    return _svg_cache[name]


def pixmap(name, color=None, size=18, dpr=2.0):
    """SVG'yi verilen renkte çizer (yüksek DPI ekranlar için 2x)."""
    color = color or TOKENS.get("text", "#e6e6e6")
    data = _svg(name).replace(b"currentColor", QColor(color).name().encode())
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    if data:
        r = QSvgRenderer(QByteArray(data))
        p = QPainter(px)
        r.render(p, QRectF(0, 0, px.width(), px.height()))
        p.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name, color=None, size=18):
    """Tema rengiyle boyanmış QIcon. Devre dışı hali soluk renkte."""
    color = color or TOKENS.get("text", "#e6e6e6")
    key = (name, color, size, TOKENS.get("text_muted"))
    if key not in _icon_cache:
        ic = QIcon()
        ic.addPixmap(pixmap(name, color, size), QIcon.Normal)
        ic.addPixmap(pixmap(name, TOKENS.get("text_muted", "#888"), size), QIcon.Disabled)
        _icon_cache[key] = ic
    return _icon_cache[key]


def dot(color, size=10):
    """Durum noktası (çevrimiçi/çalışıyor) — yazı tipine bağlı ● yerine çizilmiş daire."""
    dpr = 2.0
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    m = size * dpr * 0.15
    p.drawEllipse(QRectF(m, m, size * dpr - 2 * m, size * dpr - 2 * m))
    p.end()
    px.setDevicePixelRatio(dpr)
    return QIcon(px)


def img_tag(name, color=None, size=12):
    """Zengin metinli QLabel'lar için <img> etiketi (ikon geçici klasöre PNG olarak yazılır)."""
    import hashlib
    import tempfile
    color = QColor(color or TOKENS.get("text", "#e6e6e6")).name()
    folder = os.path.join(tempfile.gettempdir(), "spypaper-icons")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}-{hashlib.md5(color.encode()).hexdigest()[:8]}-{size}.png")
    if not os.path.exists(path):
        pixmap(name, color, size).save(path)
    return f'<img src="{path}" width="{size}" height="{size}" style="vertical-align:middle">'
