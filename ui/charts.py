"""Hafif grafik bileşenleri (QPainter). QtCharts'a gerek yok, exe büyümez."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from .theme import TOKENS

PAD_L, PAD_R, PAD_T, PAD_B = 34, 10, 10, 22


def _nice_max(v, integer=True):
    steps = (1, 2, 5,) if integer else (0.25, 0.5, 1, 2, 5,)
    for step in steps + (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000):
        if step * 4 >= v:
            return step * 4
    return v * 1.2


def _ticks(vmax, integer=True):
    m = _nice_max(vmax, integer)
    return m, [m * i / 4 for i in range(5)]


class _Base(QWidget):
    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self.color = QColor(color or TOKENS["accent"])
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        from .i18n import t
        self.empty_text = t("Veri yok")

    def _plot_rect(self):
        return QRectF(PAD_L, PAD_T, self.width() - PAD_L - PAD_R, self.height() - PAD_T - PAD_B)

    def _grid(self, p, r, ticks, vmax, fmt=lambda v: f"{v:g}"):
        grid = QColor(TOKENS["border"])
        muted = QColor(TOKENS["text_muted"])
        f = QFont(p.font())
        f.setPointSizeF(7.5)
        p.setFont(f)
        for t in ticks:
            y = r.bottom() - (t / vmax) * r.height() if vmax else r.bottom()
            p.setPen(QPen(grid, 1, Qt.SolidLine if t == 0 else Qt.DashLine))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 8, PAD_L - 6, 16), Qt.AlignRight | Qt.AlignVCenter, fmt(t))

    def _empty(self, p):
        p.setPen(QColor(TOKENS["text_muted"]))
        p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)


class LineChart(_Base):
    """points: [(x: float, y: float)]; x_label(x)->str; step=True merdiven çizgisi."""

    def __init__(self, color=None, step=False, y_fmt=None, parent=None):
        super().__init__(color, parent)
        self.points, self.step = [], step
        self.x_range = None
        self.x_label = lambda x: f"{x:g}"
        self.y_fmt = y_fmt or (lambda v: f"{v:g}")
        self.tip = None
        self.y_min_max = 0
        self.integer = True

    def set_data(self, points, x_range=None, x_label=None):
        self.points = points
        self.x_range = x_range
        if x_label:
            self.x_label = x_label
        self.update()

    def _map(self, r, x0, x1, vmax):
        def f(x, y):
            px = r.left() + ((x - x0) / (x1 - x0) if x1 > x0 else 1) * r.width()
            return QPointF(px, r.bottom() - (y / vmax) * r.height() if vmax else r.bottom())
        return f

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.points:
            self._empty(p)
            return
        r = self._plot_rect()
        x0, x1 = self.x_range or (self.points[0][0], self.points[-1][0])
        vmax, ticks = _ticks(max(max(y for _, y in self.points), self.y_min_max), self.integer)
        self._grid(p, r, ticks, vmax, self.y_fmt)
        m = self._map(r, x0, x1, vmax)

        # x etiketleri
        p.setPen(QColor(TOKENS["text_muted"]))
        for i in range(5):
            x = x0 + (x1 - x0) * i / 4
            px = r.left() + r.width() * i / 4
            align = Qt.AlignLeft if i == 0 else Qt.AlignRight if i == 4 else Qt.AlignHCenter
            rect = QRectF(px - (0 if i == 0 else 60 if i == 4 else 30), r.bottom() + 4, 60, 16)
            p.drawText(rect, align | Qt.AlignTop, self.x_label(x))

        path = QPainterPath()
        prev = None
        for x, y in self.points:
            pt = m(x, y)
            if prev is None:
                path.moveTo(pt)
            elif self.step:
                path.lineTo(QPointF(pt.x(), prev.y()))
                path.lineTo(pt)
            else:
                path.lineTo(pt)
            prev = pt
        if self.step and self.x_range and prev is not None:
            path.lineTo(QPointF(r.right(), prev.y()))

        fill = QPainterPath(path)
        end_x = path.currentPosition().x()
        fill.lineTo(QPointF(end_x, r.bottom()))
        fill.lineTo(QPointF(m(*self.points[0]).x(), r.bottom()))
        fill.closeSubpath()
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        c1 = QColor(self.color); c1.setAlpha(70)
        c2 = QColor(self.color); c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillPath(fill, g)
        p.setPen(QPen(self.color, 2))
        p.drawPath(path)
        if prev is not None:
            p.setBrush(self.color)
            p.drawEllipse(QPointF(end_x, prev.y()), 3, 3)

    def mouseMoveEvent(self, e):
        if not self.points:
            return
        r = self._plot_rect()
        x0, x1 = self.x_range or (self.points[0][0], self.points[-1][0])
        x = x0 + (e.position().x() - r.left()) / r.width() * (x1 - x0)
        best = None
        for px, py in self.points:
            if px <= x:
                best = (px, py)
        if best:
            QToolTip.showText(e.globalPosition().toPoint(), f"{self.x_label(x)}  ·  {self.y_fmt(best[1])}", self)


class BarChart(_Base):
    """labels: [str]; values: [float]; highlight: vurgulanacak indeks."""

    def __init__(self, color=None, parent=None):
        super().__init__(color, parent)
        self.labels, self.values, self.highlight = [], [], None
        self.label_every = 1
        self.tips = None

    def set_data(self, labels, values, highlight=None, label_every=1, tips=None):
        self.labels, self.values = labels, values
        self.highlight, self.label_every, self.tips = highlight, label_every, tips
        self.update()

    def _bars(self, r):
        n = len(self.values)
        slot = r.width() / n
        w = max(2.0, slot * 0.62)
        return slot, w

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.values or not any(self.values):
            self._grid(p, self._plot_rect(), [0], 1)
            self._empty(p)
            return
        r = self._plot_rect()
        vmax, ticks = _ticks(max(self.values))
        self._grid(p, r, ticks, vmax)
        slot, w = self._bars(r)
        dim = QColor(self.color); dim.setAlpha(110)
        p.setPen(Qt.NoPen)
        for i, v in enumerate(self.values):
            h = (v / vmax) * r.height()
            x = r.left() + i * slot + (slot - w) / 2
            p.setBrush(self.color if (self.highlight is None or i == self.highlight) else dim)
            p.drawRoundedRect(QRectF(x, r.bottom() - h, w, h), 3, 3)
        p.setPen(QColor(TOKENS["text_muted"]))
        for i, lab in enumerate(self.labels):
            if i % self.label_every == 0:
                x = r.left() + i * slot
                p.drawText(QRectF(x - 10, r.bottom() + 4, slot + 20, 16), Qt.AlignHCenter | Qt.AlignTop, lab)

    def mouseMoveEvent(self, e):
        if not self.values:
            return
        r = self._plot_rect()
        slot, _ = self._bars(r)
        i = int((e.position().x() - r.left()) // slot)
        if 0 <= i < len(self.values):
            t = self.tips[i] if self.tips else f"{self.labels[i]}: {self.values[i]:g}"
            QToolTip.showText(e.globalPosition().toPoint(), t, self)
