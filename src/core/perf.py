"""TPS / MSPT ölçümü.

Spypaper sunucunun dışında çalıştığı için tick sürelerini göremez; bunları sunucuya kendi komutuyla sorar
ve yanıtı konsoldan okur. Yazılıma göre kullanılan komutlar:
    Paper, Purpur, Folia, Pufferfish   tps + mspt
    Spigot / Bukkit                    tps
    Forge                              forge tps
    NeoForge                           neoforge tps
    Vanilla, Fabric, Quilt (1.20.3+)   tick query
Daha eski vanilla/Fabric sunucuları TPS bildirmez; o zaman ölçüm kapanır (Dashboard'da yazar).

Yanıt satırları konsoldan ve panelin olay akışından gizlenir (sunucunun kendi latest.log dosyasına yine yazılır).
Kullanıcı aynı anda kendisi bir komut gönderirse gizleme hemen biter, kendi çıktısını görür.
Ölçümler yalnızca bellekte tutulur (son 6 saat), diske yazılmaz.
"""
import re
import time
from collections import deque
from datetime import datetime

from .config import N_

INTERVAL = 15                 # saniye
WINDOW = 4                    # yanıt bekleme / gizleme süresi (saniye)
KEEP = 6 * 3600 // INTERVAL   # 6 saatlik örnek
FAIL_LIMIT = 3                # art arda bu kadar yanıtsız sorgudan sonra ölçüm durur

PAPER_FAMILY = {"Paper", "Purpur", "Folia", "Pufferfish", "Leaf", "Leaves", "Gale"}
SPIGOT = {"Spigot", "CraftBukkit", "Bukkit"}

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|§.")
NUM = r"(\d+(?:[.,]\d+)?)"          # Java sistem diline göre ondalık nokta ya da virgül yazar (20,0)
RE_PAPER_TPS = re.compile(r"TPS from last [\dsm, ]+:\s*\*?" + NUM)    # 1m, 5m, 15m (yeni Paper: 5s, 1m, …)
RE_MSPT_HEAD = re.compile(r"Server tick times \(avg/min/max\)")
RE_MSPT_VALS = re.compile(NUM + "/" + NUM + "/" + NUM)
RE_TQ_AVG = re.compile(r"Average time per tick:\s*" + NUM + r"\s*ms")
RE_TQ_RATE = re.compile(r"Target tick rate:\s*" + NUM)
RE_FORGE = re.compile(r"Overall\s*:.*?Mean tick time:\s*" + NUM + r"\s*ms.*?Mean TPS:\s*" + NUM)
RE_NEO = re.compile(r"Overall\s*:\s*" + NUM + r"\s*TPS\s*\(" + NUM + r"\s*ms/tick\)")
# sorgu penceresinde gizlenen satırlar (yanıtın parçaları ve "bilinmeyen komut" hatası)
HIDE = re.compile(
    r"^(TPS from last|Server tick times|\s*[◴⏲]?\s*[\d.,]+/[\d.,]+/[\d.,]+|The game is running|The game is sprinting|"
    r"The game is frozen|Target tick rate|Average time per tick|Percentiles|Dim(?:ension)?\s|Overall\s*:|"
    r".*\bTPS\s*\([\d.,]+\s*ms/tick\)|.*Mean tick time:|"
    r"Unknown or incomplete command|Unknown command|.*<--\[HERE\]|Incorrect argument)")
RE_UNKNOWN = re.compile(r"^(Unknown or incomplete command|Unknown command|Incorrect argument)")

def _f(v):
    return float(v.replace(",", "."))


STATUS = {
    "waiting": N_("Ölçüm bekleniyor…"),
    "unsupported": N_("Bu sunucu TPS bilgisi vermiyor (1.20.3'ten eski vanilla ya da Fabric)."),
    "off": N_("TPS ölçümü kapalı."),
    "stopped": N_("Sunucu kapalı."),
}


def _msg(line):
    """Konsol satırının mesaj kısmı (renk kodları temizlenmiş)."""
    from .logwatch import _parse_line
    line = ANSI.sub("", line)
    p = _parse_line(line)
    return (p[4] if p else line).strip()


def _ver_tuple(v):
    nums = [int(x) for x in re.findall(r"\d+", v or "")[:3]] + [0, 0, 0]
    return tuple(nums[:3])


def probes_for(software, version):
    """Yazılım ve sürüme göre gönderilecek komutlar (boş liste: desteklenmiyor)."""
    if software.startswith("Bedrock"):   # BDS'de TPS komutu yok
        return []
    if software in PAPER_FAMILY:
        return ["tps", "mspt"]
    if software in SPIGOT:
        return ["tps"]
    if software == "Forge":
        return ["forge tps"]
    if software == "NeoForge":
        return ["neoforge tps"]
    v = _ver_tuple(version)
    if v[0] >= 26 or v >= (1, 20, 3):
        return ["tick query"]
    if not version:                      # sürüm bilinmiyor: önce dene
        return ["tick query"]
    return []


