"""Minecraft tarzı can, zırh, açlık ve XP göstergesi.

Görseller Minecraft'ın kendi dosyalarından alınır (Oyun Dosyaları -> Icons/hud/*.png).
Dosyalar yoksa burada çizilen piksel ikonlar kullanılır (Mojang'ın görseli değil, kendi çizimimiz).
Oyundaki gibi: 10 kalp soldan, 10 but sağdan sola; her ikon 2 puan, yarım ikon 1 puan.
"""
import os

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from core.gamefiles import status as gf_status

ICON = 18                     # ekrandaki ikon boyutu (Minecraft: 9 px, 2x)
GAP = 1

# 9x9 piksel desenler (kendi çizimimiz): . boş, K kenar, R ana renk, H parlama, D koyu
_HEART = ["..KK.KK..", ".KRRKRRK.", "KRHRRRRRK", "KRRRRRRDK", "KRRRRRRDK",
          ".KRRRRDK.", "..KRRDK..", "...KDK...", "....K...."]
_FOOD = ["......KK.", ".....KHHK", "....KHHK.", "..KKRRK..", ".KRRRRK..",
         "KRRRRDK..", "KRRRDK...", ".KDDK....", "..KK....."]
_ARMOR = ["KKKK.KKKK", "KHHRKRRDK", "KHRRRRRDK", "KRRRRRRDK", ".KRRRRDK.",
          ".KRRRRDK.", ".KRRRRDK.", ".KRRDRDK.", ".KKK.KKK."]
_PALETTE = {
    "heart": {"K": "#1d0303", "R": "#d62a2a", "H": "#ff9b9b", "D": "#8f1414"},
    "heart_absorbing": {"K": "#251a00", "R": "#e6b412", "H": "#fff1a0", "D": "#9a7400"},
    "food": {"K": "#2a1606", "R": "#b8702f", "H": "#f0e6d8", "D": "#7a4518"},
    "armor": {"K": "#1a1a1a", "R": "#c8c8c8", "H": "#ffffff", "D": "#7d7d7d"},
}


