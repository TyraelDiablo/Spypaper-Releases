"""Oyuncular → Skin Değiştir: SkinsRestorer ile seçili oyuncunun skin'ini bu sunucuda değiştirir."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QVBoxLayout

from core import skinsr as SR
from core.config import detect_version
from .i18n import t
from .widgets import button, label, row


class SkinDialog(QDialog):
    job_done = Signal(object, object)

    def __init__(self, page, player):
        super().__init__(page)
        self.page, self.app, self.player = page, page.app, player
        self.setWindowTitle(t("Skin Değiştir"))
        self.setMinimumWidth(500)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label(t("Skin Değiştir: {name}", name=player.name), "PageTitle", raw=True))
        v.addWidget(label("Skin yalnızca bu sunucuda değişir. Değiştirmeyi sunucudaki SkinsRestorer eklentisi yapar; "
                          "oyuncunun bir şey kurması gerekmez. Çevrimdışı oyuncunun skin'i girişte uygulanır.",
                          "Muted", wrap=True))
        self.state = label("", wrap=True, raw=True)
        v.addWidget(self.state)
        self.install_btn = button("Kur (Modrinth: SkinsRestorer)", "primary", self._install)
        v.addLayout(row(self.install_btn, None))
        self.src = QLineEdit(self._current() or "")
        self.src.setPlaceholderText(t("Oyuncu adı (ör. Notch) ya da skin bağlantısı (https://…png)"))
        self.src.textChanged.connect(self._sync)
        self.variant = QComboBox()
        self.variant.addItem(t("Kol: otomatik"), "")
        self.variant.addItem(t("Kol: klasik (4 piksel)"), "classic")
        self.variant.addItem(t("Kol: ince (3 piksel)"), "slim")
        self.form = [self.src, self.variant]
        v.addWidget(self.src)
        v.addLayout(row(self.variant, None))
        v.addWidget(label("Oyuncu adı yazarsan o oyuncunun Mojang skin'i kopyalanır. Bağlantı, bir PNG skin dosyasının "
                          "internetten açılabilen adresi olmalı (ör. NameMC ya da Imgur bağlantısı).",
                          "Muted", wrap=True))
        self.apply_btn = button("Uygula", "primary", self._apply)
        self.clear_btn = button("Skin'i sıfırla", "ghost", self._clear)
        v.addSpacing(4)
        v.addLayout(row(self.clear_btn, None, button("Kapat", "ghost", self.reject), self.apply_btn))
        self.busy = False
        self.job_done.connect(self._installed)
        self._refresh()

    # --- durum ---
    def _context(self):
        sp = self.app.config.server_path
        mc, soft = detect_version(sp)
        return mc, (soft or "").lower()

    def _current(self):
        return (self.app.config.get("skin_overrides") or {}).get(SR.norm_uuid(self.player.uuid), "")

    def _refresh(self):
        mc, soft = self._context()
        pf = SR.plugin_file(self.app.plugins.folder)
        ready = False
        if not SR.supported(soft):
            text = t("SkinsRestorer bu sunucu türünde çalışmıyor ({soft}). Paper, Purpur, Spigot, Folia, Fabric ve "
                     "NeoForge desteklenir.", soft=soft or "?")
        elif not pf:
            text = t("SkinsRestorer kurulu değil. Kurduktan sonra sunucuyu yeniden başlat.")
        elif not pf[1]:
            text = t("SkinsRestorer devre dışı ({file}). Eklentiler sayfasından etkinleştir.", file=pf[0])
        elif not self.app.server.is_running:
            text = t("SkinsRestorer kurulu ({file}). Skin değiştirmek için sunucu açık olmalı.", file=pf[0])
        else:
            text, ready = t("SkinsRestorer kurulu ({file}).", file=pf[0]), True
        self.state.setText(text)
        self.install_btn.setVisible(SR.supported(soft) and not pf)
        self.install_btn.setEnabled(not self.busy)
        self.ready = ready
        self._sync()

    def _sync(self, *_):
        for w in self.form:
            w.setEnabled(self.ready)
        is_url = self.src.text().strip().lower().startswith(("http://", "https://"))
        self.variant.setEnabled(self.ready and is_url)
        self.apply_btn.setEnabled(self.ready and bool(self.src.text().strip()))
        self.clear_btn.setEnabled(self.ready)

    # --- kurulum ---
    def _install(self):
        if self.busy or self.page.read_only():
            return
        from core import modrinth as M
        mc, soft = self._context()
        _, loaders = M.context(soft, mc, self.app.plugins.modded)
        folder = self.app.plugins.folder
        self.busy = True
        self.install_btn.setEnabled(False)
        self.state.setText(t("Modrinth'ten indiriliyor…"))

        def work():
            try:
                self.job_done.emit(SR.install(folder, loaders, mc), None)
            except Exception as e:
                self.job_done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _err(self, e):
        return t(e.template, **e.kw) if hasattr(e, "template") else str(e)

    def _installed(self, files, err):
        self.busy = False
        if err is not None:
            self.page.error(self._err(err))
        else:
            self.page.info(t("Kuruldu: {files}", files=", ".join(files)) + "\n" +
                           t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))
        self._refresh()

    # --- uygulama ---
    def _store(self, value):
        ov = dict(self.app.config.get("skin_overrides") or {})
        key = SR.norm_uuid(self.player.uuid)
        if value:
            ov[key] = value
        else:
            ov.pop(key, None)
        self.app.config.set("skin_overrides", ov)
        self.page.skins_changed(self.player)

    def _apply(self):
        if self.page.read_only():
            return
        try:
            cmd = SR.set_command(self.player.name, self.src.text(), self.variant.currentData() or "")
        except SR.SkinError as e:
            self.page.error(self._err(e))
            return
        if not self.page.send(cmd):
            return
        self._store(SR.parse(self.src.text())[1])
        self.accept()

    def _clear(self):
        if self.page.read_only():
            return
        if not self.page.send(SR.clear_command(self.player.name)):
            return
        self._store("")
        self.accept()
