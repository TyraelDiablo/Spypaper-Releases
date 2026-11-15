"""Spypaper Remote: telefondan sunucuları izleme ve başlat/durdur.

Masaüstündeki Spypaper açıkken küçük bir web sunucusu çalışır; telefon tarayıcıdan bağlanır
(ana ekrana eklenince uygulama gibi açılır). Veritabanı yoktur:
  * eşleşen cihazlar config.json'da "remote.devices" altında, anahtarın yalnızca SHA-256 özeti tutulur
  * tek kullanımlık eşleşme kodları yalnızca bellekte, 2 dakika geçerli
  * telefon anahtarı HttpOnly çerez olarak saklar (sayfadaki JavaScript bile okuyamaz)
Telefona yalnızca özet veri gider: durum, RAM/CPU, oyuncuların can/açlık/zırh/seviye/oyun modu,
son log satırları (IP adresleri gizlenir). Serbest komut gönderilemez.
Telefonun yapabildikleri cihaz başına bilgisayardan verilen izinlere bağlıdır (PERMS): başlat/durdur,
bakım aç/kapa, sunucu ayarları. Ayar ve bakım izni yeni cihazlarda kapalı gelir. PIN'li sunucularda
her değişiklikte PIN sorulur. Güvenli mod "Yüksek" (salt okunur) ise telefondan değişiklik yapılamaz.
Java yolu ve jar adı telefondan değiştirilemez (bilgisayarda istenen bir programı çalıştırmaya
dönüşebilir); RCON/sorgu/yönetim sunucusu ayarları ve parolalar telefona hiç gönderilmez.

Arayüzden bağımsızdır. Arayüz bir "sağlayıcı" verir (bkz. Provider) ve sunucu durdurma/başlatma gibi
işleri kendi ana thread'inde yapar.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
from datetime import date, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import N_, detect_version, is_modded, resource_dir
from .logwatch import LogWatcher, ProcessMetrics, online_timeline
from .players import PlayerService

DEFAULT_PORT = 8765
CODE_TTL = 120                    # eşleşme kodunun geçerlilik süresi (sn)
COOKIE = "spr"
COOKIE_AGE = 365 * 24 * 3600
MAX_BODY = 64 * 1024              # server.properties'in tamamı gönderilebilsin
WEB_DIR = "remote_web"

REMOTE_DEFAULTS = {"enabled": False, "port": DEFAULT_PORT, "allow_control": True, "devices": []}
PERMS = {"control": True, "maintenance": False, "settings": False}     # yeni cihazın izinleri

# server.properties: telefona hiç gitmeyenler ve telefondan değiştirilemeyenler
_PROP_HIDDEN = re.compile(r"password|secret|^rcon\.|^query\.|^management-server|^enable-rcon$|^enable-query$", re.I)
_RAM_RE = re.compile(r"^\d{1,6}[MG]$", re.I)

# Telefon arayüzündeki metinler (tools/extract_strings.py buradan toplar, telefona panel dilinde gider)
WEB_STRINGS = [
    N_("Sunucular"), N_("Çevrimiçi"), N_("Kapalı"), N_("Başlatılıyor"), N_("Durduruluyor"),
    N_("Panel dışında çalışıyor"), N_("Başlat"), N_("Durdur"), N_("Yeniden Başlat"), N_("Oyuncular"),
    N_("Günlük"), N_("Haritayı Aç"), N_("Henüz oyuncu yok."), N_("Log dosyası bulunamadı."),
    N_("Bu cihaz eşli değil"),
    N_("Masaüstündeki Spypaper'da ☰ → Spypaper Remote → Yeni Cihaz Eşle'ye bas ve çıkan QR kodu telefonun kamerasıyla okut."),
    N_("Bu cihazı eşle"), N_("Cihaz adı"), N_("Eşle"), N_("Eşleşme kodu geçersiz ya da süresi dolmuş. Panelde yeni bir QR oluştur."),
    N_("Bağlantı kesildi. Masaüstündeki Spypaper açık mı?"), N_("PIN"), N_("Bu sunucu PIN ile korunuyor."),
    N_("İptal"), N_("Tamam"), N_("Sunucu durdurulsun mu?"), N_("Sunucu yeniden başlatılsın mı?"),
    N_("Bu cihazın eşleşmesini kaldır"), N_("Eşleşme kaldırılsın mı? Tekrar bağlanmak için yeni QR gerekir."),
    N_("Hayatta Kalma"), N_("Yaratıcı"), N_("Macera"), N_("İzleyici"), N_("RAM"), N_("CPU"),
    N_("Seviye {n}"), N_("Telefondan kontrol panelde kapalı."), N_("Son güncelleme: {t}"),
    N_("Çevrimdışı"), N_("Can"), N_("Açlık"), N_("Zırh"), N_("Spypaper Remote"),
    N_("Çok fazla yanlış PIN. 5 dakika sonra tekrar dene."), N_("Yanlış PIN."), N_("Bugünkü giriş"),
    N_("Sunucu klasörü bulunamadı."),
    N_("Ayarlar"), N_("Dil"), N_("Otomatik (telefonun dili)"), N_("Kaydet"), N_("Kaydedildi."),
    N_("Bakım"), N_("Bakım modu aktif"), N_("Normal mod"), N_("Bakım Modunu Başlat"), N_("Bakım Modunu Bitir"),
    N_("Bakım modu başlatılsın mı?"), N_("Otomatik bitiş: {time}"), N_("Bakım elle bitirilene kadar sürer."),
    N_("Sonraki otomatik bakım: {time}"), N_("Otomatik bakım kapalı."), N_("Otomatik bakım"),
    N_("Otomatik bakımı aç"), N_("Başlangıç saati"), N_("Süre (dk)"), N_("Bakım başlarken yedek al"),
    N_("Pzt"), N_("Sal"), N_("Çar"), N_("Per"), N_("Cum"), N_("Cmt"), N_("Paz"),
    N_("RAM (min / max)"), N_("Java"), N_("Jar dosyası"), N_("Bunlar yalnızca bilgisayardan değiştirilebilir."),
    N_("Değişikliklerin çoğu sunucu yeniden başlatılınca geçerli olur"), N_("Ayar ara…"),
    N_("Bu cihazın izinleri"), N_("Başlat / durdur"), N_("Bakım"), N_("Sunucu ayarları"),
    N_("İzinler bilgisayardaki Spypaper'dan verilir: ☰ → Spypaper Remote → Eşli cihazlar."),
    N_("Bu cihaza izin verilmemiş."),
]

STATE_LABEL = {"stopped": N_("Kapalı"), "starting": N_("Başlatılıyor"), "running": N_("Çevrimiçi"),
               "stopping": N_("Durduruluyor"), "external": N_("Panel dışında çalışıyor")}

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6 = re.compile(r"\[?(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\]?")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|§[0-9a-fk-or]", re.I)


def mask_ips(text):
    """Log satırlarındaki IP adreslerini gizler (oyuncuların IP'si telefona gitmez)."""
    text = _IPV4.sub("•.•.•.•", text)
    return _IPV6.sub(lambda m: m.group(0) if m.group(0).count(":") < 3 else "•:•:•", text)


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def local_addresses():
    """Telefonun bağlanabileceği adresler: önce ev ağı (192.168…, 10…), sonra Tailscale (100.64/10)."""
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))            # paket gönderilmez; yalnızca çıkış arayüzü seçilir
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out = []
    for a in found:
        try:
            ip = ipaddress.ip_address(a)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or a in out:
            continue
        out.append(a)

    def rank(a):
        ip = ipaddress.ip_address(a)
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return 1                                   # Tailscale / CGNAT
        return 0 if ip.is_private else 2
    return sorted(out, key=rank) or ["127.0.0.1"]


