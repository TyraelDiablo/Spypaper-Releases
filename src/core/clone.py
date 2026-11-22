"""Sunucu klonlama: bir sunucunun klasörünü kopyalar ve yeni bir profil olarak ekler.

Kopyalanmayanlar: loglar, çökme raporları, yedekler (backups/), kilit dosyaları ve isteğe göre dünya klasörleri
(<level>, Bukkit/Paper'daki <level>_nether ve <level>_the_end). Yeni sunucunun portları (server-port, query.port,
rcon.port) diğer kayıtlı sunucularla çakışmayacak şekilde değiştirilir.
"""
import os
import shutil

from .config import N_

SKIP_ALWAYS = {"logs", "crash-reports", "backups", "session.lock", "cache"}
PORT_KEYS = ("server-port", "query.port", "rcon.port")
SKIP_PROFILE_KEYS = {"id", "name", "server_path", "last_opened", "created", "pin_hash", "danger_pin_hash",
                     "skin_overrides", "content_share"}


class CloneError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def read_props(path):
    out = {}
    try:
        with open(os.path.join(path, "server.properties"), encoding="utf-8") as f:
            for ln in f:
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.rstrip("\n").split("=", 1)
                    out[k.strip()] = v
    except OSError:
        pass
    return out


def write_props(path, changes):
    p = os.path.join(path, "server.properties")
    try:
        with open(p, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return
    done = set()
    for i, ln in enumerate(lines):
        k = ln.split("=", 1)[0].strip()
        if k in changes and "=" in ln and not ln.lstrip().startswith("#"):
            lines[i] = f"{k}={changes[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in changes.items() if k not in done]
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def used_ports(paths):
    used = set()
    for p in paths:
        props = read_props(p)
        for k in PORT_KEYS:
            try:
                used.add(int(props.get(k, "")))
            except ValueError:
                pass
        if not props.get("server-port"):
            used.add(25565)
    return used


def free_port(start, used):
    p = max(1025, int(start) + 1)
    while p in used or p > 65535:
        p = p + 1 if p < 65535 else 1025
    return p


def world_dirs(level):
    return {level, f"{level}_nether", f"{level}_the_end"}


def size_of(path, skip=()):
    total = 0
    for root, dirs, files in os.walk(path):
        if root == path:
            dirs[:] = [d for d in dirs if d not in skip]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def clone(src, dest, level="world", with_world=True, other_paths=(), progress=None):
    """src'yi dest'e kopyalar. (yeni_portlar) sözlüğü döndürür. dest var olmamalı."""
    src, dest = os.path.abspath(src), os.path.abspath(dest)
    if not os.path.isdir(src):
        raise CloneError(N_("Sunucu klasörü bulunamadı: {path}"), path=src)
    if os.path.exists(dest):
        raise CloneError(N_("Hedef klasör zaten var: {path}"), path=dest)
    if dest.startswith(src + os.sep):
        raise CloneError(N_("Kopya, sunucunun kendi klasörünün içine konamaz."))
    skip = set(SKIP_ALWAYS) | (set() if with_world else world_dirs(level))
    total = max(1, size_of(src, skip))
    done = [0]

    def copy(s, d):
        shutil.copy2(s, d)
        try:
            done[0] += os.path.getsize(s)
        except OSError:
            pass
        if progress:
            progress(done[0], total)

    def ignore(folder, names):
        if os.path.abspath(folder) == src:
            return [n for n in names if n in skip]
        return [n for n in names if n == "session.lock"]

    tmp = dest + ".part"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    try:
        shutil.copytree(src, tmp, ignore=ignore, copy_function=copy)
        os.replace(tmp, dest)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    props = read_props(dest)
    used = used_ports([src, *other_paths])
    changes = {}
    for k in PORT_KEYS:
        if k in props or k == "server-port":
            try:
                cur = int(props.get(k) or 25565)
            except ValueError:
                cur = 25565
            changes[k] = free_port(cur, used)
            used.add(changes[k])
    write_props(dest, changes)
    return changes


def profile_copy(data):
    """Kopyalanacak profil ayarları (kimlik, ad, yol, PIN'ler ve sunucuya özel paylaşım hariç)."""
    return {k: v for k, v in data.items() if k not in SKIP_PROFILE_KEYS}
