"""Bot oyuncular: panelden sunucuya sahte oyuncu (fake player) koymak.

Oyuncular AFK farmlarda bilgisayar başında kalmak zorunda kalmasın diye: bot, istenen yerde durur, chunk'ları
yüklü tutar; istenirse sürekli/aralıklı vurur (mob farmı), sağ tıklar (balık, ekin, sandık) ya da eğilir.
Spypaper botları kendisi oluşturmaz; sunucu türüne göre bilinen bir eklenti/mod kullanır ve onu Modrinth'ten kurar:
  * Paper / Purpur: Spypaper'ın kendi bot motoru (SpypaperMessages eklentisi; başka eklentiye bağlı değil)
  * Fabric: Carpet (/player)
Bot listesi profilde saklanır; "Sunucu açılınca otomatik gelsin" işaretli botlar sunucu her açıldığında yerine
konur ve işine başlar.

Botlar Spypaper'ın başka yerlerinde gerçek oyuncu sayılmaz: Hile Koruması (doğrulama, izinsiz OP) ve bakım modu
onları atmaz, ön oluşturma onlar yüzünden duraklamaz, sayılarda ve raporlarda ayrı tutulur. Kendi listede olmayan
ama sunucunun içinden bağlanan (giriş satırında IP yerine "local") oyuncular da bot sayılır.
"""
import os
import re

from .config import N_

BUKKIT = {"Paper", "Purpur", "Folia", "Spigot", "Pufferfish"}
ACTIONS = ("none", "attack", "use", "sneak")
NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
LOCAL_JOIN = re.compile(r"(\w{1,16})\[/?(?:local|null|127\.0\.0\.1:0)\] logged in")

PROVIDERS = {
    "spypaper": {                        # Spypaper'ın kendi bot motoru (SpypaperMessages eklentisinin içinde)
        "name": "Spypaper bot motoru",
        "folder": "plugins",
    },
    "carpet": {
        "name": "Carpet",
        "slug": ("carpet",),
        "jar": ("fabric-carpet", "carpet"),
        "folder": "mods",
    },
}


class BotError(Exception):
    no_version = False

    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def provider_for(software):
    if software in ("Paper", "Purpur", "Pufferfish"):   # Folia'nın bölgesel zamanlayıcısı farklı: desteklenmiyor
        return "spypaper"
    if software in ("Fabric", "Quilt"):
        return "carpet"
    return None


def installed(server_path, prov):
    if prov == "spypaper":
        from . import playermsg
        return playermsg.plugin_installed(server_path)
    info = PROVIDERS[prov]
    d = os.path.join(server_path, info["folder"])
    try:
        return any(f.lower().endswith(".jar") and f.lower().startswith(info["jar"]) for f in os.listdir(d))
    except OSError:
        return False


def install(server_path, prov, software, mc_version, modded, any_version=False):
    if prov == "spypaper":
        from . import playermsg
        playermsg.set_plugin(server_path, True)
        return playermsg.JAR
    from . import modrinth as M
    info = PROVIDERS[prov]
    _kind, loaders = M.context(software, mc_version, modded)
    vers = None
    for slug in info["slug"]:
        try:
            vers = M.versions(slug, loaders) if any_version else M.versions(slug, loaders, mc_version)
        except Exception as e:                      # bu slug yoksa sıradakini dene
            print(f"[bot] {slug}: {e}")
            vers = None
        if vers:
            break
    if not vers:
        e = BotError(N_("Bu sunucu için uygun {name} sürümü bulunamadı ({soft} {mc})."), name=info["name"],
                     soft=software, mc=mc_version)
        e.no_version = not any_version
        raise e
    folder = os.path.join(server_path, info["folder"])
    os.makedirs(folder, exist_ok=True)
    path = M.download(vers[0]["file"], folder)
    if info.get("expect") and not _has_command(path, info["expect"]):
        try:
            os.remove(path)
        except OSError:
            pass
        raise BotError(N_("İndirilen dosya beklenen {name} değil; kaldırıldı."), name=info["name"])
    return path


def _has_command(jar, cmd):
    """Aynı adlı başka (ör. örnek/oyuncak) bir projeyi elemek için kaba denetim: komut ya da takma ad tanımlı
    olmalı; tanımsızsa (Brigadier ile kaydeden eklentiler) jar gerçek bir eklenti boyutunda ve örnek paket değil."""
    import zipfile
    try:
        size = os.path.getsize(jar)
        with zipfile.ZipFile(jar) as z:
            names = z.namelist()
            for n in ("plugin.yml", "paper-plugin.yml"):
                if n in names:
                    txt = z.read(n).decode("utf-8", "replace")
                    if "com.example" in txt:
                        return False
                    if re.search(rf"(?m)^\s+{re.escape(cmd)}\s*:", txt) or re.search(rf"aliases:.*\b{re.escape(cmd)}\b", txt):
                        return True
            return size > 100_000 and not any(n.startswith("com/example/") for n in names)
    except (OSError, zipfile.BadZipFile):
        return False


