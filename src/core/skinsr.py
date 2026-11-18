"""Oyuncu skin'i: SkinsRestorer eklentisi/modu üzerinden (yalnızca o sunucuda geçerli).

Spypaper skin'i kendisi giydirmez; konsola SkinsRestorer komutu gönderir:
  skin set <oyuncu_adı|bağlantı> <oyuncu> [classic|slim]     skin clear <oyuncu>
SkinsRestorer Paper, Purpur, Spigot, Folia, Fabric ve NeoForge'da çalışır (Forge ve Vanilla'da yok).
Spypaper'daki oyuncu kafaları için seçilen skin sunucu ayarında ("skin_overrides": {uuid: girdi}) tutulur.
"""
import os
import re

from .config import N_

SLUG = "skinsrestorer"
HINT = "skinsrestorer"
SUPPORTED = {"paper", "purpur", "spigot", "bukkit", "folia", "fabric", "neoforge"}
VARIANTS = ("classic", "slim")
NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
URL_RE = re.compile(r"^https?://[^\s\"']{4,500}$", re.I)


class SkinError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def supported(software):
    return (software or "").lower() in SUPPORTED


def plugin_file(folder):
    """(dosya_adı, etkin_mi) ya da None."""
    if not folder or not os.path.isdir(folder):
        return None
    for n in sorted(os.listdir(folder)):
        low = n.lower()
        if HINT in low and (low.endswith(".jar") or low.endswith(".jar.disabled")):
            return n, low.endswith(".jar")
    return None


def parse(text):
    """('name', ad) | ('url', bağlantı). Geçersizse SkinError."""
    s = (text or "").strip()
    if NAME_RE.match(s):
        return "name", s
    if URL_RE.match(s):
        return "url", s
    raise SkinError(N_("Bir oyuncu adı (ör. Notch) ya da http(s) ile başlayan bir skin bağlantısı yaz."))


def set_command(player, text, variant=""):
    if not NAME_RE.match(player or ""):
        raise SkinError(N_("Geçersiz oyuncu adı: {name}"), name=player)
    kind, value = parse(text)
    cmd = f"skin set {value} {player}"
    if kind == "url" and variant in VARIANTS:
        cmd += " " + variant
    return cmd


def clear_command(player):
    if not NAME_RE.match(player or ""):
        raise SkinError(N_("Geçersiz oyuncu adı: {name}"), name=player)
    return f"skin clear {player}"


def install(folder, loaders, game_version, progress=None):
    """SkinsRestorer'ı ve gerekli bağımlılıklarını Modrinth'ten kurar; kurulan dosya adları."""
    from . import modrinth as M
    vs = M.versions(SLUG, loaders, game_version)
    if not vs:
        raise SkinError(N_("Bu sunucu için uyumlu bir SkinsRestorer sürümü bulunamadı ({v})."), v=game_version or "?")
    os.makedirs(folder, exist_ok=True)
    v = vs[0]
    done = [M.download(v["file"], folder, progress)]
    have = M.installed_names(folder)
    for d in v["deps"]:
        pid = d.get("project_id")
        if not pid:
            continue
        dv = M.versions(pid, loaders, game_version)
        if dv and M.safe_filename(dv[0]["file"]["name"]).lower() not in have:
            done.append(M.download(dv[0]["file"], folder, progress))
    return [os.path.basename(x) for x in done]


def norm_uuid(u):
    return (u or "").replace("-", "").lower()
