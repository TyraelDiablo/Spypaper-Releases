"""logs/latest.log takibi: olay ayrıştırma, çevrimiçi zaman çizgisi, geçmiş.

Panel sunucuyu başlatmamış olsa bile çalışır; yalnızca log dosyasını okur.
"""
import gzip
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import N_

# Vanilla/Paper/Fabric dosya formatı: [17:01:02] [Server thread/INFO]: mesaj
# Paper konsol formatı:                [17:01:02 INFO]: mesaj
# Forge/NeoForge:  [17Nov2026 17:01:02.123] [Server thread/INFO] [minecraft/DedicatedServer]: mesaj
LINE_RES = (
    re.compile(r"^\[(?:\d{1,2}[A-Za-z]{3}\d{4} )?(\d{2}):(\d{2}):(\d{2})(?:[.,]\d+)?\]\s*\[[^\]]*?/(\w+)\]"
               r"(?:\s*\[[^\]]*\])*:\s?(.*)$"),
    re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\s+(\w+)\]:\s?(.*)$"),
)
NAME = r"([A-Za-z0-9_.*~-]{2,32})"
RE_JOIN = re.compile(rf"^{NAME} joined the game")
RE_LEAVE = re.compile(rf"^{NAME} left the game")
RE_CHAT = re.compile(r"^(?:\[Not Secure\]\s*)?<([^>]+)>\s?(.*)$")
RE_CMD = re.compile(rf"^{NAME} issued server command:\s*(.*)$")
RE_ADV = re.compile(rf"^{NAME} has (?:made the advancement|completed the challenge|reached the goal) \[(.+)\]")
RE_DONE = re.compile(r"^Done \(([\d.,]+)s\)")
RE_LAG = re.compile(r"Can't keep up!.*?(\d+)ms or (\d+) ticks behind")
# Paper 26.x sistem mesajlarının başına "System chat: " ekliyor:
#   System chat: Steve joined the game / System chat: Alex has made the advancement [..]
RE_SYS_PREFIX = re.compile(r"^System chat:\s*")

DEATH_PHRASES = (
    "was slain by", "was shot by", "was killed", "was blown up", "blew up", "drowned", "died",
    "fell ", "hit the ground", "burned to death", "went up in flames", "walked into fire",
    "tried to swim in lava", "discovered the floor was lava", "walked into danger zone",
    "was struck by lightning", "starved to death", "suffocated", "was squished", "was squashed",
    "was pricked to death", "walked into a cactus", "froze to death", "was frozen",
    "withered away", "was fireballed", "was pummeled", "was impaled", "was stung to death",
    "was obliterated", "experienced kinetic energy", "didn't want to live", "left the confines",
    "was poked to death", "was skewered", "was roasted", "was doomed to fall", "was sniped",
    "was spitballed", "went off with a bang", "was killed by magic", "was struck",
)

KINDS = {
    "join": N_("Giriş"), "leave": N_("Çıkış"), "chat": N_("Sohbet"), "death": N_("Ölüm"), "adv": N_("Başarım"),
    "cmd": N_("Komut"), "lag": N_("Gecikme"), "warn": N_("Uyarı"), "error": N_("Hata"), "start": N_("Başladı"),
    "stop": N_("Durdu"), "info": N_("Bilgi"),
}


@dataclass
class Event:
    time: datetime
    kind: str
    player: str
    text: str
    raw: str


def _parse_line(line):
    for rx in LINE_RES:
        m = rx.match(line)
        if m:
            h, mi, s, level, msg = m.groups()
            return int(h), int(mi), int(s), level.upper(), msg
    return None


def classify(level, msg, known_players):
    """(tür, oyuncu, metin)"""
    msg = RE_SYS_PREFIX.sub("", msg, count=1)
    m = RE_JOIN.match(msg)
    if m:
        known_players.add(m.group(1))
        return "join", m.group(1), msg
    m = RE_LEAVE.match(msg)
    if m:
        return "leave", m.group(1), msg
    m = RE_CHAT.match(msg)
    if m:
        return "chat", m.group(1), m.group(2)
    m = RE_CMD.match(msg)
    if m:
        return "cmd", m.group(1), m.group(2)
    m = RE_ADV.match(msg)
    if m:
        return "adv", m.group(1), m.group(2)
    if RE_DONE.match(msg):
        return "start", "", msg
    if msg.startswith("Stopping server") or msg.startswith("Stopping the server"):
        return "stop", "", msg
    if RE_LAG.search(msg):
        return "lag", "", msg
    first, _, rest = msg.partition(" ")
    if first in known_players and rest.startswith(DEATH_PHRASES):
        return "death", first, msg
    if level == "WARN":
        return "warn", "", msg
    if level in ("ERROR", "FATAL", "SEVERE"):
        return "error", "", msg
    return "info", "", msg


