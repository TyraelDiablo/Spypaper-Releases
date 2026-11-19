"""Dış erişim tüneli: Cloudflare "quick tunnel" (cloudflared). Hesap gerektirmez, HTTPS verir.

cloudflared programı kullanıcının bilgisayarında olmalı (Spypaper indirmez). Tünel açılınca
geçici bir https://*.trycloudflare.com adresi üretilir; uygulama kapanınca ya da panel
durunca tünel de kapanır ve adres değişir.
"""
import os
import re
import shutil
import subprocess
import threading
import time

from .config import N_

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
START_TIMEOUT = 40          # sn; ilk bağlantı yavaş olabilir
PROVIDERS = {"off": N_("Kapalı"), "cloudflare": N_("Cloudflare (cloudflared)"), "playit": N_("Playit.gg")}


class TunnelError(Exception):
    pass


def find_binary(configured=""):
    """Ayarlanan yolu ya da PATH'teki cloudflared'i bulur; yoksa None."""
    if configured and os.path.isfile(configured):
        return configured
    return shutil.which("cloudflared")


class CloudflareTunnel:
    def __init__(self, port, binary):
        self.port = int(port)
        self.binary = binary
        self.proc = None
        self.url = ""
        self.error = ""
        self._lines = []

    def start(self):
        """Tüneli başlatır ve adres gelene kadar bekler. Hata varsa TunnelError."""
        if not self.binary:
            raise TunnelError(N_("cloudflared bulunamadı. Ayarlardan programın yolunu seç."))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                [self.binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=flags, text=True, encoding="utf-8", errors="replace")
        except OSError as e:
            raise TunnelError(N_("cloudflared başlatılamadı: {e}").format(e=e)) from None
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        deadline = time.time() + START_TIMEOUT
        while time.time() < deadline:
            if self.url:
                return self.url
            if self.proc.poll() is not None:
                break
            time.sleep(0.2)
        self.stop()
        raise TunnelError(self.error or N_("Tünel adresi alınamadı (internet bağlantısını kontrol et)."))

    def _read(self):
        for line in self.proc.stdout:
            if len(self._lines) < 200:
                self._lines.append(line.rstrip())
            if not self.url:
                m = URL_RE.search(line)
                if m:
                    self.url = m.group(0)
        if not self.url:
            tail = [ln for ln in self._lines if "ERR" in ln or "error" in ln.lower()]
            self.error = (tail[-1] if tail else N_("cloudflared beklenmedik şekilde kapandı."))[:200]

    def stop(self):
        p, self.proc = self.proc, None
        self.url = ""
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
