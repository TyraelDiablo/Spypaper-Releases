import os
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QMainWindow, QMessageBox, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from core import App, ServerError, detect_version
from . import VERSION, i18n, icons, motion, theme
from .i18n import t
from .theme import TOKENS, rgba
from .widgets import ServerBridge, ask, button, err_text, label
from .pages.console import ConsolePage
from .pages.dashboard import DashboardPage
from .pages.logs import LogsPage
from .pages.players import PlayersPage
from .pages.map import MapPage
from .pages.others import AdminPage, MaintenancePage, PluginsPage, SettingsPage
from .pages.esplora import EsploraPage
from .pages.modtrans import ModTransPage
from .pages.notes import NotesPage
from .pages.teams import TeamsPage
from .pages.danger import DangerPage
from .pages.content import ContentPage, restore_sharing
from .pages.guard import GuardPage
from .pages.files import FilesPage
from .pages.tasks import TasksPage
from .pages.discord import DiscordPage
from .pages.configs import ConfigsPage

from core import N_

# Kenar çubuğu grupları (anahtar, başlık, sayfalar). Sekmeler yalnızca kendi grupları içinde sıralanır.
GROUPS = [
    ("general", N_("Genel"), [DashboardPage, ConsolePage, LogsPage, MapPage, EsploraPage, NotesPage]),
    ("players", N_("Oyuncular"), [PlayersPage, TeamsPage, AdminPage]),
    ("content", N_("İçerik"), [PluginsPage, ModTransPage, ContentPage]),
    ("server", N_("Sunucu"), [SettingsPage, ConfigsPage, FilesPage]),
    ("automation", N_("Otomasyon"), [MaintenancePage, TasksPage, DiscordPage]),
    ("security", N_("Güvenlik"), [GuardPage, DangerPage]),
]
PAGES = [cls for _, _, pages in GROUPS for cls in pages]
GROUP_OF = {cls: key for key, _, pages in GROUPS for cls in pages}
CRASH_LIMIT = 3            # bu kadar çökme...
CRASH_WINDOW = 600         # ...bu kadar saniye içinde olursa otomatik yeniden başlatma durur
RESTART_DELAY = 10


def page_order(settings):
    """Kenar çubuğundaki sayfa sırası (PAGES indeksleri) ve gizlenenler.
    Kullanıcının sırası grup içinde uygulanır; gruplar her zaman GROUPS sırasındadır."""
    names = [c.__name__ for c in PAGES]
    user = [names.index(n) for n in (settings.get("page_order") or []) if n in names]
    user += [i for i in range(len(PAGES)) if i not in user]             # yeni eklenen sayfalar grubunun sonuna
    rank = {i: r for r, i in enumerate(user)}
    group_rank = {key: g for g, (key, _, _) in enumerate(GROUPS)}
    order = sorted(range(len(PAGES)), key=lambda i: (group_rank[GROUP_OF[PAGES[i]]], rank[i]))
    hidden = {names.index(n) for n in (settings.get("hidden_pages") or []) if n in names}
    if len(hidden) >= len(PAGES):
        hidden = set()
    return order, hidden


def ask_pin(parent, profile, purpose=""):
    """Sunucuda PIN varsa sorar. Doğruysa (ya da PIN yoksa) True."""
    from core.safemode import verify_pin
    from .msgbox import get_text
    stored = profile.get("pin_hash")
    if not stored:
        return True
    for attempt in range(3):
        msg = t("'{name}' PIN ile korunuyor.", name=profile.name) + ("\n" + purpose if purpose else "")
        if attempt:
            msg += "\n" + t("Yanlış PIN, tekrar dene ({n} hak kaldı).", n=3 - attempt)
        pin, ok = get_text(parent, t("PIN gerekli"), msg, password=True)
        if not ok:
            return False
        if verify_pin(pin, stored):
            return True
    QMessageBox.warning(parent, t("PIN gerekli"), t("3 kez yanlış PIN girildi."))
    return False


def icon_button(icon_name, tip, on_click):
    b = QPushButton()
    b.setIcon(icons.icon(icon_name, None, 20))
    b.setIconSize(QSize(20, 20))
    b.setObjectName("IconButton")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(t(tip))
    b.clicked.connect(on_click)
    return b


