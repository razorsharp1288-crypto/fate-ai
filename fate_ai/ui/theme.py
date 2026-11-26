"""FATE AI design tokens and Qt stylesheet (black + deep purple)."""
from __future__ import annotations

C = {
    "bg": "#07060B",
    "bg2": "#0D0B14",
    "panel": "#12101B",
    "card": "#171422",
    "card_hi": "#1E1A2C",
    "border": "#2A2440",
    "border_hi": "#3D3360",
    "text": "#ECE9F5",
    "muted": "#9A93B3",
    "dim": "#6B6485",
    "accent": "#8B5CF6",
    "accent_hi": "#A78BFA",
    "accent_lo": "#5B21B6",
    "accent_glow": "rgba(139,92,246,0.18)",
    "ok": "#34D399",
    "warn": "#FBBF24",
    "err": "#F87171",
    "info": "#60A5FA",
    "user_bubble": "#2A1F4A",
    "ai_bubble": "#14121D",
    "code_bg": "#0B0A12",
}

FONT_STACK = '"Segoe UI Variable", "Segoe UI", "Inter", "Noto Sans", sans-serif'
MONO_STACK = '"Cascadia Code", "Cascadia Mono", Consolas, "JetBrains Mono", "DejaVu Sans Mono", monospace'


def stylesheet() -> str:
    c = C
    return f"""
* {{ font-family: {FONT_STACK}; font-size: 13px; color: {c['text']}; }}
QMainWindow, QDialog, QWidget#Page, QStackedWidget {{ background: {c['bg']}; }}
QWidget#Sidebar {{ background: {c['bg2']}; border-right: 1px solid {c['border']}; }}
QLabel#Brand {{ font-size: 18px; font-weight: 700; letter-spacing: 3px; color: {c['text']}; }}
QLabel#BrandSub {{ color: {c['accent_hi']}; font-size: 10px; letter-spacing: 2px; }}
QListWidget#Nav {{ background: transparent; border: none; outline: 0; padding: 4px; }}
QListWidget#Nav::item {{ padding: 9px 12px; border-radius: 9px; margin: 1px 4px; color: {c['muted']}; }}
QListWidget#Nav::item:hover {{ background: {c['card']}; color: {c['text']}; }}
QListWidget#Nav::item:selected {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {c['accent_lo']}, stop:1 #2E1B5C);
    color: white; }}
QLabel#PageTitle {{ font-size: 24px; font-weight: 700; }}
QLabel#PageSubtitle {{ color: {c['muted']}; font-size: 13px; }}
QLabel#H2 {{ font-size: 15px; font-weight: 650; }}
QLabel#Muted {{ color: {c['muted']}; }}
QLabel#Dim {{ color: {c['dim']}; font-size: 12px; }}
QLabel#StatValue {{ font-size: 26px; font-weight: 700; }}
QLabel#StatLabel {{ color: {c['muted']}; font-size: 12px; }}
QLabel#Badge {{ border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600; }}
QFrame#Card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#CardAccent {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #24164A, stop:1 {c['card']});
    border: 1px solid {c['border_hi']}; border-radius: 14px; }}
QFrame#Banner {{ background: {c['accent_glow']}; border: 1px solid {c['border_hi']}; border-radius: 10px; }}
QFrame#WarnBanner {{ background: rgba(251,191,36,0.10); border: 1px solid rgba(251,191,36,0.35); border-radius: 10px; }}
QPushButton {{ background: {c['card_hi']}; border: 1px solid {c['border']}; border-radius: 9px; padding: 7px 14px; }}
QPushButton:hover {{ border-color: {c['accent']}; background: #251F38; }}
QPushButton:pressed {{ background: {c['accent_lo']}; }}
QPushButton:disabled {{ color: {c['dim']}; background: {c['panel']}; border-color: {c['panel']}; }}
QPushButton#Primary {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7C3AED, stop:1 #9F67FF);
    border: none; color: white; font-weight: 600; }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #8B5CF6, stop:1 #B794FF); }}
QPushButton#Primary:disabled {{ background: #3B2F5C; color: #9A93B3; }}
QPushButton#Danger {{ background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.45); color: #FCA5A5; }}
QPushButton#Danger:hover {{ background: rgba(248,113,113,0.25); }}
QPushButton#Danger:disabled {{ background: {c['panel']}; color: {c['dim']}; border-color: {c['panel']}; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {c['muted']}; padding: 4px 8px; }}
QPushButton#Ghost:hover {{ color: {c['text']}; background: {c['card']}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {c['accent_lo']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['border_hi']};
    selection-background-color: {c['accent_lo']}; outline: 0; }}
QTextBrowser {{ background: {c['bg']}; border: none; }}
QTableWidget, QTableView, QTreeWidget, QListWidget {{ background: {c['panel']}; border: 1px solid {c['border']};
    border-radius: 10px; gridline-color: {c['border']}; alternate-background-color: {c['card']}; outline: 0; }}
QTableWidget::item, QTreeWidget::item, QListWidget::item {{ padding: 5px; }}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {c['accent_lo']}; color: white; }}
QHeaderView::section {{ background: {c['card']}; color: {c['muted']}; border: none;
    border-bottom: 1px solid {c['border']}; padding: 7px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 10px; top: -1px; background: {c['bg2']}; }}
QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 8px 16px; border: none;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
QTabBar::tab:hover {{ color: {c['text']}; }}
QProgressBar {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px; height: 12px;
    text-align: center; font-size: 10px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #6D28D9, stop:1 #A78BFA);
    border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 6px; background: {c['border']}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; margin: -6px 0; border-radius: 8px;
    border: 2px solid {c['accent']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {c['border_hi']}; background: {c['panel']}; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border_hi']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['accent_lo']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border_hi']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: {c['card_hi']}; color: {c['text']}; border: 1px solid {c['border_hi']}; padding: 6px;
    border-radius: 6px; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['border_hi']}; padding: 4px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['accent_lo']}; }}
QSplitter::handle {{ background: {c['border']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 10px; margin-top: 14px; padding: 12px 10px 10px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {c['accent_hi']}; }}
QStatusBar {{ background: {c['bg2']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
"""


def chat_css() -> str:
    c = C
    return f"""
body {{ font-family: {FONT_STACK}; color: {c['text']}; font-size: 14px; }}
.row {{ margin: 6px 0 14px 0; }}
.who {{ font-size: 11px; color: {c['muted']}; font-weight: 600; letter-spacing: 1px; margin-bottom: 4px; }}
.who-ai {{ color: {c['accent_hi']}; }}
p.who {{ margin: 0 0 4px 0; }}
p.actions {{ margin: 6px 0 0 0; }}
.actions a {{ color: {c['dim']}; text-decoration: none; font-size: 11px; margin-right: 12px; }}
pre {{ background: {c['code_bg']}; border: 1px solid {c['border']}; padding: 10px; font-family: {MONO_STACK};
      font-size: 12.5px; white-space: pre-wrap; }}
code {{ font-family: {MONO_STACK}; background: {c['code_bg']}; color: #D8B4FE; }}
a {{ color: {c['accent_hi']}; }}
table {{ border-collapse: collapse; }}
.md th, .md td {{ border: 1px solid {c['border']}; padding: 4px 8px; }}
blockquote {{ color: {c['muted']}; border-left: 3px solid {c['accent']}; padding-left: 10px; margin-left: 0; }}
"""