class _Parser:
    """Satırları sırayla işler; gece yarısı geçişini (saat geriye gidince) yakalar."""

    def __init__(self, base_date, known_players=None):
        self.day = base_date
        self.last = None
        self.known = known_players if known_players is not None else set()

    def feed(self, line):
        p = _parse_line(line.rstrip("\r\n"))
        if not p:
            return None
        h, mi, s, level, msg = p
        t = datetime.combine(self.day, datetime.min.time()).replace(hour=h, minute=mi, second=s)
        if self.last and t < self.last - timedelta(minutes=5):
            self.day += timedelta(days=1)
            t += timedelta(days=1)
        self.last = t
        kind, player, text = classify(level, msg, self.known)
        return Event(t, kind, player, text, line.rstrip("\r\n"))


def _count_wraps(lines):
    wraps, last = 0, None
    for ln in lines:
        p = _parse_line(ln)
        if p:
            sec = p[0] * 3600 + p[1] * 60 + p[2]
            if last is not None and sec < last - 300:
                wraps += 1
            last = sec
    return wraps


def parse_lines(lines, end_date):
    """Tüm satırları ayrıştırır. end_date: son satırın tarihi (dosya tarihi)."""
    start = end_date - timedelta(days=_count_wraps(lines))
    p = _Parser(start)
    return [e for e in (p.feed(ln) for ln in lines) if e], p


