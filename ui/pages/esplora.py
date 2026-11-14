"""Esplora — yapay zeka asistanı sayfası (mesaj balonlu sohbet)."""
import html
import re
import threading
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from core import N_, ai, detect_version
from core.esplora import build_system, latest_crash, preset_items, quick_items
from ..i18n import current, is_rtl, t
from ..theme import TOKENS, rgba
from ..widgets import Card, Page, button, label, row, send_guarded

LANG_EN = {
    "tr": "Turkish", "en": "English", "de": "German", "fr": "French", "es": "Spanish",
    "pt_BR": "Brazilian Portuguese", "it": "Italian", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "uk": "Ukrainian", "az": "Azerbaijani", "ja": "Japanese", "ko": "Korean", "zh_CN": "Simplified Chinese",
    "ar": "Arabic",
}
BLOCK = re.compile(r"```(\w*)\s*\n(.*?)```", re.S)


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
        else:
            parts.append(("code", body.rstrip()))
        pos = m.end()
    if text[pos:].strip():
        parts.append(("text", _inline(text[pos:])))
    return parts


class Bubble(QFrame):
    """Tek bir mesaj balonu. role: user | assistant | error | thinking"""

    def __init__(self, page, role, text, when=""):
        super().__init__()
        self.page = page
        k = TOKENS
        bg = {"user": rgba(k["accent"], 38), "assistant": k["surface_2"], "stopped": "transparent",
              "error": rgba(k["danger"], 40), "thinking": k["surface_2"]}[role]
        border = {"user": rgba(k["accent"], 90), "error": rgba(k["danger"], 110)}.get(role, k["border"])
        self.setObjectName("Bubble")
        self.setStyleSheet(f"QFrame#Bubble {{ background:{bg}; border:1px solid {border}; border-radius:14px; }}")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(6)

        who = {"user": t("Sen")}.get(role, "Esplora")
        color = {"user": k["accent"], "error": k["danger"], "stopped": k["text_muted"]}.get(role, k["info"])
        head = QLabel(f'<span style="color:{color}; font-weight:700;">{html.escape(who)}</span>'
                      + (f'&nbsp;&nbsp;<span style="color:{k["text_muted"]}; font-size:8pt;">{when}</span>' if when else ""))
        v.addWidget(head)

        if role == "thinking":
            self.dots = QLabel(t("düşünüyor…"))
            self.dots.setStyleSheet(f"color:{k['text_muted']};")
            v.addWidget(self.dots)
            return
        if role == "stopped":
            lbl = self._text("⏹ " + html.escape(text))
            lbl.setStyleSheet(f"color:{k['text_muted']}; font-style: italic; background: transparent;")
            v.addWidget(lbl)
            return
        if role in ("user", "error"):
            v.addWidget(self._text(_inline(text)))
            return
        for kind, val in split_message(text):
            if kind == "text":
                v.addWidget(self._text(val))
            elif kind == "code":
                c = self._text(f'<pre style="margin:0;">{html.escape(val)}</pre>')
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
            b = QPushButton("▶ " + t("Çalıştır"))
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

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        if not hasattr(app, "esplora_history"):
            app.esplora_history = []          # arayüz yeniden kurulsa da kalır
        self.busy = False

        head = Card("Esplora", "Bu sunucuya özel yapay zeka asistanı. Yalnızca sunucu yönetimiyle ilgili sorulara yanıt verir.")
        head.header_actions.addWidget(button("Yeni sohbet", "ghost", self.reset))
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

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(t("Esplora'ya sor… (Ctrl+Enter ile gönder)"))
        self.input.setFixedHeight(70)
        self.input.keyPressEvent = self._key
        self.gen = 0                         # her istekte artar; durdurulan isteğin geç gelen yanıtı yok sayılır
        self.send_btn = button("Gönder", "primary", self._send_or_stop)
        self.root.addLayout(row(self.input, self.send_btn, stretch_end=False))
        self.reply.connect(self._on_reply)
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
        self.chips.addWidget(button("Tüm hazır sorular ▾", "flat", self._preset_menu,
                                    tooltip="Kategorilere ayrılmış hazır sorular"))

    def _preset_menu(self):
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for icon, cat, items in preset_items(self.flags or self._flags()):
            sub = m.addMenu(f"{icon}  {t(cat)}")
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

    def _key(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.ask(self.input.toPlainText())
        else:
            QPlainTextEdit.keyPressEvent(self.input, e)

    def open_settings(self):
        from ..ai_dialog import AIDialog
        AIDialog(self.app.config.settings, self).exec()
        self.on_show()

    def reset(self):
        self.app.esplora_history.clear()
        self.render()

    # --- bağlam ---
    def context(self):
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
        if not text or self.busy:
            return
        if label is None:
            self.input.clear()
        msg = {"role": "user", "content": text, "time": datetime.now().strftime("%H:%M")}
        if label:
            msg["label"] = label
        self.app.esplora_history.append(msg)
        self._request()

    @staticmethod
    def _api_messages(hist):
        """Hata/durdurma balonlarını çıkarır, art arda gelen aynı rolleri birleştirir (bazı API'ler ister)."""
        out = []
        for m in hist[-24:]:
            if m.get("error") or m.get("stopped"):
                continue
            if out and out[-1]["role"] == m["role"]:
                out[-1]["content"] += "\n\n" + m["content"]
            else:
                out.append({"role": m["role"], "content": m["content"]})
        while out and out[0]["role"] != "user":
            out.pop(0)
        return out

    def _request(self):
        self.gen += 1
        my = self.gen
        self._set_busy(True)
        self.render(thinking=True)
        settings = self.app.config.settings
        system = build_system(self.context(), LANG_EN.get(current(), "English"))
        msgs = self._api_messages(self.app.esplora_history)

        def work():
            try:
                out, new = ai.chat_auto(settings, system, msgs)
                self.reply.emit(my, out, "", new or "")
            except Exception as e:
                err = t(e.template, **e.kw) if hasattr(e, "template") else str(e)
                self.reply.emit(my, "", err, "")
        threading.Thread(target=work, daemon=True).start()

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
        hist = self.app.esplora_history
        last_q = max((i for i, m in enumerate(hist) if m["role"] == "user" and not m.get("cmd")), default=None)
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
        else:
            self.app.esplora_history.append({"role": "assistant", "content": text, "time": now})
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
        rb = button("↻ " + t("Yeniden oluştur"), "flat", self.retry)
        h.addWidget(rb)
        if not msg.get("error") and not msg.get("stopped"):
            def copy():
                from PySide6.QtWidgets import QApplication
                QApplication.clipboard().setText(msg["content"])
                cb.setText("✓ " + t("Kopyalandı"))
            cb = button("⧉ " + t("Kopyala"), "flat", copy)
            h.addWidget(cb)
        for b in bar.findChildren(QPushButton):
            b.setStyleSheet(f"color:{TOKENS['text_muted']}; font-size:8.5pt; padding:3px 8px;")
        return bar

    def render(self, thinking=False):
        self._new_canvas()
        hist = self.app.esplora_history
        if not hist:
            hello = (t("Merhaba! Ben Esplora. Bu sunucunun ayarları, eklentileri, performansı ve oyuncuları hakkında sorabilirsin. "
                       "Önerdiğim komutları ▶ Çalıştır ile gönderebilirsin; güvenli mod kuralları geçerlidir.")
                     + "\n\n" + t("Neler sorabilirsin:") + "\n"
                     + "- " + t("**Performans:** kasma nedenleri, RAM, görüş mesafesi, Paper/Purpur ayarları") + "\n"
                     + "- " + t("**Hatalar:** son hatalar, çökme raporları, açılmayan sunucu, Java uyumu") + "\n"
                     + "- " + t("**Oyuncular:** günlük özet, şüpheli davranış, whitelist, op yetkileri") + "\n"
                     + "- " + t("**Eklentiler ve modlar:** değerlendirme, öneriler, çakışmalar, dil dosyaları") + "\n"
                     + "- " + t("**Güvenlik ve yedek:** güvenlik kontrolü, yedekleme planı, griefing sonrası") + "\n\n"
                     + t("Aşağıdaki hızlı sorulara ya da “Tüm hazır sorular” menüsüne tıklayabilirsin."))
            self._add(Bubble(self, "assistant", hello), right=False)
        for i, m in enumerate(hist):
            if m["role"] == "user":
                role = "user"
            else:
                role = "error" if m.get("error") else "stopped" if m.get("stopped") else "assistant"
            self._add(Bubble(self, role, m.get("label") or m["content"], m.get("time", "")), right=(role == "user"))
            if i == len(hist) - 1 and m["role"] == "assistant" and not thinking:
                self._add(self._actions(m), right=False)
        self.thinking = None
        if thinking:
            self.thinking = Bubble(self, "thinking", "")
            self._add(self.thinking, right=False)
            self._n = 0
            self._dots.start(400)
        else:
            self._dots.stop()

    def _tick(self):
        if self.thinking is not None:
            self._n = (self._n + 1) % 4
            self.thinking.dots.setText(t("düşünüyor…").rstrip("…. ") + "." * self._n)

    def run(self, cmd):
        if not self.app.server.is_running:
            self.warn("Sunucu kapalı iken komut gönderilemez!")
            return
        if send_guarded(self, self.app, cmd):
            self.app.esplora_history.append({"role": "user", "content": f"/{cmd}  ✓ " + t("çalıştırıldı"), "cmd": True,
                                             "time": datetime.now().strftime("%H:%M")})
            self.render()
