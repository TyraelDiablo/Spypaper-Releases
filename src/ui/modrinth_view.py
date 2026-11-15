"""Modrinth tarayıcısı (mod / eklenti / kaynak paketi) ve sunucu kaynak paketi ayarı.
Eklentiler/Modlar sayfasının "Modrinth" ve "Kaynak Paketi" sekmeleri."""
import os
import threading
import urllib.request
import webbrowser

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QVBoxLayout, QWidget,
)

from core import N_, modrinth as M
from core.config import detect_version, get_base_dir
from .i18n import t
from .widgets import Card, button, label, row


def fmt_count(n):
    for div, suf in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= div:
            return f"{n / div:.1f}{suf}".replace(".0", "")
    return str(n)


class Runner(QObject):
    """Arka planda iş çalıştırır; sonucu ana thread'e döndürür."""
    done = Signal(str, object, object)          # iş, sonuç, hata
    progress = Signal(int, int)

    def run(self, job, fn):
        def work():
            try:
                self.done.emit(job, fn(), None)
            except Exception as e:
                self.done.emit(job, None, e)
        threading.Thread(target=work, daemon=True).start()


def err_msg(e):
    return t(e.template, **e.kw) if isinstance(e, M.ModrinthError) else str(e)


_ICONS = {}


class IconLoader(QObject):
    ready = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = set()
        self.folder = os.path.join(get_base_dir(), "cache", "modrinth")

    def path(self, pid):
        return os.path.join(self.folder, pid)

    def icon(self, pid):
        if pid in _ICONS:
            return _ICONS[pid]
        p = self.path(pid)
        if os.path.exists(p):
            pm = QPixmap(p)
            _ICONS[pid] = QIcon(pm.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation)) if not pm.isNull() else None
            return _ICONS[pid]
        return None

    def request(self, hits):
        todo = [(h["id"], h["icon"]) for h in hits if h["icon"].startswith(M.CDN) and h["id"] not in self.busy
                and not os.path.exists(self.path(h["id"]))]
        if not todo:
            return
        self.busy.update(p for p, _ in todo)
        os.makedirs(self.folder, exist_ok=True)

        def work():
            for pid, url in todo:
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": M.UA})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = r.read(1_000_000)
                    with open(self.path(pid), "wb") as f:
                        f.write(data)
                    _ICONS.pop(pid, None)
                    self.ready.emit(pid)
                except Exception:
                    pass
        threading.Thread(target=work, daemon=True).start()


