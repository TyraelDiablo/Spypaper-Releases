"""Minecraft'ın kendi dil dosyaları ve eşya ikonları (Translation/ ve Icons/ klasörleri).

Bu dosyalar Mojang'a aittir, bu yüzden Spypaper ile dağıtılmaz. Her kullanıcı kendi bilgisayarında alır:
  1) Bilgisayardaki Minecraft kurulumundan (.minecraft) çıkarma — internet gerekmez.
  2) Kurulum yoksa, kullanıcının onayıyla Mojang'ın resmî sunucularından indirme
     (istemci jar'ı + asset index; BlueMap'in de kullandığı yöntem).

Minecraft dil dosyaları iki yerde durur:
  * en_us.json  -> istemci jar'ının içinde (assets/minecraft/lang/en_us.json)
  * diğerleri   -> assets/objects/<xx>/<hash>   (adlar assets/indexes/<index>.json içinde)
İkonlar istemci jar'ındaki assets/minecraft/textures/item ve textures/block klasörlerindedir.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile

from . import updater
from .config import N_, get_base_dir

PANEL_LANGS = ["tr_tr", "en_us", "de_de", "fr_fr", "es_es", "pt_br", "it_it", "nl_nl", "pl_pl",
               "ru_ru", "uk_ua", "az_az", "ja_jp", "ko_kr", "zh_cn", "ar_sa"]
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
RESOURCES = "https://resources.download.minecraft.net"
ICON_RE = re.compile(r"assets/minecraft/textures/(item|block)/([a-z0-9_]+)\.png$")
# can/açlık/zırh/XP göstergeleri (1.20.2+ sprite düzeni) -> Icons/hud/heart_full.png gibi
HUD_RE = re.compile(r"assets/minecraft/textures/gui/sprites/hud/((?:heart/(?:container|full|half|absorbing_full|absorbing_half))"
                    r"|food_(?:empty|full|half)|armor_(?:empty|full|half)|experience_bar_(?:background|progress))\.png$")
LANG_RE = re.compile(r"minecraft/lang/([a-z0-9_]+)\.json$")


def dest_dirs(base=None):
    base = base or get_base_dir()
    return os.path.join(base, "Translation"), os.path.join(base, "Icons")


def status(base=None):
    """{"langs": [...], "icons": sayı, "translation": yol, "icons_dir": yol}"""
    tdir, idir = dest_dirs(base)
    langs = sorted(f[:-5] for f in os.listdir(tdir) if f.endswith(".json")) if os.path.isdir(tdir) else []
    icons = sum(len(fs) for _, _, fs in os.walk(idir)) if os.path.isdir(idir) else 0
    return {"langs": langs, "icons": icons, "translation": tdir, "icons_dir": idir}


# ------------------------------------------------------------------ yerel kurulum
def default_mc_dir():
    home = os.path.expanduser("~")
    for p in (os.path.join(os.environ.get("APPDATA", ""), ".minecraft"),
              os.path.join(home, "Library", "Application Support", "minecraft"),
              os.path.join(home, ".minecraft")):
        if p and os.path.isdir(p):
            return p
    return None


def _vkey(name):
    nums = re.findall(r"\d+", name)
    return tuple(int(n) for n in nums) if re.match(r"^\d+\.\d+", name) else (0,)


def local_versions(mc):
    """Kurulu (jar'ı olan) temel sürümler: [(sürüm, jar, index_adı, tür)] en yeni önce."""
    vdir = os.path.join(mc or "", "versions")
    out = []
    if not os.path.isdir(vdir):
        return out
    for v in os.listdir(vdir):
        js, jar = os.path.join(vdir, v, f"{v}.json"), os.path.join(vdir, v, f"{v}.jar")
        if not (os.path.exists(js) and os.path.exists(jar)):
            continue
        try:
            with open(js, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        if meta.get("inheritsFrom"):              # Fabric/Forge profilleri: temel sürüm ayrıca listelenir
            continue
        idx = (meta.get("assetIndex") or {}).get("id") or meta.get("assets")
        out.append((v, jar, idx, meta.get("type", "")))
    return sorted(out, key=lambda c: (c[3] == "release", _vkey(c[0])), reverse=True)


def pick_local(mc, wanted=None):
    vers = local_versions(mc)
    if wanted:
        exact = [v for v in vers if v[0] == wanted]
        if exact:
            return exact[0]
    return vers[0] if vers else None


def _write_icons(jar, idir, progress=None):
    """Düz dokular (Icons/item, Icons/block) + modellerden çizilen envanter ikonları (Icons/items)."""
    n = 0
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            h = HUD_RE.match(name)
            if h:
                os.makedirs(os.path.join(idir, "hud"), exist_ok=True)
                with open(os.path.join(idir, "hud", h.group(1).replace("/", "_") + ".png"), "wb") as f:
                    f.write(z.read(name))
                continue
            m = ICON_RE.match(name)
            if m:
                d = os.path.join(idir, m.group(1))
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, m.group(2) + ".png"), "wb") as f:
                    f.write(z.read(name))
                n += 1
    try:
        from .iconrender import render_all
        n += render_all(jar, os.path.join(idir, "items"), progress)
    except Exception:
        pass                        # çizim olmasa da düz dokular kullanılabilir
    return n


