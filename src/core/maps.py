"""Hazır harita taslakları (Skyblock, PvP arenaları...).

Haritaların bir kısmı exe'nin içine gömülüdür (src/maps/: maps.json, zip'ler ve görseller); internet olmadan da
çalışır. Ek haritalar Spypaper-Releases deposundaki "haritalar" sürümünden okunur ve listeye eklenir (gömülü
olanla aynı kimlikte bir harita varsa gömülü olan kullanılır). Çevrimiçi liste alınamazsa sessizce gömülülerle
devam edilir. Çevrimiçi sürümdeki dosyalar:
  maps.json            harita listesi (aşağıdaki biçim)
  <id>.zip             dünya klasörü (içinde level.dat)
  <id>.png / .jpg      kart görseli
Yeni harita eklemek için Spypaper'ı güncellemek gerekmez: zip ve görseli yükleyip maps.json'a bir kayıt eklemek yeter.

maps.json:
{"maps": [{"id": "skyblock", "category": "skyblock", "mc": "26.3",
           "name": {"tr": "...", "en": "..."}, "desc": {"tr": "...", "en": "..."},
           "zip": "skyblock.zip", "sha256": "...", "size": 123, "image": "skyblock.png",
           "properties": {"gamemode": "adventure", ...}}]}
Dosya adları maps.json'un bulunduğu adrese göre çözülür.
"""
import hashlib
import json
import os
import random
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime

from .config import N_, get_base_dir, resource_dir
from . import updater

BASE = "https://github.com/TyraelDiablo/Spypaper-Releases/releases/download/haritalar/"
MANIFEST = BASE + "maps.json"
LEVEL_TYPES = [("minecraft:normal", N_("Normal")), ("minecraft:flat", N_("Düz")),
               ("minecraft:large_biomes", N_("Geniş biyomlar")), ("minecraft:amplified", N_("Büyütülmüş (Amplified)"))]
# taslak haritanın değiştirebileceği server.properties anahtarları (başka hiçbir şeye dokunulmaz)
ALLOWED_PROPS = {"gamemode", "force-gamemode", "difficulty", "pvp", "spawn-protection", "allow-nether", "generate-structures",
                 "spawn-monsters", "allow-flight", "level-type", "max-players"}
MAX_ZIP = 300 * 1024 * 1024          # bayt; açılmış dünya için üst sınır


class MapError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def random_seed():
    return str(random.randint(-(2 ** 63), 2 ** 63 - 1))


def cache_dir():
    d = os.path.join(get_base_dir(), "cache", "maps")
    os.makedirs(d, exist_ok=True)
    return d


def _url(name, base=BASE):
    return name if re.match(r"^https?://", name or "") else urllib.parse.urljoin(base, name or "")


def text(field, lang):
    """{'tr': .., 'en': ..} -> panel dilindeki metin (yoksa İngilizce, o da yoksa Türkçe)."""
    if isinstance(field, str):
        return field
    field = field or {}
    lang = (lang or "").lower()
    return field.get(lang) or field.get(lang.split("_")[0]) or field.get("en") or field.get("tr") or ""


def _valid(m):
    return (isinstance(m, dict) and re.fullmatch(r"[a-z0-9_\-]{1,40}", str(m.get("id", "")))
            and m.get("zip") and re.fullmatch(r"[0-9a-fA-F]{64}", str(m.get("sha256", ""))))