class PerfMonitor:
    def __init__(self, config, server):
        self.config = config
        self.server = server
        self.samples = deque(maxlen=KEEP)     # (datetime, tps|None, mspt|None)
        self.status = "stopped"
        self._probes = None
        self._next = 0.0
        self._until = 0.0                     # gizleme / yanıt penceresi sonu
        self._got = False
        self._fails = 0
        self._cur = {}
        self._mspt_next = False
        self._sending = False
        self._run = 0
        server.line_filters.append(self.filter)
        server.send_hooks.append(self._on_send)

    @property
    def enabled(self):
        v = self.config.get("perf_monitor")
        return True if v is None else bool(v)

    def set_enabled(self, on):
        self.config.set("perf_monitor", bool(on))
        if not on:
            self.status = "off"

    def latest(self):
        return self.samples[-1] if self.samples else None

    # ------------------------------------------------------------ zamanlayıcı (ana iş parçacığı)
    def tick(self, now=None):
        now = now or time.time()
        from .server import RUNNING
        if self.server.run_id != self._run:                  # yeni çalıştırma: sıfırdan başla
            self._run = self.server.run_id
            self._probes, self._fails, self._next, self._until = None, 0, now + 5, 0.0
            if self.samples:
                self.samples.append((datetime.now(), None, None))   # grafikte boşluk (yeniden başlatma)
        if not self.enabled:
            self.status = "off"
            return
        if self.server.state != RUNNING or not self.server.is_running:
            self.status = "stopped"
            return
        if self._probes is None:
            from .config import detect_version
            ver, soft = detect_version(self.config.server_path)
            self._probes = probes_for(soft, ver)
            self.status = "waiting" if self._probes else "unsupported"
        if not self._probes or self.status == "unsupported":
            return
        if self._until and now > self._until:                 # pencere kapandı: sonucu işle
            self._finish()
        if now >= self._next and not self._until:
            self._next = now + INTERVAL
            self._cur, self._got, self._mspt_next = {}, False, False
            self._until = now + WINDOW
            self._sending = True
            try:
                for cmd in self._probes:
                    self.server.try_send(cmd)
            finally:
                self._sending = False

    def _finish(self):
        self._until = 0.0
        if self._got and ("tps" in self._cur or "mspt" in self._cur):
            self._fails = 0
            tps, mspt = self._cur.get("tps"), self._cur.get("mspt")
            if tps is None and mspt:
                rate = self._cur.get("rate", 20.0)
                tps = round(min(rate, 1000.0 / mspt) if mspt > 0 else rate, 2)
            self.samples.append((datetime.now(), tps, mspt))
            self.status = "ok"
        else:
            self._fails += 1
            if self._cur.get("unknown") or self._fails >= FAIL_LIMIT:   # komutu tanımıyor ya da hiç yanıt yok
                self.status = "unsupported"

    def _on_send(self, command):
        if not self._sending:
            self._until = 0.0                                   # kullanıcı komutu: gizleme bitsin

    # ------------------------------------------------------------ satırlar (okuma iş parçacığı)
    def filter(self, line):
        """True: satır sorgunun yanıtıdır, konsolda gösterilmez."""
        if not self._until or time.time() > self._until + 1:
            return False
        msg = _msg(line)
        if not HIDE.match(msg):
            return False
        self.parse(msg)
        return True

    def parse(self, msg):
        c = self._cur
        if self._mspt_next:
            m = RE_MSPT_VALS.search(msg)
            self._mspt_next = False
            if m:
                c["mspt"] = _f(m.group(1))
                self._got = True
                return
        m = RE_PAPER_TPS.search(msg)
        if m:
            c["tps"] = min(20.0, _f(m.group(1)))
            self._got = True
            return
        if RE_MSPT_HEAD.search(msg):
            self._mspt_next = True
            return
        m = RE_TQ_RATE.search(msg)
        if m:
            c["rate"] = _f(m.group(1))
            return
        m = RE_TQ_AVG.search(msg)
        if m:
            c["mspt"] = _f(m.group(1))
            self._got = True
            return
        m = RE_FORGE.search(msg)
        if m:
            c["mspt"], c["tps"] = _f(m.group(1)), min(20.0, _f(m.group(2)))
            self._got = True
            return
        m = RE_NEO.search(msg)
        if m:
            c["tps"], c["mspt"] = min(20.0, _f(m.group(1))), _f(m.group(2))
            self._got = True
            return
        if RE_UNKNOWN.match(msg):
            c["unknown"] = True
