"""Minecraft eşya ikonlarını oyunun kendi model dosyalarından çizer (Oyun Dosyaları sırasında).

Çit, merdiven, basamak, duvar gibi blok eşyaların düz bir resmi yoktur; oyun bunları 3D modelden
envanter açısıyla çizer. Burada aynısı küçük ölçekte yapılır:
  * items/<id>.json (1.21.4+) ya da models/item/<id>.json -> model
  * model zinciri (parent) izlenir; dokular (#değişken) çözülür
  * "item/generated" -> düz ikon (layer0, layer1… üst üste)
  * "elements" -> küpler display.gui açısıyla (varsayılan [30, 225, 0]) izometrik çizilir,
    Minecraft'ın yön gölgelendirmesi (üst 1.0, kuzey/güney 0.8, doğu/batı 0.6) uygulanır
Sonuç: Icons/items/<id>.png (64x64). Sandık, yatak, kafa gibi özel çizilen eşyalar atlanır.
Yalnızca Qt (QtGui) kullanır; ek kütüphane gerekmez.
"""
import json
import math
import os
import zipfile

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF, QTransform

SIZE = 64
SHADE = {"up": 1.0, "down": 0.5, "north": 0.8, "south": 0.8, "east": 0.6, "west": 0.6}
TINT = QColor("#79c05a")                 # çimen/yaprak gibi renklendirilen yüzeyler için varsayılan yeşil
DEFAULT_GUI = (30.0, 225.0, 0.0)


class _Jar:
    def __init__(self, z):
        self.z = z
        self.names = set(z.namelist())
        self.models, self.textures = {}, {}

    def json(self, path):
        try:
            return json.loads(self.z.read(path).decode("utf-8"))
        except Exception:
            return None

    def model(self, ref):
        ref = ref.replace("minecraft:", "")
        if ref not in self.models:
            self.models[ref] = self.json(f"assets/minecraft/models/{ref}.json")
        return self.models[ref]

    def texture(self, ref):
        ref = ref.replace("minecraft:", "")
        if ref not in self.textures:
            img = None
            p = f"assets/minecraft/textures/{ref}.png"
            if p in self.names:
                img = QImage.fromData(self.z.read(p))
                if not img.isNull():
                    img = img.convertToFormat(QImage.Format_ARGB32)
                    if img.height() > img.width():          # animasyonlu doku: ilk kare
                        img = img.copy(0, 0, img.width(), img.width())
                else:
                    img = None
            self.textures[ref] = img
        return self.textures[ref]


def _resolve(jar, ref):
    """Model zincirini çözer: (dokular, elemanlar, gui_dönüşü, düz_mü)."""
    textures, elements, gui, flat = {}, None, None, False
    seen = set()
    while ref and ref not in seen:
        seen.add(ref)
        r = ref.replace("minecraft:", "")
        if r in ("item/generated", "builtin/generated", "item/handheld"):
            flat = True
            break
        m = jar.model(r)
        if not m:
            break
        for k, v in (m.get("textures") or {}).items():
            textures.setdefault(k, v)
        if elements is None and m.get("elements"):
            elements = m["elements"]
        if gui is None:
            g = ((m.get("display") or {}).get("gui") or {}).get("rotation")
            if g:
                gui = tuple(float(x) for x in g)
        ref = m.get("parent")
    if ref and ref.replace("minecraft:", "") in ("item/generated", "builtin/generated"):
        flat = True
    return textures, elements, gui or DEFAULT_GUI, flat


def _tex(textures, name, depth=0):
    v = textures.get(name.lstrip("#"))
    if v is None or depth > 8:
        return None
    return _tex(textures, v, depth + 1) if v.startswith("#") else v


def _shaded(img, shade, tint):
    out = QImage(img)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
    if tint:
        p.setCompositionMode(QPainter.CompositionMode_Multiply)
        p.fillRect(out.rect(), TINT)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        p.drawImage(0, 0, img)                               # şeffaflığı geri yükle
        p.setCompositionMode(QPainter.CompositionMode_SourceAtop)
    if shade < 1.0:
        p.fillRect(out.rect(), QColor(0, 0, 0, int(255 * (1 - shade))))
    p.end()
    return out


def _crop(img, uv):
    """uv (0-16) bölgesini keser; ters uv'ler aynalama demektir."""
    s = img.width() / 16.0
    u1, v1, u2, v2 = uv
    x, y = min(u1, u2) * s, min(v1, v2) * s
    w, h = max(abs(u2 - u1) * s, 1), max(abs(v2 - v1) * s, 1)
    part = img.copy(int(round(x)), int(round(y)), max(1, int(round(w))), max(1, int(round(h))))
    if u2 < u1 or v2 < v1:
        part = part.mirrored(u2 < u1, v2 < v1)
    return part


# yüz: (dört köşeden TL, TR, BL), varsayılan uv
def _faces(f, t):
    x1, y1, z1 = f
    x2, y2, z2 = t
    return {
        "north": (((x2, y2, z1), (x1, y2, z1), (x2, y1, z1)), (16 - x2, 16 - y2, 16 - x1, 16 - y1), (0, 0, -1)),
        "south": (((x1, y2, z2), (x2, y2, z2), (x1, y1, z2)), (x1, 16 - y2, x2, 16 - y1), (0, 0, 1)),
        "west": (((x1, y2, z1), (x1, y2, z2), (x1, y1, z1)), (z1, 16 - y2, z2, 16 - y1), (-1, 0, 0)),
        "east": (((x2, y2, z2), (x2, y2, z1), (x2, y1, z2)), (16 - z2, 16 - y2, 16 - z1, 16 - y1), (1, 0, 0)),
        "up": (((x1, y2, z1), (x2, y2, z1), (x1, y2, z2)), (x1, z1, x2, z2), (0, 1, 0)),
        "down": (((x1, y1, z2), (x2, y1, z2), (x1, y1, z1)), (x1, 16 - z2, x2, 16 - z1), (0, -1, 0)),
    }


