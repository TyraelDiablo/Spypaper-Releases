"""Sunucu Ayarları → Dünya Sınırı kartı. Çekirdek: core/worldborder.py."""
from PySide6.QtWidgets import QComboBox, QGridLayout, QSpinBox, QStackedWidget, QWidget

from core import N_, worldborder as WB

from .i18n import t
from .widgets import Card, button, label, row


def _coord():
    s = QSpinBox()
    s.setRange(-WB.MAX_COORD, WB.MAX_COORD)
    s.setSingleStep(16)
    return s


class BorderCard(Card):
    def __init__(self, page):
        super().__init__("Dünya Sınırı", "Köşe koordinatlarını (X ve Z) gir; sınır bu alanı kapsayan kare olarak çizilir.")
        self.page = page
        self.mode = QComboBox()
        self.mode.addItem(t("İki köşe"), "corners")
        self.mode.addItem(t("Merkez ve yarıçap"), "center")
        self.dim = QComboBox()
        for k, v in WB.DIMENSIONS.items():
            self.dim.addItem(t(v), k)
        self.secs = QSpinBox()
        self.secs.setRange(0, 86400)
        self.secs.setSpecialValueText(t("Hemen"))
        self.secs.setSuffix(" " + t("sn"))
        top = QGridLayout()
        top.setHorizontalSpacing(10)
        top.addWidget(label("Biçim", "Muted"), 0, 0)
        top.addWidget(self.mode, 0, 1)
        top.addWidget(label("Dünya", "Muted"), 0, 2)
        top.addWidget(self.dim, 0, 3)
        top.addWidget(label("Geçiş süresi", "Muted"), 0, 4)
        top.addWidget(self.secs, 0, 5)
        self.add(top)

        self.x1, self.z1, self.x2, self.z2 = _coord(), _coord(), _coord(), _coord()
        self.cx, self.cz = _coord(), _coord()
        self.radius = QSpinBox()
        self.radius.setRange(1, WB.MAX_SIZE // 2)
        self.radius.setSingleStep(16)
        self.stack = QStackedWidget()
        from . import motion
        motion.auto_fade(self.stack, dy=0)
        a = QWidget()
        ga = QGridLayout(a)
        ga.setContentsMargins(0, 0, 0, 0)
        for r, (name, x, z) in enumerate(((t("1. köşe"), self.x1, self.z1), (t("2. köşe"), self.x2, self.z2))):
            ga.addWidget(label(name, raw=True), r, 0)
            ga.addWidget(label("X", raw=True), r, 1)
            ga.addWidget(x, r, 2)
            ga.addWidget(label("Z", raw=True), r, 3)
            ga.addWidget(z, r, 4)
        ga.setColumnStretch(2, 1)
        ga.setColumnStretch(4, 1)
        b = QWidget()
        gb = QGridLayout(b)
        gb.setContentsMargins(0, 0, 0, 0)
        gb.addWidget(label(t("Merkez"), raw=True), 0, 0)
        gb.addWidget(label("X", raw=True), 0, 1)
        gb.addWidget(self.cx, 0, 2)
        gb.addWidget(label("Z", raw=True), 0, 3)
        gb.addWidget(self.cz, 0, 4)
        gb.addWidget(label(t("Yarıçap"), raw=True), 1, 0)
        gb.addWidget(self.radius, 1, 2)
        gb.setColumnStretch(2, 1)
        gb.setColumnStretch(4, 1)
        self.stack.addWidget(a)
        self.stack.addWidget(b)
        self.add(self.stack)
        self.preview = label("", "Muted", wrap=True)
        self.saved_lbl = label("", "Muted", wrap=True)
        self.add(self.preview)
        self.add(row(button("Sınırı Uygula", "primary", self.apply), button("Sınırı Kaldır", "ghost", self.remove), None))
        self.add(self.saved_lbl)

        self.mode.currentIndexChanged.connect(lambda i: (self.stack.setCurrentIndex(i), self.update_preview()))
        for w in (self.x1, self.z1, self.x2, self.z2, self.cx, self.cz, self.radius):
            w.valueChanged.connect(self.update_preview)

    # ---------------------------------------------------------------- durum
    def load(self):
        c = self.page.app.config.get("world_border") or {}
        for w, k, d in ((self.x1, "x1", -500), (self.z1, "z1", -500), (self.x2, "x2", 500), (self.z2, "z2", 500),
                        (self.cx, "cx", 0), (self.cz, "cz", 0), (self.radius, "radius", 500), (self.secs, "seconds", 0)):
            w.blockSignals(True)
            w.setValue(int(c.get(k, d)))
            w.blockSignals(False)
        self.mode.setCurrentIndex(max(0, self.mode.findData(c.get("mode", "corners"))))
        self.dim.setCurrentIndex(max(0, self.dim.findData(c.get("dimension", "minecraft:overworld"))))
        self.update_preview()
        app = self.page.app
        cur = WB.saved(app.config.server_path, app.properties.load().get("level-name") or "world")
        if cur is None:
            self.saved_lbl.setText(t("Kayıtlı sınır okunamadı (dünya henüz oluşmadı ya da bu sürümde farklı)."))
        elif cur[2] >= WB.MAX_SIZE:
            self.saved_lbl.setText(t("Şu an: sınır yok."))
        else:
            x0, z0, x1, z1 = WB.edges(*cur)
            self.saved_lbl.setText(t("Son kaydedilen sınır (Overworld): merkez {cx}, {cz} · {size} blok · X {x0}…{x1}, Z {z0}…{z1}",
                                     cx=WB.num(cur[0]), cz=WB.num(cur[1]), size=WB.num(cur[2]),
                                     x0=WB.num(x0), x1=WB.num(x1), z0=WB.num(z0), z1=WB.num(z1)))

    def values(self):
        if self.mode.currentData() == "corners":
            cx, cz, size, square = WB.from_corners(self.x1.value(), self.z1.value(), self.x2.value(), self.z2.value())
        else:
            (cx, cz, size), square = WB.from_center(self.cx.value(), self.cz.value(), self.radius.value()), True
        return cx, cz, size, square

    def update_preview(self):
        cx, cz, size, square = self.values()
        if size < 1:
            self.preview.setText(t("Köşeler aynı olamaz."))
            return
        x0, z0, x1, z1 = WB.edges(cx, cz, size)
        text = t("Merkez {cx}, {cz} · {size}×{size} blok · X {x0}…{x1}, Z {z0}…{z1}",
                 cx=WB.num(cx), cz=WB.num(cz), size=WB.num(size), x0=WB.num(x0), x1=WB.num(x1), z0=WB.num(z0), z1=WB.num(z1))
        if not square:
            text += "\n" + t("Sınır her zaman karedir: alanı kapsamak için uzun kenar kullanıldı.")
        self.preview.setText(text)

    def _save(self):
        self.page.app.config.set("world_border", {
            "mode": self.mode.currentData(), "dimension": self.dim.currentData(), "seconds": self.secs.value(),
            "x1": self.x1.value(), "z1": self.z1.value(), "x2": self.x2.value(), "z2": self.z2.value(),
            "cx": self.cx.value(), "cz": self.cz.value(), "radius": self.radius.value()})

    def _running(self):
        if not self.page.app.server.is_running:
            self.page.warn("Dünya sınırı sunucu çalışırken uygulanır. Önce sunucuyu başlat.")
            return False
        return True

    # ---------------------------------------------------------------- işlemler
    def apply(self):
        self._save()
        cx, cz, size, _ = self.values()
        try:
            cmds = WB.commands(cx, cz, size, self.dim.currentData(), self.secs.value())
        except WB.BorderError as e:
            self.page.warn(t(e.template, **e.kw))
            return
        if not self._running():
            return
        for c in cmds:
            if not self.page.send(c):
                return
        self.page.info(t("Sınır uygulandı: {size}×{size} blok, merkez {cx}, {cz}.",
                         size=WB.num(size), cx=WB.num(cx), cz=WB.num(cz)))

    def remove(self):
        if not self._running():
            return
        for c in WB.remove_commands(self.dim.currentData()):
            if not self.page.send(c):
                return
        self.page.info("Sınır kaldırıldı.")


N_("Dünya Sınırı")
N_("Köşe koordinatlarını (X ve Z) gir; sınır bu alanı kapsayan kare olarak çizilir.")
