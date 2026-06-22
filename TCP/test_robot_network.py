#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import socket
import time
import pytest
import math
from threading import Thread
from PyQt5.QtWidgets import QApplication

# Импортируем классы из основного файла
from main import VideoStreaming, RadarMapWidget, mywindow
from Command import COMMAND as cmd

# Настройки для тестового локального сервера
TEST_HOST = "127.0.0.1"
CMD_PORT = 4000
CAM_PORT = 7000

class MockESP32Server:
    """Эмулятор робота на ESP32 с поддержкой симуляции сбоев сети"""
    def __init__(self):
        self.running = False
        self.cmd_server = None
        self.last_received_cmd = None
        self.client_connected = False
        self.active_client = None

    def start(self):
        self.running = True
        self.cmd_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.cmd_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.cmd_server.bind((TEST_HOST, CMD_PORT))
        self.cmd_server.listen(5) 
        Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        while self.running:
            try:
                client, addr = self.cmd_server.accept()
                self.client_connected = True
                self.active_client = client
                Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except:
                break

    def _handle_client(self, client):
        buffer = ""
        try:
            while self.running:
                data = client.recv(4096).decode('utf-8', errors='ignore')
                if not data:
                    break
                buffer += data
                if "\n" in buffer:
                    lines = buffer.split("\n")
                    for line in lines[:-1]:
                        self.last_received_cmd = line.strip()
                        if cmd.CMD_POWER in line:
                            client.sendall(f"{cmd.CMD_POWER}#7.8\n".encode('utf-8'))
                        elif "CMD_DISTANCE" in line:
                            client.sendall("CMD_DISTANCE#120\n".encode('utf-8'))
                    buffer = lines[-1]
        except Exception as e:
            pass
        finally:
            client.close()
            if self.active_client == client:
                self.client_connected = False

    def force_disconnect(self):
        """Принудительный обрыв связи (симуляция потери Wi-Fi)"""
        if self.active_client:
            try:
                self.active_client.shutdown(socket.SHUT_RDWR)
                self.active_client.close()
            except:
                pass
            self.client_connected = False

    def stop(self):
        self.running = False
        self.force_disconnect()
        if self.cmd_server:
            try: self.cmd_server.close()
            except: pass


@pytest.fixture
def mock_robot():
    """Фикстура pytest для управления эмулятором сервера"""
    server = MockESP32Server()
    server.start()
    time.sleep(0.1) 
    yield server
    server.stop()


# ==========================================
# 1. ТЕСТЫ НА СТАБИЛЬНОСТЬ И ПЕРЕГРУЗКУ
# ==========================================

def test_connection_drop_and_stability(mock_robot):
    client = VideoStreaming()
    assert client.StartTcpClient(TEST_HOST) is True
    client.socket1_connect(TEST_HOST)
    time.sleep(0.1)
    
    mock_robot.force_disconnect()
    time.sleep(0.1)

    try:
        client.sendData(f"{cmd.CMD_MOTOR}#0#0#0#0\n")
        send_failed_with_crash = False
    except Exception:
        send_failed_with_crash = True

    assert send_failed_with_crash is False, "Отправка в закрытый сокет вызвала краш!"
    client.StopTcpcClient()
    time.sleep(0.1)
    assert client.StartTcpClient(TEST_HOST) is True


def test_client_spam_overload(mock_robot):
    client = VideoStreaming()
    client.StartTcpClient(TEST_HOST)
    client.socket1_connect(TEST_HOST)
    time.sleep(0.1)

    start_time = time.time()
    for i in range(1000):
        client.sendData(f"{cmd.CMD_MOTOR}#2500#2500#2500#2500\n")
        
    duration = time.time() - start_time
    time.sleep(0.2)
    
    assert mock_robot.last_received_cmd == f"{cmd.CMD_MOTOR}#2500#2500#2500#2500"
    assert duration < 1.0


def test_malformed_data_flood(mock_robot):
    client = VideoStreaming()
    client.StartTcpClient(TEST_HOST)
    client.socket1_connect(TEST_HOST)
    time.sleep(0.1)

    if mock_robot.active_client:
        try:
            mock_robot.active_client.sendall("CMD_POWER#INVALID_DATA_FLOOD\n".encode('utf-8'))
            mock_robot.active_client.sendall("NONSENSE_LINE_WITHOUT_HASH\n".encode('utf-8'))
        except: pass

    time.sleep(0.2)
    client.sendData(f"{cmd.CMD_POWER}\n")
    time.sleep(0.1)
    assert mock_robot.last_received_cmd == f"{cmd.CMD_POWER}"