class ServerPanel(QWidget):
    """Tek bir sunucunun yönetim paneli (eski ana pencere)."""

    def __init__(self, ctl, app):
        super().__init__()
        self.ctl, self.app = ctl, app
        self.bridge = ServerBridge(app.server)
        app.players.set_language(i18n.current())   # eşya adları panel dilinde
        app.logtrans.ui_t = t                       # sunucu mesajları sözlüğü panel dilinde
        app.logtrans.ui_lang = i18n.current          # İngilizce panelde sunucu satırları olduğu gibi kalır

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # --- kenar çubuğu ---
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(215)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 14)
        sv.setSpacing(0)
        name = label(app.config.name, "Brand", raw=True)
        name.setWordWrap(True)
        sv.addWidget(name)
        self.brand_sub = label("", "BrandSub")
        sv.addWidget(self.brand_sub)
        self._brand_text()
        self.nav = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.pages = []
        self.order, self.hidden = page_order(ctl.settings)
        for i, cls in enumerate(PAGES):
            page = cls(app, self.bridge)
            self.pages.append(page)
            self.stack.addWidget(page)
            b = QPushButton(t(cls.title).replace("&", "&&"))
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(b, i)
        # gruplar: başlığa tıklayınca açılır/kapanır; durum ayarlarda saklanır. Uzun listede kaydırılır.
        scroll = QScrollArea()
        scroll.setObjectName("NavScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        navw = QWidget()
        navw.setObjectName("NavInner")
        nv = QVBoxLayout(navw)
        nv.setContentsMargins(0, 0, 0, 0)
        nv.setSpacing(0)
        self.collapsed = set(ctl.settings.get("nav_collapsed") or [])
        self.group_btns, self.group_pages = {}, {}
        for key, title, classes in GROUPS:
            idx = [i for i in self.order if GROUP_OF[PAGES[i]] == key]
            visible = [i for i in idx if i not in self.hidden]
            hb = QPushButton(t(title).upper())
            hb.setObjectName("NavGroup")
            hb.setCursor(Qt.PointingHandCursor)
            hb.clicked.connect(lambda _c=False, k=key: self.toggle_group(k))
            hb.setVisible(bool(visible))                # tüm sekmeleri gizlenmiş grup görünmez
            self.group_btns[key], self.group_pages[key] = hb, visible
            nv.addWidget(hb)
            for i in idx:
                nv.addWidget(self.nav.button(i))
                if i in self.hidden:                    # Panel Düzeni'nde gizlenen sekme hiç görünmez
                    self.nav.button(i).setVisible(False)
        nv.addStretch(1)
        scroll.setWidget(navw)
        sv.addWidget(scroll, 1)
        self._apply_groups()
        self.navbar = motion.SlideBar(self.nav, navw, "left")
        danger_btn = self.nav.button(PAGES.index(DangerPage))
        danger_btn.setIcon(icons.icon("triangle-alert", TOKENS["danger"], 16))
        self._nav_texts()
        path = label(app.config.server_path, "BrandSub", raw=True)
        path.setStyleSheet("padding-top: 10px;")
        path.setWordWrap(True)
        sv.addWidget(path)
        self.nav.idClicked.connect(self.go)
        h.addWidget(side)

        # --- sağ taraf ---
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        h.addLayout(main, 1)

        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 10, 22, 10)
        tl.setSpacing(8)
        tl.addWidget(icon_button("menu", "Menü ve ayarlar (Ctrl+,)", ctl.toggle_drawer))
        back = button("Sunucular", "flat", ctl.show_home, tooltip="Ana ekrana dön")
        back.setIcon(icons.icon("arrow-left", None, 16))
        tl.addWidget(back)
        self.title_lbl = label("", "PageTitle")
        tl.addSpacing(6)
        tl.addWidget(self.title_lbl)
        tl.addStretch(1)
        self.safe_btn = button("", "flat", self.safe_menu, tooltip="Güvenli mod seviyesi")
        tl.addWidget(self.safe_btn)
        self.status = label("", "StatusPill")
        tl.addWidget(self.status)
        self.btn_start = button("Başlat", "primary", self.start)
        self.btn_stop = button("Durdur", "danger", self.stop)
        self.btn_update = button("Güncelle", "ghost", self.update_paper,
                                 tooltip="Sunucu yazılımını kur ya da güncelle (Paper, Purpur, Vanilla, Fabric, Forge, NeoForge)")
        tl.addWidget(self.btn_update)
        tl.addWidget(self.btn_start)
        tl.addWidget(self.btn_stop)
        main.addWidget(top)
        main.addWidget(self.stack, 1)

        # latest.log anlık takip (sunucu panel dışında açılmış olsa da çalışır)
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.poll_logs)
        self.log_timer.start(int(float(ctl.settings.get("log_poll_seconds")) * 1000))
        self.poll_logs()

        self.bridge.state.connect(self.on_state)
        self.on_state(app.server.state)
        self.current = 0
        self._safe_text()
        self.go(self.first_page())

    # --- güvenli mod ---
    def _safe_text(self):
        from core.safemode import LEVELS
        lvl = int(self.app.config.get("safe_mode") or 0)
        c = [theme.TOKENS["text_muted"], theme.TOKENS["info"], theme.TOKENS["warn"], theme.TOKENS["danger"]][lvl]
        self.safe_btn.setText(t("Güvenli mod: {lvl}", lvl=t(LEVELS[lvl])))
        self.safe_btn.setIcon(icons.icon("shield", c, 16))
        self.safe_btn.setStyleSheet(f"color:{c};")

    def safe_menu(self):
        from PySide6.QtWidgets import QMenu
        from core.safemode import LEVEL_INFO, LEVELS
        m = QMenu(self)
        cur = int(self.app.config.get("safe_mode") or 0)
        for i, name in enumerate(LEVELS):
            a = m.addAction(t(name) + " — " + t(LEVEL_INFO[i]))
            a.setCheckable(True)
            a.setChecked(i == cur)
            a.setData(i)
        act = m.exec(self.safe_btn.mapToGlobal(self.safe_btn.rect().bottomLeft()))
        if act is None:
            return
        new = act.data()
        if new < cur and not ask_pin(self, self.app.config, t("Güvenli mod seviyesini düşürmek için PIN gerekli.")):
            return
        self.app.config.set("safe_mode", new)
        self._safe_text()

    def poll_logs(self):
        try:
            new = self.app.logs.poll()
        except Exception as e:
            print(f"[log] {e}")
            return
        if new:
            self.bridge.events.emit(new)

    def _brand_text(self):
        ver, soft = detect_version(self.app.config.server_path)
        self.brand_sub.setText(" ".join(x for x in (soft, ver) if x) or t("Sunucu Yönetim Paneli"))

    def _page_title(self, i):
        p = self.pages[i]
        return p.page_title() if hasattr(p, "page_title") else t(PAGES[i].title)

    def _nav_texts(self):
        for i in range(len(self.pages)):
            self.nav.button(i).setText(self._page_title(i).replace("&", "&&"))

    def first_page(self):
        return next((i for i in self.order if i not in self.hidden), 0)

    # --- gruplar ---
    def _apply_groups(self):
        for key, hb in self.group_btns.items():
            closed = key in self.collapsed
            hb.setIcon(icons.icon("chevron-right" if closed else "chevron-down", TOKENS["text_muted"], 12))
            hb.setToolTip(t("Grubu aç") if closed else t("Grubu kapat"))
            hb.setProperty("closed", closed)
            for i in self.group_pages[key]:
                self.nav.button(i).setVisible(not closed)
        if getattr(self, "navbar", None):                # gösterge seçili düğmeyi izler; kapalı grupta gizlenir
            self.navbar.move(self.nav.checkedButton(), animate=False)

    def toggle_group(self, key, open_=None):
        """open_=None: aç/kapat; True: aç; False: kapat."""
        if open_ is None:
            open_ = key in self.collapsed
        if open_:
            self.collapsed.discard(key)
        else:
            self.collapsed.add(key)
        self.ctl.settings.set("nav_collapsed", sorted(self.collapsed))
        self._apply_groups()

    def go(self, i):
        key = GROUP_OF[PAGES[i]]
        if key in self.collapsed:                        # kapalı gruptaki sekmeye gidilince grup açılır
            self.toggle_group(key, open_=True)
        changed = self.stack.currentIndex() != i
        self.current = i
        self.nav.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        if changed:
            motion.fade_in(self.stack.currentWidget())
        self.title_lbl.setText(self._page_title(i))
        self.pages[i].on_show()

    def on_state(self, state):
        text, c = theme.status(state)
        self.status.setText(f"●  {t(text)}")
        self.status.setStyleSheet(f"color:{c}; background: {rgba(c, 40)};")
        self.btn_start.setEnabled(state == "stopped")
        self.btn_update.setEnabled(state == "stopped")
        self.btn_stop.setEnabled(state in ("starting", "running"))
        self.ctl.server_state_changed()

    def _eula_ok(self):
        return eula_ok(self, self.app.config.server_path)

    def _java_ok(self):
        """Seçili Java sunucunun Minecraft sürümü için yetersizse ya da bulunamıyorsa sorar."""
        from core import javamgr
        try:
            req, major, exe = javamgr.check(self.app.config)
        except Exception as e:
            print(f"[java] {e}")
            return True
        if exe and (req is None or major is None or major >= req):
            return True
        from .msgbox import choose
        if not exe:
            text = t("Seçili Java ({path}) bulunamadı.", path=self.app.config.get("java_path") or "java")
        else:
            text = t("Bu sunucu Java {req} ya da daha yenisini gerektiriyor ama seçili Java {n}. "
                     "Sunucu büyük olasılıkla açılmayacak.", req=req, n=major)
        res = choose(self, "warning", t("Java"), text,
                     [(t("İptal"), "ghost"), (t("Yine de Başlat"), "ghost"), (t("Java Yöneticisini Aç"), "primary")],
                     default=2, cancel=0)
        if res == 1:
            return True
        if res == 2:
            from .java_dialog import JavaDialog
            d = JavaDialog(self.app, self)
            d.exec()
            if d.changed:
                self.pages[PAGES.index(SettingsPage)].on_show()
                return self._java_ok()
        return False

    def start(self):
        if not self._eula_ok() or not self._java_ok():
            return
        try:
            self.app.server.start()
            self.go(PAGES.index(ConsolePage))
        except ServerError as e:
            QMessageBox.critical(self, t("Hata"), err_text(e))

    def update_paper(self):
        from .update_dialog import UpdateDialog
        UpdateDialog(self.app, self).exec()
        # yazılım değişmiş olabilir: kenar çubuğu, sayfa adları ve geçerli sayfa yenilenir
        self._brand_text()
        self._nav_texts()
        self.go(self.current)

    def stop(self):
        self.app.server.stop()

    def shutdown(self):
        self.log_timer.stop()
        self.bridge.detach()


