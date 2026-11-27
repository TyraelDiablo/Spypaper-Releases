"""Sunucu log mesajlarını oyunun kendi dil dosyalarıyla çevirir (çevrimdışı, API gerekmez).

Minecraft ölüm/giriş/başarım mesajlarını dil anahtarlarından üretir:
  en_us:  "death.attack.zombie": "%1$s was slain by %2$s"
  tr_tr:  "death.attack.zombie": "%1$s, %2$s tarafından katledildi"
en_us şablonlarından düzenli ifade kurulur, satır eşleşince hedef dildeki şablon
argümanlarla doldurulur. Argümanlardaki varlık/eşya/başarım adları da çevrilir.
Komut yanıtları (commands.*) da dil dosyasından çevrilir; "[Yönetici: yanıt]" biçimi desteklenir.
Paper/vanilla sunucunun kendi satırları için önceden hazırlanmış tablo core/logtrans_table.py'dedir
(panel diliyle, t()). Eklenti satırları çevrilmez.
"""
import re

from .config import N_
from .logtrans_table import NOT_SECURE, PANEL, is_core_logger

KEY_PREFIXES = ("death.", "multiplayer.player.joined", "multiplayer.player.left",
                "chat.type.advancement.", "multiplayer.disconnect.", "commands.", "command.",
                "permissions.requires.", "argument.")
# argümanlı şablonu yalnızca bu kadar sabit metin içeriyorsa kullan (ör. "%s" tek başına her şeye uyar)
MIN_FIXED = 6
# argümansız tam metinler: "You are not whitelisted on this server!" -> çeviri
EXACT_PREFIXES = ("multiplayer.disconnect.", "disconnect.", "command.", "commands.", "permissions.", "argument.")
NAME_PREFIXES = ("entity.minecraft.", "item.minecraft.", "block.minecraft.", "gameMode.", "options.difficulty.",
                 "effect.minecraft.", "enchantment.minecraft.")
ADMIN = re.compile(r"^\[([^\]:]+): (.+)\]$")          # chat.type.admin "[%s: %s]"
LOGGER = re.compile(r"^\[([^\]]+)\] (.*)$")
# satır başı: '[12:00:00] [Server thread/INFO]:', '[12:00:00 INFO]:', Forge/NeoForge'da üçüncü [logger/MARKER] parantezi
PREFIX = re.compile(r"^(\[\d{4}-\d{2}-\d{2} [^\]]+\]\s?|(?:\[[^\]]*\]\s*)+:\s?)(.*)$")   # ilk seçenek: Bedrock "[2026-11-26 22:48:52:003 INFO] "
ARG = re.compile(r"%(?:(\d+)\$)?s")

# Sık Paper/vanilla sunucu mesajları -> panel dili (t ile)
SERVER_MSGS = [
    # Paperclip (Paper/Purpur/Folia ilk açılışı; önek yok)
    (re.compile(r"^Applying patches\.*$"), N_("Yamalar uygulanıyor")),
    (re.compile(r"^Downloading (\S+\.jar)$"), N_("İndiriliyor: {0}")),
    (re.compile(r"^Starting org\.bukkit\.craftbukkit\.Main$"), N_("Sunucu başlatılıyor (org.bukkit.craftbukkit.Main)")),
    (re.compile(r"^Starting minecraft server version (.+)$"), N_("Minecraft sunucusu başlatılıyor, sürüm {0}")),
    (re.compile(r'^Done \(([\d.,]+)s\)! For help, type "help"'), N_("Hazır ({0} sn)! Yardım için \"help\" yazın")),
    (re.compile(r"^Stopping server$"), N_("Sunucu durduruluyor")),
    (re.compile(r"^Stopping the server$"), N_("Sunucu durduruluyor")),
    (re.compile(r"^Preparing level \"(.+)\"$"), N_("Dünya hazırlanıyor: {0}")),
    (re.compile(r"^Can't keep up! Is the server overloaded\? Running (\d+)ms or (\d+) ticks behind"),
     N_("Yetişemiyor! Sunucu aşırı yüklü olabilir: {0} ms / {1} tick geride")),
    (re.compile(r"^([A-Za-z0-9_.*~-]+) issued server command: (.*)$"), N_("{0} komut kullandı: {1}")),
    (re.compile(r"^Saving the game \(this may take a moment!\)$"), N_("Oyun kaydediliyor (biraz sürebilir)")),
    (re.compile(r"^Saved the game$"), N_("Oyun kaydedildi")),
    (re.compile(r"^Starting Minecraft server on (.+)$"), N_("Sunucu {0} adresinde dinliyor")),
    (re.compile(r"^There are (\d+) of a max of (\d+) players online: ?(.*)$"), N_("Çevrimiçi: {0}/{1} oyuncu {2}")),
]


def _template_regex(tpl):
    """'%1$s was slain by %2$s' -> regex, argüman sırası listesi."""
    parts, order, pos, seq = [], [], 0, 0
    for m in ARG.finditer(tpl):
        parts.append(re.escape(tpl[pos:m.start()]))
        idx = int(m.group(1)) if m.group(1) else (seq := seq + 1)
        order.append(idx)
        parts.append("(.+?)")
        pos = m.end()
    parts.append(re.escape(tpl[pos:]))
    return re.compile("^" + "".join(parts) + "$"), order


