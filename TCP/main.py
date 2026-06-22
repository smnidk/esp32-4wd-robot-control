#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os
import math
import time
import cv2

from threading import Thread

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *

from Command import COMMAND as cmd
from Client_Ui import Ui_Client
from Video import *


# =========================
# ПОТОКОБЕЗОПАСНЫЙ ВИДЖЕТ КАРТЫ РАДАРА С ЭМУЛЯЦИЕЙ ОДОМЕТРИИ
# =========================
class RadarMapWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []       # Список глобальных точек: [(gx, gy), ...]
        self.max_distance = 250
        self.mutex = QMutex()

        # Виртуальная одометрия (координаты робота на глобальной карте)
        self.robot_x = 0.0     # в см
        self.robot_y = 0.0     # в см
        self.robot_angle = 90.0 # в градусах (90 - смотрит строго вверх)

    def add_point(self, distance, sensor_angle=90):
        if distance <= 4 or distance >= 250: 
            return

        self.mutex.lock()
        relative_angle = sensor_angle - 90.0
        global_rad = math.radians(self.robot_angle + relative_angle)

        # Вычисляем глобальные координаты преграды
        gx = round(self.robot_x + distance * math.cos(global_rad), 1)
        gy = round(self.robot_y + distance * math.sin(global_rad), 1)

        # ФИЛЬТР БЛИЖНИХ ДУБЛИКАТОВ
        is_duplicate = False
        for old_x, old_y in self.points:
            if math.hypot(gx - old_x, gy - old_y) < 3.0: 
                is_duplicate = True
                break
        
        if not is_duplicate:
            self.points.append((gx, gy))
            if len(self.points) > 250: 
                self.points.pop(0)
                
        self.mutex.unlock()
        self.update()

    def move_robot(self, linear_speed, angular_speed):
        self.mutex.lock()
        self.robot_angle += angular_speed
        rad = math.radians(self.robot_angle)
        self.robot_x += linear_speed * math.cos(rad)
        self.robot_y += linear_speed * math.sin(rad)
        self.mutex.unlock()
        self.update()

    def clear_map(self):
        self.mutex.lock()
        self.points.clear()
        self.robot_x = 0.0
        self.robot_y = 0.0
        self.robot_angle = 90.0
        self.mutex.unlock()
        self.update()

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)

            # Фон
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(30, 30, 30))
            painter.drawRoundedRect(self.rect(), 10, 10)

            cx = self.width() // 2
            cy = int(self.height() * 0.75)
            scale = min(self.width() / (self.max_distance * 2), self.height() / self.max_distance)

            self.mutex.lock()
            # Отрисовка сетки дальномера
            painter.setPen(QPen(QColor(0, 255, 0, 35), 1, Qt.DashLine))
            for r_cm in [50, 100, 150, 200, 250]:
                r_px = int(r_cm * scale)
                painter.drawEllipse(QPoint(cx, cy), r_px, r_px)

            # Отрисовка сохраненных точек
            painter.setBrush(QBrush(QColor(255, 60, 60, 200)))
            painter.setPen(Qt.NoPen)
            
            current_rad = math.radians(self.robot_angle - 90)
            cos_a = math.cos(current_rad)
            sin_a = math.sin(current_rad)

            for gx, gy in self.points:
                dx = gx - self.robot_x
                dy = gy - self.robot_y
                rx = dx * cos_a + dy * sin_a
                ry = -dx * sin_a + dy * cos_a

                sx = cx + int(rx * scale)
                sy = cy - int(ry * scale)

                if self.rect().contains(sx, sy):
                    painter.drawEllipse(sx - 2, sy - 2, 4, 4)

            # Отрисовка линий контура
            painter.setPen(QPen(QColor(255, 30, 30, 120), 1, Qt.SolidLine))
            for i in range(len(self.points) - 1):
                x1, y1 = self.points[i]
                x2, y2 = self.points[i + 1]

                if math.hypot(x1 - x2, y1 - y2) < 15.0:
                    dx1, dy1 = x1 - self.robot_x, y1 - self.robot_y
                    lx1 = dx1 * cos_a + dy1 * sin_a
                    ly1 = -dx1 * sin_a + dy1 * cos_a
                    ex1, ey1 = int(cx + lx1 * scale), int(cy - ly1 * scale)

                    dx2, dy2 = x2 - self.robot_x, y2 - self.robot_y
                    lx2 = dx2 * cos_a + dy2 * sin_a
                    ly2 = -dx2 * sin_a + dy2 * cos_a
                    ex2, ey2 = int(cx + lx2 * scale), int(cy - ly2 * scale)

                    if (self.rect().contains(ex1, ey1) and self.rect().contains(ex2, ey2)):
                        painter.drawLine(ex1, ey1, ex2, ey2)
            self.mutex.unlock()

            # Маркер направления
            painter.setPen(QPen(QColor(0, 255, 0, 100), 1.5, Qt.SolidLine))
            painter.drawLine(cx, cy, cx, cy - 30)

            # Маркер самого робота
            painter.setBrush(QBrush(QColor(0, 150, 255)))
            painter.setPen(QPen(Qt.white, 1.5))
            painter.drawEllipse(QPoint(cx, cy), 6, 6)


