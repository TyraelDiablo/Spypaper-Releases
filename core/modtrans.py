"""Mod ve eklenti dil dosyaları: jar'ların içindeki İngilizce dil dosyalarını bulur, çeviriyi elle yapmak
için yan yana açar ve kaydedilen çeviriyi jar'ın içine hedef dil dosyası olarak yazar.

Bulunan düzenler (yol moddan moda değişir, hepsi otomatik aranır):
  assets/<ns>/lang/en_us.json        Minecraft modları (Fabric/Forge/NeoForge)   -> tr_tr.json
  lang/en.yml, messages/en_US.json   eklentiler                                   -> tr.yml, tr_TR.json
  locales/locale.json (+locale_xx)   SkinsRestorer gibi                           -> locale_tr.json
  messages_en.yml, lang_en_us.json   önekli adlar                                 -> messages_tr.yml
Biçimler: JSON ve YAML; düz ya da iç içe (iç içe anahtarlar "a.b.c" olarak gösterilir).

* Eklentiler (Paper/Spigot) dil dosyalarını ilk açılışta plugins/<Eklenti>/ altına çıkarır ve oradan okur.
  O klasör varsa çeviri oraya da yazılır; mevcut çeviri de önce oradan okunur.
* Orijinal jar ilk değişiklikten önce bir kez backups/mods/orijinal/ içine yedeklenir.
* Biçim kodları (%s, %1$s, %player%, §a, &c, <red>, {0}, \\n…) İngilizce ile aynı mı diye denetlenir.
"""
import json
import os
import re
import shutil
import zipfile
from collections import Counter
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:          # PyYAML yoksa YAML dosyaları atlanır
    yaml = None

MC_LANG_RE = re.compile(r"^assets/([^/]+)/lang/(en_us)\.json$", re.I)
EXTS = (".json", ".yml", ".yaml")
LANG_DIR_RE = re.compile(r"(^|/)(lang|langs|language|languages|locale|locales|messages|i18n|translations?|l10n)(/|$)", re.I)
EN_STEM_RE = re.compile(r"^en([_-](us|gb))?$", re.I)               # en, en_us, en_US, en-US
EN_SUFFIX_RE = re.compile(r"^(.+?)[_-](en(?:[_-](?:us|gb))?)$", re.I)  # messages_en, lang_en_US
BASE_STEMS = {"locale", "messages", "message", "lang", "language", "strings", "translations"}
TOKEN = re.compile(
    r"%[A-Za-z_][A-Za-z0-9_.-]*%"                      # %player%, %time%  (eklenti yer tutucuları)
    r"|%(?:\d+\$)?[-#+ 0,(]*\d*(?:\.\d+)?[sdfxXc%]"    # %s, %1$s, %d
    r"|[§&][0-9a-fk-orx]"                              # §a, &c renk kodları
    r"|<[a-z_#:0-9/!.-]+>"                             # <red>, </bold>, <#ff0000> (MiniMessage)
    r"|\{[^{}]*\}"                                     # {0}, {player}
    r"|\n", re.I)


@dataclass
class LangFile:
    en: str            # jar içindeki İngilizce dosya yolu
    tgt: str           # jar içindeki hedef dosya yolu
    fmt: str           # "json" | "yaml"
    mc: bool           # Minecraft dil dosyası mı (boş satırlar yazılmaz, oyun İngilizceye düşer)
    label: str         # arayüzde gösterilen kısa ad


@dataclass
class ModInfo:
    path: str
    name: str
    files: list = field(default_factory=list)      # [LangFile]
    total: int = 0
    missing: int = 0
    error: str = ""
    plugin: str = ""                               # eklentiyse plugin.yml'deki ad (veri klasörü için)

    @property
    def jar(self):
        return os.path.basename(self.path)


# ------------------------------------------------------------------ yardımcılar
def short_code(lang):
    """tr_tr -> tr, pt_br -> pt_br, zh_cn -> zh_cn (iki harf belirsizse tam kalır)."""
    a, _, b = lang.partition("_")
    return lang if a in ("pt", "zh") else a


def _styled(code, like):
    """Hedef kodunu İngilizce adın yazımına uydurur: en_US -> tr_TR, en-us -> tr-tr, en -> tr."""
    if not like or len(like) == 2:
        return short_code(code)
    sep = like[2] if len(like) > 2 else "_"
    a, _, b = code.partition("_")
    b = b or a
    return f"{a}{sep}{b.upper() if like[3:].isupper() else b}"


