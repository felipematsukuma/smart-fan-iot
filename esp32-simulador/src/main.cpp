#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <time.h>

// Configurações de Wi-Fi do Wokwi
const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Configurações MQTT
// O gateway privado do Wokwi resolve este hostname para o computador atual,
// independentemente do endereço IP atribuído pelo DHCP.
const char* mqtt_server = "host.wokwi.internal";
const int mqtt_port = 1883;
const char* device_id = "esp32_fan_01";

// Tópicos MQTT
const char* topic_telemetry = "devices/esp32_fan_01/telemetry";
const char* topic_command = "devices/esp32_fan_01/command";
const char* topic_config_command = "devices/esp32_fan_01/config/set";
const char* topic_state = "devices/esp32_fan_01/state";
const char* topic_config_state = "devices/esp32_fan_01/config";

// Pinos
const int PIN_RELAY = 23;
const int PIN_SENSOR = 34;

// Variáveis de Estado
bool is_fan_on = false;
bool clock_ready = false;
unsigned long last_telemetry_time = 0;
unsigned long fan_on_start_millis = 0;
unsigned long total_fan_on_millis = 0;
float total_energy_wh = 0.0f;
float last_power_w = 0.0f;
const long telemetry_interval = 2000;
const int AUTO_SHUTDOWN_TOLERANCE_MINUTES = 2;
const int MINUTES_PER_DAY = 24 * 60;
const int MAX_PAYLOAD_SIZE = 512;

struct FanSettings {
  bool auto_mode = true;
  int shutdown_hour = 3;
  int shutdown_minute = 0;
};

FanSettings settings;
Preferences prefs;
WiFiClient espClient;
PubSubClient client(espClient);

String formatShutdownTime() {
  char buffer[6];
  snprintf(buffer, sizeof(buffer), "%02d:%02d", settings.shutdown_hour, settings.shutdown_minute);
  return String(buffer);
}

bool parseShutdownTime(const String& value, int& hour, int& minute) {
  if (value.length() != 5 || value.indexOf(':') != 2) {
    return false;
  }

  hour = value.substring(0, 2).toInt();
  minute = value.substring(3, 5).toInt();

  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return false;
  }

  return true;
}

void saveSettings() {
  prefs.begin("fan_cfg", false);
  prefs.putBool("auto_mode", settings.auto_mode);
  prefs.putInt("shutdown_hour", settings.shutdown_hour);
  prefs.putInt("shutdown_minute", settings.shutdown_minute);
  prefs.end();
}

void loadSettings() {
  prefs.begin("fan_cfg", false);
  settings.auto_mode = prefs.getBool("auto_mode", true);
  settings.shutdown_hour = prefs.getInt("shutdown_hour", 3);
  settings.shutdown_minute = prefs.getInt("shutdown_minute", 0);
  prefs.end();
}

void initClock() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  // Horário de Brasília (UTC-3). O backend também deve usar APP_TIMEZONE.
  setenv("TZ", "BRT3", 1);
  tzset();

  Serial.println("Sincronizando relógio local...");
  struct tm timeinfo;
  for (int i = 0; i < 30; i++) {
    if (getLocalTime(&timeinfo)) {
      clock_ready = true;
      Serial.println("Relógio sincronizado.");
      return;
    }
    delay(1000);
    Serial.print(".");
  }

  Serial.println("\nFalha ao sincronizar o relógio NTP.");
  clock_ready = false;
}

unsigned long getCurrentFanOnTimeMs() {
  unsigned long elapsed = 0;
  if (is_fan_on) {
    elapsed = millis() - fan_on_start_millis;
  }
  return total_fan_on_millis + elapsed;
}

void setFanState(bool next_state) {
  if (is_fan_on == next_state) {
    return;
  }

  if (next_state) {
    fan_on_start_millis = millis();
  } else {
    if (fan_on_start_millis > 0) {
      total_fan_on_millis += millis() - fan_on_start_millis;
      fan_on_start_millis = 0;
    }
  }

  is_fan_on = next_state;
  digitalWrite(PIN_RELAY, is_fan_on ? HIGH : LOW);
}

void publishState() {
  StaticJsonDocument<MAX_PAYLOAD_SIZE> doc;
  doc["device_id"] = device_id;
  doc["is_on"] = is_fan_on;
  doc["auto_mode"] = settings.auto_mode;
  doc["shutdown_time"] = formatShutdownTime();
  doc["fan_on_time_ms"] = getCurrentFanOnTimeMs();
  doc["total_energy_wh"] = round(total_energy_wh * 1000.0f) / 1000.0f;

  char buffer[MAX_PAYLOAD_SIZE];
  serializeJson(doc, buffer);
  client.publish(topic_state, buffer, true);
  Serial.print("Estado publicado: ");
  Serial.println(buffer);
}

void publishConfigState() {
  StaticJsonDocument<MAX_PAYLOAD_SIZE> doc;
  doc["device_id"] = device_id;
  doc["auto_mode"] = settings.auto_mode;
  doc["shutdown_time"] = formatShutdownTime();

  char buffer[MAX_PAYLOAD_SIZE];
  serializeJson(doc, buffer);
  client.publish(topic_config_state, buffer, true);
  Serial.print("Configuração publicada: ");
  Serial.println(buffer);
}

