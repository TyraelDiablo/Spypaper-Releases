"""Bedrock oyuncu verileri: dünya veritabanından (LevelDB) salt okunur oyuncu bilgisi, izin listesi ve yetkiler.

Eşleme: oyuncunun MsaId'si = UUID3(md5("pocket-auth-1-xuid:" + xuid)). Veritabanında "player_<MsaId>" kaydı
"player_server_<id>" kaydını gösterir; asıl oyuncu verisi oradadır. Adlar log'daki "Player connected: ad, xuid: …"
satırlarından ve allowlist.json'dan öğrenilir ve .spypaper/bedrock_names.json'da saklanır.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid as _uuid

from . import leveldb_ro, nbt_le
from .config import N_

RE_CONNECT = re.compile(r"Player (?:connected|Spawned|disconnected):\s*(.+?),? xuid:\s*(\d+)")
GAMEMODES = {0: N_("Hayatta Kalma"), 1: N_("Yaratıcı"), 2: N_("Macera"), 5: N_("Varsayılan"), 6: N_("İzleyici")}
DIMENSIONS = {0: N_("Overworld"), 1: N_("Nether"), 2: N_("End")}
PERMS = ("visitor", "member", "operator", "custom")
PERM_NAMES = {"visitor": N_("Ziyaretçi"), "member": N_("Üye"), "operator": N_("Operatör"), "custom": N_("Özel")}
PERM_DESC = {
    "visitor": N_("Dünyayı gezer ama blok koyamaz, kıramaz, kapı/sandık kullanamaz, saldıramaz."),
    "member": N_("Blok koyar, kırar, kapı ve sandık kullanır, oyunculara ve yaratıklara saldırır."),
    "operator": N_("Üyenin yaptığı her şey ve ek olarak komut kullanır, ışınlanır, başkalarının yetkisini değiştirir."),
    "custom": N_("Aşağıda seçtiğin yetenekler: ne yapabileceğini tek tek belirlersin."),
}
LEVEL_OF = {0: "visitor", 1: "member", 2: "operator", 3: "custom"}
# Özel yetkide açılıp kapatılabilen yetenekler (oyunun kendi "Özel" ekranındakiler)
ABILITIES = [("build", N_("Blok koyabilir")), ("mine", N_("Blok kırabilir")),
             ("doorsandswitches", N_("Kapı ve şalter kullanabilir")), ("opencontainers", N_("Sandık ve kutu açabilir")),
             ("attackplayers", N_("Oyunculara saldırabilir")), ("attackmobs", N_("Yaratıklara saldırabilir")),
             ("op", N_("Operatör komutlarını kullanabilir")), ("teleport", N_("Işınlanabilir"))]
PRESETS = {"visitor": dict.fromkeys([k for k, _ in ABILITIES], 0),
           "member": {**dict.fromkeys([k for k, _ in ABILITIES], 1), "op": 0, "teleport": 0},
           "operator": dict.fromkeys([k for k, _ in ABILITIES], 1)}


def msa_id(xuid):
    h = bytearray(hashlib.md5(f"pocket-auth-1-xuid:{xuid}".encode()).digest())
    h[6] = h[6] & 0x0F | 0x30
    h[8] = h[8] & 0x3F | 0x80
    return str(_uuid.UUID(bytes=bytes(h)))


def _json(path, default):
    """BDS boş listeyi 'null' olarak yazar: türü uymayan içerik varsayılana döner."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------ adlar
def _names_file(server_path):
    return os.path.join(server_path, ".spypaper", "bedrock_names.json")


def remember(server_path, name, xuid):
    names = _json(_names_file(server_path), {})
    if names.get(xuid) != name:
        names[xuid] = name
        _write_json(_names_file(server_path), names)


def names(server_path):
    """{xuid: ad}"""
    out = dict(_json(_names_file(server_path), {}))
    for e in _json(os.path.join(server_path, "allowlist.json"), []):
        if isinstance(e, dict) and e.get("xuid") and e.get("name"):
            out.setdefault(str(e["xuid"]), e["name"])
    try:
        with open(os.path.join(server_path, "logs", "latest.log"), encoding="utf-8", errors="replace") as f:
            for ln in f:
                m = RE_CONNECT.search(ln)
                if m:
                    out[m.group(2)] = m.group(1).strip()
    except OSError:
        pass
    return out


def on_line(server_path, line):
    """Sunucu satır kancası: bağlanan oyuncunun adını kalıcı olarak hatırlar."""
    m = RE_CONNECT.search(line)
    if m:
        try:
            remember(server_path, m.group(1).strip(), m.group(2))
        except OSError:
            pass


