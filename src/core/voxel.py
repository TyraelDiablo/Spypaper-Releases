"""16×16×16 voksel (küçük küp) modeller: kaydetme ve Minecraft eşya modeline (elements) dönüştürme.

Model dosyası (içerik klasöründe <id>_model.json): {"size": 16, "voxels": {"x,y,z": "#rrggbb", ...}}
Kaynak paketinde: renkler 16×16'lık bir palet dokusuna (her renk bir piksel) yazılır, bitişik aynı renkli
voksel blokları büyük kutulara birleştirilir (eleman sayısı düşük kalsın diye) ve her yüz palet pikseline bakar.
"""
import json
import struct
import zlib

SIZE = 16
MAX_COLORS = 256


def load(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for k, c in (d.get("voxels") or {}).items():
        x, y, z = (int(v) for v in k.split(","))
        if 0 <= x < SIZE and 0 <= y < SIZE and 0 <= z < SIZE:
            out[(x, y, z)] = c
    return out


def save(path, vox):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"size": SIZE, "voxels": {f"{x},{y},{z}": c for (x, y, z), c in sorted(vox.items())}}, f)


def _boxes(vox):
    """Aynı renkli vokselleri açgözlü yöntemle kutulara birleştirir: [(x0,y0,z0,x1,y1,z1,renk)] (x1.. dahil değil)."""
    left = dict(vox)
    out = []
    for key in sorted(vox, key=lambda p: (p[1], p[2], p[0])):
        if key not in left:
            continue
        col = left[key]
        x0, y0, z0 = key
        x1 = x0 + 1
        while left.get((x1, y0, z0)) == col:
            x1 += 1
        z1 = z0 + 1
        while all(left.get((x, y0, z1)) == col for x in range(x0, x1)):
            z1 += 1
        y1 = y0 + 1
        while all(left.get((x, y1, z)) == col for x in range(x0, x1) for z in range(z0, z1)):
            y1 += 1
        for x in range(x0, x1):
            for y in range(y0, y1):
                for z in range(z0, z1):
                    left.pop((x, y, z), None)
        out.append((x0, y0, z0, x1, y1, z1, col))
    return out


def palette_png(colors):
    """Renk listesi -> 16×16 RGBA PNG baytları (renk i, (i%16, i//16) pikselinde)."""
    px = [[(0, 0, 0, 0)] * 16 for _ in range(16)]
    for i, c in enumerate(colors[:MAX_COLORS]):
        c = c.lstrip("#")
        px[i // 16][i % 16] = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in r) for r in px)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def to_model(vox, texture):
    """-> (model sözlüğü, palet renkleri). texture: 'spypaper:item/<id>'"""
    colors = []
    for c in vox.values():
        if c not in colors:
            colors.append(c)
    colors = colors[:MAX_COLORS]
    index = {c: i for i, c in enumerate(colors)}
    elements = []
    for x0, y0, z0, x1, y1, z1, col in _boxes({k: v for k, v in vox.items() if v in index}):
        i = index[col]
        u, v = i % 16, i // 16
        uv = [u + 0.25, v + 0.25, u + 0.75, v + 0.75]          # piksel ortası: kenar taşması olmasın
        face = {"uv": uv, "texture": "#p"}
        elements.append({"from": [x0, y0, z0], "to": [x1, y1, z1],
                         "faces": {d: dict(face) for d in ("north", "south", "east", "west", "up", "down")}})
    model = {"parent": "minecraft:block/block", "textures": {"p": texture, "particle": texture},
             "elements": elements}
    return model, colors


def extrude(grid, depth=2):
    """16×16 renk ızgarası (satır=y yukarıdan) -> ortada 'depth' kalınlığında voksel model."""
    vox = {}
    z0 = (SIZE - depth) // 2
    for row in range(SIZE):
        for x in range(SIZE):
            c = grid[row][x]
            if c:
                for z in range(z0, z0 + depth):
                    vox[(x, SIZE - 1 - row, z)] = c
    return vox
