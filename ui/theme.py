"""Tüm görünüm burada. Figma tasarımına uyarlamak için bu dosyayı değiştir.

PRESETS: hazır panel tasarımları (renk setleri). Yeni tasarım eklemek için
PRESETS'e bir girdi eklemen yeterli; ana ekrandaki "Panel Tasarımları"
sekmesinde otomatik görünür.
TOKENS: o an etkin renkler. apply() ile yerinde güncellenir.
"""
import re

from core import N_

BASE = {
    # yüzeyler
    "bg": "#101010", "sidebar": "#161616", "surface": "#1a1a1a", "surface_alt": "#1d1d1d",
    "surface_2": "#232323", "surface_3": "#2c2c2c", "border": "#2a2a2a", "scroll": "#3a3a3a",
    # yazı
    "text": "#e8e8e8", "text_muted": "#8a8a8a", "text_on_accent": "#0b0b0b",
    # vurgular
    "accent": "#5cda60", "accent_hover": "#6fe673",
    "danger": "#f44336", "warn": "#ffb703", "info": "#2196f3", "purple": "#9c6cf0",
    # ölçüler
    "radius": "8px", "radius_sm": "6px",
    "font": "Segoe UI", "font_mono": "Consolas", "font_size": "10pt",
}

# ad -> (görünen ad, açıklama, değişen tokenlar)
PRESETS = {
    "gece": (N_("Gece"), N_("Varsayılan koyu tema, yeşil vurgu"), {}),
    "okyanus": (N_("Okyanus"), N_("Lacivert yüzeyler, mavi vurgu"), {
        "bg": "#0b1220", "sidebar": "#0f182a", "surface": "#121c30", "surface_alt": "#15203a",
        "surface_2": "#1a2640", "surface_3": "#22304f", "border": "#1f2b45", "scroll": "#2c3c60",
        "accent": "#4aa8ff", "accent_hover": "#6cb9ff", "text_on_accent": "#06101f",
    }),
    "mor": (N_("Gece Moru"), N_("Koyu mor tonlar"), {
        "bg": "#110d18", "sidebar": "#161020", "surface": "#1b1426", "surface_alt": "#1f182c",
        "surface_2": "#251c33", "surface_3": "#30243f", "border": "#2b2138", "scroll": "#43325a",
        "accent": "#b48cff", "accent_hover": "#c4a3ff", "text_on_accent": "#130b20",
    }),
    "amber": (N_("Kehribar"), N_("Sıcak koyu tema, turuncu vurgu"), {
        "bg": "#14110d", "sidebar": "#1a1611", "surface": "#1f1a14", "surface_alt": "#231d16",
        "surface_2": "#2a231a", "surface_3": "#352c21", "border": "#2f271d", "scroll": "#4a3d2c",
        "accent": "#ffb347", "accent_hover": "#ffc46b", "text_on_accent": "#1a1206",
    }),
    "grafit": (N_("Grafit"), N_("Nötr gri, düşük doygunluk"), {
        "bg": "#17181a", "sidebar": "#1c1d20", "surface": "#212226", "surface_alt": "#242529",
        "surface_2": "#2a2b30", "surface_3": "#33353b", "border": "#2e3035", "scroll": "#44464d",
        "accent": "#d6d9df", "accent_hover": "#eceef2", "text_on_accent": "#121316",
    }),
    "acik": (N_("Açık"), N_("Aydınlık ortamlar için açık tema"), {
        "bg": "#f3f4f6", "sidebar": "#ffffff", "surface": "#ffffff", "surface_alt": "#f8f9fb",
        "surface_2": "#eef0f3", "surface_3": "#e2e6eb", "border": "#dde1e6", "scroll": "#c5cad2",
        "text": "#16181d", "text_muted": "#646b78", "text_on_accent": "#ffffff",
        "accent": "#1f9d4c", "accent_hover": "#22b057",
    }),
    "kontrast": (N_("Yüksek Kontrast"), N_("Siyah zemin, en yüksek okunabilirlik"), {
        "bg": "#000000", "sidebar": "#000000", "surface": "#000000", "surface_alt": "#0a0a0a",
        "surface_2": "#111111", "surface_3": "#222222", "border": "#ffffff", "scroll": "#ffffff",
        "text": "#ffffff", "text_muted": "#d0d0d0", "text_on_accent": "#000000",
        "accent": "#00ff7f", "accent_hover": "#66ffb2", "danger": "#ff5c5c", "warn": "#ffd400",
        "info": "#5cc8ff", "purple": "#d0a8ff",
    }),
}

