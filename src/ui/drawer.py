"""☰ ile açılan ayarlar çekmecesi."""
import os
import webbrowser

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QSlider,
    QVBoxLayout, QWidget,
)

from core import N_, get_base_dir
from . import VERSION, i18n
from .i18n import t
from . import icons
from .theme import PRESETS, TOKENS
from .widgets import label

LINKS = [
    (N_("Paper belgeleri"), "https://docs.papermc.io/paper"),
    (N_("Fabric belgeleri"), "https://docs.fabricmc.net/"),
    (N_("NeoForge belgeleri"), "https://docs.neoforged.net/"),
    (N_("BlueMap belgeleri"), "https://bluemap.bluecolored.de/wiki/"),
]


def item(text, on_click, icon_name=None, raw=False):
    """icon_name: Lucide ikon adı ya da hazır QIcon. raw=True: metin çevrilmez (sunucu adı)."""
    text = text if raw else t(text)
    b = QPushButton(("  " + text) if icon_name else text)
    if icon_name:
        b.setIcon(icons.icon(icon_name, TOKENS["text_muted"], 16) if isinstance(icon_name, str) else icon_name)
        b.setIconSize(QSize(16, 16))
    b.setObjectName("DrawerItem")
    b.setCursor(Qt.PointingHandCursor)
    b.clicked.connect(on_click)
    return b


def section(text):
    s = t(text)
    if i18n.current() in ("tr", "az"):          # Türkçe büyük harf: i -> İ, ı -> I
        s = s.replace("i", "İ").replace("ı", "I")
    return label(s.upper(), "Section")


