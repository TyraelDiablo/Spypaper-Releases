"""Spypaper Modları: Spypaper'ın hazır, tek tıkla kurulan küçük veri ve kaynak paketleri.

kind "data": veri paketi. Paper, Purpur, Spigot, Vanilla, Fabric, Forge ve NeoForge'da aynı çalışır;
  oyuncuların bir şey kurması gerekmez. Kurulum: <sunucu>/<level-name>/datapacks/spypaper_mod_<id>/
kind "resource": kaynak paketi parçası. İçerik editörünün ürettiği spypaper_resourcepack.zip'e eklenir ve
  sunucu kaynak paketi olarak oyunculara gider. Kurulu olanlar sunucu ayarında ("spymods_rp") tutulur.
"""
import json
import os
import shutil

from .config import N_
from .content import _mcmeta, data_format, Fmt

PREFIX = "spypaper_mod_"


def _fn(ns, name, lines):
    """1.21 öncesi "functions", sonrası "function" klasörü: ikisi de yazılır."""
    body = "\n".join(lines) + "\n"
    return {f"data/{ns}/function/{name}.mcfunction": body,
            f"data/{ns}/functions/{name}.mcfunction": body}


def _load_tag(fid):
    data = json.dumps({"values": [fid]}, indent=2)
    return {"data/minecraft/tags/function/load.json": data,
            "data/minecraft/tags/functions/load.json": data}


# ---------------------------------------------------------------- modlar
def _tick_tag(fid):
    data = json.dumps({"values": [fid]}, indent=2)
    return {"data/minecraft/tags/function/tick.json": data,
            "data/minecraft/tags/functions/tick.json": data}


def _keep_items(t):
    ns = "spypaper_items"
    files = {}
    files.update(_load_tag(f"{ns}:load"))
    files.update(_fn(ns, "load", [f"schedule function {ns}:loop 1s replace"]))
    # Age -32768: oyunun kendi "hiç kaybolmaz" değeri. 30 sn'de bir yerdeki tüm eşyalara yazılır
    # (kaybolma 6000 tick = 5 dk'da olduğundan arada kaybolan olmaz).
    files.update(_fn(ns, "loop", [
        "execute as @e[type=minecraft:item] run data modify entity @s Age set value -32768s",
        f"schedule function {ns}:loop 30s replace",
    ]))
    return files


def _death_coords(t):
    ns = "spypaper_death"
    files = {}
    files.update(_load_tag(f"{ns}:load"))
    files.update(_tick_tag(f"{ns}:tick"))
    files.update(_fn(ns, "load", [f"scoreboard objectives add {o} {k}" for o, k in
                                  (("spd_deaths", "deathCount"), ("spd_x", "dummy"), ("spd_y", "dummy"),
                                   ("spd_z", "dummy"))]))
    files.update(_fn(ns, "tick", [f"execute as @a[scores={{spd_deaths=1..}}] run function {ns}:report"]))
    sc = lambda o: {"score": {"name": "@s", "objective": o}, "color": "yellow"}      # noqa: E731
    msg = [{"text": "☠ " + t("Öldüğün yer:") + " ", "color": "red"}, sc("spd_x"), {"text": " ", "color": "gray"},
           sc("spd_y"), {"text": " ", "color": "gray"}, sc("spd_z"), {"text": " (", "color": "gray"},
           {"nbt": "LastDeathLocation.dimension", "entity": "@s", "color": "gray"}, {"text": ")", "color": "gray"}]
    files.update(_fn(ns, "report", [
        "execute store result score @s spd_x run data get entity @s LastDeathLocation.pos[0]",
        "execute store result score @s spd_y run data get entity @s LastDeathLocation.pos[1]",
        "execute store result score @s spd_z run data get entity @s LastDeathLocation.pos[2]",
        "tellraw @s " + json.dumps(msg, ensure_ascii=False),
        "scoreboard players set @s spd_deaths 0",
    ]))
    return files


def _flat_bars():
    from .spymods_rp import flat_bars
    return flat_bars()


