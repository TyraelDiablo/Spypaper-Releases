"""CurseForge'dan Bedrock add-on'u arama ve indirme (resmi CurseForge API'si, kullanıcının kendi API anahtarıyla).

Anahtar: console.curseforge.com'dan alınır; config.json'da şifreli saklanır ("curseforge_key").
Yazarın üçüncü taraf indirmeye izin vermediği dosyalarda indirme adresi gelmez; o zaman sayfa açılır.
"""
import json
import os
import urllib.parse
import urllib.request

from .config import N_

API = "https://api.curseforge.com/v1"
BEDROCK_SLUG = "minecraft-bedrock"
PACK_EXT = (".mcaddon", ".mcpack", ".zip")
_game_id = None


class CFError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def get_key(settings):
    from .secrets import unprotect
    return unprotect(settings.get("curseforge_key") or "") or ""


def set_key(settings, key):
    from .secrets import protect
    settings.set("curseforge_key", protect(key.strip()) if key.strip() else "")


def _get(path, key, params=None):
    if not key:
        raise CFError(N_("CurseForge API anahtarı ayarlanmamış."))
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-api-key": key, "Accept": "application/json",
                                               "User-Agent": "Spypaper (github.com/TyraelDiablo/Spypaper-Releases)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise CFError(N_("CurseForge API anahtarı geçersiz."))
        raise CFError(N_("CurseForge'a ulaşılamadı: {e}"), e=e)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise CFError(N_("CurseForge'a ulaşılamadı: {e}"), e=e)


def game_id(key):
    global _game_id
    if _game_id:
        return _game_id
    idx = 0
    while True:
        data = _get("/games", key, {"index": idx, "pageSize": 50})
        for g in data.get("data") or []:
            if g.get("slug") == BEDROCK_SLUG:
                _game_id = g["id"]
                return _game_id
        page = data.get("pagination") or {}
        idx += page.get("resultCount", 0)
        if not page.get("resultCount") or idx >= page.get("totalCount", 0):
            break
    raise CFError(N_("CurseForge'da Minecraft Bedrock bulunamadı."))


def search(key, text="", index=0, size=20):
    data = _get("/mods/search", key, {"gameId": game_id(key), "searchFilter": text, "sortField": 2,
                                      "sortOrder": "desc", "pageSize": size, "index": index})
    out = []
    for m in data.get("data") or []:
        files = [f for f in (m.get("latestFiles") or []) if str(f.get("fileName", "")).lower().endswith(PACK_EXT)]
        files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
        out.append({"id": m.get("id"), "name": m.get("name", ""), "summary": m.get("summary", ""),
                    "downloads": int(m.get("downloadCount") or 0),
                    "authors": ", ".join(a.get("name", "") for a in (m.get("authors") or [])),
                    "url": (m.get("links") or {}).get("websiteUrl", ""),
                    "file": files[0] if files else None,
                    "versions": (files[0].get("gameVersions") if files else []) or []})
    return out


def download(key, mod, dest_dir, progress=None):
    """Dosyayı indirir, yolunu döndürür. İzin verilmeyen dosyada None (sayfa açılmalı)."""
    f = mod.get("file")
    if not f:
        raise CFError(N_("Bu projede sunucuya kurulabilecek bir dosya yok."))
    url = f.get("downloadUrl")
    if not url:
        try:
            url = _get(f"/mods/{mod['id']}/files/{f['id']}/download-url", key).get("data")
        except CFError:
            url = None
    if not url:
        return None
    name = os.path.basename(f.get("fileName") or "addon.mcaddon").replace("/", "_").replace("\\", "_")
    path = os.path.join(dest_dir, name)
    req = urllib.request.Request(url, headers={"User-Agent": "Spypaper"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got, total)
    return path
