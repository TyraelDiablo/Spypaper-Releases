"""Oyunculara giden Spypaper mesajları, oyuncunun kendi oyun dilinde.

Mesajlar düz metin olarak değil Minecraft'ın çeviri bileşeniyle gönderilir:
    {"translate": "spypaper.maint.kick", "fallback": "<panel dilinde metin>"}
Oyuncunun oyunu anahtarı kendi seçtiği dilin dosyasında arar. Dil dosyaları (assets/spypaper/lang/<dil>.json)
sunucunun Spypaper kaynak paketine girer: panelin 15 dili + Türkçe + Language Wizard'la yapılan diller. Oyuncunun
dili pakette yoksa Minecraft en_us'a düşer; paket hiç yüklenmemişse "fallback" (panel dili) görünür.

Paper/Purpur/Folia'da SpypaperMessages eklentisi kuruluysa uyarılar ve atma mesajları eklentiden gider: eklenti
oyuncunun oyun dilini bilir ve metni Spypaper'ın yazdığı plugins/SpypaperMessages/messages.tsv'den seçer; kaynak
paketi gerekmez. (Atma mesajında paket işe yaramaz: oyun, bağlantı kopunca sunucu paketini bırakıp öyle gösterir.)
Eklenti yoksa uyarılar tellraw + çeviri anahtarıyla, atma panel dili + İngilizce olarak gider.
Eklenti oyuncuların oyun dilini de konsola yazar: "[SpypaperMessages] locale <ad> <dil>".
"""
import json
import os
import re
import shutil

from .config import N_

JAR = "SpypaperMessages.jar"
RE_LOCALE = re.compile(r"\[SpypaperMessages\] locale (\w{1,16}) ([A-Za-z_]+)")

# anahtar -> Türkçe kaynak metin (panel çevirileri bu metinlerle eşleşir)
MESSAGES = {
    "guard.op_kick": N_("İzinsiz yönetici yetkisi algılandı."),
    "guard.verify_kick": N_("Doğrulama başarısız: sunucunun kaynak paketi indirilmedi. Paketi kabul edip tekrar bağlan."),
    "maint.kick": N_("Sunucu bakımda. Lütfen daha sonra tekrar dene."),
    "maint.warn.600": N_("Sunucu 10 dakika içinde bakıma girecek."),
    "maint.warn.300": N_("Sunucu 5 dakika içinde bakıma girecek."),
    "maint.warn.60": N_("Sunucu 1 dakika içinde bakıma girecek."),
    "maint.warn.10": N_("Sunucu 10 saniye içinde bakıma girecek!"),
    "restart.warn.600": N_("Sunucu 10 dakika içinde yeniden başlatılacak."),
    "restart.warn.300": N_("Sunucu 5 dakika içinde yeniden başlatılacak."),
    "restart.warn.60": N_("Sunucu 1 dakika içinde yeniden başlatılacak."),
    "restart.warn.10": N_("Sunucu 10 saniye içinde yeniden başlatılıyor!"),
    "stop.warn.600": N_("Sunucu 10 dakika içinde kapanacak."),
    "stop.warn.300": N_("Sunucu 5 dakika içinde kapanacak."),
    "stop.warn.60": N_("Sunucu 1 dakika içinde kapanacak."),
    "stop.warn.10": N_("Sunucu 10 saniye içinde kapanıyor!"),
}
KEY_OF = {v: k for k, v in MESSAGES.items()}

# panel dil kodu -> Minecraft dil dosyası adları (aynı çeviri birkaç bölgeye de yazılır)
MC_FILES = {
    "tr": ["tr_tr"], "en": ["en_us", "en_gb", "en_ca", "en_au", "en_nz"], "de": ["de_de", "de_at", "de_ch"],
    "fr": ["fr_fr", "fr_ca"], "es": ["es_es", "es_mx", "es_ar", "es_cl", "es_ec", "es_uy", "es_ve"],
    "pt_BR": ["pt_br", "pt_pt"], "it": ["it_it"], "nl": ["nl_nl", "nl_be"], "pl": ["pl_pl"], "ru": ["ru_ru"],
    "uk": ["uk_ua"], "az": ["az_az"], "ja": ["ja_jp"], "ko": ["ko_kr"], "zh_CN": ["zh_cn"], "ar": ["ar_sa"],
}


def key(text):
    k = KEY_OF.get(text)
    return f"spypaper.{k}" if k else None


def tellraw(text, tr, prefix=True):
    """`tellraw @a` gövdesi. Bilinen metinler çeviri anahtarıyla, diğerleri düz metin."""
    k = key(text)
    body = {"translate": k, "fallback": tr(text)} if k else {"text": tr(text)}
    body["color"] = "yellow"
    parts = [{"text": "[!] ", "color": "red", "bold": True}] if prefix else []
    return json.dumps(parts + [body], ensure_ascii=False)


