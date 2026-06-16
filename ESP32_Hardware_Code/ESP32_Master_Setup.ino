#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>

WebServer server(80);

// ======================
// Pins
// ======================
const int STATUS_LED = 2;
const int LIGHT_PIN  = 26;
const int FAN_PIN    = 27;

bool wifiConnected = false;

// ======================
// Function Prototypes
// ======================
bool connectSavedWiFi(uint32_t timeoutMs);
bool startConfigPortal();
void startWebServer();

// ======================
// Setup
// ======================
void setup() {

  Serial.begin(115200);

  pinMode(STATUS_LED, OUTPUT);
  pinMode(LIGHT_PIN, OUTPUT);
  pinMode(FAN_PIN, OUTPUT);

  // Active LOW relays OFF
  digitalWrite(LIGHT_PIN, HIGH);
  digitalWrite(FAN_PIN, HIGH);

  digitalWrite(STATUS_LED, LOW);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  Serial.println();
  Serial.println("=================================");
  Serial.println("VisionLink Booting...");
  Serial.println("=================================");

  if (connectSavedWiFi(30000)) {

    wifiConnected = true;

    digitalWrite(STATUS_LED, HIGH);

    Serial.println("WiFi Connected");
    Serial.print("IP: ");
    Serial.println(WiFi.localIP());

  } else {

    wifiConnected = false;

    if (startConfigPortal()) {

      wifiConnected = true;

      digitalWrite(STATUS_LED, HIGH);

      Serial.println("WiFi Configured");
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());

    } else {

      Serial.println("Portal Failed");
      ESP.restart();
    }
  }

  // mDNS
  if (MDNS.begin("visionlink")) {

    Serial.println("mDNS Started");
    Serial.println("http://visionlink.local");

  } else {

    Serial.println("mDNS Failed");
  }

  startWebServer();
}

// ======================
// Loop
// ======================
void loop() {

  server.handleClient();

  // WiFi Lost
  if (wifiConnected && WiFi.status() != WL_CONNECTED) {

    wifiConnected = false;

    Serial.println();
    Serial.println("=================================");
    Serial.println("WiFi Lost");
    Serial.println("Trying Reconnect...");
    Serial.println("=================================");

    if (connectSavedWiFi(30000)) {

      wifiConnected = true;

      digitalWrite(STATUS_LED, HIGH);

      Serial.println("WiFi Reconnected");
      Serial.print("IP: ");
      Serial.println(WiFi.localIP());

    } else {

      Serial.println("Reconnect Failed");
      Serial.println("Starting Config Portal");

      if (startConfigPortal()) {

        wifiConnected = true;

        digitalWrite(STATUS_LED, HIGH);

        Serial.println("WiFi Configured");
        Serial.print("IP: ");
        Serial.println(WiFi.localIP());

      } else {

        ESP.restart();
      }
    }
  }

  delay(10);
}

// ======================
// Connect Saved WiFi
// ======================
bool connectSavedWiFi(uint32_t timeoutMs) {

  Serial.println("Searching Saved WiFi...");

  // DO NOT erase saved credentials
  WiFi.disconnect(false, false);
  delay(500);

  WiFi.mode(WIFI_STA);
  delay(500);

  WiFi.begin();

  uint32_t startTime = millis();

  bool ledState = false;
  uint32_t lastBlink = 0;

  while (WiFi.status() != WL_CONNECTED &&
         millis() - startTime < timeoutMs) {

    if (millis() - lastBlink >= 2000) {

      ledState = !ledState;
      digitalWrite(STATUS_LED, ledState);

      Serial.print(".");

      lastBlink = millis();
    }

    delay(50);
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {

    digitalWrite(STATUS_LED, HIGH);

    return true;
  }

  digitalWrite(STATUS_LED, LOW);

  return false;
}

// ======================
// Config Portal
// ======================
bool startConfigPortal() {

  digitalWrite(STATUS_LED, LOW);

  Serial.println();
  Serial.println("=================================");
  Serial.println("Starting Config Portal");
  Serial.println("SSID: VisionLink_Setup");
  Serial.println("=================================");

  WiFiManager wm;

  wm.setConfigPortalTimeout(0);

  return wm.startConfigPortal("VisionLink_Setup");
}

// ======================
// Web Server
// ======================
void startWebServer() {

  server.on("/", []() {
    server.send(200, "text/plain", "VisionLink ESP32 Running");
  });

  server.on("/light_on", []() {
    digitalWrite(LIGHT_PIN, LOW);
    server.send(200, "text/plain", "Light ON");
  });

  server.on("/light_off", []() {
    digitalWrite(LIGHT_PIN, HIGH);
    server.send(200, "text/plain", "Light OFF");
  });

  server.on("/fan_on", []() {
    digitalWrite(FAN_PIN, LOW);
    server.send(200, "text/plain", "Fan ON");
  });

  server.on("/fan_off", []() {
    digitalWrite(FAN_PIN, HIGH);
    server.send(200, "text/plain", "Fan OFF");
  });

  server.begin();

  Serial.println("Web Server Started");
}