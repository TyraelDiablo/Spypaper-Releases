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
        self.backups = BackupManager(sp, keep=lambda: profile.get("backup_keep"))
        self.logs = LogWatcher(sp)
        self.maintenance = Maintenance(profile, self.server, self.properties, self.backups, online=self.online_players)
        self.metrics = ProcessMetrics(self.server, profile)
        self.logtrans = LogTranslator(self.players.translations)
        from .guard import Guard
        self.guard = Guard(profile, self.server)
        from .scheduler import Scheduler
        self.scheduler = Scheduler(profile, self.server, self.backups)
        from .perf import PerfMonitor
        self.perf = PerfMonitor(profile, self.server)
        from .pregen import Pregen
        self.pregen = Pregen(self.server, self.online_players)
        from .sanctions import Sanctions
        self.sanctions = Sanctions(profile, self.server)
        from .perfhist import PerfHistory
        self.perfhist = PerfHistory(self)
        from .discord import Discord
        self.discord = Discord(profile, self.server)
        self.maintenance.notify = lambda started: self.discord.event("maintenance", started=started)
        self.scheduler.notify = lambda name, status: self.discord.event("task", name=name, status=status)
        self.player_locales = {}                     # oyuncu adı -> oyun dili (SpypaperMessages eklentisinden)
        self.server.line_filters.append(self._locale_line)
        try:
            from . import playermsg
            if playermsg.plugin_installed(sp):
                playermsg.write_plugin_texts(sp)     # yeni Spypaper sürümü / yeni dil: çeviriler güncel kalsın
        except OSError as e:
            print(f"[playermsg] {e}")
        self.scheduler.reporter = self._report
        self.scheduler.on_report = lambda title, lines: self.discord.event("report", name=title, text="\n".join(lines))

    def _locale_line(self, line):
        from .playermsg import parse_locale
        got = parse_locale(line)
        if got:
            self.player_locales[got[0].lower()] = got[1]
            return True                              # konsolda gösterilmez
        return False

    def _report(self, hours):
        from . import report
        title, lines = report.build(self, hours, tr=self.scheduler.tr)
        report.save(self.config.server_path, title, lines)
        return title, lines

    def online_players(self):
        """Log'daki giriş/çıkışlara göre şu an içerideki oyuncular (log'u panel okur, burada okunmaz:
        okunursa panelin olay akışı o satırları kaçırır)."""
        if not self.server.is_running:
            return []
        from .logwatch import online_timeline
        return sorted(online_timeline(self.logs.events)[1])

    @property
    def id(self):
        return self.config.id

    def set_server_path(self, path):
        if self.server.is_running:
            raise ServerError("Sunucu çalışırken klasör değiştirilemez!")
        self.config.set("server_path", path)
        for svc in (self.players, self.plugins, self.properties, self.backups, self.logs):
            svc.set_server_path(path)
