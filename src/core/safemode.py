"""Güvenli mod: kullanıcının (ve Esplora'nın) gönderdiği komutları seviyeye göre denetler.

Seviyeler:
  0 Kapalı   — her komut çalışır
  1 Düşük    — tehlikeli komutlar onay ister
  2 Orta     — tehlikeli komutlar engellenir, diğerleri onay ister
  3 Yüksek   — salt okunur: hiçbir komut gönderilemez, eklenti/ayar değiştirilemez

Panelin kendi iç komutları (save-all, list, bakım) bu denetime girmez.
"""
import hashlib
import hmac
import os
import re

from .config import N_

LEVELS = [N_("Devre dışı"), N_("Düşük"), N_("Orta"), N_("Yüksek")]
LEVEL_INFO = [
    N_("Tüm komutlar serbest."),
    N_("Tehlikeli komutlar onay ister."),
    N_("Tehlikeli komutlar engellenir, diğer komutlar onay ister."),
    N_("Salt okunur: komut gönderilemez, eklenti ve ayarlar değiştirilemez."),
]

# Sunucuyu, dünyayı veya yetkileri kalıcı etkileyen komutlar
DANGEROUS = {
    "stop", "restart", "reload", "rl", "op", "deop", "ban", "ban-ip", "pardon", "pardon-ip",
    "whitelist", "kill", "clear", "fill", "clone", "setblock", "worldborder", "difficulty",
    "gamerule", "save-off", "forceload", "kick", "execute", "function", "data", "attribute",
    "datapack", "jfr", "debug", "perf", "plugins", "pl", "lp", "luckperms", "wipe", "minecraft:stop",
}
MASS_SELECTOR = re.compile(r"@[ae]\b")


def command_root(cmd):
    c = cmd.strip().lstrip("/").split()
    return c[0].lower().removeprefix("minecraft:") if c else ""


def is_dangerous(cmd):
    root = command_root(cmd)
    if root in DANGEROUS:
        return True
    # @a / @e ile toplu kill/tp/give/effect gibi işlemler
    return bool(MASS_SELECTOR.search(cmd)) and root in {"tp", "teleport", "give", "effect", "gamemode", "xp", "experience", "enchant"}


def check(level, cmd):
    """'allow' | 'confirm' | 'block' (+ neden)."""
    level = int(level or 0)
    if level <= 0:
        return "allow", ""
    if level >= 3:
        return "block", N_("Güvenli mod (Yüksek): komut gönderilemez.")
    if is_dangerous(cmd):
        return ("confirm", N_("Bu komut tehlikeli olarak işaretli.")) if level == 1 else \
               ("block", N_("Güvenli mod (Orta): tehlikeli komutlar engellendi."))
    return ("confirm", "") if level == 2 else ("allow", "")


# ------------------------------------------------------------------ PIN
def hash_pin(pin, salt=None):
    salt = salt or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 200_000)
    return salt.hex() + "$" + h.hex()


def verify_pin(pin, stored):
    try:
        salt_hex, h_hex = stored.split("$", 1)
        calc = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(calc.hex(), h_hex)
    except Exception:
        return False
