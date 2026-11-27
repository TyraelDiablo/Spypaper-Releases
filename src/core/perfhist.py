"""Performans geçmişi: TPS, MSPT, RAM, CPU ve çevrimiçi oyuncu sayısı dakikada bir diske yazılır.

Dosyalar: <sunucu>/.spypaper/perf/YYYYMMDD.csv  (zaman;tps;mspt;ram_mb;cpu;oyuncu). KEEP_DAYS günden eskiler silinir.
Boş alan "ölçülemedi" demektir (ör. Vanilla eski sürümde TPS yok, psutil yok). Panel kapalıyken de kaydedilir
(ana penceredeki zamanlayıcı çağırır).
"""
import os
from datetime import datetime, timedelta

INTERVAL = 60            # saniye
KEEP_DAYS = 8
FIELDS = ("tps", "mspt", "ram", "cpu", "players")


def folder(server_path):
    return os.path.join(server_path, ".spypaper", "perf")


class PerfHistory:
    def __init__(self, app):
        self.app = app
        self._last = None
        self._pruned = None

    def _path(self, day):
        return os.path.join(folder(self.app.config.server_path), f"{day:%Y%m%d}.csv")

    def tick(self, now=None):
        """Çalışan sunucuda dakikada bir örnek yazar. Yazdıysa True."""
        now = now or datetime.now()
        if not self.app.server.is_running:
            return False
        if self._last and (now - self._last).total_seconds() < INTERVAL:
            return False
        self._last = now
        tps = mspt = ram = cpu = None
        last = self.app.perf.latest()
        if last and (now - last[0]).total_seconds() < 5 * 60:
            tps, mspt = last[1], last[2]
        try:
            s = self.app.metrics.sample()
            if s:
                ram, cpu = s[0], s[1]
        except Exception:
            pass
        try:
            players = len(self.app.online_players())
        except Exception:
            players = None
        self.write(now, tps, mspt, ram, cpu, players)
        if self._pruned != now.date():
            self._pruned = now.date()
            self.prune(now)
        return True

    def write(self, now, tps, mspt, ram, cpu, players):
        p = self._path(now)
        os.makedirs(os.path.dirname(p), exist_ok=True)

        def f(v, nd):
            return "" if v is None else f"{v:.{nd}f}"
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(f"{now:%H:%M:%S};{f(tps, 2)};{f(mspt, 2)};{f(ram, 0)};{f(cpu, 1)};"
                     f"{'' if players is None else players}\n")

    def prune(self, now=None):
        now = now or datetime.now()
        d = folder(self.app.config.server_path)
        if not os.path.isdir(d):
            return
        cut = (now - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
        for fn in os.listdir(d):
            if fn.endswith(".csv") and fn[:8] < cut:
                try:
                    os.remove(os.path.join(d, fn))
                except OSError:
                    pass

    def load(self, hours=24, now=None):
        """[(datetime, {"tps":…, "mspt":…, "ram":…, "cpu":…, "players":…}), …] eski → yeni."""
        now = now or datetime.now()
        start = now - timedelta(hours=hours)
        out = []
        day = start.date()
        while day <= now.date():
            p = self._path(datetime.combine(day, datetime.min.time()))
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    for line in fh:
                        parts = line.strip().split(";")
                        if len(parts) != 6:
                            continue
                        try:
                            tm = datetime.combine(day, datetime.strptime(parts[0], "%H:%M:%S").time())
                        except ValueError:
                            continue
                        if tm < start or tm > now:
                            continue
                        vals = {}
                        for k, v in zip(FIELDS, parts[1:]):
                            try:
                                vals[k] = float(v) if v != "" else None
                            except ValueError:
                                vals[k] = None
                        out.append((tm, vals))
            day += timedelta(days=1)
        return out


def summary(samples, key):
    vals = [v[key] for _, v in samples if v.get(key) is not None]
    if not vals:
        return None
    return min(vals), sum(vals) / len(vals), max(vals)


def worst_moments(samples, n=3):
    """En düşük TPS anları: [(zaman, tps, oyuncu, ram_mb)]."""
    rows = [(tm, v["tps"], v.get("players"), v.get("ram")) for tm, v in samples if v.get("tps") is not None]
    return sorted(rows, key=lambda r: r[1])[:n]
