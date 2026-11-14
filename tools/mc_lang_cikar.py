r"""Minecraft'ın kendi dil dosyalarını ve eşya ikonlarını (.minecraft) Translation/Icons klasörlerine çıkarır.

Minecraft dil dosyalarını iki yerde tutar:
  * en_us.json  -> versions\<sürüm>\<sürüm>.jar içinde (assets/minecraft/lang/en_us.json)
  * diğerleri   -> assets\objects\<xx>\<hash>   (adlar assets\indexes\<index>.json içinde)

Kullanım (SpypaperQt klasöründe):
    python tools\mc_lang_cikar.py                       # panelin 16 dili, en yeni sürüm
    python tools\mc_lang_cikar.py --hepsi               # Minecraft'taki tüm diller (~130)
    python tools\mc_lang_cikar.py --surum 1.21.4        # belirli sürüm
    python tools\mc_lang_cikar.py --mc "D:\.minecraft"  # farklı .minecraft yeri
    python tools\mc_lang_cikar.py --hedef "D:\Spypaper\dist\Translation"

Önce oyunu (istenen sürümü) launcher'dan en az bir kez açmış olman gerekir;
dil dosyaları ancak o zaman indirilir.
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PANEL_LANGS = ["tr_tr", "en_us", "de_de", "fr_fr", "es_es", "pt_br", "it_it", "nl_nl", "pl_pl",
               "ru_ru", "uk_ua", "az_az", "ja_jp", "ko_kr", "zh_cn", "ar_sa"]


def default_mc_dir():
    home = os.path.expanduser("~")
    for p in (os.path.join(os.environ.get("APPDATA", ""), ".minecraft"),
              os.path.join(home, "Library", "Application Support", "minecraft"),
              os.path.join(home, ".minecraft")):
        if p and os.path.isdir(p):
            return p
    return None


def _vkey(name):
    """'1.21.4' -> (1, 21, 4); sürüm olmayan adlar en sona."""
    nums = re.findall(r"\d+", name)
    return tuple(int(n) for n in nums) if re.match(r"^\d+\.\d+", name) else (0,)


def find_version(mc, wanted=None):
    """(sürüm_adı, jar_yolu, index_adı) — en yeni yayın sürümü ya da istenen."""
    vdir = os.path.join(mc, "versions")
    if not os.path.isdir(vdir):
        return None
    cands = []
    for v in os.listdir(vdir):
        js = os.path.join(vdir, v, f"{v}.json")
        jar = os.path.join(vdir, v, f"{v}.jar")
        if not (os.path.exists(js) and os.path.exists(jar)):
            continue
        try:
            meta = json.load(open(js, encoding="utf-8"))
        except Exception:
            continue
        if meta.get("inheritsFrom"):           # Fabric/Forge profilleri -> temel sürüm
            continue
        idx = (meta.get("assetIndex") or {}).get("id") or meta.get("assets")
        cands.append((v, jar, idx, meta.get("type", "")))
    if wanted:
        cands = [c for c in cands if c[0] == wanted]
    else:
        rel = [c for c in cands if c[3] == "release"]
        cands = rel or cands
    if not cands:
        return None
    v, jar, idx, _ = max(cands, key=lambda c: _vkey(c[0]))
    return v, jar, idx


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mc", help=".minecraft klasörü")
    ap.add_argument("--surum", help="Minecraft sürümü (örn. 1.21.4)")
    ap.add_argument("--hedef", default=os.path.join(ROOT, "Translation"), help="çıktı klasörü")
    ap.add_argument("--hepsi", action="store_true", help="tüm dilleri çıkar")
    ap.add_argument("--ikon-yok", action="store_true", help="eşya ikonlarını çıkarma")
    ap.add_argument("--ikon-hedef", default=None, help="ikon klasörü (varsayılan: hedefin yanında Icons)")
    a = ap.parse_args()

    mc = a.mc or default_mc_dir()
    if not mc or not os.path.isdir(mc):
        sys.exit("HATA: .minecraft klasörü bulunamadı. --mc ile yolunu ver.")
    found = find_version(mc, a.surum)
    if not found:
        sys.exit(f"HATA: {mc}\\versions içinde {'sürüm ' + a.surum if a.surum else 'kurulu sürüm'} bulunamadı. "
                 "Oyunu launcher'dan bir kez aç.")
    ver, jar, idx = found
    print(f".minecraft : {mc}\nSürüm      : {ver}  (asset index {idx})\nHedef      : {a.hedef}\n")
    os.makedirs(a.hedef, exist_ok=True)
    want = None if a.hepsi else set(PANEL_LANGS)
    done = []

    # 0) eşya/blok ikonları: sürüm jar'ındaki textures/item ve textures/block
    if not a.ikon_yok:
        icon_dir = a.ikon_hedef or os.path.join(os.path.dirname(os.path.abspath(a.hedef)), "Icons")
        n = 0
        with zipfile.ZipFile(jar) as z:
            for name in z.namelist():
                m = re.match(r"assets/minecraft/textures/(item|block)/([a-z0-9_]+)\.png$", name)
                if m:
                    d = os.path.join(icon_dir, m.group(1))
                    os.makedirs(d, exist_ok=True)
                    open(os.path.join(d, m.group(2) + ".png"), "wb").write(z.read(name))
                    n += 1
        print(f"{n} ikon çıkarıldı -> {icon_dir}")

    # 1) en_us: sürüm jar'ının içinden
    if want is None or "en_us" in want:
        try:
            with zipfile.ZipFile(jar) as z:
                data = z.read("assets/minecraft/lang/en_us.json")
            open(os.path.join(a.hedef, "en_us.json"), "wb").write(data)
            done.append("en_us")
        except Exception as e:
            print(f"  en_us çıkarılamadı: {e}")

    # 2) diğerleri: asset index -> objects/<hash>
    index = os.path.join(mc, "assets", "indexes", f"{idx}.json")
    if not os.path.exists(index):
        print(f"UYARI: {index} yok; sadece en_us çıkarıldı.")
    else:
        objects = json.load(open(index, encoding="utf-8")).get("objects", {})
        for name, info in sorted(objects.items()):
            m = re.match(r"minecraft/lang/([a-z0-9_]+)\.json$", name)
            if not m or (want is not None and m.group(1) not in want):
                continue
            h = info["hash"]
            src = os.path.join(mc, "assets", "objects", h[:2], h)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(a.hedef, f"{m.group(1)}.json"))
                done.append(m.group(1))
            else:
                print(f"  {m.group(1)}: nesne dosyası yok ({h[:8]}…)")

    print(f"{len(done)} dil çıkarıldı: {', '.join(sorted(done))}")
    if want:
        miss = sorted(want - set(done))
        if miss:
            print(f"Bu sürümde bulunamayanlar: {', '.join(miss)}")
    # kontrol
    p = os.path.join(a.hedef, "tr_tr.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        print(f"Kontrol: item.minecraft.diamond_sword = {d.get('item.minecraft.diamond_sword')!r}")


if __name__ == "__main__":
    main()
