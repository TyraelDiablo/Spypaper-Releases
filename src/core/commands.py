"""Konsol komut önerileri: Minecraft (Java) sunucu komutlarının sözdizimi ve tamamlama motoru.

Sözdizimi: her komutun bir ya da birkaç biçimi vardır. Biçimdeki parçalar:
  "set"            sabit kelime
  "<ad:tür>"       zorunlu argüman
  "[ad:tür]"       isteğe bağlı argüman
  "<ad:text>"      satırın geri kalanı (say, msg, kick sebebi…)
Türler: player, item, effect, enchant, gamerule, gamemode, difficulty, int, num, pos, rot, dim, bool,
        entity, text, word, time, weather, sound, biome, structure, attribute
"""
import re

from .config import N_

# türlerin ekranda görünen adı (köşeli parantez içinde)
ARG_NAMES = {
    "player": N_("oyuncu"), "target": N_("hedef"), "item": N_("eşya"), "effect": N_("efekt"),
    "enchant": N_("büyü"), "gamerule": N_("kural"), "gamemode": N_("oyun modu"), "difficulty": N_("zorluk"),
    "int": N_("sayı"), "num": N_("sayı"), "pos": N_("x y z"), "dim": N_("boyut"), "bool": N_("true/false"),
    "entity": N_("varlık"), "text": N_("mesaj"), "word": N_("ad"), "time": N_("zaman"), "rot": N_("yaw pitch"),
    "value": N_("değer"),
}
# argüman adına göre (türden önce bakılır)
NAMED = {
    "target": N_("hedef"), "count": N_("miktar"), "seconds": N_("saniye"), "amplifier": N_("güç"),
    "level": N_("seviye"), "reason": N_("sebep"), "duration": N_("süre"), "hideParticles": N_("parçacıkları gizle"),
    "from": N_("başlangıç x y z"), "to": N_("bitiş x y z"), "block": N_("blok"), "team": N_("takım"),
    "name": N_("ad"), "objective": N_("hedef skor"), "criteria": N_("ölçüt"), "host": N_("adres"),
    "port": N_("port"), "plugin": N_("eklenti"), "command": N_("komut"), "structure": N_("yapı"),
    "biome": N_("biyom"), "sound": N_("ses"), "particle": N_("parçacık"), "range": N_("aralık"),
    "slot": N_("yuva"), "option": N_("seçenek"), "displayName": N_("görünen ad"), "fadeIn": N_("giriş"),
    "stay": N_("kalış"), "fadeOut": N_("çıkış"), "attribute": N_("özellik"), "x": "x", "z": "z",
    # Bedrock
    "xpamount": N_("miktar (seviye için 10L)"), "event": N_("olay"), "ability": N_("yetenek"), "npc": N_("NPC"),
    "scene": N_("sahne"), "animation": N_("animasyon"), "intensity": N_("şiddet"), "shake": N_("sallanma türü"),
    "volume": N_("ses düzeyi"), "fade": N_("geçiş süresi"), "repeat": N_("tekrar"), "preload": N_("önceden yükle"),
    "radius": N_("yarıçap"), "data": N_("veri değeri"), "cause": N_("hasar türü"), "spread": N_("aralık"),
    "mode": N_("kip"), "perm": N_("izin"), "state": N_("durum"), "element": N_("öğe"), "preset": N_("ön ayar"),
    "fog": N_("sis"), "table": N_("ganimet tablosu"), "function": N_("fonksiyon"), "pitch": N_("perde"),
    "dest": N_("hedef x y z"), "next": N_("sonraki durum"), "blend": N_("geçiş"), "all": N_("tümü"),
}

