"""Spypaper'ı kaldırma (Ayarlar → Spypaper'ı kaldır).

Spypaper kurulum programı olmayan tek bir exe'dir; verileri exe'nin yanındadır. Kaldırma:
  - Yalnızca Spypaper'ın kendi oluşturduğu, adı bilinen dosya ve klasörler silinir (exe'nin klasörünün
    tamamı asla silinmez; exe Masaüstü'nde ya da İndirilenler'de olabilir).
  - Sunucu klasörlerine dokunulmaz.
  - Çalışan exe kendini silemediği için silme, Spypaper kapandıktan sonra gizli bir PowerShell işiyle yapılır.
  - "Ayarlarımı sakla" seçiliyse config.json, sohbet geçmişi ve kullanıcının dil dosyaları kalır; Spypaper
    aynı klasöre yeniden konunca sunucular ve ayarlar geri gelir.
"""
import base64
import json
import os
import platform
import subprocess
import sys
import urllib.parse

from .config import CONFIG_FILE, get_base_dir

ISSUES = "https://github.com/TyraelDiablo/Spypaper-Releases/issues/new"
# her zaman silinenler (yeniden oluşturulabilir)
ALWAYS = ["cache", "Translation", "Icons", CONFIG_FILE + ".tmp"]
# "Ayarlarımı sakla" seçili değilse silinenler (kullanıcının kendi verisi)
SETTINGS = [CONFIG_FILE, "esplora_chats", "Languages"]


# klasörler yalnızca içerikleri Spypaper'ınkine benziyorsa silinir (exe'nin yanında kullanıcının aynı adlı
# bir klasörü olabilir: ör. Masaüstü'nde "Icons"). cache: yalnızca bilinen alt klasörler; diğerleri: dosya uzantıları.
CACHE_SUBDIRS = {"modrinth", "skins"}
DIR_EXTS = {"Translation": (".json",), "Icons": (".png",), "Languages": (".json",),
            "esplora_chats": (".json", ".tmp")}


def looks_ours(path):
    name = os.path.basename(path)
    if os.path.islink(path):
        return False
    if name == CONFIG_FILE:                       # başka bir programın config.json'u olabilir
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return False
        return isinstance(data, dict) and ("servers" in data or "server_path" in data)
    if not os.path.isdir(path):
        return True
    if name == "cache":
        return all(c in CACHE_SUBDIRS for c in os.listdir(path))
    exts = DIR_EXTS.get(name)
    if not exts:
        return False
    for d, _, files in os.walk(path):
        if any(not f.lower().endswith(exts) for f in files):
            return False
    return True


def supported():
    """Yalnızca Windows'ta, exe olarak çalışırken (kaynak koddan çalışırken geliştiricinin dosyaları silinmesin)."""
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def targets(base=None, exe=None, keep_settings=True):
    """Silinecek mevcut yollar. Hepsi base klasörünün doğrudan içindedir."""
    base = os.path.realpath(base or get_base_dir())
    exe = exe or sys.executable
    names = list(ALWAYS) + ([] if keep_settings else list(SETTINGS))
    if exe:
        x = os.path.basename(exe)
        names += [x + ".old", x + ".new", x]
    out = []
    for n in names:
        p = os.path.realpath(os.path.join(base, n))
        if os.path.dirname(p) != base:          # güvenlik: yalnızca klasörün doğrudan içi
            continue
        if os.path.lexists(p) and p not in out and looks_ours(p):
            out.append(p)
    return out


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def script(pid, paths, base):
    """Spypaper kapanınca dosyaları silen PowerShell betiği. Klasör boş kaldıysa ve adı Spypaper ile
    başlıyorsa (kullanıcının açtığı Spypaper klasörü) o da silinir."""
    items = ",".join(_ps_quote(p) for p in paths)
    drop_dir = os.path.basename(os.path.normpath(base)).lower().startswith("spypaper")
    lines = [
        f"$p = {int(pid)}",
        "for ($i = 0; $i -lt 240 -and (Get-Process -Id $p -ErrorAction SilentlyContinue); $i++) "
        "{ Start-Sleep -Milliseconds 500 }",
        "Start-Sleep -Seconds 1",
        f"foreach ($f in @({items})) {{",
        "  for ($k = 0; $k -lt 5 -and (Test-Path -LiteralPath $f); $k++) {",
        "    Remove-Item -LiteralPath $f -Recurse -Force -ErrorAction SilentlyContinue",
        "    if (Test-Path -LiteralPath $f) { Start-Sleep -Seconds 1 }",
        "  }",
        "}",
    ]
    if drop_dir:
        b = _ps_quote(os.path.normpath(base))
        lines.append(f"if ((Test-Path -LiteralPath {b}) -and -not (Get-ChildItem -LiteralPath {b} -Force)) "
                     f"{{ Remove-Item -LiteralPath {b} -Force -ErrorAction SilentlyContinue }}")
    return "\n".join(lines) + "\n"


def command(text):
    enc = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-EncodedCommand", enc]


def launch(keep_settings):
    """Silme işini başlatır (Spypaper kapanmayı bekler). Çağıran ardından uygulamayı kapatmalı."""
    base = get_base_dir()
    paths = targets(base, sys.executable, keep_settings)
    flags = 0x08000000 | 0x00000008 | 0x00000200      # CREATE_NO_WINDOW | DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(command(script(os.getpid(), paths, base)), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return paths


def issue_url(version, lang=""):
    """Sürüm ve sistem bilgisi doldurulmuş GitHub konu sayfası (kullanıcı tarayıcıda kendisi gönderir)."""
    body = ("**Ne oldu? / What happened?**\n\n\n\n---\n"
            f"Spypaper: {version}\nWindows: {platform.platform()}\n" + (f"Panel: {lang}\n" if lang else ""))
    q = urllib.parse.urlencode({"title": f"[{version}] ", "body": body})
    return f"{ISSUES}?{q}"
