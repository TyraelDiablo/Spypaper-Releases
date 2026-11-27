"""Bedrock sunucuları için Add-on'lar sayfası: yüklü paketler (dünyada aç/kapat, sıra, sil) ve CurseForge araması."""
import os
import tempfile
import threading

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QCheckBox, QFileDialog, QInputDialog, QLineEdit, QMessageBox, QStackedWidget

from core import N_, bedrock_packs as BP, curseforge as CF
from ..i18n import t
from ..widgets import Card, Page, button, color, err_text, fill_table, label, row, segmented, table

KIND_NAMES = {"behavior": N_("Davranış"), "resource": N_("Kaynak")}


def _err(e):
    if isinstance(e, (BP.PackError, CF.CFError)):
        return t(e.template, **e.kw)
    return err_text(e)


class BedrockAddonsPage(Page):
    title = N_("Add-on'lar")
    done = Signal(object, object, str)      # (sonuç, hata, iş)

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.done.connect(self._done)
        self.tabs = segmented([N_("Yüklü"), N_("CurseForge")], self._tab)
        self.root.addWidget(self.tabs, 0, Qt.AlignLeft)
        self.stack = QStackedWidget()
        self.root.addWidget(self.stack, 1)

        # --- yüklü
        c = self.card = Card("Yüklü Paketler", "Davranış paketleri oynanışı, kaynak paketleri doku ve sesleri değiştirir. "
                                               "Değişiklikler sunucu yeniden başlayınca geçerli olur.")
        c.header_actions.addWidget(button("Paket Kur (.mcpack / .mcaddon)", "primary", self.add_file))
        c.header_actions.addWidget(button("Yenile", "ghost", self.on_show))
        self.tbl = table(["Paket", "Tür", "Sürüm", "Dünyada", "Not"], stretch_col=0)
        self.tbl.itemSelectionChanged.connect(self._sel)
        c.add(self.tbl, 1)
        self.b_toggle = button("Dünyada Aç / Kapat", "primary", self.toggle)
        self.b_up = button("Yukarı", "ghost", lambda: self.move(-1))
        self.b_down = button("Aşağı", "ghost", lambda: self.move(1))
        self.b_del = button("Sil", "danger", self.delete)
        c.add(row(self.b_toggle, self.b_up, self.b_down, self.b_del, None, stretch_end=False))
        self.detail = label("", "Muted", wrap=True)
        c.add(self.detail)
        self.tex_req = QCheckBox(t("Oyuncular kaynak paketlerini indirmek zorunda olsun (texturepack-required)"))
        self.tex_req.toggled.connect(lambda on: BP.set_texture_required(self.path, on))
        c.add(self.tex_req)
        c.add(label("Listede üstteki paket önceliklidir. Marketplace paketleri şifrelidir ve Bedrock sunucusunda kullanılamaz.",
                    "Muted", wrap=True))
        self.stack.addWidget(c)

        # --- CurseForge
        cf = self.cf = Card("CurseForge", "Ücretsiz Bedrock add-on'larını ara ve tek tıkla kur.")
        self.key_lbl = label("", "Muted", wrap=True)
        cf.add(row(self.key_lbl, None, button("API Anahtarı…", "ghost", self.set_key), stretch_end=False))
        self.q = QLineEdit()
        self.q.setPlaceholderText(t("Ara: ör. furniture, guns, more ores"))
        self.q.returnPressed.connect(self.search)
        cf.add(row(self.q, button("Ara", "primary", self.search), stretch_end=False))
        self.res = table(["Add-on", "İndirme", "Sürümler", "Yazar"], stretch_col=0)
        self.res.itemSelectionChanged.connect(self._rsel)
        cf.add(self.res, 1)
        self.rdetail = label("", "Muted", wrap=True)
        cf.add(self.rdetail)
        self.b_inst = button("Kur ve Dünyada Aç", "primary", self.install_cf)
        self.b_page = button("Sayfasını Aç", "ghost", self.open_page)
        self.cf_state = label("", "Muted", wrap=True)
        cf.add(row(self.b_inst, self.b_page, None, self.cf_state, stretch_end=False))
        self.stack.addWidget(cf)
        self.packs, self.results, self.busy = [], [], False
        self._sel()
        self._rsel()

    @property
    def path(self):
        return self.app.config.server_path

    def _settings(self):
        return getattr(self.app.ingame_ai, "settings", None)

    def _tab(self, i):
        self.stack.setCurrentIndex(i)
        if i == 1:
            self._key_state()

    # ------------------------------------------------------------------ yüklü
    def on_show(self):
        self.packs = BP.list_packs(self.path)
        on = {k: [d["pack_id"] for d in BP.enabled(self.path, k)] for k in BP.KINDS}
        self.packs.sort(key=lambda p: (p["kind"], on[p["kind"]].index(p["uuid"]) if p["uuid"] in on[p["kind"]] else 999,
                                       p["name"].lower()))
        rows = []
        for p in self.packs:
            notes = []
            if p["encrypted"]:
                notes.append(t("Marketplace (şifreli), kullanılamaz"))
            elif p["broken"]:
                notes.append(t("manifest.json okunamadı"))
            if BP.missing_deps(self.packs, p):
                notes.append(t("Gerekli paket eksik"))
            if p["beta"]:
                notes.append(t("Deneysel özellik ister"))
            if p["dev"]:
                notes.append(t("Geliştirme klasörü"))
            enabled = p["uuid"] in on[p["kind"]]
            rows.append((p["name"], t(KIND_NAMES[p["kind"]]), BP.ver_text(p["version"]),
                         (t("Açık") + f" #{on[p['kind']].index(p['uuid']) + 1}") if enabled else t("Kapalı"),
                         ", ".join(notes)))
        fill_table(self.tbl, rows, align_center=(1, 2, 3))
        for r, p in enumerate(self.packs):
            it = self.tbl.item(r, 3)
            it.setForeground(QColor(color("accent") if p["uuid"] in on[p["kind"]] else color("text_muted")))
        self.tex_req.blockSignals(True)
        self.tex_req.setChecked(BP.texture_required(self.path))
        self.tex_req.blockSignals(False)
        self._sel()

    def _cur(self):
        r = self.tbl.currentRow()
        return self.packs[r] if 0 <= r < len(self.packs) and self.tbl.selectedItems() else None

    def _sel(self):
        p = self._cur()
        usable = bool(p and p["uuid"] and not p["encrypted"])
        for b in (self.b_toggle, self.b_up, self.b_down):
            b.setEnabled(usable)
        self.b_del.setEnabled(bool(p))
        if not p:
            self.detail.setText("")
            return
        lines = [p["description"]] if p["description"] else []
        if p["min_engine"]:
            lines.append(t("En düşük oyun sürümü: {v}", v=p["min_engine"]))
        miss = BP.missing_deps(self.packs, p)
        if miss:
            lines.append(t("Eksik gerekli paketler: {list}", list=", ".join(miss)))
        if p["beta"]:
            lines.append(t("Bu paket Beta API kullanıyor; dünyada deneysel özellikler (Beta APIs) açık olmalı."))
        self.detail.setText("\n".join(lines))

    def toggle(self):
        p = self._cur()
        if not p:
            return
        on = p["uuid"] in [d["pack_id"] for d in BP.enabled(self.path, p["kind"])]
        BP.set_enabled(self.path, p, not on)
        self._after_change()

    def move(self, d):
        p = self._cur()
        if p and BP.move(self.path, p, d):
            self._after_change()

    def delete(self):
        p = self._cur()
        if not p:
            return
        if not self.confirm(t("'{name}' paketi sunucudan silinsin mi? Bu geri alınamaz.", name=p["name"])):
            return
        try:
            BP.remove(self.path, p)
        except Exception as e:
            self.error(_err(e))
        self._after_change()

    def _after_change(self):
        sel = self._cur()
        self.on_show()
        if sel:
            for r, p in enumerate(self.packs):
                if p["folder"] == sel["folder"]:
                    self.tbl.selectRow(r)
        if self.app.server.is_running:
            self.info(t("Değişiklik sunucu yeniden başlayınca geçerli olur."))

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, t("Paket seç"), "", "Bedrock (*.mcpack *.mcaddon *.zip)")
        if files:
            self._bg("install", lambda: [x for f in files for x in BP.install_file(self.path, f)])

    # ------------------------------------------------------------------ CurseForge
    def _key_state(self):
        st = self._settings()
        has = bool(st and CF.get_key(st))
        self.key_lbl.setText(t("API anahtarı ayarlı.") if has else
                             t("CurseForge araması için ücretsiz bir API anahtarı gerekir: console.curseforge.com → API keys."))
        return has

    def set_key(self):
        st = self._settings()
        if st is None:
            return
        key, ok = QInputDialog.getText(self, t("CurseForge API anahtarı"),
                                       t("console.curseforge.com'dan aldığın anahtarı yapıştır (boş bırakırsan silinir):"),
                                       QLineEdit.Password)
        if ok:
            CF.set_key(st, key)
            self._key_state()

    def search(self):
        st = self._settings()
        if not self._key_state() or self.busy:
            return
        key, text = CF.get_key(st), self.q.text().strip()
        self.cf_state.setText(t("Aranıyor…"))
        self._bg("search", lambda: CF.search(key, text))

    def _rsel(self):
        r = self.res.currentRow()
        m = self.results[r] if 0 <= r < len(self.results) and self.res.selectedItems() else None
        self.b_inst.setEnabled(bool(m and m["file"]) and not self.busy)
        self.b_page.setEnabled(bool(m and m["url"]))
        self.rdetail.setText((m["summary"] + ("\n" + t("Dosya: {f}", f=m["file"]["fileName"]) if m["file"] else
                                              "\n" + t("Kurulabilecek dosya yok."))) if m else "")
        return m

    def open_page(self):
        m = self._rsel()
        if m and m["url"]:
            QDesktopServices.openUrl(QUrl(m["url"]))

    def install_cf(self):
        m = self._rsel()
        st = self._settings()
        if not m or not st:
            return
        key, path = CF.get_key(st), self.path

        def job():
            tmp = tempfile.mkdtemp(prefix="spypaper-cf-")
            f = CF.download(key, m, tmp)
            if f is None:
                return None
            try:
                return BP.install_file(path, f)
            finally:
                try:
                    os.remove(f)
                    os.rmdir(tmp)
                except OSError:
                    pass
        self.cf_state.setText(t("İndiriliyor…"))
        self._bg("cf_install", job, m)

    # ------------------------------------------------------------------ arka plan
    def _bg(self, job, fn, ctx=None):
        self.busy = True
        self._ctx = ctx

        def work():
            try:
                self.done.emit(fn(), None, job)
            except Exception as e:
                self.done.emit(None, e, job)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, res, err, job):
        self.busy = False
        if job == "search":
            if err:
                self.cf_state.setText(_err(err))
                return
            self.results = res
            fill_table(self.res, [(m["name"], f"{m['downloads']:,}".replace(",", "."), ", ".join(m["versions"][:3]),
                                   m["authors"]) for m in res], align_center=(1, 2))
            self.cf_state.setText(t("{n} sonuç", n=len(res)))
            self._rsel()
            return
        if err:
            self.cf_state.setText("")
            self.error(_err(err))
            return
        if job == "cf_install" and res is None:
            self.cf_state.setText("")
            if self.confirm(t("Yazar bu dosyanın başka uygulamalardan indirilmesine izin "
                                                          "vermiyor. Sayfasını açıp elle indirmek ister misin? İndirdikten "
                                                          "sonra 'Paket Kur' ile kurabilirsin."), "CurseForge"):
                self.open_page()
            return
        names = ", ".join(p["name"] for p in res)
        self.cf_state.setText("")
        self.on_show()
        self.info(t("Kuruldu ve dünyada açıldı: {list}. Sunucu yeniden başlayınca geçerli olur.", list=names))
