"""3B boyama görünümü: modeli istediğin yönden çevirip doğrudan yüzeyine boya.

İki model:
  FaceModel  — blok: altı yüzün her biri ayrı 16×16 doku (derindeki pikseller yüzeydekiyle karışmaz).
  VoxelModel — 3B eşya: 16×16×16 voksel; boyamak tıklanan vokseli boyar, Shift+tık yanına voksel ekler.

Fare: sol tık boya, sağ tık sil (sürüklenirse döndürür), orta tık renk al, tekerlek yakınlaştır.
Çizim QPainter ile (ortografik, arkadan öne sıralı yüzler); seçim çizilen çokgenlerle yapılır.
"""
import math

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .theme import TOKENS

N = 16
FACES = ("up", "down", "north", "south", "east", "west")
NORMALS = {"up": (0, 1, 0), "down": (0, -1, 0), "north": (0, 0, -1), "south": (0, 0, 1),
           "east": (1, 0, 0), "west": (-1, 0, 0)}
SHADE = {"up": 1.0, "down": 0.55, "north": 0.8, "south": 0.8, "east": 0.68, "west": 0.68}


def texel_quad(face, u, v):
    """Minecraft'ın küp UV yönleriyle: yüz dokusunun (u, v) pikselinin 3B köşeleri."""
    y0, y1 = N - v - 1, N - v
    if face == "north":
        return [(N - u, y1, 0), (N - u - 1, y1, 0), (N - u - 1, y0, 0), (N - u, y0, 0)]
    if face == "south":
        return [(u, y1, N), (u + 1, y1, N), (u + 1, y0, N), (u, y0, N)]
    if face == "east":
        return [(N, y1, N - u), (N, y1, N - u - 1), (N, y0, N - u - 1), (N, y0, N - u)]
    if face == "west":
        return [(0, y1, u), (0, y1, u + 1), (0, y0, u + 1), (0, y0, u)]
    if face == "up":
        return [(u, N, v), (u + 1, N, v), (u + 1, N, v + 1), (u, N, v + 1)]
    return [(u, 0, N - v), (u + 1, 0, N - v), (u + 1, 0, N - v - 1), (u, 0, N - v - 1)]     # down


def voxel_face(x, y, z, f):
    return {
        "up": [(x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)],
        "down": [(x, y, z), (x + 1, y, z), (x + 1, y, z + 1), (x, y, z + 1)],
        "north": [(x, y, z), (x + 1, y, z), (x + 1, y + 1, z), (x, y + 1, z)],
        "south": [(x, y, z + 1), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)],
        "east": [(x + 1, y, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)],
        "west": [(x, y, z), (x, y + 1, z), (x, y + 1, z + 1), (x, y, z + 1)],
    }[f]


