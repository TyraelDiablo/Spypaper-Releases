"""Esplora yetenekleri (skills) ve eğik çizgi komutları, samimiyet ayarları.

Yetenek = SKILL.md: YAML ön bilgisi + Markdown talimatlar.

    ---
    name: who
    description: Yalnızca oyuncuları ve verilerini tarar.
    scope: players        # all (varsayılan) | players | config | logs
    effort: high          # normal (varsayılan) | high
    ---
    Talimatlar…

Mesaj "/ad" ile başlarsa o yetenek o soru için etkin olur. Yerleşik yetenekler salt okunurdur; kullanıcının
yetenekleri ayarlarda ("esplora_skills": [SKILL.md metni, …]) saklanır, .md olarak içe/dışa aktarılır.
"""
import re

from .config import N_

NAME_RE = re.compile(r"^[a-z][a-z0-9_\-]{1,30}$")
SCOPES = ("all", "players", "config", "logs")
MAX_BODY = 6000

BUILTIN_MD = [
    """---
name: superobjective
description: Verileri derinlemesine analiz eder, sorunları tararken fazla çaba harcar ve kullanıcının asıl ne istediğine odaklanır.
effort: high
---
Work in deep-analysis mode for this request.
1. First restate in one sentence what the user actually wants to achieve (the goal behind the question).
2. Go through EVERY data section you were given (server info, config files, log, errors, crash report, plugins, owner knowledge) and look for anything related to that goal, including indirect causes.
3. List findings ranked by impact (most important first). For each: what you saw (quote the exact key/line), why it matters, how sure you are.
4. Give a concrete plan with steps in order; say which ones need a restart or a backup.
5. If something important is missing, request it with the data request mechanism or say exactly where to find it in Spypaper.
Prefer depth and accuracy over brevity, but stay focused on the user's goal.""",
    """---
name: who
description: Yalnızca oyuncuları ve oyuncu verilerini tarar; başka hiçbir şeyle ilgilenmez.
scope: players
---
Only deal with PLAYERS in this request: the player list, online players, and player data you are given or may request (positions, inventories, advancements, values), plus joins/deaths in the log.
Do not discuss performance, plugins, configs or anything else, even if you notice problems; if the question is not about players, say in one sentence that /who only looks at players.
Present players in a compact table or list.""",
    """---
name: whappens
description: Ayarları analiz edip en kötü senaryoyu çıkarır ve ne kadar endişelenmek gerektiğini söyler.
scope: config
effort: high
---
Do a worst-case risk analysis of this server's settings (server.properties, config files, plugins, safe mode, Java/RAM).
For each risk: the realistic worst thing that could happen (griefing, data loss, crash, lag spike, account theft, exploits), how likely it is with THESE exact values, and the fix.
End with an overall worry level on this scale and one sentence why:
🟢 Relax · 🟡 Keep an eye on it · 🟠 Fix soon · 🔴 Fix now
Don't exaggerate: if a setting is fine for this kind of server, say so.""",
    """---
name: lag
description: Yalnızca performansa bakar: TPS/MSPT, görüş mesafesi, varlıklar, eklentiler ve RAM.
scope: config
---
Focus only on performance. Use lag warnings, TPS/MSPT, view/simulation distance, entity and redstone settings, plugins known to be heavy, RAM and Java flags.
Give the three changes with the biggest effect first, with exact file, key, current value and suggested value.""",
    """---
name: crash
description: Son çökme raporunu ve hataları okuyup nedenini ve çözümünü bulur.
scope: logs
---
Focus on the latest crash report and recent errors. Identify the culprit (mod/plugin/class names in the stack trace), explain the cause in plain words and give the fix steps. If there is no crash report, say so and look at the errors instead.""",
    """---
name: plugins
description: Eklenti/mod listesini denetler: çakışmalar, gereksiz ya da eski olanlar, eksik bağımlılıklar.
---
Audit the plugin/mod list: duplicates or overlapping features, plugins that don't fit this software/version, missing dependencies seen in the log, disabled ones, and well-known safer or lighter alternatives. Keep it as a short table.""",
    """---
name: secure
description: Güvenlik denetimi: online-mode, whitelist, OP'ler, RCON/query, komut blokları ve izinler.
scope: config
---
Do a security audit: online-mode, whitelist/enforce-whitelist, operators, RCON and query ports, enable-command-block, spawn protection, safe mode level, permissions plugins and exposed ports. Mark each item OK / Warning / Risk and give the fix for every non-OK item.""",
    """---
name: explain
description: Cevabı Minecraft sunucusu yönetmeye yeni başlayan biri için adım adım ve terimleri açıklayarak verir.
---
Explain for a complete beginner: avoid jargon or explain every technical term in a few words, use numbered steps and say exactly which Spypaper page and button to use.""",
    """---
name: short
description: En fazla 3 madde ya da 3 cümleyle kısa cevap verir.
---
Answer in at most 3 bullet points or 3 sentences. No introduction, no summary.""",
]