def announce(server, text, tr):
    """Tüm oyunculara uyarı (geri sayım vb.). Eklenti varsa her oyuncuya kendi dilinde, yoksa çeviri anahtarıyla."""
    k = key(text)
    if k and plugin_installed(server.config.server_path):
        return server.try_send(f"spypaper-say {k} {tr(text)}")
    return server.try_send("tellraw @a " + tellraw(text, tr))


def plugin_installed(server_path):
    return os.path.exists(os.path.join(server_path, "plugins", JAR))


def kick(server, name, text, tr):
    """Oyuncuyu atar; eklenti varsa oyuncunun dilinde, yoksa panel dili (+ İngilizce)."""
    sp = server.config.server_path
    k = key(text)
    local = tr(text)
    if k and plugin_installed(sp):
        return server.try_send(f"spypaper-kick {name} {k} {local}")
    english = _english().get(text, "")
    msg = local if not english or english == local else f"{local} / {english}"
    return server.try_send(f"kick {name} {msg}")


def _src_plugin():
    from .config import resource_dir
    for base in (os.path.join(resource_dir(), "ui", "assets", "plugins"),
                 os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "assets", "plugins")):
        p = os.path.join(base, JAR)
        if os.path.exists(p):
            return p
    return None


def refresh_plugin(server_path):
    """Kurulu eklenti Spypaper'la gelen sürümden farklıysa günceller (sunucu kapalıyken çağrılmalı)."""
    dst = os.path.join(server_path, "plugins", JAR)
    src = _src_plugin()
    if not src or not os.path.exists(dst):
        return False
    with open(src, "rb") as a, open(dst, "rb") as b:
        if a.read() == b.read():
            return False
    shutil.copyfile(src, dst)
    return True


def set_plugin(server_path, on):
    dst = os.path.join(server_path, "plugins", JAR)
    if on:
        src = _src_plugin()
        if not src:
            raise FileNotFoundError(JAR)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        write_plugin_texts(server_path)
    elif os.path.exists(dst):
        os.remove(dst)


def _locale_tables():
    """{panel_kodu: {türkçe: çeviri}} — yerleşik diller + Languages/ klasöründekiler."""
    from .config import get_base_dir, resource_dir
    out = {"tr": {}}
    for d in (os.path.join(resource_dir(), "locales"), os.path.join(get_base_dir(), "Languages")):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".json") or f.startswith("_"):
                continue
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                continue
            out.setdefault(f[:-5], {}).update({k: v for k, v in data.items() if v and not k.startswith("_")})
    return out


def _english():
    return _locale_tables().get("en", {})


def by_locale():
    """{minecraft_dil_kodu: {"spypaper.<anahtar>": metin}} — yerleşik diller ve Language Wizard dilleri."""
    tables = _locale_tables()
    en = tables.get("en", {})
    out = {}
    for code, table in tables.items():
        data = {}
        for k, tr_text in MESSAGES.items():
            v = tr_text if code == "tr" else (table.get(tr_text) or en.get(tr_text))
            if v:
                data[f"spypaper.{k}"] = v
        for n in MC_FILES.get(code) or [code.lower()]:
            if not re.fullmatch(r"[a-z]{2,3}(_[a-z0-9]{2,4})?", n):
                continue
            if code in MC_FILES:                       # yerleşik dil bölgeleri; Language Wizard dili (ör. de_AT) üstün
                out.setdefault(n, data)
            else:
                out[n] = data
    return out


def lang_files():
    """Kaynak paketine girecek dil dosyaları: {arşiv_yolu: json_metni} (tellraw uyarıları için)."""
    return {f"assets/spypaper/lang/{n}.json": json.dumps(d, ensure_ascii=False, indent=1) for n, d in by_locale().items()}


def write_plugin_texts(server_path):
    """Eklentinin okuduğu plugins/SpypaperMessages/messages.tsv: dil<TAB>anahtar<TAB>metin."""
    d = os.path.join(server_path, "plugins", "SpypaperMessages")
    os.makedirs(d, exist_ok=True)
    lines = [f"{loc}\t{k}\t{v.replace(chr(10), ' ').replace(chr(9), ' ')}"
             for loc, data in sorted(by_locale().items()) for k, v in data.items()]
    tmp = os.path.join(d, "messages.tsv.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, os.path.join(d, "messages.tsv"))


def parse_locale(line):
    """Eklentinin yazdığı satırdan (ad, dil) ya da None."""
    m = RE_LOCALE.search(line)
    return (m.group(1), m.group(2).lower()) if m else None