def is_tailscale(addr):
    try:
        return ipaddress.ip_address(addr) in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


def device_label(user_agent):
    ua = user_agent or ""
    osn = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua
           else "Windows" if "Windows" in ua else "Mac" if "Mac OS" in ua else "Linux" if "Linux" in ua else "")
    br = ("Edge" if "Edg/" in ua else "Samsung" if "SamsungBrowser" in ua else "Firefox" if "Firefox" in ua
          else "Chrome" if "Chrome" in ua else "Safari" if "Safari" in ua else "")
    return " · ".join(x for x in (osn, br) if x) or "Telefon"


def tail_lines(path, n=150, max_bytes=96 * 1024):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            data = f.read()
    except OSError:
        return None
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]                               # yarım ilk satır
    return lines[-n:]


class Provider:
    """Arayüzün doldurduğu köprü. Varsayılanı testler için düz çağrılardır."""

    def servers(self):
        """[ServerProfile]"""
        return []

    def app(self, sid):
        """Sunucunun App nesnesi ya da None (yalnızca okunur: server.state, metrics)."""
        return None

    def control(self, sid, action):
        """'start' | 'stop' | 'restart' — arayüzün ana thread'inde çalışır. Hata metni (str) ya da None."""
        return "not supported"

    def translate(self, text, **kw):
        return text.format(**kw) if kw else text

    def language(self):
        """Panelin dili: (kod, sağdan_sola)."""
        return "tr", False

    def languages(self):
        """[(kod, ad)] — telefonda seçilebilecek diller."""
        return [("tr", "Türkçe"), ("en", "English")]

    def table(self, lang):
        """Dilin çeviri tablosu {türkçe: çeviri} (eksikler İngilizceden). Türkçe için {}."""
        return {}

    def is_rtl(self, lang):
        return lang in ("ar", "he", "fa", "ur")

    def settings_get(self, sid):
        """Telefona gidecek sunucu ayarları (ana thread)."""
        return {}

    def settings_save(self, sid, data):
        """Ayarları uygular (ana thread). Hata metni ya da None."""
        return "not supported"

    def maintenance(self, sid, on):
        """Bakımı aç/kapat (ana thread). Hata metni ya da None."""
        return "not supported"

    def icons_dir(self):
        return ""

    def save_remote(self, data):
        """remote ayarlarını kalıcı yazar (ana thread)."""

    def on_change(self):
        """Cihaz listesi değişti (arayüz yenilensin)."""


