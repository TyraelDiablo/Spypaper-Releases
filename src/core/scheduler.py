"""Zamanlanmış görevler: belirli gün ve saatte ya da belli aralıklarla yeniden başlatma, durdurma,
başlatma, yedek, komut ve duyuru.

Görevler sunucunun profilinde ("scheduled_tasks") liste olarak durur:
    {"id", "enabled", "name", "action", "mode", "days", "time", "every", "countdown", "command", "message",
     "last_run"}
mode = "weekly": seçili günlerde HH:MM'de. mode = "interval": gece yarısından başlayarak her `every` dakikada
(ör. 30 dk -> :00 ve :30), böylece zaman Spypaper'ın ne zaman açıldığına bağlı değildir.

Zamanlayıcıyı arayüz katmanı çalıştırır (her saniye tick()). Görevler yalnızca Spypaper açıkken çalışır;
Spypaper kapalıyken (ya da bilgisayar uykudayken) kaçan görevler sonradan çalıştırılmaz.

Yeniden başlatma/durdurma isteğe bağlı geri sayımla yapılır: oyunculara 10 dk, 5 dk, 1 dk ve 10 sn önce uyarı.
Komut ve duyurular güvenli moddan geçer: engellenen komut gönderilmez. Yeniden başlatma, durdurma, başlatma
ve yedek panelin kendi işlemleridir (bakım gibi) ve güvenli moda takılmaz.
"""
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

from .config import N_

ACTIONS = {
    "restart": N_("Yeniden başlat"),
    "stop": N_("Durdur"),
    "start": N_("Başlat"),
    "backup": N_("Yedek al"),
    "command": N_("Komut çalıştır"),
    "announce": N_("Duyuru yap"),
    "report": N_("Esplora raporu"),
}
WARN_AT = (600, 300, 60, 10)
WARN_TEXT = {
    "restart": {
        600: N_("Sunucu 10 dakika içinde yeniden başlatılacak."),
        300: N_("Sunucu 5 dakika içinde yeniden başlatılacak."),
        60: N_("Sunucu 1 dakika içinde yeniden başlatılacak."),
        10: N_("Sunucu 10 saniye içinde yeniden başlatılıyor!"),
    },
    "stop": {
        600: N_("Sunucu 10 dakika içinde kapanacak."),
        300: N_("Sunucu 5 dakika içinde kapanacak."),
        60: N_("Sunucu 1 dakika içinde kapanacak."),
        10: N_("Sunucu 10 saniye içinde kapanıyor!"),
    },
}
LATE_LIMIT = 120          # bu kadar saniyeden geç fark edilen çalışma (uyku, donma) atlanır
STOP_WAIT = 180           # yeniden başlatmada sunucunun kapanmasını en fazla bu kadar bekle

DEFAULTS = {"enabled": True, "name": "", "action": "restart", "mode": "weekly", "days": [0, 1, 2, 3, 4, 5, 6],
            "time": "04:00", "every": 60, "countdown": True, "command": "", "message": "", "last_run": ""}

PRESETS = [
    (N_("Her gece 04:00'te yeniden başlat"), {"action": "restart", "mode": "weekly", "time": "04:00",
                                              "countdown": True}),
    (N_("Her 6 saatte bir yedek al"), {"action": "backup", "mode": "interval", "every": 360}),
    (N_("Her 30 dakikada bir duyuru"), {"action": "announce", "mode": "interval", "every": 30,
                                       "message": N_("Sunucumuza hoş geldin! Kurallar için /rules yaz.")}),
    (N_("Her gece 03:55'te yedek al"), {"action": "backup", "mode": "weekly", "time": "03:55"}),
    (N_("Her sabah 09:00'da Esplora raporu"), {"action": "report", "mode": "weekly", "time": "09:00"}),
]


def new_task(**kw):
    t = {**DEFAULTS, **kw, "id": uuid.uuid4().hex[:8]}
    return normalize(t)


