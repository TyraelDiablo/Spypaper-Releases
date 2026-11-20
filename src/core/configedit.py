"""Yapılandırma editörü: sunucu klasöründeki ayar dosyalarını (paper-global.yml, spigot.yml, config/*.toml,
eklenti config.yml'leri…) bulur, biçimini denetler ve güvenle kaydeder.

  * Biçim denetimi: YAML (PyYAML; tekrar eden anahtarlar da hata sayılır), TOML (tomllib), JSON.
    Diğer türler (.properties, .conf, .cfg, .ini, .txt) denetlenmez, yalnızca düzenlenir.
  * Dosyanın içeriği yeniden biçimlendirilmez: yorumlar ve sıra olduğu gibi kalır.
  * Kaydetmeden önce eski hali backups/configs/<tarih>/ altına kopyalanır (en fazla 50 klasör saklanır).
  * Dosya açıldıktan sonra dışarıda (sunucu ya da başka bir program tarafından) değiştiyse kaydetme durur.
"""
import json
import os
import re
import shutil
from datetime import datetime

from .config import N_

KINDS = {".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".json": "json", ".json5": "text",
         ".properties": "properties", ".conf": "text", ".cfg": "text", ".ini": "text", ".txt": "text",
         ".hocon": "text", ".snbt": "text", ".mcmeta": "json", ".lang": "text"}
SKIP_DIRS = {"logs", "backups", "libraries", "cache", "crash-reports",
             "versions", ".git", "node_modules", "web", "bluemap", "dynmap", "spypaper_guard", ".fabric", ".paper-remapped",
             "debug", "local", "spark", "data", "datapacks", "playerdata", "stats", "advancements", "region", "entities",
             "poi", "DIM-1", "DIM1", "java"}
MAX_SIZE = 2 * 1024 * 1024
MAX_FILES = 2000
MAX_DEPTH = 4
KEEP_BACKUPS = 50


class ConfigError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


class Conflict(ConfigError):
    """Dosya açıldıktan sonra dışarıda değişti."""


def kind_of(path):
    return KINDS.get(os.path.splitext(path)[1].lower())


def _inside(root, path):
    root, path = os.path.normcase(os.path.realpath(root)), os.path.normcase(os.path.realpath(path))
    return path != root and os.path.commonpath([root, path]) == root


def _is_world(path):
    return os.path.isfile(os.path.join(path, "level.dat"))


def list_configs(root):
    """Sunucu klasöründeki ayar dosyaları (göreli yollar, / ile). Önce kök, sonra config/, plugins/, mods/…"""
    out = []
    root = os.path.abspath(root)
    for cur, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(cur, root)
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        worlds = [d for d in dirs if _is_world(os.path.join(cur, d))]
        for w in worlds:                        # dünya klasörü: yalnızca içindeki paper-world.yml gibi ayarlar
            for f in sorted(os.listdir(os.path.join(cur, w))):
                if kind_of(f) == "yaml" and os.path.isfile(os.path.join(cur, w, f)):
                    out.append(os.path.relpath(os.path.join(cur, w, f), root).replace(os.sep, "/"))
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                         and depth < MAX_DEPTH and d not in worlds)
        for f in sorted(files):
            if not kind_of(f):
                continue
            full = os.path.join(cur, f)
            try:
                if os.path.getsize(full) > MAX_SIZE:
                    continue
            except OSError:
                continue
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
            if len(out) >= MAX_FILES:
                return _sort(out)
    return _sort(out)


def _sort(paths):
    order = {"config": 1, "plugins": 3, "mods": 4, "defaultconfigs": 5}
    return sorted(paths, key=lambda p: (0 if "/" not in p else order.get(p.split("/", 1)[0], 2), p.lower()))


# ------------------------------------------------------------------ okuma / yazma
def read(root, rel):
    """(metin, satır sonu, değiştirilme zamanı)."""
    path = os.path.join(root, rel)
    if not _inside(root, path):
        raise ConfigError(N_("Bu konum sunucu klasörünün dışında: {path}"), path=rel)
    try:
        if os.path.getsize(path) > MAX_SIZE:
            raise ConfigError(N_("Dosya çok büyük (en fazla 2 MB)."))
        with open(path, "rb") as f:
            raw = f.read()
        mtime = os.path.getmtime(path)
    except OSError as e:
        raise ConfigError(N_("Dosya açılamadı: {error}"), error=str(e))
    if b"\0" in raw[:4096]:
        raise ConfigError(N_("Bu dosya metin değil."))
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), {"newline": nl, "bom": bom}, mtime


