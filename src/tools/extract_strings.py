r"""Çevrilecek metinleri kaynak koddan toplar ve dil dosyalarını günceller.

Kullanım (SpypaperQt klasöründe):
    python tools\extract_strings.py            -> locales\_template.json + eksik raporu
    python tools\extract_strings.py --update   -> her locales\<dil>.json'a eksik anahtarları "" olarak ekler

Toplanan metinler:
  * t("..."), N_("...") çağrıları
  * label/button/Card/section/item/_toggle/StatCard/icon_button/info/warn/error/confirm/ask
    çağrılarına doğrudan verilen metinler
  * segmented([...]) / table([...]) listeleri
  * ServerError("...") şablonları
  * Sayfa sınıflarının  title = "..."  alanı
"""
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ["ui", "core"]
DIRECT = {"t", "N_", "label", "button", "Card", "section", "item", "_toggle", "StatCard", "UpdateError", "AIError",
          "info", "warn", "error", "confirm", "ServerError",
          "tr"}                                   # core'daki self.tr("...") (arayüz t ile değiştirir)
SECOND_ARG = {"icon_button": 1, "ask": (1, 2)}
LISTS = {"segmented", "table"}
TEXTY = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]")
SKIP = {"Spypaper", "server.properties", "Java", "Whitelist", "Discord", "TPS", "MSPT", "Ctrl+S"}   # çevrilmeyen özel adlar


def _name(f):
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def _const(n):
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def collect():
    keys = {}

    def add(s, where):
        if s and TEXTY.search(s) and s.strip() and s not in SKIP:
            keys.setdefault(s, where)

    for d in DIRS:
        for root, _, files in os.walk(os.path.join(ROOT, d)):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                rel = os.path.relpath(path, ROOT)
                tree = ast.parse(open(path, encoding="utf-8").read())
                for n in ast.walk(tree):
                    if isinstance(n, ast.Call):
                        name = _name(n.func)
                        if name in DIRECT and n.args:
                            add(_const(n.args[0]), f"{rel}:{n.lineno}")
                            if name in ("Card", "StatCard", "_toggle") and len(n.args) > 1:
                                add(_const(n.args[1]) if name != "_toggle" else _const(n.args[2]) if len(n.args) > 2 else None,
                                    f"{rel}:{n.lineno}")
                            for kw in n.keywords:
                                if kw.arg in ("tooltip", "title", "subtitle"):
                                    add(_const(kw.value), f"{rel}:{n.lineno}")
                        elif name in SECOND_ARG:
                            idx = SECOND_ARG[name]
                            for i in (idx if isinstance(idx, tuple) else (idx,)):
                                if len(n.args) > i:
                                    add(_const(n.args[i]), f"{rel}:{n.lineno}")
                        elif name in LISTS and n.args and isinstance(n.args[0], (ast.List, ast.Tuple)):
                            for e in n.args[0].elts:
                                add(_const(e), f"{rel}:{n.lineno}")
                        if name in ("button",):
                            for kw in n.keywords:
                                if kw.arg == "tooltip":
                                    add(_const(kw.value), f"{rel}:{n.lineno}")
                    elif isinstance(n, ast.ClassDef):
                        for st in n.body:
                            if (isinstance(st, ast.Assign) and len(st.targets) == 1
                                    and getattr(st.targets[0], "id", "") == "title"):
                                add(_const(st.value), f"{rel}:{st.lineno}")
                    elif isinstance(n, ast.FunctionDef) and n.name in ("info", "warn", "error", "confirm"):
                        for dflt in n.args.defaults:
                            add(_const(dflt), f"{rel}:{n.lineno}")
    return keys


def main():
    keys = collect()
    loc = os.path.join(ROOT, "locales")
    os.makedirs(loc, exist_ok=True)
    with open(os.path.join(loc, "_template.json"), "w", encoding="utf-8") as f:
        json.dump({"_name": "", **{k: "" for k in sorted(keys)}}, f, ensure_ascii=False, indent=2)
    print(f"{len(keys)} metin bulundu -> locales/_template.json")
    update = "--update" in sys.argv
    for fn in sorted(os.listdir(loc)):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        p = os.path.join(loc, fn)
        data = json.load(open(p, encoding="utf-8"))
        missing = [k for k in keys if not data.get(k)]
        unused = [k for k in data if not k.startswith("_") and k not in keys]
        print(f"  {fn:12} eksik: {len(missing):4}   kullanılmayan: {len(unused)}")
        if update and missing:
            for k in missing:
                data.setdefault(k, "")
            json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    if "--list" in sys.argv:
        for k, w in sorted(keys.items(), key=lambda x: x[1]):
            print(f"{w:32} {k!r}")


if __name__ == "__main__":
    main()
