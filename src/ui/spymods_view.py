"""Eklentiler/Modlar sayfasındaki "Spypaper Modları" sekmesi: hazır veri paketlerini kurar/kaldırır."""
from PySide6.QtWidgets import QVBoxLayout, QWidget

from core import spymods as SM
from core.config import detect_version
from core.danger import level_name
from .i18n import t
from .widgets import Card, button, color, label, row


class SpyModsView(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page, self.app = page, page.app
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addWidget(label("Spypaper'ın hazır modları veri ya da kaynak paketi olarak kurulur: tüm sunucu türlerinde "
                          "çalışır, oyuncuların bir şey kurması gerekmez.",
                          "Muted", wrap=True))
        self.rows = {}
        for m in SM.MODS:
            card = Card(m["name"])
            card.add(label(m["desc"], wrap=True))
            if m.get("warn"):
                card.add(label(m["warn"], "Muted", wrap=True))
            status = label("", raw=True)
            btn = button("Kur", "primary", lambda _=False, i=m["id"]: self.toggle(i))
            card.add(row(status, None, btn, stretch_end=False))
            v.addWidget(card)
            self.rows[m["id"]] = (status, btn)
        v.addStretch(1)

    def _ctx(self):
        sp = self.app.config.server_path
        return sp, level_name(self.app.properties)

    def prepare(self):
        try:
            sp, level = self._ctx()
        except Exception:
            sp, level = "", ""
        rp_ids = self.app.config.get("spymods_rp") or []
        for mid, (status, btn) in self.rows.items():
            on = bool(sp) and SM.installed(sp, level, mid, rp_ids)
            status.setText(t("Kurulu") if on else t("Kurulu değil"))
            status.setStyleSheet(f"color:{color('accent') if on else color('text_muted')};")
            btn.setText(t("Kaldır") if on else t("Kur"))
            btn.setProperty("variant", "danger" if on else "primary")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setEnabled(bool(sp))

    def toggle(self, mid):
        if self.page.read_only():
            return
        m = SM.get(mid)
        if m.get("kind") == "resource":
            return self._toggle_rp(m)
        running = self.app.server.is_running
        try:
            sp, level = self._ctx()
            if SM.installed(sp, level, mid):
                if not self.page.confirm(t("'{name}' kaldırılsın mı?", name=t(m["name"]))):
                    return
                SM.remove(sp, level, mid)
                if running:                     # çalışan sunucuda zamanlanmış işi durdur, eşyaları normale döndür
                    for cmd in m.get("on_remove") or []:
                        self.app.server.try_send(cmd)
                    self.page.info(t("Kaldırıldı. Sunucuda hemen durduruldu."))
                else:
                    self.page.info(t("Kaldırıldı."))
            else:
                SM.install(sp, level, detect_version(sp)[0], mid, t)
                self.page.info(t("Kuruldu. Etkinleşmesi için sunucuyu yeniden başlat.") if running
                               else t("Kuruldu. Sunucu açılınca etkinleşir."))
        except Exception as e:
            self.page.error(t(e.template, **e.kw) if hasattr(e, "template") else str(e))
        self.prepare()

    def _toggle_rp(self, m):
        from .pages.content import rebuild_packs
        ids = list(self.app.config.get("spymods_rp") or [])
        on = m["id"] in ids
        if on and not self.page.confirm(t("'{name}' kaldırılsın mı?", name=t(m["name"]))):
            return
        new = [i for i in ids if i != m["id"]] if on else ids + [m["id"]]
        self.app.config.set("spymods_rp", new)
        try:
            rp, shared = rebuild_packs(self.app)
        except Exception as e:
            self.app.config.set("spymods_rp", ids)          # paket üretilemedi: eski hâline dön
            self.page.error(t(e.template, **e.kw) if hasattr(e, "template") else str(e))
            self.prepare()
            return
        head = t("Kaldırıldı.") if on else t("Kaynak paketine eklendi.")
        if shared:
            tail = t("Paylaşılan paket güncellendi. Oyuncular sunucu yeniden başlatılınca yeni paketi alır.")
        elif rp:
            tail = t("Oyunculara gitmesi için İçerik Editörü'nde kaynak paketi paylaşımını aç.")
        else:
            tail = ""
        skipped = getattr(self.app, "last_skipped_content", None) or []
        if skipped:
            tail += "\n" + t("İçerik Editörü'ndeki eksik içerikler pakete eklenmedi: {names}", names=", ".join(skipped))
        self.page.info((head + "\n" + tail).strip())
        self.prepare()
