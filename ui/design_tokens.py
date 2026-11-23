# -*- coding: utf-8 -*-
"""디자인 토큰 및 QSS 스타일시트 생성.

HTML 디자인(Stitch "Precision Waveform Studio")의 토큰을
Qt Style Sheets(QSS)로 변환한 디자인 시스템이다.
"""

DESIGN_TOKENS = {
    "colors": {
        # 캔버스/서피스
        "background": "#FAF8FF",
        "surface": "#FFFFFF",
        "surface-container-lowest": "#FFFFFF",
        "surface-container-low": "#F2F3FF",
        "surface-container": "#EAEDff",
        "surface-container-high": "#E2E7FF",
        "surface-container-highest": "#DAE2FD",
        "on-surface": "#131B2E",
        "on-surface-variant": "#464554",
        "inverse-surface": "#283044",
        "inverse-on-surface": "#EEF0FF",
        "outline": "#767586",
        "outline-variant": "#C7C4D7",
        "surface-tint": "#4648D4",
        "primary": "#4648D4",
        "on-primary": "#FFFFFF",
        "primary-container": "#6063EE",
        "on-primary-container": "#FFFBFF",
        "inverse-primary": "#C0C1FF",
        "secondary": "#006398",
        "on-secondary": "#FFFFFF",
        "secondary-container": "#5BB8FE",
        "on-secondary-container": "#00476E",
        "tertiary": "#006948",
        "on-tertiary": "#FFFFFF",
        "tertiary-container": "#00855D",
        "on-tertiary-container": "#F5FFF7",
        "error": "#BA1A1A",
        "on-error": "#FFFFFF",
        "error-container": "#FFDAD6",
        "on-error-container": "#93000A",
        # 하위호환 별칭 (기존 QSS에서 사용 중)
        "neutral-50": "#FFFFFF",
        "neutral-100": "#F2F3FF",
        "neutral-200": "#E2E7FF",
        "neutral-900": "#131B2E",
        "text-secondary": "#464554",
        "input_bg": "#FFFFFF",
        "border": "#C7C4D7",
        "primary_hover": "#3F40C7",
        "primary_pressed": "#2F2EBE",
        "success": "#006948",
        "success_hover": "#005137",
        "danger": "#BA1A1A",
        "danger_hover": "#93000A",
        "focus_ring": "#4648D4",
        "wave_vocal": "#0284C7",
        "wave_mr": "#7C3AED",
        "wave_mix": "#06B6D4",
    },
    "radius": {
        "sm": 2,
        "md": 4,
        "lg": 6,
        "xl": 8,
    },
    "spacing": {
        "xs": 2,
        "sm": 4,
        "md": 8,
        "lg": 12,
        "xl": 16,
    },
    "font": {
        "family": "Hanken Grotesk, Inter, 'Segoe UI', sans-serif",
        "mono": "JetBrains Mono, 'Cascadia Code', Consolas, monospace",
        "size_base": 10,
        "size_large": 14,
        "size_xlarge": 18,
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
            color: {c['on-surface']};
            background-color: {c['background']};
        }}
        QLabel {{ color: {c['on-surface']}; background-color: transparent; }}
        QLabel[accent="true"] {{ color: {c['primary']}; font-weight: 700; }}
        QLabel[textColor="secondary"] {{ color: {c['on-surface-variant']}; }}

        /* ── 버튼 ── */
        QPushButton {{
            background-color: {c['primary']};
            color: {c['on-primary']};
            padding: 6px 16px;
            border-radius: {r['md']}px;
            border: 1px solid {c['primary']};
            font-weight: 600;
            min-height: 28px;
        }}
        QPushButton:hover {{ background-color: {c['primary_hover']}; border-color: {c['primary_hover']}; }}
        QPushButton:pressed {{ background-color: {c['primary_pressed']}; border-color: {c['primary_pressed']}; }}
        QPushButton:disabled {{ background-color: {c['surface-container-high']}; color: {c['on-surface-variant']}; border-color: {c['outline-variant']}; }}
        QPushButton:focus {{ border: 2px solid {c['focus_ring']}; }}
        QPushButton[secondary="true"] {{
            background-color: {c['surface-container-lowest']};
            color: {c['on-surface']};
            border: 1px solid {c['outline-variant']};
        }}
        QPushButton[secondary="true"]:hover {{ background-color: {c['surface-container-low']}; border-color: {c['outline']}; }}
        QPushButton[secondary="true"]:pressed {{ background-color: {c['surface-container']}; }}
        QPushButton[success="true"] {{
            background-color: {c['tertiary']};
            color: {c['on-tertiary']};
            border: 1px solid {c['tertiary']};
        }}
        QPushButton[success="true"]:hover {{ background-color: {c['success_hover']}; border-color: {c['success_hover']}; }}
        QPushButton[success="true"]:pressed {{ background-color: {c['tertiary-container']}; border-color: {c['tertiary-container']}; padding-top: 7px; padding-bottom: 5px; }}
        QPushButton[danger="true"] {{
            background-color: {c['error']};
            color: {c['on-error']};
            border: 1px solid {c['error']};
        }}
        QPushButton[danger="true"]:hover {{ background-color: {c['on-error-container']}; border-color: {c['on-error-container']}; }}
        QPushButton[danger="true"]:pressed {{ background-color: #930005; }}

        /* ── 입력 필드 ── */
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            border: 1px solid {c['outline-variant']};
            border-radius: {r['sm']}px;
            padding: 6px 10px;
            background-color: {c['input_bg']};
            color: {c['on-surface']};
            min-height: 28px;
        }}
        QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {c['focus_ring']};
            border-width: 2px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface']};
            color: {c['on-surface']};
            selection-background-color: {c['surface-container-high']};
            selection-color: {c['primary']};
            border: 1px solid {c['outline-variant']};
            outline: none;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}

        /* ── 프레임/섹션 카드 ── */
        QFrame[section="true"] {{
            border: 1px solid {c['outline-variant']};
            border-radius: {r['md']}px;
            background-color: {c['surface']};
            margin-top: {round(s['lg'] * 0.3)}px;
            margin-bottom: {round(s['lg'] * 0.3)}px;
            padding: {round(s['md'] * 0.5)}px {round(s['md'] * 0.5)}px {round(s['xs'] * 0.5)}px {round(s['md'] * 0.5)}px;
        }}

        /* ── 설정/가사/미리보기 섹션 ── */
        #settingsSection {{
            background-color: {c['surface-container-low']};
        }}
        #lyricsSection {{
            background-color: {c['surface-container-low']};
        }}
        #previewSection {{
            background-color: {c['surface-container-low']};
            border: none;
            padding: 0;
            margin-top: 0;
            margin-bottom: 0;
        }}
        #previewContent {{
            background: transparent;
        }}
        #sideMenu {{
            background-color: {c['surface']};
            border: none;
            border-right: 1px solid {c['outline-variant']};
        }}
        #sideMenuButton {{
            background-color: transparent;
            color: {c['on-surface-variant']};
            border: none;
            border-left: 3px solid transparent;
            padding: 13px 10px;
            text-align: left;
            font-weight: 600;
        }}
        #sideMenuButton:hover {{
            background-color: {c['surface-container-low']};
            color: {c['on-surface']};
        }}
        #sideMenuButton:checked {{
            background-color: {c['surface-container-low']};
            color: {c['primary']};
            border-left: 3px solid {c['primary']};
            font-weight: 800;
        }}

        /* ── 섹션 타이틀 ── */
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

        /* ── 체크박스/라디오 ── */
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 2px;
            border: 1px solid {c['outline-variant']};
            background-color: {c['surface']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c['primary']};
            border-color: {c['primary']};
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 1px solid {c['outline-variant']};
            background-color: {c['surface']};
        }}
        QRadioButton::indicator:checked {{
            background-color: {c['primary']};
            border-color: {c['primary']};
        }}

        /* ── 메뉴 ── */
        QMenu {{
            background-color: {c['surface']};
            border: 1px solid {c['outline-variant']};
            padding: 4px;
            min-width: 220px;
        }}
        QMenu::item {{
            padding: 6px 40px 6px 12px;
            min-width: 160px;
            border-radius: {r['sm']}px;
            color: {c['on-surface']};
        }}
        QMenu::item:selected {{
            background-color: {c['surface-container-high']};
            color: {c['primary']};
        }}
        QMenu::item:disabled {{
            color: {c['on-surface-variant']};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {c['outline-variant']};
            margin: 4px 8px;
        }}

        /* ── 스크롤바 ── */
        QScrollBar:vertical {{
            background: {c['surface-container-low']};
            width: 10px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {c['outline-variant']};
            border-radius: 5px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c['outline']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: {c['surface-container-low']};
            height: 10px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {c['outline-variant']};
            border-radius: 5px;
            min-width: 20px;
        }}

        /* ── 프로그레스 바 ── */
        QProgressBar {{
            border: 1px solid {c['outline-variant']};
            border-radius: {r['sm']}px;
            background-color: {c['surface-container-low']};
            text-align: center;
            color: {c['on-surface']};
            height: 18px;
        }}
        QProgressBar::chunk {{
            background-color: {c['primary']};
            border-radius: {r['sm']}px;
        }}
    """


def _apply_design_system(app) -> None:
    """QApplication에 공통 QSS 스타일시트를 적용한다."""
    app.setStyleSheet(_build_design_qss())
