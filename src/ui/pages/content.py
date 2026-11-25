"""İçerik Editörü: tablo, müzik diski (Newgrounds), alet/silah ve yiyecek ekleme; 3x3 tarif; paket oluşturma
ve kaynak paketini paylaşma. Çekirdek: core/content.py, core/newgrounds.py, core/packhost.py."""
import copy
import os
import re
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from core import N_, content as C, newgrounds as NG
from core.commands import EFFECTS, ENCHANTS

ENCH_MAX = 12          # bir eşyada en fazla büyü sayısı
ENCH_LEVEL_MAX = 255   # Minecraft büyü seviyesini 1-255 arasında kabul eder
# oyuncuyu hareket ettiren büyüler ve vanilla'daki en yüksek seviyeleri
MOTION_ENCHANTS = {"wind_burst": 3, "riptide": 3, "knockback": 2, "punch": 2}
from core.config import detect_version
from core.danger import level_name
from core.packhost import DEFAULT_PORT, HOST
from .. import icons
from ..i18n import t
from ..theme import TOKENS
from ..widgets import Card, Page, button, label, row

TYPE_ICON = {"painting": "image", "disc": "disc", "tool": "sword", "food": "apple", "hud": "heart"}


def slug(name):
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = re.sub(r"[^a-z0-9_]+", "_", (name or "").translate(tr).lower()).strip("_")
    return s[:32] or "icerik"


def item_combo(items, editable=True):
    cb = QComboBox()
    cb.setEditable(editable)
    cb.addItem("")
    cb.addItems(items)
    cb.setMaxVisibleItems(18)
    return cb