# ------------------------------------------------------------------ izin listesi ve yetkiler
def allowlist(server_path):
    return [e for e in _json(os.path.join(server_path, "allowlist.json"), []) if isinstance(e, dict)]


def permissions(server_path):
    """{xuid: seviye}"""
    return {str(e["xuid"]): e.get("permission", "member")
            for e in _json(os.path.join(server_path, "permissions.json"), []) if isinstance(e, dict) and e.get("xuid")}


def set_permission(server_path, xuid, level):
    """permissions.json'a yazar; 'member' varsayılandır ve listeden çıkarılır."""
    items = [e for e in _json(os.path.join(server_path, "permissions.json"), [])
             if isinstance(e, dict) and str(e.get("xuid")) != str(xuid)]
    if level in ("operator", "visitor", "custom"):     # BDS Özel yetkiyi de "custom" olarak burada tutar
        items.append({"permission": level, "xuid": str(xuid)})
    _write_json(os.path.join(server_path, "permissions.json"), items)


def set_allowed(server_path, name, xuid, on):
    items = [e for e in allowlist(server_path)
             if not ((xuid and str(e.get("xuid")) == str(xuid)) or (e.get("name", "").lower() == name.lower()))]
    if on:
        e = {"ignoresPlayerLimit": False, "name": name}
        if xuid:
            e["xuid"] = str(xuid)
        items.append(e)
    _write_json(os.path.join(server_path, "allowlist.json"), items)


# ------------------------------------------------------------------ oyuncu verisi
def _db_copy(server_path, server=None):
    """Veritabanının anlık kopyası. Sunucu çalışıyorsa yazmayı kısa süre durdurur (save hold / save resume)."""
    from .bedrock import level_name
    src = os.path.join(server_path, "worlds", level_name(server_path), "db")
    if not os.path.isdir(src):
        return None
    held = False
    if server is not None and getattr(server, "is_running", False):
        held = bool(server.try_send("save hold"))
        if held:
            time.sleep(2)
    dst = tempfile.mkdtemp(prefix="spypaper-bedb-")
    try:
        for n in os.listdir(src):
            p = os.path.join(src, n)
            if os.path.isfile(p) and n != "LOCK":
                shutil.copy2(p, os.path.join(dst, n))
    finally:
        if held:
            server.try_send("save resume")
    return dst


def _item(it):
    if not isinstance(it, dict) or not it.get("Name") or not it.get("Count"):
        return None
    name = str(it["Name"]).replace("minecraft:", "")
    out = {"id": name, "count": int(it.get("Count", 0)), "slot": int(it.get("Slot", -1)),
           "damage": int(it.get("Damage", 0) or 0)}
    tag = it.get("tag") or {}
    if isinstance(tag, dict):
        disp = tag.get("display") or {}
        if isinstance(disp, dict) and disp.get("Name"):
            out["custom"] = str(disp["Name"])
        if tag.get("ench"):
            out["ench"] = len(tag["ench"])
    return out


def _attr(attrs, key):
    for a in attrs or []:
        if isinstance(a, dict) and a.get("Name") == key:
            return a.get("Current", a.get("Base"))
    return None


def parse_player(nbt):
    attrs = nbt.get("Attributes") or []
    pos = nbt.get("Pos") or [0, 0, 0]
    return {
        "pos": [round(float(x), 1) for x in pos[:3]],
        "dim": int(nbt.get("DimensionId", 0)),
        "gamemode": int(nbt.get("PlayerGameMode", 5)),
        "level": int(nbt.get("PlayerLevel", 0)),
        "progress": float(nbt.get("PlayerLevelProgress", 0.0) or 0.0),
        "absorption": _attr(attrs, "minecraft:absorption") or 0.0,
        "health": _attr(attrs, "minecraft:health"),
        "hunger": _attr(attrs, "minecraft:player.hunger"),
        "inventory": [x for x in map(_item, nbt.get("Inventory") or []) if x],
        "armor": [x for x in map(_item, nbt.get("Armor") or []) if x],
        "offhand": [x for x in map(_item, nbt.get("Offhand") or []) if x],
        "ender": [x for x in map(_item, nbt.get("EnderChestInventory") or []) if x],
        "world_perm": LEVEL_OF.get(int(nbt.get("playerPermissionsLevel", 1)), "member"),
        "abilities": {k: int((nbt.get("abilities") or {}).get(k, 0)) for k, _ in ABILITIES},
    }


