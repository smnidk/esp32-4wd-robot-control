/**********************************************************************
  Filename    : Camera Car (Modified for Obstacle Avoidance Stand)
  Product     : Freenove 4WD Car for ESP32
  Author      : www.freenove.com
  Modification: 2026/05/30
**********************************************************************/

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiAP.h>
#include "esp_camera.h"
#include "Freenove_4WD_Car_WiFi.h"
#include "Freenove_4WD_Car_Emotion.h"
#include "Freenove_4WD_Car_WS2812.h"
#include "Freenove_4WD_Car_For_ESP32.h"

// --- 1. НАСТРОЙКИ УЛЬТРАЗВУКОВОГО ДАТЧИКА (HC-SR04) ---
#define TRIG_PIN 12 
#define ECHO_PIN 15

// --- 2. ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И НАСТРОЙКИ РЕЖИМА ---
bool isTestStandMode = true; // true - режим стенда (без моторов), false - боевой режим с моторами
bool blinkState = false;      // Состояние для мигания светодиодов
unsigned long obstacleTimer = 0;
unsigned long lastTelemetryTime = 0; // <<--- ИСПРАВЛЕНО: Теперь переменная объявлена на глобальном уровне!

String CmdArray[8];
int paramters[8];
bool videoFlag = 0;

// --- 3. ПРОТОТИПЫ ФУНКЦИЙ ДЛЯ КОМПИЛЯТОРА ---
int getDistance();
void alarmBlink();
void Get_Command(String inputStringTemp);
void loopTask_WIFI(void *pvParameters);
void loopTask_Cmd(void *pvParameters);
void loopTask_Camera(void *pvParameters);

// Функция замера расстояния (HC-SR04)
int getDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // таймаут 30мс (около 5 метров)
  if (duration == 0) return 400; // Если эха нет, считаем, что путь свободен
  return duration * 0.034 / 2;   // Перевод времени в сантиметры
}

// Функция мигания светодиодами при угрозе столкновения
void alarmBlink() {
  blinkState = !blinkState;
  if (blinkState) {
    ws2812_SetColor(0, 255, 0, 0); // Все 4 светодиода горят красным
    ws2812_SetColor(1, 255, 0, 0);
    ws2812_SetColor(2, 255, 0, 0);
    ws2812_SetColor(3, 255, 0, 0);
  } else {
    ws2812_Clear(); // Выключаем
  }
  ws2812_Show();
}

// --- 4. ОСНОВНЫЕ ФУНКЦИИ ИНИЦИАЛИЗАЦИИ И ЦИКЛА ---

void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  Serial.begin(115200);
  Serial.setDebugOutput(true);
  Serial.println();

  Init_Device(); // Инициализация периферии робота

  // Запуск задач FreeRTOS на ядрах процессора ESP32
  xTaskCreatePinnedToCore(loopTask_WIFI, "loopTask_WIFI", 4096, NULL, 1, NULL, 0);
  xTaskCreatePinnedToCore(loopTask_Cmd, "loopTask_Cmd", 4096, NULL, 1, NULL, 1);
  xTaskCreatePinnedToCore(loopTask_Camera, "loopTask_Camera", 4096, NULL, 1, NULL, 1);
}

void loop() {
  // Автономная логика защиты от столкновения (Проверка каждые 100 мс)
  if (millis() - obstacleTimer > 100) { 
    int distance = getDistance();
    
    if (distance < 20) { // Если препятствие ближе 20 см
      if (!isTestStandMode) {
        Motor_Move(0, 0, 0, 0); // Боевой режим: СТОП МОТОРЫ принудительно
      }
      alarmBlink();             // Мигаем светодиодами «Опасность»
      emotion_SetMode(4);       // Грустная/тревожная эмоция на матрице
    } else {
      if (blinkState) {
        blinkState = false;
        ws2812_Clear();
        ws2812_Show();
        emotion_SetMode(1);     // Возвращаем улыбку
      }
    }
    obstacleTimer = millis();
  }

  // Периодическая отправка данных дальномера для построения карты в Python
  if (millis() - lastTelemetryTime > 150) {
    int current_distance = getDistance();
    
    // Если управляющий сокет на порту 4000 активен и Python-клиент подключен
    if (cmdClient.connected()) { 
      // Отправляем пакет в формате, который без ошибок распарсит ваш скрипт main.py
      cmdClient.print("CMD_DISTANCE#" + String(current_distance) + "\n");
    }
    lastTelemetryTime = millis();
  }
}

// --- 5. РЕАЛИЗАЦИЯ ЗАДАЧ FREERTOS ---

void loopTask_WIFI(void *pvParameters) {
  while (1) {
    WIFI_Loop(); 
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

void loopTask_Cmd(void *pvParameters) {
  while (1) {
    cmdClient = server_Cmd.accept();
    if (cmdClient) {
      Serial.println("Command_Server connected to a client.");
      while (cmdClient.connected()) {
        if (cmdClient.available()) {
          String inputStringTemp = cmdClient.readStringUntil('\n');
          #ifdef DEBUG
            Serial.print("cmdClient.readStringUntil: ");
            Serial.println(inputStringTemp);
          #endif
          Get_Command(inputStringTemp);
        }
      }
      cmdClient.stop();
      Serial.println("Command Client Disconnected.");
    }
    vTaskDelay(10 / portTICK_PERIOD_MS);
  }
}

void loopTask_Camera(void *pvParameters) {
  while (1) {
    WiFiClient client = server_Camera.accept();
    if (client) {
      Serial.println("Camera_Server connected to a client.");
      if (client.connected()) {
        camera_fb_t * fb = NULL;
        while (client.connected()) {
          if (videoFlag == 1) {
            fb = esp_camera_fb_get();
            if (fb != NULL) {
              uint8_t slen[4];
              slen[0] = fb->len >> 0;
              slen[1] = fb->len >> 8;
              slen[2] = fb->len >> 16;
              slen[3] = fb->len >> 24;
              client.write(slen, 4);
              client.write(fb->buf, fb->len);
              Serial.println("Camera send");
              esp_camera_fb_return(fb);
            }
          }
        }
        client.stop();
        Serial.println("Camera Client Disconnected.");
        ESP.restart(); 
      }
    }
  }
}

void Get_Command(String inputStringTemp) {
  int string_length = inputStringTemp.length();
  for (int i = 0; i < 8; i++) {
    int index = inputStringTemp.indexOf(INTERVAL_CHAR);
    if (index < 0) {
      if (string_length > 0) {
        CmdArray[i] = inputStringTemp;         
        paramters[i] = inputStringTemp.toInt();
      }
      break;
    } else {
      string_length -= index;                                
      CmdArray[i] = inputStringTemp.substring(0, index);     
      inputStringTemp = inputStringTemp.substring(index + 1);
      paramters[i] = CmdArray[i].toInt();                    
    }
  }
  User_Get_Command(CmdArray, paramters); 
}