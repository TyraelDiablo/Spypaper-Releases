"""Çökme ya da açılış hatasında suçlu eklenti/mod tahmini.

Hata metnindeki Java yığın satırlarının (at com.example.plugin.Foo.bar(...)) paketleri, plugins/ ve mods/
klasörlerindeki jar'ların içindeki paketlerle eşleştirilir. Minecraft'ın, sunucu yazılımının ve ortak
kütüphanelerin paketleri sayılmaz. Ayrıca "Error occurred while enabling X", "Could not load 'plugins/X.jar'",
Fabric/Forge'un "Mod X requires…" ve Mixin hataları gibi doğrudan ad veren satırlar da okunur.
Sonuç bir tahmindir; ilk sıradaki jar en çok iz bırakanıdır.
"""
import os
import re
import zipfile

IGNORE = ("java.", "javax.", "jdk.", "sun.", "com.sun.", "net.minecraft.", "com.mojang.", "org.bukkit.",
          "org.spigotmc.", "io.papermc.", "ca.spottedleaf.", "net.neoforged.", "net.minecraftforge.",
          "net.fabricmc.", "cpw.mods.", "org.spongepowered.", "com.google.", "org.apache.", "io.netty.",
          "it.unimi.", "org.slf4j.", "org.joml.", "net.kyori.", "org.objectweb.", "kotlin.", "kotlinx.",
          "com.fasterxml.", "org.yaml.", "org.jline.", "net.md_5.", "com.destroystokyo.", "co.aikar.",
          "org.purpurmc.", "dev.folia.", "org.eclipse.", "oshi.", "com.zaxxer.", "org.checkerframework.",
          "org.lwjgl.", "com.llamalad7.", "org.openjdk.", "it.unimi.dsi.", "org.jetbrains.", "org.intellij.")
FRAME = re.compile(r"\bat (?:[\w.$/@-]+//)?([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*){2,})\.[\w$<>]+\(")
CAUSED = re.compile(r"(?:Caused by|Exception in [^:]*): ([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*){2,})")
DIRECT = [
    re.compile(r"Error occurred while enabling (\S+)"),
    re.compile(r"Could not load '(?:plugins|mods)[/\\]([^']+)'"),
    re.compile(r"Mod '[^']*' \(([\w-]+)\)[^\n]* (?:requires|is incompatible)"),
    re.compile(r"Mixin apply for mod ([\w-]+) failed"),
    re.compile(r"mixins? config ([\w.-]+?)\.mixins\.json"),
    re.compile(r"Plugin (\S+) generated an exception"),
    re.compile(r"Could not pass event \S+ to (\S+)"),
]

_cache = {}


def _jar_dirs(server_path):
    return [d for d in (os.path.join(server_path, "plugins"), os.path.join(server_path, "mods")) if os.path.isdir(d)]


def index(server_path):
    """{paket_öneki: jar_adı} — her jar için sınıf içeren paketlerin 3 seviyelik önekleri."""
    out = {}
    for d in _jar_dirs(server_path):
        for fn in os.listdir(d):
            if not fn.endswith(".jar"):
                continue
            p = os.path.join(d, fn)
            try:
                key = (p, os.path.getmtime(p))
            except OSError:
                continue
            prefixes = _cache.get(key)
            if prefixes is None:
                prefixes = set()
                try:
                    with zipfile.ZipFile(p) as z:
                        for n in z.namelist():
                            if n.endswith(".class") and "/" in n and not n.startswith("META-INF/"):
                                parts = n.split("/")[:-1]
                                if len(parts) >= 2:
                                    prefixes.add(".".join(parts[:3]))
                except (OSError, zipfile.BadZipFile):
                    pass
                _cache[key] = prefixes
            for pre in prefixes:
                if not pre.startswith(IGNORE):
                    out.setdefault(pre, fn)
    return out


def _names(server_path):
    """jar adlarının küçük harfli, sürümsüz biçimleri -> jar."""
    out = {}
    for d in _jar_dirs(server_path):
        for fn in os.listdir(d):
            if fn.endswith(".jar"):
                base = re.split(r"[-_+ ](?=v?\d)", fn[:-4])[0].lower()
                out.setdefault(base, fn)
                out.setdefault(fn[:-4].lower(), fn)
    return out


def suspects(text, server_path, limit=3):
    """[(jar, puan, neden)] en olası suçlular. neden: "stack" ya da "named"."""
    if not text:
        return []
    idx = index(server_path)
    score = {}
    why = {}
    for m in list(FRAME.finditer(text)) + list(CAUSED.finditer(text)):
        cls = m.group(1)
        if cls.startswith(IGNORE):
            continue
        parts = cls.split(".")
        for n in (3, 2):
            jar = idx.get(".".join(parts[:n]))
            if jar:
                score[jar] = score.get(jar, 0) + 1
                why.setdefault(jar, "stack")
                break
    names = _names(server_path)
    for rx in DIRECT:
        for m in rx.finditer(text):
            raw = m.group(1).strip("'\"[]:,").lower()
            jar = names.get(raw) or names.get(raw.replace(".jar", "")) or next(
                (j for k, j in names.items() if k and (k == raw or k.replace("-", "") == raw.replace("-", ""))), None)
            if jar:
                score[jar] = score.get(jar, 0) + 5
                why[jar] = "named"
    ranked = sorted(score.items(), key=lambda kv: -kv[1])[:limit]
    return [(jar, n, why[jar]) for jar, n in ranked]


def crash_text(server_path, history_lines, max_age_s=600):
    """Konsol geçmişi + (yeniyse) son çökme raporu."""
    import time
    parts = ["\n".join(history_lines)]
    d = os.path.join(server_path, "crash-reports")
    if os.path.isdir(d):
        files = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".txt")), key=os.path.getmtime)
        if files and time.time() - os.path.getmtime(files[-1]) < max_age_s:
            try:
                with open(files[-1], encoding="utf-8", errors="replace") as f:
                    parts.append(f.read(200_000))
            except OSError:
                pass
    return "\n".join(parts)