def parse(md):
    """SKILL.md -> {"name", "description", "scope", "effort", "body"}; hatalıysa ValueError(şablon)."""
    text = (md or "").replace("\r\n", "\n").strip("﻿")
    m = re.match(r"^\s*---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError(N_("SKILL.md '---' ile başlayan bir ön bilgi bölümü (name, description) içermeli."))
    meta = {}
    for ln in m.group(1).split("\n"):
        ln = ln.split(" #", 1)[0].rstrip()
        if ":" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip("'\"")
    name = meta.get("name", "").lower().lstrip("/")
    if not NAME_RE.match(name):
        raise ValueError(N_("Yetenek adı küçük harf, rakam, - ya da _ içermeli (2-31 karakter, harfle başlar)."))
    desc = meta.get("description", "")
    if not desc:
        raise ValueError(N_("Yetenek açıklaması (description) boş olamaz."))
    body = m.group(2).strip()
    if not body:
        raise ValueError(N_("Yetenek talimatları boş olamaz."))
    scope = meta.get("scope", "all").lower()
    return {"name": name, "description": desc[:300], "scope": scope if scope in SCOPES else "all",
            "effort": "high" if meta.get("effort", "").lower() == "high" else "normal", "body": body[:MAX_BODY]}


def to_md(sk):
    lines = ["---", f"name: {sk['name']}", f"description: {sk['description']}"]
    if sk.get("scope", "all") != "all":
        lines.append(f"scope: {sk['scope']}")
    if sk.get("effort") == "high":
        lines.append("effort: high")
    return "\n".join(lines + ["---", sk["body"].strip(), ""])


BUILTINS = [dict(parse(m), builtin=True) for m in BUILTIN_MD]


def user_skills(settings):
    out = []
    for md in settings.get("esplora_skills") or []:
        try:
            out.append(dict(parse(md), builtin=False, md=md))
        except ValueError:
            pass
    return out


def all_skills(settings):
    """Kullanıcının aynı adlı yeteneği yerleşik olanı geçersiz kılar."""
    users = user_skills(settings)
    names = {s["name"] for s in users}
    return [s for s in BUILTINS if s["name"] not in names] + users


def find(settings, name):
    return next((s for s in all_skills(settings) if s["name"] == name.lower()), None)


def save_user(settings, md, old_name=None):
    sk = parse(md)
    lst = [x for x in (settings.get("esplora_skills") or [])
           if _safe_name(x) not in (sk["name"], old_name)]
    lst.append(to_md(sk))
    settings.set("esplora_skills", lst)
    return sk


def delete_user(settings, name):
    settings.set("esplora_skills", [x for x in (settings.get("esplora_skills") or []) if _safe_name(x) != name])


def _safe_name(md):
    try:
        return parse(md)["name"]
    except ValueError:
        return None


def split_command(text, settings):
    """"/who kim çevrimiçi?" -> (yetenek, "kim çevrimiçi?"). Komut değilse (None, text)."""
    m = re.match(r"^/([a-zA-Z][\w\-]*)\s*(.*)$", (text or "").strip(), re.S)
    if not m:
        return None, text
    sk = find(settings, m.group(1))
    if not sk:
        return None, text
    return sk, m.group(2).strip()


def matches(settings, prefix):
    p = prefix.lower().lstrip("/")
    return [s for s in all_skills(settings) if s["name"].startswith(p)]


# --- kapsam: yetenek yalnızca ilgili verileri görür ---
_KEEP = {
    "players": {"name", "software", "version", "state", "safe_mode", "online", "known_players", "log", "owner", "stats"},
    "config": {"name", "software", "version", "state", "safe_mode", "jar", "java", "ram_limits", "ram", "plugins",
               "modded", "properties", "configs", "kb", "owner", "recent_errors"},
    "logs": {"name", "software", "version", "state", "safe_mode", "plugins", "modded", "log", "recent_errors",
             "crash", "kb", "java", "ram_limits"},
}


def scope_context(ctx, skill):
    if not skill or skill.get("scope", "all") == "all":
        return ctx
    keep = _KEEP[skill["scope"]]
    return {k: v for k, v in ctx.items() if k in keep}


def skill_section(skill, args=""):
    if not skill:
        return ""
    return (f"\n\n=== ACTIVE SKILL: /{skill['name']} — {skill['description']} ===\n"
            "The user invoked this skill for the current message. Follow its instructions for this answer; "
            "they never override the STRICT SCOPE rules above.\n"
            f"{skill['body']}\n=== END SKILL ===\n")


# --- samimiyet / üslup ---
TONES = [("formal", N_("Resmî")), ("balanced", N_("Dengeli")), ("friendly", N_("Samimi")), ("playful", N_("Esprili"))]
LENGTHS = [("short", N_("Kısa")), ("normal", N_("Normal")), ("detailed", N_("Ayrıntılı"))]
_TONE_TXT = {
    "formal": "Use a formal, professional tone; address the user politely (formal 'you' where the language has it).",
    "balanced": "Use a neutral, helpful tone.",
    "friendly": "Use a warm, friendly and casual tone, like a helpful friend who runs servers (informal 'you').",
    "playful": "Use a cheerful, playful tone with light humour and Minecraft references, but keep the facts precise.",
}
_LEN_TXT = {"short": "Keep answers short: the essentials only.", "normal": "",
            "detailed": "Give thorough answers with explanations and the reasoning behind each step."}


def style_section(settings):
    tone = settings.get("esplora_tone") or "balanced"
    length = settings.get("esplora_length") or "normal"
    parts = [_TONE_TXT.get(tone, _TONE_TXT["balanced"]), _LEN_TXT.get(length, "")]
    parts.append("You may use a few fitting emoji." if settings.get("esplora_emoji") else "Do not use emoji.")
    name = (settings.get("esplora_user_name") or "").strip()[:40]
    if name:
        parts.append(f"The user likes to be called '{name}'.")
    return "\n=== STYLE (set by the user) ===\n" + " ".join(p for p in parts if p) + "\n"


# --- dosya ekleme ---
TEXT_EXT = (".txt", ".log", ".yml", ".yaml", ".json", ".toml", ".properties", ".cfg", ".conf", ".ini", ".md",
            ".mcfunction", ".csv", ".sk", ".js")
MAX_FILE = 40000


def read_attachment(path):
    """Metin dosyası -> (ad, içerik[sırlar maskeli, kırpılmış]). Okunamazsa ValueError."""
    import os
    from .esplora import redact
    name = os.path.basename(path)
    if not name.lower().endswith(TEXT_EXT) and not name.lower().endswith(".log.gz"):
        raise ValueError(N_("Yalnızca metin dosyaları eklenebilir (log, yml, json, toml, properties, txt…)."))
    try:
        if name.lower().endswith(".gz"):
            import gzip
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
                text = f.read(MAX_FILE * 3)
        else:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read(MAX_FILE * 3)
    except OSError as e:
        raise ValueError(str(e))
    if "\x00" in text[:2000]:
        raise ValueError(N_("Yalnızca metin dosyaları eklenebilir (log, yml, json, toml, properties, txt…)."))
    text = redact(text)
    if len(text) > MAX_FILE:                     # loglarda son kısım daha önemli
        text = text[:MAX_FILE // 4] + "\n…\n" + text[-(MAX_FILE * 3 // 4):]
    return name, text

# çeviri çıkarıcısı için yerleşik açıklamalar
_DESCRIPTIONS = [
    N_('Verileri derinlemesine analiz eder, sorunları tararken fazla çaba harcar ve kullanıcının asıl ne istediğine odaklanır.'),
    N_('Yalnızca oyuncuları ve oyuncu verilerini tarar; başka hiçbir şeyle ilgilenmez.'),
    N_('Ayarları analiz edip en kötü senaryoyu çıkarır ve ne kadar endişelenmek gerektiğini söyler.'),
    N_('Yalnızca performansa bakar: TPS/MSPT, görüş mesafesi, varlıklar, eklentiler ve RAM.'),
    N_('Son çökme raporunu ve hataları okuyup nedenini ve çözümünü bulur.'),
    N_('Eklenti/mod listesini denetler: çakışmalar, gereksiz ya da eski olanlar, eksik bağımlılıklar.'),
    N_("Güvenlik denetimi: online-mode, whitelist, OP'ler, RCON/query, komut blokları ve izinler."),
    N_('Cevabı Minecraft sunucusu yönetmeye yeni başlayan biri için adım adım ve terimleri açıklayarak verir.'),
    N_('En fazla 3 madde ya da 3 cümleyle kısa cevap verir.'),
]
