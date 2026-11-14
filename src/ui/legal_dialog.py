"""Lisans (GNU GPL v3), gizlilik bildirimi ve üçüncü taraf bildirimleri penceresi (☰ menüsünden açılır).

Metinler legal/ klasöründen okunur (exe'de --add-data "legal;legal" ile gömülür).
Gizlilik bildirimi Türkçe arayüzde Türkçe, diğer dillerde İngilizce gösterilir.
"""
import html
import os
import webbrowser

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTabWidget, QTextBrowser, QVBoxLayout

from core import N_, resource_dir
from . import VERSION
from .i18n import current, t
from .theme import TOKENS
from .widgets import label

SOURCE_URL = "https://github.com/TyraelDiablo/Spypaper-Releases"
DOCS = {
    "privacy": (os.path.join("legal", "GIZLILIK.md"), os.path.join("legal", "PRIVACY_EN.md")),
    "thirdparty": (os.path.join("legal", "UCUNCU_TARAF.md"), os.path.join("legal", "UCUNCU_TARAF.md")),
}
FILE_TAB = {"LICENSE.txt": 0, "LICENSE": 0, "GIZLILIK.md": 1, "PRIVACY_EN.md": 1, "UCUNCU_TARAF.md": 2}


def _read(rel):
    for base in (resource_dir(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        p = os.path.join(base, rel)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
    return t("Belge bulunamadı: {f}", f=rel)


def license_html():
    """Kısa açıklama (arayüz dilinde) + GPL v3'ün tam metni (İngilizce, resmî metin)."""
    full = _read(os.path.join("legal", "LICENSE.txt"))
    intro = t("Spypaper özgür ve açık kaynak bir yazılımdır: GNU Genel Kamu Lisansı sürüm 3 (GPL-3.0) ile lisanslanmıştır. "
              "Programı ücretsiz kullanabilir, inceleyebilir, değiştirebilir ve paylaşabilirsin. Değiştirilmiş bir sürümü "
              "dağıtırsan onun kaynak kodunu da aynı lisansla paylaşman gerekir. Program hiçbir garanti olmadan sunulur.")
    note = t("Aşağıda lisansın resmî İngilizce metni yer alır; bağlayıcı olan bu metindir.")
    return (f"<h3>Spypaper v{VERSION} · GPL-3.0</h3>"
            f"<p>Copyright © 2026 Serkan Aynacı (TyraelDiablo)</p>"
            f"<p>{html.escape(intro)}</p>"
            f"<p>{html.escape(t('Kaynak kodu ve sürümler:'))} <a href='{SOURCE_URL}'>{SOURCE_URL}</a></p>"
            f"<p><i>{html.escape(note)}</i></p><hr>"
            f"<pre style='white-space:pre-wrap;font-size:11px'>{html.escape(full)}</pre>")


class LegalDialog(QDialog):
    def __init__(self, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle(t("Lisans ve Gizlilik"))
        self.resize(820, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        v.addWidget(label("Lisans ve Gizlilik", "PageTitle"))
        self.tabs = QTabWidget()
        idx = 0 if current() == "tr" else 1
        for key, title in (("license", N_("Lisans")), ("privacy", N_("Gizlilik")), ("thirdparty", N_("Üçüncü Taraf"))):
            br = QTextBrowser()
            br.setOpenLinks(False)
            br.anchorClicked.connect(self._link)
            br.document().setDefaultStyleSheet(f"a {{ color: {TOKENS['accent']}; }}")
            if key == "license":
                br.setHtml(license_html())
            else:
                br.setMarkdown(_read(DOCS[key][idx]))
            self.tabs.addTab(br, t(title))
        self.tabs.setCurrentIndex(tab)
        v.addWidget(self.tabs, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Close).setText(t("Kapat"))
        btns.button(QDialogButtonBox.Close).setProperty("variant", "ghost")
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _link(self, url):
        s = url.toString()
        name = os.path.basename(s.split("#")[0])
        if name in FILE_TAB:
            self.tabs.setCurrentIndex(FILE_TAB[name])
        elif s.startswith(("http://", "https://")):
            webbrowser.open(s)
