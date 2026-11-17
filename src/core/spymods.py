"""Spypaper Modları: Spypaper'ın hazır, tek tıkla kurulan küçük veri paketleri.

Veri paketi olduğu için Paper, Purpur, Spigot, Vanilla, Fabric, Forge ve NeoForge'da aynı çalışır;
oyuncuların bir şey kurması gerekmez. Kurulum: <sunucu>/<level-name>/datapacks/<klasör>/
Her modun klasör adı "spypaper_mod_" ile başlar; Spypaper yalnızca bunlara dokunur.
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
def _keep_items():
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


MODS = [
    {
        "id": "keep_items",
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


def installed(server_path, level, mod_id):
    try:
        return os.path.isfile(os.path.join(folder(server_path, level, mod_id), "pack.mcmeta"))
    except SpyModError:
        return False


def install(server_path, level, version, mod_id):
    m = get(mod_id)
    dp = folder(server_path, level, mod_id)
    if not os.path.isdir(os.path.join(server_path, level)):
        raise SpyModError(N_("Dünya klasörü yok: {name}. Sunucuyu bir kez başlatıp dünyayı oluştur."), name=level)
    tmp = dp + ".tmp"
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    fmt = Fmt(version or "99")
    num = data_format(fmt) if fmt.version >= (1, 21) else 15        # 1.20.x: eski biçim ("functions" klasörü)
    files = {"pack.mcmeta": json.dumps(_mcmeta("Spypaper: " + m["name"], num), indent=2,
                                       ensure_ascii=False)}
    files.update(m["files"]())
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
