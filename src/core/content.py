"""İçerik editörü: mod gerektirmeden veri paketi + kaynak paketiyle oyuna içerik ekler (Minecraft 1.21+).

Türler
  painting  tablo           data/spypaper/painting_variant + doku (kaynak paketi)
  disc      müzik diski     data/spypaper/jukebox_song + .ogg ses (kaynak paketi)
  tool      alet / silah    var olan bir eşyanın hasar, hız, dayanıklılık, büyü değerleri değiştirilmiş hali
  food      yiyecek         besin, doygunluk, yeme süresi ve efektler
  hud       HUD             kalp, açlık, zırh, hava, hotbar, nişangah, XP çubuğu görselleri (yalnızca kaynak paketi)
Her içerik bir ganimet tablosu (data/spypaper/loot_table/<id>.json) olarak üretilir; "loot give <oyuncu> loot
spypaper:<id>" ile verilir. İsteğe bağlı 3x3 tarif (data/spypaper/recipe/<id>.json).
Yeni BLOK eklenemez (veri paketiyle mümkün değil).

Çıktılar
  <dünya>/datapacks/spypaper_content/        veri paketi (her üretimde baştan yazılır)
  <sunucu>/spypaper_resourcepack.zip         kaynak paketi (tablo resmi / müzik / doku varsa)
Kaynak dosyalar (resimler, sesler): <sunucu>/spypaper_content/

Sürüm farkları: 1.21.2'de öznitelik adlarından "generic." kalktı, tariflerde anahtar düz metin oldu, yiyecekte
"consumable" geldi; 1.21.4'te item_model; 1.21.5'te bileşen biçimleri sadeleşti (attribute_modifiers liste,
enchantments düz eşleme, jukebox_playable ve painting/variant düz metin).
"""
import hashlib
import io
import json
import os
import re
import shutil
import zipfile

from .config import N_

ID_RE = re.compile(r"^[a-z0-9_]{1,32}$")
ITEM_RE = re.compile(r"^(minecraft:)?[a-z0-9_]{1,64}$")
TYPES = {"painting": N_("Tablo"), "disc": N_("Müzik Diski"), "tool": N_("Alet / Silah"), "food": N_("Yiyecek"),
         "hud": N_("HUD")}
# HUD: kaynak paketinde assets/minecraft/textures/gui/sprites/hud/<ad>.png (1.20.2+ GUI sprite düzeni).
# ad -> (görünen ad, genişlik, yükseklik). Kendi resmin bu boyutun tam katı olarak kaydedilir (ör. 2x, 4x).
HUD_SPRITES = {
    "heart/full": (N_("Kalp (dolu)"), 9, 9), "heart/half": (N_("Kalp (yarım)"), 9, 9),
    "heart/container": (N_("Kalp (boş çerçeve)"), 9, 9),
    "heart/hardcore_full": (N_("Hardcore kalp (dolu)"), 9, 9), "heart/hardcore_half": (N_("Hardcore kalp (yarım)"), 9, 9),
    "heart/poisoned_full": (N_("Zehirli kalp (dolu)"), 9, 9), "heart/poisoned_half": (N_("Zehirli kalp (yarım)"), 9, 9),
    "heart/withered_full": (N_("Solmuş kalp (dolu)"), 9, 9), "heart/withered_half": (N_("Solmuş kalp (yarım)"), 9, 9),
    "heart/absorbing_full": (N_("Emilim kalbi (dolu)"), 9, 9), "heart/absorbing_half": (N_("Emilim kalbi (yarım)"), 9, 9),
    "heart/frozen_full": (N_("Donmuş kalp (dolu)"), 9, 9), "heart/frozen_half": (N_("Donmuş kalp (yarım)"), 9, 9),
    "food_full": (N_("Açlık (dolu)"), 9, 9), "food_half": (N_("Açlık (yarım)"), 9, 9),
    "food_empty": (N_("Açlık (boş)"), 9, 9),
    "armor_full": (N_("Zırh (dolu)"), 9, 9), "armor_half": (N_("Zırh (yarım)"), 9, 9),
    "armor_empty": (N_("Zırh (boş)"), 9, 9),
    "air": (N_("Hava baloncuğu"), 9, 9), "air_bursting": (N_("Hava baloncuğu (patlayan)"), 9, 9),
    "hotbar": (N_("Hotbar"), 182, 22), "hotbar_selection": (N_("Hotbar seçimi"), 24, 23),
    "hotbar_offhand_left": (N_("İkinci el yuvası (sol)"), 29, 24),
    "hotbar_offhand_right": (N_("İkinci el yuvası (sağ)"), 29, 24),
    "crosshair": (N_("Nişangah"), 15, 15),
    "experience_bar_background": (N_("XP çubuğu (arka plan)"), 182, 5),
    "experience_bar_progress": (N_("XP çubuğu (dolu kısım)"), 182, 5),
}
TOOL_BASES = ["diamond_sword", "netherite_sword", "iron_sword", "golden_sword", "stone_sword", "wooden_sword",
              "diamond_axe", "netherite_axe", "iron_axe", "diamond_pickaxe", "netherite_pickaxe", "iron_pickaxe",
              "diamond_shovel", "diamond_hoe", "mace", "trident", "bow", "crossbow", "stick", "blaze_rod"]