def target_for(path, lang, siblings):
    """İngilizce dosyanın jar içindeki yolundan hedef dosya yolunu üretir; dil dosyası değilse None."""
    if MC_LANG_RE.match(path):
        base, fname = path.rsplit("/", 1)
        return f"{base}/{_styled(lang, fname[:5])}.json"
    folder, _, fname = path.rpartition("/")
    stem, ext = os.path.splitext(fname)
    if ext.lower() not in EXTS:
        return None
    pre = f"{folder}/" if folder else ""
    if EN_STEM_RE.match(stem) and (LANG_DIR_RE.search(folder + "/") or _has_lang_siblings(siblings, stem, ext)):
        return f"{pre}{_styled(lang, stem)}{ext}"
    m = EN_SUFFIX_RE.match(stem)
    if m and m.group(1).lower() in BASE_STEMS | {"lang", "messages"} or (m and LANG_DIR_RE.search(folder + "/")):
        sep = stem[len(m.group(1))]
        return f"{pre}{m.group(1)}{sep}{_styled(lang, m.group(2))}{ext}"
    if stem.lower() in BASE_STEMS:
        # locale.json + locale_de.json, locale_pt_BR.json … -> locale_tr.json
        sib = [s for s in siblings if s.lower().startswith(stem.lower() + "_") and s.endswith(ext)]
        if sib:
            codes = [os.path.splitext(s)[0][len(stem) + 1:] for s in sib]
            like = next((c for c in codes if len(c) == 2), None) or codes[0]
            return f"{pre}{stem}_{_styled(lang, like)}{ext}"
    return None


def _has_lang_siblings(siblings, stem, ext):
    """Aynı klasörde de.yml, fr_FR.json gibi başka dil dosyaları var mı?"""
    rx = re.compile(r"^[a-z]{2}([_-][a-z]{2})?" + re.escape(ext) + "$", re.I)
    return sum(1 for s in siblings if rx.match(s) and not s.lower().startswith("en")) >= 1


def _mod_name(z, fallback):
    names = set(z.namelist())
    try:
        if "fabric.mod.json" in names:
            return json.loads(z.read("fabric.mod.json").decode("utf-8", "ignore")).get("name") or fallback, ""
        if "quilt.mod.json" in names:
            q = json.loads(z.read("quilt.mod.json"))
            return q.get("quilt_loader", {}).get("metadata", {}).get("name") or fallback, ""
        for toml in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
            if toml in names:
                m = re.search(r'displayName\s*=\s*"([^"]+)"', z.read(toml).decode("utf-8", "ignore"))
                if m:
                    return m.group(1), ""
        for yml in ("paper-plugin.yml", "plugin.yml", "bungee.yml"):
            if yml in names:
                m = re.search(r"^name:\s*['\"]?([^'\"\r\n]+)", z.read(yml).decode("utf-8", "ignore"), re.M)
                if m:
                    return m.group(1).strip(), m.group(1).strip()
    except Exception:
        pass
    return fallback, ""


def _parse(raw, fmt):
    raw = raw.decode("utf-8-sig", "ignore") if isinstance(raw, bytes) else raw
    if fmt == "yaml":
        return yaml.safe_load(raw) or {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw = re.sub(r"(?m)^\s*//[^\n]*", "", raw)       # bazı modlar yorum / sondaki virgül içerir
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)


def flatten(d, prefix=""):
    """İç içe sözlük -> {"a.b": "metin"}. Metin listeleri tek metne (satır sonlarıyla) çevrilir."""
    out = {}
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, str):
            out[key] = v
        elif isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            out[key] = "\n".join(v)
    return out


def _set_path(root, en_root, key, value):
    """flatten'ın tersi: anahtarı İngilizce yapıdaki yola göre yazar (liste ise satırlara böler)."""
    parts, node, en_node = _split_key(en_root, key), root, en_root
    for p in parts[:-1]:
        en_node = en_node.get(p, {}) if isinstance(en_node, dict) else {}
        node = node.setdefault(p, {})
    last = parts[-1]
    en_val = en_node.get(last) if isinstance(en_node, dict) else None
    node[last] = value.split("\n") if isinstance(en_val, list) else value


