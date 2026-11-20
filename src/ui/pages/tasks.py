"""Zamanlanmış Görevler: yeniden başlatma, durdurma, başlatma, yedek, komut ve duyuru planları.
İş mantığı ve zamanlama core.scheduler'da; görevleri pencerenin saniyelik zamanlayıcısı yürütür."""
from datetime import datetime

from PySide6.QtCore import QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QMenu, QPlainTextEdit,
    QPushButton, QSpinBox, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget,
)

from core import scheduler as sch
from core.config import N_
from .. import icons
from ..i18n import t
from ..widgets import Card, Page, ask, button, label, row, table

DAYS = [N_("Pzt"), N_("Sal"), N_("Çar"), N_("Per"), N_("Cum"), N_("Cmt"), N_("Paz")]


def when_text(task):
    """İnsanın okuyacağı zaman: 'Her gün 04:00', 'Hafta içi 04:00', 'Her 30 dakikada'…"""
    if task["mode"] == "interval":
        n = task["every"]
        if n % 60 == 0:
            return t("Her saat") if n == 60 else t("Her {n} saatte", n=n // 60)
        return t("Her {n} dakikada", n=n)
    days = task["days"]
    if not days:
        return t("Gün seçilmedi")
    if len(days) == 7:
        d = t("Her gün")
    elif days == [0, 1, 2, 3, 4]:
        d = t("Hafta içi")
    elif days == [5, 6]:
        d = t("Hafta sonu")
    else:
        d = ", ".join(t(DAYS[i]) for i in days)
    return f"{d} {task['time']}"


def task_text(task):
    name = task["name"] or t(sch.ACTIONS[task["action"]])
    extra = ""
    if task["action"] == "announce":
        extra = task["message"]
    elif task["action"] == "command":
        lines = [c.strip() for c in task["command"].splitlines() if c.strip()]
        extra = "/" + lines[0] + (f" (+{len(lines) - 1})" if len(lines) > 1 else "") if lines else ""
    elif task["action"] in ("restart", "stop") and task["countdown"]:
        extra = t("geri sayımlı")
    if extra and len(extra) > 48:
        extra = extra[:47] + "…"
    return f"{name} · {extra}" if extra else name


def short_dt(dt):
    now = datetime.now()
    if dt.date() == now.date():
        return t("Bugün {time}", time=f"{dt:%H:%M}")
    if (dt.date() - now.date()).days == 1:
        return t("Yarın {time}", time=f"{dt:%H:%M}")
    return f"{dt:%d.%m %H:%M}"


class TaskDialog(QDialog):
    def __init__(self, task, new=False, parent=None):
        super().__init__(parent)
        self.task = dict(task)
        self.setWindowTitle(t("Görevi Düzenle") if not new else t("Yeni Görev"))
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)
        v.addWidget(label("Görevi Düzenle" if not new else "Yeni Görev", "PageTitle"))

        form = QFormLayout()
        form.setSpacing(9)
        self.action = QComboBox()
        for key, name in sch.ACTIONS.items():
            self.action.addItem(t(name), key)
        self.action.currentIndexChanged.connect(self._sync)
        self.name = QLineEdit()
        self.name.setMaxLength(60)
        self.name.setPlaceholderText(t("İsteğe bağlı, ör. Gece yeniden başlatması"))
        form.addRow(t("İşlem"), self.action)
        form.addRow(t("Ad"), self.name)

        self.mode = QComboBox()
        self.mode.addItem(t("Belirli günlerde ve saatte"), "weekly")
        self.mode.addItem(t("Belli aralıklarla"), "interval")
        self.mode.currentIndexChanged.connect(self._sync)
        form.addRow(t("Zamanlama"), self.mode)

        self.days_box = QWidget()
        dl = QHBoxLayout(self.days_box)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        self.day_btns = []
        for name in DAYS:
            b = QPushButton(t(name))
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.day_btns.append(b)
            dl.addWidget(b)
        dl.addStretch(1)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.lbl_days, self.lbl_time = label("Günler"), label("Saat")
        form.addRow(self.lbl_days, self.days_box)
        form.addRow(self.lbl_time, self.time)

        self.every = QSpinBox()
        self.every.setRange(1, 999)
        self.unit = QComboBox()
        self.unit.addItem(t("dakika"), 1)
        self.unit.addItem(t("saat"), 60)
        self.every_box = QWidget()
        el = QHBoxLayout(self.every_box)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(6)
        el.addWidget(label("Her"))
        el.addWidget(self.every)
        el.addWidget(self.unit)
        el.addStretch(1)
        self.lbl_every = label("Aralık")
        form.addRow(self.lbl_every, self.every_box)

        self.countdown = QCheckBox(t("Oyunculara geri sayım duyurusu yap (10 dk, 5 dk, 1 dk, 10 sn önce)"))
        self.countdown.setCursor(Qt.PointingHandCursor)
        form.addRow("", self.countdown)
        self.message = QLineEdit()
        self.message.setMaxLength(256)
        self.message.setPlaceholderText(t("Oyunculara gidecek mesaj"))
        self.lbl_message = label("Mesaj")
        form.addRow(self.lbl_message, self.message)
        self.command = QPlainTextEdit()
        self.command.setPlaceholderText(t("Her satıra bir komut, ör.\nweather clear\ntime set day"))
        self.command.setFixedHeight(96)
        self.lbl_command = label("Komutlar")
        form.addRow(self.lbl_command, self.command)
        self.enabled = QCheckBox(t("Görev açık"))
        self.enabled.setCursor(Qt.PointingHandCursor)
        form.addRow("", self.enabled)
        v.addLayout(form)
        self.hint = label("", "Muted", wrap=True)
        v.addWidget(self.hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText(t("Kaydet"))
        btns.button(QDialogButtonBox.Ok).setProperty("variant", "primary")
        btns.button(QDialogButtonBox.Cancel).setText(t("İptal"))
        btns.button(QDialogButtonBox.Cancel).setProperty("variant", "ghost")
        btns.accepted.connect(self.validate)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self._load()

    def _load(self):
        tk = self.task
        self.action.setCurrentIndex(max(0, self.action.findData(tk["action"])))
        self.name.setText(tk["name"])
        self.mode.setCurrentIndex(max(0, self.mode.findData(tk["mode"])))
        for i, b in enumerate(self.day_btns):
            b.setChecked(i in tk["days"])
        h, m = (int(x) for x in tk["time"].split(":"))
        self.time.setTime(QTime(h, m))
        n = tk["every"]
        if n % 60 == 0:
            self.unit.setCurrentIndex(1)
            self.every.setValue(n // 60)
        else:
            self.unit.setCurrentIndex(0)
            self.every.setValue(n)
        self.countdown.setChecked(tk["countdown"])
        self.message.setText(tk["message"])
        self.command.setPlainText(tk["command"])
        self.enabled.setChecked(tk["enabled"])
        self._sync()

    def _sync(self):
        act, weekly = self.action.currentData(), self.mode.currentData() == "weekly"
        for w in (self.lbl_days, self.days_box, self.lbl_time, self.time):
            w.setVisible(weekly)
        for w in (self.lbl_every, self.every_box):
            w.setVisible(not weekly)
        self.countdown.setVisible(act in ("restart", "stop"))
        for w in (self.lbl_message, self.message):
            w.setVisible(act == "announce")
        for w in (self.lbl_command, self.command):
            w.setVisible(act == "command")
        hints = {
            "restart": N_("Sunucu kapalıysa görev atlanır. Yeniden başlatma, çökme bekçisini tetiklemez."),
            "stop": N_("Sunucu kapalıysa görev atlanır."),
            "start": N_("Sunucu zaten açıksa görev atlanır."),
            "backup": N_("Sunucu açıksa önce dünya kaydedilir (save-all). Yedek sayısı sınırı burada da geçerlidir."),
            "command": N_("Komutlar güvenli moddan geçer: engellenen komut gönderilmez. Sunucu kapalıysa görev atlanır."),
            "announce": N_("Mesaj oyunculara /say ile gider. Sunucu kapalıysa görev atlanır."),
        }
        self.hint.setText(t(hints[act]) + " " + t("Görevler yalnızca Spypaper açıkken çalışır."))
        self.adjustSize()

    def validate(self):
        from ..msgbox import warning
        act, weekly = self.action.currentData(), self.mode.currentData() == "weekly"
        if weekly and not any(b.isChecked() for b in self.day_btns):
            warning(self, t("Uyarı"), t("En az bir gün seç."))
            return
        every = self.every.value() * self.unit.currentData()
        if not weekly and every < 5:
            warning(self, t("Uyarı"), t("Aralık en az 5 dakika olmalı."))
            return
        if not weekly and every > 24 * 60:
            warning(self, t("Uyarı"), t("Aralık en fazla 24 saat olabilir. Daha seyrek görevler için "
                                        "'Belirli günlerde ve saatte' seç."))
            return
        if act == "announce" and not self.message.text().strip():
            warning(self, t("Uyarı"), t("Duyuru için bir mesaj yaz."))
            return
        if act == "command" and not self.command.toPlainText().strip():
            warning(self, t("Uyarı"), t("En az bir komut yaz."))
            return
        if act == "command":
            from core.safemode import is_dangerous
            risky = [c.strip() for c in self.command.toPlainText().splitlines() if c.strip() and is_dangerous(c)]
            if risky and not ask(self, t("Bu komutlar tehlikeli olarak işaretli ve onay sorulmadan çalışacak:") +
                                 "\n" + "\n".join(risky[:5]) + "\n\n" + t("Kaydedilsin mi?"), t("Onay")):
                return
        self.task.update({
            "action": act, "name": self.name.text().strip(), "mode": self.mode.currentData(),
            "days": [i for i, b in enumerate(self.day_btns) if b.isChecked()],
            "time": self.time.time().toString("HH:mm"), "every": every,
            "countdown": self.countdown.isChecked(), "message": self.message.text().strip(),
            "command": self.command.toPlainText().strip(), "enabled": self.enabled.isChecked(),
        })
        self.accept()


class TasksPage(Page):
    title = "Zamanlanmış Görevler"

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.sched = app.scheduler
        card = Card("Zamanlanmış Görevler",
                    "Belirli saatte yeniden başlatma, yedek, komut ve duyurular. Görevler yalnızca Spypaper açıkken "
                    "çalışır; Spypaper kapalıyken kaçan görevler sonradan çalıştırılmaz.")
        self.btn_add = button("Görev Ekle", "primary", self._add_menu)
        self.btn_add.setIcon(icons.icon("plus", None, 16))
        card.header_actions.addWidget(self.btn_add)
        self.table = table(["Açık", "Görev", "Zaman", "Sonraki çalışma", "Son durum"], stretch_col=4)
        self.table.itemChanged.connect(self._toggled)
        self.table.itemDoubleClicked.connect(lambda _it: self.edit())
        self.table.itemSelectionChanged.connect(self._sel)
        card.add(self.table, 1)
        self.empty = label("Henüz görev yok. Görev Ekle'ye bas ya da hazır şablonlardan birini seç.", "Muted", wrap=True)
        card.add(self.empty)
        self.btn_edit = button("Düzenle", "ghost", self.edit)
        self.btn_run = button("Şimdi Çalıştır", "ghost", self.run_now)
        self.btn_run.setIcon(icons.icon("play", None, 16))
        self.btn_del = button("Sil", "danger", self.delete)
        card.add(row(self.btn_edit, self.btn_run, None, self.btn_del, stretch_end=False))
        self.root.addWidget(card, 1)

        self._filling = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        bridge.state.connect(lambda _s: self.refresh() if self.isVisible() else None)

    def on_show(self):
        self.refresh()
        self.timer.start(5000)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    # ------------------------------------------------------------------ tablo
    def _selected(self):
        r = self.table.currentRow()
        tasks = self.sched.tasks
        return tasks[r] if 0 <= r < len(tasks) else None

    def _sel(self):
        has = self._selected() is not None
        for b in (self.btn_edit, self.btn_run, self.btn_del):
            b.setEnabled(has)

    def refresh(self):
        tasks = self.sched.tasks
        cur = self.table.currentRow()
        self._filling = True
        self.table.setRowCount(len(tasks))
        for r, tk in enumerate(tasks):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if tk["enabled"] else Qt.Unchecked)
            chk.setData(Qt.UserRole, tk["id"])
            self.table.setItem(r, 0, chk)
            nxt = sch.next_run(tk)
            res = self.sched.results.get(tk["id"])
            if res:
                last = f"{short_dt(res[0])} · {res[1]}"
            elif tk["last_run"]:
                try:
                    last = short_dt(datetime.fromisoformat(tk["last_run"]))
                except ValueError:
                    last = ""
            else:
                last = t("Henüz çalışmadı")
            vals = [task_text(tk), when_text(tk), short_dt(nxt) if nxt else "—", last]
            for c, val in enumerate(vals, 1):
                it = QTableWidgetItem(val)
                it.setToolTip(val)
                if not tk["enabled"]:
                    it.setForeground(self.palette().placeholderText())
                self.table.setItem(r, c, it)
        self._filling = False
        self.empty.setVisible(not tasks)
        self.table.setVisible(bool(tasks))
        if 0 <= cur < len(tasks):
            self.table.selectRow(cur)
        self._sel()

    def _toggled(self, item):
        if self._filling or item.column() != 0:
            return
        if self.read_only():
            self.refresh()
            return
        self.sched.set_enabled(item.data(Qt.UserRole), item.checkState() == Qt.Checked)
        self.refresh()

    # ------------------------------------------------------------------ işlemler
    def _add_menu(self):
        m = QMenu(self)
        m.addAction(icons.icon("plus", None, 16), t("Boş görev"), lambda: self.add({}))
        m.addSeparator()
        for name, preset in sch.PRESETS:
            m.addAction(icons.icon("clock", None, 16), t(name), lambda p=preset: self.add(p))
        m.exec(self.btn_add.mapToGlobal(self.btn_add.rect().bottomLeft()))

    def add(self, preset):
        if self.read_only():
            return
        preset = dict(preset)
        if preset.get("message"):                      # şablon mesajı panel dilinde başlasın
            preset["message"] = t(preset["message"])
        d = TaskDialog(sch.new_task(**preset), new=True, parent=self)
        if d.exec():
            self.sched.upsert(d.task)
            self.refresh()
            self.table.selectRow(self.table.rowCount() - 1)

    def edit(self):
        tk = self._selected()
        if not tk or self.read_only():
            return
        d = TaskDialog(tk, parent=self)
        if d.exec():
            self.sched.upsert(d.task)
            self.refresh()

    def run_now(self):
        tk = self._selected()
        if not tk or self.read_only():
            return
        title = tk["name"] or t(sch.ACTIONS[tk["action"]])
        if tk["action"] in ("restart", "stop") and not self.confirm(
                t("'{name}' şimdi çalıştırılsın mı? Geri sayım yapılmaz.", name=title)):
            return
        status = self.sched.run(tk)
        self.refresh()
        self.info(t("'{name}': {status}", name=title, status=status))

    def delete(self):
        tk = self._selected()
        if not tk or self.read_only():
            return
        title = tk["name"] or t(sch.ACTIONS[tk["action"]])
        if not self.confirm(t("'{name}' görevi silinsin mi?", name=title)):
            return
        self.sched.remove(tk["id"])
        self.refresh()
