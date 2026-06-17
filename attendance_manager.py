import time
from datetime import datetime
import csv
import os

class AttendanceSessionManager:
    def __init__(self):
        self.is_active = False
        self.is_paused = False
        self.present_students = {}
        self.start_time = 0
        self.elapsed_before_pause = 0
        self.session_duration = 15 * 60  # 15 minutes

    def start_session(self):
        self.is_active = True
        self.is_paused = False
        self.present_students = {}
        self.start_time = time.time()
        self.elapsed_before_pause = 0

    def pause_session(self):
        if self.is_active and not self.is_paused:
            self.is_paused = True
            # Save the elapsed time before pausing
            self.elapsed_before_pause += time.time() - self.start_time

    def resume_session(self):
        if self.is_active and self.is_paused:
            self.is_paused = False
            # Restart the clock after resuming
            self.start_time = time.time()

    def stop_session(self):
        self.is_active = False
        self.is_paused = False

    def get_remaining_time(self):
        if not self.is_active:
            return 0, 0
        
        if self.is_paused:
            elapsed = self.elapsed_before_pause
        else:
            elapsed = self.elapsed_before_pause + (time.time() - self.start_time)
            
        remaining = self.session_duration - elapsed
        
        if remaining <= 0:
            self.is_active = False
            return 0, 0
            
        mins, secs = divmod(int(remaining), 60)
        return mins, secs

    def mark_present(self, student_id, student_name):
        # Do not add any student if the session is paused
        if self.is_active and not self.is_paused and student_id != "":
            if student_id not in self.present_students:
                if student_name != "Unknown" and student_name != "Scanning...":
                    self.present_students[student_id] = student_name
                    return True  # New student added to the list
        return False

    def save_to_csv(self):
        if len(self.present_students) == 0:
            return False
            
        file_exists = os.path.isfile("attendance.csv")
        date_str = datetime.now().strftime("%Y-%m-%d")
        time_str = datetime.now().strftime("%I:%M %p")
        
        with open("attendance.csv", mode='a', newline='') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Date", "Time", "Student ID", "Student Name", "Status"])
            
            for s_id, s_name in self.present_students.items():
                writer.writerow([date_str, time_str, s_id, s_name, "Present"])
                
        return True