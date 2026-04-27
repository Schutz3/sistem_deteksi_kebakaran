// ==============================================================================
// Tujuan       : Firmware ESP32 untuk 6 sensor gas MQ + kirim data via HTTP
//                Sensor: MQ135, MQ2, MQ3, MQ4, MQ5, MQ7
// Caller       : Hardware ESP32 (upload via Arduino IDE)
// Dependensi   : WiFi.h, HTTPClient.h (bawaan ESP32)
// Main Functions: setup(), loop(), readMQSensor(), sendDataToServer()
// Side Effects : HTTP POST ke backend setiap 2 detik
// ==============================================================================
// PIN ASSIGNMENT (ADC1 - ESP32):
//   MQ135 → GPIO 36 (VP)
//   MQ2   → GPIO 39 (VN)
//   MQ3   → GPIO 34
//   MQ4   → GPIO 35
//   MQ5   → GPIO 32
//   MQ7   → GPIO 33
// ==============================================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===========================
// KONFIGURASI - UBAH SESUAI KEBUTUHAN
// ===========================

// WiFi
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD  = "YOUR_WIFI_PASSWORD";

// Server Backend (IP komputer yang menjalankan FastAPI)
const char* SERVER_URL = "http://192.168.1.100:8000/api/sensor";

// ID Kamera yang terhubung ke ESP32 ini
const char* CAMERA_ID = "cam_01";

// Interval pengiriman data (ms)
const unsigned long SEND_INTERVAL = 2000;

// ===========================
// PIN DEFINISI (ADC1)
// ===========================
#define PIN_MQ135  36  // GPIO36 = VP
#define PIN_MQ2    39  // GPIO39 = VN
#define PIN_MQ3    34
#define PIN_MQ4    35
#define PIN_MQ5    32
#define PIN_MQ7    33

// ===========================
// KALIBRASI SENSOR
// ===========================
// Resistansi load (kOhm) - sesuaikan dengan rangkaian hardware
const float RL_VALUE = 10.0;

// Ro (resistansi sensor di udara bersih) - dikalibrasi di udara bersih
// Nilai default, harus dikalibrasi ulang untuk akurasi!
float Ro_MQ135 = 76.63;
float Ro_MQ2   = 9.83;
float Ro_MQ3   = 60.0;
float Ro_MQ4   = 4.4;
float Ro_MQ5   = 6.5;
float Ro_MQ7   = 27.0;

// Rasio Rs/Ro di udara bersih untuk setiap sensor (dari datasheet)
const float CLEAN_AIR_MQ135 = 3.6;
const float CLEAN_AIR_MQ2   = 9.8;
const float CLEAN_AIR_MQ3   = 60.0;
const float CLEAN_AIR_MQ4   = 4.4;
const float CLEAN_AIR_MQ5   = 6.5;
const float CLEAN_AIR_MQ7   = 27.0;

// ===========================
// VARIABEL GLOBAL
// ===========================
unsigned long lastSendTime = 0;
bool wifiConnected = false;

// LED indikator (built-in)
#define LED_PIN 2

// ===========================
// SETUP
// ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("========================================");
  Serial.println("ESP32 Fire Detection Sensor Module");
  Serial.println("========================================");

  // LED indikator
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Koneksi WiFi
  connectWiFi();

  // Set resolusi ADC ke 12-bit (0-4095)
  analogReadResolution(12);

  // Pemanasan sensor (MQ butuh ~20 detik warm-up minimum)
  Serial.println("[Sensor] Warming up (20 detik)...");
  for (int i = 20; i > 0; i--) {
    Serial.printf("  %d detik tersisa...\n", i);
    digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // Blink
    delay(1000);
  }
  digitalWrite(LED_PIN, HIGH);
  Serial.println("[Sensor] Sensor siap!");

  // Kalibrasi otomatis di udara bersih (opsional, uncomment jika diperlukan)
  // calibrateSensors();
}

// ===========================
// LOOP UTAMA
// ===========================
void loop() {
  // Cek koneksi WiFi
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    connectWiFi();
  }

  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;

    // Baca semua sensor
    float mq135 = readMQSensor(PIN_MQ135, Ro_MQ135);
    float mq2   = readMQSensor(PIN_MQ2,   Ro_MQ2);
    float mq3   = readMQSensor(PIN_MQ3,   Ro_MQ3);
    float mq4   = readMQSensor(PIN_MQ4,   Ro_MQ4);
    float mq5   = readMQSensor(PIN_MQ5,   Ro_MQ5);
    float mq7   = readMQSensor(PIN_MQ7,   Ro_MQ7);

    // Print ke Serial Monitor
    Serial.println("--- Sensor Reading ---");
    Serial.printf("MQ135(AirQ): %.2f | MQ2(Smoke): %.2f | MQ3(Alc): %.2f\n", mq135, mq2, mq3);
    Serial.printf("MQ4(CH4):    %.2f | MQ5(LPG):   %.2f | MQ7(CO):  %.2f\n", mq4, mq5, mq7);

    // Kirim ke server
    if (wifiConnected) {
      sendDataToServer(mq135, mq2, mq3, mq4, mq5, mq7);
    }

    // Blink LED saat kirim data
    digitalWrite(LED_PIN, LOW);
    delay(50);
    digitalWrite(LED_PIN, HIGH);
  }
}