# =========================
# ОСНОВНОЕ ОКНО ПРИЛОЖЕНИЯ
# =========================
class mywindow(QWidget, Ui_Client):
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # Скрываем неиспользуемые кнопки по умолчанию напрямую
        if hasattr(self, 'Light'): self.Light.hide()
        if hasattr(self, 'Track'): self.Track.hide()

        # Тёмная тема оформления
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e24;
                color: #e2e8f0;
                font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                font-size: 12px;
            }
            QPushButton {
                background-color: #2d2d38;
                border: 1px solid #4a4a5a;
                border-radius: 6px;
                color: #ffffff;
                font-weight: bold;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #3f3f52;
                border: 1px solid #00ff66;
            }
            QPushButton:pressed {
                background-color: #1a1a22;
                color: #00ff66;
            }
            QLineEdit {
                background-color: #111116;
                border: 1px solid #4a4a5a;
                border-radius: 4px;
                color: #00ff66;
                padding: 4px;
                font-weight: bold;
            }
        """)

        self.setWindowTitle("ESP32 Robot Control Station")

        # Удаление упоминаний Freenove из интерфейса
        for widget in self.findChildren(QLabel):
            if "Freenove" in widget.text():
                widget.setText("")
                widget.hide()

        # Геометрия интерфейса
        MARGIN = 15
        WIN_W, WIN_H = 820, 660
        self.resize(WIN_W, WIN_H)
        self.setMinimumSize(WIN_W, WIN_H)

        TOP_Y, TOP_H = 45, 330
        LEFT_X, LEFT_W = MARGIN, 415
        RIGHT_X = LEFT_X + LEFT_W + MARGIN
        RIGHT_W = WIN_W - RIGHT_X - MARGIN

        ROW2_Y, ROW2_H = TOP_Y + TOP_H + MARGIN, 35
        ROW3_Y = ROW2_Y + ROW2_H + 20
        ROW4_Y = ROW3_Y + 140

        if hasattr(self, 'label_Title'):
            self.label_Title.setGeometry(MARGIN, 8, WIN_W - 2 * MARGIN, 28)
            self.label_Title.setAlignment(Qt.AlignCenter)
            self.label_Title.setText("ESP32 AUTOMOTIVE ROBOT SYSTEM")
            self.label_Title.setStyleSheet("font-size: 14px; font-weight: bold; color: #007acc; letter-spacing: 1px;")

        self.label_Video.setGeometry(LEFT_X, TOP_Y, LEFT_W, TOP_H)

        self.radar_base_geom = (RIGHT_X, TOP_Y, RIGHT_W, TOP_H)
        self.radar_map = RadarMapWidget(self)
        self.radar_map.setGeometry(*self.radar_base_geom)
        self.radar_map.show()

        self.Btn_Video.setGeometry(LEFT_X + 210, ROW2_Y, LEFT_W - 210, ROW2_H)

        rec_w = 180
        rec_x = RIGHT_X + (RIGHT_W - rec_w) // 2
        self.Btn_Record = QPushButton("Начать запись", self)
        self.Btn_Record.setObjectName("Btn_Record")
        self.Btn_Record.setGeometry(rec_x, ROW2_Y, rec_w, ROW2_H)

        self.IP.setText("192.168.4.1")
        self.IP.setGeometry(LEFT_X, ROW2_Y, 95, ROW2_H)
        self.Btn_Connect.setGeometry(LEFT_X + 100, ROW2_Y, 110, ROW2_H)

        self.clear_led_interface()
        if hasattr(self, 'Btn_Buzzer'):
            self.Btn_Buzzer.hide()
            self.Btn_Buzzer.setEnabled(False)

        cx1 = LEFT_X + LEFT_W // 2
        FB_W, FB_H = 100, 35
        TURN_W = 130

        self.Btn_ForWard.setGeometry(cx1 - FB_W // 2, ROW3_Y, FB_W, FB_H)
        self.Btn_Turn_Left.setGeometry(cx1 - FB_W // 2 - 10 - TURN_W, ROW3_Y + 45, TURN_W, FB_H)
        self.Btn_Turn_Right.setGeometry(cx1 + FB_W // 2 + 10, ROW3_Y + 45, TURN_W, FB_H)
        self.Btn_BackWard.setGeometry(cx1 - FB_W // 2, ROW3_Y + 90, FB_W, FB_H)

        cx2 = RIGHT_X + RIGHT_W // 2
        CAM_W, CAM_H = 90, 32

        self.Btn_Up.setGeometry(cx2 - CAM_W // 2, ROW3_Y, CAM_W, CAM_H)
        self.Btn_Left.setGeometry(cx2 - CAM_W // 2 - 10 - CAM_W, ROW3_Y + 42, CAM_W, CAM_H)
        self.Btn_Home.setGeometry(cx2 - CAM_W // 2, ROW3_Y + 42, CAM_W, CAM_H)
        self.Btn_Right.setGeometry(cx2 + CAM_W // 2 + 10, ROW3_Y + 42, CAM_W, CAM_H)
        self.Btn_Down.setGeometry(cx2 - CAM_W // 2, ROW3_Y + 84, CAM_W, CAM_H)

        self.servo1 = 90
        self.servo2 = 90

        bat_w = 180
        bat_x = cx1 - (bat_w // 2)

        self.progress_Power.setGeometry(bat_x, ROW4_Y, bat_w, 35)
        self.progress_Power.setTextVisible(True)
        self.progress_Power.setAlignment(Qt.AlignCenter)
        self.progress_Power.setStyleSheet("""
            QProgressBar {
                border: 2px solid #555566;
                border-radius: 6px;
                background-color: #111116;
                color: #ffffff;
                font-weight: bold;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, stop:0 #00cc44, stop:1 #00ff66);
                border-radius: 4px;
                margin: 1px;
            }
        """)

        self.battery_tip = QLabel(self)
        self.battery_tip.setGeometry(bat_x + bat_w, ROW4_Y + (35 - 19) // 2, 8, 19)
        self.battery_tip.setStyleSheet("background-color: #555566; border-radius: 1px;")
        self.battery_tip.show()

        self.HSlider_Servo1.setGeometry(cx2 - CAM_W // 2 - 10 - CAM_W, ROW4_Y, 210, 28)
        self.HSlider_Servo1.setValue(self.servo1)
        self.label_Servo1.setGeometry(cx2 - CAM_W // 2 - 10 - CAM_W + 220, ROW4_Y - 4, 70, 28)

        # Индикатор угла перенесен НАВЕРХ слайдера (на противоположную сторону)
        self.VSlider_Servo2.setGeometry(WIN_W - MARGIN - 20, ROW3_Y, 20, 166)
        self.VSlider_Servo2.setValue(self.servo2)
        self.label_Servo2.setGeometry(WIN_W - MARGIN - 70, ROW3_Y - 5, 50, 26)
        self.label_Servo2.setAlignment(Qt.AlignCenter)

        self.running = True
        self.original_size = self.size()
        self.aspect_ratio = self.original_size.width() / self.original_size.height()
        self.current_linear_speed = 0.0
        self.current_angular_speed = 0.0

        self.TCP = VideoStreaming()
        self.connect_signals()

        # БЕЗОПАСНЫЙ ТАЙМЕР ДЛЯ БАТАРЕИ (Вместо зависающего фонового потока)
        self.battery_timer = QTimer(self)
        self.battery_timer.timeout.connect(self.send_battery_request)

        self.odometry_timer = QTimer(self)
        self.odometry_timer.timeout.connect(self.update_odometry)
        self.odometry_timer.start(50)

        self.video_thread = Thread(target=self.update_video_loop, daemon=True)
        self.video_thread.start()

    def clear_led_interface(self):
        led_widgets = [
            'Led_Module', 'RGB', 'Color_R', 'Color_G', 'Color_B', 'Color_W', 'W',
            'checkBox_Led_Mode1', 'checkBox_Led_Mode2', 'checkBox_Led_Mode3', 'checkBox_Led_Mode4',
            'checkBox_Matrix_Mode1', 'checkBox_Matrix_Mode2', 'checkBox_Matrix_Mode3', 'checkBox_Matrix_Mode4'
        ]
        for w_name in led_widgets:
            if hasattr(self, w_name):
                w = getattr(self, w_name)
                w.hide()
                w.setEnabled(False)

        extra_control_widgets = ['horizontalLayoutWidget_2', 'horizontalLayoutWidget_3']
        for w_name in extra_control_widgets:
            if hasattr(self, w_name):
                w = getattr(self, w_name)
                w.hide()
                w.setEnabled(False)

        camera_control_widgets = ['Btn_Cam_Left', 'Btn_Cam_Origin', 'Btn_Cam_Right']
        for w_name in camera_control_widgets:
            if hasattr(self, w_name):
                w = getattr(self, w_name)
                w.hide()
                w.setEnabled(False)

        for i in range(1, 13):
            if hasattr(self, f"L{i}"):
                getattr(self, f"L{i}").hide()

    def connect_signals(self):
        self.Btn_ForWard.pressed.connect(lambda: self.set_movement(4.0, 0.0, 2500, 2500, 2500, 2500))
        self.Btn_ForWard.released.connect(self.stop_movement)

        self.Btn_BackWard.pressed.connect(lambda: self.set_movement(-4.0, 0.0, -2500, -2500, -2500, -2500))
        self.Btn_BackWard.released.connect(self.stop_movement)

        self.Btn_Turn_Left.pressed.connect(lambda: self.set_movement(0.0, 5.0, -2500, -2500, 2500, 2500))
        self.Btn_Turn_Left.released.connect(self.stop_movement)

        self.Btn_Turn_Right.pressed.connect(lambda: self.set_movement(0.0, -5.0, 2500, 2500, -2500, -2500))
        self.Btn_Turn_Right.released.connect(self.stop_movement)

        self.Btn_Connect.clicked.connect(self.toggle_connection)
        self.Btn_Video.clicked.connect(self.toggle_video)
        self.Btn_Record.clicked.connect(self.toggle_recording)

        self.HSlider_Servo1.valueChanged.connect(self.on_servo_change)
        self.VSlider_Servo2.valueChanged.connect(self.on_servo_change)

        self.Btn_Home.clicked.connect(self.reset_servos)
        self.Btn_Up.clicked.connect(lambda: self.adjust_servo(0, 10))
        self.Btn_Down.clicked.connect(lambda: self.adjust_servo(0, -10))
        self.Btn_Left.clicked.connect(lambda: self.adjust_servo(1, -10))
        self.Btn_Right.clicked.connect(lambda: self.adjust_servo(1, 10))

    def set_movement(self, lin, ang, m1, m2, m3, m4):
        self.current_linear_speed = lin
        self.current_angular_speed = ang
        try:
            self.TCP.sendData(f"{cmd.CMD_MOTOR}#{m1}#{m2}#{m3}#{m4}\n")
        except:
            pass

    def stop_movement(self):
        self.current_linear_speed = 0.0
        self.current_angular_speed = 0.0
        try:
            self.TCP.sendData(f"{cmd.CMD_MOTOR}#0#0#0#0\n")
        except:
            pass

    def update_odometry(self):
        if self.current_linear_speed != 0.0 or self.current_angular_speed != 0.0:
            self.radar_map.move_robot(self.current_linear_speed, self.current_angular_speed)

    def send_battery_request(self):
        if "Отключить" in self.Btn_Connect.text():
            try:
                self.TCP.sendData(f"{cmd.CMD_POWER}\n")
            except:
                self.battery_timer.stop()

    def toggle_connection(self):
        if "Подключить" in self.Btn_Connect.text() or "Connect" in self.Btn_Connect.text():
            ip = self.IP.text()
            if ip:
                self.radar_map.clear_map()
                self.TCP.StartTcpClient(ip)
                self.recv_thread = Thread(target=self.recv_data_loop, args=(ip,), daemon=True)
                self.recv_thread.start()
                self.Btn_Connect.setText("Отключить")
                self.battery_timer.start(3000) # Опрос батареи каждые 3 секунды
        else:
            self.Btn_Connect.setText("Подключить")
            self.battery_timer.stop()
            self.TCP.StopTcpcClient()

    def toggle_video(self):
        if "Открыть" in self.Btn_Video.text() or "Open" in self.Btn_Video.text():
            self.Btn_Video.setText("Закрыть видео")
            if "Отключить" in self.Btn_Connect.text():
                self.TCP.sendData(f"{cmd.CMD_VIDEO}#1\n")
                Thread(target=self.TCP.streaming, args=(self.IP.text(),), daemon=True).start()
        else:
            self.Btn_Video.setText("Открыть видео")
            if "Отключить" in self.Btn_Connect.text():
                self.TCP.sendData(f"{cmd.CMD_VIDEO}#0\n")
            if self.TCP.recording:
                self.toggle_recording()

    def toggle_recording(self):
        if "Начать" in self.Btn_Record.text() or "Start" in self.Btn_Record.text():
            if "Отключить" in self.Btn_Connect.text():
                output_path = self.TCP.start_recording()
                self.Btn_Record.setText("Остановить запись")
            else:
                QMessageBox.information(self, "Запись", "Сначала подключитесь к роботу")
        else:
            output_path = self.TCP.stop_recording()
            self.Btn_Record.setText("Начать запись")

    @pyqtSlot(int)
    def update_battery_ui(self, val):
        """Безопасное обновление стилей прогресс-бара в Главном Потоке"""
        self.progress_Power.setValue(val)
        if val < 20:
            color_qss = "QProgressBar::chunk { background-color: #ff3333; border-radius: 4px; }"
        elif val < 50:
            color_qss = "QProgressBar::chunk { background-color: #ffaa00; border-radius: 4px; }"
        else:
            color_qss = "QProgressBar::chunk { background-color: #00ff66; border-radius: 4px; }"

        self.progress_Power.setStyleSheet("""
            QProgressBar { border: 2px solid #555566; border-radius: 6px; background-color: #111116; color: white; font-weight: bold; text-align: center; }
        """ + color_qss)

    def recv_data_loop(self, ip):
        self.TCP.socket1_connect(ip)
        rest_buffer = ""
        
        while "Отключить" in self.Btn_Connect.text():
            try:
                data = self.TCP.recvData()
                if not data:
                    break

                complete_data = rest_buffer + data
                lines = complete_data.split("\n")
                
                if len(lines) > 0 and complete_data and not complete_data.endswith("\n"):
                    rest_buffer = lines.pop()
                else:
                    rest_buffer = ""

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    payload = line.split("#")

                    if "CMD_DISTANCE" in line and len(payload) > 1:
                        try:
                            dist = int(payload[1])
                            angle = self.HSlider_Servo1.value()
                            self.radar_map.add_point(dist, angle)
                        except:
                            pass

                    elif "CMD_POWER" in line and len(payload) > 1:
                        try:
                            v = float(payload[1])
                            percentage = int(((v - 7.0) / 1.4) * 100)
                            val = max(0, min(percentage, 100))

                            # Передаем задачу изменения UI главному потоку через invokeMethod
                            QMetaObject.invokeMethod(self, "update_battery_ui", Qt.QueuedConnection, Q_ARG(int, val))
                        except:
                            pass
            except:
                break
        
        QMetaObject.invokeMethod(self.battery_timer, "stop", Qt.QueuedConnection)

    def adjust_servo(self, is_axis_x, diff):
        if is_axis_x:
            self.servo1 = max(0, min(180, self.servo1 + diff))
            self.HSlider_Servo1.setValue(self.servo1)
        else:
            self.servo2 = max(80, min(180, self.servo2 + diff))
            self.VSlider_Servo2.setValue(self.servo2)

    def reset_servos(self):
        self.servo1, self.servo2 = 90, 90
        self.HSlider_Servo1.setValue(self.servo1)
        self.VSlider_Servo2.setValue(self.servo2)

    def on_servo_change(self):
        self.servo1 = self.HSlider_Servo1.value()
        self.servo2 = self.VSlider_Servo2.value()
        self.label_Servo1.setText(str(self.servo1))
        self.label_Servo2.setText(str(self.servo2))
        try:
            self.TCP.sendData(f"{cmd.CMD_SERVO}#0#{180 - self.servo1}\n")
            self.TCP.sendData(f"{cmd.CMD_SERVO}#1#{self.servo2}\n")
        except:
            pass

    def update_video_loop(self):
        while self.running:
            try:
                if not self.TCP.video_Flag and self.TCP.image is not None:
                    cv2.flip(self.TCP.image, -1, self.TCP.image)
                    img = QImage(self.TCP.image.data, self.TCP.image.shape[1], self.TCP.image.shape[0], self.TCP.image.strides[0], QImage.Format_BGR888)
                    pix = QPixmap.fromImage(img)
                    QMetaObject.invokeMethod(self.label_Video, "setPixmap", Qt.QueuedConnection, Q_ARG(QPixmap, pix.scaled(self.label_Video.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                    self.TCP.video_Flag = True
            except:
                pass
            time.sleep(0.03)

    def resizeEvent(self, event):
        if float(self.width()) / self.height() != self.aspect_ratio:
            self.resize(self.width(), int(self.width() / self.aspect_ratio))

        w_scale = self.width() / self.original_size.width()
        h_scale = self.height() / self.original_size.height()

        rx, ry, rw, rh = self.radar_base_geom
        self.radar_map.setGeometry(int(rx * w_scale), int(ry * h_scale), int(rw * w_scale), int(rh * h_scale))

    def closeEvent(self, event):
        self.running = False
        try:
            self.battery_timer.stop()
            self.TCP.StopTcpcClient()
        except:
            pass
        event.accept()
        os._exit(0)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = mywindow()
    w.show()
    sys.exit(app.exec_())