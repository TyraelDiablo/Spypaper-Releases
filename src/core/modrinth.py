"""Modrinth: mod, eklenti ve kaynak paketi arama / indirme (https://api.modrinth.com/v2, giriş gerekmez).

  search(...)          GET /search?query=&facets=[[...]]&index=&offset=&limit=
  versions(...)        GET /project/{id}/version?loaders=[..]&game_versions=[..]
  download(...)        dosyayı geçici ada indirir, SHA-512 ile doğrular, sonra yerine taşır
  set_resource_pack()  server.properties: resource-pack, resource-pack-sha1, require-resource-pack

İndirmeler yalnızca cdn.modrinth.com'dan yapılır. Dosya adı Modrinth'ten gelse de temizlenir.
"""
import hashlib
import json
import os
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request

from .config import N_
from .updater import VERSION, net_reason

API = "https://api.modrinth.com/v2"
CDN = ("https://cdn.modrinth.com/",)
UA = f"TyraelDiablo/Spypaper/{VERSION} (github.com/TyraelDiablo)"

PLUGIN_LOADERS = ["paper", "purpur", "spigot", "bukkit", "folia"]
MOD_LOADERS = ["fabric", "quilt", "forge", "neoforge"]
SORTS = {"relevance": N_("En uygun"), "downloads": N_("En çok indirilen"), "follows": N_("En çok takip edilen"),
         "updated": N_("Son güncellenen"), "newest": N_("En yeni")}
_FILE_RE = re.compile(r"[^A-Za-z0-9._+\-() \[\]]")


class ModrinthError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def _get(path, params=None, timeout=15):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ModrinthError(N_("Modrinth'te bulunamadı."))
        if e.code == 429:
            raise ModrinthError(N_("Modrinth çok fazla istek aldı; biraz bekleyip tekrar dene."))
        raise ModrinthError(N_("Modrinth'e ulaşılamadı: {e}"), e=net_reason(e))
    except Exception as e:
        raise ModrinthError(N_("Modrinth'e ulaşılamadı: {e}"), e=net_reason(e))


def context(software, mc_version, modded):
    """Sunucuya göre arama varsayılanları: (proje_türü, yükleyiciler)."""
    s = (software or "").lower()
    if modded or s in MOD_LOADERS:
        return "mod", [s] if s in MOD_LOADERS else ["fabric"]
    if s in ("paper", "purpur", "folia"):
        return "plugin", ["paper", "purpur", "spigot", "bukkit"] if s != "folia" else ["folia"]
    if s in ("spigot", "bukkit"):
        return "plugin", ["spigot", "bukkit"]
    return "plugin", ["paper", "spigot", "bukkit"]


def search(query="", project_type="mod", game_version="", loaders=None, sort="relevance", offset=0, limit=20):
    facets = [[f"project_type:{project_type}"]]
    if game_version:
        facets.append([f"versions:{game_version}"])
    if loaders and project_type in ("mod", "plugin"):
        facets.append([f"categories:{lo}" for lo in loaders])
    if project_type == "mod":
        facets.append(["server_side!=unsupported"])     # yalnızca istemci modları sunucuya kurulmasın
    data = _get("/search", {"query": query.strip()[:100], "facets": json.dumps(facets),
                            "index": sort if sort in SORTS else "relevance",
                            "offset": max(0, int(offset)), "limit": max(1, min(50, int(limit)))})
    hits = []
    for h in data.get("hits", []):
        hits.append({
            "id": h.get("project_id", ""), "slug": h.get("slug", ""), "title": h.get("title", ""),
            "description": h.get("description", ""), "author": h.get("author", ""),
            "downloads": int(h.get("downloads") or 0), "icon": h.get("icon_url") or "",
            "categories": h.get("display_categories") or h.get("categories") or [],
            "server_side": h.get("server_side", ""), "client_side": h.get("client_side", ""),
            "license": h.get("license", ""), "type": h.get("project_type", project_type),
        })
    return hits, int(data.get("total_hits") or 0)


