"""Oyuncu verileri: UUID çözümleme, NBT okuma, envanter, istatistik."""
import gzip
import io
import json
import os
import re
import struct
import time
import uuid
from dataclasses import dataclass, field

import nbtlib

from .config import N_, get_base_dir

ARMOR_SLOTS = {103: N_("Miğfer"), 102: N_("Göğüslük"), 101: N_("Pantolon"), 100: N_("Bot")}
OFFHAND_SLOT = -106


@dataclass
class Player:
    name: str
    uuid: str
    data_file: str
    online: bool = False


@dataclass
class ItemRow:
    slot: str
    item_id: str
    name: str
    count: int
    enchants: list = field(default_factory=list)        # [(id, seviye)]
    stored: list = field(default_factory=list)          # büyülü kitap
    trim: tuple = None                                  # (desen, malzeme)
    custom_name: str = ""
    damage: int = 0
    color: int = None
    unbreakable: bool = False
    extra: list = field(default_factory=list)           # diğer bileşenler (ham)


@dataclass
class PlayerDetails:
    xp_level: int = 0
    xp_progress: float = 0.0                        # mevcut seviyedeki ilerleme (0-1)
    health: float = 0.0
    absorption: float = 0.0                         # altın kalpler
    food: int = 0
    gamemode: int = -1                              # 0 hayatta kalma, 1 yaratıcı, 2 macera, 3 izleyici
    armor_points: int = 0                           # zırh göstergesi (0-20)
    inventory: list = field(default_factory=list)   # ItemRow (ana envanter, 0-35)
    armor: list = field(default_factory=list)       # ItemRow (4 slot, boşlar dahil)
    offhand: ItemRow = None
    ender: list = field(default_factory=list)
    last_death: tuple = None                        # (dim, x, y, z)
    pos: tuple = None                               # (dim, x, y, z) son kaydedilen konum


def hyphenate(u):
    u = u.replace("-", "").lower()
    if len(u) != 32:
        return u
    return f"{u[:8]}-{u[8:12]}-{u[12:16]}-{u[16:20]}-{u[20:]}"


def offline_uuid(name):
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:{name}")).lower()


def floodgate_uuid(name):
    return str(uuid.uuid3(uuid.NAMESPACE_DNS, f"OfflinePlayer:Floodgate:{name}")).lower()


def _val(v):
    return v.value if hasattr(v, "value") else v


def _get(compound, *names):
    """Anahtarı büyük/küçük harf duyarsız arar (sürümler arası farklar için)."""
    if compound is None or not hasattr(compound, "keys"):
        return None
    for n in names:
        if n in compound:
            return compound[n]
    lower = {str(k).lower(): k for k in compound.keys()}
    for n in names:
        k = lower.get(n.lower())
        if k is not None:
            return compound[k]
    return None


