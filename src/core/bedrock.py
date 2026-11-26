"""Bedrock Dedicated Server (BDS): Mojang'ın resmi Bedrock sunucusu. Yalnızca vanilla (eklenti/mod yok).

İndirme: Mojang'ın indirme bağlantıları servisi; olmazsa minecraft.net indirme sayfası.
Güncellemede dünyalar ve ayar dosyaları (server.properties, allowlist.json, permissions.json) korunur.
"""
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile

from .config import N_

LINKS_API = "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links"
DOWNLOAD_PAGE = "https://www.minecraft.net/en-us/download/server/bedrock"
META = ".spypaper-bedrock.json"
KEEP = ("server.properties", "allowlist.json", "whitelist.json", "permissions.json")
DEFAULT_PORT = 19132


class BedrockError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def exe_name():
    return "bedrock_server.exe" if os.name == "nt" else "bedrock_server"


def is_bedrock(path):
    return bool(path) and (os.path.isfile(os.path.join(path, "bedrock_server.exe"))
                           or os.path.isfile(os.path.join(path, "bedrock_server"))
                           or os.path.isfile(os.path.join(path, META)))


def _platform_key(preview=False):
    win = os.name == "nt" or sys.platform.startswith("win")
    return ("serverBedrockPreview" if preview else "serverBedrock") + ("Windows" if win else "Linux")


def _get_text(url, contact=""):
    from .updater import user_agent
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(contact), "Accept-Language": "en-US"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def version_of(url):
    m = re.search(r"bedrock-server-([\d.]+)\.zip", url or "")
    return m.group(1) if m else ""


def latest_url(contact="", preview=False):
    """En yeni BDS zip adresi."""
    want = _platform_key(preview)
    try:
        data = json.loads(_get_text(LINKS_API, contact))
        for link in (data.get("result") or {}).get("links", []):
            if link.get("downloadType") == want and link.get("downloadUrl"):
                return link["downloadUrl"]
    except Exception:
        pass
    try:                                                  # yedek: indirme sayfasındaki bağlantı
        html = _get_text(DOWNLOAD_PAGE, contact)
        folder = "bin-win" if want.endswith("Windows") else "bin-linux"
        if preview:
            folder += "-preview"
        m = re.search(r'https://[^"\']+/' + folder + r'/bedrock-server-[\d.]+\.zip', html)
        if m:
            return m.group(0)
    except Exception:
        pass
    raise BedrockError(N_("Bedrock sunucusunun indirme bağlantısı bulunamadı. İnternet bağlantını kontrol et."))


def versions(contact=""):
    v = version_of(latest_url(contact))
    return [v] if v else []


def latest(version, contact=""):
    url = latest_url(contact)
    v = version_of(url)
    return {"url": url, "name": os.path.basename(url), "version": v, "build": "", "label": v, "bedrock": True}


def installed_version(path):
    try:
        with open(os.path.join(path, META), encoding="utf-8") as f:
            return json.load(f).get("version", "")
    except (OSError, ValueError):
        return ""


def install(info, path, contact="", progress=None):
    """Zip'i indirip açar; var olan dünyalar ve ayar dosyaları korunur. Başlatılacak dosyanın adını döndürür."""
    from .updater import download
    os.makedirs(path, exist_ok=True)
    zip_name = download(dict(info), path, "", contact, progress=progress)
    zpath = os.path.join(path, zip_name)
    keep = {}
    for k in KEEP:
        p = os.path.join(path, k)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                keep[k] = f.read()
    try:
        with zipfile.ZipFile(zpath) as z:
            for m in z.infolist():
                name = m.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    continue                              # zip dışına yazma girişimi
                if name.split("/")[0] == "worlds":
                    continue
                z.extract(m, path)
    except zipfile.BadZipFile:
        raise BedrockError(N_("İndirilen Bedrock dosyası bozuk."))
    finally:
        try:
            os.remove(zpath)
        except OSError:
            pass
    for k, data in keep.items():
        with open(os.path.join(path, k), "wb") as f:
            f.write(data)
    exe = exe_name()
    if os.name != "nt":
        try:
            os.chmod(os.path.join(path, exe), 0o755)
        except OSError:
            pass
    with open(os.path.join(path, META), "w", encoding="utf-8") as f:
        json.dump({"version": info.get("version", "")}, f)
    return exe


def set_properties(path, values):
    """server.properties'teki anahtarları değiştirir (yorumlar ve sıra korunur); olmayanları sona ekler."""
    p = os.path.join(path, "server.properties")
    try:
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    done = set()
    for i, ln in enumerate(lines):
        k = ln.split("=", 1)[0].strip()
        if not ln.lstrip().startswith("#") and "=" in ln and k in values:
            lines[i] = f"{k}={values[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def level_name(path):
    try:
        with open(os.path.join(path, "server.properties"), encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("level-name="):
                    return ln.split("=", 1)[1].strip() or "Bedrock level"
    except OSError:
        pass
    return "Bedrock level"
