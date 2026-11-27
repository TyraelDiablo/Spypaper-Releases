"""Bedrock server.properties: BDS dosyasındaki açıklamalardan (yorum satırları, "Allowed values") ayar formu üretir.

Her anahtarın türü dosyadaki "Allowed values" satırından çıkarılır: "true"/"false" -> bool, tırnaklı liste -> seçim,
"Integers in the range [a, b]" / "integer" -> sayı, diğerleri metin. Bilinen anahtarlar için Türkçe (ve çevrilebilir)
ad ve açıklama vardır; bilinmeyenlerde dosyadaki İngilizce açıklama gösterilir.
"""
import os
import re

from .config import N_

GROUPS = [
    ("general", N_("Genel"), ["server-name", "gamemode", "force-gamemode", "difficulty", "allow-cheats", "max-players",
                              "default-player-permission-level", "level-name", "level-seed"]),
    ("network", N_("Bağlantı"), ["online-mode", "allow-list", "server-port", "server-portv6", "enable-lan-visibility",
                                 "player-idle-timeout", "transport"]),
    ("perf", N_("Performans"), ["view-distance", "tick-distance", "max-threads", "compression-threshold",
                                "compression-algorithm", "client-side-chunk-generation-enabled"]),
    ("players", N_("Oyuncular ve İçerik"), ["texturepack-required", "chat-restriction", "disable-player-interaction",
                                            "disable-custom-skins", "disable-persona", "content-log-file-enabled",
                                            "content-log-console-output-enabled", "content-log-level"]),
    ("security", N_("Hile Önleme (sunucu denetimi)"), [
        "server-authoritative-movement-strict", "server-authoritative-dismount-strict",
        "server-authoritative-entity-interactions-strict", "server-authoritative-entity-attack-request-validation",
        "server-authoritative-entity-attack-range-validation", "server-authoritative-entity-attack-range-tolerance",
        "player-position-acceptance-threshold", "player-movement-action-direction-threshold",
        "server-authoritative-block-breaking-pick-range-scalar", "server-build-radius-ratio"]),
]

KNOWN = {
    "server-name": (N_("Sunucu adı"), N_("Oyuncuların sunucu listesinde gördüğü ad.")),
    "gamemode": (N_("Oyun modu"), N_("Yeni oyuncuların oyun modu.")),
    "force-gamemode": (N_("Oyun modunu zorla"), N_("Açıksa oyuncular her girişte yukarıdaki oyun moduna döner.")),
    "difficulty": (N_("Zorluk"), N_("Dünyanın zorluğu.")),
    "allow-cheats": (N_("Hilelere izin ver"), N_("Açıksa operatörler hile komutlarını kullanabilir.")),
    "max-players": (N_("En fazla oyuncu"), N_("Aynı anda girebilecek oyuncu sayısı.")),
    "default-player-permission-level": (N_("Yeni oyuncu yetkisi"),
                                        N_("İlk kez giren oyuncunun yetkisi: ziyaretçi, üye ya da operatör.")),
    "level-name": (N_("Dünya adı"), N_("worlds klasöründeki dünyanın adı. Değiştirirsen yeni bir dünya açılır.")),
    "level-seed": (N_("Seed"), N_("Yeni dünya oluşturulurken kullanılır; boşsa rastgele.")),
    "online-mode": (N_("Xbox girişi zorunlu"), N_("Açıksa oyuncular Microsoft/Xbox hesabıyla doğrulanır.")),
    "allow-list": (N_("İzin listesi"), N_("Açıksa yalnızca allowlist.json'daki oyuncular girebilir.")),
    "server-port": (N_("Port (IPv4)"), N_("UDP port; varsayılan 19132.")),
    "server-portv6": (N_("Port (IPv6)"), N_("UDP port; varsayılan 19133.")),
    "enable-lan-visibility": (N_("Yerel ağda görünsün"), N_("Açıksa aynı ağdaki oyuncular sunucuyu Arkadaşlar sekmesinde görür.")),
    "player-idle-timeout": (N_("Hareketsizlik süresi (dk)"),
                            N_("Bu kadar dakika hareketsiz kalan oyuncu atılır; 0 kapatır.")),
    "transport": (N_("Bağlantı altyapısı"), N_("Gelişmiş: raknet ya da nethernet. Emin değilsen değiştirme.")),
    "view-distance": (N_("Görüş mesafesi"), N_("Oyunculara gönderilen en fazla chunk uzaklığı (en az 5).")),
    "tick-distance": (N_("Etkin alan mesafesi"), N_("Oyuncunun çevresinde dünyanın işlemeye devam ettiği chunk uzaklığı (4–12).")),
    "max-threads": (N_("En fazla iş parçacığı"), N_("Sunucunun kullanacağı en fazla iş parçacığı; 0 sınırsız.")),
    "compression-threshold": (N_("Sıkıştırma eşiği"), N_("Bu boyuttan büyük ağ paketleri sıkıştırılır (bayt).")),
    "compression-algorithm": (N_("Sıkıştırma yöntemi"), N_("Ağ paketlerinin sıkıştırma algoritması.")),
    "client-side-chunk-generation-enabled": (N_("Chunk'ları oyuncu da üretsin"),
                                             N_("Açıksa oyuncunun cihazı da chunk üretir; sunucu yükü azalır.")),
    "texturepack-required": (N_("Kaynak paketi zorunlu"), N_("Açıksa oyuncular sunucunun kaynak paketlerini indirmek zorundadır.")),
    "chat-restriction": (N_("Sohbet kısıtlaması"), N_("None: serbest, Dropped: mesajlar görünmez, Disabled: sohbet kapalı.")),
    "disable-player-interaction": (N_("Oyuncu etkileşimini kapat"), N_("Açıksa oyuncular birbirleriyle etkileşemez.")),
    "disable-custom-skins": (N_("Özel görünümleri kapat"), N_("Açıksa oyuncular yalnızca varsayılan görünümleri kullanabilir.")),
    "disable-persona": (N_("Karakter oluşturucuyu kapat"), N_("Açıksa karakter oluşturucu (persona) görünümleri kapanır.")),
    "content-log-file-enabled": (N_("İçerik günlüğünü dosyaya yaz"), N_("Add-on hatalarını bir dosyaya kaydeder.")),
    "content-log-console-output-enabled": (N_("İçerik günlüğünü konsola yaz"), N_("Add-on hataları konsolda da görünür.")),
    "content-log-level": (N_("İçerik günlüğü düzeyi"), N_("Hangi önemdeki add-on iletilerinin yazılacağı.")),
}

