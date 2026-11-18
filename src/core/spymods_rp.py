"""Spypaper Modları için kaynak paketi parçaları (görseller burada üretilir, Mojang dosyası kullanılmaz).

Düz HUD barları: kalp, açlık, zırh ve hava simgelerinin yerine 9x9'luk bar parçaları çizilir.
Oyun simgeleri 8 piksel arayla 9 piksel genişliğinde çizer; parçalar üst üste binip kesintisiz bir bar olur.
Kalp ve zırh soldan sağa dolar (yarım parça sol yarı), açlık ve hava sağdan sola (yarım parça sağ yarı).
Yol: assets/minecraft/textures/gui/sprites/hud/... (Minecraft 1.20.2 ve sonrası).
"""
import struct
import zlib

HUD = "assets/minecraft/textures/gui/sprites/hud/"
TOP, BOTTOM = 1, 7          # bar satırları (9 piksel içinde 7 piksel yükseklik)


def png(w, h, px):
    """px[y][x] = (r, g, b, a) -> PNG baytları (yalnızca standart kütüphane)."""
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _hex(c, a=255):
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


def _shade(rgb, f):
    r, g, b, a = rgb
    return (max(0, min(255, int(r * f))), max(0, min(255, int(g * f))), max(0, min(255, int(b * f))), a)


def segment(fill=None, cols=range(9), empty=False):
    """Bir bar parçası. empty: koyu arka plan + çerçeve; fill: renkli dolgu (verilen sütunlarda)."""
    clear = (0, 0, 0, 0)
    px = [[clear] * 9 for _ in range(9)]
    for x in range(9):
        if empty:
            px[TOP][x] = px[BOTTOM][x] = (16, 16, 16, 255)
            for y in range(TOP + 1, BOTTOM):
                px[y][x] = (48, 48, 48, 255)
        elif x in cols:
            c = _hex(fill)
            px[TOP + 1][x] = _shade(c, 1.35)                       # üstte ışık
            for y in range(TOP + 2, BOTTOM - 1):
                px[y][x] = c
            px[BOTTOM - 1][x] = _shade(c, 0.7)                     # altta gölge
    return png(9, 9, px)


LEFT, RIGHT = range(0, 5), range(4, 9)

HEARTS = {"": "#D8343A", "poisoned_": "#7FA028", "withered_": "#3C3C3C", "absorbing_": "#E8C23A",
          "frozen_": "#6CB8EC"}


def flat_bars():
    out = {}
    empty = segment(empty=True)
    # kalpler: container, full, half; hardcore ve yanıp sönen (blinking) sürümleri
    for suffix in ("", "_blinking"):
        for hc in ("", "_hardcore"):
            out[f"{HUD}heart/container{hc}{suffix}.png"] = empty
    out[f"{HUD}heart/vehicle_container.png"] = empty
    for prefix, colr in HEARTS.items():
        for hc in ("", "hardcore_"):
            for suffix in ("", "_blinking"):
                c = colr if not suffix else "#" + "".join(f"{min(255, int(v * 1.25)):02x}" for v in _hex(colr)[:3])
                out[f"{HUD}heart/{prefix}{hc}full{suffix}.png"] = segment(c)
                out[f"{HUD}heart/{prefix}{hc}half{suffix}.png"] = segment(c, LEFT)
    out[f"{HUD}heart/vehicle_full.png"] = segment("#E08A3C")
    out[f"{HUD}heart/vehicle_half.png"] = segment("#E08A3C", LEFT)
    # açlık (sağdan sola): yarım = sağ yarı
    for suffix, colr in (("", "#C87A2A"), ("_hunger", "#6E8E2C")):
        out[f"{HUD}food_empty{suffix}.png"] = empty
        out[f"{HUD}food_full{suffix}.png"] = segment(colr)
        out[f"{HUD}food_half{suffix}.png"] = segment(colr, RIGHT)
    # zırh (soldan sağa)
    out[f"{HUD}armor_empty.png"] = empty
    out[f"{HUD}armor_full.png"] = segment("#AEBCCB")
    out[f"{HUD}armor_half.png"] = segment("#AEBCCB", LEFT)
    # hava (sağdan sola, yalnızca tam)
    out[f"{HUD}air.png"] = segment("#4A9BE8")
    out[f"{HUD}air_bursting.png"] = segment("#9ACCF4")
    out[f"{HUD}air_empty.png"] = empty
    return out
