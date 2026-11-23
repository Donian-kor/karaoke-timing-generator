# -*- coding: utf-8 -*-
"""메인 화면 사이드바 하단에 표시하는 시스템 사용량 패널.

CPU/RAM/GPU/VRAM/전력 사용량을 한 열로 나열하고,
각 항목 아래에 사용률에 따라 색이 바뀌는 가로 프로그레스바를 둔다.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# 사용률 구간별 색상: 적음(연한 파랑) → 적정(녹색) → 주의(주황) → 위험(빨강)
COLOR_LOW = "#93C5FD"
COLOR_OK = "#22C55E"
COLOR_WARN = "#F59E0B"
COLOR_HIGH = "#EF4444"
COLOR_TRACK = "#E5E7EB"


def usage_color(percent: float) -> str:
    """사용률(%)에 해당하는 프로그레스바 색상을 반환한다."""
    if percent >= 85.0:
        return COLOR_HIGH
    if percent >= 60.0:
        return COLOR_WARN
    if percent >= 25.0:
        return COLOR_OK
    return COLOR_LOW


class UsageBar(QWidget):
    """둥근 모서리의 가로 사용량 바."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, value: float) -> None:
        value = max(0.0, min(100.0, float(value)))
        if abs(value - self._value) < 0.05:
            return
        self._value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)

        radius = self.height() / 2.0
        full = QRectF(self.rect())
        painter.setBrush(QColor(COLOR_TRACK))
        painter.drawRoundedRect(full, radius, radius)

        if self._value <= 0.0:
            return

        width = max(full.width() * self._value / 100.0, self.height())
        fill = QRectF(full.x(), full.y(), width, full.height())
        painter.setBrush(QColor(usage_color(self._value)))
        painter.drawRoundedRect(fill, radius, radius)


class MetricRow(QWidget):
    """'라벨 + 값' 한 줄과 그 아래 사용량 바로 구성된 항목."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            "background: transparent; border: none;"
            "color: #64748B; font-size: 9pt; font-weight: 500;"
        )
        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value_label.setStyleSheet(
            "background: transparent; border: none;"
            "color: #334155; font-size: 9pt; font-weight: 600;"
        )

        text_row.addWidget(self.title_label)
        text_row.addStretch(1)
        text_row.addWidget(self.value_label)

        self.bar = UsageBar()
        layout.addLayout(text_row)
        layout.addWidget(self.bar)

    def set_values(self, text: str, percent: float) -> None:
        self.value_label.setText(text)
        self.bar.set_value(percent)


class SystemMonitorPanel(QFrame):
    """CPU/RAM/GPU/VRAM/전력 사용량을 보여주는 카드형 패널."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("systemMonitorCard")
        self.setStyleSheet(
            "#systemMonitorCard {"
            " background-color: #FFFFFF;"
            " border: 1px solid #E2E8F0;"
            " border-radius: 10px;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(9)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self._set_dot_color("#CBD5E1")
        self.gpu_name_label = QLabel("시스템 정보")
        self.gpu_name_label.setStyleSheet(
            "background: transparent; border: none;"
            "color: #334155; font-size: 9pt; font-weight: 700;"
        )
        header.addWidget(self.status_dot)
        header.addWidget(self.gpu_name_label, 1)
        layout.addLayout(header)

        # 스크린샷과 같은 순서: GPU → VRAM → 전력 → RAM → CPU
        self.rows = {
            "gpu": MetricRow("GPU"),
            "vram": MetricRow("VRAM"),
            "power": MetricRow("전력"),
            "ram": MetricRow("RAM"),
            "cpu": MetricRow("CPU"),
        }
        for row in self.rows.values():
            layout.addWidget(row)

        self._gpu_row_keys = ("gpu", "vram", "power")

    def _set_dot_color(self, color: str) -> None:
        self.status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 4px;"
        )

    def update_sample(self, sample: dict) -> None:
        """SystemMonitorWorker가 보낸 샘플로 표시를 갱신한다."""
        if not sample:
            return

        cpu_pct = sample.get("cpu_pct")
        if cpu_pct is not None:
            self.rows["cpu"].set_values(f"{cpu_pct:.0f}%", cpu_pct)

        ram_pct = sample.get("ram_pct")
        if ram_pct is not None:
            text = (
                f"{sample['ram_used']:.1f} / {sample['ram_total']:.1f} GB"
                f" ({ram_pct:.0f}%)"
            )
            self.rows["ram"].set_values(text, ram_pct)

        if sample.get("has_gpu"):
            name = sample.get("gpu_name") or "GPU"
            self.gpu_name_label.setText(name)
            self._set_dot_color(COLOR_OK)

            gpu_pct = sample.get("gpu_pct", 0.0)
            self.rows["gpu"].set_values(f"{gpu_pct:.0f}%", gpu_pct)

            vram_pct = sample.get("vram_pct", 0.0)
            self.rows["vram"].set_values(
                f"{sample['vram_used']:.1f} / {sample['vram_total']:.1f} GB"
                f" ({vram_pct:.0f}%)",
                vram_pct,
            )

            has_power = bool(sample.get("has_power"))
            if has_power:
                power_pct = sample.get("power_pct") or 0.0
                self.rows["power"].set_values(
                    f"{sample['power_draw']:.0f} / {sample['power_limit']:.0f} W"
                    f" ({power_pct:.0f}%)",
                    power_pct,
                )

            self.rows["gpu"].setVisible(True)
            self.rows["vram"].setVisible(True)
            self.rows["power"].setVisible(has_power)
        else:
            # GPU가 없는 환경에서는 GPU 관련 항목을 숨긴다.
            self.gpu_name_label.setText("시스템 정보")
            self._set_dot_color("#CBD5E1")
            for key in self._gpu_row_keys:
                self.rows[key].setVisible(False)
