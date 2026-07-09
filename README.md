# VisionLink Smart Class Engine 🚀

An AI-powered Smart Class System combining Zero-Latency Face Attendance and Automated Energy Control. Built for modern classrooms to save energy and automate student tracking.

## ✨ Key Features
* **Zero-Latency Live Attendance:** Hybrid tracking engine for flawless face recognition.
* **Smart Energy Control:** Auto light/fan control using human presence detection.
* **Plug & Play Hardware:** ESP32 with WiFiManager & mDNS (No hardcoded IP needed).

## 🏗️ System Architecture

The system operates across three main layers: The Software Layer (AI & UI), The Network Layer, and The Hardware Layer (IoT).

```mermaid
graph TD
    subgraph "Software Layer (Laptop / PC - Python)"
        UI[🖥️ CustomTkinter UI Dashboard]
        AI[🧠 Vision Engine Core <br>OpenCV & Face Recognition]
        DB[(📁 Local Database <br>CSV & Known Faces)]
        WQ[⚙️ Background Workers <br>HTTP Queue & Threading]
        VQ[🔊 Voice Engine <br>pyttsx3 Audio Queue]
        
        UI <-->|Live Video & Status| AI
        AI -->|Identify Faces| DB
        UI <-->|Save/Fetch Records| DB
        UI -->|Send HTTP Commands| WQ
        UI -->|Trigger Speech| VQ
    end

    subgraph "Network Layer (Zero-Latency Local Bridge)"
        WIFI((📶 Local Wi-Fi / Hotspot))
        WQ -- "Session Pooled HTTP GET <br> (visionlink.local)" --> WIFI
    end

    subgraph "Hardware Layer (ESP32 / Arduino)"
        ESP[⚙️ ESP32 Web Server <br> Port 80 & mDNS]
        WM[🌐 WiFiManager <br> VisionLink_Setup Portal]
        R1[💡 Relay 1: Smart Lights]
        R2[❄️ Relay 2: Smart Fans]
        
        WIFI --> ESP
        ESP <-->|Auto Recovery| WM
        ESP -->|Digital LOW/HIGH| R1
        ESP -->|Digital LOW/HIGH| R2
    end