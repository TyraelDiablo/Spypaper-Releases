"""Esplora — yapay zeka asistanı sayfası (mesaj balonlu sohbet)."""
import html
import re
import threading
from datetime import datetime

import base64

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
    QWidget,
)

from core import N_, ai, detect_version
from core import esplora_access as EA
from core import esplora_chats as EC
from core import esplora_kb
from core.esplora import build_system, config_files, latest_crash, preset_items, quick_items
from .. import icons
from ..i18n import current, is_rtl, t
from ..theme import TOKENS, rgba
from ..widgets import Card, Page, button, label, row, send_guarded

LANG_EN = {
    "tr": "Turkish", "en": "English", "de": "German", "fr": "French", "es": "Spanish",
    "pt_BR": "Brazilian Portuguese", "it": "Italian", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "uk": "Ukrainian", "az": "Azerbaijani", "ja": "Japanese", "ko": "Korean", "zh_CN": "Simplified Chinese",
    "ar": "Arabic",
}
BLOCK = re.compile(r"```([\w-]*)\s*\n(.*?)```", re.S)
MAX_IMAGES = 4              # bir mesajdaki en fazla görsel
IMAGE_SIDE = 1568           # uzun kenar (sağlayıcıların önerdiği üst sınır civarı)
IMAGE_HISTORY = 3           # görselleri gönderilen son kullanıcı mesajı sayısı (eskiler "[görsel]" olur)
MAX_ROUNDS = 3              # bir soruda en fazla veri isteği turu
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def encode_image(img):
    """QImage -> {"mime", "data"(base64)}: uzun kenar en fazla IMAGE_SIDE, saydamsa PNG yoksa JPEG."""
    if img.isNull():
        return None
    if max(img.width(), img.height()) > IMAGE_SIDE:
        img = img.scaled(IMAGE_SIDE, IMAGE_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    fmt, mime = ("PNG", "image/png") if img.hasAlphaChannel() else ("JPEG", "image/jpeg")
    for attempt in (fmt, "JPEG"):
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, attempt, 85 if attempt == "JPEG" else -1)
        buf.close()
        if attempt == "JPEG":
            mime = "image/jpeg"
        if ba.size() <= 3_500_000:
            break
    return {"mime": mime, "data": base64.b64encode(bytes(ba)).decode("ascii")}


def image_pixmap(im, side=120):
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(im["data"]))
    return pm.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pm.isNull() else pm


class ChatInput(QPlainTextEdit):
    """Ctrl+Enter gönderir; görsel yapıştırma (Ctrl+V) ve sürükle-bırak görsel ekler."""
    image = Signal(object)
    submit = Signal()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.submit.emit()
        else:
            super().keyPressEvent(e)

    def canInsertFromMimeData(self, src):
        return src.hasImage() or src.hasUrls() or super().canInsertFromMimeData(src)

    def insertFromMimeData(self, src):
        if src.hasImage():
            self.image.emit(QImage(src.imageData()))
            return
        if src.hasUrls():
            files = [u.toLocalFile() for u in src.urls() if u.isLocalFile() and u.toLocalFile().lower().endswith(IMAGE_EXT)]
            for f in files:
                self.image.emit(QImage(f))
            if files:
                return
        super().insertFromMimeData(src)


def _inline(s):
    s = html.escape(s.strip("\n"))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", rf'<code style="background:{TOKENS["surface_3"]};">&nbsp;\1&nbsp;</code>', s)
    out = []
    for ln in s.split("\n"):
        if re.match(r"^\s*[-*•] ", ln):
            ln = "•&nbsp;" + re.sub(r"^\s*[-*•] ", "", ln)
        elif re.match(r"^#{1,4} ", ln):
            ln = "<b>" + re.sub(r"^#{1,4} ", "", ln) + "</b>"
        out.append(ln)
    return "<br>".join(out)


