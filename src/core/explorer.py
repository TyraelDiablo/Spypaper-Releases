"""Dosyalar sekmesi: sunucu klasöründeki dosyaları kullanıcının düzenleyicisinde açma.

Düzenleyiciler (bulunanlar): VS Code, Notepad++, Not Defteri, Windows'un varsayılan programı.
Metin olmayan dosyalar (jar, dat, mca, zip…) düzenleyicide açılmaz; Gezgin'de gösterilir.
Sunucu jar'ı gibi dosyalar "varsayılan program" ile açılırsa Java'yla çalışabileceği için
ikili dosyalar hiçbir zaman çalıştırılmaz (resimler hariç).
"""
import os
import shutil
import subprocess
import sys

from .config import N_

EDITORS = {                       # anahtar -> görünen ad (çevrilenler N_ ile işaretli)
    "auto": N_("Otomatik"),
    "vscode": "VS Code",
    "notepadpp": "Notepad++",
    "notepad": N_("Not Defteri"),
    "system": N_("Varsayılan program"),
}

TEXT_EXT = {
    ".yml", ".yaml", ".properties", ".json", ".json5", ".toml", ".txt", ".log", ".cfg", ".conf", ".ini",
    ".md", ".csv", ".tsv", ".xml", ".mcfunction", ".mcmeta", ".sk", ".js", ".lang", ".bat", ".cmd", ".sh",
    ".ps1", ".html", ".css", ".snbt", ".hocon", ".secret", ".lst", ".env",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
CONFIG_EXT = {".yml", ".yaml", ".properties", ".json", ".json5", ".toml", ".cfg", ".conf", ".ini", ".hocon"}


class ExplorerError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def _first(*paths):
    return next((p for p in paths if p and os.path.isfile(p)), None)


def _vscode():
    env = os.environ
    exe = _first(
        os.path.join(env.get("LOCALAPPDATA", ""), "Programs", "Microsoft VS Code", "Code.exe"),
        os.path.join(env.get("ProgramFiles", ""), "Microsoft VS Code", "Code.exe"),
        os.path.join(env.get("ProgramFiles(x86)", ""), "Microsoft VS Code", "Code.exe"),
    )
    if exe:
        return exe
    cli = shutil.which("code")                       # PATH'teki ...\Microsoft VS Code\bin\code(.cmd)
    if cli:
        if sys.platform == "win32":
            exe = os.path.join(os.path.dirname(os.path.dirname(cli)), "Code.exe")
            return exe if os.path.isfile(exe) else None
        return cli
    return None


def _notepadpp():
    env = os.environ
    return _first(os.path.join(env.get("ProgramFiles", ""), "Notepad++", "notepad++.exe"),
                  os.path.join(env.get("ProgramFiles(x86)", ""), "Notepad++", "notepad++.exe"),
                  shutil.which("notepad++"))


def find_editors():
    """{anahtar: çalıştırılabilir yol} — bu bilgisayarda bulunan düzenleyiciler."""
    found = {}
    if p := _vscode():
        found["vscode"] = p
    if p := _notepadpp():
        found["notepadpp"] = p
    if sys.platform == "win32":
        found["notepad"] = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "notepad.exe")
    found["system"] = ""
    return found


def resolve(choice, editors=None):
    """Seçili düzenleyici (yoksa ya da 'auto' ise: VS Code > Notepad++ > Not Defteri > varsayılan)."""
    editors = editors if editors is not None else find_editors()
    if choice in editors:
        return choice
    return next(k for k in ("vscode", "notepadpp", "notepad", "system") if k in editors)


def is_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT:
        return True
    if ext in IMAGE_EXT:
        return False
    try:                                             # uzantısız/bilinmeyen: küçükse ve NUL yoksa metin
        if os.path.getsize(path) > 5 * 1024 * 1024:
            return False
        with open(path, "rb") as f:
            return b"\0" not in f.read(4096)
    except OSError:
        return False


def is_config(path):
    return os.path.splitext(path)[1].lower() in CONFIG_EXT


def inside(root, path):
    root, path = os.path.normcase(os.path.abspath(root)), os.path.normcase(os.path.abspath(path))
    return path != root and os.path.commonpath([root, path]) == root


def _spawn(args):
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, close_fds=True, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)                           # noqa: windows
    else:
        _spawn(["open" if sys.platform == "darwin" else "xdg-open", path])


def reveal(path):
    """Dosyayı Gezgin'de seçili gösterir."""
    if sys.platform == "win32":
        _spawn(["explorer", "/select,", os.path.normpath(path)])
    else:
        open_path(os.path.dirname(path))


def open_file(path, choice="auto", root=None):
    """Dosyayı açar. Dönen değer: 'editor', 'image' ya da 'revealed' (metin olmayan dosya)."""
    if not os.path.isfile(path):
        raise ExplorerError(N_("Dosya bulunamadı: {path}"), path=path)
    if not is_text(path):
        if os.path.splitext(path)[1].lower() in IMAGE_EXT:
            open_path(path)
            return "image"
        reveal(path)
        return "revealed"
    editors = find_editors()
    key = resolve(choice, editors)
    try:
        if key == "system":
            open_path(path)
        elif key == "vscode" and root and os.path.isdir(root):
            _spawn([editors[key], root, path])       # sunucu klasörü kenar çubuğunda, dosya açık
        else:
            _spawn([editors[key], path])
    except OSError as e:
        raise ExplorerError(N_("Dosya açılamadı: {error}"), error=str(e))
    return "editor"


def recycle(root, path):
    """Dosya/klasörü Geri Dönüşüm Kutusu'na taşır (yalnızca sunucu klasörünün içindekiler)."""
    if not inside(root, path):
        raise ExplorerError(N_("Bu konum sunucu klasörünün dışında: {path}"), path=path)
    if sys.platform == "win32":
        from .danger import DangerError, _recycle_windows
        try:
            _recycle_windows(path)
        except DangerError as e:
            raise ExplorerError(e.template, **e.kw)
        return
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