// ===========================
// FUNGSI: Baca Sensor MQ
// ===========================
float readMQSensor(int pin, float Ro) {
  // Baca nilai ADC (rata-rata 10 sampel untuk stabilitas)
  long total = 0;
  for (int i = 0; i < 10; i++) {
    total += analogRead(pin);
    delay(2);
  }
  float adcValue = (float)total / 10.0;

  // Hindari division by zero
  if (adcValue < 1) adcValue = 1;

  // Hitung tegangan sensor
  float voltage = adcValue * (3.3 / 4095.0);

  // Hitung Rs (resistansi sensor)
  float Rs = ((3.3 * RL_VALUE) / voltage) - RL_VALUE;
  if (Rs < 0) Rs = 0;

  // Hitung rasio Rs/Ro
  float ratio = Rs / Ro;

  // Return ratio (semakin tinggi = semakin banyak gas terdeteksi)
  // Untuk konversi ke PPM, diperlukan kurva karakteristik per sensor
  return ratio;
}

// ===========================
// FUNGSI: Kirim Data ke Server
// ===========================
void sendDataToServer(float mq135, float mq2, float mq3, float mq4, float mq5, float mq7) {
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Buat JSON payload
  StaticJsonDocument<256> doc;
  doc["camera_id"] = CAMERA_ID;
  doc["mq135"] = round(mq135 * 100) / 100.0;
  doc["mq2"]   = round(mq2 * 100)   / 100.0;
  doc["mq3"]   = round(mq3 * 100)   / 100.0;
  doc["mq4"]   = round(mq4 * 100)   / 100.0;
  doc["mq5"]   = round(mq5 * 100)   / 100.0;
  doc["mq7"]   = round(mq7 * 100)   / 100.0;

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  // Kirim HTTP POST
  int httpCode = http.POST(jsonPayload);

  if (httpCode > 0) {
    Serial.printf("[HTTP] POST response: %d\n", httpCode);
    if (httpCode == 200) {
      String response = http.getString();
      Serial.printf("[HTTP] Server: %s\n", response.c_str());
    }
  } else {
    Serial.printf("[HTTP] POST gagal: %s\n", http.errorToString(httpCode).c_str());
  }

  http.end();
}

// ===========================
// FUNGSI: Koneksi WiFi
// ===========================
void connectWiFi() {
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    wifiConnected = true;
    Serial.println();
    Serial.printf("[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    wifiConnected = false;
    Serial.println();
    Serial.println("[WiFi] Connection failed! Retrying in 5s...");
    delay(5000);
  }
}

// ===========================
// FUNGSI: Kalibrasi Sensor (Opsional)
// ===========================
void calibrateSensors() {
  Serial.println("[Calibration] Memulai kalibrasi di udara bersih...");
  Serial.println("[Calibration] Pastikan sensor dalam udara bersih!");

  // Kalibrasi MQ135
  float rs_mq135 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ135);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq135 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ135 = (rs_mq135 / 50.0) / CLEAN_AIR_MQ135;
  Serial.printf("  Ro_MQ135 = %.2f\n", Ro_MQ135);

  // Kalibrasi MQ2
  float rs_mq2 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ2);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq2 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ2 = (rs_mq2 / 50.0) / CLEAN_AIR_MQ2;
  Serial.printf("  Ro_MQ2 = %.2f\n", Ro_MQ2);

  // Kalibrasi MQ3
  float rs_mq3 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ3);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq3 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ3 = (rs_mq3 / 50.0) / CLEAN_AIR_MQ3;
  Serial.printf("  Ro_MQ3 = %.2f\n", Ro_MQ3);

  // Kalibrasi MQ4
  float rs_mq4 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ4);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq4 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ4 = (rs_mq4 / 50.0) / CLEAN_AIR_MQ4;
  Serial.printf("  Ro_MQ4 = %.2f\n", Ro_MQ4);

  // Kalibrasi MQ5
  float rs_mq5 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ5);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq5 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ5 = (rs_mq5 / 50.0) / CLEAN_AIR_MQ5;
  Serial.printf("  Ro_MQ5 = %.2f\n", Ro_MQ5);

  // Kalibrasi MQ7
  float rs_mq7 = 0;
  for (int i = 0; i < 50; i++) {
    float adc = (float)analogRead(PIN_MQ7);
    if (adc < 1) adc = 1;
    float v = adc * (3.3 / 4095.0);
    rs_mq7 += ((3.3 * RL_VALUE) / v) - RL_VALUE;
    delay(100);
  }
  Ro_MQ7 = (rs_mq7 / 50.0) / CLEAN_AIR_MQ7;
  Serial.printf("  Ro_MQ7 = %.2f\n", Ro_MQ7);

  Serial.println("[Calibration] Kalibrasi selesai!");
}