def split_message(text):
    """Metni parçalara böler: [("text", html) | ("cmds", [komut…]) | ("code", metin)]."""
    parts, pos = [], 0
    for m in BLOCK.finditer(text):
        if text[pos:m.start()].strip():
            parts.append(("text", _inline(text[pos:m.start()])))
        lang, body = m.group(1).lower(), m.group(2)
        if lang in ("mc", "mcfunction", "minecraft"):
            cmds = [l.strip().lstrip("/") for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
            if cmds:
                parts.append(("cmds", cmds))
        elif lang == "esplora-get":
            reqs = EA.parse_requests(m.group(0))
            if reqs:
                parts.append(("get", reqs))
        elif lang == "esplora-set":
            sets = EA.parse_sets(m.group(0))
            if sets:
                parts.append(("set", sets))
        else:
            parts.append(("code", body.rstrip()))
        pos = m.end()
    if text[pos:].strip():
        parts.append(("text", _inline(text[pos:])))
    return parts


class Bubble(QFrame):
    """Tek bir mesaj balonu. role: user | assistant | error | thinking"""

    def __init__(self, page, role, text, when="", images=None):
        super().__init__()
        self.page = page
        k = TOKENS
        bg = {"user": rgba(k["accent"], 38), "assistant": k["surface_2"], "stopped": "transparent", "note": "transparent",
              "error": rgba(k["danger"], 40), "thinking": k["surface_2"]}[role]
        border = {"user": rgba(k["accent"], 90), "error": rgba(k["danger"], 110)}.get(role, k["border"])
        self.setObjectName("Bubble")
        self.setStyleSheet(f"QFrame#Bubble {{ background:{bg}; border:1px solid {border}; border-radius:14px; }}")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(6)

        who = {"user": t("Sen"), "note": "Spypaper"}.get(role, "Esplora")
        color = {"user": k["accent"], "error": k["danger"], "stopped": k["text_muted"],
                 "note": k["text_muted"]}.get(role, k["info"])
        head = QLabel(f'<span style="color:{color}; font-weight:700;">{html.escape(who)}</span>'
                      + (f'&nbsp;&nbsp;<span style="color:{k["text_muted"]}; font-size:8pt;">{when}</span>' if when else ""))
        v.addWidget(head)

        if role == "thinking":
            self.dots = QLabel(t("düşünüyor…"))
            self.dots.setStyleSheet(f"color:{k['text_muted']};")
            v.addWidget(self.dots)
            return
        if role in ("stopped", "note"):
            lbl = self._text(html.escape(text))
            lbl.setStyleSheet(f"color:{k['text_muted']}; font-style: italic; background: transparent;")
            v.addWidget(lbl)
            return
        if role in ("user", "error"):
            if images:
                strip = QHBoxLayout()
                strip.setSpacing(6)
                for im in images:
                    th = QLabel()
                    if im.get("data"):
                        th.setPixmap(image_pixmap(im))
                        th.setStyleSheet("background: transparent;")
                    else:                       # kayıtlı sohbet: görsel diske yazılmadı
                        th.setText(t("[görsel]"))
                        th.setStyleSheet(f"color:{k['text_muted']}; font-style: italic; background: transparent;")
                    strip.addWidget(th)
                strip.addStretch(1)
                v.addLayout(strip)
            if text.strip():
                v.addWidget(self._text(_inline(text)))
            return
        for kind, val in split_message(text):
            if kind == "text":
                v.addWidget(self._text(val))
            elif kind == "code":
                c = self._text(f'<pre style="margin:0;">{html.escape(val)}</pre>')
                c.setStyleSheet(f"background:{k['surface']}; border-radius:8px; padding:8px; font-family:Consolas;")
                v.addWidget(c)
            elif kind == "get":
                names = ", ".join(t(EA.ITEMS[key][0]) + (f" ({arg})" if arg else "") for key, arg in val)
                g = self._text(html.escape(t("Veri istedi: {items}", items=names)))
                g.setStyleSheet(f"color:{k['text_muted']}; font-style: italic; background: transparent;")
                v.addWidget(g)
            elif kind == "set":
                v.addWidget(self._sets(val))
            elif EA.level(page.app.config, "commands.suggest") == "off":
                c = self._text(f'<pre style="margin:0;">{html.escape(chr(10).join(val))}</pre>')
                c.setStyleSheet(f"background:{k['surface']}; border-radius:8px; padding:8px; font-family:Consolas;")
                v.addWidget(c)
            else:
                v.addWidget(self._cmds(val))

    def _text(self, h):
        lbl = QLabel(h)
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setStyleSheet("background: transparent;")
        # kelime kaydırmalı QLabel kendini daraltır; metnin doğal genişliğine (en fazla 620px) izin ver
        plain = re.sub(r"<[^>]+>", "", h.replace("<br>", "\n")).replace("&nbsp;", " ")
        plain = html.unescape(plain)
        longest = max((lbl.fontMetrics().horizontalAdvance(l) for l in plain.split("\n")), default=0)
        lbl.setMinimumWidth(min(longest + 18, 620))
        return lbl

    def _sets(self, sets):
        """server.properties değişiklik önerisi: mevcut → önerilen, Uygula düğmesi (izin Onaylı ise)."""
        box = QFrame()
        box.setMinimumWidth(480)
        box.setObjectName("Cmds")
        box.setStyleSheet(f"QFrame#Cmds {{ background:{TOKENS['surface']}; border-radius:8px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        cur = self.page.app.properties.load()
        for key, val in sets:
            h = QHBoxLayout()
            c = QLabel(f"{key}: {cur.get(key, '—')}  →  {val}")
            c.setTextInteractionFlags(Qt.TextSelectableByMouse)
            c.setStyleSheet(f"font-family:Consolas; color:{TOKENS['text']}; background:transparent;")
            h.addWidget(c, 1)
            if EA.level(self.page.app.config, "settings.write") != "off":
                b = QPushButton(t("Uygula"))
                b.setProperty("variant", "primary")
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, kk=key, vv=val, bb=b: self.page.apply_setting(kk, vv, bb))
                if cur.get(key) == val:                     # zaten bu değerde (uygulanmış)
                    b.setEnabled(False)
                    b.setText(t("Uygulandı"))
                h.addWidget(b)
            v.addLayout(h)
        if EA.level(self.page.app.config, "settings.write") == "off":
            n = QLabel(t("Ayar değiştirme Veri İzinleri'nde kapalı."))
            n.setStyleSheet(f"color:{TOKENS['text_muted']}; background:transparent;")
            v.addWidget(n)
        return box

    def _cmds(self, cmds):
        box = QFrame()
        box.setMinimumWidth(480)
        box.setObjectName("Cmds")
        box.setStyleSheet(f"QFrame#Cmds {{ background:{TOKENS['surface']}; border-radius:8px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(4)
        for cmd in cmds:
            h = QHBoxLayout()
            c = QLabel(cmd)
            c.setTextInteractionFlags(Qt.TextSelectableByMouse)
            c.setStyleSheet(f"font-family:Consolas; color:{TOKENS['text']}; background:transparent;")
            b = QPushButton(t("Çalıştır"))
            b.setIcon(icons.icon("play", TOKENS.get("on_accent", "#0b0b0b"), 14))
            b.setProperty("variant", "primary")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=cmd: self.page.run(x))
            h.addWidget(c, 1)
            h.addWidget(b)
            v.addLayout(h)
        return box


class EsploraPage(Page):
    title = "Esplora"
    reply = Signal(int, str, str, str)     # istek no, metin, hata, yeni_model
    fetched = Signal(int, object)          # istek no, [(anahtar, argüman, metin, durum)]

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        if not hasattr(app, "esplora_history"):
            app.esplora_history = []          # arayüz yeniden kurulsa da kalır
        if not hasattr(app, "esplora_chat_id"):
            app.esplora_chat_id = None        # kayıtlı sohbetin kimliği (core.esplora_chats)
        self.store = EC.ChatStore.for_profile(app.config)
        self._saved_sig = None
        self.busy = False

        head = Card("Esplora", "Bu sunucuya özel yapay zeka asistanı. Yalnızca sunucu yönetimiyle ilgili sorulara yanıt verir.")
        head.header_actions.addWidget(button("Yeni sohbet", "ghost", self.reset))
        head.header_actions.addWidget(button("Geçmiş", "ghost", self.open_history,
                                             tooltip="Kayıtlı sohbetleri aç ya da sil"))
        head.header_actions.addWidget(button("Sunucu Bilgileri", "ghost", self.edit_knowledge,
                                             tooltip="Esplora'ya sunucun hakkında bilmesi gerekenleri yaz"))
        head.header_actions.addWidget(button("Veri İzinleri", "ghost", self.open_access,
                                             tooltip="Esplora'nın hangi verilere ulaşabileceğini ve hangileri için sana soracağını ayarla"))
        head.header_actions.addWidget(button("Yapay Zeka Ayarları", "ghost", self.open_settings))
        self.model_lbl = label("", "Muted")
        head.add(self.model_lbl)
        self.root.addWidget(head)

        # sohbet alanı
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("Chat")
        self.scroll.setStyleSheet(f"QScrollArea#Chat {{ background:{TOKENS['surface']}; border:1px solid {TOKENS['border']};"
                                  f" border-radius:8px; }}")
        self._new_canvas()
        self.scroll.verticalScrollBar().rangeChanged.connect(lambda _a, b: self.scroll.verticalScrollBar().setValue(b))
        self.root.addWidget(self.scroll, 1)

        # hızlı sorular (sunucunun durumuna göre değişir) + tüm hazır sorular menüsü
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        self.root.addLayout(self.chips)
        self.flags = {}

        # eklenecek görseller (gönderilmeden önce)
        self.images = []
        self.thumbs = QHBoxLayout()
        self.thumbs.setSpacing(6)
        self.root.addLayout(self.thumbs)

        self.input = ChatInput()
        self.input.setPlaceholderText(t("Esplora'ya sor… (Ctrl+Enter ile gönder, Ctrl+V ile görsel yapıştır)"))
        self.input.setFixedHeight(70)
        self.input.submit.connect(lambda: self.ask(self.input.toPlainText()))
        self.input.image.connect(self.add_image)
        self.gen = 0                         # her istekte artar; durdurulan isteğin geç gelen yanıtı yok sayılır
        self.rounds = 0                      # bu sorudaki veri isteği turu
        self.pending = None                  # onay bekleyen veri istekleri
        self.attach_btn = QPushButton()
        self.attach_btn.setIcon(icons.icon("image", None, 18))
        self.attach_btn.setProperty("variant", "ghost")
        self.attach_btn.setToolTip(t("Görsel ekle"))
        self.attach_btn.setCursor(Qt.PointingHandCursor)
        self.attach_btn.clicked.connect(self.pick_images)
        self.send_btn = button("Gönder", "primary", self._send_or_stop)
        self.root.addLayout(row(self.attach_btn, self.input, self.send_btn, stretch_end=False))
        self.reply.connect(self._on_reply)
        self.fetched.connect(self._on_fetched)
        self._dots = QTimer(self)
        self._dots.timeout.connect(self._tick)
        self.render()

    def _flags(self):
        """Hazır soruların koşulları: running, stopped, modded, plugins, lag, errors, crash."""
        a = self.app
        today = datetime.now().date()
        evs = [e for e in a.logs.events if e.time.date() == today]
        running = a.server.state in ("starting", "running")
        modded = a.plugins.modded
        return {"running": running, "stopped": not running, "modded": modded, "plugins": not modded,
                "lag": any(e.kind == "lag" for e in evs), "errors": any(e.kind == "error" for e in evs),
                "crash": latest_crash(a.config.server_path) is not None}

    def _build_chips(self):
        while self.chips.count():
            it = self.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.flags = self._flags()
        for lab, q in quick_items(self.flags):
            b = button(lab, "ghost", lambda _=False, l=lab, q=q: self.ask(t(q), label=t(l)))
            b.setToolTip(t(q))
            self.chips.addWidget(b)
        self.chips.addStretch(1)
        more = button("Tüm hazır sorular ▾", "flat", self._preset_menu, tooltip="Kategorilere ayrılmış hazır sorular")
        more.setText(more.text().replace("▾", "").strip())
        more.setIcon(icons.icon("chevron-down", None, 14))
        more.setLayoutDirection(Qt.RightToLeft)             # ok simgesi metnin sağında
        self.chips.addWidget(more)

    def _preset_menu(self):
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for icon, cat, items in preset_items(self.flags or self._flags()):
            sub = m.addMenu(icons.icon(icon, None, 16), t(cat))
            for lab, q in items:
                act = sub.addAction(t(lab))
                act.setToolTip(t(q))
                act.triggered.connect(lambda _=False, l=lab, q=q: self.ask(t(q), label=t(l)))
            sub.setToolTipsVisible(True)
        m.exec(QCursor.pos())

    def on_show(self):
        self._build_chips()
        cfg = ai.get_cfg(self.app.config.settings)
        has_key = bool(ai.api_key(cfg)) or cfg["provider"] == "openai" and cfg.get("base_url")
        self.model_lbl.setText(
            t("Model: {model} · {provider}", model=cfg["model"], provider=ai.PROVIDERS[cfg["provider"]]["name"])
            if has_key else t("API anahtarı ayarlanmamış. Başlamak için Yapay Zeka Ayarları'nı aç."))

    # --- görseller ---
    def pick_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, t("Görsel ekle"), "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        for f in files:
            self.add_image(QImage(f))

    def add_image(self, img):
        if len(self.images) >= MAX_IMAGES:
            self.warn(t("Bir mesaja en fazla {n} görsel eklenebilir.", n=MAX_IMAGES))
            return
        enc = encode_image(img)
        if not enc:
            self.warn("Resim açılamadı.")
            return
        self.images.append(enc)
        self._show_thumbs()

    def _show_thumbs(self):
        while self.thumbs.count():
            it = self.thumbs.takeAt(0)
            w = it.widget()
            if w:
                w.hide()                           # deleteLater olay döngüsünü bekler; o ana kadar boşta görünmesin
                w.deleteLater()
        for i, im in enumerate(self.images):
            box = QFrame()
            box.setObjectName("Thumb")
            box.setStyleSheet(f"QFrame#Thumb {{ background:{TOKENS['surface_2']}; border:1px solid {TOKENS['border']}; border-radius:6px; }}")
            h = QHBoxLayout(box)
            h.setContentsMargins(4, 4, 4, 4)
            th = QLabel()
            th.setPixmap(image_pixmap(im, 56))
            th.setStyleSheet("background:transparent; border:none;")
            x = button("×", "flat", lambda _=False, n=i: self._remove_image(n), tooltip="Kaldır")
            h.addWidget(th)
            h.addWidget(x)
            self.thumbs.addWidget(box)
        if self.images:
            self.thumbs.addStretch(1)

    def _remove_image(self, i):
        if 0 <= i < len(self.images):
            self.images.pop(i)
            self._show_thumbs()

    def open_access(self):
        from ..access_dialog import AccessDialog
        AccessDialog(self.app.config, self).exec()
        self.render()

    def open_settings(self):
        from ..ai_dialog import AIDialog
        AIDialog(self.app.config.settings, self).exec()
        self.on_show()

    def reset(self):
        if self.busy:
            self.stop()
        self.app.esplora_history.clear()
        self.app.esplora_chat_id = None
        self.pending = None
        self.rounds = 0
        self.render()

    # --- sohbet geçmişi ---
    def _persist(self):
        """Açık sohbeti diske yazar (ayar kapalıysa yazmaz). Değişmediyse tekrar yazmaz."""
        hist = self.app.esplora_history
        if not hist or not self.app.config.settings.get("esplora_save_chats"):
            return
        sig = (self.app.esplora_chat_id, len(hist), hist[-1].get("content", "")[:200])
        if sig == self._saved_sig:
            return
        if not self.app.esplora_chat_id:
            self.app.esplora_chat_id = EC.new_id()
        try:
            self.store.save(self.app.esplora_chat_id, hist)
            self._saved_sig = (self.app.esplora_chat_id, len(hist), hist[-1].get("content", "")[:200])
        except OSError as e:
            print(f"[esplora] sohbet kaydedilemedi: {e}")

    def open_history(self):
        from ..chat_history_dialog import ChatHistoryDialog
        self._persist()
        dlg = ChatHistoryDialog(self.store, self.app.config.settings, self.app.esplora_chat_id, self)
        dlg.exec()
        if dlg.chosen:
            self.open_chat(dlg.chosen)
        elif self.app.esplora_chat_id and not any(c["id"] == self.app.esplora_chat_id for c in self.store.list()):
            self.app.esplora_chat_id = None          # açık sohbet silindi: sonraki kayıt yeni dosyaya gider
            self._saved_sig = None

    def open_chat(self, chat_id):
        msgs = self.store.load(chat_id)
        if msgs is None:
            return False
        if self.busy:
            self.stop()
        self.app.esplora_history[:] = msgs
        self.app.esplora_chat_id = chat_id
        self.pending = None
        self.rounds = 0
        self._saved_sig = (chat_id, len(msgs), msgs[-1].get("content", "")[:200] if msgs else "")
        self.render()
        return True

    # --- bağlam ---
    def context(self, question=""):
        a = self.app
        ver, soft = detect_version(a.config.server_path)
        from core.logwatch import online_timeline
        _, online = online_timeline(a.logs.events)
        log = list(a.server.history)[-60:] if a.server.history else [e.raw for e in a.logs.events[-60:]]
        today = datetime.now().date()
        todays = [e for e in a.logs.events if e.time.date() == today]
        stats = (f"{len({e.player for e in todays if e.kind == 'join'})} unique players, "
                 f"{sum(e.kind == 'death' for e in todays)} deaths, {sum(e.kind == 'lag' for e in todays)} lag warnings, "
                 f"{sum(e.kind == 'error' for e in todays)} errors")
        return {
            "name": a.config.name, "software": soft, "version": ver,
            "state": a.server.state, "jar": a.config.get("jar_name"), "java": a.config.get("java_path"),
            "ram_limits": f"{a.config.get('ram_min')} / {a.config.get('ram_max')}",
            "safe_mode": a.config.get("safe_mode") or 0,
            "online": online, "known_players": [p.name for p in a.players.list_players(online)][:60],
            "plugins": [n.replace(".jar.disabled", " (disabled)").replace(".jar", "") for n, _, _ in a.plugins.list()],
            "modded": a.plugins.modded,
            "properties": a.properties.load(), "stats": stats, "log": log,
            # son 60 satırın dışında kalmış olabilecek hata/uyarılar ve son çökme raporu
            "recent_errors": [e.raw for e in a.logs.events if e.kind in ("error", "lag")][-20:],
            "crash": latest_crash(a.config.server_path),
            # uzman bilgi bankasından soruyla ilgili bölümler, sahibin bilgileri ve ilgili yapılandırma dosyaları
            "kb": esplora_kb.relevant(question, f"{soft} {ver} " + ("lag" if any(e.kind == "lag" for e in todays) else "")),
            "owner": (a.config.get("esplora_knowledge") or "").strip(),
            "configs": config_files(a.config.server_path, question, modded=a.plugins.modded),
        }


    # --- sohbet ---
    def _send_or_stop(self):
        if self.busy:
            self.stop()
        else:
            self.ask(self.input.toPlainText())

    def _set_busy(self, on):
        self.busy = on
        self.send_btn.setText(t("Durdur") if on else t("Gönder"))
        self.send_btn.setProperty("variant", "danger" if on else "primary")
        self.send_btn.style().unpolish(self.send_btn)
        self.send_btn.style().polish(self.send_btn)

    def ask(self, text, label=None):
        """label: hazır sorularda balonda görünen kısa metin; Esplora'ya ayrıntılı soru (text) gider."""
        text = text.strip()
        images = list(self.images) if label is None else []
        if (not text and not images) or self.busy:
            return
        if label is None:
            self.input.clear()
            self.images = []
            self._show_thumbs()
        self.pending = None                 # onay bekleyen istek varsa yeni soru onu iptal eder
        self.rounds = 0
        msg = {"role": "user", "content": text, "time": datetime.now().strftime("%H:%M")}
        if images:
            msg["images"] = images
        if label:
            msg["label"] = label
        self.app.esplora_history.append(msg)
        self._request()

    @staticmethod
    def _api_messages(hist):
        """Hata/durdurma/not balonlarını çıkarır, art arda gelen aynı rolleri birleştirir (bazı API'ler ister).
        Görseller yalnızca son IMAGE_HISTORY görselli mesajda gönderilir; öncekiler "[görsel]" olur."""
        recent = hist[-24:]
        with_img = [i for i, m in enumerate(recent)
                    if any(im.get("data") for im in m.get("images") or [])][-IMAGE_HISTORY:]
        out = []
        for i, m in enumerate(recent):
            if m.get("error") or m.get("stopped") or m.get("note"):
                continue
            parts = [{"type": "text", "text": m["content"]}] if m["content"] else []
            if m.get("images"):
                if i in with_img:
                    parts = ([{"type": "image", **im} for im in m["images"] if im.get("data")]
                             + (parts or [{"type": "text", "text": "(image)"}]))
                else:
                    parts = [{"type": "text", "text": f"[{len(m['images'])} image(s) sent earlier]"}] + parts
            if not parts:
                continue
            if out and out[-1]["role"] == m["role"]:
                out[-1]["parts"] += [{"type": "text", "text": "\n\n"}] + parts
            else:
                out.append({"role": m["role"], "parts": parts})
        while out and out[0]["role"] != "user":
            out.pop(0)
        result = []
        for m in out:
            if all(p["type"] == "text" for p in m["parts"]):
                result.append({"role": m["role"], "content": "".join(p["text"] for p in m["parts"])})
            else:
                merged = []
                for p in m["parts"]:
                    if p["type"] == "text" and merged and merged[-1]["type"] == "text":
                        merged[-1] = {"type": "text", "text": merged[-1]["text"] + p["text"]}
                    elif not (p["type"] == "text" and not p["text"].strip()):
                        merged.append(p)
                result.append({"role": m["role"], "content": merged})
        return result

    def _request(self):
        self.gen += 1
        my = self.gen
        self._set_busy(True)
        self.render(thinking=True)
        settings = self.app.config.settings
        last = next((m["content"] for m in reversed(self.app.esplora_history)
                     if m["role"] == "user" and not m.get("data") and not m.get("cmd")), "")
        prof = self.app.config
        system = build_system(EA.filter_context(self.context(last), prof), LANG_EN.get(current(), "English"),
                              access=EA.prompt_section(prof), no_commands=EA.command_rule(prof))
        msgs = self._api_messages(self.app.esplora_history)

        def work():
            try:
                out, new = ai.chat_auto(settings, system, msgs)
                self.reply.emit(my, out, "", new or "")
            except Exception as e:
                err = t(e.template, **e.kw) if hasattr(e, "template") else str(e)
                self.reply.emit(my, "", err, "")
        threading.Thread(target=work, daemon=True).start()

    def edit_knowledge(self):
        from ..knowledge_dialog import KnowledgeDialog
        KnowledgeDialog(self.app.config, self).exec()

    def stop(self):
        """Yanıtı durdurur. İstek arka planda bitse bile sonucu gösterilmez."""
        if not self.busy:
            return
        self.gen += 1
        self._set_busy(False)
        self.app.esplora_history.append({"role": "assistant", "content": t("Yanıt durduruldu."), "stopped": True,
                                         "time": datetime.now().strftime("%H:%M")})
        self.render()

    def retry(self):
        """Son kullanıcı sorusundan sonraki yanıt(lar)ı silip soruyu yeniden gönderir."""
        if self.busy:
            return
        self.pending = None
        self.rounds = 0
        hist = self.app.esplora_history
        last_q = max((i for i, m in enumerate(hist) if m["role"] == "user" and not m.get("cmd") and not m.get("data")),
                     default=None)
        if last_q is None:
            return
        del hist[last_q + 1:]
        self._request()

    def _on_reply(self, gen, text, err, new_model):
        if gen != self.gen:                 # durdurulmuş ya da eski istek
            return
        self._set_busy(False)
        now = datetime.now().strftime("%H:%M")
        self.on_show()          # model değişmiş, durum değişmiş olabilir
        if err:
            self.app.esplora_history.append({"role": "assistant", "content": err, "error": True, "time": now})
            self.render()
            return
        self.app.esplora_history.append({"role": "assistant", "content": text, "time": now})
        reqs = EA.parse_requests(text)
        if reqs and self.rounds < MAX_ROUNDS:
            self.rounds += 1
            self._handle_requests(reqs)
            return
        self.render()

    # --- veri istekleri ---
    def _handle_requests(self, reqs):
        """İzinlere göre: kapalı -> reddedilir, onaysız -> getirilir, onaylı -> sohbette sorulur."""
        lv = EA.levels(self.app.config)
        ask = [(k, a) for k, a in reqs if lv.get(k) == "ask"]
        if ask:
            self.pending = {"reqs": reqs, "ask": ask, "gen": self.gen}
            self.render()
            return
        self._fetch(reqs, approved=set())

    def decide(self, choice):
        """choice: allow | deny | always"""
        p, self.pending = self.pending, None
        if not p:
            return
        if choice == "always":
            for k, _a in p["ask"]:
                EA.set_level(self.app.config, k, "allow")
        approved = set(p["ask"]) if choice in ("allow", "always") else set()
        self._fetch(p["reqs"], approved)

    def _fetch(self, reqs, approved):
        self.gen += 1
        my = self.gen
        self._set_busy(True)
        self.render(thinking=True)
        lv = EA.levels(self.app.config)
        app = self.app

        def work():
            results = []
            for k, a in reqs:
                level = lv.get(k, "off")
                if level == "off":
                    results.append((k, a, None, "off"))
                elif level == "ask" and (k, a) not in approved:
                    results.append((k, a, None, "denied"))
                else:
                    try:
                        results.append((k, a, EA.fetch(app, k, a), "ok"))
                    except Exception as e:
                        msg = t(e.template, **e.kw) if hasattr(e, "template") else str(e)
                        results.append((k, a, msg, "error"))
            self.fetched.emit(my, results)
        threading.Thread(target=work, daemon=True).start()

    def _on_fetched(self, gen, results):
        if gen != self.gen:
            return
        now = datetime.now().strftime("%H:%M")
        given = [t(EA.ITEMS[k][0]) + (f" ({a})" if a else "") for k, a, _x, st in results if st == "ok"]
        refused = [t(EA.ITEMS[k][0]) + (f" ({a})" if a else "") for k, a, _x, st in results if st in ("denied", "off")]
        note = []
        if given:
            note.append(t("Esplora'ya verilen veri: {items}", items=", ".join(given)))
        if refused:
            note.append(t("Verilmeyen: {items}", items=", ".join(refused)))
        self.app.esplora_history.append({"role": "user", "content": EA.data_message(results), "data": True,
                                         "label": "📎 " + " · ".join(note or [t("Veri isteği yanıtlandı.")]),
                                         "time": now})
        self._set_busy(False)
        self._request()

    def apply_setting(self, key, value, btn=None):
        if self.read_only():
            return
        if EA.level(self.app.config, "settings.write") == "off":
            self.warn("Ayar değiştirme Veri İzinleri'nde kapalı.")
            return
        props = self.app.properties
        if not props.exists:
            self.warn("server.properties bulunamadı.")
            return
        old = props.load().get(key)
        props.save({key: value})
        if btn is not None:
            btn.setEnabled(False)
            btn.setText(t("Uygulandı"))
        self.app.esplora_history.append({"role": "assistant", "note": True, "time": datetime.now().strftime("%H:%M"),
                                         "content": t("server.properties: {key} {old} → {new} (sunucu yeniden başlatılınca geçerli olur)",
                                                      key=key, old=old if old is not None else "—", new=value)})
        self.render()

    def _new_canvas(self):
        inner = QWidget()
        inner.setObjectName("Canvas")
        inner.setStyleSheet("QWidget#Canvas { background: transparent; }")
        self.chat = QVBoxLayout(inner)
        self.chat.setContentsMargins(16, 16, 16, 16)
        self.chat.setSpacing(10)
        self.chat.addStretch(1)
        self.scroll.setWidget(inner)          # eski tuval ve balonları Qt siler

    def _add(self, w, right):
        line = QWidget()
        h = QHBoxLayout(line)
        h.setContentsMargins(0, 0, 0, 0)
        if right != is_rtl():
            h.addStretch(1)
            h.addWidget(w)
        else:
            h.addWidget(w)
            h.addStretch(1)
        self.chat.addWidget(line)

    def _actions(self, msg):
        """Son yanıtın altındaki küçük düğmeler: yeniden oluştur, kopyala."""
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(4, 0, 0, 0)
        h.setSpacing(4)
        rb = button("Yeniden oluştur", "flat", self.retry)
        rb.setIcon(icons.icon("rotate-ccw", TOKENS["text_muted"], 13))
        h.addWidget(rb)
        if not msg.get("error") and not msg.get("stopped"):
            def copy():
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().setText(msg["content"])
                cb.setText(t("Kopyalandı"))
                cb.setIcon(icons.icon("check", TOKENS["accent"], 13))
            cb = button("Kopyala", "flat", copy)
            cb.setIcon(icons.icon("copy", TOKENS["text_muted"], 13))
            h.addWidget(cb)
        for b in bar.findChildren(QPushButton):
            b.setStyleSheet(f"color:{TOKENS['text_muted']}; font-size:8.5pt; padding:3px 8px;")
        return bar

    def render(self, thinking=False):
        self._new_canvas()
        hist = self.app.esplora_history
        if not hist:
            hello = (t("Merhaba! Ben Esplora. Bu sunucunun ayarları, eklentileri, performansı ve oyuncuları hakkında sorabilirsin. "
                       "Önerdiğim komutları ▶ Çalıştır ile gönderebilirsin; güvenli mod kuralları geçerlidir.").replace("▶ ", "")
                     + "\n\n" + t("Neler sorabilirsin:") + "\n"
                     + "- " + t("**Performans:** kasma nedenleri, RAM, görüş mesafesi, Paper/Purpur ayarları") + "\n"
                     + "- " + t("**Hatalar:** son hatalar, çökme raporları, açılmayan sunucu, Java uyumu") + "\n"
                     + "- " + t("**Oyuncular:** günlük özet, şüpheli davranış, whitelist, op yetkileri") + "\n"
                     + "- " + t("**Eklentiler ve modlar:** değerlendirme, öneriler, çakışmalar, dil dosyaları") + "\n"
                     + "- " + t("**Güvenlik ve yedek:** güvenlik kontrolü, yedekleme planı, griefing sonrası") + "\n\n"
                     + t("Aşağıdaki hızlı sorulara ya da “Tüm hazır sorular” menüsüne tıklayabilirsin."))
            self._add(Bubble(self, "assistant", hello), right=False)
        today = datetime.now().strftime("%Y-%m-%d")

        def when(m):
            d = m.get("date")
            if d and d != today and len(d) == 10:
                return f"{d[8:10]}.{d[5:7]}.{d[:4]} {m.get('time', '')}".strip()
            return m.get("time", "")
        for i, m in enumerate(hist):
            if m.get("data") or m.get("note"):
                self._add(Bubble(self, "note", m.get("label") or m["content"], when(m)), right=False)
                continue
            if m["role"] == "user":
                role = "user"
            else:
                role = "error" if m.get("error") else "stopped" if m.get("stopped") else "assistant"
            self._add(Bubble(self, role, m.get("label") or m["content"], when(m), m.get("images")),
                      right=(role == "user"))
            if i == len(hist) - 1 and m["role"] == "assistant" and not thinking and not self.pending:
                self._add(self._actions(m), right=False)
        if self.pending and not thinking:
            self._add(self._approval(self.pending), right=False)
        self._persist()
        self.thinking = None
        if thinking:
            self.thinking = Bubble(self, "thinking", "")
            self._add(self.thinking, right=False)
            self._n = 0
            self._dots.start(400)
        else:
            self._dots.stop()

    def _approval(self, p):
        """Esplora'nın "Onaylı" verileri isteği: İzin ver / Reddet / Hep izin ver."""
        box = QFrame()
        box.setObjectName("Bubble")
        box.setStyleSheet(f"QFrame#Bubble {{ background:{rgba(TOKENS['warn'], 30)}; border:1px solid {rgba(TOKENS['warn'], 110)};"
                          f" border-radius:14px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(6)
        head = QLabel(f'<span style="color:{TOKENS["warn"]}; font-weight:700;">{html.escape(t("Esplora veri istiyor"))}</span>')
        v.addWidget(head)
        for k, a in p["ask"]:
            lab = QLabel("• " + t(EA.ITEMS[k][0]) + (f" — {a}" if a else ""))
            lab.setStyleSheet("background:transparent;")
            v.addWidget(lab)
        note = QLabel(t("Bu veriler seçtiğin yapay zeka sağlayıcısına gönderilir."))
        note.setStyleSheet(f"color:{TOKENS['text_muted']}; background:transparent;")
        v.addWidget(note)
        v.addLayout(row(button("İzin ver", "primary", lambda: self.decide("allow")),
                        button("Reddet", "ghost", lambda: self.decide("deny")),
                        button("Hep izin ver", "ghost", lambda: self.decide("always"),
                               tooltip="Bu veri türleri bundan sonra sormadan verilir (Veri İzinleri'nden değiştirilebilir)"),
                        None))
        return box

    def _tick(self):
        if self.thinking is not None:
            self._n = (self._n + 1) % 4
            self.thinking.dots.setText(t("düşünüyor…").rstrip("…. ") + "." * self._n)

    def run(self, cmd):
        if not self.app.server.is_running:
            self.warn("Sunucu kapalı iken komut gönderilemez!")
            return
        if send_guarded(self, self.app, cmd):
            self.app.esplora_history.append({"role": "user", "content": f"/{cmd}  — " + t("çalıştırıldı"), "cmd": True,
                                             "time": datetime.now().strftime("%H:%M")})
            self.render()
