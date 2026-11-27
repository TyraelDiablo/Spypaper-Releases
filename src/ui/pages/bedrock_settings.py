"""Bedrock sunucuları için Sunucu Ayarları: server.properties, dosyadaki açıklamalardan üretilen formla."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QLineEdit, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from core import N_, bedrock_props as BP
from ..i18n import t
from ..widgets import Card, Page, button, label, row

CHOICE_NAMES = {
    "survival": N_("Hayatta Kalma"), "creative": N_("Yaratıcı"), "adventure": N_("Macera"),
    "peaceful": N_("Barışçıl"), "easy": N_("Kolay"), "normal": N_("Normal"), "hard": N_("Zor"),
    "visitor": N_("Ziyaretçi"), "member": N_("Üye"), "operator": N_("Operatör"),
    "None": N_("Serbest"), "Dropped": N_("Mesajlar görünmez"), "Disabled": N_("Kapalı"),
    "disabled": N_("Kapalı"), "observe": N_("Yalnızca izle"), "enforce": N_("Uygula"),
    "error": N_("Hata"), "warning": N_("Uyarı"), "info": N_("Bilgi"), "verbose": N_("Ayrıntılı"),
}
# Sunucu açıkken komutla hemen uygulanabilenler
LIVE = {"difficulty": "difficulty {v}", "max-players": "setmaxplayers {v}", "allow-list": "allowlist {onoff}"}


class BedrockSettingsPage(Page):
    title = N_("Sunucu Ayarları")

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        bar = Card("server.properties", "Bedrock sunucusunun ayarları. Çoğu, sunucu yeniden başlayınca geçerli olur; "
                                        "zorluk, en fazla oyuncu ve izin listesi açıkken de hemen uygulanır.")
        self.state = label("", "Muted", wrap=True)
        bar.add(row(self.state, None, button("Yeniden Oku", "ghost", self.on_show),
                    button("Kaydet", "primary", self.save), stretch_end=False))
        self.root.addWidget(bar)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.root.addWidget(self.scroll, 1)
        self.widgets, self.entries = {}, []

    @property
    def path(self):
        return self.app.config.server_path

    def on_show(self):
        self.entries = BP.load(self.path)
        inner = QWidget()
        col = QVBoxLayout(inner)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(14)
        self.widgets = {}
        by_group = {}
        for e in self.entries:
            by_group.setdefault(BP.group_of(e["key"]), []).append(e)
        groups = [(g, n) for g, n, _ in BP.GROUPS] + [("advanced", N_("Gelişmiş"))]
        for gid, gname in groups:
            items = by_group.get(gid)
            if not items:
                continue
            if gid != "advanced":
                order = next(k for g, _, k in BP.GROUPS if g == gid)
                items.sort(key=lambda e: order.index(e["key"]) if e["key"] in order else 99)
            c = Card(gname, "Bu ayarların açıklaması Mojang'ın dosyasından alınır." if gid == "advanced" else "")
            grid = QGridLayout()
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            grid.setColumnStretch(2, 1)
            for r, e in enumerate(items):
                name, desc = BP.KNOWN.get(e["key"], (None, None))
                lab = label(t(name) if name else e["key"])
                lab.setToolTip(e["key"])
                w = self._widget(e)
                self.widgets[e["key"]] = (e, w)
                d = label(t(desc) if desc else e["comment"], "Muted", wrap=True)
                d.setToolTip(e["allowed"])
                grid.addWidget(lab, r, 0, Qt.AlignTop)
                grid.addWidget(w, r, 1, Qt.AlignTop)
                grid.addWidget(d, r, 2)
            c.add(grid)
            col.addWidget(c)
        col.addStretch(1)
        self.scroll.setWidget(inner)
        self.state.setText(t("{n} ayar", n=len(self.entries)))

    def _widget(self, e):
        v = e["value"]
        if e["type"] == "bool":
            w = QCheckBox()
            w.setChecked(v.lower() == "true")
            w.setCursor(Qt.PointingHandCursor)
            return w
        if e["type"] == "enum":
            w = QComboBox()
            for c in e["choices"]:
                w.addItem(t(CHOICE_NAMES[c]) if c in CHOICE_NAMES else c, c)
            i = w.findData(v)
            if i < 0:
                w.addItem(v, v)
                i = w.count() - 1
            w.setCurrentIndex(i)
            return w
        if e["type"] == "int":
            w = QSpinBox()
            lo, hi = e["range"] or (0, 2147483647)
            w.setRange(lo, min(hi, 2147483647))
            try:
                w.setValue(int(v))
            except ValueError:
                pass
            w.setMinimumWidth(120)
            return w
        if e["type"] == "float":
            w = QDoubleSpinBox()
            w.setDecimals(3)
            w.setRange(0, 1000)
            w.setSingleStep(0.05)
            try:
                w.setValue(float(v))
            except ValueError:
                pass
            return w
        w = QLineEdit(v)
        w.setMinimumWidth(220)
        return w

    @staticmethod
    def _value(e, w):
        if isinstance(w, QCheckBox):
            return "true" if w.isChecked() else "false"
        if isinstance(w, QComboBox):
            return w.currentData()
        if isinstance(w, QSpinBox):
            return str(w.value())
        if isinstance(w, QDoubleSpinBox):
            return f"{w.value():g}"
        return w.text().replace(";", "").strip()

    def save(self):
        changed = {}
        for key, (e, w) in self.widgets.items():
            nv = self._value(e, w)
            if nv != e["value"]:
                changed[key] = nv
        if not changed:
            self.info(t("Değişiklik yok."))
            return
        try:
            self.app.properties.save(changed)
        except Exception as ex:
            self.error(str(ex))
            return
        live = []
        if self.app.server.is_running:
            for k, v in changed.items():
                if k in LIVE:
                    self.app.server.try_send(LIVE[k].format(v=v, onoff="on" if v == "true" else "off"))
                    live.append(k)
        rest = [k for k in changed if k not in live]
        msg = t("{n} ayar kaydedildi.", n=len(changed))
        if live:
            msg += "\n" + t("Hemen uygulananlar: {list}", list=", ".join(live))
        if rest and self.app.server.is_running:
            msg += "\n" + t("Diğerleri sunucu yeniden başlayınca geçerli olur.")
        self.info(msg)
        self.on_show()
