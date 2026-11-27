"""Panel doğrulaması: kurulum (☰ → Panel Doğrulaması) ve doğrulama penceresi (core.auth)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QVBoxLayout)

from core import auth
from .i18n import t
from .theme import TOKENS
from .widgets import button, label, row

_LIMIT = auth.Limiter()


def _pw_field(placeholder):
    f = QLineEdit()
    f.setEchoMode(QLineEdit.Password)
    f.setPlaceholderText(t(placeholder))
    return f


# ------------------------------------------------------------------ doğrulama
class VerifyDialog(QDialog):
    def __init__(self, settings, purpose="", parent=None):
        super().__init__(parent)
        self.settings = settings
        c = auth.cfg(settings)
        self.setWindowTitle(t("Panel Doğrulaması"))
        self.setMinimumWidth(420)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Spypaper korunuyor", "PageTitle"))
        if purpose:
            v.addWidget(label(purpose, "Muted", wrap=True))
        self.pw = self.ans = self.code = None
        self.q_box = QFrame()
        qv = QVBoxLayout(self.q_box)
        qv.setContentsMargins(0, 0, 0, 0)
        if c["question"]:
            qv.addWidget(label(t(c["question"].get("q", "")), wrap=True))
            self.ans = _pw_field("Cevap")
            qv.addWidget(self.ans)
        if c["password"]:
            self.pw = _pw_field("Şifre")
            v.addWidget(self.pw)
            if c["question"]:
                self.forgot = button("Şifremi unuttum: güvenlik sorusunu cevapla", "ghost", self._forgot)
                v.addWidget(self.forgot)
                self.q_box.hide()
        v.addWidget(self.q_box)
        if not c["question"]:
            self.q_box.hide()
        if c["totp"]:
            self.code = QLineEdit()
            self.code.setPlaceholderText(t("Uygulamadaki 6 haneli kod ya da kurtarma kodu"))
            self.code.setMaxLength(12)
            v.addWidget(label("Kimlik doğrulama uygulaması", "Muted"))
            v.addWidget(self.code)
        self.err = label("", wrap=True)
        self.err.setStyleSheet(f"color:{TOKENS['danger']}")
        v.addWidget(self.err)
        self.ok_btn = button("Aç", "primary", self._try)
        self.ok_btn.setDefault(True)
        v.addLayout(row(None, button("İptal", "ghost", self.reject), self.ok_btn, stretch_end=False))
        first = self.pw or self.ans or self.code
        if first:
            QTimer.singleShot(0, first.setFocus)
        self._tick()

    def _forgot(self):
        self.pw.clear()
        self.pw.hide()
        self.forgot.hide()
        self.q_box.show()
        self.ans.setFocus()

    def _tick(self):
        w = _LIMIT.wait()
        self.ok_btn.setEnabled(w == 0)
        if w:
            self._waiting = True
            self.err.setText(t("Çok fazla yanlış deneme. {n} saniye bekle.", n=w))
            QTimer.singleShot(1000, self._tick)
        elif getattr(self, "_waiting", False):
            self._waiting = False
            self.err.setText("")

    def _try(self):
        if _LIMIT.wait():
            return
        ok, why = auth.check(self.settings,
                             password=self.pw.text() if self.pw and not self.pw.isHidden() else "",
                             answer=self.ans.text() if self.ans and not self.q_box.isHidden() else "",
                             code=self.code.text() if self.code else "")
        if ok:
            _LIMIT.ok()
            self.accept()
            return
        _LIMIT.failed()
        self.err.setText(t(why))
        for f in (self.pw, self.ans, self.code):
            if f:
                f.clear()
        self._tick()


def verify(parent, settings, purpose=""):
    """Panel doğrulaması açıksa sorar. Doğruysa (ya da kapalıysa) True."""
    if not auth.enabled(settings):
        return True
    return VerifyDialog(settings, purpose, parent).exec() == QDialog.Accepted


# ------------------------------------------------------------------ kurulum
class AuthDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(t("Panel Doğrulaması"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 18, 22, 16)
        v.setSpacing(10)
        v.addWidget(label("Panel Doğrulaması", "PageTitle"))
        v.addWidget(label("Spypaper'ı başkası kullanamasın diye açılışta ve uyku modundan çıkarken doğrulama ister. "
                          "Şifre ve uygulama kodu birlikte açılırsa ikisi de sorulur; güvenlik sorusu şifreyi "
                          "unutursan kurtarma yoludur. Sunucuların kendi PIN'leri ayrıca geçerlidir.", "Muted", wrap=True))
        self.state = label("", wrap=True)
        v.addWidget(self.state)

        # şifre
        v.addWidget(label("Şifre", "CardTitle"))
        self.pw1, self.pw2 = _pw_field("Yeni şifre"), _pw_field("Yeni şifre tekrar")
        v.addLayout(row(self.pw1, self.pw2, button("Şifreyi Kaydet", "primary", self._save_pw),
                        button("Kaldır", "ghost", lambda: self._clear("password")), stretch_end=False))
        v.addWidget(label(t("En az {n} karakter, en az bir harf ve bir rakam.", n=auth.MIN_PASSWORD), "Muted"))

        # güvenlik sorusu
        v.addWidget(label("Güvenlik sorusu", "CardTitle"))
        self.q = QComboBox()
        self.q.setEditable(True)
        for q in auth.QUESTIONS:
            self.q.addItem(t(q), q)
        self.q.setMinimumWidth(300)
        self.a = _pw_field("Cevap")
        v.addLayout(row(self.q, self.a, button("Soruyu Kaydet", "primary", self._save_q),
                        button("Kaldır", "ghost", lambda: self._clear("question")), stretch_end=False))
        v.addWidget(label("Büyük-küçük harf ve fazladan boşluk fark etmez. Cevabı başkalarının bilemeyeceği bir soru seç.",
                          "Muted", wrap=True))

        # totp
        v.addWidget(label("Kimlik doğrulama uygulaması", "CardTitle"))
        v.addWidget(label("Google Authenticator, Microsoft Authenticator, Aegis gibi bir uygulamayla 6 haneli kod. "
                          "İnternet gerekmez.", "Muted", wrap=True))
        self.totp_box = QFrame()
        self.totp_box.hide()
        tb = QHBoxLayout(self.totp_box)
        tb.setContentsMargins(0, 0, 0, 0)
        self.qr = QLabel()
        self.qr.setFixedSize(200, 200)
        tb.addWidget(self.qr)
        side = QVBoxLayout()
        self.secret_lbl = label("", wrap=True)
        self.secret_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        side.addWidget(label("Uygulamayla QR kodu tara ya da anahtarı elle gir, sonra uygulamanın gösterdiği kodu yaz.",
                             wrap=True))
        side.addWidget(self.secret_lbl)
        self.verify_code = QLineEdit()
        self.verify_code.setPlaceholderText("123456")
        self.verify_code.setMaxLength(7)
        side.addLayout(row(self.verify_code, button("Doğrula ve Aç", "primary", self._finish_totp), stretch_end=False))
        side.addStretch(1)
        tb.addLayout(side, 1)
        v.addWidget(self.totp_box)
        self.totp_btns = row(button("Uygulamayı Bağla", "primary", self._start_totp),
                             button("Kaldır", "ghost", lambda: self._clear("totp")), None)
        v.addLayout(self.totp_btns)

        # ne zaman
        v.addWidget(label("Ne zaman sorulsun", "CardTitle"))
        c = auth.cfg(settings)
        self.on_start = QCheckBox(t("Spypaper açılırken"))
        self.on_start.setChecked(c["on_start"])
        self.on_sleep = QCheckBox(t("Uyku modundan çıkarken (uyku PIN'inin yerine)"))
        self.on_sleep.setChecked(c["on_sleep"])
        for cb, k in ((self.on_start, "on_start"), (self.on_sleep, "on_sleep")):
            cb.toggled.connect(lambda on, k=k: self._set(k, on))
        v.addWidget(self.on_start)
        v.addWidget(self.on_sleep)
        self.msg = label("", wrap=True)
        v.addWidget(self.msg)
        v.addLayout(row(None, button("Kapat", "ghost", self.accept), stretch_end=False))
        self._secret = ""
        self._refresh()

    # --- yardımcılar
    def _set(self, k, val):
        c = auth.cfg(self.settings)
        c[k] = val
        auth.save(self.settings, c)

    def _say(self, text, bad=False):
        self.msg.setStyleSheet(f"color:{TOKENS['danger' if bad else 'accent']}")
        self.msg.setText(text)

    def _refresh(self):
        on = [t({"password": "Şifre", "question": "Güvenlik sorusu", "totp": "Kimlik doğrulama uygulaması"}[m])
              for m in auth.methods(self.settings)]
        self.state.setText(t("Açık: {list}", list=", ".join(on)) if on else t("Panel doğrulaması kapalı."))

    def _confirm_current(self):
        """Var olan bir yöntemi değiştirmeden/kaldırmadan önce mevcut doğrulama istenir."""
        return verify(self, self.settings, t("Değişiklik için önce mevcut doğrulamayı geç."))

    def _clear(self, key):
        c = auth.cfg(self.settings)
        if not c[key] or not self._confirm_current():
            return
        c[key] = "" if key == "password" else {}
        auth.save(self.settings, c)
        self._say(t("Kaldırıldı."))
        self._refresh()

    def _save_pw(self):
        p1, p2 = self.pw1.text(), self.pw2.text()
        why = auth.password_problem(p1)
        if why:
            return self._say(t(why, n=auth.MIN_PASSWORD), True)
        if p1 != p2:
            return self._say(t("Şifreler eşleşmiyor."), True)
        if auth.cfg(self.settings)["password"] and not self._confirm_current():
            return
        c = auth.cfg(self.settings)
        c["password"] = auth.hash_pin(p1)
        auth.save(self.settings, c)
        self.pw1.clear()
        self.pw2.clear()
        self._say(t("Şifre kaydedildi."))
        self._refresh()

    def _save_q(self):
        q = self.q.currentText().strip()
        a = self.a.text()
        if not q or len(auth.normalize_answer(a)) < 2:
            return self._say(t("Bir soru seç ve cevabını yaz."), True)
        if auth.cfg(self.settings)["question"] and not self._confirm_current():
            return
        data = self.q.currentData()
        stored_q = data if data and t(data) == q else q        # hazır soru: dile göre çevrilsin
        c = auth.cfg(self.settings)
        c["question"] = {"q": stored_q, "a": auth.hash_answer(a)}
        auth.save(self.settings, c)
        self.a.clear()
        self._say(t("Güvenlik sorusu kaydedildi."))
        self._refresh()

    def _start_totp(self):
        if auth.cfg(self.settings)["totp"] and not self._confirm_current():
            return
        from .remote_dialog import qr_pixmap
        self._secret = auth.new_secret()
        uri = auth.otpauth_uri(self._secret)
        px = qr_pixmap(uri, 200)
        if px is not None:
            self.qr.setPixmap(px)
        else:
            self.qr.setText(t("QR gösterilemiyor; anahtarı elle gir."))
        grouped = " ".join(self._secret[i:i + 4] for i in range(0, len(self._secret), 4))
        self.secret_lbl.setText(t("Anahtar: {k}", k=grouped))
        self.totp_box.show()
        self.verify_code.setFocus()

    def _finish_totp(self):
        if not self._secret:
            return
        if not auth.verify_totp(self._secret, self.verify_code.text()):
            return self._say(t("Kod tutmadı. Bilgisayarın ve telefonun saati doğru mu?"), True)
        codes = auth.recovery_codes()
        auth.setup_totp(self.settings, self._secret, codes)
        self._secret = ""
        self.totp_box.hide()
        self.verify_code.clear()
        text = "\n".join(codes)
        QGuiApplication.clipboard().setText(text)
        QMessageBox.information(self, t("Kurtarma kodları"),
                                t("Telefonunu kaybedersen bu kodlardan biriyle girebilirsin. Her kod bir kez çalışır. "
                                  "Güvenli bir yere kaydet (panoya da kopyalandı):") + "\n\n" + text)
        self._say(t("Kimlik doğrulama uygulaması bağlandı."))
        self._refresh()
