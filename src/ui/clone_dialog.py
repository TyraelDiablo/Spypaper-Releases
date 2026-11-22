"""Sunucu kartı → Kopyasını oluştur."""
import os
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QFileDialog, QFormLayout, QLineEdit, QProgressBar, QVBoxLayout

from core import clone as CL
from core.danger import level_name
from core.files import ServerProperties
from .i18n import t
from .widgets import button, label, row


class CloneDialog(QDialog):
    done_sig = Signal(object, object)
    prog_sig = Signal(int, int)

    def __init__(self, settings, prof, parent=None):
        super().__init__(parent)
        self.settings, self.prof = settings, prof
        self.profile = None
        self.setWindowTitle(t("Kopyasını Oluştur"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        v.addWidget(label(t("Kopyasını Oluştur: {name}", name=prof.name), "PageTitle", raw=True))
        v.addWidget(label("Sunucunun klasörü kopyalanır ve listeye yeni bir sunucu olarak eklenir. Loglar ve yedekler "
                          "kopyalanmaz; yeni sunucunun portu otomatik değiştirilir.", "Muted", wrap=True))
        f = QFormLayout()
        f.setSpacing(8)
        self.name = QLineEdit(t("{name} (kopya)", name=prof.name))
        base = prof.server_path.rstrip("/\\")
        dest = base + "-kopya"
        n = 2
        while os.path.exists(dest):
            dest = f"{base}-kopya{n}"
            n += 1
        self.dest = QLineEdit(dest)
        f.addRow(t("Ad"), self.name)
        f.addRow(t("Klasör"), row(self.dest, button("Gözat", "ghost", self._browse), stretch_end=False))
        v.addLayout(f)
        try:
            self.level = level_name(ServerProperties(prof.server_path))
        except Exception:
            self.level = "world"
        wsize = sum(CL.size_of(os.path.join(prof.server_path, d)) for d in CL.world_dirs(self.level)
                    if os.path.isdir(os.path.join(prof.server_path, d)))
        self.world = QCheckBox(t("Dünyayı da kopyala ({size})", size=f"{wsize / 1048576:.0f} MB"))
        self.world.setChecked(True)
        v.addWidget(self.world)
        v.addWidget(label("İşareti kaldırırsan kopya sunucu ilk açılışta yeni bir dünya oluşturur (eklentiler ve "
                          "ayarlar aynı kalır; eklenti test etmek için kullanışlı).", "Muted", wrap=True))
        self.bar = QProgressBar()
        self.bar.hide()
        v.addWidget(self.bar)
        self.status = label("", "Muted", wrap=True, raw=True)
        v.addWidget(self.status)
        self.go = button("Kopyala", "primary", self._start)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), self.go, stretch_end=False))
        self.done_sig.connect(self._done)
        self.prog_sig.connect(lambda a, b: (self.bar.setMaximum(b), self.bar.setValue(a)))   # KB

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, t("Kopyanın konacağı klasörün üst klasörünü seç"),
                                             os.path.dirname(self.dest.text()))
        if d:
            self.dest.setText(os.path.join(d, os.path.basename(self.dest.text())))

    def _start(self):
        dest, name = self.dest.text().strip(), self.name.text().strip()
        if not dest or not name:
            self.status.setText(t("Ad ve klasör boş olamaz."))
            return
        others = [p.server_path for p in self.settings.servers() if p.id != self.prof.id]
        src, level, world = self.prof.server_path, self.level, self.world.isChecked()
        self.go.setEnabled(False)
        self.bar.show()
        self.status.setText(t("Kopyalanıyor…"))

        def work():
            try:
                ports = CL.clone(src, dest, level, world, others, lambda a, b: self.prog_sig.emit(a // 1024, max(1, b // 1024)))
                self.done_sig.emit(ports, None)
            except Exception as e:
                self.done_sig.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _done(self, ports, err):
        if err is not None:
            self.go.setEnabled(True)
            self.bar.hide()
            self.status.setText(t(err.template, **err.kw) if hasattr(err, "template") else str(err))
            return
        self.profile = self.settings.add_server(self.dest.text().strip(), self.name.text().strip(),
                                                **CL.profile_copy(self.prof.data))
        self.ports = ports
        self.accept()