class ModrinthBrowser(QWidget):
    """mode: 'content' (mod/eklenti klasörüne kurar) ya da 'resourcepack' (sunucu paketi yapar)."""
    changed = Signal()

    def __init__(self, page, mode="content"):
        super().__init__()
        self.page, self.app, self.mode = page, page.app, mode
        self.hits, self.total, self.sel, self.vers = [], 0, None, []
        self.runner = Runner(self)
        self.runner.done.connect(self._done)
        self.runner.progress.connect(self._progress)
        self.icons = IconLoader(self)
        self.icons.ready.connect(self._icon_ready)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        self.q = QLineEdit()
        self.q.setPlaceholderText(t("Modrinth'te ara…"))
        self.q.returnPressed.connect(lambda: self.search())
        self.ver = QComboBox()
        self.ver.setEditable(True)
        self.ver.setMinimumWidth(110)
        self.loader = QComboBox()
        self.sort = QComboBox()
        for k, n in M.SORTS.items():
            self.sort.addItem(t(n), k)
        self.btn_search = button("Ara", "primary", lambda: self.search())
        v.addLayout(row(self.q, self.ver, self.loader, self.sort, self.btn_search, stretch_end=False))

        body = QHBoxLayout()
        body.setSpacing(14)
        left = Card()
        self.list = QListWidget()
        self.list.setIconSize(QSize(40, 40))
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._select)
        left.add(self.list, 1)
        self.count = label("", "Muted")
        self.btn_more = button("Daha Fazla", "ghost", lambda: self.search(more=True))
        left.add(row(self.count, None, self.btn_more, stretch_end=False))
        body.addWidget(left, 3)

        right = Card()
        right.setMinimumWidth(320)
        self.title = label("", "BigValue", wrap=True, raw=True)
        self.meta = label("", "Muted", wrap=True, raw=True)
        self.desc = label("", None, wrap=True, raw=True)
        right.add(self.title)
        right.add(self.meta)
        right.add(self.desc)
        self.vbox = QComboBox()
        right.add(label("Sürüm", "Muted"))
        right.add(self.vbox)
        self.note = label("", "Muted", wrap=True)
        right.add(self.note)
        self.required = QCheckBox(t("Oyuncular kabul etmek zorunda (reddederse giremez)"))
        self.required.setCursor(Qt.PointingHandCursor)
        self.required.setVisible(mode == "resourcepack")
        right.add(self.required)
        self.btn_install = button("Sunucu Paketi Yap" if mode == "resourcepack" else "Yükle", "primary", self.install)
        self.btn_page = button("Modrinth'te Aç", "ghost", self._open_page)
        right.add(row(self.btn_install, self.btn_page))
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        right.add(self.bar)
        right.body.addStretch(1)
        body.addWidget(right, 2)
        v.addLayout(body, 1)
        self.vbox.currentIndexChanged.connect(self._ver_note)
        self._ctx_ready = False
        self._clear_detail()

    # ------------------------------------------------------------ bağlam
    def prepare(self):
        """Sekme ilk açıldığında sunucunun sürümünü/yazılımını alır ve ilk aramayı yapar."""
        if self._ctx_ready:
            return
        self._ctx_ready = True
        mc, soft = detect_version(self.app.config.server_path)
        if self.mode == "resourcepack":
            self.ptype, loaders = "resourcepack", []
        else:
            self.ptype, loaders = M.context(soft, mc, self.app.plugins.modded)
        self.ver.clear()
        if mc:
            self.ver.addItem(mc, mc)
        self.ver.addItem(t("Tüm sürümler"), "")
        self.loader.clear()
        if self.ptype == "resourcepack":
            self.loader.setVisible(False)
        else:
            self.loader.addItem(" / ".join(loaders), loaders)
            for lo in (M.MOD_LOADERS if self.ptype == "mod" else M.PLUGIN_LOADERS):
                if [lo] != loaders:
                    self.loader.addItem(lo, [lo])
        self.search()

    def _game_version(self):
        txt = self.ver.currentText().strip()
        data = self.ver.currentData()
        if data is not None and self.ver.itemText(self.ver.currentIndex()) == txt:
            return data
        return txt if txt and txt != t("Tüm sürümler") else ""

    # ------------------------------------------------------------ arama
    def search(self, more=False):
        offset = len(self.hits) if more else 0
        args = dict(query=self.q.text(), project_type=self.ptype, game_version=self._game_version(),
                    loaders=self.loader.currentData() or [], sort=self.sort.currentData(), offset=offset)
        self.btn_search.setEnabled(False)
        self.count.setText(t("Aranıyor…"))
        self.runner.run("more" if more else "search", lambda: M.search(**args))

    def _fill(self, hits, append):
        if not append:
            self.list.clear()
            self.hits = []
        for h in hits:
            self.hits.append(h)
            it = QListWidgetItem(f"{h['title']}   ·   {fmt_count(h['downloads'])} ↓\n{h['description'][:140]}")
            it.setToolTip(f"{h['title']} — {h['author']}\n{h['description']}")
            ic = self.icons.icon(h["id"])
            if ic:
                it.setIcon(ic)
            self.list.addItem(it)
        self.icons.request(hits)
        self.count.setText(t("{n} / {total} sonuç", n=len(self.hits), total=fmt_count(self.total)))
        self.btn_more.setVisible(len(self.hits) < self.total)
        if not append and self.hits:
            self.list.setCurrentRow(0)
        elif not self.hits:
            self._clear_detail()
            self.count.setText(t("Sonuç yok. Sürüm filtresini 'Tüm sürümler' yapmayı dene."))

    def _icon_ready(self, pid):
        for i, h in enumerate(self.hits):
            if h["id"] == pid:
                ic = self.icons.icon(pid)
                if ic and self.list.item(i):
                    self.list.item(i).setIcon(ic)

    # ------------------------------------------------------------ ayrıntı
    def _clear_detail(self):
        self.sel = None
        self.title.setText(t("Bir sonuç seç"))
        self.meta.setText("")
        self.desc.setText("")
        self.vbox.clear()
        self.note.setText("")
        self.btn_install.setEnabled(False)
        self.btn_page.setEnabled(False)

    def _select(self, i):
        if not 0 <= i < len(self.hits):
            return
        h = self.sel = self.hits[i]
        import html as H
        self.title.setText(H.escape(h["title"]))
        side = {"required": t("gerekli"), "optional": t("isteğe bağlı"), "unsupported": t("desteklenmiyor")}
        bits = [t("{author} tarafından", author=H.escape(h["author"])), t("{n} indirme", n=fmt_count(h["downloads"]))]
        if h["type"] == "mod":
            bits.append(t("Sunucu: {s} · İstemci: {c}", s=side.get(h["server_side"], h["server_side"]),
                          c=side.get(h["client_side"], h["client_side"])))
        if h.get("license"):
            bits.append(t("Lisans: {l}", l=H.escape(h["license"])))
        self.meta.setText(" · ".join(bits))
        self.desc.setText(H.escape(h["description"]))
        self.vbox.clear()
        self.vbox.addItem(t("Sürümler yükleniyor…"))
        self.btn_install.setEnabled(False)
        self.btn_page.setEnabled(True)
        loaders = (self.loader.currentData() or []) if self.ptype != "resourcepack" else []
        gv = self._game_version()
        pid = h["id"]
        self.runner.run("versions:" + pid, lambda: M.versions(pid, loaders, gv))

    def _ver_note(self, _=None):
        i = self.vbox.currentIndex()
        if not (0 <= i < len(self.vers)):
            return
        v = self.vers[i]
        notes = [t("Dosya: {name} ({size} MB)", name=v["file"]["name"], size=f"{v['file']['size'] / 1048576:.1f}")]
        if v["deps"]:
            notes.append(t("Gerekli {n} bağımlılık da kurulacak.", n=len(v["deps"])))
        if self.mode == "content" and M.safe_filename(v["file"]["name"]).lower() in M.installed_names(self.app.plugins.folder):
            notes.append(t("Bu dosya zaten yüklü."))
        if self.sel and self.sel["type"] == "mod" and self.sel["client_side"] == "required":
            notes.append(t("Oyuncuların da bu modu kurması gerekir."))
        if self.mode == "resourcepack":
            notes.append(t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))
            if v["file"]["size"] > 250 * 1048576:
                notes.append(t("Kaynak paketi çok büyük (en fazla 250 MB)."))
        self.note.setText("\n".join(notes))

    def _open_page(self):
        if self.sel:
            kind = {"plugin": "plugin", "mod": "mod", "resourcepack": "resourcepack"}.get(self.sel["type"], "project")
            webbrowser.open(f"https://modrinth.com/{kind}/{self.sel['slug'] or self.sel['id']}")

    # ------------------------------------------------------------ kurulum
    def install(self):
        i = self.vbox.currentIndex()
        if not (self.sel and 0 <= i < len(self.vers)):
            return
        v = self.vers[i]
        if self.mode == "resourcepack":
            try:
                M.set_resource_pack(self.app.properties, v["file"]["url"], v["file"]["sha1"], self.required.isChecked())
            except Exception as e:
                self.page.error(err_msg(e))
                return
            self.page.info(t("'{name}' sunucu kaynak paketi yapıldı. Sunucu yeniden başlatılınca oyunculara sunulur.",
                             name=self.sel["title"]))
            self.changed.emit()
            return
        if self.page.read_only():
            return
        folder = self.app.plugins.folder
        loaders = self.loader.currentData() or []
        gv = self._game_version()
        self.btn_install.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        prog = self.runner.progress.emit

        def work():
            done = [M.download(v["file"], folder, prog)]
            have = M.installed_names(folder)
            for d in v["deps"]:
                pid = d.get("project_id")
                if not pid:
                    continue
                dv = M.versions(pid, loaders, gv)
                if dv and M.safe_filename(dv[0]["file"]["name"]).lower() not in have:
                    done.append(M.download(dv[0]["file"], folder, prog))
            return done
        self.runner.run("install", work)

    def _progress(self, got, total):
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(got)

    # ------------------------------------------------------------ sonuçlar
    def _done(self, job, res, err):
        if job in ("search", "more"):
            self.btn_search.setEnabled(True)
            if err:
                self.count.setText(err_msg(err))
                return
            hits, self.total = res
            self._fill(hits, job == "more")
        elif job.startswith("versions:"):
            if not self.sel or job != "versions:" + self.sel["id"]:
                return
            self.vbox.clear()
            if err:
                self.vbox.addItem(err_msg(err))
                return
            self.vers = res
            for v in res:
                kind = {"beta": " (beta)", "alpha": " (alpha)"}.get(v["type"], "")
                self.vbox.addItem(f"{v['number']}{kind}  ·  {', '.join(v['game_versions'][-3:])}  ·  {v['date']}")
            if not res:
                self.vbox.addItem(t("Bu sürüm ve yükleyici için dosya yok"))
            self.btn_install.setEnabled(bool(res))
            self._ver_note()
        elif job == "install":
            self.bar.setVisible(False)
            self.btn_install.setEnabled(True)
            if err:
                self.page.error(err_msg(err))
                return
            names = ", ".join(os.path.basename(p) for p in res)
            self.page.info(t("Yüklendi: {files}", files=names) + "\n" +
                           t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))
            self._ver_note()
            self.changed.emit()


