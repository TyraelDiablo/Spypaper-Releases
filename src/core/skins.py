"""Oyuncu kafaları: Mojang'dan skin indirip yüz (8x8 + şapka katmanı) çıkarır, diske önbellekler.

  Lisanslı hesap (UUID v4): sessionserver.mojang.com/session/minecraft/profile/<uuid>
  Lisanssız (UUID v3):      önce api.mojang.com'dan aynı adlı Mojang hesabı aranır; yoksa kafa yok.
  Skin dosyası:             textures.minecraft.net (Mojang)
Önbellek: <Spypaper>/cache/skins/<uuid>.png (ham skin), 1 gün geçerli. Bulunamayanlar da 1 gün
hatırlanır ki her açılışta Mojang'a tekrar sorulmasın.
"""
import base64
import json
import os
import re
import time
import urllib.request

from .config import get_base_dir

TTL = 86400
UA = {"User-Agent": "Spypaper"}
_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")


def cache_dir():
    d = os.path.join(get_base_dir(), "cache", "skins")
    os.makedirs(d, exist_ok=True)
    return d


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status == 204:
            return b""
        return r.read(2_000_000)


def _skin_url_for(uuid_nodash):
    raw = _get(f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid_nodash}")
    if not raw:
        return None
    for prop in json.loads(raw).get("properties", []):
        if prop.get("name") == "textures":
            tex = json.loads(base64.b64decode(prop["value"]))
            url = tex.get("textures", {}).get("SKIN", {}).get("url", "")
            if url.startswith("http://textures.minecraft.net/") or url.startswith("https://textures.minecraft.net/"):
                return "https://" + url.split("://", 1)[1]
    return None


def _uuid_for_name(name):
    if not _NAME_RE.match(name or ""):
        return None
    raw = _get(f"https://api.mojang.com/users/profiles/minecraft/{name}")
    return json.loads(raw).get("id") if raw else None


def skin_file(uuid_str, name, account):
    """Ham skin PNG'sinin yolu ya da None. Ağ isteği yapabilir: arka planda çağır."""
    u = (uuid_str or "").replace("-", "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", u):
        return None
    path = os.path.join(cache_dir(), u + ".png")
    miss = path + ".none"
    for p in (path, miss):
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < TTL:
            return path if p == path else None
    try:
        mojang = u if account == "premium" else _uuid_for_name(name)
        url = _skin_url_for(mojang) if mojang else None
        data = _get(url) if url else b""
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("no skin")
        with open(path, "wb") as f:
            f.write(data)
        if os.path.exists(miss):
            os.remove(miss)
        return path
    except Exception:
        if os.path.exists(path):                        # ağ yoksa eski önbellek de olur
            return path
        try:
            open(miss, "w").close()
        except OSError:
            pass
        return None


def cached(uuid_str):
    """Ağa çıkmadan, önbellekte varsa skin yolu."""
    u = (uuid_str or "").replace("-", "").lower()
    p = os.path.join(cache_dir(), u + ".png") if len(u) == 32 else ""
    return p if p and os.path.exists(p) else None
