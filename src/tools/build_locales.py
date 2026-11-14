r"""tools\translations\*.tsv  ->  locales\<dil>.json

Her satır:  türkçe_anahtar | en | de | ... (sütun sırası dosyanın ilk # satırında)
"\n" metin içinde satır sonu demektir. Yer tutucular ({n}, {name}...) anahtardakiyle aynı olmalı.

Kullanım:  python tools\build_locales.py
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

NAMES = {
    "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español", "pt_BR": "Português (Brasil)",
    "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "ru": "Русский", "uk": "Українська",
    "az": "Azərbaycanca", "ja": "日本語", "ko": "한국어", "zh_CN": "简体中文", "ar": "العربية",
}
PH = re.compile(r"\{[a-z_]+\}")


def main():
    tables, errors = {}, []
    for path in sorted(glob.glob(os.path.join(ROOT, "tools", "translations", "*.tsv"))):
        langs = None
        for no, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("#"):
                langs = [c.strip() for c in line[1:].split(" | ")][1:]
                continue
            cols = [c.strip().replace("\\n", "\n") for c in line.split(" | ")]
            where = f"{os.path.basename(path)}:{no}"
            if len(cols) != len(langs) + 1:
                errors.append(f"{where}: {len(cols)} sütun (beklenen {len(langs) + 1})")
                continue
            key = cols[0]
            want = sorted(PH.findall(key))
            for lang, val in zip(langs, cols[1:]):
                if sorted(PH.findall(val)) != want:
                    errors.append(f"{where} [{lang}]: yer tutucu uyuşmuyor {PH.findall(val)} != {want}")
                tables.setdefault(lang, {})[key] = val

    from extract_strings import collect
    keys = set(collect())
    out = os.path.join(ROOT, "locales")
    os.makedirs(out, exist_ok=True)
    for lang, tbl in tables.items():
        missing = sorted(keys - set(tbl))
        data = {"_name": NAMES.get(lang, lang)}
        data.update(dict(sorted(tbl.items())))
        with open(os.path.join(out, f"{lang}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"{lang:6} {len(tbl):4} metin   eksik: {len(missing)}" + (f"  {missing[:5]}" if missing else ""))
    for e in errors:
        print("HATA", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
