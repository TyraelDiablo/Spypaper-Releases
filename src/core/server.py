"""Minecraft sunucu sürecini başlatma, durdurma ve komut gönderme.

Arayüzden bağımsızdır: olaylar callback ile bildirilir. Callback'ler
okuma thread'inden çağrılır; arayüz katmanı bunları kendi ana
thread'ine taşımalıdır (Qt'de sinyal ile).
"""
import os
import subprocess
import threading
from collections import deque

STOPPED, STARTING, RUNNING, STOPPING = "stopped", "starting", "running", "stopping"


class ServerError(Exception):
    """template: çevrilebilir metin (Türkçe kaynak), kw: yer tutucular.
    Arayüz t(e.template, **e.kw) ile kullanıcının dilinde gösterir."""

    def __init__(self, template, **kw):
        self.template, self.kw = template, kw
        super().__init__(template.format(**kw) if kw else template)


class ServerProcess:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.state = STOPPED
        self._lock = threading.Lock()
        self.on_line = None   # fn(str)
        self.on_state = None  # fn(state)
        self.history = deque(maxlen=5000)   # arayüz yeniden kurulunca konsol buradan dolar

    # --- durum ---
    @property
    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def _set_state(self, state):
        self.state = state
        if self.on_state:
            self.on_state(state)

    # --- kontrol ---
    def start(self):
        if self.is_running:
            raise ServerError("Sunucu zaten çalışıyor!")
        path = self.config.server_path
        jar = self.config.get("jar_name")
        if not os.path.exists(os.path.join(path, jar)):
            raise ServerError("Klasörde '{jar}' bulunamadı:\n{path}", jar=jar, path=path)

        cmd = [
            self.config.get("java_path"),
            f"-Xmx{self.config.get('ram_max')}",
            f"-Xms{self.config.get('ram_min')}",
            # Windows'ta Java konsol çıktısını yerel kod sayfasıyla (ör. cp1254) yazar; panel UTF-8 okur.
            # Bunlar olmadan sohbetteki ş, ğ, ı gibi harfler bozulur, gönderilen komutlardaki harfler de.
            "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
        ]
        if jar.endswith("_args.txt"):
            # Forge 1.17+ / NeoForge: jar yok, argüman dosyalarıyla başlatılır
            if os.path.exists(os.path.join(path, "user_jvm_args.txt")):
                cmd.append("@user_jvm_args.txt")
            cmd += [f"@{jar}", "nogui"]
        else:
            cmd += ["-jar", jar, "nogui"]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self.process = subprocess.Popen(
                cmd, cwd=path,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, **kwargs,
            )
        except Exception as e:
            raise ServerError("Sunucu başlatılamadı:\n{e}", e=e)

        self.history.clear()
        self._set_state(STARTING)
        threading.Thread(target=self._read_output, daemon=True).start()

    def stop(self):
        if self.is_running:
            self.send("stop")
            self._set_state(STOPPING)

    def send(self, command):
        """Komut gönderir. Sunucu kapalıysa ServerError fırlatır."""
        if not self.is_running:
            raise ServerError("Sunucu kapalı iken komut gönderilemez!")
        command = command.strip().lstrip("/")
        if not command:
            return
        with self._lock:
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except Exception as e:
                raise ServerError("Komut gönderilemedi: {e}", e=e)

    def try_send(self, command):
        """Sunucu kapalıysa sessizce geçer."""
        try:
            self.send(command)
            return True
        except ServerError:
            return False

    def _read_output(self):
        proc = self.process
        while proc.poll() is None:
            line = proc.stdout.readline()
            if not line:
                break
            clean = line.rstrip()
            if "Done (" in clean or "For help, type" in clean:
                self._set_state(RUNNING)
            elif "Stopping server" in clean:
                self._set_state(STOPPING)
            self.history.append(clean)
            if self.on_line:
                self.on_line(clean)
        self._set_state(STOPPED)


_LEVEL_RE = __import__("re").compile(r"[\[/ ](INFO|WARN|ERROR|FATAL|SEVERE)\]")


def classify_log_line(text):
    """Log satırının türü: error / warn / cmd / info / plain.
    Hem '[12:00:00] [Server thread/WARN]:' hem Paper konsolu '[12:00:00 WARN]:' tanınır."""
    m = _LEVEL_RE.search(text[:60])
    level = m.group(1) if m else ""
    if level in ("ERROR", "FATAL", "SEVERE") or "Exception" in text:
        return "error"
    if level == "WARN":
        return "warn"
    if "issued server command:" in text:
        return "cmd"
    if level == "INFO":
        return "info"
    return "plain"