def _split_key(en_root, key):
    """'a.b.c' anahtarını İngilizce yapıdaki gerçek parçalara böler (anahtarın kendisi nokta içerebilir)."""
    if isinstance(en_root, dict) and key in en_root:
        return [key]
    parts, node, rest = [], en_root, key
    while rest:
        if isinstance(node, dict) and rest in node:
            parts.append(rest)
            break
        for k in sorted(node.keys() if isinstance(node, dict) else [], key=len, reverse=True):
            if rest.startswith(str(k) + "."):
                parts.append(k)
                node, rest = node[k], rest[len(str(k)) + 1:]
                break
        else:
            parts.append(rest)
            break
    return parts


def _dump(data, fmt):
    if fmt == "yaml":
        return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000).encode("utf-8")
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _data_dir(info, lf):
    """Eklentinin plugins/<Ad>/ altına çıkardığı kopyanın klasörü (varsa)."""
    if not info.plugin:
        return None
    base = os.path.join(os.path.dirname(info.path), info.plugin)
    folder = os.path.dirname(lf.en)
    d = os.path.join(base, *folder.split("/")) if folder else base
    return d if os.path.isdir(d) else None


# ------------------------------------------------------------------ tarama / okuma / yazma
def scan(folders, lang):
    """Klasör(ler)deki jar'ları tarar -> [ModInfo] (dil dosyası olmayanlar atlanır).
    folders: tek klasör ya da klasör listesi (ör. [mods, plugins])."""
    if isinstance(folders, str):
        folders = [folders]
    mods, seen = [], set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for fn in sorted(os.listdir(folder), key=str.lower):
            p = os.path.join(folder, fn)
            if not fn.lower().endswith(".jar") or p in seen:
                continue
            seen.add(p)
            info = ModInfo(p, fn[:-4])
            try:
                with zipfile.ZipFile(p) as z:
                    names = [n for n in z.namelist() if not n.endswith("/") and not n.startswith("META-INF/")]
                    info.name, info.plugin = _mod_name(z, fn[:-4])
                    by_dir = {}
                    for n in names:
                        d, _, f = n.rpartition("/")
                        by_dir.setdefault(d, []).append(f)
                    nameset = set(names)
                    for n in sorted(names):
                        d, _, f = n.rpartition("/")
                        tgt = target_for(n, lang, by_dir.get(d, []))
                        if not tgt or tgt == n:
                            continue
                        fmt = "yaml" if n.lower().endswith((".yml", ".yaml")) else "json"
                        if fmt == "yaml" and yaml is None:
                            continue
                        try:
                            en = flatten(_parse(z.read(n), fmt))
                        except Exception:
                            continue
                        if len(en) < 2:                   # dil dosyası değil (ör. tek ayarlı yapılandırma)
                            continue
                        mc = bool(MC_LANG_RE.match(n))
                        label = n.split("/")[1] if mc else n
                        lf = LangFile(n, tgt, fmt, mc, label)
                        info.files.append(lf)
                        have = _load_target(info, lf, z, nameset)
                        info.total += len(en)
                        info.missing += sum(1 for k, v in en.items() if v and not have.get(k))   # boş İngilizce satır eksik sayılmaz
            except Exception as e:
                info.error = str(e)
            if info.files or info.error:
                mods.append(info)
    return mods


def _load_target(info, lf, z, nameset):
    dd = _data_dir(info, lf)
    if dd:
        f = os.path.join(dd, lf.tgt.rsplit("/", 1)[-1])
        if os.path.exists(f):
            try:
                with open(f, "rb") as fh:
                    return flatten(_parse(fh.read(), lf.fmt))
            except Exception:
                pass
    if lf.tgt in nameset:
        try:
            return flatten(_parse(z.read(lf.tgt), lf.fmt))
        except Exception:
            return {}
    return {}


def load(info, index=0):
    """(en, hedef) düz sözlükleri. Hedef dosya yoksa boş sözlük."""
    lf = info.files[index]
    with zipfile.ZipFile(info.path) as z:
        en = flatten(_parse(z.read(lf.en), lf.fmt))
        have = _load_target(info, lf, z, set(z.namelist()))
    return en, have


def tokens_ok(en_text, tr_text):
    """Çeviride biçim kodları İngilizce ile aynı mı? (sıra önemli değil)"""
    if not tr_text:
        return True
    return Counter(t.lower() for t in TOKEN.findall(en_text)) == Counter(t.lower() for t in TOKEN.findall(tr_text))