# komut: (açıklama, [biçimler])
COMMANDS = {
    "say": (N_("Herkese sunucu adına mesaj gönderir"), ["<text>"]),
    "tell": (N_("Bir oyuncuya özel mesaj gönderir"), ["<player> <text>"]),
    "msg": (N_("Bir oyuncuya özel mesaj gönderir"), ["<player> <text>"]),
    "tellraw": (N_("Biçimli (JSON) mesaj gönderir"), ["<player> <text>"]),
    "title": (N_("Ekranda başlık gösterir"), ["<player> title <text>", "<player> subtitle <text>",
                                              "<player> actionbar <text>", "<player> clear", "<player> reset",
                                              "<player> times <fadeIn:int> <stay:int> <fadeOut:int>"]),
    "list": (N_("Çevrimiçi oyuncuları listeler"), [""]),
    "kick": (N_("Oyuncuyu sunucudan atar"), ["<player> [reason:text]"]),
    "ban": (N_("Oyuncuyu yasaklar"), ["<player> [reason:text]"]),
    "ban-ip": (N_("IP adresini yasaklar"), ["<target:word> [reason:text]"]),
    "pardon": (N_("Oyuncunun yasağını kaldırır"), ["<player>"]),
    "pardon-ip": (N_("IP yasağını kaldırır"), ["<target:word>"]),
    "banlist": (N_("Yasaklı listesini gösterir"), ["", "players", "ips"]),
    "op": (N_("Oyuncuyu yönetici yapar"), ["<player>"]),
    "deop": (N_("Yöneticiliği kaldırır"), ["<player>"]),
    "whitelist": (N_("Beyaz listeyi yönetir"), ["add <player>", "remove <player>", "on", "off", "list", "reload"]),
    "gamemode": (N_("Oyun modunu değiştirir"), ["<gamemode> [player]"]),
    "defaultgamemode": (N_("Yeni oyuncuların oyun modunu ayarlar"), ["<gamemode>"]),
    "difficulty": (N_("Zorluğu değiştirir"), ["<difficulty>"]),
    "time": (N_("Saati ayarlar"), ["set <time>", "add <int>", "query daytime", "query gametime", "query day"]),
    "weather": (N_("Havayı değiştirir"), ["clear [duration:int]", "rain [duration:int]", "thunder [duration:int]"]),
    "give": (N_("Oyuncuya eşya verir"), ["<player> <item> [count:int]"]),
    "clear": (N_("Envanteri temizler"), ["[player] [item] [count:int]"]),
    "effect": (N_("Efekt verir ya da kaldırır"), ["give <player> <effect> [seconds:int] [amplifier:int] [hideParticles:bool]",
                                                 "clear [player] [effect]"]),
    "enchant": (N_("Elindeki eşyayı büyüler"), ["<player> <enchant> [level:int]"]),
    "xp": (N_("Deneyim verir"), ["add <player> <int> levels", "add <player> <int> points",
                                 "set <player> <int> levels", "query <player> levels"]),
    "experience": (N_("Deneyim verir"), ["add <player> <int> levels", "set <player> <int> levels"]),
    "tp": (N_("Işınlar"), ["<player> <target:player>", "<player> <pos>", "<pos>"]),
    "teleport": (N_("Işınlar"), ["<player> <target:player>", "<player> <pos>"]),
    "spawnpoint": (N_("Oyuncunun doğma noktasını ayarlar"), ["[player] [pos]"]),
    "setworldspawn": (N_("Dünyanın doğma noktasını ayarlar"), ["[pos]"]),
    "kill": (N_("Varlıkları öldürür"), ["[player]"]),
    "summon": (N_("Varlık çağırır"), ["<entity> [pos]"]),
    "gamerule": (N_("Oyun kuralını görür ya da değiştirir"), ["<gamerule> [value]"]),
    "seed": (N_("Dünyanın seed'ini gösterir"), [""]),
    "save-all": (N_("Dünyayı kaydeder"), ["", "flush"]),
    "save-off": (N_("Otomatik kaydı kapatır"), [""]),
    "save-on": (N_("Otomatik kaydı açar"), [""]),
    "stop": (N_("Sunucuyu kaydedip kapatır"), [""]),
    "reload": (N_("Veri paketlerini yeniden yükler"), [""]),
    "worldborder": (N_("Dünya sınırını ayarlar"), ["set <int> [seconds:int]", "add <int> [seconds:int]",
                                                   "center <x:num> <z:num>", "get"]),
    "locate": (N_("En yakın yapıyı bulur"), ["structure <structure:word>", "biome <biome:word>"]),
    "playsound": (N_("Ses çalar"), ["<sound:word> master <player>"]),
    "stopsound": (N_("Sesi durdurur"), ["<player>"]),
    "particle": (N_("Parçacık çıkarır"), ["<particle:word> [pos]"]),
    "fill": (N_("Bir alanı blokla doldurur"), ["<from:pos> <to:pos> <block:item>"]),
    "setblock": (N_("Blok koyar"), ["<pos> <block:item>"]),
    "execute": (N_("Komutu başka bir bağlamda çalıştırır"), ["as <player> run <command:text>",
                                                            "in <dim> run <command:text>",
                                                            "at <player> run <command:text>"]),
    "team": (N_("Takımları yönetir"), ["add <team:word> [displayName:text]", "remove <team:word>",
                                       "join <team:word> [player]", "leave <player>", "empty <team:word>",
                                       "list [team:word]", "modify <team:word> <option:word> <value>"]),
    "scoreboard": (N_("Skor tablosunu yönetir"), ["objectives list", "objectives add <name:word> <criteria:word>",
                                                  "players list [player]", "players set <player> <objective:word> <int>"]),
    "tag": (N_("Varlık etiketlerini yönetir"), ["<player> add <name:word>", "<player> remove <name:word>",
                                                "<player> list"]),
    "trigger": (N_("Tetikleyici skor"), ["<objective:word>"]),
    "datapack": (N_("Veri paketlerini yönetir"), ["list", "enable <name:word>", "disable <name:word>"]),
    "function": (N_("Fonksiyon çalıştırır"), ["<name:word>"]),
    "recipe": (N_("Tarif verir ya da alır"), ["give <player> *", "take <player> *"]),
    "advancement": (N_("Başarımları verir ya da alır"), ["grant <player> everything", "revoke <player> everything"]),
    "attribute": (N_("Özellik değerini görür ya da değiştirir"), ["<player> <attribute:word> get",
                                                                  "<player> <attribute:word> base set <num>"]),
    "spectate": (N_("İzleyici modunda bir varlığı izler"), ["<target:player> [player]"]),
    "ride": (N_("Bindirir ya da indirir"), ["<player> mount <target:player>", "<player> dismount"]),
    "damage": (N_("Hasar verir"), ["<player> <num>"]),
    "item": (N_("Eşyaları değiştirir"), ["replace entity <player> <slot:word> with <item> [count:int]"]),
    "random": (N_("Rastgele sayı üretir"), ["value <range:word>", "roll <range:word>"]),
    "tick": (N_("Oyun hızını yönetir"), ["query", "rate <num>", "freeze", "unfreeze", "step [int]", "sprint <time>"]),
    "transfer": (N_("Oyuncuyu başka sunucuya aktarır"), ["<host:word> [port:int] [player]"]),
    "me": (N_("Eylem mesajı gönderir"), ["<text>"]),
    "help": (N_("Komutları listeler"), ["[command:word]"]),
    # Paper / Spigot / Bukkit
    "plugins": (N_("Eklentileri listeler (Paper/Spigot)"), [""]),
    "pl": (N_("Eklentileri listeler (Paper/Spigot)"), [""]),
    "version": (N_("Sunucu sürümünü gösterir"), ["[plugin:word]"]),
    "tps": (N_("Saniyedeki tick sayısını gösterir (Paper)"), [""]),
    "mspt": (N_("Tick süresini gösterir (Paper)"), [""]),
    "paper": (N_("Paper komutları"), ["version", "reload", "heap", "entity list", "chunkinfo"]),
}