def _write_en(jar, tdir):
    with zipfile.ZipFile(jar) as z:
        data = z.read("assets/minecraft/lang/en_us.json")
    with open(os.path.join(tdir, "en_us.json"), "wb") as f:
        f.write(data)


def extract_local(mc, version, langs=None, icons=True, base=None, log=None):
    """.minecraft'tan çıkarır. langs=None: tüm diller. (dil_sayısı, ikon_sayısı, eksik_diller) döndürür."""
    found = pick_local(mc, version)
    if not found:
        raise updater.UpdateError(N_("Bu bilgisayardaki Minecraft kurulumunda sürüm bulunamadı. Oyunu launcher'dan bir kez aç."))
    ver, jar, idx, _ = found
    tdir, idir = dest_dirs(base)
    os.makedirs(tdir, exist_ok=True)
    log = log or (lambda s: None)
    log(f"{mc} · {ver}")
    want = set(langs) if langs else None
    done = set()
    n_icons = _write_icons(jar, idir) if icons else 0
    if want is None or "en_us" in want:
        _write_en(jar, tdir)
        done.add("en_us")
    index = os.path.join(mc, "assets", "indexes", f"{idx}.json")
    if os.path.exists(index):
        with open(index, encoding="utf-8") as f:
            objects = json.load(f).get("objects", {})
        for name, info in objects.items():
            m = LANG_RE.match(name)
            if not m or (want is not None and m.group(1) not in want):
                continue
            src = os.path.join(mc, "assets", "objects", info["hash"][:2], info["hash"])
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(tdir, f"{m.group(1)}.json"))
                done.add(m.group(1))
    missing = sorted(want - done) if want else []
    return len(done), n_icons, missing, ver


# ------------------------------------------------------------------ Mojang'dan indirme
def _download(url, path_or_none, contact, sha1=None, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": updater.user_agent(contact)})
    h = hashlib.sha1()
    chunks = []
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            out = open(path_or_none, "wb") if path_or_none else None
            try:
                while True:
                    c = r.read(65536)
                    if not c:
                        break
                    h.update(c)
                    (out.write(c) if out else chunks.append(c))
                    done += len(c)
                    if progress:
                        progress(done, total)
            finally:
                if out:
                    out.close()
    except Exception as e:
        raise updater.UpdateError(N_("İndirme başarısız: {e}"), e=updater.net_reason(e))
    if sha1 and h.hexdigest() != sha1:
        raise updater.UpdateError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo="SHA1")
    return None if path_or_none else b"".join(chunks)


def mojang_version(version, contact=""):
    """Mojang listesinde sürüm: tam eşleşme yoksa en yeni yayın. (sürüm, meta) döndürür."""
    man = updater._get_json(MANIFEST, contact)
    vers = man.get("versions", [])
    entry = next((v for v in vers if v["id"] == version), None) if version else None
    if not entry:
        latest = (man.get("latest") or {}).get("release")
        entry = next((v for v in vers if v["id"] == latest), None)
    if not entry:
        raise updater.UpdateError(N_("{v} sürümü bulunamadı."), v=version or "?")
    return entry["id"], updater._get_json(entry["url"], contact)


def download_mojang(version, langs=None, icons=True, base=None, contact="", progress=None, log=None):
    """Mojang'ın sunucularından istemci jar'ını (yalnızca geçici olarak) ve dil dosyalarını indirir."""
    log = log or (lambda s: None)
    ver, meta = mojang_version(version, contact)
    tdir, idir = dest_dirs(base)
    os.makedirs(tdir, exist_ok=True)
    want = set(langs) if langs else None
    done = set()
    client = (meta.get("downloads") or {}).get("client")
    tmp = tempfile.NamedTemporaryFile(suffix=".jar", delete=False)
    tmp.close()
    try:
        log(f"Minecraft {ver}: client.jar")
        _download(client["url"], tmp.name, contact, client.get("sha1"), progress)
        n_icons = _write_icons(tmp.name, idir) if icons else 0
        if want is None or "en_us" in want:
            _write_en(tmp.name, tdir)
            done.add("en_us")
    finally:
        try:
            os.remove(tmp.name)                      # Mojang'ın jar'ı saklanmaz
        except OSError:
            pass
    index = updater._get_json(meta["assetIndex"]["url"], contact).get("objects", {})
    items = [(LANG_RE.match(n).group(1), i) for n, i in index.items()
             if LANG_RE.match(n) and (want is None or LANG_RE.match(n).group(1) in want)]
    for k, (code, info) in enumerate(sorted(items)):
        h = info["hash"]
        log(f"{code}.json")
        data = _download(f"{RESOURCES}/{h[:2]}/{h}", None, contact, h)
        with open(os.path.join(tdir, f"{code}.json"), "wb") as f:
            f.write(data)
        done.add(code)
        if progress:
            progress(k + 1, len(items))
    missing = sorted(want - done) if want else []
    return len(done), n_icons, missing, ver
