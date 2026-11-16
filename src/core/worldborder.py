"""Dünya sınırı: koordinatlardan /worldborder komutları.

Minecraft'ın dünya sınırı her zaman kare ve bir merkeze göre çizilir. Kullanıcı iki köşe (X/Z) verir;
sınır bu dikdörtgeni kapsayan en küçük karedir (kenarlar farklıysa uzun kenar alınır).
Merkez ve yarıçap ile de verilebilir.
"""
import os

from .config import N_

MAX_SIZE = 59999968            # Minecraft'ın en büyük sınırı (= sınır yok)
MAX_COORD = 29999984
DIMENSIONS = {"minecraft:overworld": N_("Overworld"), "minecraft:the_nether": N_("Nether"),
              "minecraft:the_end": N_("End")}


class BorderError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def num(v):
    """1000.0 -> '1000', 12.5 -> '12.5'"""
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


def from_corners(x1, z1, x2, z2):
    """(merkez_x, merkez_z, boyut, kare_mi)"""
    dx, dz = abs(float(x2) - float(x1)), abs(float(z2) - float(z1))
    size = max(dx, dz)
    return (float(x1) + float(x2)) / 2, (float(z1) + float(z2)) / 2, size, dx == dz


def from_center(cx, cz, radius):
    return float(cx), float(cz), float(radius) * 2


def validate(cx, cz, size):
    if not (1 <= size <= MAX_SIZE):
        raise BorderError(N_("Sınır en az 1, en fazla {max} blok olabilir."), max=MAX_SIZE)
    if abs(cx) > MAX_COORD or abs(cz) > MAX_COORD:
        raise BorderError(N_("Merkez koordinatı ±{max} içinde olmalı."), max=MAX_COORD)


def commands(cx, cz, size, dimension="minecraft:overworld", seconds=0):
    validate(cx, cz, size)
    if dimension not in DIMENSIONS:
        raise BorderError(N_("Bilinmeyen boyut."))
    pre = "" if dimension == "minecraft:overworld" else f"execute in {dimension} run "
    out = [f"{pre}worldborder center {num(cx)} {num(cz)}", f"{pre}worldborder set {num(size)}"]
    if int(seconds or 0) > 0:
        out[1] += f" {int(seconds)}"
    return out


def remove_commands(dimension="minecraft:overworld"):
    pre = "" if dimension == "minecraft:overworld" else f"execute in {dimension} run "
    return [f"{pre}worldborder center 0 0", f"{pre}worldborder set {MAX_SIZE}"]


def edges(cx, cz, size):
    """(min_x, min_z, max_x, max_z)"""
    h = size / 2
    return cx - h, cz - h, cx + h, cz + h


def saved(server_path, level="world"):
    """level.dat'taki son kaydedilen sınır: (merkez_x, merkez_z, boyut) ya da None."""
    from .players import _get, _val, read_nbt
    root = read_nbt(os.path.join(server_path, level or "world", "level.dat"))
    data = _get(root, "Data") if root is not None else None
    if data is None:
        return None
    cx, cz, size = _get(data, "BorderCenterX"), _get(data, "BorderCenterZ"), _get(data, "BorderSize")
    if size is None:                                   # yeni sürümlerde ayrı bir bölümde olabilir
        wb = _get(data, "world_border", "WorldBorder")
        if wb is not None:
            cx, cz, size = _get(wb, "center_x", "CenterX"), _get(wb, "center_z", "CenterZ"), _get(wb, "size", "Size")
    if size is None:
        return None
    try:
        return float(_val(cx) or 0), float(_val(cz) or 0), float(_val(size))
    except (TypeError, ValueError):
        return None
