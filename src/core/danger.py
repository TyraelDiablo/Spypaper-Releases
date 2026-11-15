"""Tehlikeli Bölge: geri alınamayan işlemler. Hepsi sunucu KAPALIYKEN çalışır.

  reset_world     seçilen boyutları siler (isteğe bağlı önce yedek), seed'i ayarlar
  restore_backup  dünya yedeğini geri yükler (önce mevcut dünyanın güvenlik yedeği)
  reset_players   oyuncu verilerini siler: envanter, konum, istatistik, ilerlemeler
  delete_server   sunucu klasörünü Windows Geri Dönüşüm Kutusu'na taşır (başka sistemlerde siler)

Paper/Spigot'ta Nether ve End ayrı klasörlerdedir (world_nether, world_the_end); Vanilla, Fabric ve
Forge'da dünya klasörünün içindedir (DIM-1, DIM1; 26.x'te dimensions/minecraft/...).
"""
import os
import shutil
import sys
import zipfile

from .config import N_


class DangerError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


DIMENSIONS = ("overworld", "nether", "end")


def level_name(props):
    name = (props.load().get("level-name") if props.exists else "") or "world"
    if os.path.isabs(name) or ".." in name.replace("\\", "/").split("/"):
        raise DangerError(N_("level-name geçersiz: {name}"), name=name)
    return name


def dimension_dirs(server_path, level, dim):
    """Bir boyutun sunucu klasöründeki olası klasörleri (var olanlar)."""
    base = os.path.join(server_path, level)
    cand = {
        "overworld": [base],
        "nether": [base + "_nether", os.path.join(base, "DIM-1"),
                   os.path.join(base, "dimensions", "minecraft", "the_nether")],
        "end": [base + "_the_end", os.path.join(base, "DIM1"),
                os.path.join(base, "dimensions", "minecraft", "the_end")],
    }[dim]
    return [p for p in cand if os.path.isdir(p)]


def _rmtree(path):
    def onerror(func, p, _exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)
    if os.path.exists(path):
        raise DangerError(N_("Silinemedi: {path}\nSunucu ya da başka bir program dosyayı kullanıyor olabilir."), path=path)


def _require_stopped(server):
    if server.is_running:
        raise DangerError(N_("Önce sunucuyu durdur."))


def reset_world(app, dims, seed_mode="random", seed="", backup=True):
    """dims: {'overworld','nether','end'} alt kümesi. seed_mode: 'random' | 'keep' | 'custom'.
    Silinen klasörleri ve (alındıysa) yedeğin yolunu döndürür."""
    _require_stopped(app.server)
    dims = [d for d in DIMENSIONS if d in set(dims)]
    if not dims:
        raise DangerError(N_("En az bir boyut seç."))
    sp = app.config.server_path
    level = level_name(app.properties)
    targets = []
    for d in dims:
        for p in dimension_dirs(sp, level, d):
            if p not in targets:
                targets.append(p)
    # Overworld seçiliyse dünya klasörünün tamamı gider; içindeki Nether/End ayrıca silinmez
    base = os.path.join(sp, level)
    if base in targets:
        targets = [p for p in targets if not p.startswith(base + os.sep)]
    bk = None
    if backup and targets:
        try:
            bk = app.backups.create(prefix="before_reset")
        except FileNotFoundError:
            bk = None
    for p in targets:
        _rmtree(p)
    if app.properties.exists and seed_mode != "keep":
        app.properties.save({"level-seed": seed.strip() if seed_mode == "custom" else ""})
    return targets, bk


def _safe_members(z, root):
    """Zip'teki dosyalar sunucu klasörünün dışına yazamasın (zip slip)."""
    root = os.path.realpath(root)
    out = []
    for m in z.infolist():
        name = m.filename.replace("\\", "/")
        if not name or name.startswith("/") or ":" in name.split("/")[0]:
            raise DangerError(N_("Yedek dosyası geçersiz: {name}"), name=m.filename)
        dest = os.path.realpath(os.path.join(root, name))
        if not dest.startswith(root + os.sep):
            raise DangerError(N_("Yedek dosyası geçersiz: {name}"), name=m.filename)
        out.append(m)
    return out


