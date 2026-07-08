import customtkinter as ctk
from datetime import datetime, timedelta
from PIL import Image
import pyttsx3
import threading
import queue
import time
import os  # Required for killing zombie processes
import sys
from vision_engine import VisionEngine
from attendance_manager import AttendanceSessionManager

voice_queue = queue.Queue()

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
        except:
            pass
        voice_queue.task_done()

threading.Thread(target=voice_worker, daemon=True).start()

def speak_text(text):
    voice_queue.put(text)

class VisionLinkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VisionLink Smart Class Engine")
        self.geometry("1300x800")
        ctk.set_appearance_mode("Dark")
        
        # Triggered when the user closes the window (X button) to prevent zombie processes
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.BG_MAIN = "#05080F"
        self.BG_SIDEBAR = "#0A0F1A"
        self.BG_CARD = "#121A27"
        self.ACCENT_CYAN = "#00E5FF"
        self.NEON_GREEN = "#10B981"
        self.ALERT_RED = "#F43F5E"
        self.WARNING_ORANGE = "#F59E0B"
        self.TEXT_WHITE = "#FFFFFF"
        self.TEXT_MUTED = "#64748B"
        self.BORDER_MUTED = "#1E293B"
        self.BTN_HOVER_BG = "#162032"
        self.ACTIVE_TAB_BG = "#0D1829"
        
        self.configure(fg_color=self.BG_MAIN)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.last_voice_state = "STARTUP"
        self.current_tab = "dashboard"
        
        self.sidebar_frame = ctk.CTkFrame(self, width=290, corner_radius=0, fg_color=self.BG_SIDEBAR, border_width=1, border_color="#1E293B")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(7, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        
        self.logo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#0A1120", corner_radius=15, border_width=2, border_color=self.ACCENT_CYAN)
        self.logo_frame.grid(row=0, column=0, padx=25, pady=(40, 25), sticky="ew")
        
        self.logo_label = ctk.CTkLabel(self.logo_frame, text="VISIONLINK\nSMART CLASS",
                                       font=ctk.CTkFont(size=22, weight="bold"), text_color=self.ACCENT_CYAN)
        self.logo_label.pack(pady=18)
        
        separator = ctk.CTkFrame(self.sidebar_frame, height=2, fg_color=self.BORDER_MUTED)
        separator.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 25))
        
        self.btn_dashboard = self.create_sidebar_btn("    🏠    Dashboard Home", 2, self.show_dashboard)
        self.btn_energy = self.create_sidebar_btn("    ⚡      Energy Control", 3, self.show_energy)
        self.btn_attendance = self.create_sidebar_btn("    📷    Live Attendance", 4, self.show_attendance)
        self.btn_records = self.create_sidebar_btn("    📋    Records History", 5, self.show_records)
        
        self.live_clock_label = ctk.CTkLabel(self.sidebar_frame, text="Loading Time...",
                                             font=ctk.CTkFont(size=16, weight="bold"), text_color=self.ACCENT_CYAN)
        self.live_clock_label.grid(row=7, column=0, pady=30, sticky="s")
        
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=40, pady=30)
        
        self.chart_day_labels = []
        self.chart_date_labels = []
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
        ctk.CTkLabel(self.frame_records, text="   📋   ATTENDANCE RECORDS", font=ctk.CTkFont(size=36, weight="bold"), text_color=self.TEXT_WHITE).pack(pady=40)
        
        self.show_dashboard()
        self.update_live_system()
        self.update_attendance_timer_ui()
        
        self.vision_engine = VisionEngine(camera_source=0)
        speak_text("Welcome to Vision Link Smart Class Engine.")
        
        self.latest_pil_image = None
        self.latest_human_present = False
        threading.Thread(target=self.camera_worker, daemon=True).start()
        
        self.start_camera_feed()

    def on_closing(self):
        print("[SYSTEM] Force shutting down all engines and cameras...")
        if hasattr(self, 'vision_engine'):
            self.vision_engine.release_camera()
        self.destroy()
        os._exit(0)  # Permanently terminate all background processes in the terminal

    def camera_worker(self):
        # [NEW FIX] This variable tracks the hardware state solely in the background thread
        # It prevents the lethal "Race Condition" from forcing the timer to 0
        was_hardware_on_worker = False 
        
        while True:
            try:
                is_ai_active = self.ai_status_var.get()
                is_any_device_on = self.light_var.get() or self.fan_var.get()
                is_attendance_active = getattr(self, 'attendance_running', False)
                
                # [NEW FIX] If device just turned on manually, strictly enforce the timer reset here
                if is_any_device_on and not was_hardware_on_worker:
                    self.vision_engine.presence_timer = self.vision_engine.MAX_TIMER
                was_hardware_on_worker = is_any_device_on
                
                if is_attendance_active:
                    # If paused, AI scan will stop, only camera feed will be shown
                    if self.session_manager.is_paused:
                        pil_image, human_present = self.vision_engine.get_frame(ai_active=False, scan_mode="attendance")
                    else:
                        pil_image, human_present = self.vision_engine.get_frame(ai_active=True, scan_mode="attendance")
                        
                    self.latest_pil_image = pil_image
                    self.latest_human_present = human_present
                else:
                    process_ai_now = is_ai_active and is_any_device_on
                    pil_image, human_present = self.vision_engine.get_frame(ai_active=process_ai_now, scan_mode="energy")
                    self.latest_pil_image = pil_image
                    self.latest_human_present = human_present
                    
                time.sleep(0.01)
            except Exception as e:
                time.sleep(0.1)

    def start_camera_feed(self):
        is_ai_active = self.ai_status_var.get()
        is_any_device_on = self.light_var.get() or self.fan_var.get()
        is_attendance_active = getattr(self, 'attendance_running', False)
        
        pil_image = self.latest_pil_image
        human_present = self.latest_human_present
        if pil_image:
            if is_attendance_active:
                if self.current_tab == "attendance" and hasattr(self, 'attendance_camera_screen'):
                    self.update_image_on_label(pil_image, self.attendance_camera_screen)
            else:
                if self.current_tab == "energy" and hasattr(self, 'camera_screen'):
                    self.update_image_on_label(pil_image, self.camera_screen)
                    
        # Live Background Data Capture (Adds only if not paused)
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
                self.presence_label.configure(text="    👤    Human Presence: AI OFFLINE", text_color=self.TEXT_MUTED)
            else:
                if not is_any_device_on:
                    if self.last_voice_state != "SLEEP":
                        self.last_voice_state = "SLEEP"
                    self.sleep_mode_box.configure(fg_color="#1E293B", border_color=self.BORDER_MUTED)
                    self.sleep_mode_text.configure(text="SYSTEM STATUS: SLEEP MODE\nWaiting for manual activation", text_color=self.TEXT_MUTED)
                    self.presence_label.configure(text="    👤    Human Presence: SLEEPING (CPU Saved)", text_color=self.TEXT_MUTED)
                else:
                    self.sleep_mode_box.configure(fg_color="#064E3B", border_color=self.NEON_GREEN)
                    self.sleep_mode_text.configure(text="SYSTEM STATUS: AI ACTIVE\nAuto Turn-Off Monitoring", text_color=self.NEON_GREEN)
                    
                    if human_present:
                        if self.last_voice_state != "DETECTED":
                            self.last_voice_state = "DETECTED"
                        self.presence_label.configure(text="    👤    Human Presence: DETECTED!", text_color=self.NEON_GREEN)
                    else:
                        if self.vision_engine.presence_timer > 0:
                            self.last_voice_state = "COUNTING"
                            time_left = max(0, int(self.vision_engine.presence_timer / 30))
                            self.presence_label.configure(text=f"    👤    Human Presence: SLEEPING IN ({time_left}s)", text_color=self.WARNING_ORANGE)
                        else:
                            if self.last_voice_state != "CLEAR":
                                self.last_voice_state = "CLEAR"
                                self.presence_label.configure(text="    👤    Human Presence: CLEAR", text_color=self.WARNING_ORANGE)
                                
                                # Automatically turn off hardware ONLY when timer reaches 0 and human is clear
                                if self.light_var.get():
                                    self.light_var.set(False)
                                    self.manual_light_toggle()
                                
                                if self.fan_var.get():
                                    self.fan_var.set(False)
                                    self.manual_fan_toggle()
                                
        self.after(30, self.start_camera_feed)

    def update_image_on_label(self, pil_image, label):
        orig_w, orig_h = pil_image.size
        # Reduced max height to 540 to prevent UI Overflow (Buttons getting pushed off-screen)
        ratio = min(850 / orig_w, 540 / orig_h)
        new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
        ctk_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(new_w, new_h))
        label.configure(image=ctk_img, text="")

    def update_live_system(self):
        now = datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.strftime("%A, %d %b %Y")
        
        self.live_clock_label.configure(text=f"   ⏱      {time_str}\n{date_str}")
        
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
                self.timer_label.configure(text=f" ⏱  PAUSED [{mins:02d}:{secs:02d}]", text_color=self.WARNING_ORANGE)
            else:
                self.timer_label.configure(text=f" ⏱  {mins:02d}:{secs:02d}", text_color=self.ACCENT_CYAN)
                
            if mins == 0 and secs == 0:
                self.stop_live_session()
                speak_text("15 minute scan complete. Session ended automatically.")
                
        self.after(1000, self.update_attendance_timer_ui)

    def setup_attendance_frame(self):
        top_bar = ctk.CTkFrame(self.frame_attendance, fg_color=self.BG_CARD, height=60, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED)
        top_bar.pack(side="top", fill="x", pady=(0, 20))
        top_bar.pack_propagate(False)
        
        ctk.CTkLabel(top_bar, text="   🎓  Course: Software Engineering", font=ctk.CTkFont(size=18, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=20)
        self.timer_label = ctk.CTkLabel(top_bar, text=" ⏱  15:00", font=ctk.CTkFont(size=24, weight="bold"), text_color=self.TEXT_MUTED)
        self.timer_label.pack(side="right", padx=30)
        
        bottom_bar = ctk.CTkFrame(self.frame_attendance, fg_color="transparent", height=60)
        bottom_bar.pack(side="bottom", fill="x", pady=(20, 0))
        bottom_bar.pack_propagate(False)
        
        self.btn_start_scan = ctk.CTkButton(bottom_bar, text="  ▶     START SCAN", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                            fg_color=self.NEON_GREEN, text_color="#000000", hover_color=self.ACCENT_CYAN, command=self.start_live_session)
        self.btn_start_scan.pack(side="left")
        
        self.btn_pause_scan = ctk.CTkButton(bottom_bar, text="  ⏸     PAUSE", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                            fg_color=self.WARNING_ORANGE, text_color="#000000", hover_color="#D97706", command=self.toggle_pause_session, state="disabled")
        self.btn_pause_scan.pack(side="left", padx=15)
        
        self.btn_end_scan = ctk.CTkButton(bottom_bar, text="  ⏹     STOP SESSION", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                          fg_color="#4C0519", hover_color=self.ALERT_RED, command=self.stop_live_session, state="disabled")
        self.btn_end_scan.pack(side="left")
        
        self.btn_save_session = ctk.CTkButton(bottom_bar, text="  💾   SAVE SESSION TO CSV", font=ctk.CTkFont(size=15, weight="bold"), height=45,
                                              fg_color=self.ACCENT_CYAN, text_color="#000000", hover_color="#FFFFFF", command=self.save_live_session)
        self.btn_save_session.pack(side="right")

        body_frame = ctk.CTkFrame(self.frame_attendance, fg_color="transparent")
        body_frame.pack(side="top", fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=75)
        body_frame.grid_columnconfigure(1, weight=25)
        body_frame.grid_rowconfigure(0, weight=1)
        
        cam_frame = ctk.CTkFrame(body_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        cam_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        self.attendance_camera_screen = ctk.CTkLabel(cam_frame, text="[ Vision System Standby ]\nClick 'Start Scan' to activate 15-min window",
                                                     font=ctk.CTkFont(size=18), text_color=self.TEXT_MUTED, fg_color="#000000", corner_radius=10)
        self.attendance_camera_screen.pack(fill="both", expand=True, padx=15, pady=15)
        
        list_frame = ctk.CTkFrame(body_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        list_frame.grid(row=0, column=1, sticky="nsew")
        
        list_header = ctk.CTkFrame(list_frame, fg_color="#0F172A", corner_radius=10, height=50)
        list_header.pack(fill="x", padx=10, pady=10)
        list_header.pack_propagate(False)
        
        self.present_count_lbl = ctk.CTkLabel(list_header, text=" ✅  Present: 0", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.NEON_GREEN)
        self.present_count_lbl.pack(expand=True)
        
        self.scrollable_list = ctk.CTkScrollableFrame(list_frame, fg_color="transparent")
        self.scrollable_list.pack(fill="both", expand=True, padx=5, pady=5)

    def start_live_session(self):
        self.attendance_running = True
        self.session_manager.start_session()
        
        self.btn_start_scan.configure(state="disabled", fg_color="#1E293B", text_color=self.TEXT_MUTED)
        self.btn_pause_scan.configure(state="normal", text="  ⏸     PAUSE", fg_color=self.WARNING_ORANGE)
        self.btn_end_scan.configure(state="normal", fg_color=self.ALERT_RED)
        self.timer_label.configure(text_color=self.ACCENT_CYAN)
        
        for widget in self.scrollable_list.winfo_children():
            widget.destroy()
        self.present_count_lbl.configure(text=" ✅  Present: 0")
        
        speak_text("Attendance window started. Scanning live.")

    def toggle_pause_session(self):
        if self.session_manager.is_paused:
            self.session_manager.resume_session()
            self.btn_pause_scan.configure(text="  ⏸     PAUSE", fg_color=self.WARNING_ORANGE)
            speak_text("Scanning resumed.")
        else:
            self.session_manager.pause_session()
            self.btn_pause_scan.configure(text="  ▶     RESUME", fg_color=self.NEON_GREEN)
            speak_text("Scanning paused.")

    def stop_live_session(self):
        self.attendance_running = False
        self.session_manager.stop_session()
        
        self.btn_start_scan.configure(state="normal", fg_color=self.NEON_GREEN, text_color="#000000")
        self.btn_pause_scan.configure(state="disabled", text="  ⏸     PAUSE", fg_color=self.BORDER_MUTED)
        self.btn_end_scan.configure(state="disabled", fg_color="#4C0519")
        self.timer_label.configure(text=" ⏱  00:00", text_color=self.TEXT_MUTED)
        self.attendance_camera_screen.configure(image="", text="[ Session Ended ]\nReady for Manual Override or Save")
        
        speak_text("Session stopped permanently.")

    def save_live_session(self):
        if len(self.session_manager.present_students) == 0:
            speak_text("No students were detected to save.")
            return
            
        success = self.session_manager.save_to_csv()
        if success:
            speak_text("Attendance session securely saved to database.")
            self.present_count_lbl.configure(text=" 💾  SAVED!", text_color=self.ACCENT_CYAN)
            self.stop_live_session()

    def add_student_to_ui_list(self, s_id, s_name):
        count = len(self.session_manager.present_students)
        self.present_count_lbl.configure(text=f" ✅  Present: {count}")
        
        row = ctk.CTkFrame(self.scrollable_list, fg_color=self.BG_MAIN, corner_radius=8, height=40)
        row.pack(fill="x", pady=5, padx=5)
        row.pack_propagate(False)
        
        ctk.CTkLabel(row, text=" 👤 ", font=ctk.CTkFont(size=18)).pack(side="left", padx=10)
        ctk.CTkLabel(row, text=f"{s_id} - {s_name}", font=ctk.CTkFont(size=13, weight="bold"), text_color=self.TEXT_WHITE).pack(side="left", padx=5)
        ctk.CTkLabel(row, text=" ✔ ", font=ctk.CTkFont(size=16, weight="bold"), text_color=self.NEON_GREEN).pack(side="right", padx=15)
        
        threading.Thread(target=lambda: speak_text(f"{s_name} detected"), daemon=True).start()

    def create_sidebar_btn(self, text, row, command):
        btn = ctk.CTkButton(self.sidebar_frame, text=text, font=ctk.CTkFont(size=16, weight="bold"), height=55, anchor="w",
                            fg_color="transparent", border_width=2, border_color=self.BORDER_MUTED,
                            text_color=self.TEXT_MUTED, hover_color=self.BTN_HOVER_BG, corner_radius=12, command=command)
        btn.grid(row=row, column=0, padx=25, pady=8, sticky="ew")
        return btn

    def setup_dashboard_frame(self):
        main_title_frame = ctk.CTkFrame(self.frame_dashboard, fg_color="#0F172A", corner_radius=15, border_width=2, border_color=self.ACCENT_CYAN, height=75)
        main_title_frame.pack(fill="x", pady=(0, 15))
        main_title_frame.pack_propagate(False)
        ctk.CTkLabel(main_title_frame, text="VISIONLINK SMART CLASS ENGINE", font=ctk.CTkFont(size=30, weight="bold"), text_color=self.ACCENT_CYAN).pack(expand=True)
        
        page_title_frame = ctk.CTkFrame(self.frame_dashboard, fg_color=self.BG_CARD, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED, height=50, width=300)
        page_title_frame.pack(pady=(0, 30))
        page_title_frame.pack_propagate(False)
        ctk.CTkLabel(page_title_frame, text="DASHBOARD HOME", font=ctk.CTkFont(size=18, weight="bold"), text_color=self.TEXT_WHITE).pack(expand=True)
        
        cards_frame = ctk.CTkFrame(self.frame_dashboard, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 30))
        cards_frame.grid_columnconfigure((0,1,2), weight=1, uniform="cards")
        
        self.create_stat_card(cards_frame, 0, "    🔌   Active Devices", "02 Devices", self.ACCENT_CYAN)
        self.create_stat_card(cards_frame, 1, "    🌐   Network Link", "Stable (Wi-Fi)", self.NEON_GREEN)
        self.ai_mode_display = self.create_stat_card(cards_frame, 2, "    🔋   AI Master Switch", "ACTIVE MODE", self.WARNING_ORANGE)
        
        ai_control_panel = ctk.CTkFrame(self.frame_dashboard, fg_color=self.BG_CARD, corner_radius=20, border_width=2, border_color=self.ACCENT_CYAN, height=90)
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
        self.add_info_row(hw_col, 0, "   💡  ", "Lights", "1 Device (CH-1)", self.TEXT_WHITE)
        self.add_info_row(hw_col, 1, "   ❄️  ", "Fans", "1 Device (CH-2)", self.TEXT_WHITE)
        self.add_info_row(hw_col, 2, "   📷  ", "Vision", "IP Webcam", self.TEXT_WHITE)
        self.add_info_row(hw_col, 3, "   🗄️  ", "Database", "SQLite 3.0", self.TEXT_WHITE)
        self.add_info_row(hw_col, 4, "   🧠  ", "AI Core", "Opt. Layer 1", self.TEXT_WHITE)
        
        graph_panel = ctk.CTkFrame(bottom_frame, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        graph_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        title_frame_right = ctk.CTkFrame(graph_panel, fg_color="transparent")
        title_frame_right.pack(fill="x", padx=25, pady=(25, 5))
        ctk.CTkLabel(title_frame_right, text="Energy Efficiency Analytics", font=ctk.CTkFont(size=22, weight="bold"), text_color=self.TEXT_WHITE).pack(anchor="w")
        ctk.CTkFrame(title_frame_right, height=2, fg_color=self.NEON_GREEN).pack(fill="x", pady=(5,0))
        
        ctk.CTkLabel(graph_panel, text="Weekly Power Saved (kWh) vs Manual Control", font=ctk.CTkFont(size=14), text_color=self.TEXT_MUTED).pack(anchor="w", padx=25, pady=(5, 20))
        chart_area = ctk.CTkFrame(graph_panel, fg_color="transparent")
        chart_area.pack(expand=True, pady=(0, 20))
        
        values = [0.4, 0.7, 0.5, 0.9, 0.6]
        for i in range(5):
            col_frame = ctk.CTkFrame(chart_area, fg_color="transparent")
            col_frame.grid(row=0, column=i, padx=15)
            val_lbl = ctk.CTkLabel(col_frame, text=f"{values[i]} kWh", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.ACCENT_CYAN)
            val_lbl.pack(pady=(0, 5))
            bar = ctk.CTkProgressBar(col_frame, orientation="vertical", width=25, height=70, progress_color=self.ACCENT_CYAN, fg_color=self.BORDER_MUTED)
            bar.set(values[i])
            bar.pack(pady=(0, 10))
            day_lbl = ctk.CTkLabel(col_frame, text="", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE)
            day_lbl.pack(pady=(0, 2))
            date_lbl = ctk.CTkLabel(col_frame, text="", font=ctk.CTkFont(size=12), text_color=self.TEXT_MUTED)
            date_lbl.pack()
            self.chart_day_labels.append(day_lbl)
            self.chart_date_labels.append(date_lbl)

    def setup_energy_frame(self):
        page_title_frame = ctk.CTkFrame(self.frame_energy, fg_color=self.BG_CARD, corner_radius=10, border_width=1, border_color=self.BORDER_MUTED, height=50, width=400)
        page_title_frame.pack(pady=(0, 20))
        page_title_frame.pack_propagate(False)
        ctk.CTkLabel(page_title_frame, text="    ⚡           SMART ENERGY CONTROL", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.ACCENT_CYAN).pack(expand=True)
        
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
        
        presence_badge = ctk.CTkFrame(control_panel, fg_color="#332900", corner_radius=10, border_width=1, border_color=self.WARNING_ORANGE, height=50)
        presence_badge.pack(pady=(0, 25), padx=30, fill="x")
        presence_badge.pack_propagate(False)
        self.presence_label = ctk.CTkLabel(presence_badge, text="     👤    Human Presence: WAITING...", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.WARNING_ORANGE)
        self.presence_label.pack(expand=True)
        
        self.light_card = self.create_switch_card(control_panel, "   💡  ", "Light System", "light_var", self.manual_light_toggle)
        self.fan_card = self.create_switch_card(control_panel, "   ❄️  ", "Fan System", "fan_var", self.manual_fan_toggle)
        
        cam_box = ctk.CTkFrame(control_panel, fg_color=self.BG_MAIN, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED)
        cam_box.pack(fill="x", padx=30, pady=(15, 0), ipady=5)
        ctk.CTkLabel(cam_box, text="   🎥  Camera Source", font=ctk.CTkFont(size=14, weight="bold"), text_color=self.TEXT_WHITE).pack(pady=(10, 5))
        self.ip_cam_entry = ctk.CTkEntry(cam_box, placeholder_text="http://192.168.x.x:8080/video", width=220, border_color=self.ACCENT_CYAN)
        self.ip_cam_entry.pack(pady=(0, 10))
        
        btn_container = ctk.CTkFrame(cam_box, fg_color="transparent")
        btn_container.pack(pady=(0, 10))
        btn_laptop = ctk.CTkButton(btn_container, text="Laptop Cam", width=100, fg_color="#1E293B", hover_color=self.ACCENT_CYAN, command=lambda: self.change_camera_source("laptop"))
        btn_laptop.pack(side="left", padx=5)
        btn_mobile = ctk.CTkButton(btn_container, text="Mobile Cam", width=100, fg_color="#1E293B", hover_color=self.NEON_GREEN, command=lambda: self.change_camera_source("mobile"))
        btn_mobile.pack(side="left", padx=5)
        
        self.sleep_mode_box = ctk.CTkFrame(control_panel, fg_color="#064E3B", corner_radius=12, border_width=1, border_color=self.NEON_GREEN, height=75)
        self.sleep_mode_box.pack(fill="x", padx=30, pady=(30, 0))
        self.sleep_mode_box.pack_propagate(False)
        self.sleep_mode_text = ctk.CTkLabel(self.sleep_mode_box, text="SYSTEM STATUS: AI ACTIVE\nAuto Control Enabled", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.NEON_GREEN)
        self.sleep_mode_text.pack(expand=True)

    def change_camera_source(self, cam_type):
        if cam_type == "laptop":
            self.vision_engine.change_camera(0)
            speak_text("Switched to Laptop Camera")
        elif cam_type == "mobile":
            url = self.ip_cam_entry.get().strip()
            if url == "":
                speak_text("Please enter mobile IP address first")
            else:
                if not url.endswith("video"):
                    if url.endswith("/"):
                        url += "video"
                    else:
                        url += "/video"
                self.vision_engine.change_camera(url)
                speak_text("Switched to Mobile Camera")

    def create_switch_card(self, parent, icon, name, var_name, cmd):
        card = ctk.CTkFrame(parent, fg_color=self.BG_MAIN, corner_radius=12, border_width=1, border_color=self.BORDER_MUTED, height=60)
        card.pack(fill="x", padx=30, pady=(0, 15))
        card.pack_propagate(False)
        
        icon_lbl = ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=22))
        icon_lbl.place(x=15, rely=0.5, anchor="w")
        name_lbl = ctk.CTkLabel(card, text=name, font=ctk.CTkFont(size=16, weight="bold"), text_color=self.TEXT_WHITE)
        name_lbl.place(x=45, rely=0.5, anchor="w")
        
        setattr(self, var_name, ctk.BooleanVar(master=self, value=False))
        sw = ctk.CTkSwitch(card, text="", progress_color=self.NEON_GREEN, button_hover_color=self.ACCENT_CYAN, switch_width=50, switch_height=25, variable=getattr(self, var_name), command=cmd)
        sw.place(relx=0.75, rely=0.5, anchor="center")
        
        status = ctk.CTkLabel(card, text="OFF", font=ctk.CTkFont(size=15, weight="bold"), text_color=self.TEXT_WHITE, width=40, anchor="w")
        status.place(relx=0.88, rely=0.5, anchor="center")
        setattr(self, var_name + "_lbl", status)
        return card

    def send_hardware_command(self, endpoint):
        ESP32_IP = "http://visionlink.local"
        def task():
            try:
                import urllib.request
                urllib.request.urlopen(f"{ESP32_IP}/{endpoint}", timeout=1.5)
            except Exception as e:
                print(f"[Hardware Error] Cannot reach ESP32: {e}")
        threading.Thread(target=task, daemon=True).start()

    def manual_light_toggle(self):
        val, col = ("ON", self.NEON_GREEN) if self.light_var.get() else ("OFF", self.TEXT_WHITE)
        self.light_var_lbl.configure(text=val, text_color=col)
        state = "Activated" if self.light_var.get() else "Deactivated"
        if self.light_var.get():
            # [NEW FIX] Securely transition UI state out of 'SLEEP' or 'CLEAR' when turned on manually
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
            # [NEW FIX] Securely transition UI state out of 'SLEEP' or 'CLEAR' when turned on manually
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

    def create_stat_card(self, parent, col, title, val, color):
        card = ctk.CTkFrame(parent, fg_color=self.BG_CARD, corner_radius=15, border_width=1, border_color=self.BORDER_MUTED)
        card.grid(row=0, column=col, padx=10, sticky="nsew", ipadx=10, ipady=15)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=16), text_color=self.TEXT_MUTED).pack(anchor="w", padx=20, pady=(5,0))
        val_label = ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=28, weight="bold"), text_color=color)
        val_label.pack(anchor="w", padx=20, pady=(10,5))
        return val_label

    def add_info_row(self, parent, row, icon, key, val, color):
        ctk.CTkLabel(parent, text=icon, font=ctk.CTkFont(size=18), width=30, anchor="w").grid(row=row, column=0, pady=10)
        ctk.CTkLabel(parent, text=key, font=ctk.CTkFont(size=15), text_color=self.TEXT_MUTED, width=100, anchor="w").grid(row=row, column=1)
        ctk.CTkLabel(parent, text=":", font=ctk.CTkFont(size=15), text_color=self.TEXT_MUTED, width=20, anchor="center").grid(row=row, column=2)
        ctk.CTkLabel(parent, text=val, font=ctk.CTkFont(size=15, weight="bold"), text_color=color, anchor="w").grid(row=row, column=3, padx=(10, 0))

    def reset_buttons(self):
        for btn in [self.btn_dashboard, self.btn_energy, self.btn_attendance, self.btn_records]:
            btn.configure(fg_color="transparent", border_color=self.BORDER_MUTED, text_color=self.TEXT_MUTED)

    def hide_all_frames(self):
        self.frame_dashboard.pack_forget()
        self.frame_energy.pack_forget()
        self.frame_attendance.pack_forget()
        self.frame_records.pack_forget()
        self.reset_buttons()

    def show_dashboard(self):
        self.current_tab = "dashboard"
        self.hide_all_frames()
        self.frame_dashboard.pack(fill="both", expand=True)
        self.btn_dashboard.configure(fg_color=self.ACTIVE_TAB_BG, border_color=self.ACCENT_CYAN, text_color=self.ACCENT_CYAN)

    def show_energy(self):
        self.current_tab = "energy"
        self.hide_all_frames()
        self.frame_energy.pack(fill="both", expand=True)
        self.btn_energy.configure(fg_color=self.ACTIVE_TAB_BG, border_color=self.ACCENT_CYAN, text_color=self.ACCENT_CYAN)

    def show_attendance(self):
        self.current_tab = "attendance"
        self.hide_all_frames()
        self.frame_attendance.pack(fill="both", expand=True)
        self.btn_attendance.configure(fg_color=self.ACTIVE_TAB_BG, border_color=self.ACCENT_CYAN, text_color=self.ACCENT_CYAN)

    def show_records(self):
        self.current_tab = "records"
        self.hide_all_frames()
        self.frame_records.pack(fill="both", expand=True)
        self.btn_records.configure(fg_color=self.ACTIVE_TAB_BG, border_color=self.ACCENT_CYAN, text_color=self.ACCENT_CYAN)

if __name__ == "__main__":
    app = VisionLinkApp()
    app.mainloop()