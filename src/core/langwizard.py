"""Spypaper Language Wizard: kullanıcıların Spypaper arayüzünü kendi dillerine çevirmesi.

Çeviriler exe'nin yanındaki Languages/<dil>_<ÜLKE>.json dosyasına yazılır (ör. de_AT.json, pt_PT.json); bu
klasördeki dosyalar i18n tarafından okunur, yeni dil ☰ menüsündeki dil listesinde görünür. Dosya sade bir JSON'dur:
anahtar Spypaper'ın Türkçe kaynak metni, değer çeviri. VS Code gibi bir düzenleyicide de doldurulabilir.
Özel anahtarlar: "_name" (dilin kendi adıyla adı), "_code", "_source" (çevrilen dil: İngilizce).

Yapay zekâ ile çeviri Esplora'nın yapay zekâ ayarlarını (API anahtarı) kullanır: metinler numaralı bir JSON olarak
gönderilir, yanıt da aynı numaralarla JSON olarak beklenir. Yer tutucular ({n}, {name}…) ve satır sonları korunur;
bozulan çeviri kabul edilmez.
"""
import json
import os
import re

from .config import N_, get_base_dir, resource_dir

CODE_RE = re.compile(r"^[a-z]{2,3}(?:_[A-Z]{2}|_[A-Z][a-z]{3})?$")
PH_RE = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
BATCH = 40

# önerilen diller: kod, kendi adı, İngilizce adı (yapay zekâya söylenir)
SUGGESTED = [
    ("de_AT", "Deutsch (Österreich)", "German (Austria)"), ("de_CH", "Deutsch (Schweiz)", "Swiss German"),
    ("pt_PT", "Português (Portugal)", "European Portuguese"), ("es_MX", "Español (México)", "Mexican Spanish"),
    ("fr_CA", "Français (Canada)", "Canadian French"), ("en_GB", "English (UK)", "British English"),
    ("sv_SE", "Svenska", "Swedish"), ("nb_NO", "Norsk bokmål", "Norwegian Bokmål"), ("da_DK", "Dansk", "Danish"),
    ("fi_FI", "Suomi", "Finnish"), ("cs_CZ", "Čeština", "Czech"), ("sk_SK", "Slovenčina", "Slovak"),
    ("hu_HU", "Magyar", "Hungarian"), ("ro_RO", "Română", "Romanian"), ("bg_BG", "Български", "Bulgarian"),
    ("el_GR", "Ελληνικά", "Greek"), ("sr_RS", "Српски", "Serbian"), ("hr_HR", "Hrvatski", "Croatian"),
    ("lt_LT", "Lietuvių", "Lithuanian"), ("lv_LV", "Latviešu", "Latvian"), ("et_EE", "Eesti", "Estonian"),
    ("he_IL", "עברית", "Hebrew"), ("fa_IR", "فارسی", "Persian"), ("hi_IN", "हिन्दी", "Hindi"),
    ("id_ID", "Bahasa Indonesia", "Indonesian"), ("ms_MY", "Bahasa Melayu", "Malay"), ("th_TH", "ไทย", "Thai"),
    ("vi_VN", "Tiếng Việt", "Vietnamese"), ("zh_TW", "繁體中文", "Traditional Chinese"),
    ("kk_KZ", "Қазақ тілі", "Kazakh"), ("uz_UZ", "Oʻzbekcha", "Uzbek"), ("ka_GE", "ქართული", "Georgian"),
    ("ca_ES", "Català", "Catalan"), ("eu_ES", "Euskara", "Basque"), ("gl_ES", "Galego", "Galician"),
]


class WizardError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def folder():
    return os.path.join(get_base_dir(), "Languages")


def path_for(code):
    return os.path.join(folder(), f"{code}.json")


def valid_code(code):
    return bool(CODE_RE.match(code or ""))


def mc_code(code):
    """Spypaper kodu -> Minecraft dil dosyası adı (de_AT -> de_at, ja -> ja_jp)."""
    c = code.lower()
    if "_" in c:
        return c
    return {"ja": "ja_jp", "ko": "ko_kr", "uk": "uk_ua", "ar": "ar_sa", "az": "az_az", "en": "en_us"}.get(c, f"{c}_{c}")


def source():
    """[(anahtar, ingilizce)] — Spypaper'ın çevrilecek tüm metinleri, Türkçe kaynak sırasıyla."""
    with open(os.path.join(resource_dir(), "locales", "en.json"), encoding="utf-8") as f:
        en = json.load(f)
    return [(k, v or k) for k, v in en.items() if not k.startswith("_")]


def user_languages():
    """[(kod, ad)] Languages/ klasöründeki diller."""
    out = []
    d = folder()
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                code = f[:-5]
                try:
                    with open(os.path.join(d, f), encoding="utf-8") as fh:
                        name = json.load(fh).get("_name", code)
                except (OSError, ValueError):
                    name = code
                out.append((code, name))
    return out


def load(code):
    p = path_for(code)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        raise WizardError(N_("Dil dosyası bozuk (JSON hatası): {error}"), error=str(e))
    return data if isinstance(data, dict) else {}


def save(code, name, data):
    """Kaynak sırasıyla yazar (VS Code'da da düzenli görünsün); boş çeviriler "" olarak kalır."""
    if not valid_code(code):
        raise WizardError(N_("Dil kodu dil_ÜLKE biçiminde olmalı, ör. de_AT, pt_PT ya da yalnızca fi."))
    os.makedirs(folder(), exist_ok=True)
    out = {"_name": name or code, "_code": code, "_source": "en"}
    for k, _en in source():
        out[k] = data.get(k, "")
    p = path_for(code)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return p


def problem(src, text):
    """Çeviri kaynakla uyumlu mu? Sorun yoksa "", varsa çevrilecek uyarı şablonu."""
    if not text:
        return ""
    if set(PH_RE.findall(src)) != set(PH_RE.findall(text)):
        return N_("Yer tutucular ({…}) kaynaktakiyle aynı olmalı.")
    return ""


def progress(data):
    src = source()
    done = sum(1 for k, _ in src if data.get(k))
    return done, len(src)


def _prompt(lang_name):
    return (f"Translate every value of the JSON object into {lang_name}. Do not question anything, do not explain, "
            "do not add notes. This is the user interface of Spypaper, a Minecraft server management panel; use the "
            "usual Minecraft terms of that language. Keep {placeholders}, \\n line breaks, %s, URLs, file names, "
            "commands and emoji exactly as they are. Keep the same keys. Reply with the JSON object only.")


def _parse(reply):
    s = reply.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        raise WizardError(N_("Yapay zekâ yanıtı okunamadı."))
    return json.loads(s[i:j + 1])


def ai_translate(settings, lang_name, items, chat=None):
    """items: [(anahtar, ingilizce)] -> {anahtar: çeviri}. Yer tutucusu bozulanlar atlanır."""
    from . import ai
    chat = chat or (lambda system, msgs: ai.chat_auto(settings, system, msgs, max_tokens=8000, temperature=0.2)[0])
    out = {}
    for start in range(0, len(items), BATCH):
        part = items[start:start + BATCH]
        payload = {str(i): en for i, (_k, en) in enumerate(part)}
        reply = chat(_prompt(lang_name), [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        try:
            got = _parse(reply)
        except ValueError:
            raise WizardError(N_("Yapay zekâ yanıtı okunamadı."))
        for i, (k, en) in enumerate(part):
            v = got.get(str(i))
            if isinstance(v, str) and v.strip() and not problem(en, v):
                out[k] = v
        yield out, min(start + BATCH, len(items)), len(items)