class _NoProcess:
    is_running = False
    process = None


class _ServerCache:
    """Bir sunucu için telefona özel log takibi ve oyuncu özeti (panelinkinden bağımsız)."""

    def __init__(self, prof):
        path = prof.server_path
        self.path = path
        self.metrics = ProcessMetrics(_NoProcess(), prof)    # panel dışında açılmış sunucuyu bulmak için
        self.logs = LogWatcher(path)
        self.players = PlayerService(path)
        self.details = {}                               # dat yolu -> (mtime, özet)
        self.lock = threading.Lock()

    def online(self):
        with self.lock:
            try:
                self.logs.poll()
            except Exception:
                pass
            evs = self.logs.events
            _, online = online_timeline(evs)
            today = date.today()
            joins = sum(1 for e in evs if e.kind == "join" and e.time.date() == today)
            return sorted(online, key=str.lower), joins

    def player_rows(self, online_names, limit=60):
        with self.lock:
            try:
                plist = self.players.list_players(set(online_names))
            except Exception:
                return []
            rows = []
            for p in plist[:limit]:
                row = {"name": p.name, "online": p.online}
                try:
                    mt = os.path.getmtime(p.data_file)
                    cached = self.details.get(p.data_file)
                    if cached and cached[0] == mt:
                        summary = cached[1]
                    else:
                        d = self.players.details(p)
                        summary = None if d is None else {
                            "health": round(d.health, 1), "food": d.food, "armor": d.armor_points,
                            "absorption": round(d.absorption, 1), "level": d.xp_level,
                            "progress": round(d.xp_progress, 3), "gamemode": d.gamemode,
                        }
                        self.details[p.data_file] = (mt, summary)
                    if summary:
                        row.update(summary)
                except Exception:
                    pass
                rows.append(row)
            return rows


