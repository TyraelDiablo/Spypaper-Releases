"""Spypaper çekirdek katmanı — arayüzden bağımsız iş mantığı.

Kullanım:
    from core import Settings, App
    settings = Settings()
    app = App(settings.servers()[0])
    app.server.start()
"""
from .config import N_, Settings, ServerProfile, get_base_dir, resource_dir, detect_jars, detect_version, is_modded
from .server import ServerProcess, ServerError, classify_log_line
from .players import PlayerService
from .files import PluginStore, ServerProperties, BackupManager
from .maintenance import Maintenance
from .logwatch import LogWatcher, ProcessMetrics
from .logtrans import LogTranslator


class App:
    """Tek bir sunucunun tüm servisleri; arayüz yalnızca bununla konuşur.
    config: ServerProfile (get/set/server_path)."""

    def __init__(self, profile):
        self.config = profile
        sp = profile.server_path
        self.server = ServerProcess(profile)
        self.players = PlayerService(sp)
        self.plugins = PluginStore(sp, profile)
        self.properties = ServerProperties(sp)
        self.backups = BackupManager(sp)
        self.maintenance = Maintenance(profile, self.server, self.properties, self.backups)
        self.logs = LogWatcher(sp)
        self.metrics = ProcessMetrics(self.server, profile)
        self.logtrans = LogTranslator(self.players.translations)

    @property
    def id(self):
        return self.config.id

    def set_server_path(self, path):
        if self.server.is_running:
            raise ServerError("Sunucu çalışırken klasör değiştirilemez!")
        self.config.set("server_path", path)
        for svc in (self.players, self.plugins, self.properties, self.backups, self.logs):
            svc.set_server_path(path)
