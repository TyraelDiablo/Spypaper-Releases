"""Takımlar (/team): <dünya>/data/scoreboard.dat'tan okur, değişiklikleri komutla yapar.

Takımlar sunucu açıkken komutla değişir; Minecraft scoreboard.dat'ı dünya kaydedilince yazar
(panel her değişiklikten sonra save-all gönderir). Sunucu kapalıyken takımlar yalnızca görüntülenir.
Eski sürümler PascalCase (Teams, Players, TeamColor…), yeniler snake_case anahtarlar kullanabilir;
ikisi de okunur.
"""
import glob
import json
import os
import re

from .config import N_
from .players import read_nbt

COLORS = ["white", "gray", "dark_gray", "black", "red", "dark_red", "gold", "yellow", "green", "dark_green",
          "aqua", "dark_aqua", "blue", "dark_blue", "light_purple", "dark_purple"]
COLOR_HEX = {"white": "#FFFFFF", "gray": "#AAAAAA", "dark_gray": "#555555", "black": "#000000", "red": "#FF5555",
             "dark_red": "#AA0000", "gold": "#FFAA00", "yellow": "#FFFF55", "green": "#55FF55",
             "dark_green": "#00AA00", "aqua": "#55FFFF", "dark_aqua": "#00AAAA", "blue": "#5555FF",
             "dark_blue": "#0000AA", "light_purple": "#FF55FF", "dark_purple": "#AA00AA", "reset": ""}
COLOR_NAMES = {
    "white": N_("Beyaz"), "gray": N_("Gri"), "dark_gray": N_("Koyu gri"), "black": N_("Siyah"),
    "red": N_("Kırmızı"), "dark_red": N_("Koyu kırmızı"), "gold": N_("Altın"), "yellow": N_("Sarı"),
    "green": N_("Yeşil"), "dark_green": N_("Koyu yeşil"), "aqua": N_("Turkuaz"), "dark_aqua": N_("Koyu turkuaz"),
    "blue": N_("Mavi"), "dark_blue": N_("Koyu mavi"), "light_purple": N_("Pembe"), "dark_purple": N_("Mor"),
    "reset": N_("Renksiz"),
}
VISIBILITY = ["always", "never", "hideForOtherTeams", "hideForOwnTeam"]
VISIBILITY_NAMES = {"always": N_("Herkese"), "never": N_("Hiç kimseye"),
                    "hideForOtherTeams": N_("Yalnızca takım arkadaşlarına"),
                    "hideForOwnTeam": N_("Yalnızca diğer takımlara")}
COLLISION = ["always", "never", "pushOtherTeams", "pushOwnTeam"]
COLLISION_NAMES = {"always": N_("Herkesle"), "never": N_("Hiç kimseyle"),
                   "pushOtherTeams": N_("Yalnızca diğer takımlarla"), "pushOwnTeam": N_("Yalnızca kendi takımıyla")}

TEAM_RE = re.compile(r"^[A-Za-z0-9_.+-]{1,32}$")
PLAYER_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def _get(c, *keys, default=None):
    if c is None:
        return default
    for k in keys:
        if k in c:
            return c[k]
    return default


def _text(v):
    """Metin bileşeni (JSON metni ya da NBT compound) -> düz metin."""
    if v is None:
        return ""
    if isinstance(v, str):
        s = str(v)
        try:
            v = json.loads(s)
        except ValueError:
            return s
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        out = str(v.get("text", "") or v.get("translate", ""))
        for e in v.get("extra", []) or []:
            out += _text(e)
        return out
    if isinstance(v, list):
        return "".join(_text(x) for x in v)
    return str(v)


def scoreboard_file(server_path, level="world"):
    for p in (os.path.join(server_path, level, "data", "scoreboard.dat"),
              os.path.join(server_path, level, "data", "minecraft", "scoreboard.dat")):
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(server_path, level, "data", "**", "scoreboard.dat"), recursive=True)
    return hits[0] if hits else None