RE_RANGE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


def parse(path):
    """[{key, value, comment, allowed}] — dosyadaki sırayla."""
    out, comments = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    cur = None
    for ln in lines:
        s = ln.strip()
        if s.startswith("#"):
            if cur is not None:
                cur["_c"].append(s.lstrip("#").strip())
            continue
        if "=" in s:
            k, v = s.split("=", 1)
            cur = {"key": k.strip(), "value": v.strip(), "_c": []}
            out.append(cur)
        elif not s:
            continue
    for e in out:
        allowed = " ".join(c[len("Allowed values:"):].strip() for c in e["_c"] if c.startswith("Allowed values:"))
        e["allowed"] = allowed
        e["comment"] = " ".join(c for c in e.pop("_c") if c and not c.startswith("Allowed values:"))
        e["type"], e["choices"], e["range"] = kind(allowed, e["value"])
    return out


def kind(allowed, value):
    a = allowed.lower()
    quoted = re.findall(r'"([^"]+)"', allowed)
    if set(x.lower() for x in quoted) == {"true", "false"} or a.replace(" ", "") in ("true,false",) or \
            value.lower() in ("true", "false") and not quoted:
        return "bool", [], None
    if quoted and "range" not in a and "integer" not in a and "any" not in a:
        return "enum", quoted, None
    if re.fullmatch(r"-?\d+\.\d+", value):
        return "float", [], None
    m = RE_RANGE.search(allowed)
    if m and "." not in allowed.split("[")[1].split("]")[0]:
        return "int", [], (int(m.group(1)), int(m.group(2)))
    if "integer" in a and "unlimited" not in a and "or 0" not in a.replace(",", ""):
        return "int", [], (0 if "non-negative" in a or "0" in a else 1, 2147483647)
    if m or re.fullmatch(r"-?\d+\.\d+", value):
        return "float", [], None
    if a.startswith("0-65535"):
        return "int", [], (0, 65535)
    return "text", [], None


def group_of(key):
    for gid, _name, keys in GROUPS:
        if key in keys:
            return gid
    return "advanced"


def load(server_path):
    return parse(os.path.join(server_path, "server.properties"))