def _fill(tpl, args):
    seq = iter(range(1, 100))

    def rep(m):
        i = int(m.group(1)) if m.group(1) else next(seq)
        return args.get(i, "")
    return ARG.sub(rep, tpl)


class LogTranslator:
    def __init__(self, translations, ui_t=lambda s: s):
        self.tr = translations          # core.players.Translations (en + hedef)
        self.ui_t = ui_t
        self.ui_lang = lambda: ""        # panel dili (ör. "tr", "en"); İngilizcede tablo uygulanmaz
        self._built_for = None
        self._cache = {}
        self._cache_lang = None

    def _build(self):
        key = (id(self.tr.en), self.tr.lang, len(self.tr.data))
        if self._built_for == key:
            return
        self._built_for = key
        self._cache.clear()
        en = self.tr.en
        pats = []
        for k, v in en.items():
            if k.startswith(KEY_PREFIXES) and isinstance(v, str) and "%" in v:
                fixed = len(ARG.sub("", v).strip())
                if fixed < MIN_FIXED:
                    continue
                rx, order = _template_regex(v)
                pats.append((fixed, rx, order, k))
        pats.sort(key=lambda p: -p[0])        # en uzun sabit metin önce (daha özel)
        self.patterns = pats
        self.exact = {}
        for k, v in en.items():
            if isinstance(v, str) and "%" not in v and len(v) >= MIN_FIXED and k.startswith(EXACT_PREFIXES):
                self.exact.setdefault(v, k)
        self.reverse = {}
        for k, v in en.items():
            if isinstance(v, str) and (k.startswith(NAME_PREFIXES) or
                                       (k.startswith("advancements.") and k.endswith(".title"))):
                self.reverse.setdefault(v, k)

    @property
    def active(self):
        return bool(self.tr.en) and self.tr.lang != "en_us"

    def _arg(self, a):
        bracket = a.startswith("[") and a.endswith("]")
        core = a[1:-1] if bracket else a
        k = self.reverse.get(core)
        if k and k in self.tr.data:
            core = self.tr.data[k]
        return f"[{core}]" if bracket else core

    def message(self, msg, _depth=0):
        """Tek bir log mesajını (zaman damgası olmadan) çevirir; çevrilemezse aynen döner."""
        lang = self.ui_lang() or ""
        if lang != self._cache_lang:                # panel dili değişti: eski dildeki sonuçlar atılır
            self._cache.clear()
            self._cache_lang = lang
        if msg in self._cache:
            return self._cache[msg]
        out = self._message(msg, _depth)
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[msg] = out
        return out

    def _message(self, msg, depth):
        if depth > 3 or not msg:
            return msg
        if msg.startswith("System chat: "):          # Paper 26.x öneki: çevirip öneki kaldırır
            return self.message(msg[len("System chat: "):], depth + 1)
        lg = LOGGER.match(msg)
        if lg:
            name, rest = lg.groups()
            if name == "Not Secure":                 # imzasız sohbet: yalnızca etiket çevrilir
                return f"[{self.ui_t(NOT_SECURE)}] {rest}"
            if is_core_logger(name):
                return f"[{name}] " + self.message(rest, depth + 1)
        if self.active:
            self._build()
            m = ADMIN.match(msg)
            if m and "chat.type.admin" in self.tr.en:
                inner = self.message(m.group(2), depth + 1)
                if inner != m.group(2):
                    return _fill(self.tr.data.get("chat.type.admin", "[%s: %s]"), {1: m.group(1), 2: inner})
            for _, rx, order, k in self.patterns:
                m = rx.match(msg)
                if m:
                    args = {i: self._arg(g) for i, g in zip(order, m.groups())}
                    return _fill(self.tr.data.get(k, self.tr.en[k]), args)
            k = self.exact.get(msg)
            if k and k in self.tr.data:
                return self.tr.data[k]
        if (self.ui_lang() or "").startswith("en"):     # sunucu zaten İngilizce yazıyor
            return msg
        for rx, tpl in SERVER_MSGS:
            m = rx.match(msg)
            if m:
                return self.ui_t(tpl).format(*m.groups())
        for rx, tpl, again in PANEL:
            m = rx.match(msg)
            if m:
                args = [self.message(g, depth + 1) if i in again else g for i, g in enumerate(m.groups())]
                out = self.ui_t(tpl).format(*args)
                if len(msg) > 2 and msg[0] == "#" and msg[-1] == "#":      # çerçeveli başlık: aynı genişlikte ortala
                    inner = out.strip("#").strip()
                    out = "#" + inner.center(len(msg) - 2) + "#"
                return out
        return msg

    def line(self, raw):
        """Tam log satırı: '[12:00:00] [Server thread/INFO]: mesaj' -> mesaj kısmı çevrilmiş satır.
        Öneksiz satırlar (ör. 'Starting org.bukkit.craftbukkit.Main') bütünüyle denenir."""
        m = PREFIX.match(raw)
        if not m:
            return self.message(raw)
        return m.group(1) + self.message(m.group(2))