LITERAL_SETS = {
    "gamemode": ["survival", "creative", "adventure", "spectator"],
    "difficulty": ["peaceful", "easy", "normal", "hard"],
    "time": ["day", "noon", "night", "midnight"],
    "bool": ["true", "false"],
    "dim": ["minecraft:overworld", "minecraft:the_nether", "minecraft:the_end"],
    "pos": ["~ ~ ~"],
}

GAMERULES = ["announceAdvancements", "commandBlockOutput", "disableElytraMovementCheck", "disableRaids",
             "doDaylightCycle", "doEntityDrops", "doFireTick", "doImmediateRespawn", "doInsomnia", "doLimitedCrafting",
             "doMobLoot", "doMobSpawning", "doPatrolSpawning", "doTileDrops", "doTraderSpawning", "doVinesSpread",
             "doWardenSpawning", "doWeatherCycle", "drowningDamage", "fallDamage", "fireDamage", "forgiveDeadPlayers",
             "freezeDamage", "keepInventory", "logAdminCommands", "maxCommandChainLength", "maxEntityCramming",
             "mobGriefing", "naturalRegeneration", "playersSleepingPercentage", "pvp", "randomTickSpeed",
             "reducedDebugInfo", "sendCommandFeedback", "showDeathMessages", "spawnRadius", "spectatorsGenerateChunks",
             "universalAnger", "locatorBar", "spawnChunkRadius"]