MODS = [
    {
        "id": "flat_bars",
        "kind": "resource",
        "name": N_("Düz can ve açlık barı"),
        "desc": N_("Kalpler, açlık, zırh ve hava simgeleri yerine düz, dolan barlar gösterir. Zehir, solma, donma "
                   "ve emilim kalpleri kendi renginde görünür. Kaynak paketi olarak oyunculara gider."),
        "warn": N_("Oyunculara ulaşması için İçerik Editörü'nde kaynak paketi paylaşımı açık olmalı. "
                   "Minecraft 1.21 ve sonrası gerekir."),
        "rp": _flat_bars,
    },
    {
        "id": "death_coords",
        "kind": "data",
        "name": N_("Ölüm koordinatları"),
        "desc": N_("Oyuncu ölünce öldüğü yerin koordinatları ve boyutu yalnızca ona sohbette yazılır."),
        "files": _death_coords,
        "on_remove": ["scoreboard objectives remove spd_deaths", "scoreboard objectives remove spd_x",
                      "scoreboard objectives remove spd_y", "scoreboard objectives remove spd_z"],
    },
    {
        "id": "keep_items",
        "kind": "data",
        "name": N_("Eşyalar kaybolmasın"),
        "desc": N_("Yere düşen eşyalar 5 dakika sonra kaybolmaz; ölünce düşenler de dahil. Tüm sunucu türlerinde "
                   "çalışır, oyuncuların bir şey kurması gerekmez."),
        "warn": N_("Çiftliklerden düşen eşyalar da kalıcı olur ve birikirse sunucuyu yavaşlatabilir. "
                   "Kaldırınca yüklü alandaki eşyalar yeniden 5 dakika sayar."),
        "files": _keep_items,
        "on_remove": ["schedule clear spypaper_items:loop",
                      "execute as @e[type=minecraft:item] run data modify entity @s Age set value 0s"],
    },
]


class SpyModError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def get(mod_id):
    for m in MODS:
        if m["id"] == mod_id:
            return m
    raise SpyModError(N_("Bilinmeyen mod: {id}"), id=mod_id)


def folder(server_path, level, mod_id):
    if not level or os.path.isabs(level) or ".." in level.replace("\\", "/").split("/"):
        raise SpyModError(N_("level-name geçersiz: {name}"), name=level)
    return os.path.join(server_path, level, "datapacks", PREFIX + mod_id)


def installed(server_path, level, mod_id, rp_ids=()):
    if get(mod_id).get("kind") == "resource":
        return mod_id in (rp_ids or ())
    try:
        return os.path.isfile(os.path.join(folder(server_path, level, mod_id), "pack.mcmeta"))
    except SpyModError:
        return False


def rp_files(rp_ids):
    """Kurulu kaynak paketi modlarının dosyaları (arşiv yolu -> bayt)."""
    out = {}
    for mid in rp_ids or ():
        try:
            m = get(mid)
        except SpyModError:
            continue
        if m.get("kind") == "resource":
            out.update(m["rp"]())
    return out


def install(server_path, level, version, mod_id, t=lambda s: s):
    """Veri paketi modunu kurar (kaynak paketi modları rp_files ile içerik paketine eklenir)."""
    m = get(mod_id)
    dp = folder(server_path, level, mod_id)
    if not os.path.isdir(os.path.join(server_path, level)):
        raise SpyModError(N_("Dünya klasörü yok: {name}. Sunucuyu bir kez başlatıp dünyayı oluştur."), name=level)
    tmp = dp + ".tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    fmt = Fmt(version or "99")
    num = data_format(fmt) if fmt.version >= (1, 21) else 15        # 1.20.x: eski biçim ("functions" klasörü)
    files = {"pack.mcmeta": json.dumps(_mcmeta("Spypaper: " + t(m["name"]), num), indent=2,
                                       ensure_ascii=False)}
    files.update(m["files"](t))
    for rel, body in files.items():
        p = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    if os.path.isdir(dp):
        shutil.rmtree(dp)
    os.replace(tmp, dp)
    return dp


def remove(server_path, level, mod_id):
    get(mod_id)
    dp = folder(server_path, level, mod_id)
    if os.path.isdir(dp):
        shutil.rmtree(dp)