def versions(project_id, loaders=None, game_version=""):
    if not re.fullmatch(r"[A-Za-z0-9]{1,64}", project_id or ""):
        raise ModrinthError(N_("Modrinth'te bulunamadı."))
    params = {}
    if loaders:
        params["loaders"] = json.dumps(list(loaders))
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    out = []
    for v in _get(f"/project/{project_id}/version", params):
        files = v.get("files") or []
        f = next((x for x in files if x.get("primary")), files[0] if files else None)
        if not f:
            continue
        out.append({
            "id": v.get("id", ""), "project_id": v.get("project_id", project_id), "name": v.get("name", ""),
            "number": v.get("version_number", ""), "type": v.get("version_type", "release"),
            "game_versions": v.get("game_versions") or [], "loaders": v.get("loaders") or [],
            "date": (v.get("date_published") or "")[:10], "downloads": int(v.get("downloads") or 0),
            "file": {"url": f.get("url", ""), "name": f.get("filename", ""), "size": int(f.get("size") or 0),
                     "sha512": (f.get("hashes") or {}).get("sha512", ""), "sha1": (f.get("hashes") or {}).get("sha1", "")},
            "deps": [d for d in v.get("dependencies") or [] if d.get("dependency_type") == "required"],
        })
    return out


def project(project_id):
    return _get(f"/project/{project_id}")


def safe_filename(name):
    name = os.path.basename((name or "").replace("\\", "/"))
    name = _FILE_RE.sub("_", name).strip(" .")
    return name[:150] or "download.jar"


def download(file, dest_dir, progress=None):
    """Dosyayı dest_dir'e indirir, SHA-512 (yoksa SHA-1) ile doğrular. Tam yolunu döndürür."""
    url = file.get("url", "")
    if not url.startswith(CDN):
        raise ModrinthError(N_("Güvenilmeyen indirme adresi: {url}"), url=url[:80])
    os.makedirs(dest_dir, exist_ok=True)
    name = safe_filename(file.get("name"))
    dest = os.path.join(dest_dir, name)
    tmp = dest + ".part"
    h512, h1 = hashlib.sha512(), hashlib.sha1()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or file.get("size") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h512.update(chunk)
                h1.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except Exception as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ModrinthError(N_("İndirme başarısız: {e}"), e=net_reason(e))
    want512, want1 = (file.get("sha512") or "").lower(), (file.get("sha1") or "").lower()
    if (want512 and h512.hexdigest() != want512) or (not want512 and want1 and h1.hexdigest() != want1):
        os.remove(tmp)
        raise ModrinthError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo="SHA")
    os.replace(tmp, dest)
    return dest


def installed_names(folder):
    try:
        return {f.lower().replace(".disabled", "") for f in os.listdir(folder)}
    except OSError:
        return set()


# ---------------------------------------------------------------- kaynak paketi
def set_resource_pack(props, url, sha1, required=False, prompt=""):
    if not url.startswith(("https://", "http://")) or any(c.isspace() for c in url):
        raise ModrinthError(N_("Geçersiz adres."))
    if sha1 and not re.fullmatch(r"[0-9a-fA-F]{40}", sha1):
        raise ModrinthError(N_("SHA-1 40 karakterlik bir onaltılık değer olmalı."))
    vals = {"resource-pack": url, "resource-pack-sha1": (sha1 or "").lower(),
            "require-resource-pack": "true" if required else "false",
            "resource-pack-id": str(uuid.uuid5(uuid.NAMESPACE_URL, url + (sha1 or "")))}
    if prompt:
        vals["resource-pack-prompt"] = json.dumps({"text": prompt[:200]}, ensure_ascii=False)
    props.save(vals)


def clear_resource_pack(props):
    props.save({"resource-pack": "", "resource-pack-sha1": "", "require-resource-pack": "false", "resource-pack-id": "",
                "resource-pack-prompt": ""})


def current_resource_pack(props):
    if not props.exists:
        return {}
    p = props.load()
    return {"url": p.get("resource-pack", "").replace("\\=", "=").replace("\\:", ":"),
            "sha1": p.get("resource-pack-sha1", ""),
            "required": p.get("require-resource-pack", "false").lower() == "true"}


def sha1_of_url(url, progress=None, limit=260 * 1024 * 1024):
    """Elle girilen kaynak paketi adresi için SHA-1 (dosyayı indirip hesaplar, kaydetmez)."""
    if not url.startswith(("https://", "http://")):
        raise ModrinthError(N_("Geçersiz adres."))
    h = hashlib.sha1()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > limit:
                    raise ModrinthError(N_("Kaynak paketi çok büyük (en fazla 250 MB)."))
                h.update(chunk)
                if progress:
                    progress(got, total)
    except ModrinthError:
        raise
    except Exception as e:
        raise ModrinthError(N_("İndirme başarısız: {e}"), e=net_reason(e))
    return h.hexdigest()