TOKENS = dict(BASE)
_scale = 1.0


def apply(preset="gece", high_contrast=False, font_scale=1.0):
    """TOKENS'ı yerinde günceller (modüller aynı sözlüğü gördüğü için)."""
    global _scale
    TOKENS.clear()
    TOKENS.update(BASE)
    TOKENS.update(PRESETS.get(preset, PRESETS["gece"])[2])
    if high_contrast and preset != "kontrast":
        light = preset == "acik"
        TOKENS.update({
            "text": "#000000" if light else "#ffffff",
            "text_muted": "#30343b" if light else "#cfcfcf",
            "border": "#5b616b" if light else "#6a6a6a",
        })
    _scale = max(0.8, min(1.6, float(font_scale)))


def is_light():
    return TOKENS["bg"].lower() > "#888888"


def log_colors():
    return {"error": TOKENS["danger"], "warn": TOKENS["warn"], "cmd": TOKENS["info"],
            "info": TOKENS["text_muted"], "plain": TOKENS["text"]}


def button_variants():
    return {
        "primary": (TOKENS["accent"], TOKENS["text_on_accent"], TOKENS["accent_hover"]),
        "danger": (TOKENS["danger"], "#ffffff", "#ff5a4d"),
        "warn": (TOKENS["warn"], "#111111", "#ffc53a"),
        "info": (TOKENS["info"], "#ffffff", "#42a5f5"),
        "purple": (TOKENS["purple"], "#ffffff", "#ad85f5"),
        "ghost": (TOKENS["surface_2"], TOKENS["text"], TOKENS["surface_3"]),
        "flat": ("transparent", TOKENS["text"], TOKENS["surface_2"]),
    }


def status(state):
    """Sunucu durumu -> (Türkçe kaynak metin, renk)."""
    return {
        "stopped": (N_("Kapalı"), TOKENS["danger"]),
        "starting": (N_("Başlatılıyor…"), TOKENS["warn"]),
        "running": (N_("Çalışıyor"), TOKENS["accent"]),
        "stopping": (N_("Kapanıyor…"), TOKENS["warn"]),
    }[state]


def rgba(hex_color, alpha):
    c = hex_color.lstrip("#")
    return f"rgba({int(c[0:2], 16)},{int(c[2:4], 16)},{int(c[4:6], 16)},{alpha})"


