"""Hile Koruması: panelden yapılabilen korumalar.

Spypaper sunucunun dışında çalışır; oyuncuların ağ paketlerini göremez, yalnızca konsolu ve sunucu
dosyalarını görür. Bu yüzden modüller işlevlerine göre ayrıldı ve her biri yapabildiği kadarını yapar:

  Cevher Gizleme      Paper/Purpur'un yerleşik anti-xray'i (config/paper-world-defaults.yml). Oyuncu
                      görmediği cevherleri taş (ya da sahte cevher) olarak alır; X-Ray paketi işe yaramaz.
                      Fullbright ve kaynak paketinin kendisi oyuncunun bilgisayarındadır, hiçbir sunucu göremez.
  Yetki Koruması      ops.json'u ve konsolu izler; izinli listede olmayan biri OP olursa yetkiyi geri alır
                      ve oyuncuyu atar. Panelden (konsol, Oyuncular) verilen OP kendiliğinden izinli sayılır.
  Savaş Hilesi Den.   Vuruş hızı/açısı için ağ paketleri gerekir; bunu sunucuya kurulan açık kaynak bir
                      anti-hile eklentisi (Grim, Modrinth) yapar. Spypaper yalnızca kurar/açar/kapatır.
  Bot Doğrulaması     Yalnızca kaynak paketini Spypaper paylaşırken: oyuncu girince, aynı IP'den paketin
                      gerçekten indirilip indirilmediğine bakar. İndirmeyen atılır, indiren
                      <sunucu>/spypaper_guard/verified.json'a yazılır ve bir daha denetlenmez.

"Hilelere izin ver" açıkken hiçbir koruma çalışmaz; dosya değişiklikleri (anti-xray, eklenti) geri alınır.
"""
import datetime
import ipaddress
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from collections import deque

from . import playermsg
from .config import N_

GUARD_DIR = "spypaper_guard"
DEFAULTS = {
    "allow_cheats": False,     # sunucu hilelere izin veriyor: tüm korumalar kapalı
    "xray": False, "xray_engine": 1,
    "op": False, "op_allowed": [],
    "combat": False,           # anti-hile eklentisi (Grim) açık mı
    "captcha": False, "captcha_grace": 15, "captcha_skip_bedrock": True,
}
ANTICHEAT_SLUGS = ("grimac",)          # Modrinth: GrimAC (GPL-3.0)
ANTICHEAT_HINT = "grim"                # kurulu dosya adında aranır

_OP_LINE = re.compile(r"Made ([A-Za-z0-9_.]{1,17}) a server operator")
_LOGIN = re.compile(r"([A-Za-z0-9_.]{1,17})\[/(.+?):(\d+)\] logged in")
_CMD_OP = re.compile(r"^/?(de)?op\s+([A-Za-z0-9_.]{1,17})\s*$", re.I)
NAME_RE = re.compile(r"^[A-Za-z0-9_.]{1,17}$")


class GuardError(Exception):
    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


def settings(profile):
    out = dict(DEFAULTS)
    out.update(profile.get("guard") or {})
    return out


def save(profile, **changes):
    cur = settings(profile)
    cur.update(changes)
    profile.set("guard", cur)
    return cur


def active(profile, module):
    g = settings(profile)
    return bool(g.get(module)) and not g.get("allow_cheats")


def guard_dir(server_path):
    return os.path.join(server_path, GUARD_DIR)


# ---------------------------------------------------------------- Cevher Gizleme
def paper_world_defaults(server_path):
    return os.path.join(server_path, "config", "paper-world-defaults.yml")


def xray_state(server_path):
    """(etkin_mi, motor) ya da dosya yoksa None (Paper/Purpur değil ya da sunucu hiç başlatılmadı)."""
    p = paper_world_defaults(server_path)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        lines = f.read().splitlines()
    block = _xray_block(lines)
    if block is None:
        return None
    enabled, engine = False, 1
    for i in block:
        m = re.match(r"^\s*enabled:\s*(\S+)", lines[i])
        if m:
            enabled = m.group(1).lower() == "true"
        m = re.match(r"^\s*engine-mode:\s*(\d+)", lines[i])
        if m:
            engine = int(m.group(1))
    return enabled, engine


