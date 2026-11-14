"""Ana ekran: kayıtlı sunucular ve panel tasarımları."""
import os
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QMenu, QMessageBox, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from core import N_, detect_version
from . import icons, theme
from .dialogs import ServerDialog
from .i18n import t
from .theme import PRESETS, TOKENS, rgba
from .widgets import ask, button, label, row, segmented

COLS = 3


def _ago(iso):
    if not iso:
        return t("Hiç açılmadı")
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    sec = (datetime.now() - d).total_seconds()
    if sec < 60:
        return t("Az önce")
    if sec < 3600:
        return t("{n} dk önce", n=int(sec // 60))
    if sec < 86400:
        return t("{n} saat önce", n=int(sec // 3600))
    return d.strftime("%d.%m.%Y")


class ServerCard(QFrame):
    def __init__(self, home, profile):
        super().__init__()
        self.home, self.p = home, profile
        self.setObjectName("ServerCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 14)
        v.setSpacing(10)

        icon = label("", "ServerIcon")
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignCenter)
        ip = os.path.join(profile.server_path, "server-icon.png")
        if os.path.exists(ip):
            icon.setPixmap(QPixmap(ip).scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon.setText((profile.name[:1] or "?").upper())

        name = label(profile.name, "ServerName", raw=True)
        path = label(profile.server_path, "Muted", raw=True)
        path.setToolTip(profile.server_path)
        path.setMaximumWidth(260)
        fm = path.fontMetrics()
        path.setText(fm.elidedText(profile.server_path, Qt.ElideMiddle, 250))
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(name)
        col.addWidget(path)

        more = button("•••", "flat", self.menu, tooltip="Diğer işlemler")
        more.setFixedWidth(40)
        more.setStyleSheet("padding: 4px 0px; font-size: 11pt; letter-spacing: 1px;")
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(icon)
        top.addLayout(col, 1)
        top.addWidget(more, 0, Qt.AlignTop)
        v.addLayout(top)

        ver, soft = detect_version(profile.server_path) if profile.exists else ("", "")
        self.state_badge = label("", "Badge")
        badges = [self.state_badge]
        if soft or ver:
            b = label(" ".join(x for x in (soft, ver) if x), "Badge")
            b.setStyleSheet(f"color:{TOKENS['info']}; background:{rgba(TOKENS['info'], 35)};")
            badges.append(b)
        if profile.get("pin_hash"):
            b = label("", "Badge")
            b.setText(icons.img_tag("lock", TOKENS["text_muted"], 11) + " PIN")
            b.setStyleSheet(f"color:{TOKENS['text_muted']}; background:{rgba(TOKENS['text_muted'], 35)};")
            badges.append(b)
        if not profile.exists:
            b = label("Klasör yok", "Badge")
            b.setStyleSheet(f"color:{TOKENS['danger']}; background:{rgba(TOKENS['danger'], 35)};")
            badges.append(b)
        v.addLayout(row(*badges, spacing=6))
        v.addStretch(1)

        self.open_btn = button("Aç", "primary", self.open)
        self.quick = button("Başlat", "ghost", self.quick_start, tooltip="Paneli açmadan başlat")
        v.addLayout(row(label(t("Son açılış: {when}", when=_ago(profile.get("last_opened"))), "Muted"),
                        None, self.quick, self.open_btn, stretch_end=False))
        self.refresh_status()

    def refresh_status(self):
        running = self.home.ctl.is_running(self.p.id)
        txt, c = (t("Çalışıyor"), TOKENS["accent"]) if running else (t("Kapalı"), TOKENS["text_muted"])
        self.state_badge.setText(f"● {txt}")
        self.state_badge.setStyleSheet(f"color:{c}; background:{rgba(c, 35)};")
        self.quick.setText(t("Durdur") if running else t("Başlat"))
        self.quick.setEnabled(self.p.exists)
        self.open_btn.setEnabled(self.p.exists)

    def mouseDoubleClickEvent(self, e):
        self.open()

    def open(self):
        self.home.ctl.open_server(self.p.id)

    def quick_start(self):
        from core import ServerError
        from .widgets import err_text
        from .window import ask_pin, eula_ok
        if not ask_pin(self, self.p):
            return
        app = self.home.ctl.app_for(self.p.id)
        try:
            if app.server.is_running:
                app.server.stop()
            elif eula_ok(self, self.p.server_path):
                app.server.start()
        except ServerError as e:
            QMessageBox.critical(self, t("Hata"), err_text(e))
        self.refresh_status()

    def menu(self):
        m = QMenu(self)
        m.addAction(t("Aç"), self.open)
        m.addAction(t("Düzenle…"), lambda: self.home.edit_server(self.p))
        m.addAction(t("Klasörü Aç"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.p.server_path)))
        m.addSeparator()
        m.addAction(t("Listeden Kaldır"), lambda: self.home.remove_server(self.p))
        m.exec(self.cursor().pos())


class AddCard(QFrame):
    """Boş kart: yeni sunucu oluştur ya da var olanı ekle."""

    def __init__(self, on_click, on_new=None):
        super().__init__()
        self.setObjectName("ServerCard")
        self.setStyleSheet(f"QFrame#ServerCard {{ border: 2px dashed {TOKENS['border']}; background: transparent; }}"
                           f"QFrame#ServerCard:hover {{ border-color: {TOKENS['accent']}; }}")
        self.setMinimumHeight(170)
        self.on_click = on_click
        v = QVBoxLayout(self)
        plus = label("+", "HomeTitle")
        plus.setAlignment(Qt.AlignCenter)
        plus.setStyleSheet(f"color:{TOKENS['accent']}")
        txt = label("Sunucu Ekle", "CardTitle")
        txt.setAlignment(Qt.AlignCenter)
        sub = label("Sıfırdan yeni bir sunucu oluştur ya da var olan bir sunucu klasörünü seç", "Muted", wrap=True)
        sub.setAlignment(Qt.AlignCenter)
        v.addStretch(1)
        for w in (plus, txt, sub):
            v.addWidget(w)
        if on_new:
            v.addLayout(row(None, button("Yeni Sunucu Oluştur", "primary", on_new),
                            button("Var Olanı Ekle", "ghost", on_click), None, stretch_end=False))
        v.addStretch(1)


class ThemePreview(QWidget):
    """Tema renklerinden küçük bir panel önizlemesi çizer."""

    def __init__(self, tokens):
        super().__init__()
        self.k = tokens
        self.setFixedHeight(96)

    def paintEvent(self, _):
        k = self.k
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QColor(k["border"]))
        p.setBrush(QColor(k["bg"]))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(k["sidebar"]))
        p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 1, 56, r.height() - 2), 7, 7)
        for i in range(4):
            p.setBrush(QColor(k["accent"] if i == 0 else k["surface_3"]))
            p.drawRoundedRect(QRectF(r.left() + 9, r.top() + 12 + i * 16, 38, 8), 3, 3)
        for i, (x, w) in enumerate(((68, 70), (144, 70), (220, 50))):
            if x + w > r.width() - 8:
                break
            p.setBrush(QColor(k["surface"]))
            p.drawRoundedRect(QRectF(x, 12, w, 34), 5, 5)
            p.setBrush(QColor(k["text"]))
            p.drawRoundedRect(QRectF(x + 8, 20, w * 0.45, 5), 2, 2)
            p.setBrush(QColor(k["text_muted"]))
            p.drawRoundedRect(QRectF(x + 8, 31, w * 0.65, 4), 2, 2)
        p.setBrush(QColor(k["surface"]))
        p.drawRoundedRect(QRectF(68, 54, r.width() - 76, 32), 5, 5)
        p.setBrush(QColor(k["accent"]))
        p.drawRoundedRect(QRectF(r.width() - 58, 62, 42, 16), 4, 4)
        p.setBrush(QColor(k["danger"]))
        p.drawRoundedRect(QRectF(r.width() - 106, 62, 42, 16), 4, 4)