def read_nbt(file_path):
    """gzip'li ya da düz NBT dosyasını okur, kök compound'u döndürür."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                nbt = nbtlib.File.parse(gz)
        except Exception:
            nbt = nbtlib.File.parse(io.BytesIO(raw))
        return nbt.root if hasattr(nbt, "root") else nbt
    except Exception as e:
        print(f"NBT okuma hatası: {e}")
        return None


# Panel dili -> Minecraft dil kodu
MC_LANG = {
    "tr": "tr_tr", "en": "en_us", "de": "de_de", "fr": "fr_fr", "es": "es_es", "pt_BR": "pt_br",
    "it": "it_it", "nl": "nl_nl", "pl": "pl_pl", "ru": "ru_ru", "uk": "uk_ua", "az": "az_az",
    "ja": "ja_jp", "ko": "ko_kr", "zh_CN": "zh_cn", "ar": "ar_sa",
}


def mc_lang_code(ui_lang):
    return MC_LANG.get(ui_lang, ui_lang.lower())


def lang_dirs(server_path):
    """Minecraft dil dosyalarının arandığı klasörler (öncelik sırasıyla)."""
    base = get_base_dir()
    cands = [
        os.path.join(base, "Translation"),
        os.path.join(base, "dist", "Translation"),               # calistir.bat ile kaynak koddan çalışırken
        os.path.join(os.path.dirname(base), "Translation"),
        os.path.join(os.path.dirname(base), "dist", "Translation"),
        os.path.join(server_path, "Translation"),
        server_path,
    ]
    out = []
    for d in cands:
        d = os.path.normpath(d)
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def icon_dirs(server_path):
    return [os.path.join(os.path.dirname(d), "Icons") for d in lang_dirs(server_path)
            if os.path.isdir(os.path.join(os.path.dirname(d), "Icons"))] + \
           [d for d in (os.path.join(get_base_dir(), "Icons"),) if os.path.isdir(d)]


_ICON_CACHE = {}


def icon_path(item_id, server_path):
    """Eşya ikonu (png yolu) ya da None. Bloklar için yan/üst yüz denenir."""
    key = (item_id, server_path)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    names = [("items", item_id), ("item", item_id), ("block", item_id)]   # items/: modelden çizilen ikon
    for suf in ("_side", "_front", "_top", "_0", "_bottom"):
        names.append(("block", item_id + suf))
    base = re.sub(r"_(stairs|slab|wall|fence|fence_gate|button|pressure_plate)$", "", item_id)
    if base != item_id:
        for cand in (base, base + "s", base + "_planks", base.replace("brick", "bricks")):
            names.append(("block", cand))
    if item_id.endswith("_log") or item_id.endswith("_wood"):
        names.append(("block", item_id.replace("_wood", "_log")))
    found = None
    for d in dict.fromkeys(icon_dirs(server_path)):
        for kind, n in names:
            p = os.path.join(d, kind, n + ".png")
            if os.path.exists(p):
                found = p
                break
        if found:
            break
    _ICON_CACHE[key] = found
    return found


def find_lang_file(server_path, code):
    for d in lang_dirs(server_path):
        try:
            for f in os.listdir(d):
                if f.lower() == f"{code}.json":
                    return os.path.join(d, f)
        except OSError:
            continue
    return None


def _read_json(p):
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        print(f"[HATA] {p} okunamadı: {e}")
        return {}


class Translations:
    """Minecraft eşya adları: Translation/<mc_kodu>.json (örn. de_de.json).

    en_us.json taban olarak yüklenir, seçili dil üzerine yazılır; böylece seçili dilde
    eksik olan anahtarlar İngilizce, o da yoksa ID'den üretilen ad olarak görünür.
    self.status: "ok" | "fallback" (seçili dil yok, İngilizce) | "none" (hiç dosya yok)
    """

    def __init__(self):
        self.data = {}
        self.en = {}
        self.lang = "tr_tr"
        self.file = None
        self.status = "none"

    def load(self, server_path, lang=None):
        if lang:
            self.lang = lang
        en_p = find_lang_file(server_path, "en_us")
        self.en = _read_json(en_p) if en_p else {}
        self.data = dict(self.en)
        p = find_lang_file(server_path, self.lang) if self.lang != "en_us" else en_p
        if p:
            if p != en_p:
                self.data.update(_read_json(p))
            self.file, self.status = p, "ok"
        else:
            self.file = en_p
            self.status = "fallback" if en_p else "none"
        return self.file

    def item_name(self, item_id):
        clean = str(item_id).replace("minecraft:", "")
        return (
            self.data.get(f"item.minecraft.{clean}")
            or self.data.get(f"block.minecraft.{clean}")
            or clean.replace("_", " ").title()
        )

    def ench_name(self, eid, lvl):
        n = self.data.get(f"enchantment.minecraft.{eid}") or eid.replace("_", " ").title()
        if lvl and (lvl > 1 or eid not in ("mending", "silk_touch", "infinity", "flame", "channeling",
                                           "multishot", "aqua_affinity", "binding_curse", "vanishing_curse")):
            n += " " + (self.data.get(f"enchantment.level.{lvl}") or str(lvl))
        return n

    def trim_text(self, pattern, material):
        p = self.data.get(f"trim_pattern.minecraft.{pattern}") or pattern.title()
        m = self.data.get(f"trim_material.minecraft.{material}") or material.title()
        return f"{p} · {m}"

    def search_items(self, text, limit=500):
        """[(item_id, ad)] döndürür. ID ile eşleşme de desteklenir."""
        text = text.lower().strip()
        seen, out = set(), []
        for key, value in self.data.items():
            if key.startswith("item.minecraft."):
                iid = key[len("item.minecraft."):]
            elif key.startswith("block.minecraft."):
                iid = key[len("block.minecraft."):]
            else:
                continue
            if "." in iid or iid in seen:   # alt anahtarları (açıklamalar vb.) atla
                continue
            if text and text not in value.lower() and text not in iid:
                continue
            seen.add(iid)
            out.append((iid, value))
            if len(out) >= limit:
                break
        return out


def _ench_list(obj):
    """Büyüler: 1.20.5+ {levels:{id:lvl}} / 1.21.5+ {id:lvl} / eski [{id, lvl}]."""
    out = []
    if obj is None:
        return out
    if hasattr(obj, "keys"):
        levels = _get(obj, "levels")
        src = levels if levels is not None and hasattr(levels, "keys") else obj
        for k in src.keys():
            if k in ("show_in_tooltip", "levels"):
                continue
            try:
                out.append((str(k).replace("minecraft:", ""), int(_val(src[k]))))
            except (TypeError, ValueError):
                pass
    else:
        for e in obj:
            eid = str(_val(_get(e, "id") or "")).replace("minecraft:", "")
            lvl = _get(e, "lvl")
            if eid:
                out.append((eid, int(_val(lvl)) if lvl is not None else 1))
    return out


def _text(v):
    """Özel ad: düz metin ya da JSON metin bileşeni."""
    v = _val(v)
    if hasattr(v, "keys"):
        return str(_val(_get(v, "text") or ""))
    s = str(v)
    if s.startswith("{") or s.startswith('"'):
        try:
            j = json.loads(s)
            if isinstance(j, str):
                return j
            if isinstance(j, dict):
                return j.get("text", "") + "".join(x.get("text", "") for x in j.get("extra", []) if isinstance(x, dict))
        except Exception:
            pass
    return s


_ARMOR_BASE = {"leather": 5, "chainmail": 15, "iron": 15, "golden": 7, "diamond": 33, "netherite": 37, "turtle": 25}
_ARMOR_SLOT = {"helmet": 11, "chestplate": 16, "leggings": 15, "boots": 13}
_TOOL = {"wooden": 59, "stone": 131, "iron": 250, "golden": 32, "diamond": 1561, "netherite": 2031}
_SINGLE = {"elytra": 432, "bow": 384, "crossbow": 465, "trident": 250, "shield": 336, "fishing_rod": 64,
           "shears": 238, "flint_and_steel": 64, "mace": 500, "carrot_on_a_stick": 25, "brush": 64,
           "warped_fungus_on_a_stick": 100, "turtle_helmet": 275, "wolf_armor": 64}


# vanilla zırh puanları: (miğfer, göğüslük, pantolon, bot)
_ARMOR_POINTS = {"leather": (1, 3, 2, 1), "golden": (2, 5, 3, 1), "chainmail": (2, 5, 4, 1), "copper": (2, 4, 3, 1),
                 "iron": (2, 6, 5, 2), "diamond": (3, 8, 6, 3), "netherite": (3, 8, 6, 3)}
_PIECE = {"helmet": 0, "chestplate": 1, "leggings": 2, "boots": 3}


def armor_points(item_ids):
    """Giyilen zırhın toplam zırh puanı (0-20), Minecraft'ın zırh göstergesi için."""
    total = 0
    for iid in item_ids:
        iid = (iid or "").replace("minecraft:", "")
        if iid == "turtle_helmet":
            total += 2
            continue
        mat, _, piece = iid.rpartition("_")
        if mat in _ARMOR_POINTS and piece in _PIECE:
            total += _ARMOR_POINTS[mat][_PIECE[piece]]
    return min(total, 20)