QSS = """
* {{ font-family: "{font}"; font-size: {font_size}; color: {text}; }}
QMainWindow, QWidget#Root {{ background: {bg}; }}
QWidget#Page {{ background: {bg}; }}

/* --- kenar çubuğu --- */
QWidget#Sidebar {{ background: {sidebar}; border-right: 1px solid {border}; }}
QLabel#Brand {{ font-size: 15pt; font-weight: 700; padding: 18px 18px 4px 18px; }}
QLabel#BrandSub {{ color: {text_muted}; font-size: 8.5pt; padding: 0 18px 14px 18px; }}
QPushButton#NavButton {{
    text-align: left; padding: 9px 14px; margin: 1px 10px;
    border: none; border-radius: {radius_sm}; background: transparent; color: {text_muted};
}}
QPushButton#NavButton:hover {{ background: {surface_2}; color: {text}; }}
QPushButton#NavButton:checked {{ background: {surface_3}; color: {accent}; font-weight: 600; }}

/* --- üst bar --- */
QWidget#TopBar {{ background: {bg}; border-bottom: 1px solid {border}; }}
QLabel#PageTitle {{ font-size: 14pt; font-weight: 700; }}
QLabel#StatusPill {{ border-radius: 11px; padding: 3px 12px; font-weight: 600; font-size: 9pt; }}
QPushButton#IconButton {{
    background: transparent; border: none; border-radius: {radius_sm};
    font-size: 15pt; padding: 2px 9px; color: {text};
}}
QPushButton#IconButton:hover {{ background: {surface_2}; }}

/* --- ayarlar çekmecesi --- */
QWidget#Scrim {{ background: rgba(0,0,0,150); }}
QWidget#Drawer {{ background: {sidebar}; border-right: 1px solid {border}; }}
QLabel#DrawerTitle {{ font-size: 13pt; font-weight: 700; }}
QLabel#Section {{ color: {text_muted}; font-size: 8pt; font-weight: 700; padding-top: 8px; }}
QPushButton#DrawerItem {{
    text-align: left; padding: 8px 10px; border: none; border-radius: {radius_sm};
    background: transparent; color: {text};
}}
QPushButton#DrawerItem:hover {{ background: {surface_2}; }}

/* --- ana ekran --- */
QLabel#HomeTitle {{ font-size: 20pt; font-weight: 800; }}
QFrame#ServerCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#ServerCard:hover {{ border-color: {accent}; }}
QFrame#ThemeCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
QFrame#ThemeCard[active="true"] {{ border: 2px solid {accent}; }}
QLabel#ServerName {{ font-size: 12.5pt; font-weight: 700; }}
QLabel#Badge {{ border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }}
QLabel#ServerIcon {{ background: {surface_2}; border-radius: 10px; font-size: 18pt; font-weight: 800; color: {accent}; }}

/* --- kartlar --- */
QFrame#Card {{ background: {surface}; border: 1px solid {border}; border-radius: {radius}; }}
QLabel#CardTitle {{ font-weight: 700; font-size: 10.5pt; }}
QLabel#Muted {{ color: {text_muted}; }}
QLabel#BigValue {{ font-size: 17pt; font-weight: 700; }}

/* --- input --- */
QLineEdit, QSpinBox, QPlainTextEdit, QComboBox {{
    background: {surface_2}; border: 1px solid {border}; border-radius: {radius_sm};
    padding: 6px 9px; selection-background-color: {accent}; selection-color: {text_on_accent};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {accent}; }}
QLineEdit#Mono {{ font-family: "{font_mono}"; color: {accent}; }}
QTextBrowser {{ background: {surface}; border: 1px solid {border}; border-radius: {radius_sm}; padding: 10px; }}
QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {text_muted}; padding: 7px 14px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent; }}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; font-weight: 600; }}
QPlainTextEdit#Console {{ font-family: "{font_mono}"; font-size: 9.5pt; background: {surface}; padding: 8px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {surface_2}; border: 1px solid {border}; selection-background-color: {surface_3}; selection-color: {accent}; }}

/* --- liste ve tablo --- */
QListWidget, QTableWidget {{
    background: {surface}; border: 1px solid {border}; border-radius: {radius};
    outline: none; gridline-color: {border}; alternate-background-color: {surface_alt};
}}
QListWidget::item {{ padding: 7px 10px; border-radius: {radius_sm}; margin: 1px 4px; }}
QListWidget::item:hover {{ background: {surface_2}; }}
QListWidget::item:selected {{ background: {surface_3}; color: {accent}; }}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background: {surface_3}; color: {accent}; }}
QHeaderView::section {{
    background: {surface_2}; color: {text_muted}; border: none; border-bottom: 1px solid {border};
    padding: 7px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {surface_2}; border: none; }}

/* --- segment (alt sekmeler) --- */
QPushButton#Segment {{
    background: transparent; border: none; border-radius: {radius_sm};
    padding: 6px 12px; color: {text_muted};
}}
QPushButton#Segment:hover {{ color: {text}; background: {surface_2}; }}
QPushButton#Segment:checked {{ background: {surface_3}; color: {accent}; font-weight: 600; }}

/* --- onay kutusu (toggle görünümü) --- */
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: {surface_3}; border: 1px solid {border}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

QSlider::groove:horizontal {{ height: 4px; background: {surface_3}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {text}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}

/* --- kaydırma çubuğu --- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {surface_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {scroll}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QProgressBar {{ background: {surface_2}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

QMenu {{ background: {surface_2}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {surface_3}; color: {accent}; }}
QMessageBox, QDialog, QInputDialog {{ background: {surface}; }}
QToolTip {{ background: {surface_2}; color: {text}; border: 1px solid {border}; padding: 4px; }}
"""

BUTTON_QSS = """
QPushButton[variant="{name}"] {{
    background: {bg}; color: {fg}; border: none; border-radius: {radius_sm};
    padding: 7px 14px; font-weight: 600;
}}
QPushButton[variant="{name}"]:hover {{ background: {hover}; }}
QPushButton[variant="{name}"]:pressed {{ padding-top: 8px; padding-bottom: 6px; }}
QPushButton[variant="{name}"]:disabled {{ background: {surface_2}; color: {text_muted}; }}
"""


def _scale_pt(css):
    return re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * _scale:.1f}pt", css)


def stylesheet():
    css = QSS.format(**TOKENS)
    rest = {k: v for k, v in TOKENS.items() if k != "bg"}
    for name, (bg, fg, hover) in button_variants().items():
        css += BUTTON_QSS.format(name=name, bg=bg, fg=fg, hover=hover, **rest)
    return _scale_pt(css)
