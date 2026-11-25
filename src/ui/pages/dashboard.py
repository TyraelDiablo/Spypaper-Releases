from collections import deque
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QVBoxLayout

from core import N_
from core.logwatch import KINDS, hourly_counts, online_timeline, sessions
from ..charts import BarChart, LineChart
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, label, segmented

def kind_color(k):
    return {
        "join": TOKENS["accent"], "leave": TOKENS["text_muted"], "chat": TOKENS["text"],
        "death": TOKENS["danger"], "adv": TOKENS["warn"], "cmd": TOKENS["info"],
        "lag": TOKENS["warn"], "warn": TOKENS["warn"], "error": TOKENS["danger"],
        "start": TOKENS["accent"], "stop": TOKENS["danger"], "info": TOKENS["text_muted"],
    }[k]
FEED_KINDS = {"join", "leave", "chat", "death", "adv", "cmd", "start", "stop", "error"}
GUN = [N_("Pzt"), N_("Sal"), N_("Çar"), N_("Per"), N_("Cum"), N_("Cmt"), N_("Paz")]


def fmt_dur(sec):
    sec = int(sec)
    h, m = divmod(sec // 60, 60)
    d, h = divmod(h, 24)
    if d:
        return t("{d}g {h}sa", d=d, h=h)
    return t("{h}sa {m}dk", h=h, m=m) if h else t("{m}dk", m=m)


def event_text(e, app=None):
    """Olayın gösterilecek metni. app verilirse ve log çevirisi açıksa oyunun dil dosyasıyla çevrilir."""
    if app is not None and e.kind not in ("chat", "cmd") and app.config.settings.get("translate_logs"):
        msg = e.raw.split("]: ", 1)[1] if "]: " in e.raw else e.text
        tr = app.logtrans.message(msg)
        if tr != msg:
            return tr
    if e.kind == "chat":
        return f"<{e.player}> {e.text}"
    if e.kind == "cmd":
        return f"{e.player}: {e.text}"
    if e.kind == "adv":
        return t("{player} başarım: {adv}", player=e.player, adv=e.text)
    return e.text


class StatCard(Card):
    def __init__(self, title, accent=None):
        super().__init__()
        self.body.setSpacing(2)
        self.body.setContentsMargins(16, 12, 16, 12)
        self.add(label(title, "Muted"))
        self.value = self.add(label("–", "BigValue"))
        if accent:
            self.value.setStyleSheet(f"color:{accent}")
        self.sub = self.add(label("", "Muted"))

    def set(self, value, sub=""):
        self.value.setText(str(value))
        self.sub.setText(sub)


# Panel Düzeni penceresinde gizlenebilen kartlar (anahtar, başlık)
DASH_CARDS = [
    ("online", N_("Çevrimiçi")), ("joins", N_("Bugün Giren")), ("deaths", N_("Bugün Ölüm")),
    ("chat", N_("Sohbet Mesajı")), ("lag", N_("Gecikme Uyarısı")), ("uptime", N_("Çalışma Süresi")),
    ("online_chart", N_("Çevrimiçi Oyuncular")), ("feed", N_("Son Olaylar")), ("hourly", N_("Saatlik Etkinlik")),
    ("week", N_("Son 7 Gün")), ("resources", N_("Sunucu Kaynakları")), ("perf", N_("Performans (TPS / MSPT)")),
    ("top", N_("En çok oynayanlar")),
]


def tps_color(tps):
    if tps is None:
        return TOKENS["text_muted"]
    return TOKENS["accent"] if tps >= 19 else TOKENS["warn"] if tps >= 15 else TOKENS["danger"]


def mspt_color(ms):
    if ms is None:
        return TOKENS["text_muted"]
    return TOKENS["accent"] if ms < 40 else TOKENS["warn"] if ms <= 50 else TOKENS["danger"]


class DashboardPage(Page):
    title = "Dashboard"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.metric_hist = deque(maxlen=300)   # 2 sn × 300 = 10 dk
        self._gen = None
        self._fed = 0

        # --- üst kartlar ---
        cards = QGridLayout()
        cards.setSpacing(14)
        self.c_online = StatCard("Çevrimiçi", TOKENS["accent"])
        self.c_players = StatCard("Bugün Giren")
        self.c_deaths = StatCard("Bugün Ölüm", TOKENS["danger"])
        self.c_chat = StatCard("Sohbet Mesajı")
        self.c_lag = StatCard("Gecikme Uyarısı", TOKENS["warn"])
        self.c_uptime = StatCard("Çalışma Süresi")
        for i, c in enumerate((self.c_online, self.c_players, self.c_deaths, self.c_chat, self.c_lag, self.c_uptime)):
            cards.addWidget(c, 0, i)
        self.root.addLayout(cards)

        # --- orta: çevrimiçi grafiği + son olaylar ---
        mid = QHBoxLayout()
        mid.setSpacing(14)
        oc = Card("Çevrimiçi Oyuncular", "Bugün · log'daki giriş/çıkışlardan")
        self.online_chart = LineChart(TOKENS["accent"], step=True)
        oc.add(self.online_chart, 1)
        mid.addWidget(oc, 3)

        feed = Card("Son Olaylar")
        self.feed = QListWidget()
        self.feed.setWordWrap(True)
        feed.add(self.feed, 1)
        mid.addWidget(feed, 2)
        self.root.addLayout(mid, 3)

        # --- alt: saatlik + 7 gün + kaynak ---
        bot = QHBoxLayout()
        bot.setSpacing(14)
        hc = Card("Saatlik Etkinlik", "Giriş, sohbet, ölüm, başarım, komut")
        self.hour_chart = BarChart(TOKENS["info"])
        hc.add(self.hour_chart, 1)
        bot.addWidget(hc, 2)

        wc = Card("Son 7 Gün", "Tekil oyuncu sayısı")
        self.week_chart = BarChart(TOKENS["purple"])
        wc.add(self.week_chart, 1)
        bot.addWidget(wc, 2)

        rc = Card("Sunucu Kaynakları", "Son 10 dakika · RAM")
        self.ram_chart = LineChart(TOKENS["warn"], y_fmt=lambda v: f"{v:g}G")
        self.ram_chart.integer = False
        self.res_lbl = label("", "Muted")
        rc.add(self.ram_chart, 1)
        rc.add(self.res_lbl)
        bot.addWidget(rc, 2)

        pc = Card("Performans", "Dakikada bir · 8 gün")
        pc.setToolTip(t("20 TPS ve 50 ms altı MSPT sağlıklıdır. Geçmiş panel kapalıyken de kaydedilir."))
        self.perf_mode = segmented(["TPS", "MSPT", "RAM", "CPU", "Oyuncu"], lambda _i: self.update_perf())
        self.perf_range = segmented(["1 sa", "24 sa", "7 gün"], lambda _i: self.update_perf())
        pc.header_actions.addWidget(self.perf_range)
        pc.header_actions.addWidget(self.perf_mode)
        self.perf_chart = LineChart(TOKENS["accent"])
        self.perf_chart.integer = False
        pc.add(self.perf_chart, 1)
        self.perf_lbl = label("", "Muted")
        self.perf_lbl.setTextFormat(Qt.RichText)
        self.perf_on = QCheckBox(t("TPS ölçümü"))
        self.perf_on.setToolTip(t("Spypaper sunucuya 15 saniyede bir tps/mspt (ya da tick query) komutunu gönderir; "
                                  "yanıtlar konsolda gösterilmez ama sunucunun latest.log dosyasına yazılır."))
        self.perf_on.setCursor(Qt.PointingHandCursor)
        self.perf_on.setChecked(app.perf.enabled)
        self.perf_on.toggled.connect(self._perf_toggled)
        perf_row = QHBoxLayout()
        perf_row.addWidget(self.perf_lbl, 1)
        perf_row.addWidget(self.perf_on)
        pc.add(perf_row)
        bot.addWidget(pc, 2)
        self.root.addLayout(bot, 2)

        # --- en çok oynayanlar ---
        self.top_lbl = label("", "Muted")
        self.top_lbl.setTextFormat(Qt.RichText)
        self.root.addWidget(self.top_lbl)

        hidden = set(app.config.settings.get("dashboard_hidden") or [])
        widgets = {"online": self.c_online, "joins": self.c_players, "deaths": self.c_deaths, "chat": self.c_chat,
                   "lag": self.c_lag, "uptime": self.c_uptime, "online_chart": oc, "feed": feed, "hourly": hc,
                   "week": wc, "resources": rc, "perf": pc, "top": self.top_lbl}
        for key, w in widgets.items():
            if key in hidden:
                w.setVisible(False)
                w.setProperty("user_hidden", True)

        bridge.events.connect(self.on_events)
        self.mtimer = QTimer(self)
        self.mtimer.timeout.connect(self.sample_metrics)
        self.mtimer.start(2000)
        self.slow = QTimer(self)                 # 7 gün grafiği arşivleri okur, seyrek yenilenir
        self.slow.timeout.connect(self.update_week)
        self.slow.start(5 * 60 * 1000)
        if not app.metrics.available:
            self.res_lbl.setText(t("RAM/CPU için psutil gerekli (calistir.bat ile kurulur)"))

    def on_show(self):
        self.refresh()
        self.update_week()
        self.update_perf()

    def on_server_path_changed(self):
        self.metric_hist.clear()
        self.on_show()

    def on_events(self, new):
        if self.isVisible():
            self.refresh()

    # --- çizim ---
    def refresh(self):
        evs = self.app.logs.events
        today = date.today()
        now = datetime.now()
        todays = [e for e in evs if e.time.date() == today]

        tl, online = online_timeline(evs)
        peak = max([c for tm, c in tl if tm.date() == today] + [len(online)])
        self.c_online.set(len(online), t("Bugün en yüksek: {n}", n=peak))
        joined = {e.player for e in todays if e.kind == "join"}
        self.c_players.set(len(joined), t("{n} giriş", n=sum(e.kind == 'join' for e in todays)))
        self.c_deaths.set(sum(e.kind == "death" for e in todays))
        self.c_chat.set(sum(e.kind == "chat" for e in todays), t("{n} komut", n=sum(e.kind == 'cmd' for e in todays)))
        lags = [e for e in todays if e.kind == "lag"]
        self.c_lag.set(len(lags), t("son: {time}", time=f"{lags[-1].time:%H:%M}") if lags else t("sorun yok"))
        starts = [e for e in evs if e.kind == "start"]
        running = self.app.server.is_running or (starts and not any(e.kind == "stop" and e.time > starts[-1].time for e in evs))
        if running and starts:
            self.c_uptime.set(fmt_dur((now - starts[-1].time).total_seconds()), t("başlangıç {time}", time=f"{starts[-1].time:%H:%M}"))
        else:
            self.c_uptime.set(t("Kapalı"), "")

        # çevrimiçi grafiği: bugün 00:00 → şimdi (saat cinsinden x)
        day0 = datetime.combine(today, datetime.min.time())
        start_count = 0
        pts = []
        for tm, c in tl:
            if tm < day0:
                start_count = c
            else:
                pts.append(((tm - day0).total_seconds() / 3600, c))
        pts = [(0.0, start_count)] + pts + [((now - day0).total_seconds() / 3600, len(online))]
        self.online_chart.set_data(pts, (0, max(1.0, pts[-1][0])),
                                   lambda x: f"{int(x):02}:{int((x % 1) * 60):02}")

        hc = hourly_counts(evs, today)
        self.hour_chart.set_data([f"{h:02}" for h in range(24)], hc, highlight=now.hour, label_every=3,
                                 tips=[f"{h:02}:00 – {h:02}:59 · " + t("{n} olay", n=v) for h, v in enumerate(hc)])

        # son olaylar
        if self._gen != self.app.logs.generation:
            self._gen = self.app.logs.generation
            self.feed.clear()
            self._fed = 0
        feed_new = [e for e in evs[self._fed:] if e.kind in FEED_KINDS]
        self._fed = len(evs)
        for e in feed_new[-60:]:
            it = QListWidgetItem(f"{e.time:%H:%M}   {t(KINDS[e.kind]):<8}  {event_text(e, self.app)}")
            it.setForeground(QColor(kind_color(e.kind)))
            self.feed.insertItem(0, it)
        while self.feed.count() > 60:
            self.feed.takeItem(self.feed.count() - 1)

        # en çok oynayanlar (bugün)
        top = sorted(sessions(todays, now).items(), key=lambda x: -x[1])[:5]
        if top:
            parts = [f'<b style="color:{TOKENS["text"]}">{n}</b> {fmt_dur(s)}' for n, s in top]
            self.top_lbl.setText(t("En çok oynayanlar (bugün):") + "  " + "   ·   ".join(parts))
        else:
            self.top_lbl.setText("")

    def update_week(self):
        hist = self.app.logs.daily_history(7)
        self.week_chart.set_data(
            [t(GUN[d.weekday()]) for d, *_ in hist], [u for _, u, _, _ in hist], highlight=len(hist) - 1,
            tips=[f"{d:%d.%m} · " + t("{u} oyuncu · {j} giriş · {dd} ölüm", u=u, j=j, dd=dt) for d, u, j, dt in hist])

    # --- performans ---
    def _perf_toggled(self, on):
        if self.read_only():
            self.perf_on.blockSignals(True)
            self.perf_on.setChecked(not on)
            self.perf_on.blockSignals(False)
            return
        self.app.perf.set_enabled(on)
        self.update_perf()

    PERF_KEYS = ("tps", "mspt", "ram", "cpu", "players")

    def update_perf(self):
        from core.perfhist import summary
        perf = self.app.perf
        mode = max(0, self.perf_mode.group.checkedId())
        rng = max(0, self.perf_range.group.checkedId())
        hours = (1, 24, 168)[rng]
        key = self.PERF_KEYS[mode]
        now = datetime.now()
        start = now - timedelta(hours=hours)
        if rng == 0 and mode < 2:                      # son 1 saat TPS/MSPT: 15 saniyelik canlı ölçüm
            raw = [(s[0], s[mode + 1]) for s in perf.samples if s[0] >= start and s[mode + 1] is not None]
        else:
            raw = [(tm, v[key]) for tm, v in self.app.perfhist.load(hours, now) if v.get(key) is not None]
        if key == "ram":
            raw = [(tm, v / 1024) for tm, v in raw]
        bucket = max(1, len(raw) // 360)               # uzun aralıkta ortalama alınarak seyreltilir
        pts = []
        for i in range(0, len(raw), bucket):
            part = raw[i:i + bucket]
            tm = part[len(part) // 2][0]
            pts.append(((tm - start).total_seconds() / 60, sum(v for _, v in part) / len(part)))
        colors = (TOKENS["accent"], TOKENS["info"], TOKENS["warn"], TOKENS["purple"], TOKENS["accent"])
        self.perf_chart.color = QColor(colors[mode])
        self.perf_chart.y_min_max = (20, 50, 1, 100, 1)[mode]
        self.perf_chart.integer = mode == 4
        self.perf_chart.step = mode == 4
        self.perf_chart.y_fmt = ((lambda v: f"{v:g}"), (lambda v: f"{v:g}ms"), (lambda v: f"{v:g}G"),
                                 (lambda v: f"%{v:g}"), (lambda v: f"{v:g}"))[mode]
        fmt = "%H:%M" if hours <= 24 else "%d.%m %H:%M"
        self.perf_chart.set_data(pts, (0, hours * 60), lambda x: (start + timedelta(minutes=x)).strftime(fmt))
        sm = summary([(tm, {key: v}) for tm, v in raw], key) if raw else None
        self._perf_summary = sm
        last = perf.latest()
        if perf.status == "ok" and last and (last[1] is not None or last[2] is not None):
            tps, ms = last[1], last[2]
            parts = []
            if tps is not None:
                parts.append(f'<b style="color:{tps_color(tps)}">TPS {tps:.1f}</b>')
            if ms is not None:
                parts.append(f'<b style="color:{mspt_color(ms)}">MSPT {ms:.1f} ms</b>')
            sm = self._perf_summary
            self.perf_lbl.setToolTip(t("Seçili aralıkta en düşük / ortalama / en yüksek: {a} / {b} / {c}",
                                       a=f"{sm[0]:.1f}", b=f"{sm[1]:.1f}", c=f"{sm[2]:.1f}") if sm else "")
            self.perf_lbl.setText("  ·  ".join(parts))
        else:
            from core.perf import STATUS
            self.perf_lbl.setToolTip("")
            self.perf_lbl.setWordWrap(True)
            self.perf_lbl.setText(t(STATUS.get(perf.status, STATUS["waiting"])))

    def sample_metrics(self):
        self.update_perf()
        s = self.app.metrics.sample()
        if not s:
            if self.app.metrics.available:
                self.res_lbl.setText(t("Sunucu süreci bulunamadı"))
            return
        ram, cpu, _ = s
        self.metric_hist.append((datetime.now(), ram / 1024))
        t0 = self.metric_hist[0][0]
        pts = [((tm - t0).total_seconds(), v) for tm, v in self.metric_hist]
        self.ram_chart.y_min_max = 1
        self.ram_chart.set_data(pts, (0, max(60.0, pts[-1][0])),
                                lambda x: (t0 + timedelta(seconds=x)).strftime("%H:%M"))
        self.res_lbl.setText(f"RAM {ram / 1024:.2f} GB  ·  CPU %{cpu:.0f}")