class ContentPage(Page):
    title = "İçerik Editörü"
    ng_done = Signal(object, object)       # (başlık, sanatçı, dosya, süre) / hata

    def __init__(self, app, bridge):
        super().__init__(app, bridge)
        self.items, self.cur = [], None
        self.ng_done.connect(self._ng_done)

        self.banner = label("", None, wrap=True)
        self.banner.setStyleSheet(f"color:{TOKENS['warn']}; font-weight:600;")
        self.root.addWidget(self.banner)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.root.addLayout(body, 1)

        left = Card("İçerikler")
        left.setFixedWidth(260)
        self.btn_new = button("Yeni ▾", "primary", self.new_menu)
        left.header_actions.addWidget(self.btn_new)
        self.list = QListWidget()
        self.list.setIconSize(QSize(18, 18))
        self.list.currentRowChanged.connect(self.select)
        left.add(self.list, 1)
        self.btn_del = button("Sil", "danger", self.delete)
        left.add(row(self.btn_del, None))
        left.add(label("Yeni blok eklenemez; veri paketleri yalnızca tablo, müzik diski ve var olan eşyaların "
                       "değiştirilmiş hallerini ekleyebilir.", "Muted", wrap=True))
        body.addWidget(left)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        self.col = QVBoxLayout(inner)
        self.col.setContentsMargins(0, 0, 6, 0)
        self.col.setSpacing(14)
        scroll.setWidget(inner)
        body.addWidget(scroll, 1)

        self._build_common()
        self._build_types()
        self._build_recipe()
        self._build_actions()
        self._build_pack()
        self.col.addStretch(1)

    # ------------------------------------------------------------ form
    def _build_common(self):
        c = self.c_common = Card("Genel")
        f = QFormLayout()
        f.setSpacing(8)
        self.f_type = label("", "Muted")
        self.f_name = QLineEdit()
        self.f_name.textEdited.connect(self._auto_id)
        self.f_id = QLineEdit()
        self.f_id.setPlaceholderText("ates_kilici")
        self.f_color = QComboBox()
        self.f_color.addItem(t("Varsayılan"), "")
        for col in C.COLORS:
            self.f_color.addItem(col, col)
        self.f_lore = QPlainTextEdit()
        self.f_lore.setFixedHeight(64)
        self.f_lore.setPlaceholderText(t("Eşyanın altında görünen açıklama (her satır ayrı)"))
        f.addRow(t("Tür"), self.f_type)
        f.addRow(t("Ad"), self.f_name)
        f.addRow(t("Kimlik"), self.f_id)
        f.addRow(t("Ad rengi"), self.f_color)
        f.addRow(t("Açıklama"), self.f_lore)
        self.common_form = f
        c.add(f)
        self.col.addWidget(c)

    def _build_types(self):
        self.types = QStackedWidget()
        from .. import motion
        motion.auto_fade(self.types, dy=0)
        self.col.addWidget(self.types)
        items = self._item_ids()

        # tablo
        p = Card("Tablo", "Resim, blok başına 16 piksele ölçeklenir")
        self.p_preview = QLabel()
        self.p_preview.setFixedSize(160, 160)
        self.p_preview.setAlignment(Qt.AlignCenter)
        self.p_preview.setStyleSheet(f"background:{TOKENS['surface_2']}; border-radius:8px;")
        self.p_w, self.p_h = QSpinBox(), QSpinBox()
        for s in (self.p_w, self.p_h):
            s.setRange(1, 16)
        self.p_w.valueChanged.connect(self._repaint_painting)
        self.p_h.valueChanged.connect(self._repaint_painting)
        self.p_author = QLineEdit()
        f = QFormLayout()
        f.addRow(t("Genişlik (blok)"), self.p_w)
        f.addRow(t("Yükseklik (blok)"), self.p_h)
        f.addRow(t("Ressam"), self.p_author)
        h = QHBoxLayout()
        h.addWidget(self.p_preview)
        v = QVBoxLayout()
        v.addLayout(f)
        v.addWidget(button("Tasarla…", "primary", self.design_painting))
        v.addWidget(button("Resim Seç", "ghost", self.pick_image))
        v.addStretch(1)
        h.addLayout(v, 1)
        p.add(h)
        self.types.addWidget(p)

        # disk
        d = Card("Müzik Diski", "Newgrounds ID'si gir ya da kendi ses dosyanı seç")
        self.d_ng = QLineEdit()
        self.d_ng.setPlaceholderText(t("Newgrounds ID (ör. 467339)"))
        self.d_ng_btn = button("Getir", "primary", self.fetch_ng)
        d.add(row(self.d_ng, self.d_ng_btn, button("Ses Dosyası Seç", "ghost", self.pick_sound), stretch_end=False))
        self.d_info = label("", "Muted", wrap=True)
        d.add(self.d_info)
        self.d_artist = QLineEdit()
        self.d_base = QComboBox()
        self.d_base.addItems(C.DISC_BASES)
        self.d_cmp = QSpinBox()
        self.d_cmp.setRange(1, 15)
        f = QFormLayout()
        f.addRow(t("Sanatçı"), self.d_artist)
        f.addRow(t("Disk görünümü"), self.d_base)
        f.addRow(t("Karşılaştırıcı sinyali"), self.d_cmp)
        d.add(f)
        self.d_rights = QCheckBox(t("Bu ses dosyasını kullanma ve oyunculara dağıtma hakkım var"))
        self.d_rights.setToolTip(t("İşaretlenmeden disk paketlenmez ve paylaşılmaz. Telifli parçaları izinsiz dağıtma."))
        d.add(self.d_rights)
        d.add(label("Newgrounds'taki parçaların hakları sanatçılarına aittir. Yalnızca kullanma iznin olan "
                    "parçaları ekle; sanatçının adı diskin açıklamasında görünür.", "Muted", wrap=True))
        self.d_tex = self._texture_row(d)
        self.types.addWidget(d)

        # alet / silah
        tl = Card("Alet / Silah")
        self.t_base = item_combo(C.TOOL_BASES + [i for i in items if i not in C.TOOL_BASES], True)
        self.t_dmg, self.t_spd, self.t_mine = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        self.t_dmg.setRange(0, 1000)
        self.t_spd.setRange(0.1, 20)
        self.t_spd.setSingleStep(0.1)
        self.t_mine.setRange(0, 100)
        self.t_dur = QSpinBox()
        self.t_dur.setRange(0, 100000)
        self.t_dur.setSpecialValueText(t("Varsayılan"))
        self.t_unb = QCheckBox(t("Kırılmaz"))
        self.t_glint = QCheckBox(t("Büyülü parıltı"))
        f = QFormLayout()
        f.addRow(t("Temel eşya"), self.t_base)
        f.addRow(t("Saldırı hasarı"), self.t_dmg)
        f.addRow(t("Saldırı hızı"), self.t_spd)
        f.addRow(t("Dayanıklılık"), self.t_dur)
        f.addRow(t("Kazma hızı bonusu"), self.t_mine)
        tl.add(f)
        tl.add(row(self.t_unb, self.t_glint))
        self.t_ench = []
        self.t_ench_box = QVBoxLayout()
        tl.add(label("Büyüler", "Muted"))
        tl.add(self.t_ench_box)
        tl.add(button("Büyü ekle", "ghost", self.add_ench_row))
        self.t_motion = label("", "Muted", wrap=True)
        self.t_motion.setStyleSheet(f"color:{TOKENS['warn']};")
        self.t_motion.setVisible(False)
        tl.add(self.t_motion)
        self.t_tex = self._texture_row(tl)
        self.types.addWidget(tl)

        # yiyecek
        fd = Card("Yiyecek")
        self.f_base = item_combo(C.FOOD_BASES + [i for i in items if i not in C.FOOD_BASES], True)
        self.f_nut = QSpinBox()
        self.f_nut.setRange(0, 20)
        self.f_sat, self.f_sec = QDoubleSpinBox(), QDoubleSpinBox()
        self.f_sat.setRange(0, 20)
        self.f_sec.setRange(0.1, 30)
        self.f_sec.setSingleStep(0.1)
        self.f_always = QCheckBox(t("Tokken de yenebilir"))
        f = QFormLayout()
        f.addRow(t("Temel eşya"), self.f_base)
        f.addRow(t("Besin (açlık çubuğu, 2 = 1 but)"), self.f_nut)
        f.addRow(t("Doygunluk"), self.f_sat)
        f.addRow(t("Yeme süresi (sn)"), self.f_sec)
        fd.add(f)
        fd.add(self.f_always)
        self.f_eff = []
        grid = QGridLayout()
        for i in range(3):
            e = QComboBox()
            e.addItem("")
            e.addItems(EFFECTS)
            sec, amp = QSpinBox(), QSpinBox()
            sec.setRange(1, 3600)
            sec.setSuffix(" " + t("sn"))
            amp.setRange(1, 10)
            amp.setPrefix(t("Seviye") + " ")
            grid.addWidget(e, i, 0)
            grid.addWidget(sec, i, 1)
            grid.addWidget(amp, i, 2)
            self.f_eff.append((e, sec, amp))
        fd.add(label("Yiyince verilen efektler", "Muted"))
        fd.add(grid)
        self.f_tex = self._texture_row(fd)
        self.types.addWidget(fd)

        # HUD
        hd = Card("HUD", "Oyuncuların ekranındaki kalp, açlık, zırh, hotbar gibi görsellerin yerine kendi resmin")
        self.h_sprite = QComboBox()
        for key, (name, w, h) in C.HUD_SPRITES.items():
            self.h_sprite.addItem(f"{t(name)}  ({w}×{h})", key)
        self.h_sprite.currentIndexChanged.connect(self._hud_preview)
        self.h_preview = QLabel()
        self.h_preview.setMinimumSize(200, 90)
        self.h_preview.setAlignment(Qt.AlignCenter)
        self.h_preview.setStyleSheet(f"background:{TOKENS['surface_2']}; border-radius:8px;")
        self.h_info = label("", "Muted", wrap=True)
        f = QFormLayout()
        f.addRow(t("Değiştirilecek parça"), self.h_sprite)
        hd.add(f)
        hd.add(row(self.h_preview, button("Tasarla…", "primary", self.design_hud), button("Resim Seç", "ghost", self.pick_hud), None))
        hd.add(self.h_info)
        hd.add(label("Resim parçanın boyutuna ya da tam katına (2×, 4×…) ölçeklenir; piksel sanatı için keskin büyütme "
                     "kullanılır. Yalnızca kaynak paketine girer, veri paketi ve tarif gerekmez. Paketi kabul eden "
                     "her oyuncunun ekranında görünür.", "Muted", wrap=True))
        self.types.addWidget(hd)

    def _texture_row(self, card):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        prev = QLabel()
        prev.setFixedSize(32, 32)
        prev.setStyleSheet(f"background:{TOKENS['surface_2']}; border-radius:4px;")
        h.addWidget(prev)
        h.addWidget(button("Tasarla…", "primary", self.design_texture))
        h.addWidget(button("Doku Seç (16×16)", "ghost", self.pick_texture))
        h.addWidget(button("Dokuyu Kaldır", "ghost", self.clear_texture))
        h.addStretch(1)
        card.add(box)
        note = label("Doku isteğe bağlı; seçmezsen temel eşyanın görünümü kullanılır (Minecraft 1.21.4+).", "Muted", wrap=True)
        card.add(note)
        box.preview = prev
        return box

    def _build_recipe(self):
        r = Card("Tarif", "Çalışma masasında nasıl yapıldığı")
        self.r_on = QCheckBox(t("Bu eşya için tarif ekle"))
        self.r_on.setCursor(Qt.PointingHandCursor)
        r.add(self.r_on)
        items = self._item_ids()
        h = QHBoxLayout()
        h.setSpacing(14)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.r_cells = []
        for i in range(9):
            cb = item_combo(items, True)
            cb.setFixedWidth(170)
            cb.setIconSize(QSize(20, 20))
            cb.currentTextChanged.connect(lambda _txt, c=cb: self._cell_icon(c))
            grid.addWidget(cb, i // 3, i % 3)
            self.r_cells.append(cb)
        h.addLayout(grid)
        arrow = QLabel("→")
        arrow.setStyleSheet(f"font-size:28px; color:{TOKENS['text_muted']};")
        h.addWidget(arrow)
        res = QVBoxLayout()
        self.r_result = QLabel()
        self.r_result.setFixedSize(56, 56)
        self.r_result.setAlignment(Qt.AlignCenter)
        self.r_result.setStyleSheet(f"background:{TOKENS['surface_2']}; border-radius:6px;")
        self.r_count = QSpinBox()
        self.r_count.setRange(1, 64)
        self.r_count.setPrefix("× ")
        res.addWidget(self.r_result)
        res.addWidget(self.r_count)
        res.addStretch(1)
        h.addLayout(res)
        h.addStretch(1)
        r.add(h)
        self.col.addWidget(r)
        self.c_recipe = r

    def _build_actions(self):
        a = Card()
        self.who = QComboBox()
        self.who.setEditable(True)
        self.who.setMinimumWidth(180)
        self.who.lineEdit().setPlaceholderText(t("Oyuncu"))
        self.btn_save = button("Kaydet", "primary", self.save)
        self.btn_give = button("Oyuncuya Ver", "info", self.give)
        a.add(row(self.btn_save, None, self.who, self.btn_give, stretch_end=False))
        self.col.addWidget(a)
        self.c_actions = a

    def _build_pack(self):
        k = Card("Paketler", "İçerikleri oyuna eklemek için veri paketini ve kaynak paketini oluştur")
        self.pack_lbl = label("", "Muted", wrap=True, raw=True)
        k.add(self.pack_lbl)
        self.btn_build = button("Paketleri Oluştur", "primary", self.build)
        k.add(row(self.btn_build, None))
        k.add(label("Kaynak paketi (tablo resimleri, müzikler, dokular) oyunculara bir adresten indirtilir. "
                    "Spypaper açıkken paketi kendisi paylaşabilir: ev ağı ve Tailscale'de çalışır; internetteki "
                    "oyuncular için bu portu da yönlendirmen gerekir. İstersen paketi başka bir yere yükleyip adresini "
                    "Eklentiler → Kaynak Paketi'ne yazabilirsin.", "Muted", wrap=True))
        self.share = QCheckBox(t("Kaynak paketini Spypaper paylaşsın"))
        self.share.setCursor(Qt.PointingHandCursor)
        self.addr = QComboBox()
        self.addr.setEditable(True)
        self.addr.setMinimumWidth(200)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(DEFAULT_PORT)
        self.req = QCheckBox(t("Zorunlu"))
        k.add(row(self.share, self.addr, self.port, self.req, button("Uygula", "primary", self.apply_share),
                  stretch_end=False))
        self.col.addWidget(k)

    # ------------------------------------------------------------ yardımcılar
    def _item_ids(self):
        try:
            return [iid for iid, _ in self.app.players.translations.search_items("", limit=3000)]
        except Exception:
            return []

    def _icon_for(self, iid):
        from core.players import icon_path
        iid = (iid or "").replace("minecraft:", "")
        p = icon_path(iid, self.app.config.server_path) if iid else None
        if p:
            pm = QPixmap(p)
            if not pm.isNull():
                side = min(pm.width(), pm.height())
                return pm.copy(0, 0, side, side).scaled(32, 32, Qt.KeepAspectRatio, Qt.FastTransformation)
        return None

    def _cell_icon(self, cb):
        """Eşya ikonu metin kutusunun başında (liste öğesine dokunulmaz; dokunulursa yazılan metin silinir)."""
        pm = self._icon_for(cb.currentText().strip())
        act = getattr(cb, "_icon_act", None)
        if act is None:
            from PySide6.QtWidgets import QLineEdit as _LE
            act = cb._icon_act = cb.lineEdit().addAction(QIcon(), _LE.LeadingPosition)
        act.setIcon(QIcon(pm) if pm else QIcon())
        act.setVisible(pm is not None)

    def _version(self):
        return detect_version(self.app.config.server_path)[0]

    def _auto_id(self, text):
        if self.cur is not None and not self.cur.get("_id_locked"):
            self.f_id.setText(slug(text))

    # ------------------------------------------------------------ liste
    def on_show(self):
        fmt = C.Fmt(self._version())
        v = self._version()
        if not v:
            self.banner.setText(t("Sunucunun Minecraft sürümü bilinmiyor; sunucuyu bir kez başlatınca belirlenir."))
        elif not fmt.ok:
            self.banner.setText(t("İçerik editörü için sunucu en az Minecraft {v} olmalı.", v="1.21"))
        else:
            self.banner.setText("")
        self.banner.setVisible(bool(self.banner.text()))
        self.items = copy.deepcopy(self.app.config.get("content") or [])
        self.reload_list()
        names = sorted({p.name for p in self.app.players.list_players()}, key=str.lower)
        cur = self.who.currentText()
        self.who.clear()
        self.who.addItems(names)
        self.who.setEditText(cur)
        from core.remote import local_addresses
        self.addr.clear()
        for a in local_addresses():
            self.addr.addItem(a)
        hs = self.app.config.get("content_share") or {}
        if hs.get("address"):
            self.addr.setEditText(hs["address"])
        self.port.setValue(int(hs.get("port") or DEFAULT_PORT))
        self.share.setChecked(bool(hs.get("enabled")))
        self.req.setChecked(bool(hs.get("required")))
        self._pack_status()

    def reload_list(self, select=None):
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.items:
            it = QListWidgetItem(icons.icon(TYPE_ICON[c["type"]], TOKENS["text_muted"], 18),
                                 f"{c['name']}  ·  {t(C.TYPES[c['type']])}")
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.items:
            idx = select if select is not None else max(0, min(self.list.currentRow(), len(self.items) - 1))
            self.list.setCurrentRow(idx)
            self.select(idx)
        else:
            self.select(-1)

    def new_menu(self):
        m = QMenu(self)
        for key, name in C.TYPES.items():
            a = m.addAction(icons.icon(TYPE_ICON[key], TOKENS["text_muted"], 16), t(name))
            a.setData(key)
        act = m.exec(self.btn_new.mapToGlobal(self.btn_new.rect().bottomLeft()))
        if act:
            self.new(act.data())

    def new(self, kind):
        base = {"type": kind, "id": "", "name": "", "color": "", "lore": "",
                "recipe": {"enabled": False, "grid": [""] * 9, "count": 1}}
        base.update({"painting": {"width": 2, "height": 2, "author": "", "image": ""},
                     "disc": {"sound": "", "artist": "", "length": 60, "comparator": 1, "base": "music_disc_13"},
                     "tool": {"base": "diamond_sword", "damage": 7, "speed": 1.6, "durability": 0, "mining": 0,
                              "unbreakable": False, "glint": False, "enchants": []},
                     "food": {"base": "apple", "nutrition": 4, "saturation": 2.4, "seconds": 1.6,
                              "always_eat": False, "effects": []},
                     "hud": {"sprite": "heart/full", "image": ""}}[kind])
        self.items.append(base)
        self.reload_list(len(self.items) - 1)
        self.f_name.setFocus()

    def select(self, i):
        has = 0 <= i < len(self.items)
        for w in (self.c_common, self.types, self.c_recipe, self.c_actions):
            w.setVisible(has)
        hud = has and self.items[i]["type"] == "hud"
        self.c_recipe.setVisible(has and not hud)          # HUD verilen bir eşya değil: tarif ve "Oyuncuya Ver" yok
        for w in (self.who, self.btn_give):
            w.setVisible(not hud)
        for w in (self.f_color, self.f_lore):                # HUD'da ad rengi ve açıklama kullanılmaz
            self.common_form.setRowVisible(w, not hud)
        self.btn_del.setEnabled(has)
        if not has:
            self.cur = None
            return
        c = self.cur = self.items[i]
        c["_id_locked"] = bool(c.get("id"))
        self.f_type.setText(t(C.TYPES[c["type"]]))
        self.f_name.setText(c.get("name", ""))
        self.f_id.setText(c.get("id", ""))
        self.f_color.setCurrentIndex(max(0, self.f_color.findData(c.get("color", ""))))
        self.f_lore.setPlainText(c.get("lore", ""))
        self.types.setCurrentIndex(list(C.TYPES).index(c["type"]))
        k = c["type"]
        if k == "painting":
            self.p_w.setValue(int(c["width"]))
            self.p_h.setValue(int(c["height"]))
            self.p_author.setText(c.get("author", ""))
            self._repaint_painting()
        elif k == "disc":
            self.d_rights.setChecked(bool(c.get("rights_ok")))
            self.d_artist.setText(c.get("artist", ""))
            self.d_base.setCurrentText(c.get("base", "music_disc_13"))
            self.d_cmp.setValue(int(c.get("comparator", 1)))
            self.d_ng.setText(str(c.get("newgrounds") or ""))
            self._disc_info()
            self._tex_preview(self.d_tex)
        elif k == "tool":
            self.t_base.setEditText(c["base"])
            self.t_dmg.setValue(float(c["damage"]))
            self.t_spd.setValue(float(c["speed"]))
            self.t_dur.setValue(int(c.get("durability", 0)))
            self.t_mine.setValue(float(c.get("mining", 0)))
            self.t_unb.setChecked(bool(c.get("unbreakable")))
            self.t_glint.setChecked(bool(c.get("glint")))
            self._clear_enchants()
            for ename, elv in (c.get("enchants") or []):
                self.add_ench_row(ename.replace("minecraft:", ""), elv)
            self._tex_preview(self.t_tex)
        elif k == "hud":
            self.h_sprite.blockSignals(True)
            self.h_sprite.setCurrentIndex(max(0, self.h_sprite.findData(c.get("sprite", "heart/full"))))
            self.h_sprite.blockSignals(False)
            self._hud_preview()
        elif k == "food":
            self.f_base.setEditText(c["base"])
            self.f_nut.setValue(int(c["nutrition"]))
            self.f_sat.setValue(float(c["saturation"]))
            self.f_sec.setValue(float(c["seconds"]))
            self.f_always.setChecked(bool(c.get("always_eat")))
            effs = list(c.get("effects") or []) + [("", 10, 0)] * 3
            for (e, sec, amp), (en, es, ea) in zip(self.f_eff, effs[:3]):
                e.setCurrentText(en.replace("minecraft:", ""))
                sec.setValue(int(es))
                amp.setValue(int(ea) + 1)
            self._tex_preview(self.f_tex)
        rec = c.get("recipe") or {}
        self.r_on.setChecked(bool(rec.get("enabled")))
        for cb, g in zip(self.r_cells, (rec.get("grid") or [""] * 9)):
            cb.setEditText(g.replace("minecraft:", ""))
            self._cell_icon(cb)
        self.r_count.setValue(int(rec.get("count", 1)))
        base = C.base_item(c)
        pm = self._icon_for(base) if base else None
        self.r_result.setPixmap(pm.scaled(40, 40) if pm else QPixmap())

    def _collect(self):
        c = self.cur
        c["name"] = self.f_name.text().strip()
        c["id"] = self.f_id.text().strip().lower()
        c["color"] = self.f_color.currentData() or ""
        c["lore"] = self.f_lore.toPlainText()
        k = c["type"]
        if k == "painting":
            c.update(width=self.p_w.value(), height=self.p_h.value(), author=self.p_author.text().strip())
        elif k == "disc":
            c.update(artist=self.d_artist.text().strip(), base=self.d_base.currentText(), comparator=self.d_cmp.value(),
                     rights_ok=self.d_rights.isChecked())
        elif k == "tool":
            c.update(base=self.t_base.currentText().strip().replace("minecraft:", ""), damage=self.t_dmg.value(),
                     speed=self.t_spd.value(), durability=self.t_dur.value(), mining=self.t_mine.value(),
                     unbreakable=self.t_unb.isChecked(), glint=self.t_glint.isChecked(),
                     enchants=[(e.currentText(), lv.value()) for e, lv in self.t_ench if e.currentText()])
        elif k == "hud":
            c["sprite"] = self.h_sprite.currentData()
        elif k == "food":
            c.update(base=self.f_base.currentText().strip().replace("minecraft:", ""), nutrition=self.f_nut.value(),
                     saturation=self.f_sat.value(), seconds=self.f_sec.value(), always_eat=self.f_always.isChecked(),
                     effects=[(e.currentText(), s.value(), a.value() - 1) for e, s, a in self.f_eff if e.currentText()])
        c["recipe"] = {"enabled": self.r_on.isChecked(), "count": self.r_count.value(),
                       "grid": [cb.currentText().strip().replace("minecraft:", "") for cb in self.r_cells]}

    def save(self):
        if self.cur is None:
            return False
        self._collect()
        others = [x for x in self.items if x is not self.cur]
        if any(x.get("id") == self.cur["id"] for x in others):
            self.warn(t("'{id}' kimliği başka bir içerikte kullanılıyor.", id=self.cur["id"]))
            return False
        try:
            C.validate(self.cur, C.Fmt(self._version()))
        except C.ContentError as e:
            self.warn(t(e.template, **e.kw))
            return False
        self.cur["_id_locked"] = True
        self._store()
        self.reload_list(self.items.index(self.cur))
        self._pack_status(dirty=True)
        return True

    def _store(self):
        clean = [{k: v for k, v in x.items() if not k.startswith("_")} for x in self.items if x.get("id")]
        self.app.config.set("content", clean)

    def delete(self):
        if self.cur is None or not self.confirm(t("'{name}' silinsin mi?", name=self.cur.get("name") or "?")):
            return
        self.items.remove(self.cur)
        self._store()
        self.reload_list()
        self._pack_status(dirty=True)

    # ------------------------------------------------------------ dosyalar
    def _dest(self, name):
        d = C.content_dir(self.app.config.server_path)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, name)

    def _need_id(self):
        cid = self.f_id.text().strip().lower()
        if not C.ID_RE.match(cid):
            self.warn(t("Önce geçerli bir kimlik yaz (küçük harf, rakam, _)."))
            return None
        return cid

    def pick_image(self):
        cid = self._need_id()
        if not cid:
            return
        path, _ = QFileDialog.getOpenFileName(self, t("Resim Seç"), "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self.warn("Resim açılamadı.")
            return
        self.cur["_src_image"] = path
        self._save_painting(img)

    def _save_painting(self, img):
        w, h = self.p_w.value() * 16, self.p_h.value() * 16
        scaled = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x, y = (scaled.width() - w) // 2, (scaled.height() - h) // 2
        out = scaled.copy(x, y, w, h)
        name = f"{self.f_id.text().strip().lower()}.png"
        out.save(self._dest(name), "PNG")
        self.cur["image"] = name
        self._repaint_painting(reload=False)

    def _repaint_painting(self, *_a, reload=True):
        c = self.cur
        if not c or c["type"] != "painting":
            return
        if reload and c.get("_src_image"):              # boyut değişti: kaynak resimden yeniden kırp
            img = QImage(c["_src_image"])
            if not img.isNull():
                self._save_painting(img)
                return
        p = os.path.join(C.content_dir(self.app.config.server_path), c.get("image") or "")
        pm = QPixmap(p) if c.get("image") and os.path.exists(p) else QPixmap()
        self.p_preview.setPixmap(pm.scaled(150, 150, Qt.KeepAspectRatio, Qt.FastTransformation) if not pm.isNull() else QPixmap())
        if pm.isNull():
            self.p_preview.setText(t("Resim yok"))

    def _clear_enchants(self):
        while self.t_ench_box.count():
            item = self.t_ench_box.takeAt(0)
            lay = item.layout()
            if lay:
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.t_ench = []
        self.t_motion.setVisible(False)

    def add_ench_row(self, name="", level=1):
        if len(self.t_ench) >= ENCH_MAX:
            return
        h = QHBoxLayout()
        e = QComboBox()
        e.addItem("")
        e.addItems(ENCHANTS)
        e.setCurrentText(name)
        lv = QSpinBox()
        lv.setRange(1, ENCH_LEVEL_MAX)
        lv.setValue(int(level))
        e.currentTextChanged.connect(self._check_motion)
        lv.valueChanged.connect(self._check_motion)
        rm = button("×", "ghost", lambda: self.remove_ench_row(h, e, lv))
        h.addWidget(e, 1)
        h.addWidget(lv)
        h.addWidget(rm)
        self.t_ench_box.addLayout(h)
        self.t_ench.append((e, lv))
        self._check_motion()

    def remove_ench_row(self, layout, e, lv):
        self.t_ench = [(ee, ll) for ee, ll in self.t_ench if ee is not e]
        while layout.count():
            w = layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.t_ench_box.removeItem(layout)
        layout.deleteLater()
        self._check_motion()

    def _check_motion(self, *_a):
        """Oyuncuyu fırlatan büyüler vanilla sınırının üstündeyse: anti-hile eklentisi bunu uçma/hız hilesi sanabilir."""
        over = [(e.currentText(), lv.value()) for e, lv in self.t_ench
                if e.currentText() in MOTION_ENCHANTS and lv.value() > MOTION_ENCHANTS[e.currentText()]]
        if not over:
            self.t_motion.setVisible(False)
            return
        from core import guard as G
        names = ", ".join(f"{n} {lv}" for n, lv in over)
        text = t("{list}: oyuncuyu vanilla'da mümkün olmayan bir hızla fırlatır. Anti-hile eklentileri bunu uçma ya da "
                 "hız hilesi sanıp oyuncuyu geri çekebilir veya atabilir.", list=names)
        if G.active(self.app.config, "combat"):
            text += " " + t("Bu sunucuda Savaş Hilesi Denetimi açık.")
        self.t_motion.setText("⚠ " + text)
        self.t_motion.setVisible(True)

    def pick_hud(self):
        cid = self._need_id()
        if not cid or not self.cur:
            return
        key = self.h_sprite.currentData()
        _name, w, h = C.HUD_SPRITES[key]
        path, _ = QFileDialog.getOpenFileName(self, t("Resim Seç"), "", "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self.warn("Resim açılamadı.")
            return
        k = max(1, min(8, round(img.width() / w)))
        same_ratio = abs(img.width() / img.height() - w / h) < 0.06
        out = img.scaled(w * k, h * k, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        name = f"{cid}_hud.png"
        out.save(self._dest(name), "PNG")
        self.cur["image"] = name
        self.cur["sprite"] = key
        self._hud_preview()
        if not same_ratio:
            self.warn(t("Resmin en-boy oranı bu parçaya ({w}×{h}) uymuyor; sığdırmak için uzatıldı.", w=w, h=h))

    def _hud_preview(self, *_a):
        c = self.cur
        if not c or c["type"] != "hud":
            return
        key = self.h_sprite.currentData()
        _name, w, h = C.HUD_SPRITES[key]
        p = os.path.join(C.content_dir(self.app.config.server_path), c.get("image") or "")
        pm = QPixmap(p) if c.get("image") and os.path.exists(p) else QPixmap()
        if pm.isNull():
            self.h_preview.setPixmap(QPixmap())
            self.h_preview.setText(t("Resim yok"))
            self.h_info.setText(t("Boyut: {w}×{h} piksel", w=w, h=h))
            return
        scale = max(1, min(180 // max(pm.width(), 1), 80 // max(pm.height(), 1)))
        self.h_preview.setPixmap(pm.scaled(pm.width() * scale, pm.height() * scale, Qt.KeepAspectRatio, Qt.FastTransformation))
        self.h_info.setText(t("Boyut: {w}×{h} piksel", w=w, h=h) + " · " +
                            t("Kaydedilen: {w}×{h}", w=pm.width(), h=pm.height()))

    def pick_texture(self):
        cid = self._need_id()
        if not cid:
            return
        path, _ = QFileDialog.getOpenFileName(self, t("Doku Seç (16×16)"), "", "PNG (*.png)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            self.warn("Resim açılamadı.")
            return
        side = 16 if max(img.width(), img.height()) <= 16 else 32
        img = img.scaled(side, side, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        name = f"{cid}_item.png"
        img.save(self._dest(name), "PNG")
        self.cur["texture"] = name
        self._tex_preview(self._tex_box())

    def _tex_box(self):
        return {"tool": self.t_tex, "food": self.f_tex, "disc": self.d_tex}[self.cur["type"]]

    def _current_image(self, key):
        p = os.path.join(C.content_dir(self.app.config.server_path), self.cur.get(key) or "")
        return QImage(p) if self.cur.get(key) and os.path.exists(p) else None

    def design_texture(self):
        cid = self._need_id()
        if not cid:
            return
        from ..texture_designer import TextureDesigner
        from core import voxel
        vox = None
        vp = os.path.join(C.content_dir(self.app.config.server_path), self.cur.get("voxels") or "")
        if self.cur.get("voxels") and os.path.isfile(vp):
            vox = voxel.load(vp)
        dlg = TextureDesigner(self.cur["type"], 16, 16, self._current_image("texture"),
                              cube=self.cur.get("model") or False, voxels=vox, parent=self)
        if not dlg.exec():
            return
        name = f"{cid}_item.png"
        dlg.result_image().save(self._dest(name), "PNG")
        self.cur["texture"] = name
        if dlg.is_voxel():
            vname = f"{cid}_model.json"
            voxel.save(self._dest(vname), dlg.result_voxels())
            self.cur["voxels"] = vname
            self.cur["model"] = "voxel"
        elif dlg.is_cube():
            self.cur["model"] = "cube"
        else:
            self.cur.pop("model", None)
        self._tex_preview(self._tex_box())
        self._pack_status(dirty=True)

    def design_painting(self):
        cid = self._need_id()
        if not cid:
            return
        from ..texture_designer import TextureDesigner
        w, h = self.p_w.value() * 16, self.p_h.value() * 16
        dlg = TextureDesigner("painting", w, h, self._current_image("image"), allow_cube=False, parent=self)
        if dlg.exec():
            self.cur.pop("_src_image", None)
            self._save_painting(dlg.result_image())

    def design_hud(self):
        cid = self._need_id()
        if not cid or not self.cur:
            return
        from ..texture_designer import TextureDesigner
        key = self.h_sprite.currentData()
        _name, w, h = C.HUD_SPRITES[key]
        img = self._current_image("image") if self.cur.get("sprite") == key else None
        dlg = TextureDesigner("hud", w, h, img, allow_cube=False, parent=self)
        if not dlg.exec():
            return
        name = f"{cid}_hud.png"
        dlg.result_image().save(self._dest(name), "PNG")
        self.cur["image"] = name
        self.cur["sprite"] = key
        self._hud_preview()

    def clear_texture(self):
        if self.cur:
            self.cur.pop("texture", None)
            self.cur.pop("model", None)
            self.cur.pop("voxels", None)
            self._tex_preview(self._tex_box())

    def _tex_preview(self, box):
        c = self.cur
        p = os.path.join(C.content_dir(self.app.config.server_path), c.get("texture") or "") if c else ""
        pm = QPixmap(p) if c and c.get("texture") and os.path.exists(p) else QPixmap()
        box.preview.setPixmap(pm.scaled(32, 32, Qt.KeepAspectRatio, Qt.FastTransformation) if not pm.isNull() else QPixmap())

    def pick_sound(self):
        cid = self._need_id()
        if not cid:
            return
        path, _ = QFileDialog.getOpenFileName(self, t("Ses Dosyası Seç"), "", "Audio (*.mp3 *.ogg *.wav *.flac *.aiff *.aif)")
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read(60 * 1024 * 1024)
        self._convert(cid, os.path.splitext(os.path.basename(path))[0], "", data, None)

    def fetch_ng(self):
        sid = self.d_ng.text().strip()
        if not sid:
            return
        cid = self._need_id()
        if not cid:
            return
        self.d_ng_btn.setEnabled(False)
        self.d_info.setText(t("Newgrounds'tan indiriliyor…"))

        def work():
            try:
                title, artist, data = NG.fetch(sid)
                name = f"{cid}.ogg"
                length = C.to_ogg(data, self._dest(name))
                self.ng_done.emit((title, artist, name, length, sid), None)
            except Exception as e:
                self.ng_done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _convert(self, cid, title, artist, data, ng):
        """Dönüştürme arka planda; uzun parçalarda arayüz donmasın."""
        name = f"{cid}.ogg"
        dest = self._dest(name)
        self.d_ng_btn.setEnabled(False)
        self.d_info.setText(t("Ses dönüştürülüyor…"))

        def work():
            try:
                length = C.to_ogg(data, dest)
                self.ng_done.emit((title, artist, name, length, ng), None)
            except Exception as e:
                self.ng_done.emit(None, e)
        threading.Thread(target=work, daemon=True).start()

    def _ng_done(self, res, err):
        self.d_ng_btn.setEnabled(True)
        self.d_rights.setChecked(False)          # yeni ses: onay yeniden istenir
        if err is not None:
            msg = t(err.template, **err.kw) if hasattr(err, "template") else str(err)
            self.d_info.setText(msg)
            return
        title, artist, name, length, ng = res
        c = self.cur
        if not c or c["type"] != "disc":
            return
        c.update(sound=name, length=length, newgrounds=ng or "")
        c.pop("soundcloud", None)
        if not self.f_name.text().strip():
            self.f_name.setText(title)
            self._auto_id(title)
        if artist and not self.d_artist.text().strip():
            self.d_artist.setText(artist)
        self._disc_info()

    def _disc_info(self):
        c = self.cur
        if c and c.get("sound"):
            m, s = divmod(int(float(c.get("length", 0))), 60)
            src = f"Newgrounds #{c['newgrounds']}" if c.get("newgrounds") else t("kendi dosyan")
            self.d_info.setText(t("Ses hazır: {file} · {len} · kaynak: {src}", file=c["sound"], len=f"{m}:{s:02}", src=src))
        else:
            self.d_info.setText(t("Henüz ses yok."))

    # ------------------------------------------------------------ paket
    def _pack_status(self, dirty=False):
        sp = self.app.config.server_path
        rp = os.path.join(sp, "spypaper_resourcepack.zip")
        n = len([x for x in self.items if x.get("id")])
        txt = t("{n} içerik.", n=n)
        if os.path.exists(rp):
            txt += " " + t("Kaynak paketi: {size} KB.", size=os.path.getsize(rp) // 1024)
        if dirty:
            txt += " <b>" + t("Değişiklikler için paketleri yeniden oluştur.") + "</b>"
        self.pack_lbl.setText(txt)

    def build(self):
        if self.cur is not None and self.cur.get("id") and not self.save():
            return
        items = [x for x in self.items if x.get("id")]
        try:
            level = level_name(self.app.properties)
            from core import spymods as SM
            dp, rp = C.build(self.app.config.server_path, level, self._version(), items,
                             SM.rp_files(self.app.config.get("spymods_rp") or []))
        except Exception as e:
            text = t(e.template, **e.kw) if hasattr(e, "template") else str(e)
            self.error((f"{e.item}: " if getattr(e, "item", None) else "") + text)
            return
        msg = [t("Veri paketi oluşturuldu: {path}", path=os.path.relpath(dp, self.app.config.server_path))]
        if rp:
            msg.append(t("Kaynak paketi: {file}", file=os.path.basename(rp)))
            if (self.app.config.get("content_share") or {}).get("enabled"):
                self.apply_share(quiet=True)
        if self.app.server.is_running:
            self.app.server.try_send("reload")
            self.app.server.try_send('datapack enable "file/spypaper_content"')
        msg.append(t("Tablo ve müzik diskleri sunucu yeniden başlatılınca görünür; aletler ve yiyecekler /reload ile gelir."))
        self.info("\n".join(msg))
        self._pack_status()

    def apply_share(self, quiet=False):
        sp = self.app.config.server_path
        rp = os.path.join(sp, "spypaper_resourcepack.zip")
        cfg = {"enabled": self.share.isChecked(), "address": self.addr.currentText().strip(),
               "port": self.port.value(), "required": self.req.isChecked()}
        self.app.config.set("content_share", cfg)
        if not cfg["enabled"]:
            HOST.unregister(self.app.id)
            if not quiet:
                self.info("Paylaşım kapatıldı.")
            return
        if not os.path.exists(rp):
            if not quiet:
                self.warn("Önce paketleri oluştur (kaynak paketi gerektiren bir içerik yok ya da paket henüz oluşturulmadı).")
            return
        if not cfg["address"]:
            self.warn("Paylaşım adresi seç.")
            return
        try:
            HOST.start(cfg["port"])
        except OSError as e:
            self.error(t("Port {port} açılamadı: {e}", port=cfg["port"], e=str(e)))
            return
        sha = C.sha1_file(rp)
        HOST.register(self.app.id, rp, sha)
        from core import modrinth as M
        from core import guard as G
        required = cfg["required"] or G.active(self.app.config, "captcha")   # Bot Doğrulaması paketi zorunlu kılar
        M.set_resource_pack(self.app.properties, HOST.url(cfg["address"], self.app.id, sha), sha, required)
        if not quiet:
            self.info(t("Kaynak paketi paylaşılıyor: {url}", url=HOST.url(cfg["address"], self.app.id, sha)) + "\n" +
                      t("Değişiklik sunucu yeniden başlatılınca geçerli olur."))

    def give(self):
        who = self.who.currentText().strip()
        if not self.cur or not self.cur.get("id") or not who:
            return
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}|@[aprs]", who):
            self.warn(t("Geçersiz oyuncu adı: {name}", name=who))
            return
        self.send(C.give_command(who, self.cur, self._version()))


def rebuild_packs(app):
    """İçerik ve Spypaper Modları paketlerini kayıtlı ayarlarla yeniden üretir; paylaşım açıksa yeni paketi yayınlar.
    (kaynak_paketi_yolu ya da None, paylaşıldı_mı). Hata olursa istisna fırlatır."""
    from core import guard as G, modrinth as M, spymods as SM
    sp = app.config.server_path
    version = detect_version(sp)[0]
    fmt = C.Fmt(version)
    items, skipped = [], []
    for x in app.config.get("content") or []:
        if not x.get("id"):
            continue
        try:
            C.validate(x, fmt)            # yarım kalmış içerik (ör. sesi olmayan disk) paketi bozmasın: atlanır
            items.append(x)
        except Exception:
            skipped.append(x.get("name") or x["id"])
    app.last_skipped_content = skipped
    from core import playermsg
    extra = SM.rp_files(app.config.get("spymods_rp") or [])
    if items or extra or (app.config.get("content_share") or {}).get("enabled"):
        extra.update(playermsg.lang_files())         # Spypaper'ın oyuncu mesajları oyuncunun kendi dilinde
    _, rp = C.build(sp, level_name(app.properties), version, items, extra)
    cfg = app.config.get("content_share") or {}
    if not (rp and cfg.get("enabled") and cfg.get("address")):
        if not rp:
            HOST.unregister(app.id)
            cur = M.current_resource_pack(app.properties).get("url") or ""
            if f"/{app.id}/" in cur and str(int(cfg.get("port") or DEFAULT_PORT)) in cur:
                M.clear_resource_pack(app.properties)        # artık paket yok: oyunculara olmayan adres gönderilmesin
        return rp, False
    HOST.start(int(cfg.get("port") or DEFAULT_PORT))
    sha = C.sha1_file(rp)
    HOST.register(app.id, rp, sha)
    required = cfg.get("required") or G.active(app.config, "captcha")
    M.set_resource_pack(app.properties, HOST.url(cfg["address"], app.id, sha), sha, required)
    return rp, True


def restore_sharing(settings_servers):
    """Spypaper açılınca paylaşımı açık sunucuların paketlerini yeniden yayınlar."""
    for prof in settings_servers:
        cfg = prof.get("content_share") or {}
        rp = os.path.join(prof.server_path or "", "spypaper_resourcepack.zip")
        if cfg.get("enabled") and os.path.exists(rp):
            try:
                HOST.start(int(cfg.get("port") or DEFAULT_PORT))
                HOST.register(prof.id, rp, C.sha1_file(rp))
            except OSError as e:
                print(f"[paket] {prof.name}: {e}")


N_("İçerik Editörü")