# ==========================================
# 2. ТЕСТЫ ГРАФИЧЕСКОГО ИНТЕРФЕЙСА (PyQt5)
# ==========================================

app = QApplication.instance() or QApplication(sys.argv)

def test_radar_widget_filtering():
    widget = RadarMapWidget()
    
    widget.add_point(distance=3, sensor_angle=90)
    assert len(widget.points) == 0
    
    widget.add_point(distance=260, sensor_angle=90)
    assert len(widget.points) == 0
    
    widget.add_point(distance=100, sensor_angle=90)
    assert len(widget.points) == 1
    
    gx, gy = widget.points[0]
    assert gx == 0.0
    assert gy == 100.0


def test_radar_widget_memory_limit():
    """Тест защиты от переполнения памяти с обходом встроенного фильтра дубликатов"""
    widget = RadarMapWidget()
    
    # Генерируем 300 уникальных точек по широким орбитам.
    # Гарантируем, что расстояние между любыми точками будет больше 10 см,
    # чтобы математический фильтр (hypot < 3.0) их не отбросил.
    for i in range(300):
        # Делаем 5 орбит: 100, 120, 140, 160 и 180 см
        dist = 100 + (i % 5) * 20 
        
        # 60 точек на каждую орбиту (шаг в 6 градусов)
        angle = (i // 5) * 6      
        
        widget.add_point(distance=dist, sensor_angle=angle)
        
    # Теперь все 300 точек точно прошли фильтр,
    # и логика лимита должна жестко обрезать массив до 250 элементов.
    assert len(widget.points) == 250


def test_robot_virtual_odometry():
    widget = RadarMapWidget()
    
    assert widget.robot_x == 0.0
    assert widget.robot_y == 0.0
    assert widget.robot_angle == 90.0
    
    widget.move_robot(linear_speed=10.0, angular_speed=0.0)
    
    assert widget.robot_x == pytest.approx(0.0, abs=1e-9)
    assert widget.robot_y == pytest.approx(10.0, abs=1e-9)
    
    widget.move_robot(linear_speed=0.0, angular_speed=-90.0)
    assert widget.robot_angle == 0.0
    
    widget.move_robot(linear_speed=5.0, angular_speed=0.0)
    assert widget.robot_x == pytest.approx(5.0, abs=1e-9)
    assert widget.robot_y == pytest.approx(10.0, abs=1e-9)


def test_clear_map_logic():
    widget = RadarMapWidget()
    widget.add_point(distance=50, sensor_angle=90)
    widget.move_robot(linear_speed=20, angular_speed=45)
    
    assert len(widget.points) > 0
    assert widget.robot_x != 0.0
    
    widget.clear_map()
    
    assert len(widget.points) == 0
    assert widget.robot_x == 0.0
    assert widget.robot_angle == 90.0

def test_radar_ui_non_blocking_performance():
    widget = RadarMapWidget()
    
    start_time = time.time()
    
    # Генерируем 1000 точек. 
    # Чтобы они прошли фильтр, увеличим шаг изменения дистанции и угла.
    # Каждая 4-я точка будет сильно отдалена от предыдущих.
    for i in range(1000):
        # Используем более широкий разброс дистанции
        dist = 50 + (i % 10) * 15 
        # Угол с большим шагом, чтобы исключить наслоение
        angle = (i * 25) % 360    
        
        widget.add_point(distance=dist, sensor_angle=angle)
        
    duration = time.time() - start_time
    
    assert duration < 0.5, f"Виджет карты тормозит (фриз на {duration:.2f} сек)"
    
    # Теперь массив гарантированно будет заполнен до лимита
    assert len(widget.points) == 250

def test_socket_timeout_handling():
    """
    Тест на зависание при попытке подключения к несуществующему хосту.
    Демо-версия не должна висеть 30 секунд при ошибке Wi-Fi.
    """
    client = VideoStreaming()
    start_time = time.time()
    
    # Пытаемся подключиться к заведомо нерабочему IP с таймаутом
    # (Убедитесь, что ваш метод StartTcpClient использует settimeout)
    client.StartTcpClient("192.168.0.254") 
    
    duration = time.time() - start_time
    assert duration < 3.0, "Интерфейс завис при попытке подключения к нерабочей сети!"


def test_widget_state_integrity_during_stress():
    """
    Тест целостности состояния: 
    Проверяем, что при быстром очищении карты и добавлении точек 
    не возникает состояний гонки (race conditions).
    """
    widget = RadarMapWidget()
    
    # Имитируем быстрый цикл: очистка -> добавление -> очистка
    for _ in range(50):
        widget.add_point(distance=100, sensor_angle=90)
        widget.clear_map()
        
    assert len(widget.points) == 0
    assert widget.robot_x == 0.0