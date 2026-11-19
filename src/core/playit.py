"""Dış erişim: Playit.gg (isteğe bağlı).

Playit kendi programıyla (playit, arka planda playitd hizmeti) çalışır; Spypaper onu indirmez,
başlatmaz, durdurmaz. Spypaper yalnızca:
  - "Hesabı bağla": `playit setup` çalıştırır; playit tarayıcıda onay bağlantısı açar
    (https://playit.gg/claim/<kod>). Kullanıcı onaylayınca hizmet hesaba bağlanır.
  - Tünel adresi: ajanın gizli anahtarıyla api.playit.gg/v1/agents/rundata'yı okur ve panel portuna
    giden tüneli bulur. Tüneli kullanıcı playit.gg'de kendisi oluşturur (yerel port = panel portu).
Anahtar playit.toml'dan okunur (secret_key = "..."); okunamazsa kullanıcı elle girebilir.
"""
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request

from .config import N_

API = "https://api.playit.gg"
TUNNELS_PAGE = "https://playit.gg/account/tunnels"
CLAIM_RE = re.compile(r"https://playit\.gg/claim/[0-9a-f]+", re.I)
SECRET_RE = re.compile(r'^\s*secret_key\s*=\s*"([^"]*)"', re.M)
KEY_RE = re.compile(r"^[0-9a-fA-F]{32,128}$")
TIMEOUT = 12
SETUP_TIMEOUT = 600          # sn; kullanıcının tarayıcıda onaylaması için


class PlayitError(Exception):
    pass


def _flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_binary(configured=""):
    """Ayarlanan yol, PATH'teki playit ya da Windows'taki olağan kurulum yeri; yoksa None."""
    if configured and os.path.isfile(configured):
        return configured
    found = shutil.which("playit")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for rel in (r"playit_gg\bin\playit.exe", r"playit_gg\playit.exe", r"playit\playit.exe"):
            p = os.path.join(base, rel)
            if os.path.isfile(p):
                return p
    return None


def _run(binary, *args, timeout=15):
    try:
        r = subprocess.run([binary, *args], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, creationflags=_flags())
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def secret_candidates(binary=None):
    """playit.toml'un bulunabileceği yerler (önce playit'in kendi söylediği)."""
    out = []
    if binary:
        code, text = _run(binary, "secret-path", timeout=8)
        if code == 0:
            line = text.strip().splitlines()[-1].strip() if text.strip() else ""
            if line:
                out.append(line)
    pd = os.environ.get("PROGRAMDATA") or os.environ.get("ProgramData")
    if pd:
        out.append(os.path.join(pd, "playit_gg", "playit.toml"))           # Windows hizmeti
    la = os.environ.get("LOCALAPPDATA")
    if la:
        out.append(os.path.join(la, "playit_gg", "playit.toml"))
    out.append("/etc/playit/playit.toml")
    out.append(os.path.expanduser("~/.config/playit_gg/playit.toml"))
    out.append(os.path.expanduser("~/Library/Application Support/playit_gg/playit.toml"))
    seen, res = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            res.append(p)
    return res


def parse_secret(text):
    m = SECRET_RE.search(text or "")
    key = (m.group(1) if m else (text or "")).strip()
    return key if KEY_RE.match(key) else ""


def read_secret(binary=None, manual=""):
    """(anahtar, hata). Elle girilen anahtar önce gelir."""
    key = parse_secret(manual)
    if key:
        return key, ""
    denied = False
    for p in secret_candidates(binary):
        try:
            with open(p, encoding="utf-8") as f:
                key = parse_secret(f.read())
        except PermissionError:
            denied = True
            continue
        except OSError:
            continue
        if key:
            return key, ""
    if denied:
        return "", N_("Playit anahtar dosyası okunamadı (izin yok). Anahtarı elle gir.")
    return "", N_("Playit hesabı bağlı değil. \"Hesabı bağla\" düğmesini kullan.")


