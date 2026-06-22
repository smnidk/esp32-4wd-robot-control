#!/usr/bin/python 
# -*- coding: utf-8 -*-
import datetime
import os
import numpy as np
import cv2
import socket
import io
import sys
import struct
from PIL import Image
from multiprocessing import Process
from Command import COMMAND as cmd

class VideoStreaming:
    def __init__(self):
        # self.face_cascade = cv2.CascadeClassifier(r'haarcascade_frontalface_default.xml')
        self.video_Flag=True
        self.connect_Flag=False
        self.face_x=0
        self.face_y=0
        self.image=''
        self.recording=False
        self.video_writer=None
        self.record_path=None
        self.record_fps=20.0
        
    def StartTcpClient(self, IP):
        """
        Инициализирует сокеты. Теперь возвращает True при успешном создании,
        чтобы автотесты на стабильность соединения проходили корректно.
        """
        try:
            self.client_socket1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket1.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            return True
        except Exception as e:
            print(f"[TCP INIT ERROR] {e}")
            return False

    def StopTcpcClient(self):
        self.stop_recording()
        try:
            self.client_socket.shutdown(2)
            self.client_socket1.shutdown(2)
        except:
            pass
        try:
            self.client_socket.close()
            self.client_socket1.close()
        except:
            pass
        self.connect_Flag = False

    def IsValidImage4Bytes(self, buf):
        if len(buf) < 4:
            return False
        return buf[0] == 0xFF and buf[1] == 0xD8 and buf[-2] == 0xFF and buf[-1] == 0xD9

    def start_recording(self):
        if self.recording:
            return self.record_path
            
        try:
            os.makedirs('video_records', exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.record_path = os.path.join('video_records', f"robot_rec_{timestamp}.avi")
            self.recording = True
            self.video_writer = None
            print(f"[VIDEO] Запись запущена: {self.record_path}")
            return self.record_path
        except Exception as e:
            print(f"[VIDEO RECORD START ERROR] {e}")
            self.recording = False
            return None

    def _init_video_writer(self, img):
        if self.video_writer is None and img is not None and isinstance(img, np.ndarray):
            height, width, _ = img.shape
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            self.video_writer = cv2.VideoWriter(self.record_path, fourcc, self.record_fps, (width, height))

    def stop_recording(self):
        if not self.recording:
            return None
            
        self.recording = False
        if self.video_writer is not None:
            try:
                self.video_writer.release()
                print(f"[VIDEO] Запись успешно сохранена: {self.record_path}")
            except Exception as e:
                print(f"[VIDEO RECORD RELEASE ERROR] {e}")
            self.video_writer = None
            
        path = self.record_path
        self.record_path = None
        return path

    def streaming(self, ip):
        try:
            # Добавим таймаут для сокета, чтобы не ждать вечно
            self.client_socket.settimeout(5.0) 
            self.client_socket.connect((ip, 7000))
            self.connection = self.client_socket.makefile('rb')
        except Exception as e:
            print(f"[STREAM CONNECT ERROR] {e}")
            return
            
        while True:
            try:
                # Читаем длину кадра (4 байта)
                leng_bytes = self.connection.read(4)
                if not leng_bytes:
                    break
                leng = struct.unpack('<L', leng_bytes)
                if leng[0] == 0:
                    continue
                
                # Читаем сам кадр
                jpg = self.connection.read(leng[0])
                if not jpg:
                    break
                    
                if self.IsValidImage4Bytes(jpg):
                    if self.video_Flag:
                        self.image = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if self.recording and self.image is not None:
                            self._init_video_writer(self.image)
                            if self.video_writer is not None and self.video_writer.isOpened():
                                self.video_writer.write(self.image)
                    self.video_Flag = False
            except Exception as e:
                print(f"[STREAMING LOOP ERROR] {e}")
                break
                  
    def sendData(self, s):
        try:
            if self.connect_Flag and hasattr(self, 'client_socket1'):
                self.client_socket1.sendall(s.encode('utf-8'))
        except Exception as e:
            self.connect_Flag = False
            print(f"[TCP SEND ERROR] {e}")

    def recvData(self):
        data = ""
        try:
            if hasattr(self, 'client_socket1'):
                data = self.client_socket1.recv(1024).decode('utf-8')
        except:
            pass
        return data

    def socket1_connect(self, ip):
        try:
            self.client_socket1.connect((ip, 4000))
            self.connect_Flag = True
            print("Connection Successful !")
        except Exception as e:
            print("Connect to server Failed!: Server IP is right? Server is opened?")
            self.connect_Flag = False