def _projector(gui):
    rx, ry = math.radians(gui[0]), math.radians(-gui[1])

    def rot(v, center=True):
        x, y, z = (v[0] - 8, v[1] - 8, v[2] - 8) if center else v
        x, z = x * math.cos(ry) + z * math.sin(ry), -x * math.sin(ry) + z * math.cos(ry)
        y, z = y * math.cos(rx) - z * math.sin(rx), y * math.sin(rx) + z * math.cos(rx)
        return x, y, z
    return rot


def render_model(jar, ref):
    """Bir modelin envanter ikonunu QImage olarak döndürür (ya da None)."""
    textures, elements, gui, flat = _resolve(jar, ref)
    out = QImage(SIZE, SIZE, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    if flat or not elements:
        layers = [textures.get(f"layer{i}") for i in range(5)]
        drawn = False
        for lay in layers:
            if not lay:
                continue
            img = jar.texture(_tex(textures, lay) or lay)
            if img:
                p.drawImage(out.rect(), img.scaled(SIZE, SIZE, Qt.IgnoreAspectRatio, Qt.FastTransformation))
                drawn = True
        p.end()
        return out if drawn else None

    rot = _projector(gui)
    scale = SIZE / 26.0                     # 16 birimlik küp ~42 px; çıkıntılar için pay
    polys = []
    for el in elements:
        if el.get("rotation") and abs(float(el["rotation"].get("angle", 0))) not in (0.0,):
            pass                            # eğik elemanlar (nadir) düz çizilir
        frm, to = el.get("from"), el.get("to")
        if not frm or not to:
            continue
        geo = _faces(frm, to)
        for name, face in (el.get("faces") or {}).items():
            if name not in geo:
                continue
            corners, def_uv, normal = geo[name]
            n = rot(normal, center=False)
            if n[2] <= 1e-6:                # kameraya bakmayan yüz
                continue
            tex = _tex(textures, face.get("texture", ""))
            img = jar.texture(tex) if tex else None
            if img is None:
                continue
            part = _crop(img, face.get("uv") or def_uv)
            if face.get("rotation"):
                part = part.transformed(QTransform().rotate(int(face["rotation"])))
            shade = SHADE[name] if el.get("shade", True) else 1.0
            part = _shaded(part, shade, "tintindex" in face)
            pts = [rot(c) for c in corners]
            depth = sum(q[2] for q in pts) / 3 + n[2] * 0.01
            polys.append((depth, pts, part))
    polys.sort(key=lambda x: x[0])
    for _, pts, part in polys:
        (tlx, tly, _), (trx, try_, _), (blx, bly, _) = pts
        to = lambda x, y: (SIZE / 2 + x * scale, SIZE / 2 - y * scale)
        TL, TR, BL = to(tlx, tly), to(trx, try_), to(blx, bly)
        w, h = part.width(), part.height()
        tr = QTransform((TR[0] - TL[0]) / w, (TR[1] - TL[1]) / w, (BL[0] - TL[0]) / h, (BL[1] - TL[1]) / h,
                        TL[0], TL[1])
        p.setTransform(tr)
        p.drawImage(QPointF(0, 0), part)
    p.end()
    return out if polys else None


def _item_model_ref(jar, item_id):
    """Eşyanın modeli: önce items/<id>.json (1.21.4+), yoksa models/item/<id>.json."""
    d = jar.json(f"assets/minecraft/items/{item_id}.json")
    if d:
        stack = [d.get("model")]
        while stack:
            m = stack.pop(0)
            if isinstance(m, dict):
                if m.get("type", "").endswith("model") and isinstance(m.get("model"), str):
                    return m["model"]
                for k in ("fallback", "on_false", "on_true", "model"):
                    if isinstance(m.get(k), dict):
                        stack.append(m[k])
                for c in m.get("cases", []) or []:
                    stack.append(c.get("model"))
                for e in m.get("entries", []) or []:
                    stack.append(e.get("model"))
        return None
    if f"assets/minecraft/models/item/{item_id}.json" in jar.names:
        return f"item/{item_id}"
    return None


def item_ids(jar):
    ids = {n[len("assets/minecraft/items/"):-5] for n in jar.names
           if n.startswith("assets/minecraft/items/") and n.endswith(".json")}
    if not ids:
        ids = {n[len("assets/minecraft/models/item/"):-5] for n in jar.names
               if n.startswith("assets/minecraft/models/item/") and n.endswith(".json")}
    return sorted(ids)


def render_all(jar_path, out_dir, progress=None):
    """İstemci jar'ındaki tüm eşyaların ikonlarını out_dir/<id>.png olarak yazar. Yazılan sayıyı döndürür."""
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    with zipfile.ZipFile(jar_path) as z:
        jar = _Jar(z)
        ids = item_ids(jar)
        for i, iid in enumerate(ids):
            ref = _item_model_ref(jar, iid)
            if ref:
                try:
                    img = render_model(jar, ref)
                except Exception:
                    img = None
                if img is not None:
                    img.save(os.path.join(out_dir, f"{iid}.png"))
                    n += 1
            if progress and i % 50 == 0:
                progress(i, len(ids))
    return n