class RemoteServer:
    def __init__(self, provider, data=None):
        self.p = provider
        self.data = json.loads(json.dumps({**REMOTE_DEFAULTS, **(data or {})}))
        self.lock = threading.RLock()
        self.codes = {}                                  # kod -> son geçerlilik zamanı
        self.fails = {}                                  # (tür, anahtar) -> [zamanlar]
        self.caches = {}
        self.httpd = None
        self.thread = None
        self.error = ""
        self.started_at = None
        self._tables = {}

    # ------------------------------------------------------------ dil
    def tr(self, lang):
        """lang diline çeviren t(text, **kw)."""
        tbl = self._tables.get(lang)
        if tbl is None:
            try:
                tbl = self._tables[lang] = dict(self.p.table(lang) or {})
            except Exception:
                tbl = {}

        def t(text, **kw):
            out = tbl.get(text, text)
            if kw:
                try:
                    return out.format(**kw)
                except (KeyError, IndexError, ValueError):
                    return text.format(**kw)
            return out
        return t

    def resolve_lang(self, dev, nav=""):
        """Cihazın seçtiği dil; yoksa telefonun dili; o da yoksa İngilizce."""
        codes = [c for c, _ in self.p.languages()]
        want = (dev or {}).get("lang") or ""
        if want in codes:
            return want
        for cand in [x.split(";")[0].strip() for x in (nav or "").split(",") if x.strip()][:6]:
            c = cand.replace("-", "_")
            low = {x.lower(): x for x in codes}
            if c.lower() in low:
                return low[c.lower()]
            base = c.split("_")[0].lower()
            for x in codes:
                if x.lower() == base or x.lower().startswith(base + "_"):
                    return x
        return "en" if "en" in codes else (codes[0] if codes else "tr")

    # ------------------------------------------------------------ izinler
    def perm(self, dev, key):
        if not self.data.get("allow_control", True):
            return False
        perms = {**PERMS, **((dev or {}).get("perms") or {})}
        return bool(perms.get(key))

    def perms(self, dev):
        return {k: self.perm(dev, k) for k in PERMS}

    def set_perm(self, dev_id, key, value):
        if key not in PERMS:
            return False
        with self.lock:
            for d in self.data.get("devices", []):
                if d.get("id") == dev_id:
                    d.setdefault("perms", dict(PERMS))[key] = bool(value)
                    break
            else:
                return False
        self._persist(notify=False)
        return True

    def set_device_lang(self, dev_id, lang):
        codes = {c for c, _ in self.p.languages()}
        if lang and lang not in codes:
            return False
        with self.lock:
            for d in self.data.get("devices", []):
                if d.get("id") == dev_id:
                    d["lang"] = lang
                    break
        self._persist(notify=False)
        return True

    # ------------------------------------------------------------ yaşam döngüsü
    @property
    def running(self):
        return self.httpd is not None

    @property
    def port(self):
        return int(self.data.get("port") or DEFAULT_PORT)

    def start(self, host="0.0.0.0"):
        if self.httpd:
            return True
        server = self

        class Handler(_Handler):
            remote = server
        try:
            self.httpd = _QuietServer((host, self.port), Handler)
        except OSError as e:
            self.httpd, self.error = None, str(e)
            return False
        self.httpd.daemon_threads = True
        self.error = ""
        self.started_at = time.time()
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        h, self.httpd = self.httpd, None
        if h:
            h.shutdown()
            h.server_close()

    # ------------------------------------------------------------ eşleşme
    def new_code(self):
        with self.lock:
            now = time.time()
            self.codes = {c: exp for c, exp in self.codes.items() if exp > now}
            code = secrets.token_urlsafe(12)
            self.codes[code] = now + CODE_TTL
            return code

    def code_valid(self, code):
        with self.lock:
            exp = self.codes.get(code or "")
            return bool(exp and exp > time.time())

    def pair(self, code, name):
        """Kod doğruysa yeni cihaz kaydeder ve anahtarı döndürür (yoksa None)."""
        with self.lock:
            exp = self.codes.pop(code or "", None)
            if not exp or exp < time.time():
                return None
            token = secrets.token_urlsafe(32)
            now = datetime.now().isoformat(timespec="seconds")
            dev = {"id": secrets.token_hex(4), "name": (name or "Telefon").strip()[:40] or "Telefon",
                   "hash": token_hash(token), "created": now, "last_seen": now, "perms": dict(PERMS), "lang": ""}
            self.data.setdefault("devices", []).append(dev)
            self._persist()
            return token

    def device_for(self, token):
        if not token:
            return None
        h = token_hash(token)
        with self.lock:
            for d in self.data.get("devices", []):
                if hmac.compare_digest(d.get("hash", ""), h):
                    return d
        return None

    def revoke(self, dev_id):
        with self.lock:
            before = len(self.data.get("devices", []))
            self.data["devices"] = [d for d in self.data.get("devices", []) if d.get("id") != dev_id]
            changed = len(self.data["devices"]) != before
        if changed:
            self._persist()
        return changed

    def devices(self):
        with self.lock:
            return [dict(d) for d in self.data.get("devices", [])]

    def set_option(self, key, value):
        with self.lock:
            self.data[key] = value
        self._persist(notify=False)

    def _persist(self, notify=True):
        with self.lock:
            snap = json.loads(json.dumps(self.data))
        try:
            self.p.save_remote(snap)
        except Exception as e:
            print(f"[remote] kaydedilemedi: {e}")
        if notify:
            try:
                self.p.on_change()
            except Exception:
                pass

    # ------------------------------------------------------------ hız sınırı
    def limited(self, kind, key, limit, window):
        now = time.time()
        with self.lock:
            lst = [x for x in self.fails.get((kind, key), []) if now - x < window]
            self.fails[(kind, key)] = lst
            return len(lst) >= limit

    def failed(self, kind, key):
        with self.lock:
            self.fails.setdefault((kind, key), []).append(time.time())

    # ------------------------------------------------------------ veri
    def _cache(self, prof):
        c = self.caches.get(prof.id)
        if c is None or c.path != prof.server_path:
            c = self.caches[prof.id] = _ServerCache(prof)
        return c

    def _profile(self, sid):
        for prof in self.p.servers():
            if prof.id == sid:
                return prof
        return None

    def summary(self, prof, host, t=None, dev=None):
        t = t or self.p.translate
        app = self.p.app(prof.id)
        exists = prof.exists
        state, ram, cpu = "stopped", None, None
        if app is not None and app.server.is_running:
            state = app.server.state
        if state == "stopping" and app is not None and not app.server.is_running:
            state = "stopped"
        s = None
        if exists:
            try:
                s = (app.metrics if app is not None and app.server.is_running else self._cache(prof).metrics).sample()
            except Exception:
                s = None
        if s:
            ram, cpu = round(s[0]), round(s[1], 1)
            if state == "stopped":
                state = "external"
        online, joins = self._cache(prof).online() if exists else ([], 0)
        if state == "stopped":
            online = []
        ver, soft = detect_version(prof.server_path) if exists else ("", "")
        map_url = ""
        try:
            from . import bluemap
            st = bluemap.status(prof.server_path, is_modded(prof.server_path)) if exists else {}
            if st.get("installed") and st.get("web_enabled", True):
                hn = urlparse("//" + host).hostname or "localhost"
                map_url = f"http://{'[' + hn + ']' if ':' in hn else hn}:{st['port']}"
        except Exception:
            pass
        safe = int(prof.get("safe_mode") or 0)
        perms = self.perms(dev) if dev is not None else {k: False for k in PERMS}
        if safe >= 3 or not exists:
            perms = {k: False for k in PERMS}
        return {
            "id": prof.id, "name": prof.name, "software": soft, "version": ver, "exists": exists,
            "state": state, "state_text": t(STATE_LABEL.get(state, state)),
            "online": online, "online_count": len(online), "joins_today": joins,
            "ram_mb": ram, "cpu": cpu, "ram_max": prof.get("ram_max"),
            "pin": bool(prof.get("pin_hash")), "map_url": map_url,
            "control": perms["control"], "perms": perms,
            "control_note": "" if self.data.get("allow_control", True) else t("Telefondan kontrol panelde kapalı."),
            "maintenance": self._maint(prof, t),
        }

    def _maint(self, prof, t):
        from .maintenance import _parse, next_window
        st = prof.get("maintenance_state") or {}
        if st.get("active"):
            until = _parse(st.get("until"))
            return {"active": True, "text": t("Otomatik bitiş: {time}", time=f"{until:%d.%m %H:%M}") if until
                    else t("Bakım elle bitirilene kadar sürer.")}
        w = next_window(prof.get("maintenance_schedule") or {})
        if w and w[0].isoformat(timespec="seconds") == st.get("last_window"):
            from datetime import timedelta
            w = next_window(prof.get("maintenance_schedule") or {}, w[1] + timedelta(seconds=1))
        return {"active": False, "text": t("Sonraki otomatik bakım: {time}", time=f"{w[0]:%d.%m %H:%M}") if w
                else t("Otomatik bakım kapalı.")}

    def detail(self, prof, host, t=None, dev=None):
        s = self.summary(prof, host, t, dev)
        s["players"] = self._cache(prof).player_rows(s["online"]) if s["exists"] else []
        return s

    def log(self, prof, n=150):
        lines = tail_lines(os.path.join(prof.server_path, "logs", "latest.log"), n)
        if lines is None:
            return None
        from .server import classify_log_line
        out = []
        for ln in lines:
            ln = mask_ips(_ANSI.sub("", ln))
            out.append({"t": ln[:400], "k": classify_log_line(ln)})
        return out

    def hud_sprites(self):
        d = os.path.join(self.p.icons_dir() or "", "hud")
        try:
            return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".png") and _HUD_RE.match("/hud/" + f))
        except OSError:
            return []

    def strings(self, t=None):
        t = t or self.p.translate
        return {k: t(k) for k in WEB_STRINGS}

    def _guard(self, prof, pin, device, perm, t):
        """İzin, güvenli mod ve PIN denetimi. Sorun yoksa None, varsa (kod, mesaj)."""
        if not self.data.get("allow_control", True):
            return HTTPStatus.FORBIDDEN, t("Telefondan kontrol panelde kapalı.")
        if not self.perm(device, perm):
            return HTTPStatus.FORBIDDEN, t("Bu cihaza izin verilmemiş.")
        if int(prof.get("safe_mode") or 0) >= 3:
            return HTTPStatus.FORBIDDEN, t("Güvenli mod (Yüksek): komut gönderilemez.")
        stored = prof.get("pin_hash")
        if stored:
            key = (device["id"], prof.id)
            if self.limited("pin", key, 5, 300):
                return HTTPStatus.TOO_MANY_REQUESTS, t("Çok fazla yanlış PIN. 5 dakika sonra tekrar dene.")
            from .safemode import verify_pin
            if not pin or not verify_pin(str(pin), stored):
                self.failed("pin", key)
                return HTTPStatus.UNAUTHORIZED, t("Yanlış PIN.")
        return None

    def settings_get(self, prof):
        data = self.p.settings_get(prof.id) or {}
        props = data.get("props") or {}
        data["props"] = {k: v for k, v in props.items() if not _PROP_HIDDEN.search(k)}
        return data

    def settings_save(self, prof, body, pin, device, t=None):
        t = t or self.p.translate
        g = self._guard(prof, pin, device, "settings", t)
        if g:
            return g
        clean = {}
        ram = body.get("ram") or {}
        if ram:
            lo, hi = str(ram.get("min", "")).strip().upper(), str(ram.get("max", "")).strip().upper()
            if not (_RAM_RE.match(lo) and _RAM_RE.match(hi)):
                return HTTPStatus.BAD_REQUEST, t("RAM değeri 2G ya da 2048M gibi olmalı.")
            clean["ram"] = {"min": lo, "max": hi}
        if isinstance(body.get("schedule"), dict):
            from .maintenance import normalize_schedule
            clean["schedule"] = normalize_schedule(body["schedule"])
        props = body.get("props")
        if isinstance(props, dict) and props:
            current = (self.p.settings_get(prof.id) or {}).get("props") or {}
            out = {}
            for k, v in list(props.items())[:200]:
                k = str(k)
                if k not in current or _PROP_HIDDEN.search(k):
                    continue                       # yalnızca var olan, telefona açık anahtarlar
                v = str(v)
                if "\n" in v or "\r" in v or len(v) > 300:
                    return HTTPStatus.BAD_REQUEST, t("Geçersiz değer: {key}", key=k)
                out[k] = v
            clean["props"] = out
        err = self.p.settings_save(prof.id, clean)
        if err:
            return HTTPStatus.CONFLICT, err
        return HTTPStatus.OK, ""

    def maintenance(self, prof, on, pin, device, t=None):
        t = t or self.p.translate
        g = self._guard(prof, pin, device, "maintenance", t)
        if g:
            return g
        err = self.p.maintenance(prof.id, bool(on))
        if err:
            return HTTPStatus.CONFLICT, err
        return HTTPStatus.OK, ""

    def control(self, prof, action, pin, device, t=None):
        t = t or self.p.translate
        g = self._guard(prof, pin, device, "control", t)
        if g:
            return g
        if action == "start":
            app = self.p.app(prof.id)
            if not (app is not None and app.server.is_running):
                try:
                    external = self._cache(prof).metrics.sample() is not None
                except Exception:
                    external = False
                if external:                         # panel dışında açılmış: ikinci kopya başlatılmaz
                    return HTTPStatus.CONFLICT, t("Sunucu zaten çalışıyor!")
        err = self.p.control(prof.id, action)
        if err:
            return HTTPStatus.CONFLICT, err
        return HTTPStatus.OK, ""