def eula_ok(parent, server_path):
    """Minecraft EULA'sı kabul edilmemişse sunucu açılmaz. Kullanıcıya sorup eula.txt'yi yazar.
    Panel bunu kendiliğinden kabul etmez."""
    path = os.path.join(server_path, "eula.txt")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            if any(l.strip().lower().replace(" ", "") == "eula=true" for l in f):
                return True
    except OSError:
        pass
    from .msgbox import choose
    text = (t("Sunucuyu çalıştırmak için Minecraft Son Kullanıcı Lisans Sözleşmesi'ni (EULA) kabul etmen gerekir.")
            + f"<br><br><a href='https://aka.ms/MinecraftEULA' style='color:{theme.TOKENS['accent']}'>"
              "https://aka.ms/MinecraftEULA</a><br><br>" + t("Sözleşmeyi okudun ve kabul ediyor musun?"))
    if choose(parent, "question", t("Minecraft EULA"), text,
              [(t("İptal"), "ghost"), (t("Kabul Ediyorum"), "primary")], default=1, cancel=0, rich=True) != 1:
        return False
    try:
        from datetime import datetime
        with open(path, "w", encoding="utf-8") as f:
            f.write("#By changing the setting below to TRUE you are indicating your agreement to our EULA "
                    "(https://aka.ms/MinecraftEULA).\n"
                    f"#{datetime.now().strftime('%a %b %d %H:%M:%S %Y')} (Spypaper)\neula=true\n")
    except OSError as e:
        QMessageBox.critical(parent, t("Hata"), str(e))
        return False
    return True