class FaceModel:
    """Blok: altı yüz × 16×16 renk (QColor ya da None)."""

    def __init__(self, image=None):
        self.faces = {f: [[None] * N for _ in range(N)] for f in FACES}
        if image is not None and not image.isNull():
            self.fill_from(image)

    def fill_from(self, image):
        img = image.scaled(N, N)
        for f in FACES:
            for v in range(N):
                for u in range(N):
                    c = QColor.fromRgba(img.pixel(u, v))
                    self.faces[f][v][u] = c if c.alpha() > 0 else None

    def quads(self):
        for f in FACES:
            for v in range(N):
                for u in range(N):
                    yield (f, u, v), texel_quad(f, u, v), NORMALS[f], SHADE[f], self.faces[f][v][u]

    def get(self, key):
        f, u, v = key
        return self.faces[f][v][u]

    def paint(self, key, color, add=False):
        f, u, v = key
        self.faces[f][v][u] = QColor(color) if color is not None else None

    def snapshot(self):
        return {f: [r[:] for r in g] for f, g in self.faces.items()}

    def restore(self, s):
        self.faces = {f: [r[:] for r in g] for f, g in s.items()}

    def strip(self):
        """Altı yüz yan yana (96×16): up, down, north, south, east, west."""
        img = QImage(N * 6, N, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        for i, f in enumerate(FACES):
            for v in range(N):
                for u in range(N):
                    c = self.faces[f][v][u]
                    if c is not None:
                        img.setPixelColor(i * N + u, v, c)
        return img

    def load_strip(self, img):
        for i, f in enumerate(FACES):
            for v in range(N):
                for u in range(N):
                    c = QColor.fromRgba(img.pixel(i * N + u, v))
                    self.faces[f][v][u] = c if c.alpha() > 0 else None

    def front(self):
        img = QImage(N, N, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        for v in range(N):
            for u in range(N):
                c = self.faces["south"][v][u]
                if c is not None:
                    img.setPixelColor(u, v, c)
        return img


class VoxelModel:
    """3B eşya: {(x, y, z): '#rrggbb'}."""

    def __init__(self, vox=None):
        self.vox = vox if vox is not None else {}           # tasarımcıyla aynı sözlük (katman görünümüyle ortak)

    def quads(self):
        for (x, y, z), col in self.vox.items():
            for f, (dx, dy, dz) in NORMALS.items():
                if (x + dx, y + dy, z + dz) not in self.vox:
                    yield (x, y, z, f), voxel_face(x, y, z, f), NORMALS[f], SHADE[f], QColor(col)

    def get(self, key):
        c = self.vox.get(key[:3])
        return QColor(c) if c else None

    def paint(self, key, color, add=False):
        x, y, z, f = key
        if add and color is not None:
            dx, dy, dz = NORMALS[f]
            p = (x + dx, y + dy, z + dz)
            if all(0 <= a < N for a in p):
                self.vox[p] = QColor(color).name()
            return
        if color is None:
            self.vox.pop((x, y, z), None)
        else:
            self.vox[(x, y, z)] = QColor(color).name()

    def snapshot(self):
        return dict(self.vox)

    def restore(self, s):
        self.vox.clear()
        self.vox.update(s)


class Viewport3D(QWidget):
    changed = Signal()
    picked = Signal(QColor)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.yaw, self.pitch, self.zoom = -35.0, 25.0, 1.0
        self.color = QColor("#d9332b")
        self.tool = "pen"                                     # pen | eraser | pick
        self.grid = True
        self.undo, self.redo = [], []
        self._drawn = []
        self._drag = None
        self._moved = False
        self._hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(420, 420)
        self.setFocusPolicy(Qt.StrongFocus)

    def set_model(self, model):
        self.model = model
        self.undo.clear()
        self.redo.clear()
        self.update()

    # --- geri al ---
    def push_undo(self):
        self.undo.append(self.model.snapshot())
        self.undo = self.undo[-60:]
        self.redo.clear()

    def do_undo(self):
        if self.undo:
            self.redo.append(self.model.snapshot())
            self.model.restore(self.undo.pop())
            self.update()
            self.changed.emit()

    def do_redo(self):
        if self.redo:
            self.undo.append(self.model.snapshot())
            self.model.restore(self.redo.pop())
            self.update()
            self.changed.emit()

    def view(self, yaw, pitch):
        self.yaw, self.pitch = yaw, pitch
        self.update()

    # --- izdüşüm ---
    def _xf(self):
        cy, sy = math.cos(math.radians(self.yaw)), math.sin(math.radians(self.yaw))
        cp, sp = math.cos(math.radians(self.pitch)), math.sin(math.radians(self.pitch))
        s = min(self.width(), self.height()) / (N * 1.85) * self.zoom
        cx, cyc = self.width() / 2, self.height() / 2

        def rot(p):
            x, y, z = p[0] - N / 2, p[1] - N / 2, p[2] - N / 2
            x, z = x * cy - z * sy, x * sy + z * cy           # y ekseni etrafında
            y, z = y * cp - z * sp, y * sp + z * cp           # x ekseni etrafında
            return x, y, z

        def proj(r):
            return QPointF(cx + r[0] * s, cyc - r[1] * s)

        def rotd(v):                                          # yön (normal) için: merkezsiz
            x, y, z = v
            x, z = x * cy - z * sy, x * sy + z * cy
            y, z = y * cp - z * sp, y * sp + z * cp
            return x, y, z
        return rot, proj, rotd

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TOKENS["surface_2"]))
        rot, proj, rotd = self._xf()
        faces = []
        for key, corners, normal, shade, col in self.model.quads():
            if rotd(normal)[2] <= 1e-6:                       # arka yüz: izleyiciye dönük değil
                continue
            rc = [rot(c) for c in corners]
            depth = sum(r[2] for r in rc) / 4
            faces.append((depth, key, QPolygonF([proj(r) for r in rc]), shade, col))
        faces.sort(key=lambda f: f[0])                          # uzaktan (küçük z) yakına
        grid_pen = QPen(QColor(0, 0, 0, 40), 0.6)
        empty = QColor(TOKENS.get("text_muted", "#888"))
        empty.setAlpha(28)
        for depth, key, poly, shade, col in faces:
            if col is None:
                p.setBrush(empty)
            else:
                c = QColor(col)
                c.setRgb(int(c.red() * shade), int(c.green() * shade), int(c.blue() * shade), c.alpha())
                p.setBrush(c)
            p.setPen(grid_pen if self.grid else Qt.NoPen)
            p.drawPolygon(poly)
        if self._hover is not None:
            for depth, key, poly, *_ in faces:
                if key == self._hover:
                    p.setBrush(Qt.NoBrush)
                    p.setPen(QPen(QColor(TOKENS["accent"]), 1.6))
                    p.drawPolygon(poly)
        self._drawn = faces
        p.end()

    def _hit(self, pos):
        pt = QPointF(pos)
        for depth, key, poly, *_ in reversed(self._drawn):    # en yakından
            if poly.containsPoint(pt, Qt.OddEvenFill):
                return key
        return None

    # --- fare ---
    def mousePressEvent(self, e):
        self._drag = (e.position(), self.yaw, self.pitch, e.button())
        self._moved = False
        if e.button() == Qt.LeftButton and self.tool == "pick":
            k = self._hit(e.position())
            c = self.model.get(k) if k else None
            if c is not None:
                self.picked.emit(c)
            self._drag = None
        elif e.button() == Qt.LeftButton:
            self._stroke = False
            self._paint_at(e.position(), add=bool(e.modifiers() & Qt.ShiftModifier))
        elif e.button() == Qt.MiddleButton:
            k = self._hit(e.position())
            c = self.model.get(k) if k else None
            if c is not None:
                self.picked.emit(c)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._drag and self._drag[3] == Qt.RightButton:
            d = pos - self._drag[0]
            if abs(d.x()) + abs(d.y()) > 3:
                self._moved = True
            self.yaw = self._drag[1] + d.x() * 0.6
            self.pitch = max(-89, min(89, self._drag[2] + d.y() * 0.6))
            self.update()
            return
        if self._drag and self._drag[3] == Qt.LeftButton and not (e.modifiers() & Qt.ShiftModifier):
            self._paint_at(pos)
        k = self._hit(pos)
        if k != self._hover:
            self._hover = k
            self.update()

    def mouseReleaseEvent(self, e):
        if self._drag and self._drag[3] == Qt.RightButton and not self._moved:
            k = self._hit(e.position())
            if k is not None:
                self.push_undo()
                self.model.paint(k, None)
                self.update()
                self.changed.emit()
        self._drag = None
        self._stroke = False

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def wheelEvent(self, e):
        self.zoom = max(0.4, min(3.0, self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1)))
        self.update()

    def _paint_at(self, pos, add=False):
        k = self._hit(pos)
        if k is None:
            return
        cur = self.model.get(k)
        color = None if self.tool == "eraser" else self.color
        if not add and ((color is None and cur is None) or
                        (color is not None and cur is not None and cur.name() == color.name())):
            return
        if not getattr(self, "_stroke", False):
            self.push_undo()
            self._stroke = True
        self.model.paint(k, color, add=add and color is not None)
        self.update()
        self.changed.emit()
