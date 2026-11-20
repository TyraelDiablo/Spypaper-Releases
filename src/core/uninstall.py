"""Spypaper'ı kaldırma (Ayarlar → Spypaper'ı kaldır).

Spypaper kurulum programı olmayan tek bir exe'dir; verileri exe'nin yanındadır. Kaldırma:
  - Yalnızca Spypaper'ın kendi oluşturduğu, adı bilinen dosya ve klasörler silinir (exe'nin klasörünün
    tamamı asla silinmez; exe Masaüstü'nde ya da İndirilenler'de olabilir).
  - Sunucu klasörlerine dokunulmaz.
  - Çalışan exe kendini silemediği için silme, Spypaper kapandıktan sonra gizli bir PowerShell işiyle yapılır.
  - "Ayarlarımı sakla" seçiliyse config.json, sohbet geçmişi ve kullanıcının dil dosyaları kalır; Spypaper
    aynı klasöre yeniden konunca sunucular ve ayarlar geri gelir.
"""
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


def _q(path):
    """cmd için çift tırnaklı yol (% işareti ikilenir)."""
    return '"' + path.replace("%", "%%") + '"'


def script(pids, paths, base, exe=""):
    """Spypaper kapanınca dosyaları silen .cmd betiği (PowerShell kullanılmaz: gizli/kodlanmış PowerShell
    komutlarını virüs koruması sessizce engelleyebiliyor). Önce Spypaper süreçlerinin (tek dosyalı exe'de
    açıcı süreç + Python süreci) kapanmasını, sonra exe'nin kilidinin kalkmasını bekler; her adımı
    %TEMP%\\spypaper_uninstall.log'a yazar. Klasör boş kaldıysa ve adı Spypaper ile başlıyorsa o da silinir.
    En sonda betik kendini siler."""
    log = '>>"%TEMP%\\spypaper_uninstall.log"'
    L = ["@echo off", "chcp 65001 >nul", "setlocal",
         f"echo [%date% %time%] Spypaper kaldırma başladı {log}"]
    for pid in pids:
        pid = int(pid)
        L += ["set /a n=0", f":w{pid}",
              f'tasklist /FI "PID eq {pid}" /NH 2>nul | find " {pid} " >nul || goto d{pid}',
              "set /a n+=1", "if %n% geq 120 goto d" + str(pid),
              "ping -n 2 127.0.0.1 >nul", f"goto w{pid}", f":d{pid}"]
    if exe:                                    # exe'nin kilidi kalkana kadar (en fazla ~60 sn) silmeyi dene
        L += ["set /a n=0", ":wexe", f"del /f /q {_q(exe)} >nul 2>&1",
              f"if not exist {_q(exe)} goto dexe", "set /a n+=1", "if %n% geq 60 goto dexe",
              "ping -n 2 127.0.0.1 >nul", "goto wexe", ":dexe"]
    for p in paths:
        if p == exe:
            continue
        d = _q(p.rstrip("\\") + "\\")
        L.append(f"if exist {d} (rmdir /s /q {_q(p)} >nul 2>&1) else (del /f /q {_q(p)} >nul 2>&1)")
        L.append(f"if exist {_q(p)} echo silinemedi: {_q(p)} {log}")
    if exe:
        L.append(f"if exist {_q(exe)} echo silinemedi: {_q(exe)} {log}")
    if os.path.basename(os.path.normpath(base)).lower().startswith("spypaper"):
        L.append(f"rmdir {_q(os.path.normpath(base))} >nul 2>&1")
    L += [f"echo [%date% %time%] bitti {log}", '(goto) 2>nul & del /f /q "%~f0"']
    return "\r\n".join(L) + "\r\n"


def launch(keep_settings):
    """Silme işini başlatır (Spypaper kapanmayı bekler). Çağıran ardından uygulamayı kapatmalı."""
    import tempfile
    base = get_base_dir()
    exe = sys.executable
    paths = targets(base, exe, keep_settings)
    pids = [os.getpid()]
    if getattr(sys, "frozen", False) and hasattr(os, "getppid"):
        pids.append(os.getppid())            # tek dosyalı exe: açıcı süreç exe'yi kilitli tutar
    exe_path = os.path.realpath(exe) if os.path.realpath(exe) in paths else ""
    fd, bat = tempfile.mkstemp(prefix="spypaper_uninstall_", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(script(pids, paths, base, exe_path))
    no_window, new_group, breakaway = 0x08000000, 0x00000200, 0x01000000
    args = dict(close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                cwd=tempfile.gettempdir())
    cmd = [os.environ.get("ComSpec", "cmd.exe"), "/d", "/c", bat]
    try:                                       # Spypaper bir iş nesnesindeyse onunla birlikte kapanmasın
        subprocess.Popen(cmd, creationflags=no_window | new_group | breakaway, **args)
    except OSError:
        subprocess.Popen(cmd, creationflags=no_window | new_group, **args)
    return paths


def issue_url(version, lang=""):
    """Sürüm ve sistem bilgisi doldurulmuş GitHub konu sayfası (kullanıcı tarayıcıda kendisi gönderir)."""
    body = ("**Ne oldu? / What happened?**\n\n\n\n---\n"
            f"Spypaper: {version}\nWindows: {platform.platform()}\n" + (f"Panel: {lang}\n" if lang else ""))
    q = urllib.parse.urlencode({"title": f"[{version}] ", "body": body})
    return f"{ISSUES}?{q}"
