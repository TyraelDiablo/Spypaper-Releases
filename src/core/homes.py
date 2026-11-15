"""Evler: her oyuncu için en fazla 10 kayıtlı konum (yalnızca panelden). Sunucu profilinde saklanır:
   "homes": {"<uuid>": [{"name", "dim", "x", "y", "z"}]}
"""
import re

from .config import N_
from .players import quote

MAX_HOMES = 10
DIMENSIONS = {"minecraft:overworld": N_("Overworld"), "minecraft:the_nether": N_("Nether"),
              "minecraft:the_end": N_("End")}
_DIM_RE = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


class HomeError(ValueError):
    pass


def homes(profile, uuid):
    return list((profile.get("homes") or {}).get(uuid, []))


def _save(profile, uuid, items):
    allh = dict(profile.get("homes") or {})
    if items:
        allh[uuid] = items
    else:
        allh.pop(uuid, None)
    profile.set("homes", allh)


def add(profile, uuid, name, dim, x, y, z):
    name = (name or "").strip()[:32]
    if not name:
        raise HomeError(N_("Evin adını yaz."))
    if not _DIM_RE.match(dim or ""):
        raise HomeError(N_("Geçersiz boyut."))
    try:
        x, y, z = (round(float(v), 1) for v in (x, y, z))
    except (TypeError, ValueError):
        raise HomeError(N_("Koordinatlar sayı olmalı."))
    if not all(-30_000_000 <= v <= 30_000_000 for v in (x, z)) or not -2048 <= y <= 2048:
        raise HomeError(N_("Koordinatlar dünya sınırının dışında."))
    items = homes(profile, uuid)
    items = [h for h in items if h["name"].lower() != name.lower()]   # aynı ad: üzerine yaz
    if len(items) >= MAX_HOMES:
        raise HomeError(N_("Bir oyuncu en fazla {n} ev ekleyebilir."))
    items.append({"name": name, "dim": dim, "x": x, "y": y, "z": z})
    _save(profile, uuid, items)


def remove(profile, uuid, name):
    _save(profile, uuid, [h for h in homes(profile, uuid) if h["name"] != name])


def fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


def tp_command(player_name, home):
    return f"execute in {home['dim']} run tp {quote(player_name)} {fmt(home['x'])} {fmt(home['y'])} {fmt(home['z'])}"
