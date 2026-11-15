"""Spypaper'ın kendi güncellemesi: GitHub Releases'taki en son sürümü denetler, exe'yi indirip değiştirir.

  GET https://api.github.com/repos/<REPO>/releases/latest
      -> {"tag_name": "v2.4", "body": "...", "html_url": "...",
          "assets": [{"name": "Spypaper.exe", "browser_download_url": "...", "size": n, "digest": "sha256:..."}]}

Repo private ise GitHub giriş yapılmadan 404 döner; bu durumda "denetlenemedi" denir, uygulama normal açılır.
Çalışan exe Windows'ta silinemez ama yeniden adlandırılabilir: yeni exe indirilir (Spypaper.exe.new),
çalışan exe Spypaper.exe.old olur, yenisi yerine geçer ve yeniden başlatılır. .old bir sonraki açılışta silinir.
Kaynak koddan çalışırken (exe değil) yalnızca sürüm sayfası açılır.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from .config import N_, get_base_dir
from .updater import VERSION, net_reason

REPO = "TyraelDiablo/spypaper-releases"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"


class AppUpdateError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def vkey(v):
    """'v2.10.1' -> (2, 10, 1). Sayı olmayan parçalar en küçük sayılır."""
    parts = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in parts) or (0,)


def is_newer(remote, local=VERSION):
    a, b = vkey(remote), vkey(local)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def frozen():
    return bool(getattr(sys, "frozen", False))


def check(timeout=6):
    """En son sürüm bilgisi: {'version', 'notes', 'page', 'url', 'name', 'size', 'sha256'} (url exe yoksa '')."""
    req = urllib.request.Request(API, headers={
        "User-Agent": f"Spypaper/{VERSION}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise AppUpdateError(N_("Sürüm bilgisi bulunamadı (repo gizli ya da henüz sürüm yayınlanmamış)."))
        raise AppUpdateError(N_("Güncelleme denetlenemedi: {e}"), e=net_reason(e))
    except Exception as e:
        raise AppUpdateError(N_("Güncelleme denetlenemedi: {e}"), e=net_reason(e))
    asset = next((a for a in data.get("assets") or []
                  if str(a.get("name", "")).lower().endswith(".exe")), None) or {}
    digest = str(asset.get("digest") or "")
    return {
        "version": str(data.get("tag_name") or "").lstrip("vV"),
        "notes": str(data.get("body") or "")[:4000],
        "page": data.get("html_url") or PAGE,
        "url": asset.get("browser_download_url") or "",
        "name": asset.get("name") or "",
        "size": int(asset.get("size") or 0),
        "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else "",
    }


def download(info, progress=None):
    """Yeni exe'yi çalışan exe'nin yanına <ad>.new olarak indirir ve doğrular. Dosya yolunu döndürür."""
    if not info.get("url"):
        raise AppUpdateError(N_("Bu sürümde indirilecek exe yok."))
    exe = sys.executable if frozen() else os.path.join(get_base_dir(), "Spypaper.exe")
    tmp = exe + ".new"
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(info["url"], headers={"User-Agent": f"Spypaper/{VERSION}"})
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
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise AppUpdateError(N_("İndirme başarısız: {e}"), e=net_reason(e))
    if info.get("sha256") and h.hexdigest().lower() != info["sha256"].lower():
        os.remove(tmp)
        raise AppUpdateError(N_("Dosya doğrulanamadı ({algo} uyuşmuyor). Güncelleme iptal edildi."), algo="SHA-256")
    with open(tmp, "rb") as f:
        if f.read(2) != b"MZ":                         # Windows programı değilse kurma
            os.remove(tmp)
            raise AppUpdateError(N_("İndirilen dosya geçerli bir program değil."))
    return tmp


def apply_and_restart(new_path):
    """Çalışan exe'yi yenisiyle değiştirir ve yeni exe'yi başlatır. Çağıran ardından uygulamayı kapatmalı."""
    exe = sys.executable
    old = exe + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass
    os.replace(exe, old)
    try:
        os.replace(new_path, exe)
    except OSError:
        os.replace(old, exe)                           # geri al
        raise
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=flags, close_fds=True)


def cleanup():
    """Bir önceki güncellemeden kalan .old / .new dosyalarını siler."""
    if not frozen():
        return
    for ext in (".old", ".new"):
        try:
            os.remove(sys.executable + ext)
        except OSError:
            pass
