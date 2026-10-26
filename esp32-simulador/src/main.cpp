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
#ifndef FAN_DEVICE_ID
#define FAN_DEVICE_ID "esp32_fan_01"
#endif
const char* device_id = FAN_DEVICE_ID;

// Tópicos MQTT
const char* topic_telemetry = "devices/" FAN_DEVICE_ID "/telemetry";
const char* topic_command = "devices/" FAN_DEVICE_ID "/command";
const char* topic_config_command = "devices/" FAN_DEVICE_ID "/config/set";
const char* topic_state = "devices/" FAN_DEVICE_ID "/state";
const char* topic_config_state = "devices/" FAN_DEVICE_ID "/config";

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
unsigned long last_energy_time = 0;
unsigned long last_wifi_attempt = 0;
unsigned long last_mqtt_attempt = 0;
const unsigned long WIFI_RETRY_MS = 10000;
const unsigned long MQTT_RETRY_MS = 3000;
const float VOLTAGE_RMS = 127.0f;
const float CURRENT_SCALE_A = 0.8f;
const float POWER_FACTOR = 0.90f;
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
  if (value.length() != 5 || value.indexOf(':') != 2 ||
      !isDigit(value[0]) || !isDigit(value[1]) ||
      !isDigit(value[3]) || !isDigit(value[4])) {
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

  // NTP synchronization continues asynchronously; never hold the control loop.
  clock_ready = false;
}

void integrateLocalEnergy() {
  const unsigned long now = millis();
  const unsigned long elapsed = now - last_energy_time;
  total_energy_wh += last_power_w * elapsed / 3600000.0f;
  last_energy_time = now;
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

  integrateLocalEnergy();
  if (!next_state) last_power_w = 0.0f;
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
  if (!client.publish(topic_state, buffer, true)) Serial.println("State publish failed");
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
  if (!client.publish(topic_config_state, buffer, true)) Serial.println("Config publish failed");
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

  if ((doc.containsKey("is_on") && !doc["is_on"].is<bool>()) ||
      (doc.containsKey("auto_mode") && !doc["auto_mode"].is<bool>())) {
    Serial.println("Invalid boolean command field");
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
    } else {
      Serial.println("Unknown action");
      return;
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

void maintainConnectivity() {
  const unsigned long now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (now - last_wifi_attempt >= WIFI_RETRY_MS) {
      last_wifi_attempt = now;
      WiFi.reconnect();
    }
    return;
  }
  if (!client.connected() && now - last_mqtt_attempt >= MQTT_RETRY_MS) {
    last_mqtt_attempt = now;
    if (client.connect(device_id)) {
      client.subscribe(topic_command, 1);
      client.subscribe(topic_config_command, 1);
      publishState();
      publishConfigState();
    } else {
      Serial.printf("MQTT unavailable, rc=%d; local protection stays active\n", client.state());
    }
  }
  if (client.connected()) client.loop();
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_SENSOR, INPUT);
  digitalWrite(PIN_RELAY, LOW);

  loadSettings();

  WiFi.setAutoReconnect(true);
  WiFi.begin(ssid, password);
  last_energy_time = millis();
  initClock();
  client.setBufferSize(768);
  client.setSocketTimeout(1);
  client.setKeepAlive(30);
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
  const float voltage_rms = VOLTAGE_RMS;

  if (is_fan_on) {
    int raw_analog = analogRead(PIN_SENSOR);
    if (raw_analog < 0 || raw_analog > 4095) {
      Serial.println("Invalid ADC reading; skipping telemetry");
      last_telemetry_time = millis();
      return;
    }
    current_a = (raw_analog / 4095.0f) * CURRENT_SCALE_A;
    power_w = current_a * voltage_rms * POWER_FACTOR;
  }

  unsigned long now = millis();
  integrateLocalEnergy();
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
  if (client.connected() && !client.publish(topic_telemetry, buffer)) {
    Serial.println("Telemetry publish failed");
  }

  Serial.print("Telemetria enviada: ");
  Serial.println(buffer);
  last_telemetry_time = now;
}

void loop() {
  clock_ready = time(nullptr) > 1700000000;

  if (is_fan_on && shouldAutoShutdown()) {
    Serial.println("Horário de desligamento atingido. Desligando ventilador.");
    setFanState(false);
    publishState();
  }

  maintainConnectivity();
  unsigned long now = millis();
  if (now - last_telemetry_time > telemetry_interval) {
    sendTelemetry();
  }
}