def save(root, rel, text, fmt, mtime):
    """Kaydeder; eski hali yedekler. Yeni değiştirilme zamanını döndürür.
    mtime dosyanın açıldığı andaki zamansa ve dosya o zamandan beri değiştiyse Conflict."""
    path = os.path.join(root, rel)
    if not _inside(root, path):
        raise ConfigError(N_("Bu konum sunucu klasörünün dışında: {path}"), path=rel)
    if mtime is not None and os.path.exists(path) and abs(os.path.getmtime(path) - mtime) > 0.001:
        raise Conflict(N_("Dosya sen açtıktan sonra değişti (sunucu ya da başka bir program yazmış olabilir)."))
    if os.path.exists(path):
        backup(root, rel)
    data = text.replace("\r\n", "\n").replace("\n", fmt.get("newline", "\n")).encode("utf-8")
    if fmt.get("bom"):
        data = b"\xef\xbb\xbf" + data
    tmp = path + ".spypaper.tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise ConfigError(N_("Kaydedilemedi: {error}"), error=str(e))
    return os.path.getmtime(path)


def backup_root(root):
    return os.path.join(root, "backups", "configs")


def backup(root, rel):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_root(root), stamp, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(os.path.join(root, rel), dest)
    _prune(backup_root(root))
    return dest


def _prune(folder):
    try:
        dirs = sorted(d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d)))
    except OSError:
        return
    for d in dirs[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(folder, d), ignore_errors=True)


def backups_of(root, rel):
    """[(zaman damgası klasörü, tam yol)] yeniden eskiye."""
    out = []
    base = backup_root(root)
    try:
        for d in sorted(os.listdir(base), reverse=True):
            p = os.path.join(base, d, rel)
            if os.path.isfile(p):
                out.append((d, p))
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ denetim
HINTS = (   # (ham mesajda geçen, açıklama)
    ("found character '\\t'", N_("YAML'da sekme (Tab) kullanılamaz; girintide boşluk kullan.")),
    ("expected <block end>", N_("Girinti hatalı: bu satır üstündekilerle aynı hizada değil.")),
    ("mapping values are not allowed", N_("Bu satırda fazladan ':' var ya da girinti hatalı. Değer ':' içeriyorsa tırnak içine al.")),
    ("could not find expected ':'", N_("Bir anahtarın ':' işareti eksik ya da girinti hatalı.")),
    ("while scanning a quoted scalar", N_("Açılan tırnak kapanmamış.")),
    ("found unexpected end of stream", N_("Dosya beklenmedik yerde bitti: kapanmamış tırnak ya da parantez olabilir.")),
    ("expected ',' or ']'", N_("Köşeli parantez [ ] kapanmamış ya da öğeler arasında virgül eksik.")),
    ("expected ',' or '}'", N_("Süslü parantez { } kapanmamış ya da öğeler arasında virgül eksik.")),
    ("found undefined alias", N_("Tanımsız bir takma ad (*) kullanılmış.")),
    ("Expecting property name enclosed in double quotes", N_("JSON'da son öğeden sonra virgül olamaz ve anahtarlar çift tırnakla yazılır.")),
    ("Expecting ',' delimiter", N_("JSON'da öğeler arasında virgül eksik.")),
    ("Invalid value", N_("Değer geçersiz ya da eksik (metinler tırnak içinde yazılır).")),
)


def _yaml_loader():
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        seen = {}
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError:
                continue
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r} (first at line {seen[key] + 1})", key_node.start_mark)
            seen[key] = key_node.start_mark.line
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    return Loader


def validate(kind, text):
    """Hata yoksa None; varsa {line, col, message, hint, hint_kw}. line 1'den başlar."""
    if kind == "yaml":
        import yaml
        try:
            yaml.load(text, Loader=_yaml_loader())
            return None
        except yaml.MarkedYAMLError as e:
            m = e.problem_mark or e.context_mark
            raw = " ".join(x for x in (e.context, e.problem) if x)
            res = {"line": m.line + 1 if m else 0, "col": m.column + 1 if m else 0, "message": raw}
            dup = re.match(r"duplicate key (.+) \(first at line (\d+)\)", e.problem or "")
            if dup:
                res["hint"] = N_("Aynı anahtar iki kez yazılmış: {key} (ilki {line}. satırda).")
                res["hint_kw"] = {"key": dup.group(1).strip("'\""), "line": dup.group(2)}
            return _hint(res)
        except yaml.YAMLError as e:
            return {"line": 0, "col": 0, "message": str(e)}
    if kind == "toml":
        import tomllib
        try:
            tomllib.loads(text)
            return None
        except tomllib.TOMLDecodeError as e:
            msg = str(e)
            m = re.search(r"\(at line (\d+), column (\d+)\)", msg)
            res = {"line": int(m.group(1)) if m else 0, "col": int(m.group(2)) if m else 0,
                   "message": re.sub(r"\s*\(at line \d+, column \d+\)", "", msg)}
            if "Cannot overwrite a value" in msg or "Cannot declare" in msg:
                res["hint"] = N_("Aynı anahtar ya da tablo iki kez tanımlanmış.")
            return _hint(res)
    if kind == "json":
        try:
            json.loads(text) if text.strip() else None
            return None
        except json.JSONDecodeError as e:
            return _hint({"line": e.lineno, "col": e.colno, "message": e.msg})
    return None


def _hint(res):
    if "hint" not in res:
        for needle, hint in HINTS:
            if needle in res["message"]:
                res["hint"] = hint
                break
    return res