def _xray_block(lines):
    """anti-xray: bölümünün doğrudan alt satırlarının indeksleri."""
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)anti-xray:\s*$", line)
        if not m:
            continue
        base = len(m.group(1))
        child, out = None, []
        for j in range(i + 1, len(lines)):
            s = lines[j]
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            ind = len(s) - len(s.lstrip())
            if ind <= base:
                break
            if child is None:
                child = ind
            if ind == child:
                out.append(j)
        return out
    return None


def set_xray(server_path, enabled, engine=1):
    """Yorumları bozmadan yalnızca anti-xray'in enabled ve engine-mode satırlarını değiştirir."""
    p = paper_world_defaults(server_path)
    if not os.path.isfile(p):
        raise GuardError(N_("config/paper-world-defaults.yml bulunamadı. Cevher gizleme yalnızca Paper ve Purpur'da var; sunucuyu bir kez başlatıp kapat."))
    with open(p, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    block = _xray_block(lines)
    if not block:
        raise GuardError(N_("Ayar dosyasında anti-xray bölümü bulunamadı."))
    seen = set()
    for i in block:
        m = re.match(r"^(\s*)(enabled|engine-mode):", lines[i])
        if m:
            seen.add(m.group(2))
            val = ("true" if enabled else "false") if m.group(2) == "enabled" else str(int(engine))
            lines[i] = f"{m.group(1)}{m.group(2)}: {val}"
    if "enabled" not in seen:
        raise GuardError(N_("Ayar dosyasında anti-xray bölümü bulunamadı."))
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + ("\n" if text.endswith("\n") else ""))


# ---------------------------------------------------------------- Savaş Hilesi Denetimi (eklenti)
def anticheat_file(folder):
    """(dosya_adı, etkin_mi) ya da None."""
    if not os.path.isdir(folder):
        return None
    for n in sorted(os.listdir(folder)):
        low = n.lower()
        if ANTICHEAT_HINT in low and (low.endswith(".jar") or low.endswith(".jar.disabled")):
            return n, low.endswith(".jar")
    return None


def set_anticheat(folder, enabled):
    cur = anticheat_file(folder)
    if not cur or cur[1] == enabled:
        return
    p = os.path.join(folder, cur[0])
    os.rename(p, p[:-len(".disabled")] if p.endswith(".disabled") else p + ".disabled")


def install_anticheat(folder, loaders, game_version, progress=None):
    """Modrinth'ten anti-hile eklentisini ve gerekli bağımlılıklarını kurar. Kurulan dosya adlarını döndürür."""
    from . import modrinth as M
    vs, last = [], None
    for slug in ANTICHEAT_SLUGS:
        try:
            vs = M.versions(slug, loaders, game_version)
        except M.ModrinthError as e:
            last = e
            continue
        if vs:
            break
    if not vs:
        if last is not None:
            raise last
        raise GuardError(N_("Bu sunucu sürümü için uyumlu bir anti-hile sürümü bulunamadı ({v})."), v=game_version or "?")
    os.makedirs(folder, exist_ok=True)
    v = vs[0]
    done = [M.download(v["file"], folder, progress)]
    have = M.installed_names(folder)
    for d in v["deps"]:
        pid = d.get("project_id")
        if not pid:
            continue
        dv = M.versions(pid, loaders, game_version)
        if dv and M.safe_filename(dv[0]["file"]["name"]).lower() not in have:
            done.append(M.download(dv[0]["file"], folder, progress))
    return [os.path.basename(x) for x in done]


