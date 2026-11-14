"""Bakım modu: MOTD değiştirme, whitelist, otomatik yedek ve geri sayım.

Geri sayım duvar saatine göre tutulur (next_at); her saniye azaltılan
sayaç yerine bu sayede uygulama donsa bile kayma olmaz. Zamanlayıcıyı
arayüz katmanı çalıştırır (Qt'de QTimer ile tick() çağrılır).
"""
from datetime import datetime, timedelta

MAINT_MOTD = "§c§lSunucu Şu An Bakım Modundadır...\\n§e§lLütfen Daha Sonra Tekrar Deneyin!"
DEFAULT_MOTD = "GKMY. Bir Minecraft Sunucusu."
WARN_AT = 10  # saniye


class Maintenance:
    def __init__(self, config, server, properties, backups):
        self.config = config
        self.server = server
        self.props = properties
        self.backups = backups
        self.active = False
        self.original_motd = ""
        self._warned = False
        self.reset_timer()

    @property
    def interval(self):
        return timedelta(hours=float(self.config.get("maintenance_interval_hours")))

    def reset_timer(self):
        self.next_at = datetime.now() + self.interval
        self._warned = False

    def remaining(self):
        return max(timedelta(0), self.next_at - datetime.now()) if not self.active else timedelta(0)

    def tick(self):
        """Her saniye çağrılır. Bakım otomatik başladıysa True döner."""
        if self.active:
            return False
        left = self.remaining().total_seconds()
        if left <= WARN_AT and not self._warned:
            self.server.try_send("say §c§l[UYARI] Sunucu 10 saniye içinde Bakım Moduna girecektir!")
            self._warned = True
        if left <= 0:
            self.enable()
            return True
        return False

    def enable(self):
        """Bakımı başlatır. Alınan yedeğin yolunu döndürür (alınamadıysa None)."""
        if self.props.exists:
            current = self.props.get("motd", "")
            if current != MAINT_MOTD:
                self.original_motd = current
            self.props.set("motd", MAINT_MOTD)
        self.active = True
        self.server.try_send("save-all flush")
        self.server.try_send("whitelist on")
        try:
            return self.backups.create()
        except Exception:
            return None

    def disable(self):
        if self.props.exists:
            self.props.set("motd", self.original_motd or DEFAULT_MOTD)
        self.active = False
        self.server.try_send("whitelist off")
        self.reset_timer()
