"""Uygulama ayarları ve kayıtlı sunucu profilleri (config.json).

config.json yapısı:
{
  "language": "tr", "theme": "gece", "font_scale": 1.0, ...   # genel ayarlar
  "servers": [ {"id": "...", "name": "GKMY", "server_path": "...", "jar_name": ...}, ... ],
  "last_server": "<id>"
}
Eski tek sunuculu config.json ({"server_path": ...}) otomatik taşınır.
"""
import json
import os
import re
import sys
import uuid
from datetime import datetime

CONFIG_FILE = "config.json"


def N_(text):
    """Çeviri işareti: metni olduğu gibi döndürür, tools/extract_strings.py toplar.
    Gösterilirken arayüz t(...) uygular."""
    return text

SERVER_DEFAULTS = {
    "name": "",
    "server_path": "",
    "jar_name": "server.jar",
    "java_path": "java",
    "ram_min": "2G",
    "ram_max": "4G",
    "bluemap_url": "http://localhost:8100",
    "maintenance_schedule": {},   # core.maintenance.SCHEDULE_DEFAULTS
    "maintenance_state": {},
    "notes": "",               # kullanıcının bu sunucu için notları
    "homes": {},               # core.homes: oyuncu başına en fazla 10 ev
    "esplora_knowledge": "",   # sunucu sahibinin Esplora için yazdığı bilgiler
    "content": [],             # core.content: içerik editörünün içerikleri
    "content_share": {},       # kaynak paketini Spypaper paylaşsın mı (core.packhost)
    "guard": {},               # Hile Koruması (core.guard.DEFAULTS)
    "world_border": {},        # Dünya Sınırı kartının son değerleri (core.worldborder)
    "esplora_access": {},      # Esplora veri izinleri (core.esplora_access)
    "auto_restart": False,     # çökünce otomatik yeniden başlat
    "backup_keep": 0,          # saklanacak yedek sayısı (0 = sınırsız)
    "danger_pin_hash": "",     # sunucuda PIN yoksa yalnızca Tehlikeli Bölge için PIN
    "last_opened": "",
    "safe_mode": 0,            # 0 kapalı, 1 düşük, 2 orta, 3 yüksek (core.safemode)
    "pin_hash": "",            # boşsa PIN yok
    "mods_folder": "",         # boşsa <sunucu>/mods
    "created": "",
}

APP_DEFAULTS = {
    "language": "tr",
    "theme": "gece",
    "font_scale": 1.0,
    "high_contrast": False,
    "reduce_motion": False,
    "confirm_on_close": True,
    "open_last_on_start": False,
    "console_max_lines": 5000,
    "log_poll_seconds": 1,
    "update_contact": "",
    "translate_logs": True,
    "check_updates": True,
    "player_heads": True,      # oyuncu kafalarını Mojang'dan indir (core.skins)     # açılışta Spypaper güncellemesi denetlensin (core.appupdate)
    "skip_version": "",
    "page_order": [],          # sunucu panelindeki sekmelerin sırası (sayfa sınıf adları)
    "hidden_pages": [],
    "dashboard_hidden": [],    # gösterge panelinde gizlenen kartlar
    "ai": {},                  # yapay zeka ayarları (core.ai)
    "esplora_save_chats": True,  # Esplora sohbetleri bu bilgisayarda saklansın (core.esplora_chats)
    "servers": [],
    "last_server": "",
}


def get_base_dir():
    """exe ya da main.py'nin bulunduğu dizin."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    """Exe içine gömülü dosyalar (PyInstaller --add-data) için kök."""
    return getattr(sys, "_MEIPASS", get_base_dir())


MODDED = {"Fabric", "Quilt", "Forge", "NeoForge"}     # eklenti yerine mod kullanan yazılımlar
ARGS_FILE = "win_args.txt" if os.name == "nt" else "unix_args.txt"


def detect_args_files(path):
    """Forge (1.17+) / NeoForge kurulumlarının başlatma argüman dosyaları (göreli yol, / ile).
    Bunlar jar yerine 'java @user_jvm_args.txt @libraries/.../win_args.txt' biçiminde çalıştırılır."""
    out = []
    for sub in (("net", "neoforged", "neoforge"), ("net", "minecraftforge", "forge")):
        base = os.path.join(path, "libraries", *sub)
        if not os.path.isdir(base):
            continue
        for ver in os.listdir(base):
            if os.path.isfile(os.path.join(base, ver, ARGS_FILE)):
                out.append("/".join(("libraries",) + sub + (ver, ARGS_FILE)))
    # sayı ve metin parçaları ayrı tutulur ki "21.1.77" ile "21.1.77.1" karşılaştırılırken hata olmasın
    def key(p):
        ver = p.split("/")[-2]          # libraries/.../<sürüm>/win_args.txt
        return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.\-]", ver)]
    return sorted(out, key=key, reverse=True)


def detect_jars(path):
    """Klasördeki çalıştırılabilir sunucu jar'ları (ve Forge/NeoForge argüman dosyaları), en olası önce."""
    if not os.path.isdir(path):
        return []
    jars = [f for f in os.listdir(path) if f.lower().endswith(".jar") and "installer" not in f.lower()]

    def score(f):
        low = f.lower()
        return (0 if low == "server.jar" else
                1 if re.match(r"(paper|purpur|spigot|folia|pufferfish|fabric-server|minecraft_server|forge-)", low)
                else 2 if "server" in low else 3, low)
    return detect_args_files(path) + sorted(jars, key=score)


