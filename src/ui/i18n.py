"""Çok dil desteği.

Kaynak dil Türkçe; anahtar Türkçe metnin kendisidir (gettext tarzı):
    t("Oyuncular")                     -> "Players"
    t("{n} oyuncu", n=3)               -> "3 players"
Çeviriler: locales/<kod>.json (exe'ye gömülü).
Exe'nin yanındaki Languages/<kod>.json gömülü dosyanın üzerine yazar,
yeni dil eklemek için de oraya dosya koymak yeterli ("_name" anahtarı = dilin adı).
Eksik çeviri önce İngilizceye, o da yoksa Türkçe kaynağa düşer
(Türkçe bilmeyen biri yarım çeviride Türkçe değil İngilizce görsün).
"""
import json
import os

from core.config import get_base_dir, resource_dir

LANGUAGES = [
    ("tr", "Türkçe"), ("en", "English"), ("de", "Deutsch"), ("fr", "Français"),
    ("es", "Español"), ("pt_BR", "Português (Brasil)"), ("it", "Italiano"),
    ("nl", "Nederlands"), ("pl", "Polski"), ("ru", "Русский"), ("uk", "Українська"),
    ("az", "Azərbaycanca"), ("ja", "日本語"), ("ko", "한국어"), ("zh_CN", "简体中文"),
    ("ar", "العربية"),
]
RTL = {"ar", "he", "fa", "ur"}

_table = {}
_lang = "tr"


def _dirs():
    return [os.path.join(resource_dir(), "locales"), os.path.join(get_base_dir(), "Languages")]


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[i18n] {path}: {e}")
        return {}


def available():
    """[(kod, ad)] — yerleşik diller + Languages/ klasöründe bulunan ek diller."""
    langs = list(LANGUAGES)
    known = {c for c, _ in langs}
    ext = os.path.join(get_base_dir(), "Languages")
    if os.path.isdir(ext):
        for f in sorted(os.listdir(ext)):
            code = f[:-5]
            if f.endswith(".json") and code not in known:
                langs.append((code, _read(os.path.join(ext, f)).get("_name", code)))
    return langs


def load(lang):
    global _lang
    _lang = lang
    _table.clear()
    _table.update(table_for(lang))


def table_for(lang):
    """Bir dilin çeviri tablosu (eksikler İngilizceden). Türkçe için boş tablo."""
    out = {}
    if lang == "tr":
        return out
    for code in (("en", lang) if lang != "en" else ("en",)):
        for d in _dirs():
            p = os.path.join(d, f"{code}.json")
            if os.path.exists(p):
                out.update({k: v for k, v in _read(p).items() if v and not k.startswith("_")})
    return out


def current():
    return _lang


def is_rtl():
    return _lang in RTL


def t(text, **kw):
    out = _table.get(text, text)
    if kw:
        try:
            return out.format(**kw)
        except (KeyError, IndexError, ValueError):
            return text.format(**kw)
    return out