def _pattern(rows, palette, half=None, empty=False):
    img = QImage(9, 9, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    for y, line in enumerate(rows):
        for x, ch in enumerate(line):
            if ch == ".":
                continue
            if empty and ch != "K":
                col = QColor("#2a2a2a")
            elif half == "left" and x > 4 and ch != "K":
                col = QColor("#2a2a2a")
            elif half == "right" and x < 4 and ch != "K":
                col = QColor("#2a2a2a")
            else:
                col = QColor(palette[ch])
            img.setPixelColor(x, y, col)
    return img


class _Sprites:
    """Minecraft sprite'ları (varsa) ya da kendi çizimimiz."""

    def __init__(self):
        d = os.path.join(gf_status()["icons_dir"], "hud")
        self.mc = os.path.isdir(d)

        def load(name):
            p = os.path.join(d, name + ".png")
            img = QImage(p) if self.mc and os.path.exists(p) else QImage()
            return None if img.isNull() else img
        self.s = {k: load(k) for k in ("heart_container", "heart_full", "heart_half", "heart_absorbing_full",
                                       "heart_absorbing_half", "food_empty", "food_full", "food_half",
                                       "armor_empty", "armor_full", "armor_half",
                                       "experience_bar_background", "experience_bar_progress")}
        fb = {
            "heart_container": _pattern(_HEART, _PALETTE["heart"], empty=True),
            "heart_full": _pattern(_HEART, _PALETTE["heart"]),
            "heart_half": _pattern(_HEART, _PALETTE["heart"], half="left"),
            "heart_absorbing_full": _pattern(_HEART, _PALETTE["heart_absorbing"]),
            "heart_absorbing_half": _pattern(_HEART, _PALETTE["heart_absorbing"], half="left"),
            "food_empty": _pattern(_FOOD, _PALETTE["food"], empty=True),
            "food_full": _pattern(_FOOD, _PALETTE["food"]),
            "food_half": _pattern(_FOOD, _PALETTE["food"], half="right"),
            "armor_empty": _pattern(_ARMOR, _PALETTE["armor"], empty=True),
            "armor_full": _pattern(_ARMOR, _PALETTE["armor"]),
            "armor_half": _pattern(_ARMOR, _PALETTE["armor"], half="left"),
        }
        for k, v in fb.items():
            if self.s.get(k) is None:
                self.s[k] = v

    def get(self, name):
        return self.s.get(name)


class HudWidget(QWidget):
    """Üstte zırh ve XP seviyesi, altta 10 kalp ve 10 but, en altta XP çubuğu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sprites = _Sprites()
        self.health = self.food = self.armor = 0
        self.absorption = 0.0
        self.level, self.progress = 0, 0.0
        self.hidden_stats = False              # yaratıcı/izleyici: can ve açlık oyunda görünmez
        self.empty = True
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def sizeHint(self):
        w = 20 * (ICON + GAP) + 24
        return QSize(w, ICON * 2 + 4 + 8 + 10 + 2)

    def set_values(self, health=0, food=0, armor=0, absorption=0.0, level=0, progress=0.0, hidden=False):
        self.health, self.food, self.armor = health, food, armor
        self.absorption, self.level, self.progress = absorption, level, progress
        self.hidden_stats, self.empty = hidden, False
        self.update()

    def clear(self):
        self.empty = True
        self.update()

    def _icon(self, p, name, x, y):
        img = self.sprites.get(name)
        if img is not None:
            p.drawImage(QRectF(x, y, ICON, ICON), img)

    def _row(self, p, y, value, full, half, empty, right_to_left=False, x0=0, count=10, back=None):
        for i in range(count):
            x = x0 + ((count - 1 - i) if right_to_left else i) * (ICON + GAP)
            if back:
                self._icon(p, back, x, y)
            pts = value - i * 2
            if pts >= 2:
                self._icon(p, full, x, y)
            elif pts == 1:
                self._icon(p, half, x, y)
            elif not back and empty:
                self._icon(p, empty, x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        if self.empty:
            p.end()
            return
        if self.hidden_stats:
            p.setOpacity(0.35)
        half_w = 10 * (ICON + GAP)
        right_x = half_w + 24
        y_top, y_mid = 0, ICON + 4
        # zırh (yalnızca varsa, oyundaki gibi kalplerin üstünde)
        if self.armor > 0:
            self._row(p, y_top, self.armor, "armor_full", "armor_half", "armor_empty")
        # altın kalpler (emilim) kalplerin üstünde
        if self.absorption > 0:
            # yalnızca dolu altın kalpler (oyundaki gibi boş çerçeve yok)
            self._row(p, y_top, int(round(self.absorption)), "heart_absorbing_full", "heart_absorbing_half", None,
                      x0=right_x if self.armor else 0)
        self._row(p, y_mid, int(round(self.health)), "heart_full", "heart_half", None, back="heart_container")
        self._row(p, y_mid, int(self.food), "food_full", "food_half", "food_empty", right_to_left=True, x0=right_x,
                  back="food_empty")
        p.setOpacity(1.0)
        # XP çubuğu ve seviye
        bar_y = y_mid + ICON + 8
        bar_w = right_x + half_w - GAP
        bg, fg = self.sprites.get("experience_bar_background"), self.sprites.get("experience_bar_progress")
        bar_h = 10
        if bg is not None and fg is not None:
            p.drawImage(QRectF(0, bar_y, bar_w, bar_h), bg)
            w = int(fg.width() * self.progress)
            if w > 0:
                p.drawImage(QRectF(0, bar_y, bar_w * self.progress, bar_h), fg.copy(0, 0, w, fg.height()))
        else:
            p.fillRect(QRectF(0, bar_y, bar_w, bar_h), QColor("#1b1b1b"))
            p.fillRect(QRectF(1, bar_y + 1, (bar_w - 2) * self.progress, bar_h - 2), QColor("#80ff20"))
            p.setPen(QColor("#000000"))
            p.drawRect(QRectF(0, bar_y, bar_w, bar_h))
        if self.level > 0:
            f = QFont(self.font())
            f.setBold(True)
            f.setPointSizeF(max(8.0, f.pointSizeF()))
            p.setFont(f)
            txt = str(self.level)
            r = QRectF(0, bar_y - 18, bar_w, 16)
            p.setPen(QColor("#000000"))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p.drawText(r.translated(dx, dy), Qt.AlignHCenter | Qt.AlignBottom, txt)
            p.setPen(QColor("#80ff20"))
            p.drawText(r, Qt.AlignHCenter | Qt.AlignBottom, txt)
        p.end()
