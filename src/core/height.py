"""Yapı yüksekliği: Overworld'ün alt/üst sınırını bir veri paketiyle (dimension_type) değiştirir.

Oyunun kendi overworld.json'u sunucunun jar'larından okunur (sürüm farklarına dayanıklı olsun diye) ve yalnızca
min_y, height ve logical_height değiştirilir. Paket: <dünya>/datapacks/spypaper_height.
Kurallar (Minecraft): min_y ve height 16'nın katı, -2032 ≤ min_y, min_y + height ≤ 2032, height ≤ 4064.
"""
import io
import json
import os
import shutil
import zipfile

from .config import N_

PACK = "spypaper_height"
ENTRY = "data/minecraft/dimension_type/overworld.json"
DEFAULT = (-64, 320)                  # (en alt Y, en üst Y) – üst sınır dahil değil: blok koyulabilen son Y = 319
LIMIT = 2032
PRESETS = [(N_("Varsayılan"), -64, 320), (N_("Yüksek"), -64, 640), (N_("Çok yüksek"), -64, 1024),
           (N_("Derin ve yüksek"), -512, 1024), (N_("En büyük"), -2032, 2032)]


class HeightError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def recommended_ram_gb(min_y, max_y):
    """Önerilen en az RAM (GB). Varsayılan yükseklikte 4 GB; parça (chunk) başına bellek yükseklikle artar ama boş
    gökyüzü bölümleri ucuz olduğu için doğrusal değil (~yükseklik^0,6)."""
    h = max(16, max_y - min_y)
    gb = 4 * (h / 384) ** 0.6
    return max(4, int(-(-gb // 1)))       # yukarı yuvarla


def parse_gb(ram):
    s = str(ram or "").strip().upper()
    try:
        if s.endswith("G"):
            return float(s[:-1])
        if s.endswith("M"):
            return float(s[:-1]) / 1024
        return float(s) / 1024 if s else 0
    except ValueError:
        return 0


def validate(min_y, max_y):
    if min_y % 16 or max_y % 16:
        raise HeightError(N_("En alt ve en üst Y 16'nın katı olmalı."))
    if min_y < -LIMIT or max_y > LIMIT:
        raise HeightError(N_("Yükseklik {lo} ile {hi} arasında olmalı."), lo=-LIMIT, hi=LIMIT)
    if max_y - min_y < 16:
        raise HeightError(N_("En üst Y, en alt Y'den en az 16 fazla olmalı."))


def _pack_dir(server_path, level):
    return os.path.join(server_path, level, "datapacks", PACK)


def current(server_path, level):
    """(min_y, max_y, paket_var_mı)"""
    p = os.path.join(_pack_dir(server_path, level), *ENTRY.split("/"))
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return int(d["min_y"]), int(d["min_y"]) + int(d["height"]), True
    except (OSError, ValueError, KeyError):
        return DEFAULT[0], DEFAULT[1], False


def _read_from_zip(z, depth=0):
    try:
        return z.read(ENTRY)
    except KeyError:
        pass
    if depth >= 1:
        return None
    for n in z.namelist():                # vanilla/Paper paketleyicisi: META-INF/versions/<v>/server-<v>.jar
        if n.endswith(".jar") and ("versions/" in n or "server" in n.lower()):
            try:
                with zipfile.ZipFile(io.BytesIO(z.read(n))) as inner:
                    data = _read_from_zip(inner, depth + 1)
                    if data:
                        return data
            except (zipfile.BadZipFile, KeyError):
                pass
    return None


def vanilla_dimension(server_path):
    """Sunucu klasöründeki jar'lardan oyunun overworld.json'u. Önce önbellekteki asıl oyun jar'ları denenir."""
    cands = []
    for sub in ("cache", "versions", os.path.join("libraries", "net", "minecraft"), ".fabric", ""):
        root = os.path.join(server_path, sub)
        if not os.path.isdir(root):
            continue
        depth0 = root.rstrip(os.sep).count(os.sep)
        for r, dirs, files in os.walk(root):
            if r.count(os.sep) - depth0 >= (0 if sub == "" else 5):
                dirs[:] = []
            if os.path.basename(r) in ("plugins", "mods", "backups", "world", "logs"):
                dirs[:] = []
                continue
            cands += [os.path.join(r, f) for f in files if f.endswith(".jar")]
    cands.sort(key=lambda p: (0 if "mojang" in p or "server-" in os.path.basename(p) else 1, -os.path.getsize(p)))
    for jar in cands:
        try:
            with zipfile.ZipFile(jar) as z:
                data = _read_from_zip(z)
            if data:
                return json.loads(data.decode("utf-8"))
        except (OSError, zipfile.BadZipFile, ValueError):
            continue
    raise HeightError(N_("Oyunun boyut tanımı sunucu dosyalarında bulunamadı. Sunucuyu bir kez başlatıp durdur, "
                         "sonra tekrar dene."))


def apply(server_path, level, min_y, max_y, pack_format=None):
    """Veri paketini yazar (ya da varsayılana dönülürse siler). Değişiklik sunucu yeniden başlayınca geçerli olur."""
    validate(min_y, max_y)
    d = _pack_dir(server_path, level)
    if (min_y, max_y) == DEFAULT:
        if os.path.isdir(d):
            shutil.rmtree(d)
        return None
    dim = vanilla_dimension(server_path)
    dim["min_y"] = min_y
    dim["height"] = max_y - min_y
    dim["logical_height"] = max_y - min_y
    os.makedirs(os.path.join(d, "data", "minecraft", "dimension_type"), exist_ok=True)
    with open(os.path.join(d, *ENTRY.split("/")), "w", encoding="utf-8") as f:
        json.dump(dim, f, indent=2)
    fmt = pack_format or 48
    with open(os.path.join(d, "pack.mcmeta"), "w", encoding="utf-8") as f:
        json.dump({"pack": {"description": f"Spypaper: build height {min_y}..{max_y - 1}", "pack_format": fmt,
                            "supported_formats": [fmt, 1000], "min_format": fmt, "max_format": 1000}}, f, indent=2)
    return d


def risks(old, new, world_exists):
    """Var olan dünyada riskli değişiklikler için uyarı şablonları."""
    out = []
    if not world_exists:
        return out
    if new[0] != old[0]:
        out.append(N_("En alt Y'yi değiştirmek var olan dünyada eski bölgelerin altını boş ya da bozuk bırakabilir."))
    if new[1] < old[1]:
        out.append(N_("Üst sınırı düşürmek, sınırın üstündeki yapıları siler."))
    return out