EFFECTS = ["speed", "slowness", "haste", "mining_fatigue", "strength", "instant_health", "instant_damage",
           "jump_boost", "nausea", "regeneration", "resistance", "fire_resistance", "water_breathing", "invisibility",
           "blindness", "night_vision", "hunger", "weakness", "poison", "wither", "health_boost", "absorption",
           "saturation", "glowing", "levitation", "luck", "unluck", "slow_falling", "conduit_power",
           "dolphins_grace", "bad_omen", "hero_of_the_village", "darkness"]
ENCHANTS = ["protection", "fire_protection", "feather_falling", "blast_protection", "projectile_protection",
            "respiration", "aqua_affinity", "thorns", "depth_strider", "frost_walker", "binding_curse", "soul_speed",
            "swift_sneak", "sharpness", "smite", "bane_of_arthropods", "knockback", "fire_aspect", "looting",
            "sweeping_edge", "efficiency", "silk_touch", "unbreaking", "fortune", "power", "punch", "flame",
            "infinity", "luck_of_the_sea", "lure", "loyalty", "impaling", "riptide", "channeling", "multishot",
            "quick_charge", "piercing", "density", "breach", "wind_burst", "mending", "vanishing_curse"]
ENTITIES = ["zombie", "skeleton", "creeper", "spider", "enderman", "villager", "cow", "pig", "sheep", "chicken",
            "horse", "wolf", "cat", "iron_golem", "wither", "ender_dragon", "warden", "lightning_bolt", "armor_stand",
            "item_frame", "tnt", "allay", "axolotl", "bee", "fox", "goat", "parrot", "piglin", "blaze", "ghast",
            "slime", "witch", "pillager", "evoker", "ravager", "phantom", "drowned", "husk", "stray", "breeze"]

MAX = 8


def _parse_variant(v):
    out = []
    for tok in v.split():
        m = re.fullmatch(r"([<\[])([^:\]>]+)(?::([^\]>]+))?[>\]]", tok)
        if m:
            name, typ = m.group(2), m.group(3) or m.group(2)
            out.append({"kind": "arg", "name": name, "type": typ, "optional": m.group(1) == "["})
        else:
            out.append({"kind": "lit", "text": tok})
    return out


SPECS = {name: (desc, [_parse_variant(v) for v in variants]) for name, (desc, variants) in COMMANDS.items()}


def _tokens(text):
    """'give Ali dia' -> (['give','Ali'], 'dia');  'give Ali ' -> (['give','Ali'], '')"""
    parts = text.split(" ")
    return [p for p in parts[:-1] if p != ""], parts[-1]


def _match_prefix(variant, done):
    """Biçim, yazılmış tamamlanmış parçalarla uyuşuyor mu; uyuşuyorsa sıradaki parçanın indeksi.
    'pos' türü üç kelime (x y z) tüketir; yarım yazılmışsa hâlâ o parçada sayılır."""
    i = k = 0
    while k < len(done):
        if i >= len(variant):
            return None
        part, tok = variant[i], done[k]
        if part["kind"] == "lit":
            if tok.lower() != part["text"].lower():
                return None
            i += 1
            k += 1
        elif part["type"] == "text":
            return i                                    # satırın kalanı hep bu argümanda
        elif part["type"] in ("pos", "rot"):
            n = 3 if part["type"] == "pos" else 2
            take = min(n, len(done) - k)
            k += take
            if take < n:
                return i
            i += 1
        else:
            i += 1
            k += 1
    return i


LIT_LABEL = N_("sabit")


def _arg_label(part, tr):
    typ = part["type"]
    shown = NAMED.get(part["name"]) or ARG_NAMES.get(typ) or ARG_NAMES.get(part["name"])
    name = tr(shown) if shown else part["name"]
    return f"[{name}]" if part["optional"] else f"<{name}>"


