"""Paper sunucu jar'ını PaperMC Fill API (v3) üzerinden günceller.

API: https://docs.papermc.io/misc/downloads-api
  GET /v3/projects/paper                              -> {"versions": {"1.21": ["1.21.4", ...], ...}}
  GET /v3/projects/paper/versions/{v}/builds          -> [{"id", "channel", "downloads": {"server:default": {...}}}]
PaperMC her istekte yazılımı tanıtan ve iletişim bilgisi içeren bir User-Agent ister.
"""
import hashlib
import json
import os
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .config import N_

API = "https://fill.papermc.io/v3/projects/paper"
VERSION = "2.1"


class UpdateError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def user_agent(contact=""):
    return f"Spypaper/{VERSION} (Minecraft server panel; contact: {contact or 'not set'})"


def net_reason(e):
    """urllib hatalarını okunur hale getirir: '<urlopen error [Errno 11001] ...>' -> '[Errno 11001] ...'."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason}"
    if isinstance(e, urllib.error.URLError):
        return str(e.reason)
    if isinstance(e, TimeoutError):
        return "timeout"
    return str(e)


def _get_json(url, contact):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(contact), "Accept": "application/json"})
    host = urllib.parse.urlparse(url).netloc
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except json.JSONDecodeError as e:
        raise UpdateError(N_("{host} beklenmeyen bir yanıt verdi: {e}"), host=host, e=e)
    except Exception as e:
        raise UpdateError(N_("{host} adresine bağlanılamadı: {e}"), host=host, e=net_reason(e))
    if isinstance(data, dict) and data.get("ok") is False:
        raise UpdateError(N_("PaperMC hatası: {e}"), e=data.get("message", "?"))
    return data


def _vkey(v):
    return tuple(int(x) if x.isdigit() else -1 for x in re.split(r"[.\-]", v))


def list_versions(contact=""):
    """Kararlı Minecraft sürümleri, en yeni önce (pre/rc hariç)."""
    data = _get_json(API, contact)
    vers = [v for group in data.get("versions", {}).values() for v in group]
    vers = [v for v in vers if re.fullmatch(r"\d+\.\d+(\.\d+)?", v)]
    return sorted(set(vers), key=_vkey, reverse=True)


def latest_build(mc_version, contact=""):
    """{'version', 'build', 'url', 'name', 'sha256', 'size'} — en yeni STABLE build."""
    builds = _get_json(f"{API}/versions/{mc_version}/builds", contact)
    if isinstance(builds, dict):
        builds = builds.get("builds", [])
    stable = [b for b in builds if str(b.get("channel", "")).upper() == "STABLE"]
    if not stable:
        raise UpdateError(N_("{v} için kararlı (STABLE) Paper sürümü yok."), v=mc_version)
    b = max(stable, key=lambda x: int(x.get("id", 0)))
    dl = (b.get("downloads") or {}).get("server:default") or {}
    if not dl.get("url"):
        raise UpdateError(N_("İndirme adresi bulunamadı."))
    return {
        "version": mc_version, "build": int(b["id"]), "url": dl["url"],
        "name": dl.get("name") or f"paper-{mc_version}-{b['id']}.jar",
        "sha256": (dl.get("checksums") or {}).get("sha256", ""), "size": dl.get("size", 0),
    }


def current_build(server_path, jar_name):
    """(mc_sürümü, build) — jar adından ya da latest.log'dan. Bilinmiyorsa ("", 0)."""
    m = re.search(r"paper-(\d+\.\d+(?:\.\d+)?)-(\d+)\.jar$", jar_name or "", re.I)
    if m:
        return m.group(1), int(m.group(2))
    log = os.path.join(server_path, "logs", "latest.log")
    if os.path.exists(log):
        with open(log, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                # "This server is running Paper version 1.21.4-232-ver/1.21.4@abc (..."
                m = re.search(r"running Paper version (\d+\.\d+(?:\.\d+)?)-(\d+)", line)
                if m:
                    return m.group(1), int(m.group(2))
                if i > 400:
                    break
    return "", 0


def download(info, server_path, old_jar, contact="", progress=None):
    """Yeni jar'ı indirir, SHA-256 doğrular, eskisini backups/jars/ içine taşır.
    Yeni jar adını döndürür. progress(alınan, toplam)."""
    tmp = os.path.join(server_path, info["name"] + ".part")
    # doğrulama: sağlayıcı SHA-256 ya da SHA-1 verirse ona göre
    algo = "sha256" if info.get("sha256") else "sha1" if info.get("sha1") else ""
    h = hashlib.new(algo) if algo else hashlib.sha256()
    try:
        req = urllib.request.Request(info["url"], headers={"User-Agent": user_agent(contact)})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise UpdateError(N_("İndirme başarısız: {e}"), e=net_reason(e))

    if algo and h.hexdigest().lower() != info[algo].lower():
        os.remove(tmp)
        raise UpdateError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo=algo.upper())

    old = os.path.join(server_path, old_jar) if old_jar else ""
    if old and os.path.exists(old) and os.path.basename(old) != info["name"]:
        bdir = os.path.join(server_path, "backups", "jars")
        os.makedirs(bdir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.move(old, os.path.join(bdir, f"{stamp}_{os.path.basename(old)}"))
    final = os.path.join(server_path, info["name"])
    os.replace(tmp, final)
    return info["name"]
