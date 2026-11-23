"""Doku tasarım ekranı: piksel piksel renk boyama (kalem, silgi, kova, damlalık, ayna), hazır şablonlar ve önizleme.

Eşya (alet/yiyecek/plak) için 16×16; tablo için genişlik×16 × yükseklik×16; HUD için parçanın boyutu.
Eşyalarda "Blok (küp)" görünümü seçilirse doku 16×16×16 bir küpün altı yüzüne de uygulanır.
"""
from PySide6.QtCore import QPointF, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPolygonF, QShortcut, QTransform
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QDialog, QGridLayout, QHBoxLayout,
                               QPushButton, QVBoxLayout, QWidget)

from core import N_, texture_templates as TT
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row

PALETTE = ["#000000", "#3b3b3b", "#7f7f7f", "#c6c6c6", "#ffffff", "#5b3a1e", "#7a5230", "#c98a3c",
           "#e0b030", "#ffe066", "#f08a24", "#d9332b", "#a8483a", "#e0457b", "#c86bff", "#6b3fb5",
           "#2f4fd8", "#5fd7e6", "#2fa3a3", "#3fa34d", "#7ed957", "#1f5d2b", "#e8e0d0", "#1d1d22"]

TOOLS = [("pen", N_("Kalem"), "B"), ("eraser", N_("Silgi"), "E"), ("fill", N_("Kova"), "G"),
         ("pick", N_("Damlalık"), "I")]