def api_call(path, key, body=None, opener=urllib.request.urlopen):
    req = urllib.request.Request(API + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Agent-Key {key}"})
    try:
        with opener(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PlayitError(N_("Playit anahtarı geçersiz. Hesabı yeniden bağla.")) from None
        raise PlayitError(N_("Playit yanıt vermedi ({e}).").format(e=e.code)) from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise PlayitError(N_("Playit'e bağlanılamadı: {e}").format(e=getattr(e, "reason", e))) from None
    status = data.get("status") if isinstance(data, dict) else None
    if status != "success":
        err = data.get("data") if isinstance(data, dict) else data
        if isinstance(err, dict) and any(k in str(err) for k in ("Auth", "auth", "Secret", "Key")):
            raise PlayitError(N_("Playit anahtarı geçersiz. Hesabı yeniden bağla."))
        raise PlayitError(N_("Playit hatası: {e}").format(e=str(err)[:160]))
    return data.get("data") or {}


def _field(t, name):
    for f in ((t.get("agent_config") or {}).get("fields") or []):
        if f.get("name") == name:
            return f.get("value") or ""
    return ""


def tunnels(key, opener=urllib.request.urlopen):
    """Bu ajana bağlı tüneller: [{name, address, type, port_type, local_ip, local_port, disabled}]"""
    data = api_call("/v1/agents/rundata", key, opener=opener)
    out = []
    for t in data.get("tunnels") or []:
        lp = _field(t, "local_port")
        out.append({
            "name": t.get("name") or "",
            "address": t.get("display_address") or "",
            "type": t.get("tunnel_type") or "",
            "type_display": t.get("tunnel_type_display") or t.get("tunnel_type") or "",
            "port_type": t.get("port_type") or "",
            "local_ip": _field(t, "local_ip"),
            "local_port": int(lp) if lp.isdigit() else 0,
            "disabled": t.get("disabled_reason") or "",
        })
    return out, (data.get("permissions") or {}).get("account_status") or ""


def url_for(tn):
    addr = tn["address"]
    return ("https://" if tn["type"] == "https" else "http://") + addr


class PlayitTunnel:
    """Panel portuna giden Playit tünelini bulur. Hizmeti Spypaper çalıştırmaz; stop bir şey kapatmaz."""

    def __init__(self, port, binary=None, manual_key="", opener=urllib.request.urlopen):
        self.port = int(port)
        self.binary = binary
        self.manual_key = manual_key
        self.opener = opener
        self.url = ""
        self.others = []          # diğer tüneller (ör. Minecraft) bilgi için
        self.account = ""

    def start(self):
        key, err = read_secret(self.binary, self.manual_key)
        if not key:
            raise PlayitError(err)
        found, self.account = tunnels(key, self.opener)
        mine = [t for t in found if t["local_port"] == self.port and t["port_type"] in ("tcp", "both", "")]
        self.others = [t for t in found if t not in mine]
        live = [t for t in mine if not t["disabled"]]
        if live:
            self.url = url_for(live[0])
            return self.url
        if mine:
            raise PlayitError(N_("Playit tüneli kapalı: {e}").format(e=mine[0]["disabled"]))
        raise PlayitError(N_("Playit'te {port} portuna giden tünel yok. playit.gg'de TCP tüneli ekle "
                             "(yerel port {port}).").format(port=self.port))

    def stop(self):
        self.url = ""


class Linker:
    """`playit setup` ile hesabı bağlar. state: "" | wait | url | done | fail; msg; url."""

    def __init__(self, binary, open_url=None):
        self.binary = binary
        self.open_url = open_url
        self.state = ""
        self.msg = ""
        self.url = ""
        self.proc = None
        self._opened = False

    def start(self):
        if not self.binary:
            self.state, self.msg = "fail", N_("playit programı bulunamadı. playit.gg/download adresinden kur.")
            return
        self.state, self.msg, self.url = "wait", "", ""
        try:
            self.proc = subprocess.Popen([self.binary, "setup"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                                         creationflags=_flags())
        except OSError as e:
            self.state, self.msg = "fail", N_("playit başlatılamadı: {e}").format(e=e)
            return
        threading.Thread(target=self._read, daemon=True).start()
        tm = threading.Timer(SETUP_TIMEOUT, self.cancel)
        tm.daemon = True
        tm.start()

    def _read(self):
        lines = []
        for line in self.proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
            m = CLAIM_RE.search(line)
            if m and not self.url:
                self.url = m.group(0)
                self.state = "url"
                if self.open_url and not self._opened and os.name != "nt":   # Windows'ta playit kendisi açar
                    self._opened = True
                    self.open_url(self.url)
            if "setup is complete" in line.lower():
                self.state = "done"
        code = self.proc.wait()
        text = "\n".join(lines)
        if self.state == "done" or code == 0:
            self.state = "done"
        elif "already has a configured secret" in text:
            self.state, self.msg = "done", N_("Playit zaten bir hesaba bağlı.")
        elif self.state != "fail":
            tail = lines[-1] if lines else ""
            self.state, self.msg = "fail", (tail[:200] or N_("Hesap bağlanamadı."))

    def cancel(self):
        p = self.proc
        if p and p.poll() is None:
            p.terminate()
            if self.state in ("wait", "url"):
                self.state, self.msg = "fail", N_("Onay beklerken süre doldu.")


def status_text(binary):
    """`playit status` çıktısının ilk satırı (bilgi için); program yoksa boş."""
    if not binary:
        return ""
    code, text = _run(binary, "status", timeout=8)
    return text.strip().splitlines()[0][:160] if text.strip() else ""
