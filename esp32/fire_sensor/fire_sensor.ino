// ==============================================================================
// Tujuan       : Firmware ESP32 untuk 6 sensor gas MQ + kirim data via HTTP
//                Sensor: MQ135, MQ2, MQ3, MQ4, MQ5, MQ7
// Caller       : Hardware ESP32 (upload via Arduino IDE)
// Dependensi   : WiFi.h, HTTPClient.h (bawaan ESP32)
// Main Functions: setup(), loop(), readMQSensor(), sendDataToServer()
// Side Effects : HTTP POST ke backend setiap 2 detik
// ==============================================================================

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ===========================
// KONFIGURASI - UBAH SESUAI KEBUTUHAN
// ===========================

// WiFi
const char* WIFI_SSID     = "AARCH";
const char* WIFI_PASSWORD  = "XnbadFXM";

// Server Backend (IP komputer yang menjalankan FastAPI)
const char* SERVER_URL = "https://pbl.scz.my.id/api/sensor";

// ID Kamera yang terhubung ke ESP32 ini
const char* CAMERA_ID = "cam_01";

// Interval pengiriman data (ms)
const unsigned long SEND_INTERVAL = 2000;

// ===========================
// PIN DEFINISI (ADC1) & ARRAY
// ===========================
const int mqPins[] = {32, 33, 34, 35, 36, 39}; 
const int jumlahSensor = 6;

// Label masing-masing sensor (sesuaikan urutan pin)
String namaSensor[] = {"MQ-4 (CH4)", "MQ-5 (GAS)", "MQ-135 (Air)", "MQ-2 (SMOKE)", "MQ-7 (CO)", "MQ-3 (Metana)"};

// Array penampung data runtime sensor (RAW ADC)
int sensorValues[6] = {0, 0, 0, 0, 0, 0};

// ===========================
// VARIABEL GLOBAL
// ===========================
unsigned long lastSendTime = 0;
bool wifiConnected = false;

// LED indikator (built-in)
#define LED_PIN 2

// Fungsi Prototipe
void connectWiFi();
int readMQSensor(int pin);
void sendDataToServer();

// ===========================
// SETUP
// ===========================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("========================================");
  Serial.println("ESP32 Fire Detection Sensor Module");
  Serial.println("========================================");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  connectWiFi();
  analogReadResolution(12);

  // Pemanasan sensor
  Serial.println("[Sensor] Warming up (20 detik)...");
  for (int i = 20; i > 0; i--) {
    Serial.printf("  %d detik tersisa...\n", i);
    digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // Blink
    delay(1000);
  }
  digitalWrite(LED_PIN, HIGH);
  Serial.println("[Sensor] Sensor siap!");

}

// ===========================
// LOOP UTAMA
// ===========================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    wifiConnected = false;
    connectWiFi();
  }

  unsigned long now = millis();
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;

    Serial.println("--- Sensor Reading ---");
    // Baca seluruh pin dengan array constraint
    for (int i = 0; i < jumlahSensor; i++) {
        sensorValues[i] = readMQSensor(mqPins[i]);
        Serial.printf("%s: %d | ", namaSensor[i].c_str(), sensorValues[i]);
    }
    Serial.println();

    if (wifiConnected) {
      sendDataToServer();
    }

    digitalWrite(LED_PIN, LOW);
    delay(50);
    digitalWrite(LED_PIN, HIGH);
  }
}

// ===========================
// FUNGSI: Baca Sensor MQ
// ===========================
int readMQSensor(int pin) {
  // Rata-ratakan 10 sampel untuk mengurangi noise RAW ADC
  long total = 0;
  for (int i = 0; i < 10; i++) {
    total += analogRead(pin);
    delay(2);
  }
  return total / 10; // Mengirimkan nilai mentah 0-4095 (12-bit)
}

// ===========================
// FUNGSI: Kirim Data ke Server
// ===========================
void sendDataToServer() {
  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");

  // Map Array ke JSON API Format (sesuai spesifikasi sistem)
  // idx 0 -> mq4 | idx 1 -> mq5 | idx 2 -> mq135 | idx 3 -> mq2 | idx 4 -> mq7 | idx 5 -> mq3
  StaticJsonDocument<256> doc;
  doc["camera_id"] = CAMERA_ID;
  doc["mq4"]   = sensorValues[0];
  doc["mq5"]   = sensorValues[1];
  doc["mq135"] = sensorValues[2];
  doc["mq2"]   = sensorValues[3];
  doc["mq7"]   = sensorValues[4];
  doc["mq3"]   = sensorValues[5];

  String jsonPayload;
  serializeJson(doc, jsonPayload);

  int httpCode = http.POST(jsonPayload);

  if (httpCode > 0) {
    if (httpCode == 200) {
      String response = http.getString();
      Serial.printf("[HTTP] Server: %s\n", response.c_str());
    } else {
      Serial.printf("[HTTP] POST failed (res code): %d\n", httpCode);
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
