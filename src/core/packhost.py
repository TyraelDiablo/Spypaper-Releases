"""Kaynak paketi paylaşımı: içerik editörünün ürettiği paketi oyunculara Spypaper'ın kendisi sunar.

Minecraft sunucu kaynak paketini bir adresten indirtir. Spypaper açıkken küçük bir HTTP sunucusu
yalnızca kayıtlı paket dosyalarını verir: GET /<sunucu_id>/<sha1>.zip  (başka hiçbir dosya verilmez).
Ev ağı ve Tailscale'de doğrudan çalışır; internetteki oyuncular için bu port da yönlendirilmeli ya da
paket başka bir yere yüklenip adresi elle girilmeli.
"""
import os
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8766
_PATH = re.compile(r"^/([A-Za-z0-9_-]{1,64})/([0-9a-f]{40})\.zip$")


class _Handler(BaseHTTPRequestHandler):
    server_version = "Spypaper"
    sys_version = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        m = _PATH.match(self.path.split("?", 1)[0])
        entry = self.server.host.files.get((m.group(1), m.group(2))) if m else None
        if not entry or not os.path.isfile(entry):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        size = os.path.getsize(entry)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(entry, "rb") as f:
            while True:
                chunk = f.read(256 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


class PackHost:
    def __init__(self):
        self.files = {}            # (sunucu_id, sha1) -> dosya yolu
        self.httpd = None
        self.port = None

    @property
    def running(self):
        return self.httpd is not None

    def start(self, port=DEFAULT_PORT):
        if self.httpd and self.port == port:
            return
        self.stop()
        self.httpd = _Server(("0.0.0.0", int(port)), _Handler)
        self.httpd.host = self
        self.port = int(port)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.httpd = self.port = None

    def register(self, sid, path, sha1):
        for k in [k for k in self.files if k[0] == sid]:
            del self.files[k]
        self.files[(sid, sha1)] = path

    def unregister(self, sid):
        for k in [k for k in self.files if k[0] == sid]:
            del self.files[k]

    def url(self, address, sid, sha1):
        host = f"[{address}]" if ":" in address else address
        return f"http://{host}:{self.port}/{sid}/{sha1}.zip"


HOST = PackHost()