def usage(variant, tr, highlight=None):
    """Biçimin okunur hali; highlight indeksi '«…»' ile işaretlenmez, (metin, [(başlangıç, bitiş)]) döner."""
    out, spans, pos = [], [], 0
    for i, part in enumerate(variant):
        s = part["text"] if part["kind"] == "lit" else _arg_label(part, tr)
        if i == highlight:
            spans.append((pos, pos + len(s)))
        out.append(s)
        pos += len(s) + 1
    return " ".join(out), spans


def suggest(text, ctx, tr=lambda s, **k: s):
    """Konsol girdisi için öneriler.

    ctx: {"players": [...], "items": [...]}
    Döner: {"items": [(eklenecek_metin, görünen, açıklama)], "hint": (komut_biçimi, vurgulu_aralıklar) ya da None}
    'eklenecek_metin' girdinin tamamının yeni hali.
    """
    text = text.lstrip("/")
    bedrock = ctx.get("edition") == "bedrock"
    specs = SPECS_BEDROCK if bedrock else SPECS
    done, cur = _tokens(text)
    base = text[: len(text) - len(cur)]
    res = {"items": [], "hint": None}
    if not done:                                         # komut adı yazılıyor
        q = cur.lower()
        names = sorted(n for n in specs if n.startswith(q))
        for n in names[:MAX]:
            desc, variants = specs[n]
            first = usage(variants[0], tr)[0]
            res["items"].append((n + " ", f"{n} {first}".strip(), tr(desc)))
        if len(names) == 1 or cur.lower() in specs:
            n = cur.lower() if cur.lower() in specs else names[0]
            res["hint"] = (n + " " + usage(specs[n][1][0], tr)[0], [])
        return res
    cmd = done[0].lower()
    if cmd not in specs:
        return res
    desc, variants = specs[cmd]
    rest = done[1:]
    cands, hint, hint_open = [], None, False
    for v in variants:
        i = _match_prefix(v, rest)
        if i is None:
            continue
        if hint is None or (not hint_open and i < len(v)):   # doldurulacak parçası kalan biçim öncelikli
            u, spans = usage(v, tr, highlight=i if i < len(v) else None)
            hint = (f"{cmd} {u}".strip(), [(a + len(cmd) + 1, b + len(cmd) + 1) for a, b in spans])
            hint_open = i < len(v)
        if i >= len(v):
            continue
        part = v[i]
        if part["kind"] == "lit":
            cands.append((part["text"], tr(LIT_LABEL)))
        else:
            for val in _values(part, ctx):
                cands.append((val, _arg_label(part, tr)))
    res["hint"] = hint
    q = cur.lower()
    seen = set()
    for val, label in cands:
        low = val.lower()
        if low in seen or not (low.startswith(q) or (":" not in q and low.split(":")[-1].startswith(q))):
            continue
        seen.add(low)
        res["items"].append((base + val + ("" if val.endswith(("=", "{")) else " "), val, label))
        if len(res["items"]) >= MAX:
            break
    return res


def _values(part, ctx):
    typ = part["type"]
    if ctx.get("edition") == "bedrock":
        if typ == "player":
            return list(ctx.get("players") or []) + SELECTORS_BEDROCK
        if typ == "gamerule":
            return GAMERULES_BEDROCK
        if part["name"] == "event":
            return MOB_EVENTS
        if part["name"] == "ability":
            return ABILITIES
        if typ in LITERAL_SETS_BEDROCK:
            return LITERAL_SETS_BEDROCK[typ]
    if typ == "player" or part["name"] == "target" and typ == "player":
        return list(ctx.get("players") or []) + ["@a", "@p", "@r", "@s"]
    if typ == "item":
        return list(ctx.get("items") or [])
    if typ == "effect":
        return EFFECTS
    if typ == "enchant":
        return ENCHANTS
    if typ == "gamerule":
        return GAMERULES
    if typ == "entity":
        return ENTITIES
    return LITERAL_SETS.get(typ, [])