def max_durability(item_id):
    if item_id in _SINGLE:
        return _SINGLE[item_id]
    mat, _, kind = item_id.partition("_")
    if kind in _ARMOR_SLOT and mat in _ARMOR_BASE:
        return _ARMOR_BASE[mat] * _ARMOR_SLOT[kind]
    if kind in ("sword", "pickaxe", "axe", "shovel", "hoe") and mat in _TOOL:
        return _TOOL[mat]
    return 0


def parse_item_props(item, row):
    comp = _get(item, "components")
    if comp is not None:                        # 1.20.5+ veri bileşenleri
        g = lambda k: _get(comp, f"minecraft:{k}", k)
        row.enchants = _ench_list(g("enchantments"))
        row.stored = _ench_list(g("stored_enchantments"))
        tr = g("trim")
        if tr is not None:
            row.trim = (str(_val(_get(tr, "pattern") or "")).replace("minecraft:", ""),
                        str(_val(_get(tr, "material") or "")).replace("minecraft:", ""))
        if g("custom_name") is not None:
            row.custom_name = _text(g("custom_name"))
        if g("damage") is not None:
            row.damage = int(_val(g("damage")))
        dc = g("dyed_color")
        if dc is not None:
            row.color = int(_val(_get(dc, "rgb") if hasattr(dc, "keys") else dc))
        row.unbreakable = g("unbreakable") is not None
        known = {"enchantments", "stored_enchantments", "trim", "custom_name", "damage", "dyed_color",
                 "unbreakable", "repair_cost"}
        row.extra = [str(k).replace("minecraft:", "") for k in comp.keys()
                     if str(k).replace("minecraft:", "") not in known]
        return
    tag = _get(item, "tag")                     # eski format
    if tag is None:
        return
    row.enchants = _ench_list(_get(tag, "Enchantments"))
    row.stored = _ench_list(_get(tag, "StoredEnchantments"))
    tr = _get(tag, "Trim")
    if tr is not None:
        row.trim = (str(_val(_get(tr, "pattern") or "")).replace("minecraft:", ""),
                    str(_val(_get(tr, "material") or "")).replace("minecraft:", ""))
    disp = _get(tag, "display")
    if disp is not None:
        if _get(disp, "Name") is not None:
            row.custom_name = _text(_get(disp, "Name"))
        if _get(disp, "color") is not None:
            row.color = int(_val(_get(disp, "color")))
    if _get(tag, "Damage") is not None:
        row.damage = int(_val(_get(tag, "Damage")))
    row.unbreakable = bool(_val(_get(tag, "Unbreakable") or 0))


