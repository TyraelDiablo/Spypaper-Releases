"""Sunucu Ayarları: Oyunculara giden mesajların dili (core.playermsg)."""
from core import playermsg as PM
from core.config import detect_version
from .i18n import t
from .widgets import Card, button, label, row

BUKKIT = {"Paper", "Purpur", "Folia", "Spigot", "Pufferfish"}


class PlayerMsgCard(Card):
    def __init__(self, page):
        super().__init__("Oyunculara Giden Mesajlar", "Uyarılar, geri sayımlar ve atma mesajları her oyuncunun kendi oyun dilinde")
        self.page = page
        self.add(label("Paper, Purpur ve Folia'da SpypaperMessages eklentisi oyuncunun oyun dilini bilir ve uyarıları ve atma "
                       "mesajlarını o dilde gönderir (16 dil ve Language Wizard'la yaptığın diller; olmayanlar İngilizce). "
                       "Eklenti yoksa uyarılar sunucunun Spypaper kaynak paketinden çevrilir, atma mesajları panel dilinde "
                       "ve İngilizce gider.", "Muted", wrap=True))
        self.status = label("", wrap=True)
        self.add(self.status)
        self.btn_plugin = button("Eklentiyi Kur", "ghost", self.toggle_plugin)
        self.btn_pack = button("Kaynak Paketini Yenile", "ghost", self.refresh_pack)
        self.add(row(self.btn_plugin, self.btn_pack))

    def _bukkit(self):
        return detect_version(self.page.app.config.server_path)[1] in BUKKIT

    def load(self):
        app = self.page.app
        sp = app.config.server_path
        share = (app.config.get("content_share") or {}).get("enabled")
        lines = [t("Kaynak paketi paylaşımı (eklentisiz uyarılar için): {s}", s=t("açık") if share else t("kapalı (İçerik Editörü'nden açılır)"))]
        if self._bukkit():
            on = PM.plugin_installed(sp)
            lines.append(t("Uyarı ve atma mesajları: {s}", s=t("oyuncunun dilinde (SpypaperMessages eklentisi)") if on
                           else t("panel dilinde + İngilizce. Oyuncunun dilinde olması için eklentiyi kur.")))
            self.btn_plugin.setText(t("Eklentiyi Kaldır") if on else t("Eklentiyi Kur"))
            self.btn_plugin.show()
        else:
            lines.append(t("Atma mesajları: panel dilinde + İngilizce (bu sunucu türü eklenti yükleyemez)."))
            self.btn_plugin.hide()
        self.status.setText("\n".join(lines))

    def toggle_plugin(self):
        app = self.page.app
        sp = app.config.server_path
        on = not PM.plugin_installed(sp)
        try:
            PM.set_plugin(sp, on)
        except OSError as e:
            self.page.error(str(e))
            return
        self.load()
        if app.server.is_running:
            self.page.info(t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))

    def refresh_pack(self):
        from .pages.content import rebuild_packs
        try:
            rp, shared = rebuild_packs(self.page.app)
        except Exception as e:
            self.page.error(str(e))
            return
        if not rp:
            self.page.info(t("Kaynak paketi paylaşımı kapalı; önce İçerik Editörü'nden paylaşımı aç."))
        else:
            self.page.info(t("Kaynak paketi yenilendi; oyuncular bir sonraki girişte yeni paketi alır.") if shared
                           else t("Kaynak paketi oluşturuldu ama paylaşım kapalı."))
