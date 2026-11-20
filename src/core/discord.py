"""Discord bildirimleri (webhook): sunucu açıldı/kapandı/çöktü, oyuncu girdi/çıktı/öldü, başarım, sohbet,
bakım ve zamanlanmış görevler.

Merkezi bir sunucu ya da bot yoktur: kullanıcı kendi Discord kanalında bir webhook oluşturur, adresini
Spypaper'a yapıştırır; Spypaper mesajları doğrudan Discord'a gönderir. Tek yönlüdür.

Ayarlar sunucunun profilinde ("discord"):
    {"enabled": bool, "url": <secrets.protect ile şifreli webhook adresi>, "events": {olay: bool}}
Webhook adresi bir paroladır (bilen herkes o kanala yazabilir); config.json'da şifreli durur.

Oyuncu olayları sunucunun konsol çıktısından okunur, bu yüzden yalnızca Spypaper'ın başlattığı sunucularda
çalışır. Gönderim arka plandaki tek bir iş parçacığıyla, sırayla yapılır; Discord'un hız sınırına (429)
uyulur. Mesajlarda @everyone / rol / kullanıcı etiketleri hiçbir zaman çalışmaz (allowed_mentions boş).
"""
import json
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import secrets
from .config import N_

URL_RE = re.compile(r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d{5,25}/[\w-]{20,100}/?$")

EVENTS = {                       # olay -> (ayar adı, varsayılan)
    "start": (N_("Sunucu açıldı"), True),
    "stop": (N_("Sunucu kapandı"), True),
    "crash": (N_("Sunucu çöktü"), True),
    "join": (N_("Oyuncu girdi"), True),
    "leave": (N_("Oyuncu çıktı"), True),
    "death": (N_("Oyuncu öldü"), False),
    "adv": (N_("Başarımlar"), False),
    "chat": (N_("Sohbet mesajları"), False),
    "maintenance": (N_("Bakım başladı / bitti"), True),
    "task": (N_("Zamanlanmış görevler"), False),
}
COLORS = {
    "start": 0x57F287, "stop": 0x95A5A6, "crash": 0xED4245, "join": 0x3BA55D, "leave": 0x747F8D,
    "death": 0x992D22, "adv": 0xFEE75C, "chat": 0x5865F2, "maintenance": 0xE67E22, "task": 0x3498DB,
    "test": 0x5865F2,
}
QUEUE_MAX = 100
UA = "DiscordBot (https://github.com/TyraelDiablo/Spypaper-Releases, 1) Spypaper"


class DiscordError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def valid_url(url):
    return bool(URL_RE.match((url or "").strip()))


def post(url, payload, timeout=10):
    """Webhook'a gönderir. Hız sınırında bekleyip en fazla 3 kez dener. Hata olursa DiscordError."""
    if not valid_url(url):
        raise DiscordError(N_("Geçersiz Discord webhook adresi."))
    data = json.dumps(payload).encode("utf-8")
    for _ in range(3):
        req = urllib.request.Request(url.strip(), data=data, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout):
                return
        except urllib.error.HTTPError as e:
            if e.code == 429:                                   # hız sınırı
                try:
                    wait = float(json.loads(e.read().decode("utf-8", "replace")).get("retry_after", 1))
                except (ValueError, AttributeError):
                    wait = float(e.headers.get("Retry-After") or 1)
                time.sleep(min(max(wait, 0.5), 30))
                continue
            if e.code in (401, 403, 404):
                raise DiscordError(N_("Discord webhook'u bulunamadı ya da silinmiş (HTTP {code})."), code=e.code)
            raise DiscordError(N_("Discord isteği reddetti (HTTP {code})."), code=e.code)
        except (urllib.error.URLError, OSError) as e:
            raise DiscordError(N_("Discord'a bağlanılamadı: {error}"), error=str(getattr(e, "reason", e)))
    raise DiscordError(N_("Discord hız sınırı: mesaj gönderilemedi."))


def _clip(text, n):
    text = str(text or "")
    return text if len(text) <= n else text[:n - 1] + "…"


class Discord:
    def __init__(self, config, server):
        self.config = config
        self.server = server
        self.tr = lambda text, **kw: text.format(**kw) if kw else text   # arayüz panel diline çevirir
        self.last_error = ""               # son gönderim hatası (çevrilmiş), arayüz gösterir
        self.last_sent = None
        self._q = queue.Queue(maxsize=QUEUE_MAX)
        self._worker = None
        self._known = set()                # ölüm mesajları için içerideki oyuncular
        self._started_run = 0
        server.hooks.append(self.on_line)
        server.state_hooks.append(self.on_state)

    # ------------------------------------------------------------ ayarlar
    @property
    def settings(self):
        s = dict(self.config.get("discord") or {})
        ev = {k: d for k, (_, d) in EVENTS.items()}
        ev.update({k: bool(v) for k, v in (s.get("events") or {}).items() if k in EVENTS})
        return {"enabled": bool(s.get("enabled")), "url": s.get("url", ""), "events": ev}

    def url(self):
        return secrets.unprotect(self.settings["url"])

    def save(self, enabled, events, url=None):
        s = self.settings
        s["enabled"] = bool(enabled)
        s["events"] = {k: bool(events.get(k, d)) for k, (_, d) in EVENTS.items()}
        if url is not None:
            url = url.strip()
            if url and not valid_url(url):
                raise DiscordError(N_("Geçersiz Discord webhook adresi."))
            s["url"] = secrets.protect(url) if url else ""
        self.config.set("discord", s)
        self.last_error = ""

    def active(self, kind):
        s = self.settings
        return s["enabled"] and bool(s["url"]) and s["events"].get(kind, False)

    # ------------------------------------------------------------ olaylar
    def on_line(self, line):
        """Sunucunun her konsol satırı (okuma iş parçacığından)."""
        from .logwatch import RE_DONE, _parse_line, classify
        p = _parse_line(line)
        if not p:
            return
        kind, player, text = classify(p[3], p[4], self._known)
        if kind == "start":
            if self._started_run != self.server.run_id:       # her çalıştırmada bir kez
                self._started_run = self.server.run_id
                m = RE_DONE.match(text)
                self.event("start", secs=m.group(1).replace(",", ".") if m else "")
            return
        if kind == "leave":
            self._known.discard(player)
        if kind in ("join", "leave", "death", "adv", "chat"):
            self.event(kind, player=player, text=text)

    def on_state(self, state):
        from .server import STOPPED
        if state == STOPPED:
            self._known.clear()
            self.event("crash" if self.server.crashed else "stop", code=self.server.exit_code)

    def event(self, kind, **kw):
        """Olayı (açıksa) gönderim sırasına koyar. Hiçbir zaman hata fırlatmaz."""
        try:
            if not self.active(kind):
                return
            self._enqueue(self.payload(kind, **kw))
        except Exception as e:
            print(f"[discord] {e}")

    # ------------------------------------------------------------ mesaj
    def payload(self, kind, player="", text="", secs="", code=None, name="", status="", started=True):
        tr = self.tr
        title, desc, author = "", "", None
        if kind == "start":
            title = "🟢 " + tr("Sunucu açıldı")
            desc = tr("Açılış {secs} saniye sürdü.", secs=secs) if secs else ""
        elif kind == "stop":
            title = "⚫ " + tr("Sunucu kapandı")
        elif kind == "crash":
            title = "🔴 " + tr("Sunucu beklenmedik şekilde kapandı")
            desc = tr("Çökme bekçisi açık: sunucu birazdan yeniden başlatılacak.") if self.config.get("auto_restart") \
                else tr("Sunucuyu yeniden başlatmak için Spypaper'ı kullan.")
            if code not in (None, 0):
                desc += "\n" + tr("Çıkış kodu: {code}", code=code)
        elif kind == "join":
            title = "➡️ " + tr("{name} oyuna girdi", name=player)
        elif kind == "leave":
            title = "⬅️ " + tr("{name} oyundan çıktı", name=player)
        elif kind == "death":
            title, desc = "☠️ " + tr("{name} öldü", name=player), text
        elif kind == "adv":
            title, desc = "🏆 " + tr("{name} bir başarım kazandı", name=player), f"**{text}**"
        elif kind == "chat":
            author, desc = {"name": player}, text
        elif kind == "maintenance":
            title = "🛠️ " + (tr("Bakım başladı") if started else tr("Bakım bitti"))
        elif kind == "task":
            title, desc = "⏰ " + tr("Zamanlanmış görev: {name}", name=name), status
        elif kind == "test":
            title = "✅ " + tr("Spypaper bağlantı testi")
            desc = tr("Bu kanal artık '{server}' sunucusunun bildirimlerini alacak.", server=self.config.name)
        embed = {"color": COLORS.get(kind, 0x5865F2), "footer": {"text": _clip(self.config.name, 100)},
                 "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if title:
            embed["title"] = _clip(title, 250)
        if desc:
            embed["description"] = _clip(desc, 2000)
        if author:
            embed["author"] = {"name": _clip(author["name"], 250)}
        return {"username": _clip(self.config.name or "Spypaper", 80), "embeds": [embed],
                "allowed_mentions": {"parse": []}}

    # ------------------------------------------------------------ gönderim
    def _enqueue(self, payload):
        try:
            self._q.put_nowait(payload)
        except queue.Full:                         # sohbet seli: en eski mesaj düşer
            try:
                self._q.get_nowait()
                self._q.put_nowait(payload)
            except (queue.Empty, queue.Full):
                pass
        if not self._worker or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def _run(self):
        while True:
            try:
                payload = self._q.get(timeout=30)
            except queue.Empty:
                return                             # boşta kalan iş parçacığı kapanır, gerekince yeniden açılır
            try:
                post(self.url(), payload)
                self.last_sent, self.last_error = datetime.now(), ""
            except DiscordError as e:
                self.last_error = self.tr(e.template, **e.kw)
            except Exception as e:
                self.last_error = str(e)
            time.sleep(0.4)                        # webhook başına ~5 istek / 2 sn sınırının altında kal

    def test(self, url=None):
        """Test mesajını hemen gönderir (çağıran arka planda çalıştırmalı). Hata olursa DiscordError."""
        post((url or self.url()).strip(), self.payload("test"))
        self.last_sent, self.last_error = datetime.now(), ""