class ThemeCard(QFrame):
    def __init__(self, ctl, key):
        super().__init__()
        self.setObjectName("ThemeCard")
        name, desc, over = PRESETS[key]
        tokens = dict(theme.BASE)
        tokens.update(over)
        active = ctl.settings.get("theme") == key
        self.setProperty("active", "true" if active else "false")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)
        v.addWidget(ThemePreview(tokens))
        btn = button(N_("Etkin") if active else N_("Uygula"), "ghost" if active else "primary",
                     lambda: ctl.set_setting("theme", key))
        btn.setEnabled(not active)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(name, "CardTitle"))
        col.addWidget(label(desc, "Muted", wrap=True))
        h = QHBoxLayout()
        h.addLayout(col, 1)
        h.addWidget(btn, 0, Qt.AlignVCenter)
        v.addLayout(h)


class HomeScreen(QWidget):
    def __init__(self, ctl):
        super().__init__()
        self.ctl = ctl
        self.setObjectName("Page")
        self.cards = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        from .window import icon_button
        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 10, 22, 10)
        tl.addWidget(icon_button("menu", "Menü ve ayarlar (Ctrl+,)", ctl.toggle_drawer))
        tl.addWidget(label("Spypaper", "PageTitle"))
        tl.addStretch(1)
        tl.addWidget(button("Var Olanı Ekle", "ghost", self.add_server, tooltip="Var olan bir sunucu klasörünü ekle"))
        tl.addWidget(button("Yeni Sunucu Oluştur", "primary", self.new_server,
                            tooltip="Sunucu yazılımını indirip sıfırdan bir sunucu kur"))
        root.addWidget(top)

        body = QVBoxLayout()
        body.setContentsMargins(32, 26, 32, 22)
        body.setSpacing(16)
        root.addLayout(body, 1)

        hello = label(self._greeting(), "HomeTitle")
        self.summary = label("", "Muted")
        body.addWidget(hello)
        body.addWidget(self.summary)
        self.tabs = segmented(["Sunucular", "Panel Tasarımları"], self._tab)
        body.addLayout(row(self.tabs))

        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)

        # sunucular
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        self.grid = QGridLayout(inner)
        self.grid.setContentsMargins(0, 0, 6, 0)
        self.grid.setSpacing(16)
        sc.setWidget(inner)
        self.pages.addWidget(sc)

        # temalar
        tc = QScrollArea()
        tc.setWidgetResizable(True)
        tinner = QWidget()
        tg = QGridLayout(tinner)
        tg.setContentsMargins(0, 0, 6, 0)
        tg.setSpacing(16)
        for i, key in enumerate(PRESETS):
            tg.addWidget(ThemeCard(ctl, key), i // COLS, i % COLS)
        tg.setRowStretch(len(PRESETS) // COLS + 1, 1)
        tc.setWidget(tinner)
        self.pages.addWidget(tc)

        tip = label("İpucu: Dil, yazı boyutu ve erişilebilirlik ayarları için sol üstteki ☰ menüsünü kullan.", "Muted")
        body.addWidget(tip)

    @staticmethod
    def _greeting():
        h = datetime.now().hour
        return t("Günaydın") if 5 <= h < 12 else t("İyi günler") if h < 18 else t("İyi akşamlar")

    def _tab(self, i):
        self.pages.setCurrentIndex(i)

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        servers = sorted(self.ctl.settings.servers(), key=lambda p: p.get("last_opened") or "", reverse=True)
        self.cards = [ServerCard(self, p) for p in servers]
        for i, c in enumerate(self.cards + [AddCard(self.add_server, self.new_server)]):
            self.grid.addWidget(c, i // COLS, i % COLS)
        for c in range(COLS):
            self.grid.setColumnStretch(c, 1)
        self.grid.setRowStretch((len(self.cards) + 1) // COLS + 1, 1)
        self.refresh_status()

    def refresh_status(self):
        for c in self.cards:
            c.refresh_status()
        n = len(self.cards)
        on = sum(self.ctl.is_running(c.p.id) for c in self.cards)
        self.summary.setText(t("{n} kayıtlı sunucu · {on} çalışıyor", n=n, on=on) if n
                             else t("Henüz kayıtlı sunucu yok. Yeni bir sunucu oluştur ya da var olan bir sunucu klasörünü ekle."))

    # --- işlemler ---
    def add_server(self):
        dlg = ServerDialog(self.ctl.settings, parent=self)
        if dlg.exec():
            prof = dlg.save()
            self.refresh()
            if ask(self, t("'{name}' eklendi. Şimdi açılsın mı?", name=prof.name), t("Sunucu Ekle")):
                self.ctl.open_server(prof.id)

    def new_server(self):
        from .new_server_dialog import NewServerDialog
        dlg = NewServerDialog(self.ctl.settings, parent=self)
        if dlg.exec() and dlg.profile:
            self.refresh()
            if ask(self, t("'{name}' oluşturuldu. Şimdi açılsın mı?", name=dlg.profile.name), t("Yeni Sunucu Oluştur")):
                self.ctl.open_server(dlg.profile.id)

    def edit_server(self, prof):
        from .window import ask_pin
        if not ask_pin(self, prof, t("Ayarları değiştirmek için PIN gerekli.")):
            return
        if self.ctl.is_running(prof.id):
            QMessageBox.warning(self, t("Uyarı"), t("Sunucu çalışırken düzenlenemez."))
            return
        dlg = ServerDialog(self.ctl.settings, prof, parent=self)
        if dlg.exec():
            dlg.save()
            self.ctl.forget_server(prof.id)
            self.refresh()

    def remove_server(self, prof):
        from .window import ask_pin
        if not ask_pin(self, prof):
            return
        if self.ctl.is_running(prof.id):
            QMessageBox.warning(self, t("Uyarı"), t("Sunucu çalışırken listeden kaldırılamaz."))
            return
        if ask(self, t("'{name}' listeden kaldırılsın mı?\nSunucu dosyaları silinmez.", name=prof.name), t("Onay")):
            self.ctl.forget_server(prof.id)
            self.ctl.settings.remove_server(prof.id)
            self.refresh()
