"""Oluşmuş yapıları (köy, kale, antik şehir…) Java dünyasının bölge dosyalarından okuyup BlueMap'e işaret olarak yazar.

Yalnızca tamamen oluşmuş chunk'lardaki yapılar alınır: seed'den hesaplanmaz, keşfedilmemiş yerleri ele vermez.
İşaretler BlueMap'in harita ayarlarına (maps/*.conf) Spypaper'a ait bir 'marker-sets' bloğu olarak eklenir;
HOCON aynı anahtarlı nesneleri birleştirdiği için kullanıcının kendi işaret grupları bozulmaz.
"""
import glob
import io
import os
import re
import struct
import zlib

from . import N_

BEGIN = "# >>> Spypaper: yapılar (otomatik, elle düzenleme) >>>"
END = "# <<< Spypaper: yapılar <<<"
SET_ID = "spypaper-structures"

# Yapı türü -> (grup, görünen ad). Gruplar panelde seçilir; listede olmayanlar "other".
GROUPS = [
    ("village", N_("Köyler")), ("outpost", N_("Yağmacı karakolları")), ("mansion", N_("Orman konakları")),
    ("stronghold", N_("Kaleler (End portalı)")), ("ancient_city", N_("Antik şehirler")),
    ("trial", N_("Deneme odaları")), ("monument", N_("Okyanus anıtları")), ("temple", N_("Tapınaklar")),
    ("ruins", N_("Harabeler ve gemiler")), ("mineshaft", N_("Maden şaftları")),
    ("nether", N_("Nether kaleleri ve burçlar")), ("end_city", N_("End şehirleri")),
    ("portal", N_("Yıkık portallar")), ("other", N_("Diğer")),
]
DEFAULT_GROUPS = ["village", "outpost", "mansion", "stronghold", "ancient_city", "trial", "monument",
                  "temple", "nether", "end_city"]

NAMES = {
    "village": N_("Köy"), "pillager_outpost": N_("Yağmacı karakolu"), "mansion": N_("Orman konağı"),
    "stronghold": N_("Kale"), "ancient_city": N_("Antik şehir"), "trial_chambers": N_("Deneme odası"),
    "monument": N_("Okyanus anıtı"), "desert_pyramid": N_("Çöl tapınağı"), "jungle_pyramid": N_("Orman tapınağı"),
    "swamp_hut": N_("Cadı kulübesi"), "igloo": N_("İglo"), "ocean_ruin": N_("Okyanus harabesi"),
    "shipwreck": N_("Gemi enkazı"), "buried_treasure": N_("Gömülü hazine"), "trail_ruins": N_("İz harabesi"),
    "mineshaft": N_("Maden şaftı"), "fortress": N_("Nether kalesi"), "bastion_remnant": N_("Burç kalıntısı"),
    "end_city": N_("End şehri"), "ruined_portal": N_("Yıkık portal"), "abandoned_camp": N_("Terk edilmiş kamp"),
}


def kind(sid):
    """'minecraft:village_plains' -> ('village', 'village')"""
    s = sid.split(":", 1)[-1]
    for base in sorted(NAMES, key=len, reverse=True):
        if s == base or s.startswith(base + "_"):
            break
    else:
        base = s
    group = {"village": "village", "pillager_outpost": "outpost", "mansion": "mansion", "stronghold": "stronghold",
             "ancient_city": "ancient_city", "trial_chambers": "trial", "monument": "monument",
             "desert_pyramid": "temple", "jungle_pyramid": "temple", "swamp_hut": "temple", "igloo": "temple",
             "ocean_ruin": "ruins", "shipwreck": "ruins", "buried_treasure": "ruins", "trail_ruins": "ruins",
             "mineshaft": "mineshaft", "fortress": "nether", "bastion_remnant": "nether",
             "end_city": "end_city", "ruined_portal": "portal"}.get(base, "other")
    return base, group


# ------------------------------------------------------------------ bölge dosyaları
def _chunks(path):
    """Bir .mca dosyasındaki chunk'ların ham NBT baytları."""
    try:
        with open(path, "rb") as f:
            b = f.read()
    except OSError:
        return
    if len(b) < 8192:
        return
    for i in range(1024):
        off = int.from_bytes(b[i * 4:i * 4 + 3], "big") * 4096
        if not off or off + 5 > len(b):
            continue
        ln = struct.unpack(">I", b[off:off + 4])[0]
        comp = b[off + 4]
        data = b[off + 5:off + 4 + ln]
        try:
            if comp == 2:
                yield zlib.decompress(data)
            elif comp == 1:
                import gzip
                yield gzip.decompress(data)
            elif comp == 3:
                yield data
        except Exception:
            continue


def _quick_has_start(raw):
    # çoğu chunk'ta yapı başlangıcı yok: NBT'yi ayrıştırmadan önce ucuz bir ön eleme
    return b"ChunkX" in raw