class Canvas(QWidget):
    changed = Signal()
    picked = Signal(QColor)

    def __init__(self, w, h, parent=None):
        super().__init__(parent)
        self.w, self.h = w, h
        self.px = [[None] * w for _ in range(h)]       # QColor | None
        self.color = QColor("#d9332b")
        self.tool = "pen"
        self.mirror = False
        self.grid = True
        self.undo, self.redo = [], []
        self._stroke = False
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self.hover = None

    # --- veri ---
    def snapshot(self):
        return [r[:] for r in self.px]

    def push_undo(self):
        self.undo.append(self.snapshot())
        self.undo = self.undo[-60:]
        self.redo.clear()

    def do_undo(self):
        if self.undo:
            self.redo.append(self.snapshot())
            self.px = self.undo.pop()
            self.update()
            self.changed.emit()

    def do_redo(self):
        if self.redo:
            self.undo.append(self.snapshot())
            self.px = self.redo.pop()
            self.update()
            self.changed.emit()

    def set_image(self, img):
        img = img.convertToFormat(QImage.Format_ARGB32)
        if img.width() != self.w or img.height() != self.h:
            img = img.scaled(self.w, self.h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        self.px = [[(QColor.fromRgba(img.pixel(x, y)) if QColor.fromRgba(img.pixel(x, y)).alpha() > 0 else None)
                    for x in range(self.w)] for y in range(self.h)]
        self.update()
        self.changed.emit()

    def image(self):
        img = QImage(self.w, self.h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        for y in range(self.h):
            for x in range(self.w):
                c = self.px[y][x]
                if c is not None:
                    img.setPixelColor(x, y, c)
        return img

    def stamp(self, grid16, ox=0, oy=0):
        """16×16 şablonu tuvale basar (tablo gibi büyük tuvallerde ortalanır)."""
        self.push_undo()
        for y in range(16):
            for x in range(16):
                c = grid16[y][x]
                if c and 0 <= oy + y < self.h and 0 <= ox + x < self.w:     # boş pikseller alttakini bozmaz
                    self.px[oy + y][ox + x] = QColor(c)
        self.update()
        self.changed.emit()

    def clear(self):
        self.push_undo()
        self.px = [[None] * self.w for _ in range(self.h)]
        self.update()
        self.changed.emit()

    def fill_all(self, color):
        self.push_undo()
        self.px = [[QColor(color) for _ in range(self.w)] for _ in range(self.h)]
        self.update()
        self.changed.emit()

    # --- geometri ---
    def _cell(self):
        return max(1, min(self.width() // self.w, self.height() // self.h))

    def _origin(self):
        c = self._cell()
        return (self.width() - c * self.w) // 2, (self.height() - c * self.h) // 2

    def _at(self, pos):
        c = self._cell()
        ox, oy = self._origin()
        x, y = (pos.x() - ox) // c, (pos.y() - oy) // c
        return (int(x), int(y)) if 0 <= x < self.w and 0 <= y < self.h else None

    # --- boyama ---
    def _apply(self, x, y):
        pts = [(x, y)] + ([(self.w - 1 - x, y)] if self.mirror else [])
        for px, py in pts:
            if self.tool == "pen":
                self.px[py][px] = QColor(self.color)
            elif self.tool == "eraser":
                self.px[py][px] = None
            elif self.tool == "fill":
                self._flood(px, py)
        self.update()
        self.changed.emit()

    def _flood(self, x, y):
        target = self.px[y][x]
        key = (lambda c: None if c is None else c.rgba())
        tk, new = key(target), self.color.rgba()
        if tk == new:
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if 0 <= cx < self.w and 0 <= cy < self.h and key(self.px[cy][cx]) == tk:
                self.px[cy][cx] = QColor(self.color)
                stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]

    def mousePressEvent(self, e):
        p = self._at(e.position().toPoint())
        if not p:
            return
        if self.tool == "pick" or e.button() == Qt.MiddleButton:
            c = self.px[p[1]][p[0]]
            if c is not None:
                self.picked.emit(QColor(c))
            return
        self.push_undo()
        self._erase_btn = e.button() == Qt.RightButton
        if self._erase_btn:
            old, self.tool = self.tool, "eraser"
            self._apply(*p)
            self.tool = old
        else:
            self._apply(*p)
        self._stroke = self.tool in ("pen", "eraser") or self._erase_btn

    def mouseMoveEvent(self, e):
        p = self._at(e.position().toPoint())
        if p != self.hover:
            self.hover = p
            self.update()
        if self._stroke and p:
            if self._erase_btn:
                old, self.tool = self.tool, "eraser"
                self._apply(*p)
                self.tool = old
            else:
                self._apply(*p)

    def mouseReleaseEvent(self, e):
        self._stroke = False

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        c = self._cell()
        ox, oy = self._origin()
        light, dark = QColor("#3a3a40"), QColor("#2e2e34")
        for y in range(self.h):
            for x in range(self.w):
                r = QRect(ox + x * c, oy + y * c, c, c)
                p.fillRect(r, light if (x + y) % 2 else dark)
                col = self.px[y][x]
                if col is not None:
                    p.fillRect(r, col)
        if self.grid and c >= 8:
            p.setPen(QColor(0, 0, 0, 60))
            for x in range(self.w + 1):
                p.drawLine(ox + x * c, oy, ox + x * c, oy + self.h * c)
            for y in range(self.h + 1):
                p.drawLine(ox, oy + y * c, ox + self.w * c, oy + y * c)
        if self.mirror:
            p.setPen(QColor(TOKENS["accent"]))
            mx = ox + self.w * c // 2
            p.drawLine(mx, oy, mx, oy + self.h * c)
        if self.hover:
            p.setPen(QColor(255, 255, 255, 180))
            p.setBrush(Qt.NoBrush)
            p.drawRect(ox + self.hover[0] * c, oy + self.hover[1] * c, c - 1, c - 1)
        p.end()


class Preview(QWidget):
    """Eşya görünümü (düz) ya da 16×16×16 küp (izometrik üç yüz)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.img = QImage()
        self.cube = False
        self.setFixedSize(150, 150)

    def set(self, img, cube):
        self.img, self.cube = img, cube
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TOKENS["surface_2"]))
        if self.img.isNull():
            return
        if not self.cube:
            s = min(self.width(), self.height()) - 30
            r = QRect((self.width() - s) // 2, (self.height() - s) // 2, s, s)
            p.drawImage(r, self.img)
            p.end()
            return
        # izometrik küp: üst, sol, sağ yüz
        s = 52.0
        cx, cy = self.width() / 2, self.height() / 2 - 4
        top = [QPointF(cx, cy - s), QPointF(cx + s, cy - s / 2), QPointF(cx, cy), QPointF(cx - s, cy - s / 2)]
        left = [QPointF(cx - s, cy - s / 2), QPointF(cx, cy), QPointF(cx, cy + s), QPointF(cx - s, cy + s / 2)]
        right = [QPointF(cx, cy), QPointF(cx + s, cy - s / 2), QPointF(cx + s, cy + s / 2), QPointF(cx, cy + s)]
        w, h = self.img.width(), self.img.height()
        for quad, shade in ((top, 1.0), (left, 0.8), (right, 0.62)):
            src = QPolygonF([QPointF(0, 0), QPointF(w, 0), QPointF(w, h), QPointF(0, h)])
            if quad is top:
                dst = QPolygonF([quad[3], quad[0], quad[1], quad[2]])
            else:
                dst = QPolygonF(quad)
            tr = QTransform()
            if QTransform.quadToQuad(src, dst, tr):
                p.save()
                p.setTransform(tr)
                p.drawImage(QRect(0, 0, w, h), self.img)
                p.restore()
            p.setBrush(QColor(0, 0, 0, int(255 * (1 - shade))))
            p.setPen(Qt.NoPen)
            p.drawPolygon(QPolygonF(quad))
        p.end()


class TextureDesigner(QDialog):
    """kind: tool | food | disc | painting | hud. allow_cube: eşyalarda blok (küp) görünümü seçeneği."""

    def __init__(self, kind, w=16, h=16, image=None, cube=False, allow_cube=True, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle(t("Doku Tasarımı"))
        self.resize(980, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.addWidget(label("Doku Tasarımı", "PageTitle"))
        v.addWidget(label("Piksel piksel boya: sol tık boyar, sağ tık siler, orta tık renk alır. Ctrl+Z geri al, Ctrl+Y yinele.",
                          "Muted", wrap=True))
        body = QHBoxLayout()
        v.addLayout(body, 1)

        # sol: araçlar
        side = QVBoxLayout()
        self.tool_group = QButtonGroup(self)
        for key, name, sc in TOOLS:
            b = QPushButton(f"{t(name)}  ({sc})")
            b.setCheckable(True)
            b.setProperty("variant", "ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            self.tool_group.addButton(b)
            side.addWidget(b)
            QShortcut(QKeySequence(sc), self, lambda k=key: self._set_tool(k))
            if key == "pen":
                b.setChecked(True)
        self.mirror_btn = QPushButton(t("Ayna (simetri)"))
        self.mirror_btn.setCheckable(True)
        self.mirror_btn.setProperty("variant", "ghost")
        self.mirror_btn.toggled.connect(lambda on: (setattr(self.canvas, "mirror", on), self.canvas.update()))
        side.addWidget(self.mirror_btn)
        self.grid_btn = QPushButton(t("Izgara"))
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.setProperty("variant", "ghost")
        self.grid_btn.toggled.connect(lambda on: (setattr(self.canvas, "grid", on), self.canvas.update()))
        side.addWidget(self.grid_btn)
        side.addSpacing(10)
        side.addWidget(button("Geri Al", "ghost", lambda: self.canvas.do_undo()))
        side.addWidget(button("Yinele", "ghost", lambda: self.canvas.do_redo()))
        side.addWidget(button("Temizle", "ghost", lambda: self.canvas.clear()))
        side.addWidget(button("Hepsini Boya", "ghost", lambda: self.canvas.fill_all(self.canvas.color)))
        side.addStretch(1)
        body.addLayout(side)

        # orta: tuval
        self.canvas = Canvas(w, h)
        self.canvas.picked.connect(self._set_color)
        self.canvas.changed.connect(self._refresh_preview)
        body.addWidget(self.canvas, 1)
        QShortcut(QKeySequence.Undo, self, self.canvas.do_undo)
        QShortcut(QKeySequence.Redo, self, self.canvas.do_redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.canvas.do_redo)

        # sağ: renkler, şablon, biçim, önizleme
        right = QVBoxLayout()
        right.addWidget(label("Renk", "CardTitle"))
        self.swatch = QPushButton()
        self.swatch.setFixedHeight(28)
        self.swatch.setCursor(Qt.PointingHandCursor)
        self.swatch.setToolTip(t("Özel renk seç"))
        self.swatch.clicked.connect(self._custom_color)
        right.addWidget(self.swatch)
        grid = QGridLayout()
        grid.setSpacing(3)
        for i, col in enumerate(PALETTE):
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:{col}; border:1px solid {TOKENS['border']}; border-radius:4px;}}")
            b.clicked.connect(lambda _=False, c=col: self._set_color(QColor(c)))
            grid.addWidget(b, i // 6, i % 6)
        right.addLayout(grid)
        self.recent = QHBoxLayout()
        self.recent.setSpacing(3)
        right.addLayout(self.recent)
        self._recent = []

        self.allow_cube = allow_cube and w == 16 and h == 16 and kind in ("tool", "food", "disc")
        tpls = []
        if w >= 16 and h >= 16:                    # önce bu türün şablonları, sonra diğerleri
            tpls = TT.for_kind(kind)
            tpls += [(k, n) for k, n in TT.for_kind("tool") + TT.for_kind("food") + TT.for_kind("disc") if (k, n) not in tpls]
        if tpls:
            right.addSpacing(8)
            right.addWidget(label("Şablon", "CardTitle"))
            self.tpl = QComboBox()
            for k, n in tpls:
                self.tpl.addItem(t(n), k)
            right.addWidget(self.tpl)
            right.addWidget(label("Şablon ana renk = seçili renk, ikinci renk = son kullanılan renk.", "Muted", wrap=True))
            right.addWidget(button("Şablonu Uygula", "ghost", self.apply_template))
        if self.allow_cube:
            right.addSpacing(8)
            right.addWidget(label("Görünüm", "CardTitle"))
            self.shape = QComboBox()
            self.shape.addItem(t("Eşya (düz)"), "item")
            self.shape.addItem(t("Blok (16×16×16 küp)"), "cube")
            self.shape.setCurrentIndex(1 if cube else 0)
            self.shape.currentIndexChanged.connect(self._refresh_preview)
            right.addWidget(self.shape)
        right.addSpacing(8)
        right.addWidget(label("Önizleme", "CardTitle"))
        self.preview = Preview()
        right.addWidget(self.preview, 0, Qt.AlignHCenter)
        self.size_lbl = label(t("Boyut: {w}×{h} piksel", w=w, h=h), "Muted")
        right.addWidget(self.size_lbl)
        right.addStretch(1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(220)
        body.addWidget(rw)

        v.addLayout(row(None, button("İptal", "ghost", self.reject), button("Kaydet", "primary", self.accept),
                        stretch_end=False))
        self._set_color(QColor("#d9332b"), remember=False)
        if image is not None and not image.isNull():
            self.canvas.set_image(image)
        self._refresh_preview()

    # --- yardımcılar ---
    def _set_tool(self, k):
        self.canvas.tool = k
        for b, (key, _n, _s) in zip(self.tool_group.buttons(), TOOLS):
            b.setChecked(key == k)
        self.canvas.setCursor(Qt.CrossCursor if k != "pick" else Qt.PointingHandCursor)

    def _set_color(self, c, remember=True):
        if remember and self.canvas.color.name() != c.name():
            prev = self.canvas.color.name()
            if prev not in self._recent:
                self._recent = ([prev] + self._recent)[:6]
                self._draw_recent()
        self.canvas.color = QColor(c)
        self.swatch.setStyleSheet(f"QPushButton{{background:{c.name()}; border:1px solid {TOKENS['border']}; border-radius:6px;}}")
        if self.canvas.tool in ("eraser", "pick"):
            self._set_tool("pen")

    def _draw_recent(self):
        while self.recent.count():
            it = self.recent.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()
        for col in self._recent:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setToolTip(col)
            b.setStyleSheet(f"QPushButton{{background:{col}; border:1px solid {TOKENS['border']}; border-radius:4px;}}")
            b.clicked.connect(lambda _=False, c=col: self._set_color(QColor(c)))
            self.recent.addWidget(b)
        self.recent.addStretch(1)

    def _custom_color(self):
        c = QColorDialog.getColor(self.canvas.color, self, t("Renk seç"))
        if c.isValid():
            self._set_color(c)

    def apply_template(self):
        key = self.tpl.currentData()
        second = self._recent[0] if self._recent else None
        g = TT.render(key, self.canvas.color.name(), second)
        self.canvas.stamp(g, (self.canvas.w - 16) // 2, (self.canvas.h - 16) // 2)

    def _refresh_preview(self, *_):
        self.preview.set(self.canvas.image(), self.is_cube())

    # --- sonuç ---
    def is_cube(self):
        return bool(self.allow_cube and self.shape.currentData() == "cube")

    def result_image(self):
        return self.canvas.image()