def detect_version(path):
    """latest.log'dan Minecraft sürümü ve yazılım (Paper/Purpur/Fabric/Forge/NeoForge/Vanilla...)."""
    log = os.path.join(path, "logs", "latest.log")
    ver, soft = "", ""
    if os.path.exists(log):
        try:
            with open(log, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i > 600:
                        break
                    m = re.search(r"Starting minecraft server version ([\w.\-]+)", line)
                    if m:
                        ver = m.group(1)
                    if not soft:
                        m = re.search(r"This server is running (\w+) version", line)
                        if m:
                            soft = m.group(1)
                        elif re.search(r"launchTarget, neoforgeserver|NeoForge mod loading|neoforge-\d", line, re.I):
                            soft = "NeoForge"
                        elif re.search(r"launchTarget, forgeserver|MinecraftForge v\d|Forge mod loading", line):
                            soft = "Forge"
                        elif "with Quilt Loader" in line:
                            soft = "Quilt"
                        elif "with Fabric Loader" in line:
                            soft = "Fabric"
                    if ver and soft:
                        break
        except Exception:
            pass
    if not soft:
        if os.path.isdir(os.path.join(path, "libraries", "net", "neoforged")):
            soft = "NeoForge"
        elif os.path.isdir(os.path.join(path, "libraries", "net", "minecraftforge", "forge")):
            soft = "Forge"
    if not soft:
        for j in detect_jars(path):
            low = j.lower()
            for name, label in (("paper", "Paper"), ("purpur", "Purpur"), ("spigot", "Spigot"), ("folia", "Folia"),
                                ("fabric", "Fabric"), ("quilt", "Quilt"), ("neoforge", "NeoForge"), ("forge", "Forge")):
                if name in low:
                    soft = label
                    break
            if soft:
                break
    return ver, soft or ("Vanilla" if ver else "")


def is_modded(path):
    return detect_version(path)[1] in MODDED


class ServerProfile:
    """Tek bir kayıtlı sunucu. ServerProcess vb. bunu 'config' olarak kullanır."""

    def __init__(self, settings, data):
        self.settings = settings
        self.data = data

    @property
    def id(self):
        return self.data["id"]

    @property
    def name(self):
        return self.data.get("name") or os.path.basename(self.server_path.rstrip("/\\")) or "Sunucu"

    @property
    def server_path(self):
        return self.data.get("server_path", "")

    def get(self, key):
        return self.data.get(key, SERVER_DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def save(self):
        self.settings.save()

    @property
    def exists(self):
        return os.path.isdir(self.server_path)


class Settings:
    def __init__(self, path=None):
        self.path = path or os.path.join(get_base_dir(), CONFIG_FILE)
        self.data = json.loads(json.dumps(APP_DEFAULTS))
        self.load()

    def load(self):
        raw = {}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception:
                raw = {}
        # eski tek sunuculu format -> profil
        if "server_path" in raw and not raw.get("servers"):
            legacy = {k: raw.pop(k) for k in list(raw) if k in SERVER_DEFAULTS}
            if legacy.get("server_path"):
                raw["servers"] = [self._new_server_dict(**legacy)]
                raw["last_server"] = raw["servers"][0]["id"]
        self.data.update(raw)
        for s in self.data["servers"]:
            for k, v in SERVER_DEFAULTS.items():
                s.setdefault(k, v)
            s.setdefault("id", uuid.uuid4().hex[:10])
        self.save()

    def save(self):
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[config] kaydedilemedi: {e}")

    def get(self, key):
        return self.data.get(key, APP_DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # --- sunucular ---
    @staticmethod
    def _new_server_dict(**kw):
        d = dict(SERVER_DEFAULTS)
        d.update(kw)
        d["id"] = uuid.uuid4().hex[:10]
        d["created"] = d.get("created") or datetime.now().isoformat(timespec="seconds")
        if not d.get("name"):
            d["name"] = os.path.basename(d["server_path"].rstrip("/\\")) or "Sunucu"
        jars = detect_jars(d["server_path"])
        if jars and d.get("jar_name") not in jars:
            d["jar_name"] = jars[0]
        return d

    def servers(self):
        return [ServerProfile(self, d) for d in self.data["servers"]]

    def server(self, sid):
        for d in self.data["servers"]:
            if d["id"] == sid:
                return ServerProfile(self, d)
        return None

    def add_server(self, path, name="", **kw):
        d = self._new_server_dict(server_path=path, name=name, **kw)
        self.data["servers"].append(d)
        self.save()
        return ServerProfile(self, d)

    def remove_server(self, sid):
        self.data["servers"] = [d for d in self.data["servers"] if d["id"] != sid]
        if self.data.get("last_server") == sid:
            self.data["last_server"] = ""
        self.save()

    def touch(self, sid):
        p = self.server(sid)
        if p:
            p.data["last_opened"] = datetime.now().isoformat(timespec="seconds")
            self.data["last_server"] = sid
            self.save()