# ---------------------------------------------------------------- Bedrock Dedicated Server
# Bedrock'un sözdizimi Java'dan farklıdır: effect'te "give" yok, xp miktarı önce gelir ("10L"), locate kısa yazılabilir,
# oyun kuralları küçük harflidir; seçicilerde hasitem, family, has_property, haspermission gibi filtreler vardır.
COMMANDS_BEDROCK = {
    "say": (N_("Herkese sunucu adına mesaj gönderir"), ["<text>"]),
    "tell": (N_("Bir oyuncuya özel mesaj gönderir"), ["<player> <text>"]),
    "msg": (N_("Bir oyuncuya özel mesaj gönderir"), ["<player> <text>"]),
    "w": (N_("Bir oyuncuya özel mesaj gönderir"), ["<player> <text>"]),
    "me": (N_("Eylem mesajı gönderir"), ["<text>"]),
    "tellraw": (N_("Biçimli mesaj gönderir (rawtext JSON)"), ["<player> <text>"]),
    "title": (N_("Ekranda başlık gösterir"), ["<player> title <text>", "<player> subtitle <text>",
                                              "<player> actionbar <text>", "<player> clear", "<player> reset",
                                              "<player> times <fadeIn:int> <stay:int> <fadeOut:int>"]),
    "titleraw": (N_("Biçimli başlık gösterir (rawtext JSON)"), ["<player> title <text>", "<player> subtitle <text>",
                                                                "<player> actionbar <text>"]),
    "list": (N_("Çevrimiçi oyuncuları listeler"), [""]),
    "kick": (N_("Oyuncuyu sunucudan atar"), ["<player> [reason:text]"]),
    "op": (N_("Oyuncuyu operatör yapar"), ["<player>"]),
    "deop": (N_("Operatörlüğü kaldırır"), ["<player>"]),
    "allowlist": (N_("İzin listesini yönetir"), ["add <player>", "remove <player>", "list", "on", "off", "reload"]),
    "permission": (N_("permissions.json'u yönetir"), ["list", "reload"]),
    "setmaxplayers": (N_("En fazla oyuncu sayısını değiştirir"), ["<int>"]),
    "changesetting": (N_("Sunucu ayarını değiştirir"), ["allow-cheats <bool>", "difficulty <difficulty>"]),
    "gamemode": (N_("Oyun modunu değiştirir"), ["<gamemode> [player]"]),
    "defaultgamemode": (N_("Yeni oyuncuların oyun modunu ayarlar"), ["<gamemode>"]),
    "difficulty": (N_("Zorluğu değiştirir"), ["<difficulty>"]),
    "time": (N_("Saati ayarlar"), ["set <time>", "add <int>", "query daytime", "query gametime", "query day"]),
    "daylock": (N_("Gün döngüsünü durdurur"), ["[bool]"]),
    "alwaysday": (N_("Gün döngüsünü durdurur"), ["[bool]"]),
    "weather": (N_("Havayı değiştirir"), ["clear [duration:int]", "rain [duration:int]", "thunder [duration:int]",
                                         "query"]),
    "toggledownfall": (N_("Yağmuru açar ya da kapatır"), [""]),
    "give": (N_("Oyuncuya eşya verir"), ["<player> <item> [count:int] [data:int]"]),
    "clear": (N_("Envanteri temizler"), ["[player] [item] [data:int] [count:int]"]),
    "effect": (N_("Efekt verir ya da kaldırır (Bedrock'ta 'give' yazılmaz)"),
               ["<player> <effect> [seconds:int] [amplifier:int] [hideParticles:bool]", "<player> clear"]),
    "enchant": (N_("Elindeki eşyayı büyüler"), ["<player> <enchant> [level:int]"]),
    "xp": (N_("Deneyim verir (seviye için sayının sonuna L: 10L)"), ["<xpamount:word> [player]"]),
    "tp": (N_("Işınlar"), ["<player> <target:player>", "<player> <pos>", "<pos>"]),
    "teleport": (N_("Işınlar"), ["<player> <target:player>", "<player> <pos>", "<pos>"]),
    "spawnpoint": (N_("Oyuncunun doğma noktasını ayarlar"), ["[player] [pos]"]),
    "clearspawnpoint": (N_("Oyuncunun doğma noktasını siler"), ["[player]"]),
    "setworldspawn": (N_("Dünyanın doğma noktasını ayarlar"), ["[pos]"]),
    "spreadplayers": (N_("Oyuncuları alana dağıtır"), ["<x:num> <z:num> <spread:num> <range:num> <player>"]),
    "kill": (N_("Varlıkları öldürür"), ["[player]"]),
    "damage": (N_("Hasar verir"), ["<player> <int> [cause:word]"]),
    "summon": (N_("Varlık çağırır"), ["<entity> [pos]", "<entity> <name:word> [pos]"]),
    "ride": (N_("Bindirir ya da indirir"), ["<player> start_riding <target:player>", "<player> stop_riding",
                                           "<player> evict_riders", "<player> summon_rider <entity>"]),
    "gamerule": (N_("Oyun kuralını görür ya da değiştirir"), ["<gamerule> [value]"]),
    "locate": (N_("En yakın yapıyı ya da biyomu bulur (Bedrock'ta kısa yazılabilir: locate village)"),
               ["structure <structure>", "biome <biome:word>", "<structure>"]),
    "fill": (N_("Bir alanı blokla doldurur"), ["<from:pos> <to:pos> <block:item> [mode:word]"]),
    "setblock": (N_("Blok koyar"), ["<pos> <block:item> [mode:word]"]),
    "clone": (N_("Bir alanı kopyalar"), ["<from:pos> <to:pos> <dest:pos>"]),
    "structure": (N_("Yapı kaydeder ya da yükler"), ["save <name:word> <from:pos> <to:pos>", "load <name:word> <pos>",
                                                    "delete <name:word>"]),
    "execute": (N_("Komutu başka bir bağlamda çalıştırır"), ["as <player> run <command:text>",
                                                            "at <player> run <command:text>",
                                                            "in <dim> run <command:text>",
                                                            "if entity <player> run <command:text>"]),
    "testfor": (N_("Seçiciye uyan varlık var mı bakar"), ["<player>"]),
    "testforblock": (N_("Bir konumdaki bloğu denetler"), ["<pos> <block:item>"]),
    "scoreboard": (N_("Skor tablosunu yönetir"), ["objectives list", "objectives add <name:word> dummy [displayName:text]",
                                                  "objectives setdisplay sidebar [objective:word]",
                                                  "players list [player]", "players set <player> <objective:word> <int>",
                                                  "players add <player> <objective:word> <int>"]),
    "tag": (N_("Varlık etiketlerini yönetir"), ["<player> add <name:word>", "<player> remove <name:word>", "<player> list"]),
    "function": (N_("Fonksiyon çalıştırır"), ["<name:word>"]),
    "reload": (N_("Fonksiyonları ve betikleri yeniden yükler"), ["", "all"]),
    "playsound": (N_("Ses çalar"), ["<sound:word> [player] [pos] [volume:num] [pitch:num]"]),
    "stopsound": (N_("Sesi durdurur"), ["<player> [sound:word]"]),
    "music": (N_("Müzik çalar ya da durdurur"), ["play <sound:word> [volume:num] [fade:num] [repeat:word]",
                                                "queue <sound:word> [volume:num] [fade:num] [repeat:word]",
                                                "stop [fade:num]", "volume <volume:num>"]),
    "particle": (N_("Parçacık çıkarır"), ["<particle:word> [pos]"]),
    "camerashake": (N_("Kamerayı sallar"), ["add <player> [intensity:num] [seconds:num] [shake:word]", "stop [player]"]),
    "camera": (N_("Oyuncunun kamerasını yönetir"), ["<player> clear", "<player> fade", "<player> set <preset:word>"]),
    "fog": (N_("Sis ayarlarını yönetir"), ["<player> push <fog:word> <name:word>", "<player> pop <name:word>",
                                           "<player> remove <name:word>"]),
    "hud": (N_("Oyuncunun ekran öğelerini gizler ya da gösterir"), ["<player> hide [element:word]",
                                                                    "<player> reset [element:word]"]),
    "inputpermission": (N_("Oyuncunun kamera/hareket iznini ayarlar"),
                        ["query <player> <perm:word>", "set <player> <perm:word> <state:word>"]),
    "ability": (N_("Oyuncu yeteneğini ayarlar (uçma, sessiz, dünya kurucu; Education özelliği gerekebilir)"),
                ["<player> <ability:word> [bool]"]),
    "dialogue": (N_("NPC diyalog penceresi açar"), ["open <npc:player> <player> [scene:word]",
                                                   "change <npc:player> <scene:word> [player]"]),
    "playanimation": (N_("Varlığa animasyon oynatır"), ["<player> <animation:word> [next:word] [blend:num]"]),
    "mobevent": (N_("Dünya olaylarını açar ya da kapatır"), ["<event:word> [bool]"]),
    "event": (N_("Varlığa olay tetikler"), ["entity <player> <event:word>"]),
    "tickingarea": (N_("Bir alanın sürekli yüklü (aktif) kalmasını sağlar"),
                    ["add <from:pos> <to:pos> [name:word] [preload:bool]",
                     "add circle <pos> <radius:int> [name:word] [preload:bool]",
                     "remove <name:word>", "remove_all", "list [all:word]", "preload <name:word> [preload:bool]"]),
    "schedule": (N_("Fonksiyonu ileri bir zamana planlar"), ["on_area_loaded add <from:pos> <to:pos> <function:word>",
                                                           "delay add <function:word> <time:word> [mode:word]"]),
    "loot": (N_("Ganimet tablosu düşürür ya da verir"), ["spawn <pos> loot <table:word>",
                                                         "give <player> loot <table:word>"]),
    "replaceitem": (N_("Yuvadaki eşyayı değiştirir"), ["entity <player> <slot:word> <int> <item> [count:int]"]),
    "recipe": (N_("Tarif verir ya da alır"), ["give <player> *", "take <player> *"]),
    "scriptevent": (N_("Betik olayı gönderir"), ["<name:word> <text>"]),
    "transfer": (N_("Oyuncuyu başka sunucuya aktarır"), ["<player> <host:word> <port:int>"]),
    "save": (N_("Yedek için kaydetmeyi yönetir"), ["hold", "query", "resume"]),
    "stop": (N_("Sunucuyu kaydedip kapatır"), [""]),
    "help": (N_("Komutları listeler"), ["[command:word]"]),
}