def read_log_file(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def archive_date(file_name):
    """'2026-11-12-1.log.gz' -> date"""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", file_name)
    return date(*map(int, m.groups())) if m else None


def parse_file(path):
    name = os.path.basename(path)
    d = archive_date(name) or datetime.fromtimestamp(os.path.getmtime(path)).date()
    events, _ = parse_lines(read_log_file(path), d)
    return events


# ------------------------------------------------------------------ istatistik
def online_timeline(events):
    """[(zaman, çevrimiçi_sayısı)] — giriş/çıkış ve sunucu başla/dur olaylarından."""
    online, out = set(), []
    for e in events:
        if e.kind == "join":
            online.add(e.player)
        elif e.kind == "leave":
            online.discard(e.player)
        elif e.kind in ("start", "stop"):
            online.clear()
        else:
            continue
        out.append((e.time, len(online)))
    return out, online


def sessions(events, now=None):
    """{oyuncu: toplam_saniye} — açık oturumlar şimdiye kadar sayılır."""
    now = now or datetime.now()
    open_at, total = {}, defaultdict(float)
    for e in events:
        if e.kind == "join":
            open_at[e.player] = e.time
        elif e.kind == "leave" and e.player in open_at:
            total[e.player] += (e.time - open_at.pop(e.player)).total_seconds()
        elif e.kind in ("start", "stop"):
            for p, t in open_at.items():
                total[p] += (e.time - t).total_seconds()
            open_at.clear()
    for p, t in open_at.items():
        total[p] += (now - t).total_seconds()
    return dict(total)


def hourly_counts(events, day, kinds=("join", "chat", "death", "adv", "cmd")):
    c = [0] * 24
    for e in events:
        if e.time.date() == day and e.kind in kinds:
            c[e.time.hour] += 1
    return c


class LogWatcher:
    """latest.log'u takip eder. poll() yeni olayları döndürür."""

    def __init__(self, server_path):
        self.set_server_path(server_path)

    def set_server_path(self, path):
        self.server_path = path
        self.logs_dir = os.path.join(path, "logs")
        self.path = os.path.join(self.logs_dir, "latest.log")
        self.reset()
        self._history_cache = {}

    def reset(self):
        self.generation = getattr(self, "generation", 0) + 1  # arayüz bunu görünce baştan çizer
        self.events = []
        self.pos = 0
        self.buf = ""
        self.parser = None
        self.file_id = None

    def _id(self):
        st = os.stat(self.path)
        return (st.st_ino, getattr(st, "st_birthtime", 0)), st.st_size

    def poll(self):
        """Yeni olayları döndürür. Dosya yenilendiyse (sunucu yeniden başladı)
        baştan okur ve 'reset' işaretli boş olmayan liste yerine tüm olayları döndürür."""
        if not os.path.exists(self.path):
            if self.events:
                self.reset()
            return []
        try:
            fid, size = self._id()
        except OSError:
            return []
        rotated = self.file_id is not None and (fid != self.file_id or size < self.pos)
        if rotated:
            self.reset()
        self.file_id = fid
        if size == self.pos:
            return []

        with open(self.path, "rb") as f:
            f.seek(self.pos)
            chunk = f.read()
        self.pos += len(chunk)
        text = self.buf + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self.buf = lines.pop()  # yarım satır

        if self.parser is None:
            mdate = datetime.fromtimestamp(os.path.getmtime(self.path)).date()
            new, self.parser = parse_lines(lines, mdate)
        else:
            new = [e for e in (self.parser.feed(ln) for ln in lines) if e]
        self.events.extend(new)
        return new

    # --- arşiv ---
    def archives(self):
        """[(dosya_yolu, tarih)] yeniden eskiye."""
        if not os.path.isdir(self.logs_dir):
            return []
        out = []
        for f in os.listdir(self.logs_dir):
            d = archive_date(f)
            if d and f.endswith(".log.gz"):
                out.append((os.path.join(self.logs_dir, f), d))
        return sorted(out, key=lambda x: (x[1], x[0]), reverse=True)

    def _archive_events(self, path):
        key = (path, os.path.getsize(path))
        if key not in self._history_cache:
            try:
                self._history_cache[key] = parse_file(path)
            except Exception:
                self._history_cache[key] = []
        return self._history_cache[key]

    def daily_history(self, days=7):
        """Son N gün için [(tarih, tekil_oyuncu, giriş_sayısı, ölüm)] eskiden yeniye."""
        today = date.today()
        first = today - timedelta(days=days - 1)
        players, joins, deaths = defaultdict(set), Counter(), Counter()
        evs = list(self.events)
        for path, d in self.archives():
            if d >= first - timedelta(days=1):
                evs.extend(self._archive_events(path))
        for e in evs:
            d = e.time.date()
            if d < first or d > today:
                continue
            if e.kind == "join":
                players[d].add(e.player)
                joins[d] += 1
            elif e.kind == "death":
                deaths[d] += 1
        return [(first + timedelta(days=i),
                 len(players[first + timedelta(days=i)]),
                 joins[first + timedelta(days=i)],
                 deaths[first + timedelta(days=i)]) for i in range(days)]


# ------------------------------------------------------------------ RAM / CPU
class ProcessMetrics:
    """Sunucu java sürecinin RAM/CPU kullanımı (psutil gerekir; yoksa devre dışı)."""

    def __init__(self, server, config):
        self.server, self.config = server, config
        self._proc = None
        try:
            import psutil
            self.psutil = psutil
        except ImportError:
            self.psutil = None

    @property
    def available(self):
        return self.psutil is not None

    def _find(self):
        ps = self.psutil
        if self.server.is_running:
            try:
                return ps.Process(self.server.process.pid)
            except ps.Error:
                return None
        # panel dışında başlatılmış sunucu: cwd sunucu klasörü olan java süreci
        target = os.path.normcase(os.path.abspath(self.config.server_path))
        for p in ps.process_iter(["name"]):
            try:
                if "java" in (p.info["name"] or "").lower() and os.path.normcase(p.cwd()) == target:
                    return p
            except ps.Error:
                continue
        return None

    def sample(self):
        """(ram_mb, cpu_yüzde, başlama_zamanı) ya da None."""
        if not self.psutil:
            return None
        ps = self.psutil
        try:
            if self._proc is None or not self._proc.is_running():
                self._proc = self._find()
                if self._proc:
                    self._proc.cpu_percent(None)
            if not self._proc:
                return None
            rss = self._proc.memory_info().rss / 1024 / 1024
            cpu = self._proc.cpu_percent(None) / (ps.cpu_count() or 1)
            return rss, cpu, datetime.fromtimestamp(self._proc.create_time())
        except ps.Error:
            self._proc = None
            return None
