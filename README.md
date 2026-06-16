# VisionLink Smart Class Engine 🚀

An AI-powered Smart Class System combining Zero-Latency Face Attendance and Automated Energy Control. Built for modern classrooms to save energy and automate student tracking.

## ✨ Key Features
* **Zero-Latency Live Attendance:** Hybrid tracking engine for flawless face recognition.
* **Smart Energy Control:** Auto light/fan control using human presence detection.
* **Plug & Play Hardware:** ESP32 with WiFiManager & mDNS (No hardcoded IP needed).

## 🛠️ Hardware Setup Guide (ESP32)
1. Open the `ESP32_Hardware_Code` folder and upload the `.ino` file to your ESP32 board.
2. Connect your Relay module to **Pin 26 (Light)** and **Pin 27 (Fan)**.
3. Power up the ESP32. It will automatically broadcast a WiFi hotspot named `VisionLink_Setup`.
4. Connect to this hotspot from your phone. A portal will open.
5. Select your local WiFi or Mobile Hotspot, enter the password, and click **Save**.
6. The ESP32 is now connected! You never have to touch the hardware code again.

## 💻 How to Run the Software
1. Install requirements: `pip install -r requirements.txt`
2. Run the engine: `python main.py`
3. Connect your laptop to the same WiFi as the ESP32.
4. Open the Dashboard and enjoy the magic!