FOOD_BASES = ["apple", "golden_apple", "bread", "cookie", "cooked_beef", "cooked_porkchop", "baked_potato",
              "pumpkin_pie", "cake", "melon_slice", "sweet_berries", "honey_bottle", "carrot", "mushroom_stew"]
DISC_BASES = ["music_disc_13", "music_disc_cat", "music_disc_blocks", "music_disc_chirp", "music_disc_far",
              "music_disc_mall", "music_disc_mellohi", "music_disc_stal", "music_disc_strad", "music_disc_ward",
              "music_disc_wait", "music_disc_pigstep", "music_disc_otherside"]
COLORS = ["white", "yellow", "gold", "red", "dark_red", "light_purple", "dark_purple", "aqua", "dark_aqua",
          "green", "dark_green", "blue", "dark_blue", "gray", "dark_gray", "black"]
MIN_VERSION = (1, 21)


class ContentError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def vtuple(v):
    parts = [int(x) for x in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(parts) or (0,)


class Fmt:
    """Sunucu sürümüne göre biçim seçimleri."""

    def __init__(self, version):
        v = vtuple(version)
        self.version = v
        self.ok = v >= MIN_VERSION
        self.v1212 = v >= (1, 21, 2)
        self.v1214 = v >= (1, 21, 4)
        self.v1215 = v >= (1, 21, 5)

    def attr(self, name):
        return f"minecraft:{name}" if self.v1212 else {
            "attack_damage": "minecraft:generic.attack_damage", "attack_speed": "minecraft:generic.attack_speed",
            "mining_efficiency": "minecraft:player.mining_efficiency"}[name]


def mc(item):
    item = (item or "").strip().lower()
    return item if ":" in item else "minecraft:" + item


def _text(s, color=None):
    out = {"text": s, "italic": False}
    if color:
        out["color"] = color
    return out


# ---------------------------------------------------------------- doğrulama
def validate(c, fmt=None):
    if c.get("type") not in TYPES:
        raise ContentError(N_("Bilinmeyen içerik türü."))
    if not ID_RE.match(c.get("id", "")):
        raise ContentError(N_("Kimlik yalnızca küçük harf, rakam ve _ içerebilir (en fazla 32)."))
    if not (c.get("name") or "").strip():
        raise ContentError(N_("Bir ad yaz."))
    t = c["type"]
    if t == "painting":
        if not c.get("image"):
            raise ContentError(N_("Tablo için resim seç."))
        if not (1 <= int(c.get("width", 0)) <= 16 and 1 <= int(c.get("height", 0)) <= 16):
            raise ContentError(N_("Tablo boyutu 1-16 blok olmalı."))
    if t == "disc" and not c.get("sound"):
        raise ContentError(N_("Disk için müzik ekle (Newgrounds ID ya da ses dosyası)."))
    if t == "disc" and not c.get("rights_ok"):
        raise ContentError(N_("Bu diskin dağıtma onayı işaretlenmemiş. Ses dosyasını kullanma ve dağıtma hakkın olduğunu onayla."))
    if t == "hud":
        if c.get("sprite") not in HUD_SPRITES:
            raise ContentError(N_("Değiştirilecek HUD parçasını seç."))
        if not c.get("image"):
            raise ContentError(N_("HUD parçası için resim seç."))
    if t in ("tool", "food") and not ITEM_RE.match(c.get("base", "")):
        raise ContentError(N_("Geçersiz temel eşya."))
    if t == "food" and fmt and not fmt.v1212:
        raise ContentError(N_("Yiyecekler için sunucu en az Minecraft {v} olmalı."), v="1.21.2")
    rec = c.get("recipe") or {}
    if rec.get("enabled"):
        grid = rec.get("grid") or []
        if len(grid) != 9 or not any(grid):
            raise ContentError(N_("Tarifte en az bir eşya olmalı."))
        for g in grid:
            if g and not ITEM_RE.match(g):
                raise ContentError(N_("Tarifte geçersiz eşya: {item}"), item=g)


# ---------------------------------------------------------------- bileşenler
def base_item(c):
    t = c["type"]
    if t == "painting":
        return "minecraft:painting"
    if t == "hud":
        return ""
    if t == "disc":
        return mc(c.get("base") or "music_disc_13")
    return mc(c["base"])


def components(c, fmt):
    comps = {"minecraft:item_name" if c["type"] in ("painting", "disc") else "minecraft:custom_name":
             _text(c["name"], c.get("color") or None)}
    lore = [l for l in (c.get("lore") or "").splitlines() if l.strip()][:8]
    if lore:
        comps["minecraft:lore"] = [_text(l, "gray") for l in lore]
    t = c["type"]
    if t == "painting":
        if fmt.v1215:
            comps["minecraft:painting/variant"] = f"spypaper:{c['id']}"
        else:
            comps["minecraft:entity_data"] = {"id": "minecraft:painting", "variant": f"spypaper:{c['id']}"}
    elif t == "disc":
        comps["minecraft:jukebox_playable"] = f"spypaper:{c['id']}" if fmt.v1215 else {"song": f"spypaper:{c['id']}"}
    elif t == "tool":
        mods = [
            {"type": fmt.attr("attack_damage"), "id": "minecraft:base_attack_damage",
             "amount": round(float(c.get("damage", 7)) - 1, 2), "operation": "add_value", "slot": "mainhand"},
            {"type": fmt.attr("attack_speed"), "id": "minecraft:base_attack_speed",
             "amount": round(float(c.get("speed", 1.6)) - 4, 2), "operation": "add_value", "slot": "mainhand"},
        ]
        if float(c.get("mining", 0) or 0) > 0:
            mods.append({"type": fmt.attr("mining_efficiency"), "id": f"spypaper:{c['id']}_mining",
                         "amount": float(c["mining"]), "operation": "add_value", "slot": "mainhand"})
        comps["minecraft:attribute_modifiers"] = mods if fmt.v1215 else {"modifiers": mods}
        if c.get("unbreakable"):
            comps["minecraft:unbreakable"] = {}
        elif int(c.get("durability", 0) or 0) > 0:
            comps["minecraft:max_damage"] = int(c["durability"])
        ench = {mc(e): min(255, int(lv)) for e, lv in (c.get("enchants") or []) if e and int(lv) > 0}
        if ench:
            comps["minecraft:enchantments"] = ench if fmt.v1215 else {"levels": ench}
        if c.get("glint"):
            comps["minecraft:enchantment_glint_override"] = True
    elif t == "food":
        comps["minecraft:food"] = {"nutrition": int(c.get("nutrition", 4)), "saturation": float(c.get("saturation", 2.4)),
                                   "can_always_eat": bool(c.get("always_eat"))}
        effects = [{"id": mc(e), "duration": int(sec) * 20, "amplifier": max(0, int(amp))}
                   for e, sec, amp in (c.get("effects") or []) if e and int(sec) > 0]
        comps["minecraft:consumable"] = {"consume_seconds": float(c.get("seconds", 1.6)),
                                         **({"on_consume_effects": [{"type": "minecraft:apply_effects",
                                                                     "effects": effects}]} if effects else {})}
    if c.get("texture") and t in ("tool", "food", "disc") and fmt.v1214:
        comps["minecraft:item_model"] = f"spypaper:{c['id']}"
    return comps


def loot_table(c, fmt):
    return {"pools": [{"rolls": 1, "entries": [{"type": "minecraft:item", "name": base_item(c), "functions": [
        {"function": "minecraft:set_components", "components": components(c, fmt)}]}]}]}


def recipe(c, fmt):
    rec = c.get("recipe") or {}
    grid = [(g or "").strip() for g in rec.get("grid", [""] * 9)]
    rows = [grid[0:3], grid[3:6], grid[6:9]]
    rows = [r for r in rows if any(r)]
    cols = [i for i in range(3) if any(r[i] for r in rows)]
    rows = [[r[i] for i in cols] for r in rows]
    letters, key = {}, {}
    for r in rows:
        for g in r:
            if g and g not in letters:
                letters[g] = "ABCDEFGHI"[len(letters)]
                key[letters[g]] = mc(g) if fmt.v1212 else {"item": mc(g)}
    pattern = ["".join(letters[g] if g else " " for g in r) for r in rows]
    return {"type": "minecraft:crafting_shaped", "category": "equipment" if c["type"] == "tool" else "misc",
            "pattern": pattern, "key": key,
            "result": {"id": base_item(c), "count": max(1, min(64, int(rec.get("count", 1)))),
                       "components": components(c, fmt)}}


_BARE = re.compile(r"[A-Za-z0-9._+\-]+")
TEXT_COMPONENTS = ("minecraft:item_name", "minecraft:custom_name")


def snbt(v):
    """JSON değerini /give komutundaki SNBT biçimine çevirir."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ",".join(snbt(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join((k if _BARE.fullmatch(k) else snbt(k)) + ":" + snbt(x) for k, x in v.items()) + "}"
    raise TypeError(type(v))


def give_command(player, c, version=None):
    """Oyuncuya eşyayı /give ile, bileşenleri komutun içinde vererek verir.
    loot give'daki set_components bazı sunucularda (ör. Paper 26.x) uygulanmıyor; eşya düz geliyordu.
    1.21.5'ten önce metin bileşenleri JSON metni olarak yazılır, sonra doğrudan SNBT."""
    fmt = Fmt(version) if version else Fmt("99")
    parts = []
    for key, val in components(c, fmt).items():
        if not fmt.v1215 and key in TEXT_COMPONENTS:
            val = json.dumps(val, ensure_ascii=False)
        elif not fmt.v1215 and key == "minecraft:lore":
            val = [json.dumps(x, ensure_ascii=False) for x in val]
        parts.append(f"{key}={snbt(val)}")
    return f"give {player} {base_item(c)}[{','.join(parts)}]"


# ---------------------------------------------------------------- paketler
def _mcmeta(description, fmt_num):
    # Doğru pack_format sürüme göre değişir; geniş aralık verilir ki yeni sürümler de kabul etsin.
    return {"pack": {"description": description, "pack_format": fmt_num,
                     "supported_formats": [fmt_num, 1000], "min_format": fmt_num, "max_format": 1000}}


def data_format(fmt):
    v = fmt.version
    return 71 if v >= (1, 21, 5) else 61 if v >= (1, 21, 4) else 57 if v >= (1, 21, 2) else 48


def resource_format(fmt):
    v = fmt.version
    return 55 if v >= (1, 21, 5) else 46 if v >= (1, 21, 4) else 42 if v >= (1, 21, 2) else 34


def content_dir(server_path):
    return os.path.join(server_path, "spypaper_content")


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build(server_path, level, version, items, extra_rp=None):
    """Veri paketini ve (gerekirse) kaynak paketini üretir. (veri_paketi_klasörü, kaynak_paketi_yolu ya da None).
    extra_rp: Spypaper Modları'ndan gelen kaynak paketi dosyaları (arşiv yolu -> bayt); içerikler bunların üstüne yazar."""
    fmt = Fmt(version)
    if not fmt.ok:
        raise ContentError(N_("İçerik editörü için sunucu en az Minecraft {v} olmalı."), v="1.21")
    if os.path.isabs(level) or ".." in level.replace("\\", "/").split("/"):
        raise ContentError(N_("level-name geçersiz: {name}"), name=level)
    for c in items:
        try:
            validate(c, fmt)
        except ContentError as e:
            e.item = c.get("name") or c.get("id")          # hangi içerikte sorun olduğu söylensin
            raise
    seen = {}
    for c in items:
        if c["type"] == "hud":
            if c["sprite"] in seen:
                e = ContentError(N_("Bu HUD parçası iki kez değiştirilmiş: {other}"), other=seen[c["sprite"]])
                e.item = c.get("name") or c.get("id")
                raise e
            seen[c["sprite"]] = c.get("name") or c["id"]
    dp = os.path.join(server_path, level, "datapacks", "spypaper_content")
    if os.path.isdir(dp):
        shutil.rmtree(dp)
    _write(os.path.join(dp, "pack.mcmeta"), _mcmeta("Spypaper içerikleri", data_format(fmt)))
    src = content_dir(server_path)
    rp_files = dict(extra_rp or {})
    sounds = {}
    placeable = []
    for c in items:
        i = c["id"]
        if c["type"] == "hud":                     # yalnızca kaynak paketi: Minecraft'ın kendi HUD görselinin yerine geçer
            rp_files[f"assets/minecraft/textures/gui/sprites/hud/{c['sprite']}.png"] = os.path.join(src, c["image"])
            continue
        _write(os.path.join(dp, "data", "spypaper", "loot_table", f"{i}.json"), loot_table(c, fmt))
        if (c.get("recipe") or {}).get("enabled"):
            _write(os.path.join(dp, "data", "spypaper", "recipe", f"{i}.json"), recipe(c, fmt))
        if c["type"] == "painting":
            _write(os.path.join(dp, "data", "spypaper", "painting_variant", f"{i}.json"), {
                "asset_id": f"spypaper:{i}", "width": int(c["width"]), "height": int(c["height"]),
                "title": _text(c["name"], "yellow"), "author": _text(c.get("author") or "Spypaper", "gray")})
            placeable.append(f"spypaper:{i}")
            rp_files[f"assets/spypaper/textures/painting/{i}.png"] = os.path.join(src, c["image"])
        elif c["type"] == "disc":
            desc = f"{c.get('artist')} - {c['name']}" if c.get("artist") else c["name"]
            _write(os.path.join(dp, "data", "spypaper", "jukebox_song", f"{i}.json"), {
                "sound_event": {"sound_id": f"spypaper:music_disc.{i}"}, "description": _text(desc),
                "length_in_seconds": max(1.0, float(c.get("length", 60))),
                "comparator_output": max(1, min(15, int(c.get("comparator", 1))))})
            sounds[f"music_disc.{i}"] = {"sounds": [{"name": f"spypaper:records/{i}", "stream": True}]}
            rp_files[f"assets/spypaper/sounds/records/{i}.ogg"] = os.path.join(src, c["sound"])
        if c.get("texture") and c["type"] in ("tool", "food", "disc") and fmt.v1214:
            rp_files[f"assets/spypaper/textures/item/{i}.png"] = os.path.join(src, c["texture"])
            if c.get("model") == "cube":          # 16×16×16 blok görünümü: aynı doku altı yüzde
                model = {"parent": "minecraft:block/cube_all", "textures": {"all": f"spypaper:item/{i}"}}
            else:
                parent = "minecraft:item/handheld" if c["type"] == "tool" else "minecraft:item/generated"
                model = {"parent": parent, "textures": {"layer0": f"spypaper:item/{i}"}}
            rp_files[f"assets/spypaper/models/item/{i}.json"] = json.dumps(model)
            rp_files[f"assets/spypaper/items/{i}.json"] = json.dumps(
                {"model": {"type": "minecraft:model", "model": f"spypaper:item/{i}"}})
    if placeable:
        _write(os.path.join(dp, "data", "minecraft", "tags", "painting_variant", "placeable.json"),
               {"replace": False, "values": placeable})
    rp = os.path.join(server_path, "spypaper_resourcepack.zip")
    if not rp_files:
        if os.path.exists(rp):
            os.remove(rp)
        return dp, None
    if sounds:
        rp_files["assets/spypaper/sounds.json"] = json.dumps(sounds, indent=2)
    rp_files["pack.mcmeta"] = json.dumps(_mcmeta("Spypaper içerikleri", resource_format(fmt)), indent=2)
    tmp = rp + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in sorted(rp_files.items()):
            if isinstance(data, str) and os.path.isabs(data):
                if not os.path.isfile(data):
                    raise ContentError(N_("Dosya bulunamadı: {path}"), path=os.path.basename(data))
                z.write(data, arc)
            else:
                z.writestr(arc, data)
    os.replace(tmp, rp)
    return dp, rp


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- ses
def to_ogg(data, dest, max_minutes=15):
    """MP3/WAV/FLAC/OGG baytlarını tek kanallı OGG Vorbis'e çevirir (disk sesi konumdan gelsin). Süre (sn)."""
    try:
        import numpy as np
        import soundfile as sf
    except ImportError:
        raise ContentError(N_("Ses dönüştürme için gereken bileşen (soundfile) bulunamadı."))
    try:
        audio, sr = sf.read(io.BytesIO(data), always_2d=True, dtype="float32")
    except Exception:
        raise ContentError(N_("Ses dosyası okunamadı (MP3, OGG, WAV ya da FLAC olmalı)."))
    frames = audio.shape[0]
    if not frames:
        raise ContentError(N_("Ses dosyası boş."))
    if frames / sr > max_minutes * 60:
        raise ContentError(N_("Parça çok uzun (en fazla {n} dakika)."), n=max_minutes)
    mono = audio.mean(axis=1)
    peak = float(np.abs(mono).max() or 1.0)
    if peak > 1.0:
        mono = mono / peak
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    # libsndfile uzun bir OGG'yi tek seferde yazarken çöküyor (segfault); parça parça yaz
    tmp = dest + ".part"
    with sf.SoundFile(tmp, "w", samplerate=sr, channels=1, format="OGG", subtype="VORBIS") as out:
        for i in range(0, frames, 16384):
            out.write(mono[i:i + 16384])
    os.replace(tmp, dest)
    return round(frames / sr, 1)
