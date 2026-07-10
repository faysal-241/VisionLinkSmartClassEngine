import customtkinter as ctk
from datetime import datetime, timedelta
from PIL import Image
import pyttsx3
import threading
import queue
import time
import os
import sys
import csv
import socket
import requests # [NEW]: Ultra-fast HTTP requests
from vision_engine import VisionEngine
from attendance_manager import AttendanceSessionManager

voice_queue = queue.Queue()
hardware_queue = queue.Queue()
# [NEW]: Thread-safe lock for shared camera frame data
frame_lock = threading.Lock()
# [NEW]: Callback queue for hardware status notifications to UI
hw_status_queue = queue.Queue()

def voice_worker():
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    while True:
        text = voice_queue.get()
        if text is None:
            break
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
        voice_queue.task_done()

# [IMPROVED]: Hardware worker with mDNS caching and status feedback
def hardware_worker():
    session = requests.Session()
    ESP32_HOST = "visionlink.local"
    cached_ip = None

    def resolve_host():
        nonlocal cached_ip
        try:
            cached_ip = socket.gethostbyname(ESP32_HOST)
            return cached_ip
        except Exception:
            cached_ip = None
            return None

    while True:
        endpoint = hardware_queue.get()
        if endpoint is None:
            break
        try:
            host = cached_ip or resolve_host()
            if host is None:
                hw_status_queue.put(("error", f"ESP32 not found on network"))
                hardware_queue.task_done()
                continue
            
            url = f"http://{host}/{endpoint}"
            session.get(url, timeout=1.0)
            action = endpoint.replace("_", " ").title()
            hw_status_queue.put(("success", f"{action} — Signal sent"))
            print(f"[HARDWARE] Signal sent instantly: {endpoint}")
        except Exception as e:
            cached_ip = None  # Reset cache on error to re-resolve next time
            hw_status_queue.put(("error", f"ESP32 unreachable — Check WiFi"))
            print(f"[HARDWARE ERROR] Failed to reach ESP32: {e}")
        hardware_queue.task_done()

threading.Thread(target=voice_worker, daemon=True).start()
threading.Thread(target=hardware_worker, daemon=True).start()

def speak_text(text):
    voice_queue.put(text)

class VisionLinkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VisionLink Smart Class Engine")
        self.geometry("1300x800")
        self.minsize(1100, 700)
        ctk.set_appearance_mode("Dark")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.BG_MAIN = "#090D16"         # Dark Slate Black
        self.BG_SIDEBAR = "#111625"      # Dark Navy Slate
        self.BG_CARD = "#171D2F"         # Clean Navy Card
        self.ACCENT_CYAN = "#3B82F6"     # Premium Cobalt Blue
        self.NEON_GREEN = "#10B981"      # Emerald Green
        self.ALERT_RED = "#EF4444"       # Coral Red
        self.WARNING_ORANGE = "#F59E0B"  # Amber Orange
        self.TEXT_WHITE = "#F3F4F6"      # Soft Off-white
        self.TEXT_MUTED = "#9CA3AF"      # Slate Gray
        self.BORDER_MUTED = "#222A3F"    # Dark Border
        self.BTN_HOVER_BG = "#222C47"    # Button hover
        self.ACTIVE_TAB_BG = "#1E253A"   # Active tab highlight

        self.configure(fg_color=self.BG_MAIN)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.last_voice_state = "STARTUP"
        self.current_tab = "dashboard"
        self._img_cache = {}  # [NEW]: CTkImage cache for performance
        self._toast_widgets = []  # [NEW]: Active toast notifications

        self.sidebar_frame = ctk.CTkFrame(self, width=290, corner_radius=0, fg_color=self.BG_SIDEBAR, border_width=1, border_color=self.BORDER_MUTED)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # [NEW]: Vertical indicator bar next to active sidebar button
        self.sidebar_indicator = ctk.CTkFrame(self.sidebar_frame, width=4, fg_color=self.ACCENT_CYAN, corner_radius=2)

        self.logo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.logo_frame.grid(row=0, column=0, padx=25, pady=(40, 25), sticky="ew")

        self.logo_label = ctk.CTkLabel(self.logo_frame, text="VISIONLINK", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE)
        self.logo_label.pack(pady=(0, 2))
        self.logo_sub = ctk.CTkLabel(self.logo_frame, text="SMART CLASS ENGINE  v2.0", font=ctk.CTkFont(size=10, weight="bold"), text_color=self.ACCENT_CYAN)
        self.logo_sub.pack()

        separator = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color=self.BORDER_MUTED)
        separator.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 25))

        self.btn_dashboard = self.create_sidebar_btn("    🏠    Dashboard Home", 2, self.show_dashboard)
        self.btn_energy = self.create_sidebar_btn("    ⚡        Energy Control", 3, self.show_energy)
        self.btn_attendance = self.create_sidebar_btn("    📷    Live Attendance", 4, self.show_attendance)
        self.btn_records = self.create_sidebar_btn("    📋    Records History", 5, self.show_records)

        self.live_clock_label = ctk.CTkLabel(self.sidebar_frame, text="Loading Time...", font=ctk.CTkFont(size=13), text_color=self.TEXT_MUTED)
        self.live_clock_label.grid(row=7, column=0, pady=30, sticky="s")

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=40, pady=30)

        self.chart_day_labels = []
        self.chart_date_labels = []
        self.chart_bars = []  # [NEW]: Store chart bar references for live updates
        self.chart_val_labels = []  # [NEW]: Store chart value labels for live updates
        self.current_day_str = ""

        self.session_manager = AttendanceSessionManager()
        self.attendance_running = False

        self.frame_dashboard = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.setup_dashboard_frame()
        self.frame_energy = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.setup_energy_frame()
        self.frame_attendance = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.setup_attendance_frame()

        self.frame_records = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.setup_records_frame()  # [NEW]: Full records tab

        self.show_dashboard()
        self.update_live_system()
        self.update_attendance_timer_ui()
        self.poll_hardware_status()  # [NEW]: Poll for hardware toast notifications

        self.vision_engine = VisionEngine(camera_source=0)
        speak_text("Welcome to Vision Link Smart Class Engine.")

        # [IMPROVED]: Thread-safe shared frame data
        self.latest_pil_image = None
        self.latest_human_present = False
        self._frame_consumed = True  # [NEW]: Frame skip flag
        
        threading.Thread(target=self.camera_worker, daemon=True).start()

        self.start_camera_feed()

        # [NEW]: Update dashboard live data after engine loads
        self.after(500, self.update_dashboard_live_data)

        # [NEW]: Keyboard shortcuts
        self.bind("<F1>", lambda e: self.show_dashboard())
        self.bind("<F2>", lambda e: self.show_energy())
        self.bind("<F3>", lambda e: self.show_attendance())
        self.bind("<F4>", lambda e: self.show_records())
        self.bind("<space>", lambda e: self._handle_space_key())
        self.bind("<Escape>", lambda e: self._handle_escape_key())
        self.bind("<Control-s>", lambda e: self.save_live_session())

    def _handle_space_key(self):
        if self.current_tab == "attendance":
            if not self.attendance_running:
                self.start_live_session()
            else:
                self.toggle_pause_session()

    def _handle_escape_key(self):
        if self.current_tab == "attendance" and self.attendance_running:
            self.stop_live_session()

    def on_closing(self):
        print("[SYSTEM] Shutting down all engines and cameras...")
        if hasattr(self, 'vision_engine'):
            self.vision_engine.release_camera()
            # [IMPROVED]: Properly terminate AI subprocess
            if hasattr(self.vision_engine, 'ai_process') and self.vision_engine.ai_process.is_alive():
                self.vision_engine.ai_process.terminate()
                self.vision_engine.ai_process.join(timeout=2)
        # Signal workers to stop
        voice_queue.put(None)
        hardware_queue.put(None)
        self.destroy()
        os._exit(0)

    def camera_worker(self):
        was_hardware_on_worker = False
        print("[CAMERA WORKER] Thread started successfully.")
        while True:
            try:
                is_ai_active = self.ai_status_var.get()
                is_any_device_on = self.light_var.get() or self.fan_var.get()
                is_attendance_active = getattr(self, 'attendance_running', False)

                if is_any_device_on and not was_hardware_on_worker:
                    self.vision_engine.presence_timer = self.vision_engine.MAX_TIMER
                was_hardware_on_worker = is_any_device_on

                # [IMPROVED]: Skip frame processing if UI hasn't consumed the last one
                if not self._frame_consumed:
                    time.sleep(0.01)
                    continue

                active_tab = getattr(self, 'current_tab', 'attendance')

                if is_attendance_active and active_tab == "attendance":
                    if self.session_manager.is_paused:
                        pil_image, human_present = self.vision_engine.get_frame(ai_active=False, scan_mode="attendance")
                    else:
                        pil_image, human_present = self.vision_engine.get_frame(ai_active=True, scan_mode="attendance")
                    
                    with frame_lock:
                        self.latest_pil_image = pil_image
                        self.latest_human_present = human_present
                        self._frame_consumed = False
                else:
                    process_ai_now = is_ai_active and is_any_device_on
                    pil_image, human_present = self.vision_engine.get_frame(ai_active=process_ai_now, scan_mode="energy")
                    
                    with frame_lock:
                        self.latest_pil_image = pil_image
                        self.latest_human_present = human_present
                        self._frame_consumed = False

                time.sleep(0.01)
            except Exception as e:
                print(f"[CAMERA WORKER ERROR] {e}")
                time.sleep(0.1)

    def start_camera_feed(self):
        is_ai_active = self.ai_status_var.get()
        is_any_device_on = self.light_var.get() or self.fan_var.get()
        is_attendance_active = getattr(self, 'attendance_running', False)

        # [IMPROVED]: Thread-safe frame read
        with frame_lock:
            pil_image = self.latest_pil_image
            human_present = self.latest_human_present
            self._frame_consumed = True

        if pil_image:
            if self.current_tab == "attendance" and is_attendance_active and hasattr(self, 'attendance_camera_screen'):
                self.update_image_on_label(pil_image, self.attendance_camera_screen)
            elif self.current_tab == "energy" and hasattr(self, 'camera_screen'):
                self.update_image_on_label(pil_image, self.camera_screen)

        if is_attendance_active and self.session_manager.is_active and not self.session_manager.is_paused:
            for face_data in getattr(self.vision_engine, 'latest_identified_faces', []):
                s_id = face_data.get('id', '')
                s_name = face_data.get('name', 'Unknown')
                if s_id != "" and s_name != "Unknown" and s_name != "Scanning...":
                    added = self.session_manager.mark_present(s_id, s_name)
                    if added:
                        self.add_student_to_ui_list(s_id, s_name)

        if not is_attendance_active:
            if not is_ai_active:
                if self.last_voice_state != "MANUAL":
                    self.last_voice_state = "MANUAL"
                    speak_text("AI Engine Offline. Manual Control Activated.")
                    self.sleep_mode_box.configure(fg_color="#4C0519", border_color=self.ALERT_RED)
                    self.sleep_mode_text.configure(text="SYSTEM STATUS: MANUAL\nAI Engine Offline", text_color=self.ALERT_RED)
                    self.presence_label.configure(text=" 👤  Presence: AI Offline", text_color=self.TEXT_MUTED)
            else:
                if not is_any_device_on:
                    if self.last_voice_state != "SLEEP":
                        self.last_voice_state = "SLEEP"
                        self.sleep_mode_box.configure(fg_color="#1E293B", border_color=self.BORDER_MUTED)
                        self.sleep_mode_text.configure(text="SYSTEM STATUS: SLEEP MODE\nWaiting for manual activation", text_color=self.TEXT_MUTED)
                        self.presence_label.configure(text=" 👤  Presence: Sleeping (CPU Saved)", text_color=self.TEXT_MUTED)
                else:
                    self.sleep_mode_box.configure(fg_color="#064E3B", border_color=self.NEON_GREEN)
                    self.sleep_mode_text.configure(text="SYSTEM STATUS: AI ACTIVE\nAuto Turn-Off Monitoring", text_color=self.NEON_GREEN)

                    if human_present:
                        if self.last_voice_state != "DETECTED":
                            self.last_voice_state = "DETECTED"
                            self.presence_label.configure(text=" 👤  Presence: Detected", text_color=self.NEON_GREEN)
                    else:
                        if self.vision_engine.presence_timer > 0:
                            self.last_voice_state = "COUNTING"
                            time_left = max(0, int(self.vision_engine.presence_timer / 30))
                            self.presence_label.configure(text=f" 👤  Presence: Empty (Sleep in {time_left}s)", text_color=self.WARNING_ORANGE)
                        else:
                            if self.last_voice_state != "CLEAR":
                                self.last_voice_state = "CLEAR"
                                self.presence_label.configure(text=" 👤  Presence: Clear", text_color=self.WARNING_ORANGE)

                            if self.light_var.get():
                                self.light_var.set(False)
                                self.manual_light_toggle()

                            if self.fan_var.get():
                                self.fan_var.set(False)
                                self.manual_fan_toggle()

        self.after(30, self.start_camera_feed)

    def update_image_on_label(self, pil_image, label):
        orig_w, orig_h = pil_image.size
        ratio = min(850 / orig_w, 540 / orig_h)
        new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)

        cache_key = id(label)
        cached = self._img_cache.get(cache_key)
        
        if cached and cached._size == (new_w, new_h):
            cached.configure(light_image=pil_image, dark_image=pil_image)
            # Re-associate image if it was cleared previously (e.g. image="")
            try:
                if label.cget("image") != cached:
                    label.configure(image=cached, text="")
            except Exception:
                label.configure(image=cached, text="")
        else:
            ctk_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(new_w, new_h))
            self._img_cache[cache_key] = ctk_img
            label.configure(image=ctk_img, text="")

    def update_live_system(self):
        now = datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.strftime("%A, %d %b %Y")

        self.live_clock_label.configure(text=f"    ⏱           {time_str}\n{date_str}")

        check_day = now.strftime("%d")
        if check_day != self.current_day_str:
            self.current_day_str = check_day
            for i in range(5):
                target_date = now - timedelta(days=4-i)
                self.chart_day_labels[i].configure(text=target_date.strftime("%a"))
                self.chart_date_labels[i].configure(text=target_date.strftime("%d/%m"))

        self.after(1000, self.update_live_system)

    def update_attendance_timer_ui(self):
        if getattr(self, 'attendance_running', False) and self.session_manager.is_active:
            mins, secs = self.session_manager.get_remaining_time()

            if self.session_manager.is_paused:
                self.timer_label.configure(text=f"  ⏱    PAUSED [{mins:02d}:{secs:02d}]", text_color=self.WARNING_ORANGE)
            else:
                self.timer_label.configure(text=f"  ⏱    {mins:02d}:{secs:02d}", text_color=self.ACCENT_CYAN)

            if mins == 0 and secs == 0:
                self.stop_live_session()
                speak_text("15 minute scan complete. Session ended automatically.")

        self.after(1000, self.update_attendance_timer_ui)

    # ==================================================================================
    #   🔔  TOAST NOTIFICATION SYSTEM
    # ==================================================================================
    def poll_hardware_status(self):
        """Poll hardware status queue and show toast notifications."""
        try:
            while not hw_status_queue.empty():
                status_type, message = hw_status_queue.get_nowait()
                self.show_toast(message, status_type)
        except Exception:
            pass
        self.after(200, self.poll_hardware_status)

    def show_toast(self, message, toast_type="success"):
        """Show an animated toast notification in the top-right corner."""
        color = self.NEON_GREEN if toast_type == "success" else self.ALERT_RED
        icon = " ✅ " if toast_type == "success" else " ❌ "
        border_color = color
        bg_color = "#0A1A14" if toast_type == "success" else "#1A0A10"

        toast = ctk.CTkFrame(self, fg_color=bg_color, corner_radius=12, border_width=2, border_color=border_color, width=320, height=45)
        toast.place(relx=0.98, rely=0.02, anchor="ne")
        toast.lift()
        toast.pack_propagate(False)

        ctk.CTkLabel(toast, text=f"  {icon}  {message}", font=ctk.CTkFont(size=13, weight="bold"), text_color=color).pack(expand=True, padx=10)

        self._toast_widgets.append(toast)

        # Auto-dismiss after 3 seconds with fade
        def dismiss():
            try:
                toast.place_forget()
                toast.destroy()
                if toast in self._toast_widgets:
                    self._toast_widgets.remove(toast)
            except Exception:
                pass

        self.after(3000, dismiss)

    # ==================================================================================
    #   📷  ATTENDANCE FRAME
    # ==================================================================================
    def get_current_time_slot(self):
        import datetime
        now = datetime.datetime.now()
        current_minutes = now.hour * 60 + now.minute
        
        slots = [
            ("08:30 AM - 10:00 AM", 510, 600),
            ("10:00 AM - 11:30 AM", 600, 690),
            ("11:30 AM - 01:00 PM", 690, 780),
            ("01:00 PM - 02:30 PM", 780, 870),
            ("02:30 PM - 04:00 PM", 870, 960),
            ("04:00 PM - 05:30 PM", 960, 1050),
            ("05:30 PM - 07:00 PM", 1050, 1140),
            ("07:00 PM - 08:30 PM", 1140, 1230),
            ("08:30 PM - 10:00 PM", 1230, 1320),
        ]
        
        for slot_name, start, end in slots:
            if start <= current_minutes < end:
                return slot_name
                
        if current_minutes < 510:
            return "08:30 AM - 10:00 AM"
        return "08:30 PM - 10:00 PM"

    def setup_attendance_frame(self):
        self.frame_attendance.grid_columnconfigure(0, weight=1)
        self.frame_attendance.grid_rowconfigure(1, weight=1)

        # Top bar of attendance panel
        top_bar = ctk.CTkFrame(self.frame_attendance, fg_color=self.BG_CARD, height=60, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED)
        top_bar.pack(fill="x", pady=(0, 15))
        top_bar.pack_propagate(False)

        ctk.CTkLabel(top_bar, text="    🎓  Course: Software Engineering", font=ctk.CTkFont(size=18, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=20)

        # [NEW]: Time Slot dropdown in top bar (dynamically defaults to current time slot!)
        ctk.CTkLabel(top_bar, text=" 📅  Time Slot:", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=(30, 10))
        self.time_slot_var = ctk.StringVar(value=self.get_current_time_slot())
        self.time_slot_menu = ctk.CTkOptionMenu(
            top_bar,
            values=[
                "08:30 AM - 10:00 AM",
                "10:00 AM - 11:30 AM",
                "11:30 AM - 01:00 PM",
                "01:00 PM - 02:30 PM",
                "02:30 PM - 04:00 PM",
                "04:00 PM - 05:30 PM",
                "05:30 PM - 07:00 PM",
                "07:00 PM - 08:30 PM",
                "08:30 PM - 10:00 PM"
            ],
            variable=self.time_slot_var,
            width=180,
            height=32,
            fg_color=self.BG_MAIN,
            button_color=self.BG_MAIN,
            button_hover_color=self.BTN_HOVER_BG,
            dropdown_fg_color=self.BG_CARD,
            dropdown_hover_color=self.BTN_HOVER_BG,
            dropdown_text_color=self.TEXT_WHITE
        )
        self.time_slot_menu.pack(side="left")
        
        # [NEW]: Camera selection in top bar
        ctk.CTkLabel(top_bar, text=" 📷  Camera:", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=(30, 10))
        self.attendance_camera_var = ctk.StringVar(value="Laptop Camera")
        self.attendance_camera_menu = ctk.CTkOptionMenu(
            top_bar,
            values=["Laptop Camera", "USB Camera", "Mobile Camera"],
            variable=self.attendance_camera_var,
            width=150,
            height=32,
            fg_color=self.BG_MAIN,
            button_color=self.BG_MAIN,
            button_hover_color=self.BTN_HOVER_BG,
            dropdown_fg_color=self.BG_CARD,
            dropdown_hover_color=self.BTN_HOVER_BG,
            dropdown_text_color=self.TEXT_WHITE,
            command=self.change_attendance_camera
        )
        self.attendance_camera_menu.pack(side="left")
        self.timer_label = ctk.CTkLabel(top_bar, text="  ⏱    15:00", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.TEXT_MUTED)
        self.timer_label.pack(side="right", padx=30)

        bottom_bar = ctk.CTkFrame(self.frame_attendance, fg_color="transparent", height=60)
        bottom_bar.pack(side="bottom", fill="x", pady=(20, 0))
        bottom_bar.pack_propagate(False)

        self.btn_start_scan = ctk.CTkButton(bottom_bar, text="   ▶         START SCAN", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                            fg_color=self.NEON_GREEN, text_color="#000000", hover_color=self.ACCENT_CYAN, command=self.start_live_session)
        self.btn_start_scan.pack(side="left")

        self.btn_pause_scan = ctk.CTkButton(bottom_bar, text="   ⏸         PAUSE", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                            fg_color=self.WARNING_ORANGE, text_color="#000000", hover_color="#D97706", command=self.toggle_pause_session, state="disabled")
        self.btn_pause_scan.pack(side="left", padx=15)

        self.btn_end_scan = ctk.CTkButton(bottom_bar, text="   ⏹         STOP SESSION", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                          fg_color="#4C0519", hover_color=self.ALERT_RED, command=self.stop_live_session, state="disabled")
        self.btn_end_scan.pack(side="left")

        self.btn_save_session = ctk.CTkButton(bottom_bar, text="   💾   SAVE SESSION TO CSV", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                              fg_color=self.ACCENT_CYAN, text_color="#000000", hover_color="#FFFFFF", command=self.save_live_session)
        self.btn_save_session.pack(side="right")
        
        body_frame = ctk.CTkFrame(self.frame_attendance, fg_color="transparent")
        body_frame.pack(side="top", fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=75)
        body_frame.grid_columnconfigure(1, weight=25)
        body_frame.grid_rowconfigure(0, weight=1)

        cam_frame = ctk.CTkFrame(body_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        cam_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        self.attendance_camera_screen = ctk.CTkLabel(cam_frame, text="[ Vision System Standby ]\nClick 'Start Scan' to activate 15-min window", font=ctk.CTkFont(size=18), text_color=self.TEXT_MUTED, fg_color="#000000", corner_radius=10)
        self.attendance_camera_screen.pack(fill="both", expand=True, padx=15, pady=15)

        list_frame = ctk.CTkFrame(body_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        list_frame.grid(row=0, column=1, sticky="nsew")

        list_header = ctk.CTkFrame(list_frame, fg_color="#0F172A", corner_radius=10, height=50)
        list_header.pack(fill="x", padx=10, pady=10)
        list_header.pack_propagate(False)

        self.present_count_lbl = ctk.CTkLabel(list_header, text="  ✅    Present: 0", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.NEON_GREEN)
        self.present_count_lbl.pack(expand=True)

        self.scrollable_list = ctk.CTkScrollableFrame(list_frame, fg_color="transparent")
        self.scrollable_list.pack(fill="both", expand=True, padx=5, pady=5)

    def start_live_session(self):
        self.attendance_running = True
        self.session_manager.start_session()

        self.btn_start_scan.configure(state="disabled", fg_color="#1E293B", text_color=self.TEXT_MUTED)
        self.btn_pause_scan.configure(state="normal", text="   ⏸         PAUSE", fg_color=self.WARNING_ORANGE)
        self.btn_end_scan.configure(state="normal", fg_color=self.ALERT_RED)
        self.timer_label.configure(text_color=self.ACCENT_CYAN)

        for widget in self.scrollable_list.winfo_children():
            widget.destroy()
        self.present_count_lbl.configure(text="  ✅    Present: 0")

        speak_text("Attendance window started. Scanning live.")

    def toggle_pause_session(self):
        if self.session_manager.is_paused:
            self.session_manager.resume_session()
            self.btn_pause_scan.configure(text="   ⏸         PAUSE", fg_color=self.WARNING_ORANGE)
            speak_text("Scanning resumed.")
        else:
            self.session_manager.pause_session()
            self.btn_pause_scan.configure(text="   ▶         RESUME", fg_color=self.NEON_GREEN)
            speak_text("Scanning paused.")

    def stop_live_session(self):
        self.attendance_running = False
        self.session_manager.stop_session()

        self.btn_start_scan.configure(state="normal", fg_color=self.NEON_GREEN, text_color="#000000")
        self.btn_pause_scan.configure(state="disabled", text="   ⏸         PAUSE", fg_color=self.BORDER_MUTED)
        self.btn_end_scan.configure(state="disabled", fg_color="#4C0519")
        self.timer_label.configure(text="  ⏱    00:00", text_color=self.TEXT_MUTED)
        self.attendance_camera_screen.configure(image="", text="[ Session Ended ]\nReady for Manual Override or Save")
        self._img_cache.pop(id(self.attendance_camera_screen), None)

        speak_text("Session stopped permanently.")

    def save_live_session(self):
        if len(self.session_manager.present_students) == 0:
            speak_text("No students were detected to save.")
            return

        time_slot = self.time_slot_var.get()
        success = self.session_manager.save_to_csv(time_slot=time_slot)
        if success:
            speak_text("Attendance session securely saved to database.")
            self.present_count_lbl.configure(text="  💾   SAVED!", text_color=self.ACCENT_CYAN)
            self.show_toast("Attendance saved to CSV", "success")
            self.stop_live_session()
            
            # [NEW]: Update dashboard stats after saving
            self.after(500, self.update_dashboard_live_data)

    def add_student_to_ui_list(self, s_id, s_name):
        count = len(self.session_manager.present_students)
        self.present_count_lbl.configure(text=f"  ✅    Present: {count}")

        row = ctk.CTkFrame(self.scrollable_list, fg_color=self.BG_MAIN, corner_radius=8, height=50)
        row.pack(fill="x", pady=4, padx=5)
        row.pack_propagate(False)

        # Get initials for student avatar
        initials = "".join([part[0] for part in s_name.split() if part])[:2].upper()

        avatar = ctk.CTkFrame(row, fg_color=self.ACTIVE_TAB_BG, width=32, height=32, corner_radius=16)
        avatar.pack(side="left", padx=10, pady=9)
        avatar.pack_propagate(False)

        avatar_lbl = ctk.CTkLabel(avatar, text=initials, font=ctk.CTkFont(size=12, weight="bold"), text_color=self.ACCENT_CYAN)
        avatar_lbl.pack(expand=True)

        txt_container = ctk.CTkFrame(row, fg_color="transparent")
        txt_container.pack(side="left", fill="both", expand=True, pady=5)

        name_lbl = ctk.CTkLabel(txt_container, text=s_name, font=ctk.CTkFont(size=13, weight="bold"), text_color=self.TEXT_WHITE, anchor="w")
        name_lbl.pack(anchor="w", pady=(2, 0))

        id_lbl = ctk.CTkLabel(txt_container, text=s_id, font=ctk.CTkFont(size=11), text_color=self.TEXT_MUTED, anchor="w")
        id_lbl.pack(anchor="w")

        check = ctk.CTkLabel(row, text=" ✔ ", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.NEON_GREEN)
        check.pack(side="right", padx=15)

        speak_text(f"{s_name} detected")

    # ==================================================================================
    #   🏠  SIDEBAR & NAVIGATION
    # ==================================================================================
    def create_sidebar_btn(self, text, row, command):
        btn = ctk.CTkButton(self.sidebar_frame, text=text, font=ctk.CTkFont(size=14), height=50, anchor="w", fg_color="transparent", hover_color=self.BTN_HOVER_BG, border_spacing=15, text_color=self.TEXT_MUTED, corner_radius=10, command=command)
        btn.grid(row=row, column=0, padx=20, pady=6, sticky="ew")
        return btn

    # ==================================================================================
    #   🏠  DASHBOARD FRAME
    # ==================================================================================
    def setup_dashboard_frame(self):
        main_title_frame = ctk.CTkFrame(self.frame_dashboard, fg_color=self.BG_CARD, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED, height=70)
        main_title_frame.pack(fill="x", pady=(0, 20))
        main_title_frame.pack_propagate(False)
        ctk.CTkLabel(main_title_frame, text="VISIONLINK SMART CLASS ENGINE", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.TEXT_WHITE).pack(expand=True)

        header_container = ctk.CTkFrame(self.frame_dashboard, fg_color="transparent")
        header_container.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header_container, text="System Overview", font=ctk.CTkFont(size=18, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left")

        cards_frame = ctk.CTkFrame(self.frame_dashboard, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 30))
        cards_frame.grid_columnconfigure((0,1,2), weight=1, uniform="cards")

        self.stat_faces_label = self.create_stat_card(cards_frame, 0, "    👥   Known Faces", "Loading...", self.ACCENT_CYAN)
        self.stat_sessions_label = self.create_stat_card(cards_frame, 1, "    📊   Total Sessions", "Loading...", self.NEON_GREEN)
        self.ai_mode_display = self.create_stat_card(cards_frame, 2, "    🔋   AI Master Switch", "ACTIVE MODE", self.WARNING_ORANGE)

        ai_control_panel = ctk.CTkFrame(self.frame_dashboard, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED, height=90)
        ai_control_panel.pack(fill="x", pady=(0, 30))
        ai_control_panel.pack_propagate(False)

        self.ai_status_var = ctk.BooleanVar(master=self, value=True)
        switch_container = ctk.CTkFrame(ai_control_panel, fg_color="transparent")
        switch_container.place(relx=0.5, rely=0.5, anchor="center")

        self.ai_status_badge = ctk.CTkFrame(switch_container, fg_color="#064E3B", corner_radius=8, border_width=1, border_color=self.NEON_GREEN, width=160, height=45)
        self.ai_status_badge.pack(side="left", padx=(0, 20))
        self.ai_status_badge.pack_propagate(False)

        self.ai_switch_label = ctk.CTkLabel(self.ai_status_badge, text="STATUS: AI ACTIVE", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.NEON_GREEN)
        self.ai_switch_label.pack(expand=True)

        self.ai_switch = ctk.CTkSwitch(switch_container, text="", progress_color=self.NEON_GREEN, button_color="#FFFFFF", button_hover_color=self.ACCENT_CYAN, switch_width=70, switch_height=35, variable=self.ai_status_var, command=self.toggle_ai_system)
        self.ai_switch.pack(side="left")

        bottom_frame = ctk.CTkFrame(self.frame_dashboard, fg_color="transparent")
        bottom_frame.pack(fill="both", expand=True)

        details_panel = ctk.CTkFrame(bottom_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        details_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        title_frame_left = ctk.CTkFrame(details_panel, fg_color="transparent")
        title_frame_left.pack(fill="x", padx=25, pady=(25, 20))
        ctk.CTkLabel(title_frame_left, text="System Configurations", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(anchor="w")
        ctk.CTkFrame(title_frame_left, height=2, fg_color=self.WARNING_ORANGE).pack(fill="x", pady=(5,0))

        hw_col = ctk.CTkFrame(details_panel, fg_color="transparent")
        hw_col.pack(anchor="w", padx=25, pady=(0, 25))
        self.add_info_row(hw_col, 0, " 💡 ", "Lights", "1 Device (CH-1)", self.TEXT_WHITE)
        self.add_info_row(hw_col, 1, " ❄️ ", "Fans", "1 Device (CH-2)", self.TEXT_WHITE)
        self.add_info_row(hw_col, 2, " 📷 ", "Vision", "IP Webcam", self.TEXT_WHITE)
        self.add_info_row(hw_col, 3, " 🗄️ ", "Database", "CSV Storage", self.TEXT_WHITE)
        self.add_info_row(hw_col, 4, " 🧠 ", "AI Core", "Opt. Layer 1", self.TEXT_WHITE)

        graph_panel = ctk.CTkFrame(bottom_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        graph_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))

        title_frame_right = ctk.CTkFrame(graph_panel, fg_color="transparent")
        title_frame_right.pack(fill="x", padx=25, pady=(25, 5))
        ctk.CTkLabel(title_frame_right, text="Attendance This Week", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(anchor="w")
        ctk.CTkFrame(title_frame_right, height=2, fg_color=self.NEON_GREEN).pack(fill="x", pady=(5,0))

        ctk.CTkLabel(graph_panel, text="Daily Student Count (Last 5 Days)", font=ctk.CTkFont(size=14), text_color=self.TEXT_MUTED).pack(anchor="w", padx=25, pady=(5, 20))
        chart_area = ctk.CTkFrame(graph_panel, fg_color="transparent")
        chart_area.pack(expand=True, pady=(0, 20))

        # [IMPROVED]: Chart bars stored as references for live updates
        for i in range(5):
            col_frame = ctk.CTkFrame(chart_area, fg_color="transparent")
            col_frame.grid(row=0, column=i, padx=15)
            val_lbl = ctk.CTkLabel(col_frame, text="0", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.ACCENT_CYAN)
            val_lbl.pack(pady=(0, 5))
            bar = ctk.CTkProgressBar(col_frame, orientation="vertical", width=25, height=70, progress_color=self.ACCENT_CYAN, fg_color=self.BORDER_MUTED)
            bar.set(0)
            bar.pack(pady=(0, 10))
            day_lbl = ctk.CTkLabel(col_frame, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE)
            day_lbl.pack(pady=(0, 2))
            date_lbl = ctk.CTkLabel(col_frame, text="", font=ctk.CTkFont(size=12), text_color=self.TEXT_MUTED)
            date_lbl.pack()
            self.chart_day_labels.append(day_lbl)
            self.chart_date_labels.append(date_lbl)
            self.chart_bars.append(bar)
            self.chart_val_labels.append(val_lbl)

    # [NEW]: Update dashboard with live data from CSV and engine
    def update_dashboard_live_data(self):
        try:
            # Count known faces
            if hasattr(self, 'vision_engine'):
                face_count = len(self.vision_engine.known_face_names)
                unique_names = len(set(self.vision_engine.known_face_names))
                self.stat_faces_label.configure(text=f"{unique_names} Students")

            # Count sessions and daily attendance from CSV
            csv_path = "attendance.csv"
            session_count = 0
            daily_counts = {}

            if os.path.isfile(csv_path) and os.path.getsize(csv_path) > 0:
                with open(csv_path, mode='r', newline='') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    dates_times = set()
                    for row in reader:
                        if len(row) >= 4:
                            date_key = row[0]
                            session_key = f"{row[0]}_{row[1]}"
                            dates_times.add(session_key)
                            daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
                    session_count = len(dates_times)

            self.stat_sessions_label.configure(text=f"{session_count} Sessions")

            # Update chart bars with last 5 days attendance
            now = datetime.now()
            for i in range(5):
                target_date = now - timedelta(days=4-i)
                date_str = target_date.strftime("%Y-%m-%d")
                count = daily_counts.get(date_str, 0)
                max_count = max(daily_counts.values()) if daily_counts else 1
                bar_val = min(1.0, count / max(max_count, 1))
                self.chart_bars[i].set(bar_val)
                self.chart_val_labels[i].configure(text=str(count))

        except Exception as e:
            print(f"[DASHBOARD] Error updating live data: {e}")

    # ==================================================================================
    #   ⚡    ENERGY CONTROL FRAME
    # ==================================================================================
    def setup_energy_frame(self):
        header_container = ctk.CTkFrame(self.frame_energy, fg_color="transparent")
        header_container.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(header_container, text="Smart Energy Control", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left")

        content_frame = ctk.CTkFrame(self.frame_energy, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=55, uniform="main_cols")
        content_frame.grid_columnconfigure(1, weight=45, uniform="main_cols")

        camera_panel = ctk.CTkFrame(content_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        camera_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(camera_panel, text="Live Vision Feed", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(pady=(20, 10))

        self.camera_screen = ctk.CTkLabel(camera_panel, text="[ Camera Initializing... ]\nWaiting for Video Engine", font=ctk.CTkFont(size=18), text_color=self.TEXT_MUTED, fg_color="#000000", corner_radius=10)
        self.camera_screen.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        control_panel = ctk.CTkFrame(content_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        control_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        ctk.CTkLabel(control_panel, text="Hardware Command Hub", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(pady=(25, 20))

        presence_badge = ctk.CTkFrame(control_panel, fg_color=self.BG_MAIN, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED, height=50)
        presence_badge.pack(pady=(0, 25), padx=30, fill="x")
        presence_badge.pack_propagate(False)
        self.presence_label = ctk.CTkLabel(presence_badge, text=" 👤  Presence Status: Scanning...", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE)
        self.presence_label.pack(expand=True)

        self.light_card = self.create_switch_card(control_panel, "    💡   ", "Light System", "light_var", self.manual_light_toggle)
        self.fan_card = self.create_switch_card(control_panel, "    ❄️   ", "Fan System", "fan_var", self.manual_fan_toggle)

        cam_box = ctk.CTkFrame(control_panel, fg_color=self.BG_MAIN, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED)
        cam_box.pack(fill="x", padx=30, pady=(15, 0), ipady=5)
        ctk.CTkLabel(cam_box, text="    🎥   Camera Source", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE).pack(pady=(10, 5))

        btn_container = ctk.CTkFrame(cam_box, fg_color="transparent")
        btn_container.pack(pady=(0, 10))

        # --- [NEW UPDATE]: 3 Buttons with adjusted width and store references ---
        self.btn_laptop = ctk.CTkButton(btn_container, text="Laptop Cam", width=75, fg_color=self.ACCENT_CYAN, hover_color=self.ACCENT_CYAN, command=lambda: self.change_camera_source("laptop"))
        self.btn_laptop.pack(side="left", padx=3)

        self.btn_usb = ctk.CTkButton(btn_container, text="USB Cam", width=75, fg_color=self.BG_CARD, hover_color=self.WARNING_ORANGE, command=lambda: self.change_camera_source("usb"))
        self.btn_usb.pack(side="left", padx=3)

        self.btn_mobile = ctk.CTkButton(btn_container, text="Mobile Cam", width=75, fg_color=self.BG_CARD, hover_color=self.NEON_GREEN, command=lambda: self.change_camera_source("mobile"))
        self.btn_mobile.pack(side="left", padx=3)
        # ---------------------------------------------------

        # IP camera frame (hidden by default)
        self.ip_cam_frame = ctk.CTkFrame(cam_box, fg_color="transparent")
        
        self.ip_cam_entry = ctk.CTkEntry(self.ip_cam_frame, placeholder_text="http://192.168.x.x:8080/video", width=140, border_color=self.ACCENT_CYAN)
        self.ip_cam_entry.pack(side="left", padx=(0, 5), pady=(0, 10))
        
        btn_connect = ctk.CTkButton(self.ip_cam_frame, text="Connect", width=60, fg_color=self.ACCENT_CYAN, text_color=self.BG_MAIN, hover_color=self.NEON_GREEN, command=self.connect_mobile_camera)
        btn_connect.pack(side="left", pady=(0, 10))

        self.sleep_mode_box = ctk.CTkFrame(control_panel, fg_color=self.BG_MAIN, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED, height=75)
        self.sleep_mode_box.pack(fill="x", padx=30, pady=(30, 0))
        self.sleep_mode_box.pack_propagate(False)
        self.sleep_mode_text = ctk.CTkLabel(self.sleep_mode_box, text="SYSTEM STATUS: INITIALIZING...", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_MUTED)
        self.sleep_mode_text.pack(expand=True)

    def change_camera_source(self, cam_type):
        if cam_type == "laptop":
            if hasattr(self, 'ip_cam_frame'):
                self.ip_cam_frame.pack_forget()
            self.update_camera_button_states("laptop")
            threading.Thread(target=self._process_camera_change, args=("laptop",), daemon=True).start()
        elif cam_type == "usb":
            if hasattr(self, 'ip_cam_frame'):
                self.ip_cam_frame.pack_forget()
            self.update_camera_button_states("usb")
            threading.Thread(target=self._process_camera_change, args=("usb",), daemon=True).start()
        elif cam_type == "mobile":
            if hasattr(self, 'ip_cam_frame'):
                self.ip_cam_frame.pack(pady=(0, 5))
            self.update_camera_button_states("mobile")
            speak_text("Please enter mobile IP address and click connect")

    def connect_mobile_camera(self):
        threading.Thread(target=self._process_camera_change, args=("mobile",), daemon=True).start()

    def update_camera_button_states(self, active_type):
        if not hasattr(self, 'btn_laptop') or not self.btn_laptop:
            return
        self.btn_laptop.configure(fg_color=self.BG_CARD)
        self.btn_usb.configure(fg_color=self.BG_CARD)
        self.btn_mobile.configure(fg_color=self.BG_CARD)
        
        if active_type == "laptop":
            self.btn_laptop.configure(fg_color=self.ACCENT_CYAN)
        elif active_type == "usb":
            self.btn_usb.configure(fg_color=self.WARNING_ORANGE)
        elif active_type == "mobile":
            self.btn_mobile.configure(fg_color=self.NEON_GREEN)

    def _process_camera_change(self, cam_type):
        if hasattr(self, 'camera_screen'):
            self.camera_screen.configure(image="", text="[ Switching Camera... ]\nPlease wait safely.")
        
        time.sleep(0.5)

        if cam_type == "laptop":
            self.vision_engine.change_camera(0)
            speak_text("Switched to Laptop Camera")
            if hasattr(self, 'attendance_camera_var'):
                self.attendance_camera_var.set("Laptop Camera")
                
        elif cam_type == "usb":
            self.vision_engine.change_camera(1)
            speak_text("Switched to USB Camera")
            if hasattr(self, 'attendance_camera_var'):
                self.attendance_camera_var.set("USB Camera")
                
        elif cam_type == "mobile":
            url = self.ip_cam_entry.get().strip()
            if url == "":
                speak_text("Please enter mobile IP address first")
                if hasattr(self, 'camera_screen'):
                    self.camera_screen.configure(image="", text="[ Offline Standby ]\nPlease select a camera source.")
            else:
                if url.isdigit():
                    self.vision_engine.change_camera(int(url))
                    speak_text(f"Switched to Camera {url}")
                else:
                    if not url.endswith("video"):
                        if url.endswith("/"):
                            url += "video"
                        else:
                            url += "/video"
                    self.vision_engine.change_camera(url)
                    speak_text("Switched to Mobile Camera")
                if hasattr(self, 'attendance_camera_var'):
                    self.attendance_camera_var.set("Mobile Camera")

    def change_attendance_camera(self, choice):
        if choice == "Laptop Camera":
            self.vision_engine.change_camera(0)
            speak_text("Switched to Laptop Camera")
            self.show_toast("Laptop Camera active", "success")
        elif choice == "USB Camera":
            self.vision_engine.change_camera(1)
            speak_text("Switched to USB Camera")
            self.show_toast("USB Camera active", "success")
        elif choice == "Mobile Camera":
            url = self.ip_cam_entry.get().strip()
            if url == "":
                speak_text("Set mobile IP address in Energy Control first")
                self.show_toast("Set Mobile IP on Energy tab", "error")
                self.attendance_camera_var.set("Laptop Camera")
            else:
                if url.isdigit():
                    self.vision_engine.change_camera(int(url))
                    speak_text(f"Switched to Camera {url}")
                else:
                    if not url.endswith("video"):
                        if url.endswith("/"):
                            url += "video"
                        else:
                            url += "/video"
                    self.vision_engine.change_camera(url)
                    speak_text("Switched to Mobile Camera")
                    self.show_toast("Mobile Camera active", "success")

    def create_switch_card(self, parent, icon, name, var_name, cmd):
        card = ctk.CTkFrame(parent, fg_color=self.BG_MAIN, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED, height=60)
        card.pack(fill="x", padx=30, pady=(0, 15))
        card.pack_propagate(False)

        icon_lbl = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=20))
        icon_lbl.place(x=15, rely=0.5, anchor="w")
        name_lbl = ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE)
        name_lbl.place(x=45, rely=0.5, anchor="w")

        setattr(self, var_name, ctk.BooleanVar(master=self, value=False))
        sw = ctk.CTkSwitch(card, text="", progress_color=self.NEON_GREEN, button_hover_color=self.ACCENT_CYAN, switch_width=44, switch_height=22, variable=getattr(self, var_name), command=cmd)
        sw.place(relx=0.75, rely=0.5, anchor="center")

        status = ctk.CTkLabel(card, text="OFF", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_MUTED, width=40, anchor="w")
        status.place(relx=0.88, rely=0.5, anchor="center")
        setattr(self, var_name + "_lbl", status)
        return card

    def send_hardware_command(self, endpoint):
        hardware_queue.put(endpoint)

    def manual_light_toggle(self):
        val, col = ("ON", self.NEON_GREEN) if self.light_var.get() else ("OFF", self.TEXT_WHITE)
        self.light_var_lbl.configure(text=val, text_color=col)
        state = "Activated" if self.light_var.get() else "Deactivated"
        if self.light_var.get():
            self.vision_engine.presence_timer = self.vision_engine.MAX_TIMER
            self.last_voice_state = "COUNTING"
            self.send_hardware_command("light_on")
        else:
            self.send_hardware_command("light_off")
        speak_text(f"Light {state}")

    def manual_fan_toggle(self):
        val, col = ("ON", self.NEON_GREEN) if self.fan_var.get() else ("OFF", self.TEXT_WHITE)
        self.fan_var_lbl.configure(text=val, text_color=col)
        state = "Activated" if self.fan_var.get() else "Deactivated"
        if self.fan_var.get():
            self.vision_engine.presence_timer = self.vision_engine.MAX_TIMER
            self.last_voice_state = "COUNTING"
            self.send_hardware_command("fan_on")
        else:
            self.send_hardware_command("fan_off")
        speak_text(f"Fan {state}")

    def toggle_ai_system(self):
        if self.ai_status_var.get():
            self.ai_status_badge.configure(fg_color="#064E3B", border_color=self.NEON_GREEN)
            self.ai_switch_label.configure(text="STATUS: AI ACTIVE", text_color=self.NEON_GREEN)
            self.ai_switch.configure(progress_color=self.NEON_GREEN)
            self.ai_mode_display.configure(text="ACTIVE MODE", text_color=self.WARNING_ORANGE)
        else:
            self.ai_status_badge.configure(fg_color="#4C0519", border_color=self.ALERT_RED)
            self.ai_switch_label.configure(text="STATUS: OFFLINE", text_color=self.ALERT_RED)
            self.ai_switch.configure(progress_color=self.ALERT_RED)
            self.ai_mode_display.configure(text="OFFLINE", text_color=self.ALERT_RED)

    # ==================================================================================
    #   📋  RECORDS HISTORY FRAME (NEW)
    # ==================================================================================
    def setup_records_frame(self):
        # Title bar
        title_bar = ctk.CTkFrame(self.frame_records, fg_color=self.BG_CARD, height=60, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED)
        title_bar.pack(fill="x", pady=(0, 15))
        title_bar.pack_propagate(False)
        ctk.CTkLabel(title_bar, text="    📋   ATTENDANCE RECORDS", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=20)
        self.records_count_label = ctk.CTkLabel(title_bar, text=" 📊  Total: 0 records", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_CYAN)
        self.records_count_label.pack(side="right", padx=20)

        # Search and controls bar
        controls_bar = ctk.CTkFrame(self.frame_records, fg_color="transparent", height=50)
        controls_bar.pack(fill="x", pady=(0, 10))
        controls_bar.pack_propagate(False)

        self.records_search = ctk.CTkEntry(controls_bar, placeholder_text=" 🔍  Search by Student ID or Name...", width=260, height=40, border_color=self.ACCENT_CYAN, fg_color=self.BG_CARD)
        self.records_search.pack(side="left", padx=(0, 15))
        self.records_search.bind("<KeyRelease>", lambda e: self.load_records_data())

        # Time Slot Filter Dropdown
        ctk.CTkLabel(controls_bar, text="Filter Slot:", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=(0, 5))
        self.records_slot_filter_var = ctk.StringVar(value="All Slots")
        self.records_slot_filter = ctk.CTkOptionMenu(
            controls_bar,
            values=[
                "All Slots",
                "08:30 AM - 10:00 AM",
                "10:00 AM - 11:30 AM",
                "11:30 AM - 01:00 PM",
                "01:00 PM - 02:30 PM",
                "02:30 PM - 04:00 PM",
                "04:00 PM - 05:30 PM",
                "05:30 PM - 07:00 PM",
                "07:00 PM - 08:30 PM",
                "08:30 PM - 10:00 PM"
            ],
            variable=self.records_slot_filter_var,
            width=170,
            height=40,
            fg_color=self.BG_MAIN,
            button_color=self.ACCENT_CYAN,
            button_hover_color=self.NEON_GREEN,
            dropdown_fg_color=self.BG_MAIN,
            dropdown_hover_color=self.ACCENT_CYAN,
            dropdown_text_color=self.TEXT_WHITE,
            command=lambda v: self.load_records_data()
        )
        self.records_slot_filter.pack(side="left", padx=(0, 15))

        btn_refresh = ctk.CTkButton(controls_bar, text="   🔄   Refresh", font=ctk.CTkFont(size=14, weight="bold"), height=40, width=110, fg_color=self.ACCENT_CYAN, text_color="#000000", hover_color="#FFFFFF", command=self.load_records_data)
        btn_refresh.pack(side="left", padx=(0, 10))

        btn_clear = ctk.CTkButton(controls_bar, text="   🗑   Clear All", font=ctk.CTkFont(size=14, weight="bold"), height=40, width=110, fg_color="#4C0519", hover_color=self.ALERT_RED, command=self.clear_all_records)
        btn_clear.pack(side="right")

        # Table header
        header_frame = ctk.CTkFrame(self.frame_records, fg_color="#0F172A", corner_radius=10, height=45)
        header_frame.pack(fill="x", pady=(0, 5))
        header_frame.pack_propagate(False)

        headers = [("Date", 0.12), ("Time", 0.12), ("Time Slot", 0.18), ("Student ID", 0.20), ("Student Name", 0.25), ("Status", 0.13)]
        current_x = 0.0
        for header_text, width_ratio in headers:
            ctk.CTkLabel(header_frame, text=header_text, font=ctk.CTkFont(size=14, weight="bold"), text_color=self.ACCENT_CYAN, anchor="w").place(relx=current_x, rely=0.5, anchor="w", relwidth=width_ratio)
            current_x += width_ratio

        # Scrollable records table
        self.records_scroll = ctk.CTkScrollableFrame(self.frame_records, fg_color="transparent")
        self.records_scroll.pack(fill="both", expand=True)

        # Empty state placeholder
        self.records_empty_label = ctk.CTkLabel(self.records_scroll, text="No attendance records found.\nSave a session from Live Attendance to see data here.", font=ctk.CTkFont(size=16), text_color=self.TEXT_MUTED)
        self.records_empty_label.pack(expand=True, pady=80)

    def load_records_data(self):
        """Load and display attendance records from CSV."""
        # Clear existing rows
        for widget in self.records_scroll.winfo_children():
            widget.destroy()

        csv_path = "attendance.csv"
        search_query = self.records_search.get().strip().lower() if hasattr(self, 'records_search') else ""

        if not os.path.isfile(csv_path) or os.path.getsize(csv_path) == 0:
            self.records_empty_label = ctk.CTkLabel(self.records_scroll, text="No attendance records found.\nSave a session from Live Attendance to see data here.", font=ctk.CTkFont(size=16), text_color=self.TEXT_MUTED)
            self.records_empty_label.pack(expand=True, pady=80)
            self.records_count_label.configure(text=" 📊  Total: 0 records")
            return

        records = []
        try:
            with open(csv_path, mode='r', newline='') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 5:
                        records.append(row)
        except Exception as e:
            print(f"[RECORDS] Error reading CSV: {e}")
            return

        # Filter by search query (Search in Student ID or Student Name)
        if search_query:
            filtered_records = []
            for r in records:
                if len(r) >= 6:
                    if search_query in r[3].lower() or search_query in r[4].lower():
                        filtered_records.append(r)
                elif len(r) >= 5:
                    if search_query in r[2].lower() or search_query in r[3].lower():
                        filtered_records.append(r)
            records = filtered_records

        # Filter by selected time slot
        slot_filter = self.records_slot_filter_var.get()
        if slot_filter != "All Slots":
            filtered_by_slot = []
            for r in records:
                r_slot = r[2] if len(r) >= 6 else "N/A"
                if r_slot == slot_filter:
                    filtered_by_slot.append(r)
            records = filtered_by_slot

        # Reverse to show newest first
        records.reverse()

        # Count unique student attendances (unique per Date + Time Slot + Student ID) to avoid duplicate scans
        present_keys = set()
        for r in records:
            if len(r) >= 6:
                r_date = r[0]
                r_slot = r[2]
                r_id = r[3]
                status = r[5]
            else:
                r_date = r[0]
                r_slot = "N/A"
                r_id = r[2]
                status = r[4]
                
            if status == "Present":
                present_keys.add((r_date, r_slot, r_id))
                
        total_present = len(present_keys)

        if slot_filter == "All Slots":
            self.records_count_label.configure(text=f" 📊  Total: {len(records)} records | Present: {total_present}")
        else:
            self.records_count_label.configure(text=f" 📊  Slot Present: {total_present} students")

        if len(records) == 0:
            empty_lbl = ctk.CTkLabel(self.records_scroll, text="No matching records found.", font=ctk.CTkFont(size=16), text_color=self.TEXT_MUTED)
            empty_lbl.pack(expand=True, pady=80)
            return

        # Render rows
        for idx, row in enumerate(records):
            bg = self.BG_CARD if idx % 2 == 0 else self.BG_MAIN
            row_frame = ctk.CTkFrame(self.records_scroll, fg_color=bg, corner_radius=8, height=40)
            row_frame.pack(fill="x", pady=2, padx=2)
            row_frame.pack_propagate(False)

            # Map values dynamically depending on row length (5 vs 6 columns)
            if len(row) >= 6:
                r_date = row[0]
                r_time = row[1]
                r_slot = row[2]
                r_id = row[3]
                r_name = row[4]
                r_status = row[5]
            else:
                r_date = row[0]
                r_time = row[1]
                r_slot = "N/A"
                r_id = row[2]
                r_name = row[3]
                r_status = row[4]

            cols = [(r_date, 0.12), (r_time, 0.12), (r_slot, 0.18), (r_id, 0.20), (r_name, 0.25), (r_status, 0.13)]
            current_x = 0.0
            for col_text, width_ratio in cols:
                text_color = self.NEON_GREEN if col_text == "Present" else self.TEXT_WHITE
                ctk.CTkLabel(row_frame, text=col_text, font=ctk.CTkFont(size=13), text_color=text_color, anchor="w").place(relx=current_x, rely=0.5, anchor="w", relwidth=width_ratio)
                current_x += width_ratio

    def clear_all_records(self):
        """Clear all attendance records."""
        csv_path = "attendance.csv"
        try:
            if os.path.isfile(csv_path):
                os.remove(csv_path)
            self.load_records_data()
            self.show_toast("All records cleared", "success")
            speak_text("All attendance records cleared.")
            self.after(500, self.update_dashboard_live_data)
        except Exception as e:
            print(f"[RECORDS] Error clearing records: {e}")

    # ==================================================================================
    #   🔧  UTILITY METHODS
    # ==================================================================================
    def create_stat_card(self, parent, col, title, val, color):
        card = ctk.CTkFrame(parent, fg_color=self.BG_CARD, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED)
        card.grid(row=0, column=col, padx=10, sticky="nsew", ipadx=10, ipady=12)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14), text_color=self.TEXT_MUTED).pack(anchor="w", padx=20, pady=(5,0))
        val_label = ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=24, weight="bold"), text_color=color)
        val_label.pack(anchor="w", padx=20, pady=(5,5))
        return val_label

    def add_info_row(self, parent, row, icon, key, val, color):
        ctk.CTkLabel(parent, text=icon, font=ctk.CTkFont(size=16), width=40, anchor="center").grid(row=row, column=0, pady=8)
        ctk.CTkLabel(parent, text=key, font=ctk.CTkFont(size=14), text_color=self.TEXT_MUTED, width=100, anchor="w").grid(row=row, column=1)
        ctk.CTkLabel(parent, text=val, font=ctk.CTkFont(size=14, weight="bold"), text_color=color, anchor="w").grid(row=row, column=2, padx=(10, 0))

    def reset_buttons(self):
        for name in ["dashboard", "energy", "attendance", "records"]:
            btn = getattr(self, f"btn_{name}")
            btn.configure(fg_color="transparent", text_color=self.TEXT_MUTED)

    def hide_all_frames(self):
        self.frame_dashboard.pack_forget()
        self.frame_energy.pack_forget()
        self.frame_attendance.pack_forget()
        self.frame_records.pack_forget()
        self.reset_buttons()

    def switch_tab(self, tab_name):
        self.current_tab = tab_name
        self.hide_all_frames()

        # Show correct frame
        frame = getattr(self, f"frame_{tab_name}")
        frame.pack(fill="both", expand=True)

        # Highlight active button
        active_btn = getattr(self, f"btn_{tab_name}")
        active_btn.configure(fg_color=self.ACTIVE_TAB_BG, text_color=self.TEXT_WHITE)

        # Position indicator bar
        self.sidebar_indicator.place(in_=active_btn, x=6, rely=0.25, relheight=0.5)

        # Trigger specific tab callbacks
        if tab_name == "dashboard":
            self.after(100, self.update_dashboard_live_data)
        elif tab_name == "records":
            self.load_records_data()

    def show_dashboard(self):
        self.switch_tab("dashboard")

    def show_energy(self):
        self.switch_tab("energy")

    def show_attendance(self):
        self.switch_tab("attendance")

    def show_records(self):
        self.switch_tab("records")

if __name__ == "__main__":
    app = VisionLinkApp()
    app.mainloop()