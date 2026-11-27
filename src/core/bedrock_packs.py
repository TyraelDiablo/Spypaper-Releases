"""Bedrock add-on'ları: davranış (behavior) ve kaynak (resource) paketleri.

Paket klasörleri: behavior_packs, resource_packs (ve development_* eşleri). Her paketin manifest.json'u vardır.
Bir paketin dünyada açık olması: worlds/<dünya>/world_behavior_packs.json / world_resource_packs.json.
Marketplace paketleri şifrelidir (hesaba bağlı); BDS onları yükleyemez, Spypaper yalnızca işaretler.
"""
import json
import os
import re
import shutil
import tempfile
import zipfile

from .config import N_

KINDS = {"behavior": "behavior_packs", "resource": "resource_packs"}
DEV = {"behavior": "development_behavior_packs", "resource": "development_resource_packs"}
WORLD_FILE = {"behavior": "world_behavior_packs.json", "resource": "world_resource_packs.json"}
ENCRYPTED_MAGIC = b"\xfc\xb9\xcf\x9b"           # Marketplace contents.json başlığı
MAX_UNZIP = 1024 * 1024 * 1024                  # 1 GB: zip bombasına karşı


class PackError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def _loads(text):
    """manifest.json'larda sık görülen // ve /* */ yorumlarını ve sondaki virgülleri tolere eder."""
    try:
        return json.loads(text)
    except ValueError:
        pass
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return json.loads(re.sub(r",\s*([}\]])", r"\1", "".join(out)))


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return _loads(f.read())
    except (OSError, ValueError):
        return default


def _ver(v):
    if isinstance(v, list):
        return [int(x) for x in v[:3]] + [0] * (3 - len(v[:3]))
    if isinstance(v, str):
        return [int(x) for x in (re.findall(r"\d+", v) + ["0", "0", "0"])[:3]]
    return [0, 0, 0]


def ver_text(v):
    return ".".join(str(x) for x in _ver(v))


def kind_of(manifest):
    types = {(m.get("type") or "").lower() for m in (manifest.get("modules") or []) if isinstance(m, dict)}
    if types & {"data", "script", "client_data", "javascript"}:
        return "behavior"
    if "resources" in types:
        return "resource"
    if "world_template" in types:
        return "world_template"
    if "skin_pack" in types:
        return "skin_pack"
    return ""


def uses_beta_api(manifest):
    for d in manifest.get("dependencies") or []:
        if isinstance(d, dict) and d.get("module_name") and "beta" in str(d.get("version", "")):
            return True
    return False


def _pack_info(folder, kind, dev=False):
    man = _read_json(os.path.join(folder, "manifest.json"))
    enc = False
    try:
        with open(os.path.join(folder, "contents.json"), "rb") as f:
            enc = f.read(4) == ENCRYPTED_MAGIC
    except OSError:
        pass
    if not isinstance(man, dict):
        return {"folder": folder, "kind": kind, "name": os.path.basename(folder), "uuid": "", "version": [0, 0, 0],
                "description": "", "deps": [], "encrypted": enc, "broken": not enc, "dev": dev, "beta": False}
    h = man.get("header") or {}
    deps = [d.get("uuid") for d in (man.get("dependencies") or []) if isinstance(d, dict) and d.get("uuid")]
    return {"folder": folder, "kind": kind, "name": str(h.get("name") or os.path.basename(folder)),
            "uuid": str(h.get("uuid") or ""), "version": _ver(h.get("version")),
            "description": str(h.get("description") or ""), "deps": deps, "encrypted": enc,
            "broken": False, "dev": dev, "beta": uses_beta_api(man),
            "min_engine": ver_text(h.get("min_engine_version")) if h.get("min_engine_version") else ""}


def list_packs(server_path):
    out = []
    for kind in KINDS:
        for base, dev in ((KINDS[kind], False), (DEV[kind], True)):
            root = os.path.join(server_path, base)
            try:
                names = sorted(os.listdir(root), key=str.lower)
            except OSError:
                continue
            for n in names:
                p = os.path.join(root, n)
                if os.path.isdir(p) and (os.path.isfile(os.path.join(p, "manifest.json"))
                                         or os.path.isfile(os.path.join(p, "contents.json"))):
                    out.append(_pack_info(p, kind, dev))
    return out


# ------------------------------------------------------------------ dünyada açık olanlar
def world_dir(server_path):
    from .bedrock import level_name
    return os.path.join(server_path, "worlds", level_name(server_path))


def enabled(server_path, kind):
    data = _read_json(os.path.join(world_dir(server_path), WORLD_FILE[kind]), [])
    return [d for d in data if isinstance(d, dict) and d.get("pack_id")] if isinstance(data, list) else []


def _write_enabled(server_path, kind, items):
    d = world_dir(server_path)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, WORLD_FILE[kind])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, p)


def set_enabled(server_path, pack, on):
    items = [d for d in enabled(server_path, pack["kind"]) if d.get("pack_id") != pack["uuid"]]
    if on:
        items.insert(0, {"pack_id": pack["uuid"], "version": list(pack["version"])})   # üstteki önceliklidir
    _write_enabled(server_path, pack["kind"], items)


