"""Eklentiler, server.properties, sunucu ikonu ve dünya yedekleri."""
import os
import shutil
import zipfile
from datetime import datetime

from .config import N_, is_modded


# --- eklentiler / modlar ---
class PluginStore:
    """Paper/Purpur/Spigot için plugins/, Fabric/Quilt/Forge/NeoForge için mods/ klasörünü yönetir.
    Yazılım her listelemede yeniden algılanır (Güncelle ile yazılım değişebilir)."""

    def __init__(self, server_path, profile=None):
        self.profile = profile
        self.set_server_path(server_path)

    def set_server_path(self, path):
        self.server_path = path

    @property
    def modded(self):
        return is_modded(self.server_path)

    @property
    def folder(self):
        if self.modded:
            custom = self.profile.get("mods_folder") if self.profile else ""
            return custom or os.path.join(self.server_path, "mods")
        return os.path.join(self.server_path, "plugins")

    def list(self):
        """[(dosya_adı, boyut_byte, etkin_mi)] — .jar.disabled dosyaları devre dışı sayılır."""
        if not os.path.isdir(self.folder):
            return []
        out = []
        for f in sorted(os.listdir(self.folder), key=str.lower):
            low = f.lower()
            if low.endswith(".jar") or low.endswith(".jar.disabled"):
                size = os.path.getsize(os.path.join(self.folder, f))
                out.append((f, size, low.endswith(".jar")))
        return out

    def add(self, paths):
        os.makedirs(self.folder, exist_ok=True)
        for src in paths:
            shutil.copy2(src, os.path.join(self.folder, os.path.basename(src)))

    def remove(self, file_name):
        p = os.path.join(self.folder, file_name)
        if os.path.exists(p):
            os.remove(p)

    def toggle(self, file_name):
        p = os.path.join(self.folder, file_name)
        new = p[:-len(".disabled")] if p.endswith(".disabled") else p + ".disabled"
        os.rename(p, new)
        return os.path.basename(new)


# --- server.properties ---
class ServerProperties:
    def __init__(self, server_path):
        self.set_server_path(server_path)

    def set_server_path(self, path):
        self.server_path = path
        self.file = os.path.join(path, "server.properties")

    @property
    def exists(self):
        return os.path.exists(self.file)

    def load(self):
        """Sıralı {anahtar: değer} sözlüğü."""
        props = {}
        if not self.exists:
            return props
        with open(self.file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    props[k.strip()] = v.strip()
        return props

    def save(self, values):
        """Yorumları ve sırayı koruyarak değerleri günceller."""
        if not self.exists:
            raise FileNotFoundError(N_("server.properties dosyası bulunamadı!"))
        values = {k: ("true" if v is True else "false" if v is False else str(v)) for k, v in values.items()}
        written, lines = set(), []
        with open(self.file, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.rstrip("\n")
                s = raw.strip()
                if s and not s.startswith("#") and "=" in s:
                    k = s.split("=", 1)[0].strip()
                    if k in values:
                        lines.append(f"{k}={values[k]}")
                        written.add(k)
                        continue
                lines.append(raw)
        for k, v in values.items():
            if k not in written:
                lines.append(f"{k}={v}")
        with open(self.file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def set(self, key, value):
        self.save({key: value})

    def get(self, key, default=None):
        return self.load().get(key, default)

    def set_icon(self, png_path):
        shutil.copy2(png_path, os.path.join(self.server_path, "server-icon.png"))

    @property
    def icon_path(self):
        p = os.path.join(self.server_path, "server-icon.png")
        return p if os.path.exists(p) else None


# --- whitelist / ban listeleri ---
def read_name_list(server_path, file_name):
    """whitelist.json, banned-players.json, ops.json -> [isim]."""
    import json
    p = os.path.join(server_path, file_name)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return [e.get("name", "?") for e in json.load(f)]
    except Exception:
        return []


# --- yedekler ---
class BackupManager:
    WORLD_DIRS = ("world", "world_nether", "world_the_end")

    def __init__(self, server_path):
        self.set_server_path(server_path)

    def set_server_path(self, path):
        self.server_path = path
        self.folder = os.path.join(path, "backups")

    def create(self, progress=None):
        """Tüm dünya klasörlerini tek zip'e yedekler. progress(i, toplam) çağrılabilir."""
        worlds = [w for w in self.WORLD_DIRS if os.path.isdir(os.path.join(self.server_path, w))]
        if not worlds:
            raise FileNotFoundError(N_("'world' klasörü bulunamadı!"))
        files = []
        for w in worlds:
            base = os.path.join(self.server_path, w)
            for root, _, fs in os.walk(base):
                for fn in fs:
                    if fn == "session.lock":
                        continue
                    full = os.path.join(root, fn)
                    files.append((full, os.path.relpath(full, self.server_path)))
        os.makedirs(self.folder, exist_ok=True)
        zip_path = os.path.join(self.folder, f"world_backup_{datetime.now():%Y%m%d_%H%M%S}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for i, (full, rel) in enumerate(files, 1):
                try:
                    z.write(full, rel)
                except (PermissionError, OSError):
                    pass
                if progress:
                    progress(i, len(files))
        return zip_path

    def list(self):
        """[(dosya_adı, boyut_byte, datetime)] yeniden eskiye."""
        if not os.path.isdir(self.folder):
            return []
        out = []
        for f in os.listdir(self.folder):
            if f.endswith(".zip"):
                p = os.path.join(self.folder, f)
                out.append((f, os.path.getsize(p), datetime.fromtimestamp(os.path.getmtime(p))))
        return sorted(out, key=lambda x: x[2], reverse=True)
