"""Sunucu Ayarları → Yapı Yüksekliği kartı. Çekirdek: core/height.py."""
import os

from PySide6.QtWidgets import QCheckBox, QComboBox, QMessageBox, QSpinBox

from core import height as H
from .i18n import t
from .widgets import Card, button, label, row


def _y():
    s = QSpinBox()
    s.setRange(-H.LIMIT, H.LIMIT)
    s.setSingleStep(16)
    return s


class HeightCard(Card):
    def __init__(self, page):
        super().__init__("Yapı Yüksekliği", "Overworld'de blok koyulabilen en alt ve en üst Y. Değişiklik sunucu yeniden "
                                            "başlayınca geçerli olur; Spypaper bunun için dünyaya bir veri paketi ekler.")
        self.page = page
        self.preset = QComboBox()
        for name, lo, hi in H.PRESETS:
            self.preset.addItem(f"{t(name)}  ({lo} … {hi - 1})", (lo, hi))
        self.preset.addItem(t("Özel"), None)
        self.preset.currentIndexChanged.connect(self._preset)
        self.lo, self.hi = _y(), _y()
        for w in (self.lo, self.hi):
            w.valueChanged.connect(self._changed)
        self.add(row(label("Hazır", "Muted"), self.preset, label("En alt Y", "Muted"), self.lo,
                     label("En üst Y", "Muted"), self.hi, None, button("Uygula", "primary", self.apply_height),
                     stretch_end=False))
        self.deep = QCheckBox(t("Derinlerde de arazi üret (yalnızca yeni keşfedilen bölgeler)"))
        self.deep.setChecked(True)
        self.deep.setToolTip(t("Alt sınır -64'ün altındaysa ana kaya yeni tabana iner, aradaki bölge derin taşla dolar. "
                               "Önceden oluşmuş bölgelerin altı boş kalır."))
        self.add(self.deep)
        self.info = label("", "Muted", wrap=True)
        self.add(self.info)
        self.ram_warn = label("", "Muted", wrap=True)
        from .theme import TOKENS
        self.ram_warn.setStyleSheet(f"color:{TOKENS.get('warning', TOKENS.get('danger', '#e0a030'))};")
        self.ram_btn = button("RAM'i Artır", "ghost", self.raise_ram)
        self.add(row(self.ram_warn, self.ram_btn, stretch_end=False))

    # ------------------------------------------------------------------
    def _ctx(self):
        app = self.page.app
        level = app.properties.load().get("level-name") or "world"
        return app, level

    def load(self):
        app, level = self._ctx()
        lo, hi, has = H.current(app.config.server_path, level)
        self.saved = (lo, hi)
        self.deep.setChecked(H.deep_terrain(app.config.server_path, level) or not has)
        self._set(lo, hi)

    def _set(self, lo, hi):
        for w, v in ((self.lo, lo), (self.hi, hi)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._changed()

    def _preset(self, i):
        v = self.preset.itemData(i)
        if v:
            self._set(*v)

    def _changed(self, *_):
        lo, hi = self.lo.value(), self.hi.value()
        i = next((k for k in range(self.preset.count()) if self.preset.itemData(k) == (lo, hi)), self.preset.count() - 1)
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(i)
        self.preset.blockSignals(False)
        self.deep.setVisible(lo < H.DEFAULT[0])
        rec = H.recommended_ram_gb(lo, hi)
        self.info.setText(t("Yükseklik {h} blok (Y {lo} … {top}). Önerilen en az RAM: {rec} GB.",
                            h=hi - lo, lo=lo, top=hi - 1, rec=rec))
        have = H.parse_gb(self.page.app.config.get("ram_max"))
        low = have < rec
        self.ram_warn.setText(t("Bu sunucunun en fazla RAM'i {have} — bu yükseklik için en az {rec} GB önerilir. "
                                "Uygulamadan önce RAM'i artır.", have=self.page.app.config.get("ram_max") or "?", rec=rec)
                              if low else "")
        self.ram_warn.setVisible(low)
        self.ram_btn.setVisible(low)

    def raise_ram(self):
        rec = H.recommended_ram_gb(self.lo.value(), self.hi.value())
        c = self.page.app.config
        c.data["ram_max"] = f"{rec}G"
        c.save()
        self.page.ram_max.setText(f"{rec}G")
        self._changed()
        self.page.info(t("En fazla RAM {rec} GB yapıldı. Bilgisayarında yeterli bellek olduğundan emin ol.", rec=rec))

    def apply_height(self):
        app, level = self._ctx()
        lo, hi = self.lo.value(), self.hi.value()
        try:
            H.validate(lo, hi)
        except H.HeightError as e:
            self.page.warn(t(e.template, **e.kw))
            return
        if app.server.is_running:
            self.page.warn("Yapı yüksekliğini değiştirmeden önce sunucuyu durdur.")
            return
        rec = H.recommended_ram_gb(lo, hi)
        if H.parse_gb(app.config.get("ram_max")) < rec:
            if QMessageBox.question(self, t("Yapı Yüksekliği"), t(
                    "Bu yükseklik için en az {rec} GB RAM önerilir, sunucuda {have} var. Düşük RAM'le kasma ve çökme "
                    "olabilir.\n\nYine de uygulansın mı?", rec=rec, have=app.config.get("ram_max") or "?")) != QMessageBox.Yes:
                return
        world_exists = os.path.exists(os.path.join(app.config.server_path, level, "region")) or \
            os.path.exists(os.path.join(app.config.server_path, level, "dimensions"))
        risks = H.risks(self.saved, (lo, hi), world_exists)
        if risks:
            msg = "\n".join("• " + t(r) for r in risks) + "\n\n" + t("Önce dünya yedeği alman önerilir. Devam edilsin mi?")
            if QMessageBox.question(self, t("Yapı Yüksekliği"), msg) != QMessageBox.Yes:
                return
        try:
            from core.content import Fmt, data_format
            from core.config import detect_version
            ver = detect_version(app.config.server_path)[0] or ""
            fmt = data_format(Fmt(ver)) if ver else None
            H.apply(app.config.server_path, level, lo, hi, fmt, deep=self.deep.isChecked())
        except H.HeightError as e:
            self.page.warn(t(e.template, **e.kw))
            return
        except Exception as e:
            self.page.error(str(e))
            return
        self.saved = (lo, hi)
        self.page.info(t("Yapı yüksekliği Y {lo} … {top} olarak ayarlandı. Sunucuyu başlatınca geçerli olur.", lo=lo, top=hi - 1)
                       if (lo, hi) != H.DEFAULT else t("Yapı yüksekliği varsayılana döndü (veri paketi kaldırıldı)."))
