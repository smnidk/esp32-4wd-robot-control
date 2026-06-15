/**********************************************************************
  Filename    : Camera Car (Obstacle Blocking Only)
  Product     : Freenove 4WD Car for ESP32
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

// --- ULTRASONIC ---
#define TRIG_PIN 12 
#define ECHO_PIN 15

unsigned long obstacleTimer = 0;
unsigned long lastTelemetryTime = 0;
unsigned long debugTimer = 0;
unsigned long ultrasonicScanTimer = 0;
int currentLeftMotor = 0;
int currentRightMotor = 0;

String CmdArray[8];
int paramters[8];
bool videoFlag = 0;

// Обязательное объявление серверов (внешние объекты для других потоков)
extern WiFiServer server_Cmd;
extern WiFiServer server_Camera;

// Прототипы функций, чтобы компилятор видел их до вызова в setup()
void loopTask_Camera(void *pvParameters);
void Get_Command(String inputStringTemp);

// -------------------- DISTANCE --------------------
int getDistance() {
  const int samples = 5; // Возьмем 5 замеров для точности
  int distances[samples];
  int validSamples = 0;
  int sum = 0;

  for (int i = 0; i < samples; i++) {
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    
    // Ограничиваем время ожидания (timeout) до 15000 мкс (около 250 см), чтобы код не зависал
    long duration = pulseIn(ECHO_PIN, HIGH, 15000); 
    int d = duration * 0.034 / 2;

    // Фильтруем заведомый бред датчика (0 или слишком далеко)
    if (d > 2 && d < 250) { 
      distances[validSamples] = d;
      validSamples++;
    }
    delay(10); // Небольшая пауза между импульсами, чтобы эхо утихло
  }

  // Если получили хоть какие-то адекватные замеры
  if (validSamples > 0) {
    // Находим минимальное обнаруженное расстояние среди валидных (самое безопасное для робота)
    int minDistance = distances[0];
    for(int i = 1; i < validSamples; i++) {
      if(distances[i] < minDistance) {
        minDistance = distances[i];
      }
    }
    return minDistance;
  }
  
  return 999; // Если датчик ничего не поймал, возвращаем "путь свободен"
}

// -------------------- BLOCKING RULE --------------------
bool isForwardBlocked(int leftMotor, int rightMotor, int distance) {
  bool forward = (leftMotor > 0 && rightMotor > 0);
  return forward && distance < 15;
}

// -------------------- OBSTACLE MODE --------------------
void Obstacle_Avoidance_Car() {
  if (millis() - obstacleTimer < 100) return;
  obstacleTimer = millis();

  int distance = getDistance(); // Переменная создается прямо здесь!
  if (distance <= 0) return;

  if (distance < 15) {
    Motor_Move(-1500, -1500, -1500, -1500);
    WS2812_Set_Color_1(0xFFF, 255, 0, 0);
  }
  else if (distance < 25) {
    Motor_Move(-1200, -1200, 1200, 1200);
    WS2812_Set_Color_1(0xFFF, 255, 120, 0);
  }
  else {
    Motor_Move(1500, 1500, 1500, 1500);
    WS2812_Set_Color_1(0xFFF, 0, 255, 0);
  }

  WS2812_Show(0);
}

// -------------------- MODE SELECT --------------------
void Custom_Car_Select(int mode) {
  if (mode == 3) {
    Obstacle_Avoidance_Car();
  } else {
    Car_Select(mode);
  }
}

// -------------------- WIFI --------------------
void WiFi_Init() {
  ssid_Router     = (char*)"Redmi Note 11";    
  password_Router = (char*)"prl_dswp";    
  ssid_AP         = (char*)"Sunshine";    
  password_AP     = (char*)"Sunshine";    
  frame_size      = FRAMESIZE_CIF;
}

WiFiServer server_Cmd(4000);
WiFiServer server_Camera(7000);

// -------------------- SETUP --------------------
void setup() {
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  Serial.begin(115200);

  WiFi_Init();
  WiFi_Setup(1);

  server_Cmd.begin(4000);
  server_Camera.begin(7000);

  cameraSetup();
  Emotion_Setup();
  WS2812_Setup();
  PCA9685_Setup();
  Light_Setup();
  Track_Setup();

  Setup_Battery_Monitor();

  // Создание фоновых задач для ядер процессора ESP32
  xTaskCreateUniversal(loopTask_Camera, "loopTask_Camera", 8192, NULL, 0, NULL, 0);
  xTaskCreateUniversal(loopTask_WTD, "loopTask_WTD", 8192, NULL, 0, NULL, 0);
}

// -------------------- MAIN LOOP --------------------
void loop() {
  // 1. Принимаем входящее подключение от Python-клиента
  WiFiClient client = server_Cmd.accept();

  if (client) {
    Serial.println("Python UI connected via TCP!");

    while (client.connected()) {
      
      // 2. ОТПРАВКА ДАННЫХ ДЛЯ КАРТЫ РАДАРА (Каждые 300 мс)
      // Перенесено внутрь цикла, где объект client гарантированно существует и активен
      if (millis() - debugTimer > 300) { 
        debugTimer = millis();
        int d = getDistance();
        Serial.print("Distance sent to UI: ");
        Serial.println(d);
        
        // Отправляем строго в формате, который ждет ваш Python-скрипт
        client.print("CMD_DISTANCE#" + String(d) + "\n");
      }

      // 3. АВТОМАТИЧЕСКИЙ СЕЙФ-РЕЖИМ ПРИ ЕЗДЕ (Каждые 60 мс)
      if (millis() - ultrasonicScanTimer > 60) {
        ultrasonicScanTimer = millis();
        int current_d = getDistance(); 
        
        if (isForwardBlocked(currentLeftMotor, currentRightMotor, current_d)) {
          Motor_Move(0, 0, 0, 0); // Экстренное торможение!
          currentLeftMotor = 0;
          currentRightMotor = 0;
          WS2812_Set_Color_1(0xFFF, 255, 0, 0); // Включаем красный свет
          WS2812_Show(0);
        }
      }

      // 4. ОБРАБОТКА ВХОДЯЩИХ КОМАНД ОТ ПУЛЬТА
      if (client.available()) {
        String inputStringTemp = client.readStringUntil('\n');
        Get_Command(inputStringTemp);

        if (CmdArray[0] == CMD_MOTOR) {
          Car_SetMode(0);
          int distance = getDistance();
          int leftMotor  = paramters[1];
          int rightMotor = paramters[3];

          if (isForwardBlocked(leftMotor, rightMotor, distance)) {
            Motor_Move(0, 0, 0, 0); 
            currentLeftMotor = 0;
            currentRightMotor = 0;
            WS2812_Set_Color_1(0xFFF, 255, 0, 0);
            WS2812_Show(0);
          } else {
            // Запоминаем текущую скорость для фонового мониторинга безопасности
            currentLeftMotor = leftMotor;
            currentRightMotor = rightMotor;
            Motor_Move(leftMotor, leftMotor, rightMotor, rightMotor);
          }
        }

        if (CmdArray[0] == CMD_LED_MOD)
          WS2812_SetMode(paramters[1]);

        if (CmdArray[0] == CMD_LED)
          WS2812_Set_Color_1(paramters[1], paramters[2], paramters[3], paramters[4]);

        if (CmdArray[0] == CMD_MATRIX_MOD)
          Emotion_SetMode(paramters[1]);

        if (CmdArray[0] == CMD_VIDEO)
          videoFlag = paramters[1];

        if (CmdArray[0] == CMD_SERVO) {
          if (paramters[1] == 0) Servo_1_Angle(paramters[2]);
          else if (paramters[1] == 1) Servo_2_Angle(paramters[2]);
        }

        if (CmdArray[0] == CMD_CAR_MODE) {
          Car_SetMode(paramters[1]);
        }

        // Очистка массивов парсера
        for (int i = 0; i < 8; i++) {
          CmdArray[i] = "";
          paramters[i] = 0;
        }
      }

      WS2812_Show(ws2812_task_mode);
      Custom_Car_Select(carFlag);
    }
    
    // Если клиент отключился от сети
    client.stop();
    Serial.println("Python UI disconnected.");
    
    // Гасим моторы на случай аварийного обрыва связи
    Motor_Move(0, 0, 0, 0);
    currentLeftMotor = 0;
    currentRightMotor = 0;
  }
}

// -------------------- РЕАЛИЗАЦИЯ ФУНКЦИИ loopTask_Camera --------------------
void loopTask_Camera(void *pvParameters) {
  while (1) {
    WiFiClient client = server_Camera.accept();
    if (client) {
      Serial.println("Camera_Server connected to a client.");
      while (client.connected()) {
        if (videoFlag == 1) {
          camera_fb_t * fb = esp_camera_fb_get();
          if (fb != NULL) {
            uint8_t slen[4];
            slen[0] = fb->len >> 0;
            slen[1] = fb->len >> 8;
            slen[2] = fb->len >> 16;
            slen[3] = fb->len >> 24;
            client.write(slen, 4);
            client.write(fb->buf, fb->len);
            esp_camera_fb_return(fb);
          }
        }
        vTaskDelay(30 / portTICK_PERIOD_MS); // Ограничение частоты отправки кадров
      }
      client.stop();
      Serial.println("Camera Client Disconnected.");
    }
    vTaskDelay(100 / portTICK_PERIOD_MS);
  }
}

// -------------------- РЕАЛИЗАЦИЯ ПАРСЕРА КОМАНД Get_Command --------------------
void Get_Command(String inputStringTemp) {
  inputStringTemp.trim();
  int string_length = inputStringTemp.length();
  for (int i = 0; i < 8; i++) {
    int index = inputStringTemp.indexOf(INTERVAL_CHAR);
    if (index < 0) {
      if (string_length > 0) {
        CmdArray[i] = inputStringTemp;         
        paramters[i] = inputStringTemp.toInt();
      } else {
        CmdArray[i] = "";
        paramters[i] = 0;
      }
      break;
    }
    CmdArray[i] = inputStringTemp.substring(0, index);
    paramters[i] = CmdArray[i].toInt();
    inputStringTemp = inputStringTemp.substring(index + 1);
    string_length = inputStringTemp.length();
  }
}