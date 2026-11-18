"""Java Yöneticisi: sunucunun Minecraft sürümüne uygun Java'yı seçer ya da Temurin'i indirir (core.javamgr)."""
import os
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QFileDialog, QProgressBar, QTableWidgetItem, QVBoxLayout

from core import javamgr as jm
from core.config import N_
from . import icons
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row, table

SOURCES = {"spypaper": N_("Spypaper indirdi"), "system": N_("Bilgisayarda kurulu"), "PATH": "PATH",
           "JAVA_HOME": "JAVA_HOME", "minecraft": N_("Minecraft Launcher")}


class JavaDialog(QDialog):
    progress = Signal(int, int)
    finished_job = Signal(str, str)        # java yolu, hata

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.cfg = app.config
        self.changed = False
        self._cancel = False
        self.setWindowTitle(t("Java Yöneticisi"))
        self.setMinimumSize(820, 480)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label("Java Yöneticisi", "PageTitle"))
        self.need = label("", "CardTitle", wrap=True)
        v.addWidget(self.need)
        self.current = label("", "Muted", wrap=True)
        v.addWidget(self.current)

        self.table = table(["Sürüm", "Kaynak", "Konum", ""], stretch_col=2)
        self.table.setTextElideMode(Qt.ElideMiddle)          # uzun yolların başı ve sonu görünsün
        self.table.setWordWrap(False)
        self.table.itemDoubleClicked.connect(lambda _it: self.use_selected())
        self.table.itemSelectionChanged.connect(self._sel)
        v.addWidget(self.table, 1)
        v.addWidget(label("Spypaper Java'yı sisteme kurmaz: indirilen Java, Spypaper'ın yanındaki java klasörüne açılır; "
                          "PATH ve diğer programlar etkilenmez. Minecraft Launcher'ın kendi Java'ları da kullanılabilir.",
                          "Muted", wrap=True))
        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.msg = label("", "Muted", wrap=True)
        v.addWidget(self.msg)

        self.btn_dl = button("", "ghost", self.download)
        self.btn_dl.setIcon(icons.icon("circle-arrow-up", None, 16))
        self.btn_cancel = button("İptal", "ghost", self._cancel_dl)
        self.btn_cancel.hide()
        self.btn_browse = button("Gözat…", "ghost", self.browse)
        self.btn_use = button("Bu Java'yı Kullan", "primary", self.use_selected)
        v.addLayout(row(self.btn_dl, self.btn_cancel, self.btn_browse, None, button("Kapat", "ghost", self.accept),
                        self.btn_use, stretch_end=False))

        self.progress.connect(self._on_progress)
        self.finished_job.connect(self._done)
        self.refresh()

    # ------------------------------------------------------------------ durum
    def refresh(self, select=None):
        self.ver = jm.mc_version(self.cfg.server_path, self.cfg.get("jar_name"))
        self.req = jm.required_java(self.ver)
        self.rec = jm.recommended(self.req)
        if self.req:
            self.need.setText(t("Bu sunucu Minecraft {v}: Java {n} ya da daha yenisi gerekir.", v=self.ver, n=self.req))
        else:
            self.need.setText(t("Sunucunun Minecraft sürümü bilinmiyor. Sunucuyu bir kez başlatınca belirlenir; "
                                "en yeni sürümler için Java 25 önerilir."))
        cur = jm.resolve(self.cfg.get("java_path"))
        major, full, _ = jm.info(cur) if cur else (None, "", "")
        if not cur:
            self.current.setText(t("Seçili Java ({path}) bulunamadı.", path=self.cfg.get("java_path") or "java"))
            self.current.setStyleSheet(f"color:{TOKENS['danger']}")
        elif self.req and major is not None and major < self.req:
            self.current.setText(t("Seçili Java {n} ({full}) bu sunucu için çok eski.", n=major, full=full))
            self.current.setStyleSheet(f"color:{TOKENS['danger']}")
        else:
            self.current.setText(t("Seçili: Java {n} ({full}) · {path}", n=major if major is not None else "?",
                                   full=full, path=cur))
            self.current.setStyleSheet("")
        self.btn_dl.setText(t("Java {n} İndir (Temurin)", n=self.rec))

        self.javas = jm.find_javas()
        best = jm.best_for(self.req, self.javas)
        cur_n = os.path.normcase(cur) if cur else ""
        self.table.setRowCount(len(self.javas))
        sel_row = -1
        for r, j in enumerate(self.javas):
            fits = self.req is None or j["major"] >= self.req
            src = t(SOURCES.get(j["source"], j["source"]))
            if j["vendor"] and j["source"] != "minecraft":
                src += f" · {j['vendor']}"
            mark = ""
            if os.path.normcase(j["path"]) == cur_n:
                mark, sel_row = t("Seçili"), r
            elif best and j["path"] == best["path"]:
                mark = t("Önerilen")
            elif not fits:
                mark = t("Çok eski")
            cells = [f"Java {j['major']}  ({j['version']})", src, j["path"], mark]
            for c, val in enumerate(cells):
                it = QTableWidgetItem(val)
                it.setToolTip(val)
                if not fits:
                    it.setForeground(self.palette().placeholderText())
                elif c == 3 and mark:
                    it.setForeground(self._color(mark))
                self.table.setItem(r, c, it)
        if select:
            sel_row = next((i for i, j in enumerate(self.javas)
                            if os.path.normcase(j["path"]) == os.path.normcase(select)), sel_row)
        elif best and (sel_row < 0 or (self.req and self.javas[sel_row]["major"] < self.req)):
            sel_row = self.javas.index(best)                 # seçili Java yetersizse önerilen hazır seçili gelsin
        if sel_row >= 0:
            self.table.selectRow(sel_row)
        if not self.javas:
            self.msg.setText(t("Bu bilgisayarda Java bulunamadı. Java {n} İndir'e bas.", n=self.rec))
        self._sel()

    def _color(self, mark):
        from PySide6.QtGui import QColor
        return QColor(TOKENS["accent"] if mark in (t("Seçili"), t("Önerilen")) else TOKENS["danger"])

    def _selected(self):
        r = self.table.currentRow()
        return self.javas[r] if 0 <= r < len(self.javas) else None

    def _sel(self):
        self.btn_use.setEnabled(self._selected() is not None)

    # ------------------------------------------------------------------ seçme
    def _apply(self, path):
        major = jm.info(path)[0]
        if self.req and major is not None and major < self.req:
            from .widgets import ask
            if not ask(self, t("Java {n} bu sunucu için çok eski (Java {req} gerekir). Yine de seçilsin mi?",
                               n=major, req=self.req), t("Onay")):
                return False
        self.cfg.set("java_path", path)
        self.changed = True
        self.msg.setStyleSheet(f"color:{TOKENS['accent']}")
        self.msg.setText(t("Sunucu artık bu Java ile başlatılacak: {path}", path=path))
        self.refresh(select=path)
        return True

    def use_selected(self):
        j = self._selected()
        if j:
            self._apply(j["path"])

    def browse(self):
        start = os.path.dirname(jm.resolve(self.cfg.get("java_path")) or "") or os.environ.get("ProgramFiles", "")
        p, _ = QFileDialog.getOpenFileName(self, t("java.exe dosyasını seç"), start, f"Java ({jm.EXE})")
        if not p:
            return
        if jm.info(p)[0] is None:
            self.msg.setStyleSheet(f"color:{TOKENS['danger']}")
            self.msg.setText(t("Bu dosya çalışan bir Java değil."))
            return
        self._apply(os.path.normpath(p))

    # ------------------------------------------------------------------ indirme
    def download(self):
        self._cancel = False
        self.btn_dl.setEnabled(False)
        self.btn_cancel.show()
        self.bar.show()
        self.bar.setMaximum(0)
        self.msg.setStyleSheet("")
        self.msg.setText(t("Java {n} indiriliyor (Eclipse Temurin, api.adoptium.net)…", n=self.rec))
        contact = self.cfg.settings.get("update_contact") if hasattr(self.cfg, "settings") else ""
        major = self.rec

        def emit(sig, *a):                       # pencere kapandıysa sinyal gönderilemez
            try:
                sig.emit(*a)
            except RuntimeError:
                pass

        def work():
            try:
                path = jm.download(major, contact, progress=lambda a, b: emit(self.progress, a, b),
                                   cancelled=lambda: self._cancel)
                emit(self.finished_job, path, "")
            except jm.JavaError as e:
                emit(self.finished_job, "", t(e.template, **e.kw))
            except Exception as e:
                emit(self.finished_job, "", str(e))
        threading.Thread(target=work, daemon=True).start()

    def _cancel_dl(self):
        self._cancel = True

    def _on_progress(self, got, total):
        if total:
            self.bar.setMaximum(total)
            self.bar.setValue(got)
            self.bar.setFormat(f"{got / 1048576:.1f} / {total / 1048576:.1f} MB")

    def _done(self, path, err):
        self.bar.hide()
        self.btn_cancel.hide()
        self.btn_dl.setEnabled(True)
        if err:
            self.msg.setStyleSheet(f"color:{TOKENS['danger']}")
            self.msg.setText(err)
            return
        self._apply(path)
        self.msg.setText(t("Java indirildi ve bu sunucu için seçildi: {path}", path=path))

    def reject(self):
        self._cancel = True
        super().reject()

    def accept(self):
        self._cancel = True
        super().accept()