class PlayerService:
    def __init__(self, server_path):
        self.server_path = server_path
        self.translations = Translations()
        self.name_to_uuid = {}
        self.uuid_to_name = {}
        self.data_files = {}
        self.translations.load(server_path)

    def set_server_path(self, path):
        self.server_path = path
        self.translations.load(path)

    def set_language(self, ui_lang):
        """Eşya adlarını panel diline göre yükler."""
        return self.translations.load(self.server_path, mc_lang_code(ui_lang))

    # --- isim/UUID ---
    def resolve_uuid(self, name):
        if name in self.name_to_uuid:
            return self.name_to_uuid[name]
        if name[:1] in (".", "*", "_"):
            return floodgate_uuid(name.lstrip(".*_"))
        return offline_uuid(name)

    def _load_name_cache(self):
        self.name_to_uuid.clear()
        self.uuid_to_name.clear()

        def add(name, u):
            u = hyphenate(str(u))
            self.name_to_uuid[name] = u
            self.uuid_to_name[u] = name

        cache = os.path.join(self.server_path, "usercache.json")
        if os.path.exists(cache):
            try:
                with open(cache, "r", encoding="utf-8") as f:
                    for e in json.load(f):
                        if e.get("name") and e.get("uuid"):
                            add(e["name"], e["uuid"])
            except Exception as e:
                print(f"usercache okuma hatası: {e}")

        log = os.path.join(self.server_path, "logs", "latest.log")
        if os.path.exists(log):
            uuid_re = re.compile(r"UUID of player ([A-Za-z0-9_.*~-]+) is ([a-f0-9-]+)", re.I)
            join_re = re.compile(r"INFO\]:\s*(?:System chat:\s*)?([A-Za-z0-9_.*~-]+)\s+joined the game", re.I)
            try:
                with open(log, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        m = uuid_re.search(line)
                        if m:
                            add(m.group(1), m.group(2))
                            continue
                        m = join_re.search(line)
                        if m and m.group(1) not in self.name_to_uuid:
                            add(m.group(1), offline_uuid(m.group(1)))
            except Exception as e:
                print(f"Log okuma hatası: {e}")

    def _find_data_files(self):
        found = {}
        for sub in (("world", "playerdata"), ("world", "players", "data"),
                    ("world", "players"), ("playerdata",)):
            d = os.path.join(self.server_path, *sub)
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.endswith(".dat"):
                        found[hyphenate(fn[:-4])] = os.path.join(d, fn)
        return found

    @staticmethod
    def _name_from_dat(path):
        """bukkit.lastKnownName etiketinden isim kurtarır."""
        try:
            with gzip.open(path, "rb") as f:
                data = f.read()
            idx = data.find(b"lastKnownName")
            if idx != -1:
                pos = idx + len(b"lastKnownName")
                n = struct.unpack(">H", data[pos:pos + 2])[0]
                return data[pos + 2:pos + 2 + n].decode("utf-8", errors="ignore")
        except Exception:
            pass
        return None

    def stats_file(self, u):
        for name in (hyphenate(u), u.replace("-", "")):
            for sub in (("world", "stats"), ("world", "players", "stats")):
                p = os.path.join(self.server_path, *sub, f"{name}.json")
                if os.path.exists(p):
                    return p
        return None

    def _is_online(self, u, online_names=None, name=None):
        if online_names is not None and name is not None:
            return name in online_names
        p = self.stats_file(u)
        try:
            return bool(p) and time.time() - os.path.getmtime(p) < 60
        except Exception:
            return False

    def list_players(self, online_names=None):
        """Tüm oyuncular. online_names verilirse (ör. 'list' komutundan)
        çevrimiçi durumu oradan alınır, yoksa stats dosyası tarihinden tahmin edilir."""
        self._load_name_cache()
        self.data_files = self._find_data_files()
        players = []
        for u, path in self.data_files.items():
            name = self.uuid_to_name.get(u) or self._name_from_dat(path) or f"Bilinmeyen ({u[:8]})"
            self.name_to_uuid.setdefault(name, u)
            players.append(Player(name, u, path, self._is_online(u, online_names, name)))
        players.sort(key=lambda p: (not p.online, p.name.lower()))
        return players

    # --- detaylar ---
    def _item(self, item, slot_label=None):
        iid = str(_val(_get(item, "id") or ""))
        c = _get(item, "count", "Count")
        count = int(_val(c)) if c is not None else 1
        if slot_label is not None:
            slot = slot_label
        else:
            sl = _get(item, "Slot")
            slot = str(int(sl)) if sl is not None else "-"
        row = ItemRow(slot, iid.replace("minecraft:", ""), self.translations.item_name(iid), count)
        try:
            parse_item_props(item, row)
        except Exception as e:
            print(f"[eşya] özellik okunamadı: {e}")
        return row

    def details(self, player):
        root = read_nbt(player.data_file)
        if root is None:
            return None
        d = PlayerDetails()
        d.xp_level = int(_val(root.get("XpLevel", 0)))
        d.health = float(_val(root.get("Health", 0)))
        d.food = int(_val(root.get("foodLevel", 0)))
        d.xp_progress = max(0.0, min(1.0, float(_val(root.get("XpP", 0)))))
        d.absorption = float(_val(root.get("AbsorptionAmount", 0)))
        d.gamemode = int(_val(root.get("playerGameType", -1)))

        inv = _get(root, "Inventory") or []
        by_slot = {}
        for i in inv:
            try:
                by_slot[int(_val(_get(i, "Slot") or 0))] = i
            except Exception:
                pass
        d.inventory = [self._item(i) for s, i in sorted(by_slot.items()) if 0 <= s <= 35]

        # Zırh: 1) eski düzen Inventory slot 100-103, 2) 1.21.5+ "equipment",
        #       3) entity düzeni "ArmorItems" [ayak, bacak, göğüs, kafa]
        labels = list(ARMOR_SLOTS.values())
        armor = {label: by_slot[s] for s, label in ARMOR_SLOTS.items() if s in by_slot}
        eq = _get(root, "equipment", "Equipment")
        if eq:
            for key, label in (("head", "Miğfer"), ("chest", "Göğüslük"), ("legs", "Pantolon"), ("feet", "Bot")):
                it = _get(eq, key)
                if it and _get(it, "id"):
                    armor[label] = it
        ai = _get(root, "ArmorItems")
        if ai:
            for it, label in zip(list(ai), ("Bot", "Pantolon", "Göğüslük", "Miğfer")):
                if it and _get(it, "id") and label not in armor:
                    armor[label] = it
        d.armor = [self._item(armor[l], l) if l in armor else ItemRow(l, "", N_("(Boş)"), 0) for l in labels]
        d.armor_points = armor_points(r.item_id for r in d.armor)

        off = None
        if eq and _get(eq, "offhand") and _get(_get(eq, "offhand"), "id"):
            off = _get(eq, "offhand")
        elif OFFHAND_SLOT in by_slot:
            off = by_slot[OFFHAND_SLOT]
        else:
            hi = _get(root, "HandItems")
            if hi and len(hi) > 1 and _get(hi[1], "id"):
                off = hi[1]
        d.offhand = self._item(off, N_("2. El")) if off is not None else None

        ender = _get(root, "EnderItems", "ender_items", "enderItems") or []
        d.ender = [self._item(i) for i in ender if _get(i, "id")]

        try:
            p = [float(_val(v)) for v in list(root.get("Pos", []))]
            dim = _val(root.get("Dimension", "minecraft:overworld"))
            if isinstance(dim, (int, float)):                  # 1.16 öncesi sayısal boyut
                dim = {-1: "minecraft:the_nether", 1: "minecraft:the_end"}.get(int(dim), "minecraft:overworld")
            if len(p) == 3:
                d.pos = (str(dim), *(round(c, 1) for c in p))
        except Exception:
            pass
        ld = root.get("LastDeathLocation")
        if ld:
            pos = list(ld.get("pos", []))
            if len(pos) == 3:
                d.last_death = (str(_val(ld.get("dimension", "minecraft:overworld"))),
                                *[int(p) for p in pos])
        return d

    def stats(self, player):
        """{'play_time_sec', 'deaths', 'jumps', 'mob_kills', 'player_kills', 'walk_cm'} ya da None."""
        p = self.stats_file(player.uuid)
        if not p:
            return None
        with open(p, "r", encoding="utf-8") as f:
            custom = json.load(f).get("stats", {}).get("minecraft:custom", {})
        return {
            "play_time_sec": custom.get("minecraft:play_time", custom.get("minecraft:play_one_minute", 0)) // 20,
            "deaths": custom.get("minecraft:deaths", 0),
            "jumps": custom.get("minecraft:jump", 0),
            "mob_kills": custom.get("minecraft:mob_kills", 0),
            "player_kills": custom.get("minecraft:player_kills", 0),
            "walk_cm": custom.get("minecraft:walk_one_cm", 0),
        }


# --- oyuncu komutları (şablon -> komut) ---
def quote(name):
    return f'"{name}"' if not re.fullmatch(r"[A-Za-z0-9_]+", name) else name


PLAYER_COMMANDS = {
    "heal":        "effect give {p} minecraft:instant_health 1 10",
    "feed":        "effect give {p} minecraft:saturation 1 20",
    "starve":      "effect give {p} minecraft:hunger 30 255",
    "kill":        "kill {p}",
    "random_tp":   "spreadplayers ~ ~ 0 10000 false {p}",
    "spawn":       "execute in minecraft:overworld run tp {p} 0 ~ 0",
}


def build_command(template, player_name, **kw):
    return template.format(p=quote(player_name), **kw)


def give_command(player_name, item_id, amount):
    return f"give {quote(player_name)} minecraft:{item_id} {int(amount)}"


def tp_death_command(player_name, last_death):
    dim, x, y, z = last_death
    return f"execute in {dim} run tp {quote(player_name)} {x} {y} {z}"


def account_type(uuid_str):
    """'premium' (Mojang hesabı, UUID v4), 'offline' (lisanssız / çevrimdışı mod, UUID v3) ya da ''."""
    u = (uuid_str or "").replace("-", "")
    if len(u) != 32:
        return ""
    return {"4": "premium", "3": "offline"}.get(u[12], "")


def tp_to_player_command(player_name, target):
    return f"tp {quote(player_name)} {quote(target)}"


def parse_list_output(line):
    """'There are 2 of a max of 20 players online: a, b' -> {'a','b'} ya da None."""
    m = re.search(r"players online:\s*(.*)$", line)
    if not m:
        return None
    return {n.strip() for n in m.group(1).split(",") if n.strip()}
