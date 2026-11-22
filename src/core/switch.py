"""Sunucu yazılımını değiştirirken (ör. Paper → Fabric, Forge → Paper) klasörü yeni yazılıma hazırlar.

- Uyumsuz eklentiler (plugins) ve modlar (mods) silinmez, backups/switch-<tarih>/ içine taşınır.
- Bukkit tabanlılar (Paper/Purpur/Folia) Nether ve End'i ayrı <dünya>_nether / <dünya>_the_end klasörlerinde tutar.
  Vanilla ve mod yükleyicilere geçerken bunlar ana dünyanın içine geri taşınır; tersinde Paper ilk açılışta
  kendisi ayırır. Oyuncu verisi (playerdata, stats, advancements) her iki düzende de ana dünyadadır, korunur.
"""
import os
import shutil
from datetime import datetime

from .config import N_

BUKKIT = {"paper", "purpur", "folia", "spigot", "bukkit"}
MODDED = {"fabric", "forge", "neoforge"}


class SwitchError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def family(key):
    if key == "velocity":
        return "proxy"
    if key in BUKKIT:
        return "bukkit"
    if key in MODDED:
        return key                      # Fabric, Forge, NeoForge modları birbirine uymaz
    return "vanilla"


def _dirs_with_files(p):
    return os.path.isdir(p) and any(f for f in os.listdir(p) if not f.startswith("."))


def _dim_parts(server_path, level):
    """Bukkit'in ayrı boyut klasörlerinde ana dünyaya taşınacak parçalar: [(kaynak, hedef)]."""
    world = os.path.join(server_path, level)
    out = []
    for suffix, dims in (("_nether", ("DIM-1", os.path.join("dimensions", "minecraft", "the_nether"))),
                         ("_the_end", ("DIM1", os.path.join("dimensions", "minecraft", "the_end")))):
        side = os.path.join(server_path, level + suffix)
        for d in dims:
            src = os.path.join(side, d)
            if _dirs_with_files(src):
                out.append((src, os.path.join(world, d)))
    return out


def plan(server_path, level, old_key, new_key):
    """Yapılacakların listesi: [{"kind", "text"(şablon), "kw"}]. Değişiklik yapmaz."""
    old_f, new_f = family(old_key), family(new_key)
    if "proxy" in (old_f, new_f) and old_f != new_f:
        raise SwitchError(N_("Velocity bir proxy'dir; Minecraft sunucusuyla birbirine dönüştürülemez. "
                             "Proxy için ayrı bir sunucu oluştur."))
    steps = []
    if old_f == new_f:
        return steps
    from .software import SOFTWARE
    names = {"old": SOFTWARE.get(old_key, {}).get("name", old_key), "new": SOFTWARE.get(new_key, {}).get("name", new_key)}
    plugins = os.path.join(server_path, "plugins")
    mods = os.path.join(server_path, "mods")
    if new_f != "bukkit" and _dirs_with_files(plugins):
        n = len([f for f in os.listdir(plugins) if f.lower().endswith(".jar")])
        steps.append({"kind": "plugins", "text": N_("{n} eklenti (plugins klasörü) yedeğe taşınacak; {new} eklenti çalıştırmaz."), "kw": dict(names, n=n)})
    if _dirs_with_files(mods) and (new_f not in MODDED or old_f in MODDED):
        n = len([f for f in os.listdir(mods) if f.lower().endswith(".jar")])
        steps.append({"kind": "mods", "text": N_("{n} mod (mods klasörü) yedeğe taşınacak; {old} modları {new} ile çalışmaz."), "kw": dict(names, n=n)})
    if old_f == "bukkit" and new_f != "bukkit":
        parts = _dim_parts(server_path, level)
        if parts:
            steps.append({"kind": "dims", "text": N_("Nether ve End, {level}_nether / {level}_the_end klasörlerinden ana dünyanın içine taşınacak."),
                          "kw": {"level": level}})
    if old_f in MODDED and new_f not in MODDED:
        steps.append({"kind": "note", "text": N_("Dünyadaki mod blokları, eşyaları ve yaratıkları yeni yazılımda kaybolur."), "kw": {}})
    steps.append({"kind": "note", "text": N_("Dünya, oyuncu verileri (envanter, konum, ilerlemeler), whitelist, banlar ve OP'ler korunur."), "kw": {}})
    return steps


def apply(server_path, level, old_key, new_key, log=None):
    """plan()'daki taşımaları yapar. Taşınanların gittiği klasörü döndürür (yoksa "")."""
    steps = plan(server_path, level, old_key, new_key)
    kinds = {s["kind"] for s in steps}
    if not kinds & {"plugins", "mods", "dims"}:
        return ""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(server_path, "backups", f"switch-{old_key}-to-{new_key}-{stamp}")
    os.makedirs(dest, exist_ok=True)
    for kind in ("plugins", "mods"):
        if kind in kinds:
            src = os.path.join(server_path, kind)
            shutil.move(src, os.path.join(dest, kind))
            os.makedirs(src, exist_ok=True)
            if log:
                log(kind)
    if "dims" in kinds:
        for src, target in _dim_parts(server_path, level):
            if os.path.exists(target) and os.listdir(target):
                # ana dünyada zaten bir kopya varsa (eski vanilla kalıntısı) onu yedeğe al, Paper'ınki güncel
                shutil.move(target, os.path.join(dest, "old-" + os.path.relpath(target, server_path).replace(os.sep, "_")))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.move(src, target)
        for suffix in ("_nether", "_the_end"):     # boşalan Bukkit klasörlerini yedeğe al (level.dat, uid.dat vb.)
            side = os.path.join(server_path, level + suffix)
            if os.path.isdir(side):
                shutil.move(side, os.path.join(dest, level + suffix))
        if log:
            log("dims")
    return dest
