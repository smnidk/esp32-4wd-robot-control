#include <Freenove_WS2812_Lib_for_ESP32.h>

#define TRIG_PIN 12 
#define ECHO_PIN 15

// Настройки светодиодов WS2812
#define WS2812_PIN        32  // Пин управления светодиодами на плате Freenove
#define LEDS_COUNT        12  // Всего 12 светодиодов на корпусе
#define CRITICAL_DIST_CM  25  // Критическое расстояние в сантиметрах

// Создаем объект для управления светодиодной лентой
Freenove_ESP32_WS2812 ledStrip = Freenove_ESP32_WS2812(LEDS_COUNT, WS2812_PIN, 0, TYPE_GRB);

bool blinkState = false; // Переменная для мигания красным цветом

void setup() {
  Serial.begin(115200);
  
  // Инициализация пинов датчика
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  
  // Инициализация светодиодов
  ledStrip.begin();
  ledStrip.setBrightness(50); // Яркость от 0 до 255
  
  Serial.println("--- Старт теста датчика HC-SR04 с WS2812 индикацией ---");
}

void loop() {
  // Очищаем триггер
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  
  // Выдаем импульс в 10 микросекунд
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  // Измеряем время ответного импульса
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); 
  
  // Вычисляем расстояние в сантиметрах
  int distance = duration * 0.034 / 2;
  
  // Вывод в Монитор порта
  Serial.print("Расстояние: ");
  
  if (duration == 0) {
    Serial.println("Вне диапазона или датчик не подключен!");
    
    // Если датчик потерял сигнал, подсветим светодиоды синим (сигнал ошибки)
    for (int i = 0; i < LEDS_COUNT; i++) {
      ledStrip.setLedColorData(i, 0, 0, 255); // Синий цвет (R=0, G=0, B=255)
    }
    ledStrip.show();
  } 
  else {
    Serial.print(distance);
    Serial.println(" см");
    
    // Проверка критического расстояния
    if (distance <= CRITICAL_DIST_CM && distance > 0) {
      // КРИТИЧЕСКОЕ РАССТОЯНИЕ: мигаем всеми светодиодами красным цветом
      blinkState = !blinkState;
      
      for (int i = 0; i < LEDS_COUNT; i++) {
        if (blinkState) {
          ledStrip.setLedColorData(i, 255, 0, 0); // Красный цвет (R=255, G=0, B=0)
        } else {
          ledStrip.setLedColorData(i, 0, 0, 0);   // Выключено
        }
      }
      ledStrip.show();
    } 
    else {
      // ВСЕ КОРРЕКТНО: ровный зеленый свет на передних и задних светодиодах
      for (int i = 0; i < LEDS_COUNT; i++) {
        ledStrip.setLedColorData(i, 0, 255, 0); // Зеленый цвет (R=0, G=255, B=0)
      }
      ledStrip.show();
    }
  }
  
  delay(400); // Замер и обновление светодиодов каждые 400 мс
}