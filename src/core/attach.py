"""Spypaper dışında (ya da Spypaper kapanıp yeniden açılınca) hâlâ çalışan sunucuya yeniden bağlanma.

Spypaper sunucuyu kendi alt süreci olarak başlatır; Spypaper kapanırsa (çökme, görev yöneticisi…) sunucu çalışmaya
devam edebilir ama konsolu (stdin/stdout) kaybolur. Spypaper açılınca:
  * sunucu klasöründe çalışan java süreci aranır (psutil, çalışma klasörü = sunucu klasörü),
  * konsol çıktısı logs/latest.log'dan izlenir,
  * komutlar RCON ile gönderilir (server.properties'te RCON açıksa; Spypaper sunucuyu başlatırken bunu kendisi
    hazırlayabilir: rastgele güçlü parola, şifreli saklanır). RCON yoksa konsol yalnızca okunur.
ExternalProcess, subprocess.Popen'ın ServerProcess'in kullandığı kısmını taklit eder; böylece geri kalan her şey
(durum, kancalar, TPS, Discord…) değişmeden çalışır.
"""
import os
import queue
import secrets as pysecrets
import socket
import struct
import threading
import time

RCON_PORT_OFFSET = 10


# ------------------------------------------------------------ RCON
class Rcon:
    def __init__(self, host, port, password, timeout=5):
        self.host, self.port, self.password, self.timeout = host, port, password, timeout
        self.sock = None
        self._id = 0
        self._lock = threading.Lock()

    def _pkt(self, kind, body):
        self._id += 1
        data = struct.pack("<ii", self._id, kind) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(data)) + data)
        return self._id

    def _read(self):
        def exact(n):
            buf = b""
            while len(buf) < n:
                chunk = self.sock.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("rcon closed")
                buf += chunk
            return buf
        size = struct.unpack("<i", exact(4))[0]
        data = exact(size)
        rid, kind = struct.unpack("<ii", data[:8])
        return rid, kind, data[8:-2].decode("utf-8", "replace")

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._pkt(3, self.password)
        rid, _k, _b = self._read()
        if rid == -1:
            self.close()
            raise PermissionError("rcon auth")

    def command(self, cmd):
        with self._lock:
            if self.sock is None:
                self.connect()
            try:
                self._pkt(2, cmd)
                return self._read()[2]
            except OSError:
                self.close()
                self.connect()
                self._pkt(2, cmd)
                return self._read()[2]

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = None


# ------------------------------------------------------------ server.properties
def _props(path):
    out = {}
    try:
        with open(os.path.join(path, "server.properties"), encoding="utf-8") as f:
            for ln in f:
                if "=" in ln and not ln.lstrip().startswith("#"):
                    k, v = ln.rstrip("\n").split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def rcon_settings(server_path):
    """(port, parola) ya da None."""
    p = _props(server_path)
    if p.get("enable-rcon", "false").lower() != "true" or not p.get("rcon.password"):
        return None
    try:
        return int(p.get("rcon.port") or 25575), p["rcon.password"]
    except ValueError:
        return None


def ensure_rcon(server_path):
    """Spypaper'ın yeniden bağlanabilmesi için RCON'u açar (zaten açıksa dokunmaz). True: değişiklik yapıldı."""
    if rcon_settings(server_path):
        return False
    p = _props(server_path)
    try:
        port = int(p.get("server-port") or 25565) + RCON_PORT_OFFSET
    except ValueError:
        port = 25575
    from .clone import write_props
    write_props(server_path, {"enable-rcon": "true", "rcon.port": str(port),
                              "rcon.password": pysecrets.token_urlsafe(24), "broadcast-rcon-to-ops": "false"})
    return True


# ------------------------------------------------------------ süreç arama
def find_process(server_path):
    try:
        import psutil
    except ImportError:
        return None
    target = os.path.normcase(os.path.abspath(server_path))
    for p in psutil.process_iter(["name"]):
        try:
            if "java" in (p.info["name"] or "").lower() and os.path.normcase(p.cwd()) == target:
                return p
        except psutil.Error:
            continue
    return None


# ------------------------------------------------------------ Popen taklidi
class _Stdin:
    def __init__(self, owner):
        self.owner = owner

    def write(self, text):
        cmd = text.strip()
        if not cmd:
            return
        if not self.owner.rcon:
            raise OSError("no rcon")
        try:
            reply = self.owner.rcon.command(cmd)
        except (OSError, ConnectionError):
            if cmd.split()[0].lower() in ("stop", "end", "restart"):
                return                               # sunucu kapanırken bağlantı kopar: beklenen durum
            raise
        for ln in (reply or "").splitlines():
            if ln.strip():
                self.owner.extra.put(ln)

    def flush(self):
        pass


class _Stdout:
    """logs/latest.log'u sondan izler (yeni dönen dosyayı da yakalar) + RCON yanıtları."""

    def __init__(self, owner, log_path):
        self.owner, self.path = owner, log_path
        self.f, self.inode = None, None

    def _open(self, at_end):
        try:
            f = open(self.path, encoding="utf-8", errors="replace")
        except OSError:
            return
        if at_end:
            f.seek(0, os.SEEK_END)
        if self.f:
            self.f.close()
        self.f, self.inode = f, os.stat(self.path).st_size

    def readline(self):
        if self.f is None:
            self._open(at_end=True)
        while True:
            try:
                return self.owner.extra.get_nowait() + "\n"
            except queue.Empty:
                pass
            if self.owner.poll() is not None:
                return ""
            if self.f:
                line = self.f.readline()
                if line:
                    return line
                try:                                         # log döndü (yeni gün / yeniden başlatma)
                    if os.stat(self.path).st_size < self.f.tell():
                        self._open(at_end=False)
                except OSError:
                    pass
            else:
                self._open(at_end=False)
            time.sleep(0.25)


class ExternalProcess:
    def __init__(self, ps_proc, server_path):
        self.ps = ps_proc
        self.pid = ps_proc.pid
        self.extra = queue.Queue()
        self.rcon = None
        st = rcon_settings(server_path)
        if st:
            r = Rcon("127.0.0.1", st[0], st[1])
            try:
                r.connect()
                self.rcon = r
            except (OSError, PermissionError):
                r.close()
        self.stdin = _Stdin(self)
        self.stdout = _Stdout(self, os.path.join(server_path, "logs", "latest.log"))

    @property
    def writable(self):
        return self.rcon is not None

    def poll(self):
        try:
            return None if self.ps.is_running() and self.ps.status() != "zombie" else 0
        except Exception:
            return 0

    def wait(self, timeout=None):
        try:
            self.ps.wait(timeout=timeout)
        except Exception:
            pass
        if self.rcon:
            self.rcon.close()
        return 0
