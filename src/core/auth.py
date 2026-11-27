"""Panel doğrulaması: Spypaper'a erişim için şifre, güvenlik sorusu ve kimlik doğrulama uygulaması (TOTP).

Ayar: config.json -> "panel_auth"
  password : PBKDF2 hash (safemode.hash_pin) ya da ""
  question : {"q": soru, "a": hash(normalize(cevap))} ya da {}
  totp     : {"secret": şifreli base32 (core.secrets), "recovery": [hash...]} ya da {}
  on_start : Spypaper açılırken sor
  on_sleep : uyku modundan çıkarken sor (uyku PIN'i yerine)

Doğrulama: şifre ve TOTP ayarlıysa ikisi de istenir. Güvenlik sorusu şifrenin yerine geçer
("Şifremi unuttum"); TOTP yerine tek kullanımlık kurtarma kodu girilebilir. Yalnızca soru ayarlıysa soru sorulur.
"""
import base64
import hashlib
import hmac
import os
import re
import struct
import time
import unicodedata
import urllib.parse

from .config import N_
from .safemode import hash_pin, verify_pin

ISSUER = "Spypaper"
PERIOD, DIGITS = 30, 6
MIN_PASSWORD = 8
QUESTIONS = [
    N_("İlk evcil hayvanının adı neydi?"),
    N_("Doğduğun şehir neresi?"),
    N_("İlk okulunun adı neydi?"),
    N_("En sevdiğin Minecraft bloğu hangisi?"),
    N_("Çocukken en sevdiğin oyun neydi?"),
]


def cfg(settings):
    c = dict(settings.get("panel_auth") or {})
    c.setdefault("password", "")
    c.setdefault("question", {})
    c.setdefault("totp", {})
    c.setdefault("on_start", False)
    c.setdefault("on_sleep", True)
    return c


def save(settings, c):
    settings.set("panel_auth", c)


def enabled(settings):
    c = cfg(settings)
    return bool(c["password"] or c["totp"] or c["question"])


def methods(settings):
    c = cfg(settings)
    return [k for k in ("password", "question", "totp") if c[k]]


# ------------------------------------------------------------------ şifre
def password_problem(pw):
    if len(pw) < MIN_PASSWORD:
        return N_("Şifre en az {n} karakter olmalı.")
    if not (re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", pw) and re.search(r"\d", pw)):
        return N_("Şifrede en az bir harf ve bir rakam olmalı.")
    return None


# ------------------------------------------------------------------ güvenlik sorusu
def normalize_answer(a):
    a = unicodedata.normalize("NFKC", a or "").casefold()
    a = a.replace("ı", "i").replace("i̇", "i")
    return re.sub(r"\s+", " ", a).strip()


def hash_answer(a):
    return hash_pin(normalize_answer(a))


def verify_answer(a, stored):
    return bool(stored) and verify_pin(normalize_answer(a), stored)


# ------------------------------------------------------------------ TOTP (RFC 6238)
def new_secret():
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _key(secret):
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def totp(secret, at=None, step=0):
    counter = int((at if at is not None else time.time()) // PERIOD) + step
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def verify_totp(secret, code, at=None, window=1):
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code):
        return False
    return any(hmac.compare_digest(totp(secret, at, s), code) for s in range(-window, window + 1))


def otpauth_uri(secret, account="Spypaper"):
    label = urllib.parse.quote(f"{ISSUER}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&digits={DIGITS}&period={PERIOD}"


def recovery_codes(n=8):
    out = []
    for _ in range(n):
        raw = base64.b32encode(os.urandom(5)).decode("ascii")[:8]
        out.append(f"{raw[:4]}-{raw[4:]}")
    return out


def _norm_rc(code):
    return re.sub(r"[\s-]", "", code or "").upper()


def hash_recovery(code):
    return hash_pin(_norm_rc(code))


def use_recovery(settings, code):
    """Kurtarma kodu doğruysa siler (tek kullanımlık) ve True döndürür."""
    c = cfg(settings)
    codes = list((c["totp"] or {}).get("recovery") or [])
    for i, h in enumerate(codes):
        if verify_pin(_norm_rc(code), h):
            del codes[i]
            c["totp"] = dict(c["totp"], recovery=codes)
            save(settings, c)
            return True
    return False


def totp_secret(settings):
    from .secrets import unprotect
    return unprotect((cfg(settings)["totp"] or {}).get("secret", "")) or ""


def setup_totp(settings, secret, codes):
    from .secrets import protect
    c = cfg(settings)
    c["totp"] = {"secret": protect(secret), "recovery": [hash_recovery(x) for x in codes]}
    save(settings, c)


# ------------------------------------------------------------------ doğrulama
def check(settings, password="", answer="", code=""):
    """(tamam, hata_şablonu). Kurtarma kodu TOTP alanına yazılabilir."""
    c = cfg(settings)
    if not enabled(settings):
        return True, None
    first_ok = True
    if c["password"]:
        if password:
            first_ok = verify_pin(password, c["password"])
        elif answer and c["question"]:
            first_ok = verify_answer(answer, c["question"].get("a"))
        else:
            first_ok = False
        if not first_ok:
            return False, N_("Şifre ya da güvenlik sorusunun cevabı yanlış.")
    elif c["question"]:
        if not verify_answer(answer, c["question"].get("a")):
            return False, N_("Güvenlik sorusunun cevabı yanlış.")
    if c["totp"]:
        sec = totp_secret(settings)
        ok = bool(sec) and verify_totp(sec, code)
        if not ok and _norm_rc(code) and not re.fullmatch(r"\d{6}", re.sub(r"\s", "", code)):
            ok = use_recovery(settings, code)
        if not ok:
            return False, N_("Doğrulama kodu yanlış.")
    return True, None


class Limiter:
    """Art arda yanlış denemelerde bekleme: 5 yanlıştan sonra 30 sn, sonra katlanarak (en çok 15 dk)."""

    def __init__(self):
        self.fails, self.until = 0, 0.0

    def wait(self, now=None):
        return max(0, int(self.until - (now or time.time())))

    def failed(self, now=None):
        self.fails += 1
        if self.fails >= 5:
            self.until = (now or time.time()) + min(900, 30 * 2 ** (self.fails - 5))

    def ok(self):
        self.fails, self.until = 0, 0.0
