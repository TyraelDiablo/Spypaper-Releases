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
        self.hooks = []       # fn(str): her satırda, arayüzden bağımsız (ör. core.guard)
        self.send_hooks = []  # fn(str): gönderilen her komutta
        self.state_hooks = [] # fn(state): her durum değişiminde, arayüzden bağımsız (ör. core.discord)
        self.line_filters = []  # fn(str) -> True: satır panelin kendi sorgusunun yanıtı, gösterilmez (core.perf)
        self.history = deque(maxlen=5000)   # arayüz yeniden kurulunca konsol buradan dolar
        self.stop_requested = False
        self.crashed = False                # son kapanış beklenmedik miydi (durdurulmadan kapandı)
        self.exit_code = None
        self.run_id = 0                     # her başlatmada artar
        self.ended_run = 0                  # sona eren son çalıştırmanın numarası (çökme bekçisi için)
        self.external = False               # Spypaper dışında açık kalmış sunucuya yeniden bağlanıldı (core.attach)

    # --- durum ---
    @property
    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def _set_state(self, state):
        self.state = state
        for hook in list(self.state_hooks):
            try:
                hook(state)
            except Exception as e:
                print(f"[hook] {e}")
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
        if self.config.get("rcon_attach") is not False:
            try:
                from .attach import ensure_rcon
                ensure_rcon(path)               # Spypaper kapansa da sonra yeniden bağlanılabilsin
            except Exception as e:
                print(f"[attach] {e}")
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
        self.external = False
        self.stop_requested = False
        self.crashed = False
        self.exit_code = None
        self.run_id += 1
        self._set_state(STARTING)
        threading.Thread(target=self._read_output, daemon=True).start()

    def attach(self):
        """Sunucu klasöründe hâlâ çalışan bir java süreci varsa ona bağlanır. True: bağlandı."""
        if self.is_running:
            return False
        try:
            from .attach import ExternalProcess, find_process
            ps = find_process(self.config.server_path)
            if not ps:
                return False
            proc = ExternalProcess(ps, self.config.server_path)
        except Exception as e:
            print(f"[attach] {e}")
            return False
        self.history.clear()
        try:                                    # bağlamı göstermek için log'un son satırları
            with open(os.path.join(self.config.server_path, "logs", "latest.log"), encoding="utf-8",
                      errors="replace") as f:
                from .attach import normalize
                from .perf import HIDE, _msg
                for ln in f.readlines()[-300:]:
                    ln = normalize(ln)
                    if ln and not HIDE.match(_msg(ln)) and not self._filtered(ln):   # TPS sorguları gizli
                        self.history.append(ln)
        except OSError:
            pass
        self.process = proc
        self.external = True
        self.stop_requested = False
        self.crashed = False
        self.exit_code = None
        self.run_id += 1
        self._set_state(RUNNING)
        threading.Thread(target=self._read_output, daemon=True).start()
        return True

    @property
    def can_send(self):
        return self.is_running and (not self.external or self.process.writable)

    def stop(self):
        if self.is_running:
            self.stop_requested = True
            self.send("stop")
            self._set_state(STOPPING)

    def send(self, command):
        """Komut gönderir. Sunucu kapalıysa ServerError fırlatır."""
        if not self.is_running:
            raise ServerError("Sunucu kapalı iken komut gönderilemez!")
        command = command.strip().lstrip("/")
        if not command:
            return
        if self.external and not self.process.writable:
            raise ServerError("Bu sunucu Spypaper kapalıyken açık kaldı ve RCON kapalı; konsol yalnızca okunabilir. "
                              "Komut gönderebilmek için sunucuyu bir kez Spypaper'dan yeniden başlat.")
        for hook in list(self.send_hooks):
            try:
                hook(command)
            except Exception as e:
                print(f"[hook] {e}")
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

    def _filtered(self, line):
        for f in list(self.line_filters):
            try:
                if f(line):
                    return True
            except Exception as e:
                print(f"[filter] {e}")
        return False

    def _read_output(self):
        proc = self.process
        run = self.run_id
        while proc.poll() is None:
            line = proc.stdout.readline()
            if not line:
                break
            clean = line.rstrip()
            if "Done (" in clean or "For help, type" in clean:
                self._set_state(RUNNING)
            elif "Stopping server" in clean or "Stopping the server" in clean:
                self.stop_requested = True          # konsoldan /stop da isteyerek durdurmadır
                self._set_state(STOPPING)
            if self._filtered(clean):
                continue
            self.history.append(clean)
            for hook in list(self.hooks):
                try:
                    hook(clean)
                except Exception as e:
                    print(f"[hook] {e}")
            if self.on_line:
                self.on_line(clean)
        try:
            self.exit_code = proc.wait(timeout=10)
        except Exception:
            self.exit_code = None
        self.crashed = not self.stop_requested
        self.ended_run = run
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