class Drawer(QWidget):
    WIDTH = 340

    def __init__(self, ctl, parent):
        super().__init__(parent)
        self.ctl = ctl
        s = ctl.settings
        self.setObjectName("Drawer")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(self.WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.setContentsMargins(18, 14, 10, 6)
        head.addWidget(label("Spypaper", "DrawerTitle"))
        head.addStretch(1)
        close = QPushButton()
        close.setIcon(icons.icon("x", TOKENS["text_muted"], 16))
        close.setObjectName("IconButton")
        close.setToolTip(t("Kapat (Esc)"))
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(ctl.toggle_drawer)
        head.addWidget(close)
        outer.addLayout(head)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(14, 0, 14, 14)
        v.setSpacing(6)
        sc.setWidget(inner)
        outer.addWidget(sc, 1)

        # --- gezinme ---
        v.addWidget(section("Gezinme"))
        v.addWidget(item("Ana Ekran", ctl.show_home, "house"))
        v.addWidget(item("Yeni Sunucu Oluştur", self._new, "circle-plus"))
        v.addWidget(item("Var Olanı Ekle", self._add, "folder-open"))
        self.servers_box = QVBoxLayout()
        self.servers_box.setSpacing(2)
        v.addLayout(self.servers_box)

        # --- dil ---
        v.addWidget(section("Dil"))
        self.lang = QComboBox()
        for code, name in i18n.available():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.get("language"))))
        self.lang.currentIndexChanged.connect(lambda i: ctl.set_setting("language", self.lang.itemData(i)))
        v.addWidget(self.lang)
        hint = label("Çeviri eksikse Türkçe gösterilir. Languages klasörüne JSON ekleyerek dil ekleyebilirsin.", "Muted", wrap=True)
        v.addWidget(hint)

        # --- görünüm ---
        v.addWidget(section("Görünüm"))
        v.addWidget(label("Panel tasarımı", "Muted"))
        self.theme = QComboBox()
        for key, (name, _d, _o) in PRESETS.items():
            self.theme.addItem(t(name), key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.get("theme"))))
        self.theme.currentIndexChanged.connect(lambda i: ctl.set_setting("theme", self.theme.itemData(i)))
        v.addWidget(self.theme)

        self.scale_lbl = label("", "Muted")
        v.addWidget(self.scale_lbl)
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(80, 160)
        self.scale.setSingleStep(10)
        self.scale.setPageStep(10)
        self.scale.setValue(int(round(float(s.get("font_scale")) * 100)))
        self._scale_text(self.scale.value())
        self.scale.valueChanged.connect(self._scale_text)
        self.scale.valueChanged.connect(
            lambda val: None if self.scale.isSliderDown() else ctl.set_setting("font_scale", round(val / 100, 2)))
        self.scale.sliderReleased.connect(lambda: ctl.set_setting("font_scale", round(self.scale.value() / 100, 2)))
        v.addWidget(self.scale)

        # --- erişilebilirlik ---
        v.addWidget(section("Erişilebilirlik"))
        v.addWidget(self._toggle("Yüksek kontrast", "high_contrast",
                                 "Yazı ve kenarlıkları belirginleştirir"))
        v.addWidget(self._toggle("Animasyonları azalt", "reduce_motion",
                                 "Menü kayma efektini kapatır"))
        v.addWidget(label("Kısayollar: Ctrl+, menü · Esc kapat · ↑↓ konsol geçmişi", "Muted", wrap=True))

        v.addWidget(self._toggle("Sunucu loglarını çevir", "translate_logs",
                                 "Ölüm, giriş ve başarım mesajlarını oyunun dil dosyalarıyla panel diline çevirir"))

        # --- yapay zeka ---
        v.addWidget(section("Yapay Zeka"))
        v.addWidget(item("Yapay Zeka Ayarları", self._ai, "sparkles"))

        # --- telefon ---
        v.addWidget(section("Telefon"))
        v.addWidget(item("Spypaper Remote", self._remote, "smartphone"))

        # --- genel ---
        v.addWidget(section("Genel"))
        v.addWidget(self._toggle("Açılışta son sunucuyu aç", "open_last_on_start",
                                 "Kapalıyken uygulama ana ekranla açılır"))
        v.addWidget(self._toggle("Çıkarken çalışan sunucuları sor", "confirm_on_close",
                                 "Kapalıysa sunucular sormadan durdurulur"))
        lim = QComboBox()
        for n in (1000, 2000, 5000, 10000, 20000, 50000):
            lim.addItem(f"{n:,}".replace(",", "."), n)
        cur = int(s.get("console_max_lines"))
        if lim.findData(cur) < 0:
            lim.addItem(str(cur), cur)
        lim.setCurrentIndex(lim.findData(cur))
        lim.currentIndexChanged.connect(lambda i: s.set("console_max_lines", lim.itemData(i)))
        h = QHBoxLayout()
        h.addWidget(label("Konsol satır sınırı"), 1)
        h.addWidget(lim)
        v.addLayout(h)
        v.addWidget(label("Güncelleme iletişim bilgisi", "Muted"))
        contact = QLineEdit(s.get("update_contact") or "")
        contact.setPlaceholderText(t("e-posta ya da site (PaperMC indirmeleri için)"))
        contact.setToolTip(t("PaperMC, indirme isteklerinde yazılımı kullananla iletişim kurulabilecek bir adres ister. Yalnızca PaperMC'ye gönderilir."))
        contact.editingFinished.connect(lambda: s.set("update_contact", contact.text().strip()))
        v.addWidget(contact)

        # --- diğer ---
        v.addWidget(section("Diğer"))
        v.addWidget(item("Panel klasörünü aç", lambda: self._open_dir(get_base_dir()), "folder-open"))
        v.addWidget(item("Dil dosyaları klasörü", lambda: self._open_dir(os.path.join(get_base_dir(), "Languages")), "languages"))
        for name, url in LINKS:
            v.addWidget(item(name, lambda _=False, u=url: webbrowser.open(u), "external-link"))
        v.addWidget(item("Oyun Dosyaları (dil ve ikon)", self._gamefiles, "package"))
        v.addWidget(item("Lisans ve Gizlilik", self._legal, "scale"))
        v.addWidget(item("Hakkında", self._about, "info"))
        v.addStretch(1)
        v.addWidget(label(f"Spypaper v{VERSION}", "Muted"))

    # --- yardımcılar ---
    def _toggle(self, text, key, tip):
        cb = QCheckBox(t(text))
        cb.setToolTip(t(tip))
        cb.setCursor(Qt.PointingHandCursor)
        cb.setChecked(bool(self.ctl.settings.get(key)))
        cb.toggled.connect(lambda on: self.ctl.set_setting(key, on))
        return cb

    def _scale_text(self, v):
        self.scale_lbl.setText(t("Yazı boyutu: %{n}", n=v))

    def sync(self):
        """Çekmece açılırken son açılan sunucuları listeler."""
        while self.servers_box.count():
            w = self.servers_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        recent = sorted(self.ctl.settings.servers(), key=lambda p: p.get("last_opened") or "", reverse=True)[:5]
        for p in recent:
            dot = icons.dot(TOKENS["accent"] if self.ctl.is_running(p.id) else TOKENS["text_muted"])
            self.servers_box.addWidget(item(p.name, lambda _=False, sid=p.id: self.ctl.open_server(sid), dot, raw=True))

    def _ai(self):
        from .ai_dialog import AIDialog
        AIDialog(self.ctl.settings, self).exec()

    def _new(self):
        self.ctl.toggle_drawer(animate=False)
        self.ctl.show_home()
        self.ctl.home.new_server()

    def _add(self):
        self.ctl.toggle_drawer(animate=False)
        self.ctl.show_home()
        self.ctl.home.add_server()

    @staticmethod
    def _open_dir(path):
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _remote(self):
        from .remote_dialog import RemoteDialog
        RemoteDialog(self.ctl, self).exec()

    def _gamefiles(self):
        from .gamefiles_dialog import GameFilesDialog
        GameFilesDialog(self).exec()

    def _legal(self):
        from .legal_dialog import LegalDialog
        LegalDialog(self).exec()

    def _about(self):
        from .msgbox import choose
        choose(self, "about", t("Hakkında"), t(
            "Spypaper v{v}\nMinecraft sunucu yönetim paneli.\n\nPython + PySide6 · nbtlib · psutil", v=VERSION)
            + "\n\n" + "© 2026 Serkan Aynacı (TyraelDiablo) · GPL-3.0"
            + "\n" + t("Özgür ve açık kaynak yazılım. Ayrıntılar: ☰ → Lisans ve Gizlilik.")
            + "\n\n" + t("Resmi bir Minecraft ürünü değildir. Mojang ya da Microsoft tarafından onaylanmamıştır ve onlarla bağlantılı değildir."),
            [(t("Tamam"), "primary")])