def builtin(folder=None):
    """Exe'ye gömülü haritalar."""
    folder = folder or os.path.join(resource_dir(), "maps")
    try:
        with open(os.path.join(folder, "maps.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for m in data.get("maps") or []:
        if _valid(m) and os.path.isfile(os.path.join(folder, os.path.basename(m["zip"]))):
            m["_local"] = folder
            out.append(m)
    return out


def fetch_manifest(contact="", url=MANIFEST, local=None):
    """Gömülü + çevrimiçi haritalar. Gömülü harita varken çevrimiçi hata yutulur."""
    maps = builtin(local)
    try:
        data = updater._get_json(url, contact)
    except Exception:
        if maps:
            return maps
        raise
    have = {m["id"] for m in maps}
    for m in data.get("maps") or []:
        if _valid(m) and m["id"] not in have:
            m["_base"] = url.rsplit("/", 1)[0] + "/"
            maps.append(m)
    return maps


def image_path(m, contact=""):
    """Kart görselini önbelleğe indirir; yolunu ya da None döndürür."""
    img = m.get("image")
    if not img:
        return None
    if m.get("_local"):
        p = os.path.join(m["_local"], os.path.basename(img))
        return p if os.path.isfile(p) else None
    ext = os.path.splitext(urllib.parse.urlparse(img).path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        return None
    p = os.path.join(cache_dir(), f"{m['id']}-{hashlib.sha1(img.encode()).hexdigest()[:8]}{ext}")
    if os.path.exists(p):
        return p
    try:
        req = urllib.request.Request(_url(img, m.get("_base", BASE)),
                                     headers={"User-Agent": updater.user_agent(contact)})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            return None
        with open(p + ".part", "wb") as f:
            f.write(data)
        os.replace(p + ".part", p)
        return p
    except Exception:
        return None


def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def compatible(m, server_version):
    """Harita, sunucu sürümünde açılabilir mi? (eski dünya yeni sürümde açılır; tersi olmaz)"""
    return not server_version or not m.get("mc") or _vkey(server_version) >= _vkey(m["mc"])


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(m, contact="", progress=None):
    """Zip'i indirir (gömülüyse diskten alır) ve SHA-256 ile doğrular. (yol, geçici_mi)"""
    if m.get("_local"):
        p = os.path.join(m["_local"], os.path.basename(m["zip"]))
        if _sha256(p).lower() != m["sha256"].lower():
            raise MapError(N_("Harita doğrulanamadı (SHA-256 uyuşmuyor)."))
        if progress:
            size = os.path.getsize(p)
            progress(size, size)
        return p, False
    fd, tmp = tempfile.mkstemp(prefix="spypaper_map_", suffix=".zip")
    os.close(fd)
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(_url(m["zip"], m.get("_base", BASE)),
                                     headers={"User-Agent": updater.user_agent(contact)})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or m.get("size") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_ZIP:
                    raise MapError(N_("Harita dosyası çok büyük."))
                f.write(chunk)
                h.update(chunk)
                if progress:
                    progress(got, total)
    except MapError:
        os.remove(tmp)
        raise
    except Exception as e:
        os.remove(tmp)
        raise MapError(N_("Harita indirilemedi: {e}"), e=updater.net_reason(e))
    if h.hexdigest().lower() != m["sha256"].lower():
        os.remove(tmp)
        raise MapError(N_("Harita doğrulanamadı (SHA-256 uyuşmuyor)."))
    return tmp, True


def extract_world(zip_path, dest):
    """Zip içindeki dünyayı (level.dat'ın bulunduğu klasör) dest klasörüne açar. dest var olmamalı."""
    if os.path.exists(dest):
        raise MapError(N_("Hedef klasör zaten var: {path}"), path=dest)
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if sum(i.file_size for i in z.infolist()) > MAX_ZIP:
            raise MapError(N_("Harita dosyası çok büyük."))
        roots = [n[:-len("level.dat")] for n in names if n == "level.dat" or n.endswith("/level.dat")]
        if not roots:
            raise MapError(N_("Zip içinde dünya bulunamadı (level.dat yok)."))
        root = min(roots, key=len)
        tmpdir = dest + ".part"
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)
        os.makedirs(tmpdir)
        base = os.path.realpath(tmpdir)
        for n in names:
            if not n.startswith(root):
                continue
            rel = n[len(root):]
            if not rel or rel.startswith(("players/", "playerdata/")) or rel in ("session.lock",):
                continue
            out = os.path.realpath(os.path.join(tmpdir, *rel.split("/")))
            if not out.startswith(base + os.sep):            # zip-slip koruması
                raise MapError(N_("Zip dosyası geçersiz yol içeriyor."))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, "wb") as f:
                shutil.copyfileobj(src, f)
        os.replace(tmpdir, dest)
    return dest


def apply_properties(props_path, overrides):
    """server.properties'te yalnızca izin verilen anahtarları değiştirir/ekler."""
    overrides = {k: str(v) for k, v in (overrides or {}).items() if k in ALLOWED_PROPS}
    if not overrides:
        return {}
    lines = []
    if os.path.exists(props_path):
        with open(props_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = set()
    for i, ln in enumerate(lines):
        k = ln.split("=", 1)[0].strip()
        if k in overrides and not ln.lstrip().startswith("#"):
            lines[i] = f"{k}={overrides[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in overrides.items() if k not in done]
    with open(props_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return overrides


def install(m, server_path, level="world", contact="", progress=None, replace=False):
    """Haritayı sunucuya kurar. replace=True: mevcut dünya (Bukkit/Paper'daki <level>_nether ve <level>_the_end dahil)
    önce "-yedek-<tarih>" ekiyle yeniden adlandırılır. (yedeklenen_klasörler, uygulanan_ayarlar)"""
    if not level or os.path.isabs(level) or ".." in level.replace("\\", "/").split("/"):
        raise MapError(N_("level-name geçersiz: {name}"), name=level)
    dest = os.path.join(server_path, level)
    if os.path.exists(dest) and not replace:
        raise MapError(N_("Hedef klasör zaten var: {path}"), path=dest)
    zip_path, is_tmp = download(m, contact, progress)
    moved = []
    stamp = f"-yedek-{datetime.now():%Y%m%d-%H%M%S}"
    try:
        if replace:
            for d in (dest, dest + "_nether", dest + "_the_end"):
                if os.path.exists(d):
                    os.replace(d, d + stamp)
                    moved.append(d)
        try:
            extract_world(zip_path, dest)
        except Exception:
            if os.path.exists(dest + ".part"):
                shutil.rmtree(dest + ".part", ignore_errors=True)
            for d in moved:                                # açılamadı: eski dünyayı geri koy
                if not os.path.exists(d):
                    os.replace(d + stamp, d)
            moved = []
            raise
    finally:
        if is_tmp:
            os.remove(zip_path)
    applied = apply_properties(os.path.join(server_path, "server.properties"), m.get("properties"))
    return [os.path.basename(d) + stamp for d in moved], applied
