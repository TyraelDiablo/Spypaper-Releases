"""Esplora yetenek (SKILL.md) düzenleyici, yetenek listesi ve samimiyet (üslup) ayarları."""
import os

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QVBoxLayout)

from core import N_, esplora_skills as SK
from .i18n import t
from .widgets import button, label, row

SCOPE_NAMES = [("all", N_("Tüm veriler")), ("players", N_("Yalnızca oyuncular")),
               ("config", N_("Ayarlar ve eklentiler")), ("logs", N_("Loglar ve çökmeler"))]


def _err(e):
    return t(str(e))


class SkillDialog(QDialog):
    """skill=None: yeni yetenek; yerleşik bir yetenek açılırsa kopyası olarak kaydedilir."""

    def __init__(self, settings, skill=None, parent=None):
        super().__init__(parent)
        self.settings, self.skill = settings, skill
        self.old_name = skill["name"] if skill and not skill.get("builtin") else None
        self.setWindowTitle(t("Yetenek oluştur") if not skill else t("Yetenek: /{name}", name=skill["name"]))
        self.resize(760, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Yetenek", "PageTitle"))
        v.addWidget(label("Yetenek, Esplora'ya bir iş için özel talimatlar verir. Sohbette /ad yazarak çağrılır "
                          "(ör. /yedekkontrol). SKILL.md biçiminde içe ve dışa aktarabilirsin.", "Muted", wrap=True))
        f = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("ornek-yetenek")
        self.desc = QLineEdit()
        self.desc.setPlaceholderText(t("Bu yetenek ne yapar? (komut listesinde görünür)"))
        self.scope = QComboBox()
        for k, n in SCOPE_NAMES:
            self.scope.addItem(t(n), k)
        self.effort = QCheckBox(t("Daha fazla çaba (derin analiz)"))
        f.addRow(t("Komut adı"), row(label("/"), self.name, stretch_end=False))
        f.addRow(t("Açıklama"), self.desc)
        f.addRow(t("Görebildiği veriler"), row(self.scope, self.effort))
        v.addLayout(f)
        v.addWidget(label("Talimatlar", "CardTitle"))
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText(t("Esplora bu yetenek çağrıldığında ne yapsın? Örnek:\n"
                                       "1. Son yedeğin ne zaman alındığına bak.\n"
                                       "2. 24 saatten eskiyse uyar ve Zamanlanmış Görevler'de yedek görevi öner.\n"
                                       "3. Cevabı tek bir tabloyla ver."))
        v.addWidget(self.body, 1)
        self.state = label("", "Muted", wrap=True)
        v.addWidget(self.state)
        v.addLayout(row(button("SKILL.md İçe Aktar…", "ghost", self.import_md),
                        button("SKILL.md Dışa Aktar…", "ghost", self.export_md), None,
                        button("İptal", "ghost", self.reject), button("Kaydet", "primary", self.save),
                        stretch_end=False))
        if skill:
            self._fill(skill)
            if skill.get("builtin"):
                self.state.setText(t("Bu yerleşik bir yetenek. Kaydedersen aynı adla senin sürümün kullanılır; "
                                     "silince yerleşik olana döner."))

    def _fill(self, sk):
        self.name.setText(sk["name"])
        self.desc.setText(t(sk["description"]) if sk.get("builtin") else sk["description"])
        self.scope.setCurrentIndex(max(0, self.scope.findData(sk.get("scope", "all"))))
        self.effort.setChecked(sk.get("effort") == "high")
        self.body.setPlainText(sk["body"])

    def _md(self):
        return SK.to_md({"name": self.name.text().strip().lower().lstrip("/"), "description": self.desc.text().strip(),
                         "scope": self.scope.currentData(), "effort": "high" if self.effort.isChecked() else "normal",
                         "body": self.body.toPlainText()})

    def import_md(self):
        path, _ = QFileDialog.getOpenFileName(self, t("SKILL.md İçe Aktar"), "", "Markdown (*.md);;*")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                self._fill(SK.parse(f.read()))
            self.state.setText(t("İçe aktarıldı: {path}", path=os.path.basename(path)))
        except (OSError, ValueError) as e:
            self.state.setText(_err(e))

    def export_md(self):
        try:
            md = SK.to_md(SK.parse(self._md()))
        except ValueError as e:
            self.state.setText(_err(e))
            return
        path, _ = QFileDialog.getSaveFileName(self, t("SKILL.md Dışa Aktar"), "SKILL.md", "Markdown (*.md)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(md)
            self.state.setText(t("Kaydedildi: {path}", path=path))

    def save(self):
        try:
            SK.save_user(self.settings, self._md(), self.old_name)
        except ValueError as e:
            self.state.setText(_err(e))
            return
        self.accept()


class SkillsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(t("Yetenekler"))
        self.resize(640, 520)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.addWidget(label("Yetenekler", "PageTitle"))
        v.addWidget(label("Sohbette /ad yazarak çağır. Yerleşik yetenekleri açıp kendi sürümünü kaydedebilirsin.",
                          "Muted", wrap=True))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self.edit())
        v.addWidget(self.list, 1)
        v.addLayout(row(button("Yeni…", "primary", lambda: self.edit(new=True)), button("Aç / Düzenle…", "ghost", self.edit),
                        button("Sil", "ghost", self.delete), None, button("Kapat", "ghost", self.accept),
                        stretch_end=False))
        self.refresh()

    def refresh(self):
        self.list.clear()
        users = {s["name"] for s in SK.user_skills(self.settings)}
        for sk in SK.all_skills(self.settings):
            desc = t(sk["description"]) if sk.get("builtin") else sk["description"]
            tag = t("yerleşik") if sk.get("builtin") else (t("düzenlenmiş") if any(b["name"] == sk["name"] for b in SK.BUILTINS)
                                                          else t("senin"))
            it = QListWidgetItem(f"/{sk['name']}  ·  {tag}\n{desc}")
            it.setData(256, sk["name"])
            self.list.addItem(it)
        self._users = users

    def _current(self):
        it = self.list.currentItem()
        return SK.find(self.settings, it.data(256)) if it else None

    def edit(self, new=False):
        sk = None if new else self._current()
        if not new and not sk:
            return
        if SkillDialog(self.settings, sk, self).exec():
            self.refresh()

    def delete(self):
        sk = self._current()
        if not sk:
            return
        if sk.get("builtin"):
            self.list.setToolTip(t("Yerleşik yetenekler silinemez."))
            return
        SK.delete_user(self.settings, sk["name"])
        self.refresh()


class StyleDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(t("Samimiyet ayarları"))
        self.resize(520, 300)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.addWidget(label("Esplora nasıl konuşsun?", "PageTitle"))
        f = QFormLayout()
        self.tone = QComboBox()
        for k, n in SK.TONES:
            self.tone.addItem(t(n), k)
        self.tone.setCurrentIndex(max(0, self.tone.findData(settings.get("esplora_tone") or "balanced")))
        self.length = QComboBox()
        for k, n in SK.LENGTHS:
            self.length.addItem(t(n), k)
        self.length.setCurrentIndex(max(0, self.length.findData(settings.get("esplora_length") or "normal")))
        self.emoji = QCheckBox(t("Emoji kullanabilsin"))
        self.emoji.setChecked(bool(settings.get("esplora_emoji")))
        self.uname = QLineEdit(settings.get("esplora_user_name") or "")
        self.uname.setPlaceholderText(t("İsteğe bağlı"))
        self.uname.setMaxLength(40)
        f.addRow(t("Üslup"), self.tone)
        f.addRow(t("Cevap uzunluğu"), self.length)
        f.addRow(t("Sana nasıl hitap etsin?"), self.uname)
        f.addRow("", self.emoji)
        v.addLayout(f)
        v.addStretch(1)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), button("Kaydet", "primary", self.save),
                        stretch_end=False))

    def save(self):
        s = self.settings
        s.set("esplora_tone", self.tone.currentData())
        s.set("esplora_length", self.length.currentData())
        s.set("esplora_emoji", self.emoji.isChecked())
        s.set("esplora_user_name", self.uname.text().strip())
        self.accept()