class MainWindow(QMainWindow):
    """Ana ekran + sunucu panelleri + ☰ ayarlar çekmecesi."""

    def __init__(self, settings):
        super().__init__()
        from . import msgbox
        msgbox.install()                      # Windows mesaj kutuları yerine panele özel kutular
        self.settings = settings
        self.apps = {}        # id -> App   (UI yeniden kurulsa da yaşar; çalışan sunucular durmaz)
        self.panels = {}      # id -> ServerPanel
        self.view = ("home", None, 0)
        self.drawer_open = False
        self.setWindowTitle("Spypaper")
        self.resize(1240, 800)
        self.setMinimumSize(1000, 660)

        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.toggle_drawer)
        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.drawer_open and self.toggle_drawer())
        self.home_timer = QTimer(self)
        self.home_timer.timeout.connect(lambda: self.home.refresh_status() if self.view[0] == "home" else None)
        self.home_timer.start(2000)
        self.build()
        from .remote_dialog import RemoteController
        self.remote = RemoteController(self)        # Spypaper Remote (telefon), ayarda açıksa başlar
        self.remote.autostart()
        self._handled_run, self._crashes = {}, {}
        restore_sharing(self.settings.servers())          # içerik editörünün kaynak paketi paylaşımı
        # otomatik bakım: tüm sunucular için (paneli açık olmasa da) saniyede bir
        self.maint_timer = QTimer(self)
        self.maint_timer.timeout.connect(self.maintenance_tick)
        self.maint_timer.start(1000)

        last = settings.get("last_server")
        if settings.get("open_last_on_start") and settings.server(last):
            self.open_server(last)

    # ------------------------------------------------------------ kurulum
    def apply_look(self):
        s = self.settings
        i18n.load(s.get("language"))
        theme.apply(s.get("theme"), s.get("high_contrast"), s.get("font_scale"))
        qapp = QApplication.instance()
        qapp.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        qapp.setStyleSheet(theme.stylesheet())
        motion.REDUCED = bool(s.get("reduce_motion"))

    def build(self):
        """Tüm arayüzü (yeniden) kurar. Dil/tema değişince çağrılır."""
        from .home import HomeScreen
        from .drawer import Drawer
        self.apply_look()
        for p in self.panels.values():
            p.shutdown()
        self.panels.clear()
        old = self.centralWidget()

        root = QWidget()
        root.setObjectName("Root")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.home = HomeScreen(self)
        self.stack.addWidget(self.home)

        self.scrim = QWidget(root)
        self.scrim.setObjectName("Scrim")
        self.scrim.setAttribute(Qt.WA_StyledBackground, True)
        self.scrim.hide()
        self.scrim.mousePressEvent = lambda e: self.toggle_drawer()
        self.drawer = Drawer(self, root)
        self.drawer.hide()
        self.setCentralWidget(root)
        if old:
            old.deleteLater()

        keep_open, self.drawer_open = self.drawer_open, False
        kind, sid, page = self.view
        if kind == "server" and self.settings.server(sid):
            self.open_server(sid, page, check_pin=False)
        else:
            self.show_home()
        if keep_open:           # ayar değişince çekmece açık kalsın
            self.toggle_drawer(animate=False)

    def rebuild_later(self):
        QTimer.singleShot(0, self.build)

    # ------------------------------------------------------------ gezinme
    def show_home(self):
        if self.drawer_open:
            self.toggle_drawer()
        cur = self.stack.currentWidget()
        if isinstance(cur, ServerPanel):
            self.view = ("home", None, 0)
        self.view = ("home", None, 0)
        self.home.refresh()
        was = self.stack.currentWidget()
        self.stack.setCurrentWidget(self.home)
        if was is not self.home:
            motion.fade_in(self.home)
        self.setWindowTitle("Spypaper")

    def app_for(self, sid):
        if sid not in self.apps:
            app = self.apps[sid] = App(self.settings.server(sid))
            app.maintenance.tr = t                  # oyunculara giden uyarılar panel dilinde
            app.guard.tr = t
            app.scheduler.tr = t
            app.discord.tr = t
        return self.apps[sid]

    def watchdog(self):
        """Çökme bekçisi: 'Çökünce yeniden başlat' açık sunucu beklenmedik kapanırsa yeniden başlatır."""
        now = time.time()
        for sid, app in list(self.apps.items()):
            srv = app.server
            if not srv.ended_run or self._handled_run.get(sid) == srv.ended_run or srv.is_running:
                continue
            self._handled_run[sid] = srv.ended_run          # her kapanış bir kez işlenir
            if not (srv.crashed and app.config.get("auto_restart")):
                continue
            hist = [x for x in self._crashes.get(sid, []) if now - x < CRASH_WINDOW] + [now]
            self._crashes[sid] = hist
            name = app.config.name
            if len(hist) >= CRASH_LIMIT:
                srv.history.append("[Spypaper] " + t("Sunucu {n} dakikada {k} kez çöktü; otomatik yeniden başlatma durduruldu.",
                                                     n=CRASH_WINDOW // 60, k=len(hist)))
                from .msgbox import warning
                QTimer.singleShot(0, lambda n=name, k=len(hist): warning(self, t("Çökme bekçisi"), t(
                    "'{name}' {n} dakikada {k} kez çöktü; otomatik yeniden başlatma durduruldu. Konsoldaki hataya bak.",
                    name=n, n=CRASH_WINDOW // 60, k=k)))
                continue
            line = "[Spypaper] " + t("Sunucu beklenmedik şekilde kapandı; {s} saniye içinde yeniden başlatılıyor.", s=RESTART_DELAY)
            srv.history.append(line)
            if srv.on_line:
                srv.on_line(line)
            QTimer.singleShot(RESTART_DELAY * 1000, lambda a=app: self._auto_restart(a))

    def _auto_restart(self, app):
        if app.server.is_running or app.maintenance.active:
            return
        try:
            app.server.start()
            self.server_state_changed()
        except Exception as e:
            print(f"[bekçi] {app.config.name}: {e}")

    def maintenance_tick(self):
        self.watchdog()
        for app in list(self.apps.values()):
            try:
                app.guard.tick()
            except Exception as e:
                print(f"[koruma] {app.config.name}: {e}")
            try:
                app.perf.tick()                     # TPS/MSPT sorgusu (yalnızca çalışan sunucularda)
            except Exception as e:
                print(f"[tps] {app.config.name}: {e}")
        for prof in self.settings.servers():
            if not prof.exists:
                continue
            if any(x.get("enabled", True) for x in prof.get("scheduled_tasks") or []):
                try:                                # zamanlanmış görevler (paneli açık olmasa da)
                    if self.app_for(prof.id).scheduler.tick():
                        self.server_state_changed()
                except Exception as e:
                    print(f"[görev] {prof.name}: {e}")
            if not (prof.get("maintenance_state") or {}).get("active") and \
                    not (prof.get("maintenance_schedule") or {}).get("enabled"):
                continue
            app = self.app_for(prof.id)
            if prof.id not in self.panels and app.server.is_running:
                try:                                # paneli açık değilse içerideki oyuncuları bilmek için
                    app.logs.poll()
                except Exception:
                    pass
            try:
                if app.maintenance.tick():
                    self.server_state_changed()
            except Exception as e:
                print(f"[bakım] {prof.name}: {e}")

    def open_server(self, sid, page=0, check_pin=True):
        prof = self.settings.server(sid)
        if not prof:
            return
        if not prof.exists:
            QMessageBox.warning(self, t("Uyarı"), t("Sunucu klasörü bulunamadı:\n{path}", path=prof.server_path))
            return
        if check_pin and not ask_pin(self, prof):
            return
        if self.drawer_open:
            self.toggle_drawer(animate=False)
        app = self.app_for(sid)
        if sid not in self.panels:
            panel = ServerPanel(self, app)
            self.panels[sid] = panel
            self.stack.addWidget(panel)
        panel = self.panels[sid]
        was = self.stack.currentWidget()
        self.stack.setCurrentWidget(panel)
        if was is not panel:
            motion.fade_in(panel, dy=0)
        panel.go(page if 0 < page < len(PAGES) else panel.first_page())
        self.view = ("server", sid, page)
        self.settings.touch(sid)
        self.setWindowTitle(f"{prof.name} — Spypaper")

    def current_panel(self):
        w = self.stack.currentWidget()
        return w if isinstance(w, ServerPanel) else None

    def forget_server(self, sid):
        """Listeden kaldırılan / klasörü değişen sunucunun önbelleğini temizler."""
        p = self.panels.pop(sid, None)
        if p:
            p.shutdown()
            self.stack.removeWidget(p)
            p.deleteLater()
        app = self.apps.get(sid)
        if app and not app.server.is_running:
            self.apps.pop(sid, None)

    def remote_changed(self, sid):
        """Telefondan ayar/bakım değişti: o sunucunun açık sayfası yenilensin."""
        p = self.panels.get(sid)
        if p and p.isVisible():
            p.pages[p.current].on_show()
        self.server_state_changed()

    def server_state_changed(self):
        if self.view[0] == "home":
            self.home.refresh_status()

    def is_running(self, sid):
        a = self.apps.get(sid)
        return bool(a and a.server.is_running)

    # ------------------------------------------------------------ ayarlar
    def set_setting(self, key, value):
        if self.settings.get(key) == value:
            return
        self.settings.set(key, value)
        if key in ("language", "theme", "high_contrast", "font_scale", "translate_logs"):
            p = self.current_panel()
            if p:
                self.view = ("server", self.view[1], p.current)
            self.rebuild_later()

    # ------------------------------------------------------------ çekmece
    def _drawer_x(self, shown):
        w = self.drawer.width()
        if i18n.is_rtl():
            return self.width() - w if shown else self.width()
        return 0 if shown else -w

    def toggle_drawer(self, animate=True):
        # yeni kurulan kök widget henüz boyutlanmamış olabilir; pencere boyutunu kullan
        self.centralWidget().resize(self.size())
        self.drawer.setFixedHeight(self.height())
        self.scrim.setGeometry(0, 0, self.width(), self.height())
        opening = not self.drawer_open
        self.drawer_open = opening
        if opening:
            self.drawer.sync()
            self.scrim.show()
            self.scrim.raise_()
            self.drawer.move(self._drawer_x(False), 0)
            self.drawer.show()
            self.drawer.raise_()
        animate = animate and not self.settings.get("reduce_motion")
        end = QPoint(self._drawer_x(opening), 0)
        if not animate:
            self.drawer.move(end)
            if not opening:
                self.drawer.hide()
                self.scrim.hide()
            return
        self._anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setEndValue(end)
        if not opening:
            self._anim.finished.connect(lambda: (self.drawer.hide(), self.scrim.hide()))
        self._anim.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "drawer", None) and self.drawer_open:
            self.scrim.setGeometry(0, 0, self.width(), self.height())
            self.drawer.setFixedHeight(self.height())
            self.drawer.move(self._drawer_x(True), 0)

    # ------------------------------------------------------------ çıkış
    def closeEvent(self, e):
        """Çalışan sunucular her zaman düzgünce durdurulur (dünya kaydı bozulmasın)."""
        unsaved = [f"{p.app.config.name}: {pg.rel}" for p in self.panels.values() for pg in p.pages
                   if isinstance(pg, ConfigsPage) and pg.dirty]
        if unsaved and not ask(self, t("Kaydedilmemiş yapılandırma değişiklikleri var:\n{files}\n\nYine de çıkılsın mı?",
                                       files="\n".join(unsaved)), t("Çıkış")):
            e.ignore()
            return
        running = [a for a in self.apps.values() if a.server.is_running]
        if running and self.settings.get("confirm_on_close"):
            names = ", ".join(a.config.name for a in running)
            if not ask(self, t("Çalışan sunucular durdurulup çıkılsın mı?\n{names}", names=names), t("Çıkış")):
                e.ignore()
                return
        for a in running:
            a.server.stop()
        for a in running:
            try:
                a.server.process.wait(timeout=30)
            except Exception:
                pass
        self.remote.shutdown()
        e.accept()
