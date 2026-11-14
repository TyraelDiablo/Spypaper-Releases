"""BlueMap: algılama, Modrinth'ten otomatik kurulum ve yapılandırma.

* Paper/Purpur/Spigot: plugins/bluemap-*.jar, ayarlar plugins/BlueMap/*.conf
* Fabric/Forge/NeoForge: mods/bluemap-*.jar, ayarlar config/bluemap/*.conf
* BlueMap ilk açılışta Minecraft'ın istemci dosyalarını (dokular) Mojang'dan indirmek için
  core.conf içinde "accept-download: true" ister. Bu Mojang'ın dosyası olduğu için panel bunu
  yalnızca kullanıcının açık onayıyla değiştirir.
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import updater
from .config import N_

MODRINTH = "https://api.modrinth.com/v2/project/bluemap/version"
LOADERS = {
    "paper": ["paper", "spigot", "bukkit"], "purpur": ["purpur", "paper", "spigot", "bukkit"],
    "fabric": ["fabric"], "forge": ["forge"], "neoforge": ["neoforge"],
}
DEFAULT_PORT = 8100


def _jar(server_path, modded):
    folder = os.path.join(server_path, "mods" if modded else "plugins")
    try:
        for f in os.listdir(folder):
            if f.lower().startswith("bluemap") and f.lower().endswith(".jar"):
                return os.path.join(folder, f)
    except OSError:
        pass
    return None


def config_dir(server_path):
    for d in (os.path.join(server_path, "plugins", "BlueMap"), os.path.join(server_path, "config", "bluemap")):
        if os.path.isdir(d):
            return d
    return None


def _conf_value(path, key):
    """HOCON dosyasından basit 'anahtar: değer' okur (yorum satırları atlanır)."""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s.startswith(("#", "//")):
                    continue
                m = re.match(rf'^{re.escape(key)}\s*[:=]\s*"?([^"\s#]+)"?', s)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def status(server_path, modded):
    """{"installed", "jar", "config", "accepted", "port", "web_enabled"}"""
    cfg = config_dir(server_path)
    jar = _jar(server_path, modded)
    st = {"installed": bool(jar), "jar": jar, "config": cfg, "accepted": None,
          "port": DEFAULT_PORT, "web_enabled": True}
    if cfg:
        acc = _conf_value(os.path.join(cfg, "core.conf"), "accept-download")
        st["accepted"] = None if acc is None else acc.lower() == "true"
        port = _conf_value(os.path.join(cfg, "webserver.conf"), "port")
        if port and port.isdigit():
            st["port"] = int(port)
        en = _conf_value(os.path.join(cfg, "webserver.conf"), "enabled")
        st["web_enabled"] = en is None or en.lower() == "true"
    return st


def default_url(server_path, modded):
    return f"http://localhost:{status(server_path, modded)['port']}"


def accept_download(server_path):
    """core.conf içinde accept-download: false -> true. Başarılıysa True."""
    cfg = config_dir(server_path)
    if not cfg:
        return False
    p = os.path.join(cfg, "core.conf")
    try:
        with open(p, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return False
    new, n = re.subn(r"(?m)^(\s*accept-download\s*[:=]\s*)false\b", r"\1true", text)
    if not n:                                    # zaten true ya da satır yok
        return (_conf_value(p, "accept-download") or "").lower() == "true"
    with open(p, "w", encoding="utf-8") as f:
        f.write(new)
    return True


def find_release(software_key, mc_version, contact=""):
    """Modrinth'ten bu yazılım ve Minecraft sürümü için en yeni BlueMap dosyası.
    (bilgi, tam_eşleşme_mi) döndürür. Sürüme uygun dosya yoksa en yenisi ve False."""
    loaders = LOADERS.get(software_key)
    if not loaders:
        raise updater.UpdateError(N_("BlueMap bu sunucu yazılımında çalışmaz ({s}). Paper, Purpur, Fabric, Forge ya da NeoForge gerekir."),
                                  s=software_key)

    def query(game):
        q = {"loaders": json.dumps(loaders)}
        if game:
            q["game_versions"] = json.dumps([game])
        return updater._get_json(MODRINTH + "?" + urllib.parse.urlencode(q), contact)

    exact = True
    vers = query(mc_version) if mc_version else []
    if not vers:
        vers, exact = query(None), False
    if not vers:
        raise updater.UpdateError(N_("Modrinth'te uygun BlueMap sürümü bulunamadı."))
    v = vers[0]                                  # Modrinth en yeniyi önce verir
    f = next((x for x in v["files"] if x.get("primary")), v["files"][0])
    return {"version": v.get("version_number", ""), "game_versions": v.get("game_versions", []),
            "url": f["url"], "name": f["filename"], "sha1": f.get("hashes", {}).get("sha1", ""),
            "size": f.get("size", 0)}, exact


def install(info, server_path, modded, contact="", progress=None):
    """Seçilen BlueMap dosyasını plugins/ ya da mods/ içine indirir; eski bluemap jar'ını yedekler."""
    folder = os.path.join(server_path, "mods" if modded else "plugins")
    os.makedirs(folder, exist_ok=True)
    old = _jar(server_path, modded)
    req = urllib.request.Request(info["url"], headers={"User-Agent": updater.user_agent(contact)})
    tmp = os.path.join(folder, info["name"] + ".part")
    h = hashlib.sha1()
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise updater.UpdateError(N_("İndirme başarısız: {e}"), e=updater.net_reason(e))
    if info.get("sha1") and h.hexdigest() != info["sha1"]:
        os.remove(tmp)
        raise updater.UpdateError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo="SHA1")
    if old and os.path.basename(old) != info["name"]:
        bdir = os.path.join(server_path, "backups", "jars")
        os.makedirs(bdir, exist_ok=True)
        os.replace(old, os.path.join(bdir, os.path.basename(old)))
    os.replace(tmp, os.path.join(folder, info["name"]))
    return info["name"]


def reachable(url, timeout=2):
    """Harita web sunucusu yanıt veriyor mu?"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # yerel adres: sistem vekilini kullanma
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=timeout) as r:
            return 200 <= r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False