def _backup_dir(info):
    return os.path.join(os.path.dirname(os.path.dirname(info.path)), "backups", "mods", "orijinal")


def _backup(info):
    bdir = _backup_dir(info)
    os.makedirs(bdir, exist_ok=True)
    bkp = os.path.join(bdir, info.jar)
    if not os.path.exists(bkp):
        shutil.copy2(info.path, bkp)
    return bkp


def build(info, index, translations, en=None):
    """Kaydedilecek dosyanın içeriği (bayt).
    Minecraft dil dosyalarında boş satırlar yazılmaz (oyun İngilizceyi gösterir);
    eklenti dosyalarında boş satırlara İngilizce yazılır, çünkü çoğu eklenti eksik anahtarda hata verir."""
    lf = info.files[index]
    with zipfile.ZipFile(info.path) as z:
        en_root = _parse(z.read(lf.en), lf.fmt)
    if en is None:
        en = flatten(en_root)
    if lf.mc or not isinstance(en_root, dict) or all(isinstance(v, str) for v in en_root.values()):
        if lf.mc:
            out = {k: translations[k] for k in en if translations.get(k)}
            out.update({k: v for k, v in translations.items() if v and k not in en})
        else:
            out = {k: translations.get(k) or v for k, v in en.items()}
        return _dump(out, lf.fmt), sum(1 for k in en if translations.get(k))
    root = {}
    for k, v in en.items():
        _set_path(root, en_root, k, translations.get(k) or v)
    return _dump(root, lf.fmt), sum(1 for k in en if translations.get(k))


def save(info, index, translations, en=None):
    """Çeviriyi jar'ın içine (ve eklentinin veri klasörü varsa oraya da) yazar. Çevrilmiş satır sayısını döndürür."""
    lf = info.files[index]
    data, n = build(info, index, translations, en)
    _backup(info)
    tmp = info.path + ".tmp"
    with zipfile.ZipFile(info.path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename != lf.tgt:
                dst.writestr(item, src.read(item.filename))
        dst.writestr(lf.tgt, data)
    os.replace(tmp, info.path)
    dd = _data_dir(info, lf)
    if dd:
        f = os.path.join(dd, lf.tgt.rsplit("/", 1)[-1])
        if os.path.exists(f):
            bdir = os.path.join(_backup_dir(info), info.plugin)
            os.makedirs(bdir, exist_ok=True)
            if not os.path.exists(os.path.join(bdir, os.path.basename(f))):
                shutil.copy2(f, os.path.join(bdir, os.path.basename(f)))
        with open(f, "wb") as fh:
            fh.write(data)
    return n


def data_copy_path(info, index):
    """Eklentinin veri klasöründeki hedef dosya (yazılacaksa) ya da None."""
    lf = info.files[index]
    dd = _data_dir(info, lf)
    return os.path.join(dd, lf.tgt.rsplit("/", 1)[-1]) if dd else None


def export(info, index, folder, lang):
    """İngilizce ve mevcut hedef dosyayı <klasör>/<jar>/ altına çıkarır (düz JSON). Klasör yolunu döndürür."""
    lf = info.files[index]
    sub = lf.label.replace("/", "_")
    out = os.path.join(folder, info.jar[:-4], sub)
    os.makedirs(out, exist_ok=True)
    en, have = load(info, index)
    en_file = os.path.splitext(lf.en.rsplit("/", 1)[-1])[0] + ".json"
    with open(os.path.join(out, en_file), "w", encoding="utf-8") as f:
        json.dump(en, f, ensure_ascii=False, indent=2)
    tgt_file = os.path.join(out, os.path.splitext(lf.tgt.rsplit("/", 1)[-1])[0] + ".json")
    if not os.path.exists(tgt_file):                       # elle yapılmış çalışmanın üzerine yazma
        merged = {k: have.get(k, "") for k in en}
        with open(tgt_file, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
    return out


def read_translation_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    fmt = "yaml" if path.lower().endswith((".yml", ".yaml")) else "json"
    return flatten(_parse(raw, fmt))


def restore_original(info):
    bkp = os.path.join(_backup_dir(info), info.jar)
    if os.path.exists(bkp):
        shutil.copy2(bkp, info.path)
        return True
    return False