def backup_tops(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return sorted({m.filename.replace("\\", "/").split("/")[0] for m in z.infolist() if m.filename.strip("/")})


def restore_backup(app, zip_name, safety_backup=True, progress=None):
    """backups/<zip_name> yedeğini geri yükler. Yedekte bulunan dünya klasörleri önce silinir."""
    _require_stopped(app.server)
    sp = app.config.server_path
    path = os.path.join(app.backups.folder, os.path.basename(zip_name))
    if not os.path.isfile(path):
        raise DangerError(N_("Yedek bulunamadı: {name}"), name=zip_name)
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise DangerError(N_("Yedek dosyası bozuk: {name}"), name=zip_name)
    with z:
        members = _safe_members(z, sp)
        tops = sorted({m.filename.replace("\\", "/").split("/")[0] for m in members})
        if not tops:
            raise DangerError(N_("Yedek boş: {name}"), name=zip_name)
        bad = [t for t in tops if t in ("backups", "plugins", "mods", "config", "libraries") or "." in t]
        if bad:
            raise DangerError(N_("Bu bir dünya yedeği değil: {name}"), name=zip_name)
        bk = None
        if safety_backup:
            try:
                bk = app.backups.create(prefix="before_restore")
            except FileNotFoundError:
                bk = None
        for t in tops:
            p = os.path.join(sp, t)
            if os.path.isdir(p):
                _rmtree(p)
        for i, m in enumerate(members, 1):
            z.extract(m, sp)
            if progress:
                progress(i, len(members))
    return tops, bk


PLAYER_DIRS = ("playerdata", "stats", "advancements", "players")


def reset_players(app):
    """Oyuncu verilerini siler (envanter, konum, istatistik, ilerlemeler). Dünyaya dokunmaz."""
    _require_stopped(app.server)
    base = os.path.join(app.config.server_path, level_name(app.properties))
    gone = []
    for d in PLAYER_DIRS:
        p = os.path.join(base, d)
        if os.path.isdir(p):
            _rmtree(p)
            gone.append(p)
    return gone


def _forbidden(path):
    """Silinmesi felakete yol açacak klasörler."""
    real = os.path.realpath(path)
    if os.path.dirname(real) == real:                          # sürücü kökü
        return True
    home = os.path.realpath(os.path.expanduser("~"))
    if real == home or home.startswith(real + os.sep):          # ev klasörü ya da onu içeren bir yer
        return True
    from .config import get_base_dir
    base = os.path.realpath(get_base_dir())
    if base == real or base.startswith(real + os.sep):         # Spypaper'ın kendi klasörü
        return True
    return False


def looks_like_server(path):
    return any(os.path.exists(os.path.join(path, f)) for f in
               ("server.properties", "eula.txt", "logs", "world")) or \
        any(f.endswith(".jar") for f in os.listdir(path))


def _recycle_windows(path):
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI = 3, 0x40, 0x10, 0x4, 0x400
    op = SHFILEOPSTRUCTW(None, FO_DELETE, os.path.abspath(path) + "\0", None,
                         FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI, False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0 or op.fAnyOperationsAborted or os.path.exists(path):
        raise DangerError(N_("Klasör Geri Dönüşüm Kutusu'na taşınamadı (kod {code})."), code=rc)


def delete_server(app):
    """Sunucu klasörünü siler. Windows'ta Geri Dönüşüm Kutusu'na taşır. 'recycle' ya da 'deleted' döner."""
    _require_stopped(app.server)
    sp = app.config.server_path
    if not sp or not os.path.isdir(sp):
        return "missing"
    if _forbidden(sp) or not looks_like_server(sp):
        raise DangerError(N_("Bu klasör güvenlik nedeniyle silinmez: {path}"), path=sp)
    if sys.platform == "win32":
        _recycle_windows(sp)
        return "recycle"
    _rmtree(sp)
    return "deleted"