def scan_region_dir(region_dir):
    """[(id, x, y, z)] — yalnızca tamamen oluşmuş chunk'lardaki yapı başlangıçları."""
    import nbtlib
    out = []
    for path in glob.glob(os.path.join(region_dir, "r.*.mca")):
        for raw in _chunks(path):
            if not _quick_has_start(raw):
                continue
            try:
                n = nbtlib.File.parse(io.BytesIO(raw))
            except Exception:
                continue
            if str(n.get("Status", "")).split(":")[-1] != "full":
                continue
            starts = (n.get("structures") or n.get("Structures") or {}).get("starts") or \
                     (n.get("structures") or n.get("Structures") or {}).get("Starts") or {}
            for sid, v in starts.items():
                if str(v.get("id", sid)) == "INVALID":
                    continue
                bbs = [list(map(int, c["BB"])) for c in v.get("Children", []) if "BB" in c]
                if bbs:
                    x0, y0, z0 = min(b[0] for b in bbs), min(b[1] for b in bbs), min(b[2] for b in bbs)
                    x1, y1, z1 = max(b[3] for b in bbs), max(b[4] for b in bbs), max(b[5] for b in bbs)
                    x, y, z = (x0 + x1) // 2, y1, (z0 + z1) // 2
                else:
                    x, y, z = int(v.get("ChunkX", 0)) * 16 + 8, 64, int(v.get("ChunkZ", 0)) * 16 + 8
                out.append((str(v.get("id", sid)), x, y, z))
    return out


# ------------------------------------------------------------------ BlueMap haritaları
def _conf(path, key):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            txt = _strip_block(f.read())
    except OSError:
        return None
    m = re.search(rf'^\s*{key}\s*[:=]\s*"([^"]*)"', txt, re.M)
    return m.group(1) if m else None


def region_dir(server_path, world, dimension):
    base = os.path.join(server_path, world)
    dim = (dimension or "minecraft:overworld").split(":")[-1]
    cand = {
        "overworld": [os.path.join(base, "dimensions", "minecraft", "overworld", "region"), os.path.join(base, "region")],
        "the_nether": [os.path.join(base, "dimensions", "minecraft", "the_nether", "region"),
                       os.path.join(base, "DIM-1", "region")],
        "the_end": [os.path.join(base, "dimensions", "minecraft", "the_end", "region"),
                    os.path.join(base, "DIM1", "region")],
    }.get(dim, [os.path.join(base, "dimensions", *(dimension or "").split(":"), "region")])
    for p in cand:
        if os.path.isdir(p):
            return p
    return None


def maps(server_path):
    """[(conf_path, region_dir)] BlueMap'in tanımlı haritaları."""
    from .bluemap import config_dir
    cfg = config_dir(server_path)
    out = []
    if not cfg:
        return out
    for conf in sorted(glob.glob(os.path.join(cfg, "maps", "*.conf"))):
        world = _conf(conf, "world")
        if not world:
            continue
        rd = region_dir(server_path, world, _conf(conf, "dimension"))
        if rd:
            out.append((conf, rd))
    return out


def _strip_block(txt):
    i, j = txt.find(BEGIN), txt.find(END)
    if i >= 0 and j > i:
        txt = txt[:i].rstrip("\n") + "\n" + txt[j + len(END):].lstrip("\n")
    return txt


def _q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _block(items, tr, set_label):
    lines = [BEGIN, "marker-sets: {", f"  {SET_ID}: {{", f"    label: {_q(set_label)}",
             "    toggleable: true", "    default-hidden: false", "    sorting: 10", "    markers: {"]
    for i, (sid, x, y, z) in enumerate(sorted(items, key=lambda s: (s[0], s[1], s[3]))):
        base, _g = kind(sid)
        name = tr(NAMES[base]) if base in NAMES else sid.split(":")[-1].replace("_", " ").title()
        lines += [f"      s{i}: {{", '        type: "poi"', f"        label: {_q(name)}",
                  f"        detail: {_q(f'{name}<br>{x}, {y}, {z}')}",
                  f"        position: {{ x: {x}, y: {y}, z: {z} }}", "        max-distance: 100000", "      }"]
    lines += ["    }", "  }", "}", END]
    return "\n".join(lines) + "\n"


def write_markers(conf, items, tr=lambda s: s, set_label="Yapılar"):
    with open(conf, encoding="utf-8", errors="ignore") as f:
        txt = _strip_block(f.read())
    if items is not None:
        txt = txt.rstrip("\n") + "\n\n" + _block(items, tr, set_label)
    tmp = conf + ".spypaper.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(txt)
    os.replace(tmp, conf)


def update(server_path, groups, tr=lambda s: s, set_label="Yapılar", enabled=True):
    """Tüm BlueMap haritalarındaki yapı işaretlerini yeniler. {harita adı: işaret sayısı} döner."""
    res = {}
    for conf, rd in maps(server_path):
        if not enabled:
            write_markers(conf, None)
            continue
        items = [s for s in scan_region_dir(rd) if kind(s[0])[1] in groups]
        write_markers(conf, items, tr, set_label)
        res[os.path.splitext(os.path.basename(conf))[0]] = len(items)
    return res