# ---------------------------------------------------------------- Bot Doğrulaması: paket damgası
def stamp_pack(zip_path):
    """Pakete rastgele bir doğrulama dosyası ekler: özet değişir, oyuncular paketi yeniden indirmek zorunda kalır
    (önbellekteki eski paketle doğrulamayı atlayamazlar)."""
    fd, tmp = tempfile.mkstemp(suffix=".zip", dir=os.path.dirname(zip_path))
    os.close(fd)
    try:
        with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                if info.filename != "spypaper_verify.txt":
                    dst.writestr(info, src.read(info.filename))
            dst.writestr("spypaper_verify.txt", secrets.token_hex(16))
        shutil.move(tmp, zip_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def norm_ip(s):
    s = (s or "").strip().strip("[]")
    try:
        ip = ipaddress.ip_address(s.split("%")[0])
    except ValueError:
        return s.lower()
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.compressed


def same_client(a, b, local=()):
    """Aynı istemci mi: aynı IP ya da ikisi de bu bilgisayar (oyuncu sunucuyla aynı bilgisayardaysa
    oyuna 127.0.0.1'den, pakete ev ağı adresinden gelir)."""
    a, b = norm_ip(a), norm_ip(b)
    if a == b:
        return True
    mine = {"127.0.0.1", "::1"} | {norm_ip(x) for x in local}
    return a in mine and b in mine


# ---------------------------------------------------------------- Koruma servisi
class Guard:
    """Sunucu başına. Konsol satırlarını ve gönderilen komutları dinler; panel sayfası açık olmasa da çalışır."""

    def __init__(self, profile, server, host=None, local=None):
        self.profile, self.server = profile, server
        if host is None:
            from .packhost import HOST as host
        self.host = host
        self._local = local                     # test için; None ise remote.local_addresses
        self.tr = lambda s, **kw: s.format(**kw) if kw else s
        self.on_event = None                    # fn(olay_sözlüğü) — arayüz
        self.events = deque(maxlen=200)
        self._lock = threading.Lock()
        self._last_ops = 0.0
        self._pending = {}                      # oyuncu -> Timer
        self._used = set()                      # doğrulamada harcanan indirmeler (ip, zaman)
        server.hooks.append(self.on_line)
        server.send_hooks.append(self.on_send)

    # --- yardımcılar ---
    @property
    def server_path(self):
        return self.profile.server_path

    def local(self):
        if self._local is not None:
            return self._local
        try:
            from .remote import local_addresses
            return local_addresses()
        except Exception:
            return []

    def log(self, kind, text, **kw):
        ev = {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "text": text, "kw": kw}
        self.events.append(ev)
        try:
            os.makedirs(guard_dir(self.server_path), exist_ok=True)
            with open(os.path.join(guard_dir(self.server_path), "guard.log"), "a", encoding="utf-8") as f:
                f.write(f"{ev['time']} [{kind}] {text.format(**kw) if kw else text}\n")
        except OSError:
            pass
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                pass

    # --- konsol ---
    def on_line(self, line):
        if settings(self.profile).get("allow_cheats"):
            return
        if active(self.profile, "op") and _OP_LINE.search(line):
            self.check_ops()
        m = _LOGIN.search(line)
        if m and active(self.profile, "captcha"):
            self.on_login(m.group(1), m.group(2))

    def on_send(self, command):
        """Panelden gönderilen op/deop: izinli listeyi günceller (panel sahibinin kararı)."""
        m = _CMD_OP.match(command.strip())
        if not m:
            return
        name = m.group(2)
        allowed = [n for n in settings(self.profile)["op_allowed"] if n.lower() != name.lower()]
        if not m.group(1):
            allowed.append(name)
        save(self.profile, op_allowed=allowed)

    def tick(self):
        """Ana döngüden saniyede bir; ops.json'u 5 saniyede bir denetler (eklenti/komut bloğu ile verilen OP)."""
        if not self.server.is_running or not active(self.profile, "op"):
            return
        now = time.time()
        if now - self._last_ops >= 5:
            self._last_ops = now
            self.check_ops()

    # --- Yetki Koruması ---
    def ops(self):
        try:
            with open(os.path.join(self.server_path, "ops.json"), encoding="utf-8") as f:
                data = json.load(f)
            return [str(o.get("name", "")) for o in data if isinstance(o, dict) and o.get("name")]
        except (OSError, ValueError):
            return []

    def seed_allowed(self):
        """Korumayı açarken şu anki OP'ları izinli say."""
        names = sorted(set(settings(self.profile)["op_allowed"]) | set(self.ops()), key=str.lower)
        save(self.profile, op_allowed=names)
        return names

    def check_ops(self):
        allowed = {n.lower() for n in settings(self.profile)["op_allowed"]}
        with self._lock:
            for name in self.ops():
                if name.lower() in allowed or not NAME_RE.match(name):
                    continue
                self.server.try_send(f"deop {name}")
                playermsg.kick(self.server, name, N_("İzinsiz yönetici yetkisi algılandı."), self.tr)
                self.log("op", N_("İzinsiz OP geri alındı ve oyuncu atıldı: {name}"), name=name)

    # --- Bot Doğrulaması ---
    def verified_path(self):
        return os.path.join(guard_dir(self.server_path), "verified.json")

    def verified(self):
        try:
            with open(self.verified_path(), encoding="utf-8") as f:
                return json.load(f).get("players", {})
        except (OSError, ValueError, AttributeError):
            return {}

    def mark_verified(self, name, how="pack"):
        with self._lock:
            data = self.verified()
            data[name.lower()] = {"name": name, "date": datetime.date.today().isoformat(), "how": how}
            os.makedirs(guard_dir(self.server_path), exist_ok=True)
            tmp = self.verified_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"players": data}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.verified_path())

    def unverify(self, name):
        with self._lock:
            data = self.verified()
            if data.pop(name.lower(), None) is not None:
                with open(self.verified_path(), "w", encoding="utf-8") as f:
                    json.dump({"players": data}, f, ensure_ascii=False, indent=2)

    def downloaded(self, ip, since):
        """Bu IP'den kullanılmamış bir indirme var mı; varsa onu harcar: bir indirme yalnızca bir girişi doğrular
        (aynı IP'den gelen bot sürüsü tek indirmeyle geçemez)."""
        local = self.local()
        with self._lock:
            for dip, ts in self.host.downloads_for(self.profile.id):
                if ts >= since and (dip, ts) not in self._used and same_client(ip, dip, local):
                    self._used.add((dip, ts))
                    return True
        return False

    def on_login(self, name, ip):
        g = settings(self.profile)
        if name.lower() in self.verified():
            return
        if g.get("captcha_skip_bedrock") and name.startswith("."):
            return                              # Geyser/Floodgate: Bedrock oyuncuları Java paketi indiremez
        since = time.time() - 300               # paket, "logged in"den önce (yapılandırma aşamasında) iner
        if self.downloaded(ip, since):
            self.mark_verified(name)
            self.log("captcha", N_("Doğrulandı: {name}"), name=name)
            return
        old = self._pending.pop(name.lower(), None)
        if old:
            old.cancel()
        t = threading.Timer(max(3, int(g.get("captcha_grace") or 15)), self._recheck, (name, ip, since))
        t.daemon = True
        self._pending[name.lower()] = t
        t.start()

    def _recheck(self, name, ip, since):
        self._pending.pop(name.lower(), None)
        if not active(self.profile, "captcha") or name.lower() in self.verified():
            return
        if self.downloaded(ip, since):
            self.mark_verified(name)
            self.log("captcha", N_("Doğrulandı: {name}"), name=name)
            return
        playermsg.kick(self.server, name, N_("Doğrulama başarısız: sunucunun kaynak paketi indirilmedi. Paketi kabul edip tekrar bağlan."), self.tr)
        self.log("captcha", N_("Kaynak paketini indirmediği için atıldı: {name}"), name=name)
