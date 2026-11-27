"""Sunucu şablonu (.spytemplate): bir sunucunun ayarlarını başka bir sunucuya taşımak için.

İçinde: server.properties (portlar, IP, seed, RCON parolası hariç), eklenti/mod listesi (Modrinth'te bulunanlar
sürümüyle), eklenti/mod ayar dosyaları (yalnızca metin; .jar yok) ve Spypaper ayarları (zamanlanmış görevler,
bakım planı, hile koruması, RAM, güvenli mod, çökme bekçisi). Dünya, oyuncu verisi, oyun dosyaları, Discord
adresi ve PIN'ler GİRMEZ.

Uygularken eklentiler Modrinth'ten indirilir; Modrinth'te olmayanlar adlarıyla listelenir (elle eklenmeli).
"""
import io
import json
import os
import zipfile

from . import modrinth
from .config import N_

FORMAT = 1
EXT = ".spytemplate"
SKIP_PROPS = {"server-port", "query.port", "rcon.port", "rcon.password", "server-ip", "level-seed",
              "resource-pack-sha1", "management-server-secret"}
PROFILE_KEYS = ("ram_min", "ram_max", "scheduled_tasks", "maintenance_schedule", "guard", "auto_restart",
                "backup_keep", "safe_mode", "perf_monitor", "world_border", "esplora_knowledge")
TEXT_EXT = (".yml", ".yaml", ".json", ".json5", ".toml", ".properties", ".txt", ".conf", ".cfg", ".ini", ".snbt")
MAX_FILE = 512 * 1024
MAX_TOTAL = 20 * 1024 * 1024
SECRET_WORDS = ("token", "password", "secret", "webhook", "apikey", "api-key", "api_key")


class TemplateError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def _jar_folder(server_path, modded):
    return os.path.join(server_path, "mods" if modded else "plugins")


def _config_roots(server_path, modded):
    return ["config", "defaultconfigs"] if modded else ["plugins"]


def _props(server_path):
    out = {}
    try:
        with open(os.path.join(server_path, "server.properties"), encoding="utf-8") as f:
            for ln in f:
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.rstrip("\n").split("=", 1)
                    if k.strip() not in SKIP_PROPS:
                        out[k.strip()] = v
    except OSError:
        pass
    return out


def _looks_secret(name):
    n = name.lower()
    return any(w in n for w in SECRET_WORDS)


def export(app, dest, software, mc_version, modded, identify=True):
    """Şablonu `dest` dosyasına yazar. {"plugins": n, "known": k, "files": f} döndürür."""
    sp = app.config.server_path
    jar_dir = _jar_folder(sp, modded)
    jars = sorted(f for f in os.listdir(jar_dir) if f.endswith(".jar")) if os.path.isdir(jar_dir) else []
    known = {}
    if identify and jars:
        try:
            hashes = {modrinth._sha1(os.path.join(jar_dir, j)): j for j in jars}
            res = modrinth._post("/version_files", {"hashes": list(hashes), "algorithm": "sha1"})
            for h, v in (res or {}).items():
                if h in hashes:
                    known[hashes[h]] = {"project": v.get("project_id"), "version": v.get("id")}
        except Exception as e:
            print(f"[şablon] modrinth: {e}")
    plugins = [{"file": j, **known.get(j, {})} for j in jars]
    profile = {k: app.config.get(k) for k in PROFILE_KEYS}
    manifest = {"format": FORMAT, "name": app.config.name, "software": software, "mc": mc_version,
                "modded": bool(modded), "properties": _props(sp), "profile": profile, "plugins": plugins}
    total, nfiles = 0, 0
    tmp = dest + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for root in _config_roots(sp, modded):
            base = os.path.join(sp, root)
            for d, dirs, files in os.walk(base):
                dirs[:] = [x for x in dirs if not x.startswith(".") and x.lower() not in ("logs", "cache", "data",
                                                                                          "libs", "libraries")]
                for f in files:
                    p = os.path.join(d, f)
                    rel = os.path.relpath(p, sp).replace(os.sep, "/")
                    if not f.lower().endswith(TEXT_EXT) or _looks_secret(f):
                        continue
                    size = os.path.getsize(p)
                    if size > MAX_FILE or total + size > MAX_TOTAL:
                        continue
                    z.write(p, "files/" + rel)
                    total += size
                    nfiles += 1
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
    os.replace(tmp, dest)
    return {"plugins": len(plugins), "known": len(known), "files": nfiles}


def read(path):
    try:
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read("manifest.json").decode("utf-8"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        raise TemplateError(N_("Bu dosya bir Spypaper sunucu şablonu değil."))
    if not isinstance(m, dict) or m.get("format", 0) > FORMAT:
        raise TemplateError(N_("Bu şablon Spypaper'ın daha yeni bir sürümüyle yapılmış; önce Spypaper'ı güncelle."))
    return m


def _safe_rel(rel):
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    return not (rel.startswith("/") or ".." in parts or ":" in parts[0] or not parts[0])


def apply(app, path, parts=("properties", "profile", "files", "plugins"), modded=None, progress=None):
    """Şablonu bu sunucuya uygular (sunucu kapalı olmalı).
    Döndürür: {"props": n, "files": n, "installed": [ad], "missing": [ad], "skipped": [ad]}"""
    if app.server.is_running:
        raise TemplateError(N_("Şablonu uygulamadan önce sunucuyu durdur."))
    m = read(path)
    sp = app.config.server_path
    out = {"props": 0, "files": 0, "installed": [], "missing": [], "skipped": []}
    if "properties" in parts and m.get("properties"):
        from .clone import write_props
        props = {k: v for k, v in m["properties"].items() if k not in SKIP_PROPS}
        write_props(sp, props)
        out["props"] = len(props)
    if "profile" in parts:
        for k in PROFILE_KEYS:
            if k in (m.get("profile") or {}) and m["profile"][k] is not None:
                app.config.set(k, m["profile"][k])
    if "files" in parts:
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if not n.startswith("files/") or n.endswith("/"):
                    continue
                rel = n[6:]
                if not _safe_rel(rel) or not rel.lower().endswith(TEXT_EXT):
                    continue
                dest = os.path.join(sp, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(z.read(n))
                out["files"] += 1
    if "plugins" in parts:
        modded = m.get("modded") if modded is None else modded
        jar_dir = _jar_folder(sp, modded)
        os.makedirs(jar_dir, exist_ok=True)
        have = set(os.listdir(jar_dir))
        items = m.get("plugins") or []
        for i, p in enumerate(items, 1):
            name = p.get("file", "?")
            if progress:
                progress(i, len(items), name)
            if name in have:
                out["skipped"].append(name)
                continue
            if not p.get("version"):
                out["missing"].append(name)
                continue
            try:
                v = modrinth._get(f"/version/{p['version']}")
                info = modrinth._file_info(v)
                if not info:
                    raise ValueError("no file")
                modrinth.download(info, jar_dir)
                out["installed"].append(info["name"])
            except Exception as e:
                print(f"[şablon] {name}: {e}")
                out["missing"].append(name)
    return out


def summary(m):
    """Önizleme için kısa metin parçaları."""
    plugins = m.get("plugins") or []
    known = sum(1 for p in plugins if p.get("version"))
    return {"name": m.get("name", ""), "software": m.get("software", ""), "mc": m.get("mc", ""),
            "props": len(m.get("properties") or {}), "plugins": len(plugins), "known": known,
            "tasks": len((m.get("profile") or {}).get("scheduled_tasks") or [])}


def to_bytes(manifest):
    """Testler için: yalnızca manifest içeren şablon."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
    return buf.getvalue()