class ResourcePackView(QWidget):
    """Şu anki sunucu kaynak paketi + Modrinth'ten seç + elle adres gir."""

    def __init__(self, page):
        super().__init__()
        self.page, self.app = page, page.app
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        cur = Card("Sunucu Kaynak Paketi", "Oyuncular girerken bu paketi indirmeleri istenir")
        self.cur_lbl = label("", "Muted", wrap=True, raw=True)
        cur.add(self.cur_lbl)
        self.url = QLineEdit()
        self.url.setPlaceholderText(t("ya da doğrudan indirme adresi (https://…/paket.zip)"))
        self.sha = QLineEdit()
        self.sha.setPlaceholderText("SHA-1")
        self.sha.setMaximumWidth(330)
        self.req = QCheckBox(t("Zorunlu"))
        self.req.setCursor(Qt.PointingHandCursor)
        cur.add(row(self.url, self.sha, button("SHA-1 Hesapla", "ghost", self.calc), stretch_end=False))
        cur.add(row(self.req, None, button("Kaldır", "danger", self.clear), button("Kaydet", "primary", self.save),
                    stretch_end=False))
        self.bar = QProgressBar()
        self.bar.setVisible(False)
        cur.add(self.bar)
        v.addWidget(cur)
        self.browser = ModrinthBrowser(page, "resourcepack")
        self.browser.changed.connect(self.refresh)
        v.addWidget(self.browser, 1)
        self.runner = Runner(self)
        self.runner.done.connect(self._done)
        self.runner.progress.connect(lambda a, b: (self.bar.setRange(0, b or 0), self.bar.setValue(a)))

    def refresh(self):
        import html as H
        c = M.current_resource_pack(self.app.properties)
        if c.get("url"):
            self.cur_lbl.setText(t("Şu an: {url}", url=H.escape(c["url"])) + "<br>" +
                                 ("SHA-1: " + H.escape(c["sha1"]) if c["sha1"] else t("SHA-1 yok (oyuncular her girişte yeniden indirebilir)")) +
                                 ("  ·  " + t("Zorunlu") if c["required"] else ""))
        else:
            self.cur_lbl.setText(t("Sunucuda kaynak paketi yok."))
        self.req.setChecked(bool(c.get("required")))

    def prepare(self):
        self.refresh()
        self.browser.prepare()

    def save(self):
        u = self.url.text().strip()
        if not u:
            return
        try:
            M.set_resource_pack(self.app.properties, u, self.sha.text().strip(), self.req.isChecked())
        except Exception as e:
            self.page.error(err_msg(e))
            return
        self.page.info(t("Kaydedildi. Değişiklik sunucu yeniden başlatılınca geçerli olur."))
        self.refresh()

    def clear(self):
        if self.page.confirm(t("Sunucunun kaynak paketi kaldırılsın mı?")):
            M.clear_resource_pack(self.app.properties)
            self.refresh()

    def calc(self):
        u = self.url.text().strip()
        if not u:
            return
        self.bar.setVisible(True)
        self.bar.setRange(0, 0)
        self.runner.run("sha", lambda: M.sha1_of_url(u, self.runner.progress.emit))

    def _done(self, job, res, err):
        self.bar.setVisible(False)
        if err:
            self.page.error(err_msg(err))
        else:
            self.sha.setText(res)


N_("Modrinth")
N_("Kaynak Paketi")
N_("Yüklü")
