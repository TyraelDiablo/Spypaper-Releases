"""Sıfırdan sunucu oluşturma: klasör, sunucu yazılımı, server.properties ve (kullanıcı kabul ettiyse) eula.txt.

Sunucu yazılımı core.software sağlayıcılarıyla indirilir; Forge/NeoForge kurulum programı çalıştırılır.
"""
import os
import re
from datetime import datetime

from . import software, updater
from .config import N_

GAMEMODES = ("survival", "creative", "adventure")
DIFFICULTIES = ("peaceful", "easy", "normal", "hard")


def java_hint(mc_version):
    """Minecraft sürümü için gereken en düşük Java sürümü (bilgi amaçlı)."""
    nums = [int(x) for x in re.findall(r"\d+", mc_version or "")[:3]] + [0, 0, 0]
    major, minor, patch = nums[:3]
    if major >= 26:
        return 25
    if major == 1 and (minor > 20 or (minor == 20 and patch >= 5)):
        return 21
    if major == 1 and minor >= 18:
        return 17
    if major == 1 and minor == 17:
        return 16
    return 8


def safe_folder_name(name):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().rstrip(".")
    return s or "Sunucu"


def properties_text(motd, port, max_players, gamemode, difficulty, online_mode, whitelist):
    lines = [
        "#Minecraft server properties",
        f"#Spypaper ile oluşturuldu: {datetime.now():%Y-%m-%d %H:%M}",
        f"motd={motd}",
        f"server-port={port}",
        f"max-players={max_players}",
        f"gamemode={gamemode}",
        f"difficulty={difficulty}",
        f"online-mode={'true' if online_mode else 'false'}",
        f"white-list={'true' if whitelist else 'false'}",
        f"enforce-whitelist={'true' if whitelist else 'false'}",
        "view-distance=10",
        "simulation-distance=10",
        "spawn-protection=16",
    ]
    return "\n".join(lines) + "\n"


def create(path, software_key, version, *, motd="A Minecraft Server", port=25565, max_players=20,
           gamemode="survival", difficulty="normal", online_mode=True, whitelist=False,
           accept_eula=False, java="java", contact="", progress=None, log=None):
    """Sunucuyu oluşturur. Başlatılacak dosyanın adını (jar ya da Forge/NeoForge argüman dosyası) döndürür."""
    log = log or (lambda s: None)
    if os.path.isdir(path) and os.listdir(path):
        raise updater.UpdateError(N_("Seçilen klasör boş değil: {path}"), path=path)
    os.makedirs(path, exist_ok=True)
    log(f"{software.SOFTWARE[software_key]['name']} {version}")
    info = software.latest_build(software_key, version, contact)
    if info.get("installer"):
        start = software.install_with_installer(info, path, java, contact, progress=progress, log=log)
    else:
        start = updater.download(info, path, "", contact, progress=progress)
    with open(os.path.join(path, "server.properties"), "w", encoding="utf-8") as f:
        f.write(properties_text(motd, port, max_players, gamemode, difficulty, online_mode, whitelist))
    if accept_eula:
        # kullanıcı pencerede Minecraft EULA'sını açıkça kabul etti
        with open(os.path.join(path, "eula.txt"), "w", encoding="utf-8") as f:
            f.write("#By changing the setting below to TRUE you are indicating your agreement to our EULA "
                    "(https://aka.ms/MinecraftEULA).\n"
                    f"#{datetime.now().strftime('%a %b %d %H:%M:%S %Y')} (Spypaper)\neula=true\n")
    return start
