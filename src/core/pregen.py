"""Dünya ön yükleme: Chunky eklentisi/modu ile bölgeleri önceden oluşturur.

Spypaper Chunky'yi Modrinth'ten kurar (Paper/Purpur/Folia/Spigot, Fabric, Forge, NeoForge) ve komutlarını gönderir.
İlerleme konsoldaki Chunky satırlarından okunur. 'Oyuncu girince duraklat' açıksa sunucuda oyuncu varken iş durur,
sunucu boşalınca devam eder (ana penceredeki zamanlayıcı yürütür).
"""
import os
import re

from .config import N_

SLUG = "chunky"
RE_PROGRESS = re.compile(r"\[Chunky\] Task running for (\S+)\. Processed: (\d+) chunks \(([\d.,]+)%\), ETA: ([\d:]+), "
                         r"Rate: ([\d.,]+) cps", re.I)
RE_DONE = re.compile(r"\[Chunky\] Task finished for (\S+)", re.I)
RE_STOP = re.compile(r"\[Chunky\] Task (paused|stopped|cancelled|canceled) for (\S+)", re.I)
BUKKIT = {"Paper", "Purpur", "Folia", "Spigot", "CraftBukkit", "Bukkit", "Pufferfish"}


class PregenError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def world_names(software, level):
    """Chunky'nin beklediği dünya adları: Bukkit'te klasör adı, diğerlerinde boyut kimliği."""
    if software in BUKKIT:
        return {"overworld": level, "nether": level + "_nether", "end": level + "_the_end"}
    return {"overworld": "minecraft:overworld", "nether": "minecraft:the_nether", "end": "minecraft:the_end"}


def installed(folder):
    try:
        return any(f.lower().startswith("chunky") and f.lower().endswith(".jar") for f in os.listdir(folder))
    except OSError:
        return False


def install(folder, software, mc_version, modded):
    from . import modrinth as M
    _kind, loaders = M.context(software, mc_version, modded)
    vers = M.versions(SLUG, loaders, mc_version) or M.versions(SLUG, loaders)
    if not vers:
        raise PregenError(N_("Bu sunucu için uygun Chunky sürümü bulunamadı ({soft} {mc})."), soft=software, mc=mc_version)
    return M.download(vers[0]["file"], folder)


def start_commands(world, cx, cz, radius):
    return [f"chunky world {world}", "chunky shape square", f"chunky center {int(cx)} {int(cz)}",
            f"chunky radius {int(radius)}", "chunky start"]


class Pregen:
    """Bir sunucunun ön yükleme durumu (konsol satırlarından)."""

    def __init__(self, server, online=None):
        self.server, self.online = server, online
        self.state = "idle"            # idle | running | paused | done
        self.percent = 0.0
        self.eta = ""
        self.rate = 0.0
        self.world = ""
        self.auto_pause = True
        self._paused_by_us = False

    def feed(self, line):
        m = RE_PROGRESS.search(line)
        if m:
            self.world = m.group(1)
            self.percent = float(m.group(3).replace(",", "."))
            self.eta = m.group(4)
            self.rate = float(m.group(5).replace(",", "."))
            if self.state != "paused":
                self.state = "running"
            return True
        if RE_DONE.search(line):
            self.state, self.percent, self.eta = "done", 100.0, ""
            return True
        m = RE_STOP.search(line)
        if m:
            self.state = "paused" if m.group(1).lower() == "paused" else "idle"
            return True
        return False

    def send(self, cmd):
        self.server.send(cmd)

    def started(self):
        self.state, self.percent, self.eta, self._paused_by_us = "running", 0.0, "", False

    def tick(self):
        """Oyuncu girince duraklat / boşalınca devam et."""
        if not self.server.is_running or not self.auto_pause or self.state not in ("running", "paused"):
            return
        try:
            n = len(self.online()) if self.online else 0
        except Exception:
            return
        if n and self.state == "running":
            self.server.try_send("chunky pause")
            self.state, self._paused_by_us = "paused", True
        elif not n and self.state == "paused" and self._paused_by_us:
            self.server.try_send("chunky continue")
            self.state, self._paused_by_us = "running", False
