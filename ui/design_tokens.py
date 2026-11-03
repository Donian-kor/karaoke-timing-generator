# -*- coding: utf-8 -*-
"""공통 디자인 토큰과 QSS 스타일시트 (pyside6-gui-design / pyside6-ui 원칙 적용).

karaoke_gui.py와 audio_editor.py에서 중복되던 DESIGN_TOKENS와
_build_design_qss()를 이 모듈에 중앙화한다.
"""

from PySide6.QtWidgets import QApplication

# ─── 디자인 토큰 ───
DESIGN_TOKENS = {
    "colors": {
        "primary": "#1976D2",
        "primary_hover": "#1565C0",
        "primary_pressed": "#0D47A1",
        "accent": "#FF4081",
        "success": "#4CAF50",
        "danger": "#F44336",
        "warning": "#FFC107",
        "neutral-50": "#FAFAFA",
        "neutral-100": "#F5F5F5",
        "neutral-200": "#EEEEEE",
        "neutral-900": "#212121",
        "text-secondary": "#757575",
        "border": "#BDBDBD",
        "input_bg": "#FFFFFF",
        "focus_ring": "#1976D2",
    },
    "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32},
    "radius": {"sm": 0, "md": 0, "lg": 0},
    "font": {
        "size_small": 9,
        "size_base": 11,
        "size_large": 14,
        "size_xl": 18,
        "family": "Inter, Segoe UI, sans-serif",
    },
}


def _build_design_qss() -> str:
    """애플리케이션 전체에 적용할 QSS 스타일시트를 반환한다."""
    c = DESIGN_TOKENS["colors"]
    r = DESIGN_TOKENS["radius"]
    s = DESIGN_TOKENS["spacing"]
    f = DESIGN_TOKENS["font"]
    return f"""
        QWidget, QDialog {{
            font-family: {f['family']};
            font-size: {f['size_base']}pt;
            color: {c['neutral-900']};
            background-color: {c['neutral-50']};
        }}
        QLabel {{ color: {c['neutral-900']}; background-color: transparent; }}
        QLabel[accent="true"] {{ color: {c['primary']}; font-weight: 700; }}
        QLabel[textColor="secondary"] {{ color: {c['text-secondary']}; }}
        QPushButton {{
            background-color: {c['primary']};
            color: white;
            padding: 6px 16px;
            border-radius: {r['md']}px;
            border: none;
            font-weight: 600;
            min-height: 28px;
        }}
        QPushButton:hover {{ background-color: {c['primary_hover']}; }}
        QPushButton:pressed {{ background-color: {c['primary_pressed']}; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton:disabled {{ background-color: #94A3B8; color: #F8FAFC; }}
        QPushButton:focus {{ border: 2px solid {c['focus_ring']}; }}
        QPushButton[secondary="true"] {{
            background-color: {c['neutral-100']};
            color: {c['neutral-900']};
            border: 1px solid {c['border']};
        }}
        QPushButton[secondary="true"]:hover {{ background-color: {c['neutral-200']}; }}
        QPushButton[secondary="true"]:pressed {{ background-color: #CBD5E1; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton[success="true"] {{ background-color: {c['success']}; color: white; }}
        QPushButton[success="true"]:hover {{ background-color: #16A34A; }}
        QPushButton[success="true"]:pressed {{ background-color: #15803D; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton[danger="true"] {{ background-color: {c['danger']}; color: white; }}
        QPushButton[danger="true"]:hover {{ background-color: #DC2626; }}
        QPushButton[danger="true"]:pressed {{ background-color: #B91C1C; padding-top: 7px; padding-bottom: 5px; }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            border: 1px solid {c['border']};
            border-radius: {r['sm']}px;
            padding: 6px 10px;
            background-color: {c['input_bg']};
            min-height: 28px;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {c['focus_ring']};
            border-width: 2px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['input_bg']};
            color: {c['neutral-900']};
            selection-background-color: #DBEAFE;
            selection-color: #1E3A8A;
            border: 1px solid {c['border']};
            outline: none;
        }}
        QFrame[section="true"] {{
            border: 1px solid {c['border']};
            border-radius: {r['md']}px;
            background-color: {c['neutral-50']};
            margin-top: {round(s['lg'] * 0.3)}px;
            margin-bottom: {round(s['lg'] * 0.3)}px;
            padding: {round(s['md'] * 0.5)}px {round(s['md'] * 0.5)}px {round(s['xs'] * 0.5)}px {round(s['md'] * 0.5)}px;
        }}
        #settingsSection {{
            background-color: #F0F7FF;
        }}
        #lyricsSection {{
            background-color: #F5F3FF;
        }}
        #previewSection {{
            background-color: #E2E8F0;
            border: none;
            border-bottom: 1px solid #CBD5E1;
            padding: 0;
            margin-top: 0;
            margin-bottom: 0;
        }}
        #previewContent {{
            background: transparent;
        }}
        #sideMenu {{
            background-color: #EEF2F7;
            border: none;
            border-right: 1px solid {c['border']};
        }}
        #sideMenuButton {{
            background-color: transparent;
            color: #334155;
            border: none;
            border-left: 3px solid transparent;
            padding: 13px 10px;
            text-align: left;
            font-weight: 600;
        }}
        #sideMenuButton:hover {{
            background-color: #E2E8F0;
        }}
        #sideMenuButton:checked {{
            background-color: {c['input_bg']};
            color: {c['primary']};
            border-left: 3px solid {c['primary']};
            font-weight: 800;
        }}
        QFrame[section="true"] QLabel[sectionTitle="true"] {{
            font-size: {f['size_large']}pt;
            font-weight: 800;
            color: {c['primary']};
            padding-left: {s['xs']}px;
            padding-bottom: {s['xs']}px;
            background-color: transparent;
            border: none;
            border-bottom: 2px solid {c['primary']};
            margin-bottom: {s['sm']}px;
        }}
        QSlider::groove:horizontal {{
            border: none;
            height: 6px;
            background: {c['neutral-200']};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {c['primary']};
            border: none;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {c['primary_hover']};
        }}
        QSlider#trackVolumeSlider::groove:horizontal {{
            background: #0F766E;
        }}
        QSlider#trackVolumeSlider {{
            background: transparent;
        }}
        QSlider#trackVolumeSlider::handle:horizontal {{
            background: #0F766E;
        }}
        QSlider#trackVolumeSlider::handle:horizontal:hover {{
            background: #115E59;
        }}
        QSlider#trackHeightSlider::groove:horizontal {{
            background: #7C3AED;
        }}
        QSlider#trackHeightSlider {{
            background: transparent;
        }}
        QSlider#trackHeightSlider::handle:horizontal {{
            background: #7C3AED;
        }}
        QSlider#trackHeightSlider::handle:horizontal:hover {{
            background: #6D28D9;
        }}
        #previewSection QSlider::groove:horizontal {{
            background: #4CAF50;
        }}
        QScrollBar:vertical {{
            width: 10px;
            background: {c['neutral-100']};
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: {c['text-secondary']};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {c['neutral-900']}; }}
    """


def _apply_design_system(app: QApplication) -> None:
    """QApplication에 공통 QSS 스타일시트를 적용한다."""
    app.setStyleSheet(_build_design_qss())