def world_name(software, level, dim):
    """Komutun beklediği dünya adı: Bukkit'te klasör adı, diğerlerinde boyut kimliği."""
    if software in BUKKIT:
        return {"minecraft:the_nether": level + "_nether", "minecraft:the_end": level + "_the_end"}.get(dim, level)
    return dim


# ------------------------------------------------------------ komutlar
def spawn_commands(prov, bot, software, level):
    n = bot["name"]
    x, y, z = (round(float(bot[k]), 2) for k in ("x", "y", "z"))
    yaw, pitch = round(float(bot.get("yaw", 0)), 1), round(float(bot.get("pitch", 0)), 1)
    w = world_name(software, level, bot.get("dim", "minecraft:overworld"))
    if prov == "carpet":
        return [f"player {n} spawn at {x} {y} {z} facing {yaw} {pitch} in {w} in survival"]
    return [f"spypaper-bot spawn {n} {w} {x} {y} {z} {yaw} {pitch}"]


def action_commands(prov, bot):
    n, act = bot["name"], bot.get("action", "none")
    every = max(1, int(bot.get("interval", 20)))
    if prov == "carpet":
        out = [f"player {n} stop"]
        if act == "attack":
            out.append(f"player {n} attack interval {every}" if bot.get("interval") else f"player {n} attack continuous")
        elif act == "use":
            out.append(f"player {n} use interval {every}" if bot.get("interval") else f"player {n} use continuous")
        elif act == "sneak":
            out.append(f"player {n} sneak")
        return out
    return [f"spypaper-bot action {n} {act} {int(bot.get('interval') or 0)}"]


def remove_commands(prov, name):
    return [f"player {name} kill"] if prov == "carpet" else [f"spypaper-bot remove {name}"]


# ------------------------------------------------------------ yönetici
class Bots:
    def __init__(self, config, server):
        self.config, self.server = config, server
        self.local = set()                 # bu oturumda "local" bağlanan oyuncular (küçük harf)
        server.line_filters.append(self._line)

    # liste
    def entries(self):
        return list(self.config.get("bots") or [])

    def _save(self, items):
        self.config.set("bots", items)

    def get(self, name):
        return next((b for b in self.entries() if b["name"].lower() == name.lower()), None)

    def upsert(self, bot):
        if not NAME_RE.match(bot.get("name", "")):
            raise BotError(N_("Bot adı 3-16 karakter olmalı; yalnızca harf, rakam ve _ kullanılabilir."))
        if bot.get("action") not in ACTIONS:
            bot["action"] = "none"
        items = [b for b in self.entries() if b["name"].lower() != bot["name"].lower()] + [bot]
        self._save(items)

    def delete(self, name):
        self._save([b for b in self.entries() if b["name"].lower() != name.lower()])

    def is_bot(self, name):
        n = (name or "").lower()
        return n in self.local or any(b["name"].lower() == n for b in self.entries())

    def names(self):
        return {b["name"].lower() for b in self.entries()} | self.local

    # sunucu
    def _line(self, line):
        m = LOCAL_JOIN.search(line)
        if m:
            self.local.add(m.group(1).lower())
        return False                       # yalnızca izler, satırı gizlemez

    def spawn(self, bot, software, level):
        prov = provider_for(software)
        if not prov:
            raise BotError(N_("Bu sunucu türünde bot desteklenmiyor (Paper, Purpur ya da Fabric gerekir)."))
        if not installed(self.config.server_path, prov):
            raise BotError(N_("{name} kurulu değil; önce Kur'a bas ve sunucuyu yeniden başlat."),
                           name=PROVIDERS[prov]["name"])
        for c in spawn_commands(prov, bot, software, level) + action_commands(prov, bot):
            self.server.send(c)

    def act(self, bot, software):
        prov = provider_for(software)
        for c in action_commands(prov, bot):
            self.server.send(c)

    def remove(self, name, software):
        prov = provider_for(software)
        for c in remove_commands(prov, name):
            self.server.send(c)

    def autostart(self, software, level):
        """Sunucu açılınca: "otomatik" işaretli botları yerine koyar."""
        done = 0
        for b in self.entries():
            if b.get("auto"):
                try:
                    self.spawn(b, software, level)
                    done += 1
                except Exception as e:
                    print(f"[bot] {b['name']}: {e}")
        return done