def normalize(t):
    t = {**DEFAULTS, **(t or {})}
    t["id"] = str(t.get("id") or uuid.uuid4().hex[:8])
    t["enabled"] = bool(t["enabled"])
    t["name"] = str(t["name"] or "")[:60]
    if t["action"] not in ACTIONS:
        t["action"] = DEFAULTS["action"]
    if t["mode"] not in ("weekly", "interval"):
        t["mode"] = "weekly"
    t["days"] = sorted({int(d) for d in t.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
    try:
        h, m = (int(x) for x in str(t["time"]).split(":", 1))
        t["time"] = f"{max(0, min(23, h)):02}:{max(0, min(59, m)):02}"
    except ValueError:
        t["time"] = DEFAULTS["time"]
    try:
        t["every"] = max(5, min(24 * 60, int(t["every"])))        # her gün gece yarısından hizalanır
    except (TypeError, ValueError):
        t["every"] = DEFAULTS["every"]
    t["countdown"] = bool(t["countdown"])
    t["command"] = str(t["command"] or "")[:4000]
    t["message"] = str(t["message"] or "")[:256]
    t["last_run"] = str(t.get("last_run") or "")
    return t


def lead(task):
    """Geri sayım süresi (saniye): uyarılar görev zamanından bu kadar önce başlar."""
    return max(WARN_AT) if task["action"] in WARN_TEXT and task["countdown"] else 0


def occurrences(task, start, end):
    """start < T <= end aralığındaki çalışma zamanları (sıralı)."""
    out = []
    if task["mode"] == "interval":
        step = timedelta(minutes=task["every"])
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while day <= end:
            k = max(0, int((start - day) / step))
            t = day + k * step
            while t < day + timedelta(days=1) and t <= end:
                if t > start:
                    out.append(t)
                t += step
            day += timedelta(days=1)
        return out
    if not task["days"]:
        return out
    h, m = (int(x) for x in task["time"].split(":"))
    day = start.replace(hour=h, minute=m, second=0, microsecond=0) - timedelta(days=1)
    while day <= end:
        if day > start and day.weekday() in task["days"]:
            out.append(day)
        day += timedelta(days=1)
    return out


def next_run(task, now=None):
    """Sıradaki çalışma zamanı (kapalı ya da gün seçilmemişse None)."""
    if not task["enabled"]:
        return None
    now = now or datetime.now()
    occ = occurrences(task, now, now + timedelta(days=8))
    return occ[0] if occ else None


class Scheduler:
    def __init__(self, config, server, backups):
        self.config = config
        self.server = server
        self.backups = backups
        self.tr = lambda text, **kw: text.format(**kw) if kw else text   # arayüz panel diline çevirir
        self.results = {}          # görev id -> (zaman, durum metni) — yalnızca bu oturumda
        self.on_change = None      # fn(): sunucu durumu değişti (arayüz yenilensin)
        self.notify = None         # fn(görev adı, durum) — Discord bildirimi (core.discord)
        self._last = None
        self._busy = set()         # sürmekte olan yeniden başlatma/yedek
        self.reporter = None       # fn(saat) -> (başlık, satırlar) — core.report
        self.on_report = None      # fn(başlık, satırlar) — Discord

    # ------------------------------------------------------------ görevler
    @property
    def tasks(self):
        return [normalize(t) for t in self.config.get("scheduled_tasks") or []]

    def save(self, tasks):
        self.config.set("scheduled_tasks", [normalize(t) for t in tasks])

    def upsert(self, task):
        task = normalize(task)
        tasks = self.tasks
        for i, t in enumerate(tasks):
            if t["id"] == task["id"]:
                tasks[i] = task
                break
        else:
            tasks.append(task)
        self.save(tasks)
        return task

    def remove(self, tid):
        self.save([t for t in self.tasks if t["id"] != tid])
        self.results.pop(tid, None)

    def set_enabled(self, tid, on):
        tasks = self.tasks
        for t in tasks:
            if t["id"] == tid:
                t["enabled"] = bool(on)
        self.save(tasks)

    @property
    def any_enabled(self):
        return any(t.get("enabled", True) for t in self.config.get("scheduled_tasks") or [])

    # ------------------------------------------------------------ zamanlayıcı
    def tick(self, now=None):
        """Her saniye çağrılır. Bir görev çalıştıysa True."""
        now = now or datetime.now()
        prev, self._last = self._last, now
        if prev is None or now <= prev:
            return False                                    # ilk tur ya da saat geri alındı
        if (now - prev).total_seconds() > LATE_LIMIT:       # uyku/donma: aradaki her şey atlanır
            return False
        ran = False
        for task in self.tasks:
            if not task["enabled"]:
                continue
            ld = lead(task)
            if ld:                                          # geri sayım uyarıları
                for sec in WARN_AT:
                    for t in occurrences(task, prev + timedelta(seconds=sec), now + timedelta(seconds=sec)):
                        if self.server.is_running:
                            self.server.try_send("say §c§l[!] §e" + self.tr(WARN_TEXT[task["action"]][sec]))
            for t in occurrences(task, prev, now):
                self.run(task, when=t)
                ran = True
        return ran

    # ------------------------------------------------------------ çalıştırma
    def _log(self, text):
        line = "[Spypaper] " + text
        self.server.history.append(line)
        if self.server.on_line:
            self.server.on_line(line)

    def _result(self, task, status, notify=False):
        self.results[task["id"]] = (datetime.now(), status)
        if notify and self.notify:
            try:
                self.notify(self.title(task), status)
            except Exception as e:
                print(f"[görev] bildirim: {e}")

    def _mark(self, task, when):
        tasks = self.tasks
        for t in tasks:
            if t["id"] == task["id"]:
                t["last_run"] = when.isoformat(timespec="seconds")
        self.save(tasks)

    def title(self, task):
        return task["name"] or self.tr(ACTIONS[task["action"]])

    def run(self, task, when=None):
        """Görevi şimdi çalıştırır. Durum metnini döndürür (çevrilmiş)."""
        when = when or datetime.now()
        try:
            status = getattr(self, "_do_" + task["action"])(task)
        except Exception as e:
            status = self.tr("Hata: {error}", error=str(e))
        self._mark(task, when)
        self._result(task, status, notify=task["action"] not in ("backup", "report"))   # yedeğin sonucu bitince bildirilir
        self._log(self.tr("Zamanlanmış görev '{name}': {status}", name=self.title(task), status=status))
        if self.on_change:
            self.on_change()
        return status

    def _skip_stopped(self):
        return self.tr("Atlandı: sunucu kapalı.")

    def _do_restart(self, task):
        if not self.server.is_running:
            return self._skip_stopped()
        if task["id"] in self._busy:
            return self.tr("Atlandı: önceki çalışma sürüyor.")
        self._busy.add(task["id"])
        proc = self.server.process
        self.server.stop()

        def work():
            try:
                end = time.time() + STOP_WAIT
                while proc.poll() is None and time.time() < end:
                    time.sleep(0.5)
                if proc.poll() is None:
                    self._result(task, self.tr("Hata: sunucu {s} saniyede kapanmadı.", s=STOP_WAIT))
                    return
                time.sleep(2)                               # dosya kilitleri bırakılsın
                if not self.server.is_running:
                    self.server.start()
            except Exception as e:
                self._result(task, self.tr("Hata: {error}", error=str(e)))
                self._log(self.tr("Zamanlanmış görev '{name}': {status}", name=self.title(task),
                                  status=self.tr("Hata: {error}", error=str(e))))
            finally:
                self._busy.discard(task["id"])
        threading.Thread(target=work, daemon=True).start()
        return self.tr("Yeniden başlatılıyor.")

    def _do_stop(self, task):
        if not self.server.is_running:
            return self._skip_stopped()
        self.server.stop()
        return self.tr("Durduruldu.")

    def _do_start(self, task):
        if self.server.is_running:
            return self.tr("Atlandı: sunucu zaten açık.")
        self.server.start()
        return self.tr("Başlatıldı.")

    def _do_backup(self, task):
        if task["id"] in self._busy:
            return self.tr("Atlandı: önceki yedek sürüyor.")
        self._busy.add(task["id"])
        running = self.server.is_running
        if running:
            self.server.try_send("save-all flush")

        def work():
            try:
                if running:
                    time.sleep(3)                           # save-all bitsin
                path = self.backups.create()
                self._result(task, self.tr("Yedek alındı: {file}", file=os.path.basename(path)), notify=True)
            except Exception as e:
                msg = self.tr("Yedek alınamadı: {err}", err=self.tr(str(e)))
                self._result(task, msg, notify=True)
                self._log(self.tr("Zamanlanmış görev '{name}': {status}", name=self.title(task), status=msg))
            finally:
                self._busy.discard(task["id"])
        threading.Thread(target=work, daemon=True).start()
        return self.tr("Yedek alınıyor…")

    def _send_checked(self, cmd):
        from .safemode import check
        verdict, why = check(self.config.get("safe_mode"), cmd)
        if verdict == "block":
            return self.tr(why)
        self.server.send(cmd)
        return ""

    def _do_command(self, task):
        if not self.server.is_running:
            return self._skip_stopped()
        cmds = [c.strip().lstrip("/") for c in task["command"].splitlines() if c.strip()]
        if not cmds:
            return self.tr("Atlandı: komut yok.")
        blocked = [c for c in cmds if self._send_checked(c)]
        if blocked:
            return self.tr("{n} komut gönderildi, {k} komut güvenli mod yüzünden engellendi.",
                           n=len(cmds) - len(blocked), k=len(blocked))
        return self.tr("{n} komut gönderildi.", n=len(cmds))

    def _do_announce(self, task):
        if not self.server.is_running:
            return self._skip_stopped()
        msg = task["message"].strip()
        if not msg:
            return self.tr("Atlandı: mesaj yok.")
        err = self._send_checked("say " + msg)
        return err or self.tr("Duyuru gönderildi.")

    def _do_report(self, task):
        """Rapor dönemi: son çalışmadan bu yana (en az 1 saat, en fazla 7 gün); ilk çalışmada 24 saat."""
        if not self.reporter:
            return self.tr("Atlandı: rapor hazır değil.")
        hours = 24
        if task.get("last_run"):
            try:
                hours = (datetime.now() - datetime.fromisoformat(task["last_run"])).total_seconds() / 3600
            except ValueError:
                pass
        hours = max(1, min(24 * 7, round(hours)))
        title, lines = self.reporter(hours)
        if self.on_report:
            try:
                self.on_report(title, lines)
            except Exception as e:
                print(f"[görev] rapor: {e}")
        return self.tr("Rapor hazırlandı ({n} saat).", n=hours)
