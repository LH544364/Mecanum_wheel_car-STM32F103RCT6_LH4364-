#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
机器人/小车远程控制上位机
基于 PyQt5，深色科技风界面
功能：图传画面占位、四电机转速监控（含曲线图）、方向/转向摇杆、速度面板、急停按钮
"""

import sys
import math
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSizePolicy, QFrame, QSpacerItem
)
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QRadialGradient, QFontDatabase, QMouseEvent, QKeyEvent,
    QPainterPath, QPolygonF
)


# ======================== 全局配色常量 ========================
COLOR_BG_DARK      = "#1e1e2e"   # 主背景色
COLOR_BG_CARD      = "#252536"   # 卡片背景
COLOR_BG_WIDGET    = "#2a2a3c"   # 控件背景
COLOR_TEXT_PRIMARY = "#cdd6f4"   # 主文字色
COLOR_TEXT_SECOND  = "#a6adc8"   # 次文字色
COLOR_ACCENT_BLUE  = "#89b4fa"   # 强调蓝
COLOR_ACCENT_RED   = "#f38ba8"   # 强调红
COLOR_BORDER       = "#45475a"   # 边框色
COLOR_CHART_LINE   = "#89b4fa"   # 曲线颜色
COLOR_CHART_BG     = "#1a1a28"   # 图表背景
COLOR_JOYSTICK_BASE = QColor(40, 42, 60)
COLOR_JOYSTICK_KNOB = QColor(137, 180, 250)

FONT_FAMILY = "Microsoft YaHei, Segoe UI, sans-serif"


# ======================== 自定义摇杆控件 ========================
class JoystickWidget(QWidget):
    """
    圆形摇杆控件：支持鼠标拖拽/点击 和 键盘 WASD 控制
    - 按下鼠标并拖动，内部小圆点跟随移动
    - 松开鼠标后，小圆点弹性复位到中心
    - 同时提供 keyboard_offset 属性，供外部设置键盘偏移量
    """

    def __init__(self, parent=None, label_text="摇杆"):
        super().__init__(parent)
        self._label_text = label_text

        # 摇杆状态
        self._mouse_offset = QPointF(0, 0)      # 鼠标拖拽偏移 (-1 ~ 1)
        self._keyboard_offset = QPointF(0, 0)    # 键盘偏移 (-1 ~ 1)
        self._mouse_active = False                # 鼠标是否按住

        # 动画过渡用
        self._current_display_offset = QPointF(0, 0)

        self.setMinimumSize(160, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # --- 公共属性 ---
    def set_keyboard_offset(self, dx, dy):
        """由外部（MainWindow）设置键盘偏移量，范围 -1..1"""
        self._keyboard_offset = QPointF(
            max(-1.0, min(1.0, dx)),
            max(-1.0, min(1.0, dy))
        )

    def effective_offset(self):
        """
        返回当前有效偏移量（鼠标优先，否则键盘）
        返回 QPointF，x/y 范围 -1..1
        """
        if self._mouse_active:
            return self._mouse_offset
        return self._keyboard_offset

    def reset(self):
        """复位摇杆到中心（急停时调用）"""
        self._mouse_offset = QPointF(0, 0)
        self._keyboard_offset = QPointF(0, 0)
        self._mouse_active = False
        self._current_display_offset = QPointF(0, 0)
        self.update()

    # --- 绘制 ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        cx = w / 2.0
        cy = h / 2.0
        radius = side / 2.0 - 10  # 留边距

        # ---- 底座渐变 ----
        base_gradient = QRadialGradient(cx, cy, radius * 1.1)
        base_gradient.setColorAt(0.0, QColor(60, 62, 80))
        base_gradient.setColorAt(0.7, QColor(35, 37, 55))
        base_gradient.setColorAt(1.0, QColor(25, 27, 42))
        painter.setPen(QPen(QColor(COLOR_BORDER), 2))
        painter.setBrush(QBrush(base_gradient))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # ---- 内圈装饰环 ----
        inner_radius = radius * 0.7
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), inner_radius, inner_radius)

        # ---- 十字参考线 ----
        painter.setPen(QPen(QColor(80, 82, 100), 1, Qt.DashLine))
        painter.drawLine(QPointF(cx - inner_radius, cy), QPointF(cx + inner_radius, cy))
        painter.drawLine(QPointF(cx, cy - inner_radius), QPointF(cx, cy + inner_radius))

        # ---- 计算目标偏移（平滑过渡） ----
        target = self.effective_offset()
        # 简单平滑插值（lerp）
        lerp_factor = 0.3
        self._current_display_offset = QPointF(
            self._current_display_offset.x() + (target.x() - self._current_display_offset.x()) * lerp_factor,
            self._current_display_offset.y() + (target.y() - self._current_display_offset.y()) * lerp_factor,
        )

        knob_x = cx + self._current_display_offset.x() * inner_radius
        knob_y = cy - self._current_display_offset.y() * inner_radius  # Y轴反转（上为正）

        # ---- 活动小圆点 ----
        knob_r = radius * 0.18
        knob_gradient = QRadialGradient(knob_x, knob_y, knob_r * 1.5)
        knob_gradient.setColorAt(0.0, QColor(180, 210, 255))
        knob_gradient.setColorAt(0.5, COLOR_JOYSTICK_KNOB)
        knob_gradient.setColorAt(1.0, QColor(70, 120, 200))
        painter.setPen(QPen(QColor(120, 160, 220), 1.5))
        painter.setBrush(QBrush(knob_gradient))
        painter.drawEllipse(QPointF(knob_x, knob_y), knob_r, knob_r)

        # ---- 底部标签 ----
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        font = QFont(FONT_FAMILY.split(",")[0].strip(), 9)
        painter.setFont(font)
        text_rect = QRectF(0, h - 18, w, 16)
        painter.drawText(text_rect, Qt.AlignCenter, self._label_text)

        painter.end()

    # --- 鼠标事件 ---
    def _get_joystick_offset(self, pos):
        """根据鼠标位置计算摇杆偏移量 (-1..1)"""
        w = self.width()
        h = self.height()
        side = min(w, h)
        radius = side / 2.0 - 10
        inner_radius = radius * 0.7
        cx = w / 2.0
        cy = h / 2.0

        dx = (pos.x() - cx) / inner_radius
        dy = -(pos.y() - cy) / inner_radius  # Y反转
        # 限制在单位圆内
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 1.0:
            dx /= dist
            dy /= dist
        return QPointF(dx, dy)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._mouse_active = True
            self._mouse_offset = self._get_joystick_offset(event.pos())
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._mouse_active:
            self._mouse_offset = self._get_joystick_offset(event.pos())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._mouse_active = False
            self._mouse_offset = QPointF(0, 0)
            self.update()

    def sizeHint(self):
        return QSize(180, 180)


# ======================== 电机监控卡片 ========================
class MotorMonitorWidget(QWidget):
    """
    单个电机监控卡片：标题、曲线图、目标/实际转速标签
    曲线图使用 QPainter 绘制，历史数据存储在内部列表中
    """

    def __init__(self, parent=None, motor_name="A"):
        super().__init__(parent)
        self.motor_name = motor_name
        self.target_speed = 0
        self.actual_speed = 0

        # 曲线历史数据（最近100个点）
        self._history_size = 100
        self._target_history = [0.0] * self._history_size
        self._actual_history = [0.0] * self._history_size

        self.setMinimumSize(200, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def update_speeds(self, target, actual):
        """更新当前转速数据"""
        self.target_speed = target
        self.actual_speed = actual
        # 滚动历史数据
        self._target_history.pop(0)
        self._target_history.append(float(target))
        self._actual_history.pop(0)
        self._actual_history.append(float(actual))
        self.update()

    def reset(self):
        """急停复位"""
        self.target_speed = 0
        self.actual_speed = 0
        self._target_history = [0.0] * self._history_size
        self._actual_history = [0.0] * self._history_size
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 10

        # ---- 卡片背景 ----
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLOR_BG_CARD))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 8, 8)

        # ---- 标题 ----
        painter.setPen(QColor(COLOR_TEXT_PRIMARY))
        title_font = QFont(FONT_FAMILY.split(",")[0].strip(), 10, QFont.Bold)
        painter.setFont(title_font)
        title = f"{self.motor_name}电机的实际转速曲线"
        painter.drawText(QRectF(margin, 4, w - 2 * margin, 22), Qt.AlignLeft | Qt.AlignVCenter, title)

        # ---- 图表区域 ----
        chart_x = margin
        chart_y = 28
        chart_w = w - 2 * margin
        chart_h = h - 70  # 留出底部标签空间

        # 图表背景
        painter.setPen(QPen(QColor(COLOR_BORDER), 1))
        painter.setBrush(QColor(COLOR_CHART_BG))
        painter.drawRoundedRect(QRectF(chart_x, chart_y, chart_w, chart_h), 4, 4)

        # 坐标轴
        painter.setPen(QPen(QColor(100, 102, 120), 1))
        # 零线
        zero_y = chart_y + chart_h / 2.0
        painter.drawLine(QPointF(chart_x, zero_y), QPointF(chart_x + chart_w, zero_y))

        # 网格线（水平）
        for i in range(1, 4):
            frac = i / 4.0
            yy = chart_y + chart_h * frac
            painter.setPen(QPen(QColor(55, 57, 75), 1, Qt.DotLine))
            painter.drawLine(QPointF(chart_x, yy), QPointF(chart_x + chart_w, yy))

        # 绘制曲线数据（目标转速 - 蓝色虚线，实际转速 - 青色实线）
        max_val = 100.0  # 默认量程 ±100
        # 根据历史数据动态调整量程
        all_vals = self._target_history + self._actual_history
        abs_max = max(max(abs(v) for v in all_vals), 10.0)
        max_val = abs_max * 1.2

        def val_to_y(v):
            return zero_y - (v / max_val) * (chart_h / 2.0 - 2)

        # 目标曲线（虚线）
        painter.setPen(QPen(QColor(200, 160, 100), 1.5, Qt.DashLine))  # 橙色虚线
        path_target = QPainterPath()
        first = True
        for i, val in enumerate(self._target_history):
            x = chart_x + (i / (self._history_size - 1)) * chart_w
            y = val_to_y(val)
            if first:
                path_target.moveTo(x, y)
                first = False
            else:
                path_target.lineTo(x, y)
        painter.drawPath(path_target)

        # 实际曲线（实线）
        painter.setPen(QPen(QColor(COLOR_CHART_LINE), 1.8))
        path_actual = QPainterPath()
        first = True
        for i, val in enumerate(self._actual_history):
            x = chart_x + (i / (self._history_size - 1)) * chart_w
            y = val_to_y(val)
            if first:
                path_actual.moveTo(x, y)
                first = False
            else:
                path_actual.lineTo(x, y)
        painter.drawPath(path_actual)

        # 图例
        legend_y = chart_y + 4
        legend_x = chart_x + chart_w - 60
        painter.setPen(QColor(200, 160, 100))
        painter.drawText(QRectF(legend_x - 50, legend_y, 60, 12), Qt.AlignRight, "目标")
        painter.setPen(QColor(COLOR_CHART_LINE))
        painter.drawText(QRectF(legend_x + 15, legend_y, 60, 12), Qt.AlignLeft, "实际")

        # ---- 底部标签 ----
        label_y = int(chart_y + chart_h + 4)
        label_font = QFont(FONT_FAMILY.split(",")[0].strip(), 9)
        painter.setFont(label_font)

        # 目标转速标签
        painter.setPen(QColor(COLOR_TEXT_SECOND))
        painter.drawText(QRectF(margin, label_y, w - 2 * margin, 16),
                         Qt.AlignLeft, f"{self.motor_name}电机目标转速：")
        painter.setPen(QColor(200, 160, 100))
        painter.drawText(QRectF(margin + 100, label_y, 60, 16),
                         Qt.AlignLeft, str(self.target_speed))

        # 实际转速标签
        painter.setPen(QColor(COLOR_TEXT_SECOND))
        painter.drawText(QRectF(margin, label_y + 14, w - 2 * margin, 16),
                         Qt.AlignLeft, f"{self.motor_name}电机实际转速：")
        painter.setPen(QColor(COLOR_ACCENT_BLUE))
        painter.drawText(QRectF(margin + 100, label_y + 14, 60, 16),
                         Qt.AlignLeft, str(self.actual_speed))

        painter.end()

    def sizeHint(self):
        return QSize(280, 220)


# ======================== 速度面板控件 ========================
class SpeedPanel(QWidget):
    """
    速度面板：上下箭头按钮 + 速度值显示
    """

    speed_changed = None  # 信号兼容，直接用回调

    def __init__(self, parent=None, on_speed_changed=None):
        super().__init__(parent)
        self._speed = 0
        self._on_speed_changed = on_speed_changed

        self.setMinimumSize(120, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 上箭头按钮
        self.btn_up = QPushButton("▲\n点击加速")
        self.btn_up.setCursor(Qt.PointingHandCursor)
        self.btn_up.clicked.connect(self._increase)

        # 速度显示
        self.label_speed = QLabel("速度面板")
        self.label_speed.setAlignment(Qt.AlignCenter)

        self.label_value = QLabel("0")
        self.label_value.setAlignment(Qt.AlignCenter)

        # 下箭头按钮
        self.btn_down = QPushButton("▼\n点击减速")
        self.btn_down.setCursor(Qt.PointingHandCursor)
        self.btn_down.clicked.connect(self._decrease)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        layout.addWidget(self.btn_up)
        layout.addStretch(1)
        layout.addWidget(self.label_speed)
        layout.addWidget(self.label_value)
        layout.addStretch(1)
        layout.addWidget(self.btn_down)

    def _increase(self):
        self._speed += 10
        self._update_display()
        if self._on_speed_changed:
            self._on_speed_changed(self._speed)

    def _decrease(self):
        self._speed = max(0, self._speed - 10)
        self._update_display()
        if self._on_speed_changed:
            self._on_speed_changed(self._speed)

    def _update_display(self):
        self.label_value.setText(str(self._speed))

    def get_speed(self):
        return self._speed

    def set_speed(self, val):
        self._speed = max(0, val)
        self._update_display()

    def reset(self):
        self._speed = 0
        self._update_display()

    def sizeHint(self):
        return QSize(140, 180)


# ======================== 主窗口 ========================
class MainWindow(QMainWindow):
    """机器人远程控制上位机主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("机器人远程控制上位机 — K230图传 & 电机监控")
        self.resize(1200, 800)

        # ---- 键盘状态 ----
        self._key_w = False
        self._key_a = False
        self._key_s = False
        self._key_d = False

        # ---- 全局速度 ----
        self._global_speed = 0

        # ---- 构建UI ----
        self._setup_ui()
        self._apply_theme()

        # ---- 定时器：100ms 刷新 ----
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(100)  # 100ms

    # ============ UI搭建 ============
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(8)

        # ---- 上半部分：图传（左）+ 电机监控（右） ----
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # 图传画面区（左，约占 40% 宽度）
        self.video_widget = self._create_video_panel()
        top_layout.addWidget(self.video_widget, 4)

        # 电机监控区（右，约占 60% 宽度）- 2×2 网格
        self.motor_grid_widget = self._create_motor_panel()
        top_layout.addWidget(self.motor_grid_widget, 6)

        root_layout.addLayout(top_layout, 55)

        # ---- 下半部分：控制区 ----
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(12)

        # 左下：方向控制摇杆
        self.joystick_dir = JoystickWidget(label_text="方向控制 (WASD)")
        bottom_layout.addWidget(self.joystick_dir, 3)

        # 中下：速度面板
        self.speed_panel = SpeedPanel(on_speed_changed=self._on_global_speed_changed)
        bottom_layout.addWidget(self.speed_panel, 2)

        # 右下：转向摇杆 + 急停按钮
        right_bottom_layout = QHBoxLayout()
        right_bottom_layout.setSpacing(8)

        self.joystick_turn = JoystickWidget(label_text="转向控制")
        right_bottom_layout.addWidget(self.joystick_turn, 3)

        # 急停按钮
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setMinimumSize(80, 80)
        self.btn_stop.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_stop.clicked.connect(self._on_stop)
        right_bottom_layout.addWidget(self.btn_stop, 1)

        bottom_right_container = QWidget()
        bottom_right_container.setLayout(right_bottom_layout)
        bottom_layout.addWidget(bottom_right_container, 5)

        root_layout.addLayout(bottom_layout, 45)

    def _create_video_panel(self):
        """创建图传画面占位区域"""
        panel = QFrame()
        panel.setObjectName("videoPanel")
        panel.setMinimumSize(300, 300)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏
        title_label = QLabel("K230的图传画面")
        title_label.setObjectName("videoTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFixedHeight(30)

        # 视频占位区域
        video_area = QLabel("等待视频流...")
        video_area.setObjectName("videoPlaceholder")
        video_area.setAlignment(Qt.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(video_area, 1)

        return panel

    def _create_motor_panel(self):
        """创建2×2电机监控网格"""
        grid = QWidget()
        grid_layout = QGridLayout(grid)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(6)

        # 网格布局：左上D, 右上A, 左下C, 右下B
        # row=0 col=0: D电机（左上）
        # row=0 col=1: A电机（右上）
        # row=1 col=0: C电机（左下）
        # row=1 col=1: B电机（右下）
        self.motor_D = MotorMonitorWidget(motor_name="D")
        self.motor_A = MotorMonitorWidget(motor_name="A")
        self.motor_C = MotorMonitorWidget(motor_name="C")
        self.motor_B = MotorMonitorWidget(motor_name="B")

        grid_layout.addWidget(self.motor_D, 0, 0)
        grid_layout.addWidget(self.motor_A, 0, 1)
        grid_layout.addWidget(self.motor_C, 1, 0)
        grid_layout.addWidget(self.motor_B, 1, 1)

        # 所有电机卡片等比例
        grid_layout.setRowStretch(0, 1)
        grid_layout.setRowStretch(1, 1)
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)

        return grid

    # ============ 全局主题 QSS ============
    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLOR_BG_DARK};
            }}
            QWidget {{
                font-family: "{FONT_FAMILY}";
                color: {COLOR_TEXT_PRIMARY};
            }}
            /* 图传面板 */
            #videoPanel {{
                background-color: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
            #videoTitle {{
                background-color: {COLOR_BG_WIDGET};
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
                font-weight: bold;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 4px;
            }}
            #videoPlaceholder {{
                background-color: #000000;
                color: {COLOR_TEXT_SECOND};
                font-size: 18px;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            /* 电机监控卡片 */
            MotorMonitorWidget {{
                background-color: {COLOR_BG_CARD};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
            }}
            /* 速度面板按钮 */
            QPushButton {{
                background-color: {COLOR_BG_WIDGET};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3a3a52;
                border-color: {COLOR_ACCENT_BLUE};
            }}
            QPushButton:pressed {{
                background-color: #2a2a3a;
            }}
            /* 急停按钮 */
            #btnStop {{
                background-color: #d64550;
                color: #ffffff;
                border: 2px solid #f38ba8;
                border-radius: 40px;
                font-size: 16px;
                font-weight: bold;
            }}
            #btnStop:hover {{
                background-color: #e05560;
                border-color: #ffa0b5;
            }}
            #btnStop:pressed {{
                background-color: #b0303c;
                border-color: #d06070;
            }}
            /* 速度面板标签 */
            #speedLabel {{
                font-size: 13px;
                font-weight: bold;
                color: {COLOR_TEXT_PRIMARY};
            }}
            #speedValue {{
                font-size: 36px;
                font-weight: bold;
                color: {COLOR_ACCENT_BLUE};
            }}
        """)

        # 为特定控件设置 objectName
        self.btn_stop.setObjectName("btnStop")
        self.speed_panel.label_speed.setObjectName("speedLabel")
        self.speed_panel.label_value.setObjectName("speedValue")

    # ============ 键盘事件 ============
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_W:
            self._key_w = True
        elif key == Qt.Key_A:
            self._key_a = True
        elif key == Qt.Key_S:
            self._key_s = True
        elif key == Qt.Key_D:
            self._key_d = True
        self._sync_keyboard_to_joystick()

    def keyReleaseEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key_W:
            self._key_w = False
        elif key == Qt.Key_A:
            self._key_a = False
        elif key == Qt.Key_S:
            self._key_s = False
        elif key == Qt.Key_D:
            self._key_d = False
        self._sync_keyboard_to_joystick()

    def _sync_keyboard_to_joystick(self):
        """将WASD状态转换为方向摇杆的键盘偏移"""
        dx = 0.0
        dy = 0.0
        if self._key_a:
            dx -= 1.0
        if self._key_d:
            dx += 1.0
        if self._key_w:
            dy += 1.0
        if self._key_s:
            dy -= 1.0
        # 归一化
        if dx != 0 or dy != 0:
            mag = math.sqrt(dx * dx + dy * dy)
            dx /= mag
            dy /= mag
        self.joystick_dir.set_keyboard_offset(dx, dy)

    # ============ 定时器刷新 ============
    def _on_tick(self):
        """每100ms更新所有电机目标/实际转速"""
        # 获取方向摇杆偏移
        dir_offset = self.joystick_dir.effective_offset()
        # 获取转向摇杆偏移
        turn_offset = self.joystick_turn.effective_offset()

        # 全局速度
        base_speed = self._global_speed

        # 方向偏移映射：
        # dy > 0 (W/前) → 前进 → 所有电机正转
        # dy < 0 (S/后) → 后退 → 所有电机反转
        # dx > 0 (D/右) → 右侧电机减速、左侧加速（差速转向）
        # dx < 0 (A/左) → 左侧电机减速、右侧加速
        forward_speed = base_speed * dir_offset.y()   # 前后分量
        turn_diff = base_speed * dir_offset.x() * 0.5  # 差速分量

        # 转向摇杆：纯旋转（原地旋转），绕Z轴
        rotate_diff = base_speed * turn_offset.x()

        # 计算各电机目标速度
        # 四轮布局：左前=C(左下), 右前=D(左上), 左后=?, 右后=?
        # 简化模型：左列=C/D, 右列=A/B
        # C(左下) = 左前, D(左上) = 左后, A(右上) = 右前, B(右下) = 右后
        # 前进时：全部正转
        # 左转时：左侧减速/反转，右侧加速
        # 原地右转：左侧正转，右侧反转
        target_C = forward_speed - turn_diff - rotate_diff  # 左电机
        target_D = forward_speed - turn_diff - rotate_diff  # 左电机
        target_A = forward_speed + turn_diff + rotate_diff  # 右电机
        target_B = forward_speed + turn_diff + rotate_diff  # 右电机

        # 取整
        target_C = int(round(target_C))
        target_D = int(round(target_D))
        target_A = int(round(target_A))
        target_B = int(round(target_B))

        # 更新电机卡片（实际转速暂用目标转速模拟，后续接入真实数据时替换）
        self.motor_C.update_speeds(target_C, target_C)
        self.motor_D.update_speeds(target_D, target_D)
        self.motor_A.update_speeds(target_A, target_A)
        self.motor_B.update_speeds(target_B, target_B)

        # 刷新摇杆
        self.joystick_dir.update()
        self.joystick_turn.update()

    # ============ 速度回调 ============
    def _on_global_speed_changed(self, speed):
        """速度面板值变化"""
        self._global_speed = speed

    # ============ 急停 ============
    def _on_stop(self):
        """急停按钮：所有目标转速清零，摇杆复位"""
        self._global_speed = 0
        self.speed_panel.reset()
        self.joystick_dir.reset()
        self.joystick_turn.reset()

        # 释放所有键盘状态
        self._key_w = False
        self._key_a = False
        self._key_s = False
        self._key_d = False

        # 电机归零
        self.motor_A.update_speeds(0, 0)
        self.motor_B.update_speeds(0, 0)
        self.motor_C.update_speeds(0, 0)
        self.motor_D.update_speeds(0, 0)


# ======================== 程序入口 ========================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RobotControlUpper")

    # 全局字体设置
    font = QFont(FONT_FAMILY.split(",")[0].strip(), 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