SPECS_BEDROCK = {n: (d, [_parse_variant(v) for v in vs]) for n, (d, vs) in COMMANDS_BEDROCK.items()}

GAMERULES_BEDROCK = ["commandblockoutput", "commandblocksenabled", "dodaylightcycle", "doentitydrops", "dofiretick",
                     "doimmediaterespawn", "doinsomnia", "dolimitedcrafting", "domobloot", "domobspawning",
                     "dotiledrops", "doweathercycle", "drowningdamage", "falldamage", "firedamage", "freezedamage",
                     "functioncommandlimit", "keepinventory", "maxcommandchainlength", "mobgriefing",
                     "naturalregeneration", "playerssleepingpercentage", "projectilescanbreakblocks", "pvp",
                     "randomtickspeed", "recipesunlock", "respawnblocksexplode", "sendcommandfeedback",
                     "showbordereffect", "showcoordinates", "showdaysplayed", "showdeathmessages",
                     "showrecipemessages", "showtags", "spawnradius", "tntexplodes", "tntexplosiondropdecay"]
LITERAL_SETS_BEDROCK = {
    "gamemode": ["survival", "creative", "adventure", "spectator", "default", "s", "c", "a", "d"],
    "difficulty": ["peaceful", "easy", "normal", "hard", "p", "e", "n", "h"],
    "dim": ["overworld", "nether", "the_end"],
    "structure": ["village", "ancient_city", "bastion_remnant", "buried_treasure", "end_city", "fortress",
                  "mansion", "mineshaft", "monument", "pillager_outpost", "ruined_portal", "shipwreck",
                  "stronghold", "temple", "trail_ruins", "trial_chambers"],
}
# Bedrock seçici filtreleri: ortak @a @p @r @e @s yanında @initiator ve sürüme özel filtreler
SELECTORS_BEDROCK = ["@a", "@p", "@r", "@e", "@s", "@initiator", "@a[tag=", "@e[type=", "@e[family=monster]",
                     "@a[hasitem={item=", "@a[haspermission={movement=enabled}]", "@e[has_property={",
                     "@a[m=survival]", "@a[l=", "@a[lm=", "@a[scores={", "@a[r=", "@e[c=1]"]
MOB_EVENTS = ["minecraft:pillager_patrols_event", "minecraft:wandering_trader_event", "events_enabled"]
ABILITIES = ["mayfly", "mute", "worldbuilder"]
