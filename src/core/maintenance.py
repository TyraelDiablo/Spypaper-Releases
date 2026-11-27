"""Bakım modu: MOTD, whitelist, oyuncuları atma, otomatik yedek ve haftalık plan.

Bakım başlarken:
  * whitelist.json yedeklenir ve boşaltılır, whitelist açılır (whitelist zaten açık olan sunucularda
    da kimse giremesin; OP'ler Minecraft'ta whitelist'e takılmaz)
  * içerideki OP olmayan oyuncular atılır, MOTD değişir, dünya kaydedilip yedek alınır
Bakım biterken whitelist.json'ın eski hali (bakım sırasında eklenenlerle birlikte), whitelist'in
eski açık/kapalı durumu ve eski MOTD geri gelir.

Bakımın durumu sunucunun profilinde ("maintenance_state") ve ayrıca
<sunucu>/backups/whitelist_maintenance.json dosyasında tutulur; panel bakım sırasında kapansa ya da
çökse bile whitelist kaybolmaz, açılışta bakım kaldığı yerden sürer.

Plan ("maintenance_schedule"): seçili günlerde HH:MM'de başlar, süre dolunca kendiliğinden biter.
Zamanlayıcıyı arayüz katmanı çalıştırır (her saniye tick()).
"""
import json
import os
import threading
from datetime import datetime, timedelta

from . import playermsg
from .config import N_

MOTD_LINES = (N_("Sunucu şu an bakımda."), N_("Lütfen daha sonra tekrar dene."))
DEFAULT_MOTD = "A Minecraft Server"
WARN_AT = (600, 300, 60, 10)                     # bakımdan önce oyunculara uyarı (saniye)
SCHEDULE_DEFAULTS = {"enabled": False, "days": [0], "time": "04:00", "duration": 30, "backup": True}

WARN_TEXT = {
    600: N_("Sunucu 10 dakika içinde bakıma girecek."),
    300: N_("Sunucu 5 dakika içinde bakıma girecek."),
    60: N_("Sunucu 1 dakika içinde bakıma girecek."),
    10: N_("Sunucu 10 saniye içinde bakıma girecek!"),
}
KICK_TEXT = N_("Sunucu bakımda. Lütfen daha sonra tekrar dene.")


def _parse(ts):
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def _iso(dt):
    return dt.isoformat(timespec="seconds") if dt else ""