void handleIncomingCommand(const String& message) {
  StaticJsonDocument<MAX_PAYLOAD_SIZE> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error) {
    Serial.print("JSON inválido recebido: ");
    Serial.println(message);
    return;
  }

  if (doc.containsKey("action")) {
    const String action = doc["action"].as<String>();
    if (action == "ON") {
      setFanState(true);
    } else if (action == "OFF") {
      setFanState(false);
    } else if (action == "AUTO") {
      settings.auto_mode = true;
      saveSettings();
    } else if (action == "MANUAL") {
      settings.auto_mode = false;
      saveSettings();
    }
  }

  if (doc.containsKey("is_on")) {
    setFanState(doc["is_on"].as<bool>());
  }

  if (doc.containsKey("shutdown_time")) {
    const String shutdown_time = doc["shutdown_time"].as<String>();
    int hour = 0;
    int minute = 0;
    if (parseShutdownTime(shutdown_time, hour, minute)) {
      settings.shutdown_hour = hour;
      settings.shutdown_minute = minute;
      saveSettings();
    } else {
      Serial.println("Valor de shutdown_time inválido. Use HH:MM");
    }
  }

  if (doc.containsKey("auto_mode")) {
    settings.auto_mode = doc["auto_mode"].as<bool>();
    saveSettings();
  }

  publishState();
  publishConfigState();
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message = "";
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  Serial.print("Mensagem recebida [");
  Serial.print(topic);
  Serial.print("]:");
  Serial.println(message);

  if (strcmp(topic, topic_command) == 0 || strcmp(topic, topic_config_command) == 0) {
    handleIncomingCommand(message);
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando ao Broker MQTT...");
    if (client.connect(device_id)) {
      Serial.println(" Conectado!");
      client.subscribe(topic_command);
      client.subscribe(topic_config_command);
      publishState();
      publishConfigState();
    } else {
      Serial.print("Falhou, rc=");
      Serial.print(client.state());
      Serial.println(" Tentando novamente em 3 segundos...");
      delay(3000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_SENSOR, INPUT);
  digitalWrite(PIN_RELAY, LOW);

  loadSettings();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Conectado!");

  initClock();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

bool shouldAutoShutdown() {
  if (!settings.auto_mode || !clock_ready) {
    return false;
  }

  time_t now_epoch = time(nullptr);
  struct tm timeinfo;
  localtime_r(&now_epoch, &timeinfo);

  int current_minutes = (timeinfo.tm_hour * 60) + timeinfo.tm_min;
  int shutdown_minutes = (settings.shutdown_hour * 60) + settings.shutdown_minute;
  int minutes_since_scheduled_time = (
    (current_minutes - shutdown_minutes) + MINUTES_PER_DAY
  ) % MINUTES_PER_DAY;

  return minutes_since_scheduled_time <= AUTO_SHUTDOWN_TOLERANCE_MINUTES;
}

void sendTelemetry() {
  float current_a = 0.0f;
  float power_w = 0.0f;
  const float voltage_rms = 127.0f;

  if (is_fan_on) {
    int raw_analog = analogRead(PIN_SENSOR);
    current_a = (raw_analog / 4095.0f) * 0.8f;
    if (current_a < 0.05f) {
      current_a = 0.28f;
    }
    power_w = current_a * voltage_rms * 0.90f;
  }

  unsigned long now = millis();
  if (is_fan_on && now > last_telemetry_time) {
    total_energy_wh += (power_w * (now - last_telemetry_time)) / 3600000.0f;
  }

  last_power_w = power_w;

  StaticJsonDocument<MAX_PAYLOAD_SIZE> doc;
  doc["device_id"] = device_id;
  doc["is_on"] = is_fan_on;
  doc["auto_mode"] = settings.auto_mode;
  doc["shutdown_time"] = formatShutdownTime();
  doc["voltage_rms"] = voltage_rms;
  doc["current_a"] = round(current_a * 1000.0f) / 1000.0f;
  doc["power_w"] = round(power_w * 100.0f) / 100.0f;
  doc["total_energy_wh"] = round(total_energy_wh * 1000.0f) / 1000.0f;
  doc["fan_on_time_ms"] = getCurrentFanOnTimeMs();
  doc["timestamp"] = now;

  char buffer[MAX_PAYLOAD_SIZE];
  serializeJson(doc, buffer);
  client.publish(topic_telemetry, buffer);

  Serial.print("Telemetria enviada: ");
  Serial.println(buffer);
  last_telemetry_time = now;
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  if (is_fan_on && shouldAutoShutdown()) {
    Serial.println("Horário de desligamento atingido. Desligando ventilador.");
    setFanState(false);
    publishState();
  }

  unsigned long now = millis();
  if (now - last_telemetry_time > telemetry_interval) {
    sendTelemetry();
  }
}