def read_teams(server_path, level="world"):
    """[{'name','display','color','prefix','suffix','friendly_fire','see_invisible','nametag','death','collision','players'}]"""
    path = scoreboard_file(server_path, level)
    root = read_nbt(path) if path else None
    if root is None:
        return []
    data = _get(root, "data", default=root)
    out = []
    for t in _get(data, "Teams", "teams", default=[]) or []:
        name = str(_get(t, "Name", "name", default=""))
        if not name:
            continue
        out.append({
            "name": name,
            "display": _text(_get(t, "DisplayName", "display_name")) or name,
            "color": str(_get(t, "TeamColor", "color", default="reset") or "reset"),
            "prefix": _text(_get(t, "MemberNamePrefix", "member_name_prefix")),
            "suffix": _text(_get(t, "MemberNameSuffix", "member_name_suffix")),
            "friendly_fire": bool(int(_get(t, "AllowFriendlyFire", "allow_friendly_fire", default=1))),
            "see_invisible": bool(int(_get(t, "SeeFriendlyInvisibles", "see_friendly_invisibles", default=1))),
            "nametag": str(_get(t, "NameTagVisibility", "name_tag_visibility", default="always")),
            "death": str(_get(t, "DeathMessageVisibility", "death_message_visibility", default="always")),
            "collision": str(_get(t, "CollisionRule", "collision_rule", default="always")),
            "players": sorted((str(p) for p in _get(t, "Players", "players", default=[]) or []), key=str.lower),
        })
    return sorted(out, key=lambda x: x["name"].lower())


def _q(text):
    """Metin bileşeni olarak güvenli tırnaklı metin (JSON ve SNBT'de geçerli)."""
    return json.dumps(str(text), ensure_ascii=False)


def check_team(name):
    if not TEAM_RE.match(name or ""):
        raise ValueError(N_("Takım adı yalnızca harf, rakam ve _ . + - içerebilir (en fazla 32 karakter)."))


def check_player(name):
    if not PLAYER_RE.match(name or ""):
        raise ValueError(N_("Geçersiz oyuncu adı: {name}"))


def cmd_add(name, display=""):
    check_team(name)
    return f"team add {name} {_q(display)}" if display else f"team add {name}"


def cmd_remove(name):
    check_team(name)
    return f"team remove {name}"


def cmd_join(team, player):
    check_team(team)
    check_player(player)
    return f"team join {team} {player}"


def cmd_leave(player):
    check_player(player)
    return f"team leave {player}"


def cmd_empty(team):
    check_team(team)
    return f"team empty {team}"


def cmd_modify(team, before, after):
    """İki ayar sözlüğü arasındaki farkı team modify komutlarına çevirir."""
    check_team(team)
    out = []
    if after["display"] != before.get("display"):
        out.append(f"team modify {team} displayName {_q(after['display'] or team)}")
    if after["color"] != before.get("color"):
        if after["color"] not in COLORS + ["reset"]:
            raise ValueError("color")
        out.append(f"team modify {team} color {after['color']}")
    for key, opt in (("prefix", "prefix"), ("suffix", "suffix")):
        if after[key] != before.get(key):
            out.append(f"team modify {team} {opt} {_q(after[key])}")
    for key, opt in (("friendly_fire", "friendlyFire"), ("see_invisible", "seeFriendlyInvisibles")):
        if after[key] != before.get(key):
            out.append(f"team modify {team} {opt} {'true' if after[key] else 'false'}")
    for key, opt, allowed in (("nametag", "nametagVisibility", VISIBILITY), ("death", "deathMessageVisibility", VISIBILITY),
                              ("collision", "collisionRule", COLLISION)):
        if after[key] != before.get(key):
            if after[key] not in allowed:
                raise ValueError(key)
            out.append(f"team modify {team} {opt} {after[key]}")
    return out