def normalize_schedule(s):
    s = {**SCHEDULE_DEFAULTS, **(s or {})}
    s["enabled"] = bool(s["enabled"])
    s["days"] = sorted({int(d) for d in s.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
    try:
        h, m = (int(x) for x in str(s["time"]).split(":", 1))
        s["time"] = f"{max(0, min(23, h)):02}:{max(0, min(59, m)):02}"
    except ValueError:
        s["time"] = SCHEDULE_DEFAULTS["time"]
    try:
        s["duration"] = max(5, min(24 * 60, int(s["duration"])))
    except (TypeError, ValueError):
        s["duration"] = SCHEDULE_DEFAULTS["duration"]
    s["backup"] = bool(s["backup"])
    return s


def next_window(schedule, now=None):
    """(başlangıç, bitiş): şu an içinde bulunulan ya da sıradaki bakım penceresi. Plan kapalıysa None."""
    s = normalize_schedule(schedule)
    if not s["enabled"] or not s["days"]:
        return None
    now = now or datetime.now()
    h, m = (int(x) for x in s["time"].split(":"))
    dur = timedelta(minutes=s["duration"])
    base = now.replace(hour=h, minute=m, second=0, microsecond=0)
    for off in range(-1, 8):                        # dün başlayıp hâlâ süren pencere de sayılır
        start = base + timedelta(days=off)
        if start.weekday() in s["days"] and start + dur > now:
            return start, start + dur
    return None


class Maintenance:
    def __init__(self, config, server, properties, backups, online=None):
        self.config = config
        self.server = server
        self.props = properties
        self.backups = backups
        self.online = online or (lambda: [])          # çevrimiçi oyuncu adları
        self.tr = lambda s, **kw: s.format(**kw) if kw else s   # arayüz panel diline çevirir
        self.notify = None                             # fn(started: bool) — Discord bildirimi (core.discord)
        self._warned = set()

    # ------------------------------------------------------------ durum
    @property
    def state(self):
        return dict(self.config.get("maintenance_state") or {})

    def _save_state(self, st):
        self.config.set("maintenance_state", st)

    @property
    def active(self):
        return bool(self.state.get("active"))

    @property
    def schedule(self):
        return normalize_schedule(self.config.get("maintenance_schedule"))

    def set_schedule(self, s):
        self.config.set("maintenance_schedule", normalize_schedule(s))
        self._warned.clear()

    def until(self):
        """Otomatik bitiş zamanı (elle başlatılan bakımda None)."""
        return _parse(self.state.get("until"))

    def next_start(self, now=None):
        w = next_window(self.schedule, now)
        if not w:
            return None
        if _iso(w[0]) == self.state.get("last_window"):      # bu pencere zaten işlendi (elle bitirildi vb.)
            w = next_window(self.schedule, w[1] + timedelta(seconds=1))
        return w[0] if w else None

    def remaining(self):
        """Sıradaki otomatik bakıma kalan süre (plan yoksa ya da bakımdaysa None)."""
        if self.active:
            return None
        n = self.next_start()
        return max(timedelta(0), n - datetime.now()) if n else None

    def motd(self):
        a, b = (self.tr(x) for x in MOTD_LINES)
        return f"§c§l{a}\\n§e{b}"

    # ------------------------------------------------------------ zamanlayıcı
    def tick(self, now=None):
        """Her saniye çağrılır. Bakım başladı/bittiyse 'started' / 'ended', yoksa None."""
        now = now or datetime.now()
        if self.active:
            until = self.until()
            if until and now >= until:
                self.disable()
                return "ended"
            return None
        w = next_window(self.schedule, now)
        if not w or _iso(w[0]) == self.state.get("last_window"):
            return None
        start, end = w
        left = (start - now).total_seconds()
        if left > 0:
            for sec in WARN_AT:
                if left <= sec and (start, sec) not in self._warned:
                    self._warned.add((start, sec))
                    if left > sec - 2:                 # uyarı zamanı kaçırıldıysa (panel yeni açıldı) geç
                        playermsg.announce(self.server, WARN_TEXT[sec], self.tr)
            return None
        self.enable(until=end, window=start, backup=self.schedule["backup"], wait=False)
        return "started"

    # ------------------------------------------------------------ whitelist
    @property
    def _be(self):
        from .bedrock import is_bedrock
        return is_bedrock(self.config.server_path)

    @property
    def _k(self):
        """Java / Bedrock farkları: dosya, ayar ve komut adları."""
        if self._be:
            return {"file": "allowlist.json", "prop": "allow-list", "motd": "server-name", "cmd": "allowlist"}
        return {"file": "whitelist.json", "prop": "white-list", "motd": "motd", "cmd": "whitelist"}

    def _motd_value(self):
        if self._be:                                   # Bedrock sunucu adında renk kodu ve satır sonu yok
            a, b = (self.tr(x) for x in MOTD_LINES)
            return f"{a} - {b}"
        return self.motd()

    @property
    def _wl_file(self):
        return os.path.join(self.config.server_path, self._k["file"])

    @property
    def _wl_backup(self):
        return os.path.join(self.config.server_path, "backups", "whitelist_maintenance.json")

    def _read_json(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, type(default)) else default
        except (OSError, ValueError):
            return default

    def _write_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def _whitelist_on(self):
        if not self.props.exists:
            return False
        return self.props.load().get(self._k["prop"], "false").lower() == "true"

    def _ops(self):
        if self._be:                                   # Bedrock'ta izin listesi operatörleri de dışarıda tutar
            return set()
        return {str(o.get("name", "")).lower() for o in
                self._read_json(os.path.join(self.config.server_path, "ops.json"), [])}

    # ------------------------------------------------------------ aç / kapat
    def enable(self, until=None, window=None, backup=True, wait=True):
        """Bakımı başlatır. Alınan yedeğin yolunu döndürür (alınamadıysa ya da istenmediyse None).
        wait=False: yedek arka planda alınır (otomatik bakım ve telefon; panel donmasın)."""
        if self.active:
            return None
        now = datetime.now()
        if window is None:                             # elle başlatıldı: içinde bulunulan plan penceresi işlenmiş sayılır
            w = next_window(self.schedule, now)
            if w and w[0] <= now:
                window = w[0]
        st = {"active": True, "since": _iso(now), "until": _iso(until),
              "auto": until is not None, "last_window": _iso(window) or self.state.get("last_window", "")}
        if self.props.exists:
            cur = self.props.load()
            st["motd"] = cur.get(self._k["motd"], "")
            st["whitelist_was_on"] = cur.get(self._k["prop"], "false").lower() == "true"
        entries = self._read_json(self._wl_file, [])
        st["whitelist"] = entries
        try:                                           # durum diske yazılmadan whitelist'e dokunulmaz
            self._write_json(self._wl_backup, entries)
        except OSError:
            pass
        self._save_state(st)

        running = self.server.is_running
        try:
            self._write_json(self._wl_file, [])
        except OSError:
            pass
        if self.props.exists:
            self.props.save({self._k["motd"]: self._motd_value(), self._k["prop"]: True})
        if running:
            self.server.try_send(f"{self._k['cmd']} reload")
            self.server.try_send(f"{self._k['cmd']} on")
            ops = self._ops()
            for name in self.online():
                if name.lower() not in ops:
                    playermsg.kick(self.server, name, KICK_TEXT, self.tr)
            self.server.try_send("save-all flush")
        self._notify(True)
        if not backup:
            return None
        if not wait:
            def work():
                try:
                    self.backups.create()
                except Exception as e:
                    print(f"[bakım] yedek alınamadı: {e}")
            threading.Thread(target=work, daemon=True).start()
            return None
        try:
            return self.backups.create()
        except Exception:
            return None

    def disable(self):
        st = self.state
        if not st.get("active"):
            return
        old = st.get("whitelist")
        if old is None:
            old = self._read_json(self._wl_backup, [])
        now = self._read_json(self._wl_file, [])      # bakımda elle eklenenler de kalsın
        seen = {str(e.get("uuid") or e.get("xuid") or e.get("name", "")).lower() for e in old if isinstance(e, dict)}
        merged = list(old) + [e for e in now if isinstance(e, dict)
                              and str(e.get("uuid") or e.get("xuid") or e.get("name", "")).lower() not in seen]
        try:
            self._write_json(self._wl_file, merged)
        except OSError:
            pass
        was_on = bool(st.get("whitelist_was_on"))
        if self.props.exists:
            motd = st.get("motd")
            vals = {self._k["prop"]: was_on}
            if motd is not None:
                vals[self._k["motd"]] = motd if motd and motd != self._motd_value() else (
                    "Bedrock server" if self._be else DEFAULT_MOTD)
            self.props.save(vals)
        if self.server.is_running:
            self.server.try_send(f"{self._k['cmd']} reload")
            if not was_on:
                self.server.try_send(f"{self._k['cmd']} off")
        self._save_state({"active": False, "last_window": st.get("last_window", "")})
        try:
            os.remove(self._wl_backup)
        except OSError:
            pass
        self._warned.clear()
        self._notify(False)

    def _notify(self, started):
        if self.notify:
            try:
                self.notify(started)
            except Exception as e:
                print(f"[bakım] bildirim: {e}")
