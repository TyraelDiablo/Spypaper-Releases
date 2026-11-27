"""Güncellemeden önce deneme: sunucunun bir kopyasına yeni yazılımı kurup açar; sorunsuz açılırsa asıl
sunucu güncellenir.

Kopya, sunucu klasörünün yanına (.spypaper-trial-<ad>) alınır: dünya dahil (dönüşüm de denensin diye), yedekler,
loglar, BlueMap haritası ve önbellekler hariç. Kopyada port boş bir porta, RCON/sorgu kapalıya çekilir; sunucu
"Done" yazana kadar beklenir. Açılmazsa son hata satırları ve olası suçlu eklenti/mod (core.blame) döner.
Kopya her durumda silinir. Asıl sunucuya dokunulmaz.
"""
import os
import shutil
import socket
import time

from . import blame
from .config import N_

SKIP = {"backups", "logs", "crash-reports", "cache", "bluemap", "session.lock", "libraries", "versions",
        ".paper-remapped", "spypaper_resourcepack.zip"}
TIMEOUT = 15 * 60


class TrialError(Exception):
    def __init__(self, template, **kw):
        super().__init__(template.format(**kw) if kw else template)
        self.template, self.kw = template, kw


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Cfg:
    """Asıl profilin ayarlarını kullanır; klasör, jar ve RCON farklı."""

    def __init__(self, base, path, jar):
        self._base, self.server_path, self._jar = base, path, jar
        self.name = base.name + " (deneme)"

    def get(self, key, default=None):
        if key == "jar_name":
            return self._jar
        if key == "rcon_attach":
            return False
        v = self._base.get(key)
        return default if v is None else v


def copy_server(src, progress=None, cancel=None):
    dst = os.path.join(os.path.dirname(os.path.abspath(src)), ".spypaper-trial-" + os.path.basename(src.rstrip("\\/")))
    if os.path.exists(dst):
        shutil.rmtree(dst, ignore_errors=True)
    files = []
    for root, dirs, fs in os.walk(src):
        rel = os.path.relpath(root, src)
        if rel == ".":
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".spypaper-trial")]
            fs = [f for f in fs if f not in SKIP]
        else:
            dirs[:] = [d for d in dirs if d != "session.lock"]
        files += [os.path.join(root, f) for f in fs if f != "session.lock"]
    for i, f in enumerate(files, 1):
        if cancel and cancel():
            raise TrialError(N_("İptal edildi."))
        out = os.path.join(dst, os.path.relpath(f, src))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            shutil.copy2(f, out)
        except OSError:
            pass
        if progress and i % 50 == 0:
            progress(i, len(files))
    return dst


def prepare_props(path):
    from .clone import write_props
    write_props(path, {"server-port": str(_free_port()), "enable-rcon": "false", "enable-query": "false",
                       "motd": "Spypaper trial"})


def run(base_config, trial_path, jar, log=None, timeout=TIMEOUT, cancel=None):
    """Kopyayı açar. (başarılı, son_satırlar, şüpheliler)"""
    from .server import ServerProcess, RUNNING, STOPPED
    srv = ServerProcess(_Cfg(base_config, trial_path, jar))
    srv.start()
    t0 = time.time()
    ok = False
    try:
        while time.time() - t0 < timeout:
            if cancel and cancel():
                break
            if srv.state == RUNNING:
                ok = True
                break
            if srv.state == STOPPED:
                break
            if log and srv.history:
                log(srv.history[-1][-160:])
            time.sleep(0.5)
    finally:
        if srv.is_running:
            try:
                srv.stop()
            except Exception:
                pass
            for _ in range(120):
                if srv.state == STOPPED:
                    break
                time.sleep(0.5)
            if srv.is_running:
                try:
                    srv.process.kill()
                except Exception:
                    pass
    lines = list(srv.history)
    sus = [] if ok else blame.suspects(blame.crash_text(trial_path, lines[-400:]), trial_path)
    errors = [ln for ln in lines if "ERROR" in ln or "Exception" in ln or "FATAL" in ln][-8:]
    return ok, errors or lines[-8:], sus


def cleanup(path):
    for _ in range(10):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(1)                              # Windows: java dosyaları hemen bırakmayabilir
