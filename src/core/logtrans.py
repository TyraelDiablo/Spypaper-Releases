"""Sunucu log mesajlarını oyunun kendi dil dosyalarıyla çevirir (çevrimdışı, API gerekmez).

Minecraft ölüm/giriş/başarım mesajlarını dil anahtarlarından üretir:
  en_us:  "death.attack.zombie": "%1$s was slain by %2$s"
  tr_tr:  "death.attack.zombie": "%1$s, %2$s tarafından katledildi"
en_us şablonlarından düzenli ifade kurulur, satır eşleşince hedef dildeki şablon
argümanlarla doldurulur. Argümanlardaki varlık/eşya/başarım adları da çevrilir.
Paper'ın sık sunucu mesajları için küçük bir sözlük vardır (panel diliyle, t()).
"""
import re

from .config import N_

KEY_PREFIXES = ("death.", "multiplayer.player.joined", "multiplayer.player.left",
                "chat.type.advancement.", "multiplayer.disconnect.")
NAME_PREFIXES = ("entity.minecraft.", "item.minecraft.", "block.minecraft.")
ARG = re.compile(r"%(?:(\d+)\$)?s")

# Sık Paper/vanilla sunucu mesajları -> panel dili (t ile)
SERVER_MSGS = [
    (re.compile(r"^Starting minecraft server version (.+)$"), N_("Minecraft sunucusu başlatılıyor, sürüm {0}")),
    (re.compile(r'^Done \(([\d.,]+)s\)! For help, type "help"'), N_("Hazır ({0} sn)! Yardım için \"help\" yazın")),
    (re.compile(r"^Stopping server$"), N_("Sunucu durduruluyor")),
    (re.compile(r"^Stopping the server$"), N_("Sunucu durduruluyor")),
    (re.compile(r"^Preparing level \"(.+)\"$"), N_("Dünya hazırlanıyor: {0}")),
    (re.compile(r"^Can't keep up! Is the server overloaded\? Running (\d+)ms or (\d+) ticks behind"),
     N_("Yetişemiyor! Sunucu aşırı yüklü olabilir: {0} ms / {1} tick geride")),
    (re.compile(r"^([A-Za-z0-9_.*~-]+) issued server command: (.*)$"), N_("{0} komut kullandı: {1}")),
    (re.compile(r"^([A-Za-z0-9_.*~-]+) lost connection: (.*)$"), N_("{0} bağlantısı koptu: {1}")),
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
        self._built_for = None
        self._cache = {}

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
                rx, order = _template_regex(v)
                pats.append((len(ARG.sub("", v)), rx, order, k))
        pats.sort(key=lambda p: -p[0])        # en uzun sabit metin önce (daha özel)
        self.patterns = pats
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

    def message(self, msg):
        """Tek bir log mesajını (zaman damgası olmadan) çevirir; çevrilemezse aynen döner."""
        if msg in self._cache:
            return self._cache[msg]
        if msg.startswith("System chat: "):          # Paper 26.x öneki: çevirip öneki kaldırır
            out = self.message(msg[len("System chat: "):])
            self._cache[msg] = out
            return out
        out = msg
        if self.active:
            self._build()
            for _, rx, order, k in self.patterns:
                m = rx.match(msg)
                if m:
                    args = {i: self._arg(g) for i, g in zip(order, m.groups())}
                    out = _fill(self.tr.data.get(k, self.tr.en[k]), args)
                    break
        if out == msg:
            for rx, tpl in SERVER_MSGS:
                m = rx.match(msg)
                if m:
                    out = self.ui_t(tpl).format(*m.groups())
                    break
        if len(self._cache) > 5000:
            self._cache.clear()
        self._cache[msg] = out
        return out

    def line(self, raw):
        """Tam log satırı: '[12:00:00] [Server thread/INFO]: mesaj' -> mesaj kısmı çevrilmiş satır."""
        m = re.match(r"^(\[[^\]]*\](?:\s*\[[^\]]*\])?:\s?)(.*)$", raw)
        if not m:
            return raw
        return m.group(1) + self.message(m.group(2))