def _web_file(name):
    for base in (os.path.join(resource_dir(), WEB_DIR), os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), WEB_DIR)):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            return p
    return None


_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".png": "image/png", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json"}
_STATIC = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/icon.png": "icon.png",
           "/icon.svg": "icon.svg", "/manifest.webmanifest": "manifest.webmanifest"}
_HUD_RE = re.compile(r"^/hud/([a-z_]{3,40})\.png$")
_SRV_RE = re.compile(r"^/api/servers/([A-Za-z0-9_-]{1,64})(?:/(log|start|stop|restart|settings|maintenance))?$")


class _QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):     # bozuk istekler konsola yığın izi basmasın
        pass


class _Handler(BaseHTTPRequestHandler):
    remote = None                # RemoteServer
    server_version = "SpypaperRemote"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):   # konsola ya da dosyaya erişim kaydı yazılmaz
        pass

    # ------------------------------------------------------------ yardımcılar
    def _headers(self, code, ctype, length, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, code, obj, extra=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._headers(code, "application/json; charset=utf-8", len(body), extra)
        self.wfile.write(body)

    def _err(self, code, msg):
        self._json(code, {"error": msg})

    def _token(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        m = c.get(COOKIE)
        return m.value if m else None

    def _device(self):
        dev = self.remote.device_for(self._token())
        if dev:
            dev["last_seen"] = datetime.now().isoformat(timespec="seconds")
        return dev

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8")) or {}
        except Exception:
            return {}

    def _client(self):
        return self.client_address[0] if self.client_address else "?"

    def _send_file(self, path):
        ext = os.path.splitext(path)[1]
        with open(path, "rb") as f:
            data = f.read()
        self._headers(HTTPStatus.OK, _TYPES.get(ext, "application/octet-stream"), len(data))
        self.wfile.write(data)

    # ------------------------------------------------------------ GET
    def do_GET(self):
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"[remote] {e}")
            try:
                self._err(HTTPStatus.INTERNAL_SERVER_ERROR, "error")
            except Exception:
                pass

    def _get(self):
        url = urlparse(self.path)
        path = url.path
        r = self.remote
        if path in _STATIC or path == "/pair":
            f = _web_file(_STATIC.get(path, "index.html"))
            return self._send_file(f) if f else self._err(HTTPStatus.NOT_FOUND, "missing")
        if path == "/api/me":
            dev = self._device()
            q = parse_qs(url.query)
            code = (q.get("code") or [""])[0]
            lang = r.resolve_lang(dev, (q.get("nav") or [""])[0] or self.headers.get("Accept-Language", ""))
            return self._json(HTTPStatus.OK, {
                "paired": bool(dev), "device": dev["name"] if dev else "", "lang": lang, "rtl": r.p.is_rtl(lang),
                "lang_pref": (dev or {}).get("lang", ""), "langs": r.p.languages(),
                "perms": r.perms(dev) if dev else {}, "control_on": bool(r.data.get("allow_control", True)),
                "strings": r.strings(r.tr(lang)), "code_valid": r.code_valid(code) if code else None,
                "suggest_name": device_label(self.headers.get("User-Agent", "")),
                "hud": r.hud_sprites() if dev else [],
            })
        m = _HUD_RE.match(path)
        if m:
            p = os.path.join(r.p.icons_dir() or "", "hud", m.group(1) + ".png")
            if self._device() and os.path.isfile(p):
                return self._send_file(p)
            return self._err(HTTPStatus.NOT_FOUND, "missing")
        dev = self._device()
        if not dev:
            return self._err(HTTPStatus.UNAUTHORIZED, "not paired")
        host = self.headers.get("Host", "localhost")
        t = r.tr(r.resolve_lang(dev, self.headers.get("Accept-Language", "")))
        if path == "/api/servers":
            return self._json(HTTPStatus.OK, {"servers": [r.summary(p, host, t, dev) for p in r.p.servers()],
                                              "time": datetime.now().strftime("%H:%M:%S")})
        m = _SRV_RE.match(path)
        if m:
            prof = r._profile(m.group(1))
            if not prof:
                return self._err(HTTPStatus.NOT_FOUND, "server")
            if m.group(2) == "log":
                lines = r.log(prof)
                return self._json(HTTPStatus.OK, {"lines": lines or [], "missing": lines is None})
            if m.group(2) == "settings":
                if not r.perm(dev, "settings"):
                    return self._err(HTTPStatus.FORBIDDEN, t("Bu cihaza izin verilmemiş."))
                return self._json(HTTPStatus.OK, r.settings_get(prof))
            if m.group(2) is None:
                d = r.detail(prof, host, t, dev)
                d["time"] = datetime.now().strftime("%H:%M:%S")
                return self._json(HTTPStatus.OK, d)
        return self._err(HTTPStatus.NOT_FOUND, "not found")

    # ------------------------------------------------------------ POST
    def do_POST(self):
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"[remote] {e}")
            try:
                self._err(HTTPStatus.INTERNAL_SERVER_ERROR, "error")
            except Exception:
                pass

    def _post(self):
        r = self.remote
        t = r.tr(r.resolve_lang(None, self.headers.get("Accept-Language", "")))
        # başka sitelerin bu adrese istek atmasını engeller: özel başlık + JSON şart (CORS ön kontrolüne yanıt yok)
        if self.headers.get("X-Spypaper") != "1" or "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._err(HTTPStatus.FORBIDDEN, "forbidden")
        path = urlparse(self.path).path
        body = self._body()
        if path == "/api/pair":
            ip = self._client()
            if r.limited("pair", ip, 10, 60):
                return self._err(HTTPStatus.TOO_MANY_REQUESTS, "slow down")
            token = r.pair(str(body.get("code") or ""), str(body.get("name") or ""))
            if not token:
                r.failed("pair", ip)
                return self._err(HTTPStatus.FORBIDDEN, t(
                    "Eşleşme kodu geçersiz ya da süresi dolmuş. Panelde yeni bir QR oluştur."))
            cookie = f"{COOKIE}={token}; Max-Age={COOKIE_AGE}; Path=/; HttpOnly; SameSite=Strict"
            return self._json(HTTPStatus.OK, {"ok": True}, {"Set-Cookie": cookie})
        dev = self._device()
        if not dev:
            return self._err(HTTPStatus.UNAUTHORIZED, "not paired")
        t = r.tr(r.resolve_lang(dev, self.headers.get("Accept-Language", "")))
        if path == "/api/me/lang":
            ok = r.set_device_lang(dev["id"], str(body.get("lang") or ""))
            return self._json(HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST, {"ok": ok})
        if path == "/api/logout":
            r.revoke(dev["id"])
            return self._json(HTTPStatus.OK, {"ok": True},
                              {"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
        m = _SRV_RE.match(path)
        if m and m.group(2) in ("start", "stop", "restart"):
            prof = r._profile(m.group(1))
            if not prof:
                return self._err(HTTPStatus.NOT_FOUND, "server")
            code, msg = r.control(prof, m.group(2), body.get("pin"), dev, t)
            if code != HTTPStatus.OK:
                return self._json(code, {"error": msg, "need_pin": code == HTTPStatus.UNAUTHORIZED})
            return self._json(HTTPStatus.OK, {"ok": True})
        if m and m.group(2) in ("settings", "maintenance"):
            prof = r._profile(m.group(1))
            if not prof:
                return self._err(HTTPStatus.NOT_FOUND, "server")
            if m.group(2) == "settings":
                code, msg = r.settings_save(prof, body, body.get("pin"), dev, t)
            else:
                code, msg = r.maintenance(prof, body.get("on"), body.get("pin"), dev, t)
            if code != HTTPStatus.OK:
                return self._json(code, {"error": msg, "need_pin": code == HTTPStatus.UNAUTHORIZED})
            return self._json(HTTPStatus.OK, {"ok": True})
        return self._err(HTTPStatus.NOT_FOUND, "not found")
