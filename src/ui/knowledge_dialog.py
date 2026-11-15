"""Esplora'ya sunucu hakkında bilgi verme penceresi (sunucu profilinde "esplora_knowledge")."""
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPlainTextEdit, QVBoxLayout

from .i18n import t
from .widgets import button, label

LIMIT = 8000


class KnowledgeDialog(QDialog):
    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.setWindowTitle(t("Sunucu Bilgileri"))
        self.resize(720, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Esplora'ya sunucunu anlat", "PageTitle"))
        v.addWidget(label("Esplora bunları her soruda bilir: sunucunun amacı, kuralları, yetkililer, ekonomi, "
                          "eklentileri nasıl kullandığın, bilinen sorunlar… Parola ya da gizli bilgi yazma.", "Muted", wrap=True))
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(t("Örnek:\n- Survival sunucusu, 15-20 oyuncu, Türkçe konuşuluyor.\n- Kurallar: hile, griefing ve hakaret yasak; ilk ihlalde 1 gün ban.\n"
                                       "- Yetkililer: Ali (kurucu), Ayşe (moderatör).\n- Ekonomi EssentialsX ile; başlangıç parası 500.\n"
                                       "- Haftalık bakım Pazartesi 04:00.\n- Bilinen sorun: büyük demir çiftliği spawn'da kasma yapıyor."))
        self.edit.setPlainText(profile.get("esplora_knowledge") or "")
        self.edit.textChanged.connect(self._count)
        v.addWidget(self.edit, 1)
        self.counter = label("", "Muted")
        h = QHBoxLayout()
        h.addWidget(self.counter)
        h.addStretch(1)
        h.addWidget(button("İptal", "ghost", self.reject))
        h.addWidget(button("Kaydet", "primary", self.save))
        v.addLayout(h)
        self._count()

    def _count(self):
        n = len(self.edit.toPlainText())
        self.counter.setText(t("{n} / {max} karakter", n=n, max=LIMIT))

    def save(self):
        self.profile.set("esplora_knowledge", self.edit.toPlainText()[:LIMIT])
        self.accept()