def load(server_path, server=None):
    """Oyuncu listesi: veritabanındakiler + izin listesinde olup hiç girmemiş olanlar."""
    nm = names(server_path)
    by_msa = {msa_id(x): x for x in set(nm) | {str(e.get("xuid")) for e in allowlist(server_path) if e.get("xuid")}}
    perms = permissions(server_path)
    allowed_x = {str(e.get("xuid")) for e in allowlist(server_path) if e.get("xuid")}
    allowed_n = {e.get("name", "").lower() for e in allowlist(server_path)}
    out, seen = [], set()
    tmp = _db_copy(server_path, server)
    try:
        db = leveldb_ro.read_db(tmp, lambda k: k.startswith(b"player_")) if tmp else {}
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    for k, v in db.items():
        if k.startswith(b"player_server_"):
            continue
        try:
            ref = nbt_le.loads(v)[1]
        except nbt_le.NBTError:
            continue
        msa = ref.get("MsaId") or k[len(b"player_"):].decode("ascii", "replace")
        xuid = by_msa.get(msa, "")
        data = db.get(str(ref.get("ServerId", "")).encode())
        try:
            info = parse_player(nbt_le.loads(data)[1]) if data else {}
        except nbt_le.NBTError:
            info = {}
        name = nm.get(xuid) or msa[:8]
        perm = perms.get(xuid) or info.get("world_perm") or "member"
        out.append(dict(info, name=name, xuid=xuid, known=bool(xuid), has_data=bool(info), server_id=ref.get("ServerId"),
                        perm=perm,
                        allowed=bool(xuid and xuid in allowed_x) or name.lower() in allowed_n))
        seen.add(xuid)
    for e in allowlist(server_path):                 # izin listesinde olup hiç girmemiş olanlar
        x = str(e.get("xuid") or "")
        if x and x in seen or not e.get("name"):
            continue
        out.append({"name": e["name"], "xuid": x, "known": True, "has_data": False, "perm": perms.get(x, "member"),
                    "allowed": True})
    out.sort(key=lambda p: p["name"].lower())
    return out


def write_permission(server_path, xuid, level, abilities=None):
    """Oyuncunun dünyadaki yetkisini yazar (Özel dahil). Sunucu KAPALI olmalı.
    level: visitor|member|operator|custom; abilities: {ad: 0/1} (custom için)."""
    from . import leveldb_write
    from .bedrock import level_name
    dbdir = os.path.join(server_path, "worlds", level_name(server_path), "db")
    db = leveldb_ro.read_db(dbdir, lambda k: k.startswith(b"player_"))
    ref = db.get(f"player_{msa_id(xuid)}".encode())
    if not ref:
        raise ValueError("no-data")
    sid = str(nbt_le.loads(ref)[1].get("ServerId", "")).encode()
    data = db.get(sid)
    if not data:
        raise ValueError("no-data")
    lv = {v: k for k, v in LEVEL_OF.items()}[level]
    ab = dict(PRESETS.get(level) or {}, **(abilities or {}))
    changes = {("playerPermissionsLevel",): lv, ("permissionsLevel",): 1 if level == "operator" else 0}
    changes.update({("abilities", k): int(bool(v)) for k, v in ab.items()})
    where = nbt_le.locate(data)
    changes = {p: v for p, v in changes.items() if p in where}
    leveldb_write.put(dbdir, sid, nbt_le.patch(data, changes))
    # BDS girişte permissions.json'a bakar; "custom" yazılıysa dünyadaki yeteneklere dokunmaz
    set_permission(server_path, xuid, level)


# ------------------------------------------------------------------ ilk girişte verilecek Özel yetki
def _pending_path(server_path):
    return os.path.join(server_path, ".spypaper", "pending_perms.json")


def pending(server_path):
    """{xuid: {ad: 0/1}} — verisi henüz olmayan oyunculara bekleyen Özel yetkiler."""
    d = _json(_pending_path(server_path), {})
    return d if isinstance(d, dict) else {}


def set_pending(server_path, xuid, abilities):
    d = pending(server_path)
    if abilities is None:
        d.pop(str(xuid), None)
    else:
        d[str(xuid)] = {k: int(bool(v)) for k, v in abilities.items()}
    os.makedirs(os.path.dirname(_pending_path(server_path)), exist_ok=True)
    _write_json(_pending_path(server_path), d)
    if abilities is not None:
        set_permission(server_path, xuid, "custom")


def apply_pending(server_path):
    """Sunucu başlamadan hemen önce (kapalıyken) çağrılır: verisi oluşmuş oyunculara bekleyen yetkiyi yazar."""
    from .bedrock import is_bedrock
    if not is_bedrock(server_path):
        return
    d = pending(server_path)
    for xuid, ab in list(d.items()):
        try:
            write_permission(server_path, xuid, "custom", ab)
            d.pop(xuid)
        except ValueError:          # oyuncu henüz girmedi
            pass
    if d != pending(server_path):
        _write_json(_pending_path(server_path), d)
