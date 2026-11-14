"""API anahtarlarını config.json'da düz metin tutmamak için.

Windows: DPAPI (CryptProtectData) — yalnızca aynı Windows kullanıcısı çözebilir.
Diğer sistemler: yalnızca gizleme (base64); gerçek şifreleme değildir.
"""
import base64
import ctypes
import os

PREFIX_DPAPI = "dpapi:"
PREFIX_B64 = "b64:"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _dpapi(data, protect):
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src, _keep = _blob(data)
    out = _BLOB()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(src), None, None, None, None, 0x01, ctypes.byref(out))  # UI_FORBIDDEN
    if not ok:
        raise OSError("DPAPI hatası")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def protect(text):
    if not text:
        return ""
    raw = text.encode("utf-8")
    if os.name == "nt":
        try:
            return PREFIX_DPAPI + base64.b64encode(_dpapi(raw, True)).decode()
        except Exception:
            pass
    return PREFIX_B64 + base64.b64encode(raw).decode()


def unprotect(stored):
    if not stored:
        return ""
    try:
        if stored.startswith(PREFIX_DPAPI):
            return _dpapi(base64.b64decode(stored[len(PREFIX_DPAPI):]), False).decode("utf-8")
        if stored.startswith(PREFIX_B64):
            return base64.b64decode(stored[len(PREFIX_B64):]).decode("utf-8")
    except Exception:
        return ""
    return stored


def mask(key):
    return (key[:7] + "…" + key[-4:]) if len(key) > 14 else ("•" * len(key))