def move(server_path, pack, delta):
    items = enabled(server_path, pack["kind"])
    i = next((k for k, d in enumerate(items) if d.get("pack_id") == pack["uuid"]), None)
    if i is None:
        return False
    j = max(0, min(len(items) - 1, i + delta))
    items.insert(j, items.pop(i))
    _write_enabled(server_path, pack["kind"], items)
    return True


def missing_deps(packs, pack):
    have = {p["uuid"] for p in packs}
    return [u for u in pack["deps"] if u not in have]


def remove(server_path, pack):
    for kind in KINDS:
        if pack["uuid"]:
            items = [d for d in enabled(server_path, kind) if d.get("pack_id") != pack["uuid"]]
            if items != enabled(server_path, kind):
                _write_enabled(server_path, kind, items)
    root = os.path.realpath(server_path)
    target = os.path.realpath(pack["folder"])
    if not target.startswith(root + os.sep):
        raise PackError(N_("Paket klasörü sunucu klasörünün dışında; silinmedi."))
    shutil.rmtree(target)


# ------------------------------------------------------------------ kurulum
def _safe_extract(z, dest):
    total = 0
    root = os.path.realpath(dest)
    for m in z.infolist():
        name = m.filename.replace("\\", "/")
        if not name or name.startswith("/") or ".." in name.split("/"):
            continue
        total += m.file_size
        if total > MAX_UNZIP:
            raise PackError(N_("Paket çok büyük (açılmış hali 1 GB'ı geçiyor)."))
        out = os.path.realpath(os.path.join(dest, name))
        if not out.startswith(root + os.sep) and out != root:
            continue
        if m.is_dir():
            os.makedirs(out, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with z.open(m) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _find_manifests(root):
    found = []
    for dirpath, dirs, files in os.walk(root):
        if "manifest.json" in files:
            found.append(dirpath)
            dirs[:] = []                       # paketin içindeki alt klasörlere inme
    return found


def _slug(name):
    s = re.sub(r"§.", "", name)
    s = re.sub(r"[^\w .-]+", "", s, flags=re.UNICODE).strip(" .")
    return s[:48] or "pack"


def install_file(server_path, file_path, enable=True):
    """.mcpack / .mcaddon / .zip kurar. Kurulan paketlerin listesini döndürür."""
    if not zipfile.is_zipfile(file_path):
        raise PackError(N_("Bu bir Bedrock paketi değil (.mcpack / .mcaddon olmalı)."))
    work = tempfile.mkdtemp(prefix="spypaper-pack-")
    try:
        with zipfile.ZipFile(file_path) as z:
            _safe_extract(z, work)
        for dp, _, files in list(os.walk(work)):          # .mcaddon içinde .mcpack'ler olabilir
            for f in files:
                if f.lower().endswith((".mcpack", ".mcaddon")):
                    inner = os.path.join(dp, f)
                    sub = inner + "_x"
                    os.makedirs(sub, exist_ok=True)
                    try:
                        with zipfile.ZipFile(inner) as z:
                            _safe_extract(z, sub)
                    except zipfile.BadZipFile:
                        pass
        dirs = _find_manifests(work)
        if not dirs:
            raise PackError(N_("Paketin içinde manifest.json bulunamadı."))
        installed, skipped = [], []
        for d in dirs:
            if os.path.isfile(os.path.join(d, "contents.json")):
                with open(os.path.join(d, "contents.json"), "rb") as f:
                    if f.read(4) == ENCRYPTED_MAGIC:
                        raise PackError(N_("Bu bir Marketplace paketi (şifreli). Bedrock sunucusu şifreli paketleri yükleyemez."))
            man = _read_json(os.path.join(d, "manifest.json"))
            if not isinstance(man, dict):
                raise PackError(N_("manifest.json okunamadı."))
            kind = kind_of(man)
            if kind not in KINDS:
                skipped.append(kind or "?")
                continue
            h = man.get("header") or {}
            uuid = str(h.get("uuid") or "")
            folder_name = f"{_slug(str(h.get('name') or 'pack'))}_{uuid[:8]}"
            dest = os.path.join(server_path, KINDS[kind], folder_name)
            if os.path.isdir(dest):
                shutil.rmtree(dest)                              # aynı paketin eski sürümü
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copytree(d, dest)
            info = _pack_info(dest, kind)
            if enable and uuid:
                set_enabled(server_path, info, True)
            installed.append(info)
        if not installed:
            raise PackError(N_("Pakette sunucuya kurulabilecek bir davranış ya da kaynak paketi yok (ör. yalnızca skin paketi)."))
        return installed
    finally:
        shutil.rmtree(work, ignore_errors=True)


def texture_required(server_path):
    try:
        with open(os.path.join(server_path, "server.properties"), encoding="utf-8") as f:
            return any(ln.strip() == "texturepack-required=true" for ln in f)
    except OSError:
        return False


def set_texture_required(server_path, on):
    from .bedrock import set_properties
    set_properties(server_path, {"texturepack-required": "true" if on else "false"})
