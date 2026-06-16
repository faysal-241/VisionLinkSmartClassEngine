import cv2
import os
import urllib.request
import numpy as np
from PIL import Image
import threading
import time
import face_recognition

print("[SYSTEM] Loading Pure Human Structure AI Engine (Zero-Latency Hybrid Edition)...")

class VisionEngine:
    def __init__(self, camera_source=0):
        print("[SYSTEM] Connecting to Camera...")
        self.camera_source = camera_source
        
        self.running = True
        self.current_frame = None
        self.ret = False
        self.lock = threading.Lock()

        self.cap = cv2.VideoCapture(camera_source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened() and camera_source == 0:
            self.cap = cv2.VideoCapture(1)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self.cap.isOpened():
            print("[SUCCESS] Camera Connected!")
            threading.Thread(target=self._capture_loop, daemon=True).start()
        else:
            print("[ERROR] No Camera Access!")

        # ==============================================================
        # Attendance System Variables
        # ==============================================================
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        self.load_known_faces()

        # Optimizer variables for smooth video tracking
        self.frame_count = 0
        self.cached_face_data = []

        # ===============================================
        # AI Model Directory Setup
        # ===============================================
        self.model_dir = "ai_models"
        os.makedirs(self.model_dir, exist_ok=True)
        self.face_proto = os.path.join(self.model_dir, "deploy.prototxt")
        self.face_model = os.path.join(self.model_dir, "res10_300x300_ssd_iter_140000.caffemodel")
        self.body_proto = os.path.join(self.model_dir, "MobileNetSSD_deploy.prototxt")
        self.body_model = os.path.join(self.model_dir, "MobileNetSSD_deploy.caffemodel")
        self.download_models()

        self.face_net = cv2.dnn.readNetFromCaffe(self.face_proto, self.face_model)
        self.body_net = cv2.dnn.readNetFromCaffe(self.body_proto, self.body_model)

        self.presence_timer = 0
        self.MAX_TIMER = 90
        print("[SUCCESS] Ultimate Human Engine Ready!")

    def load_known_faces(self):
        folder_path = "known_faces"
        print("[INFO] Loading Known Faces from folder...")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"[WARNING] Created missing '{folder_path}' folder. Please add images!")
            return

        for filename in os.listdir(folder_path):
            if filename.endswith(".jpg") or filename.endswith(".png"):
                id_name = filename.split('.')[0]
                student_id = id_name.split('_')[0]
                student_name = id_name.split('_')[1]

                image_path = os.path.join(folder_path, filename)
                image = face_recognition.load_image_file(image_path)
                
                encodings = face_recognition.face_encodings(image)
                if len(encodings) > 0:
                    encoding = encodings[0]
                    self.known_face_encodings.append(encoding)
                    self.known_face_names.append(student_name)
                    self.known_face_ids.append(student_id)
                else:
                    print(f"[WARNING] No face found in {filename}!")
        print(f"[SUCCESS] Total {len(self.known_face_names)} faces loaded successfully!")

    def _capture_loop(self):
        while self.running:
            if self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret and isinstance(self.camera_source, str):
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                with self.lock:
                    self.ret = ret
                    self.current_frame = frame
            else:
                time.sleep(0.01)

    def change_camera(self, new_source):
        print(f"[SYSTEM] Switching Camera to: {new_source}")
        with self.lock:
            if self.cap.isOpened():
                self.cap.release()
            self.camera_source = new_source
            self.cap = cv2.VideoCapture(new_source)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if self.cap.isOpened():
                print("[SUCCESS] New Camera Connected!")
            else:
                print("[ERROR] Failed to connect! Reverting to Laptop Camera.")
                self.camera_source = 0
                self.cap = cv2.VideoCapture(0)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def download_models(self):
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
        urllib.request.install_opener(opener)

        if not os.path.exists(self.face_proto):
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt", self.face_proto)
        if not os.path.exists(self.face_model):
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel", self.face_model)
        if not os.path.exists(self.body_proto):
            urllib.request.urlretrieve("https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/MobileNetSSD_deploy.prototxt", self.body_proto)
        if not os.path.exists(self.body_model):
            urls = [
                "https://raw.githubusercontent.com/PINTO0309/MobileNet-SSD-RealSense/master/caffemodel/MobileNetSSD/MobileNetSSD_deploy.caffemodel",
                "https://huggingface.co/spaces/Imran606/cds/resolve/main/MobileNetSSD_deploy.caffemodel"
            ]
            for url in urls:
                try:
                    urllib.request.urlretrieve(url, self.body_model)
                    break
                except Exception:
                    pass

    def get_frame(self, ai_active=True, scan_mode="energy"):
        with self.lock:
            if not self.ret or self.current_frame is None:
                return None, False
            frame = self.current_frame.copy()

        if not ai_active:
            if scan_mode == "energy":
                self.presence_timer = 0
            final_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(final_rgb), False

        h, w = frame.shape[:2]
        human_found_now = False

        if scan_mode == "energy":
            blob_body = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
            self.body_net.setInput(blob_body)
            body_detections = self.body_net.forward()

            for i in range(body_detections.shape[2]):
                confidence = body_detections[0, 0, i, 2]
                class_id = int(body_detections[0, 0, i, 1])
                if class_id == 15 and confidence > 0.40:
                    box = body_detections[0, 0, i, 3:7] * [w, h, w, h]
                    (startX, startY, endX, endY) = box.astype("int")
                    cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 255), 2)
                    cv2.putText(frame, f"Human Body: {int(confidence*100)}%", (startX, startY-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    human_found_now = True

            if not human_found_now:
                blob_face = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
                self.face_net.setInput(blob_face)
                face_detections = self.face_net.forward()

                for i in range(face_detections.shape[2]):
                    confidence = face_detections[0, 0, i, 2]
                    if confidence > 0.55:
                        box = face_detections[0, 0, i, 3:7] * [w, h, w, h]
                        (startX, startY, endX, endY) = box.astype("int")
                        cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)
                        cv2.putText(frame, f"Face Target: {int(confidence*100)}%", (startX, startY-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        human_found_now = True

            if human_found_now:
                self.presence_timer = self.MAX_TIMER
            else:
                if self.presence_timer > 0:
                    self.presence_timer -= 1
                sec_left = int(self.presence_timer / 30) + 1
                cv2.putText(frame, f"NO HUMAN! SLEEPING IN: {sec_left}s", (w//2 - 200, h//2), cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 255), 3)

        elif scan_mode == "attendance":
            # ===============================================
            # ATTENDANCE MODE: Zero-Lag Hybrid Tracking Engine
            # ===============================================
            blob_face = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.face_net.setInput(blob_face)
            face_detections = self.face_net.forward()

            current_boxes = []
            for i in range(face_detections.shape[2]):
                confidence = face_detections[0, 0, i, 2]
                if confidence > 0.50:
                    box = face_detections[0, 0, i, 3:7] * [w, h, w, h]
                    (startX, startY, endX, endY) = box.astype("int")
                    startX, startY = max(0, startX), max(0, startY)
                    endX, endY = min(w, endX), min(h, endY)
                    
                    if endX - startX > 20 and endY - startY > 20: 
                        current_boxes.append((startX, startY, endX, endY))

            self.frame_count += 1
            
            if self.frame_count % 8 == 0 and len(current_boxes) > 0:
                self.cached_face_data = [] 
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                fr_boxes = [(startY, endX, endY, startX) for (startX, startY, endX, endY) in current_boxes]

                try:
                    face_encodings = face_recognition.face_encodings(rgb_frame, fr_boxes)

                    for box, face_encoding in zip(current_boxes, face_encodings):
                        matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.45) 
                        name = "Unknown"
                        student_id = ""

                        face_distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
                        if len(face_distances) > 0:
                            best_match_index = np.argmin(face_distances)
                            if matches[best_match_index]:
                                name = self.known_face_names[best_match_index]
                                student_id = self.known_face_ids[best_match_index]

                        self.cached_face_data.append({'box': box, 'name': name, 'id': student_id})
                except Exception as e:
                    pass

            # STEP 3: Draw Results Flawlessly (with dynamic text box width!)
            for box in current_boxes:
                startX, startY, endX, endY = box
                display_name = "Scanning..."
                display_id = ""
                box_color = (0, 255, 255) 

                for cached in self.cached_face_data:
                    c_startX, c_startY, c_endX, c_endY = cached['box']
                    live_center_x = (startX + endX) / 2
                    cache_center_x = (c_startX + c_endX) / 2
                    
                    if abs(live_center_x - cache_center_x) < 150: 
                        display_name = cached['name']
                        display_id = cached['id']
                        if display_name != "Unknown":
                            box_color = (255, 215, 0) 
                        else:
                            box_color = (0, 0, 255) 
                        break

                display_text = f"{display_id} {display_name}" if display_id != "" else display_name
                text_color = (0, 0, 0) if display_name != "Unknown" else (255, 255, 255)
                
                # NEW: Calculate the exact width of the text to make sure the background box is wide enough!
                (text_width, text_height), _ = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_DUPLEX, 0.6, 1)
                
                # Make the colored background expand if the text is very long
                background_endX = max(endX, startX + text_width + 10)

                cv2.rectangle(frame, (startX, startY), (endX, endY), box_color, 2)
                cv2.rectangle(frame, (startX, endY - 30), (background_endX, endY), box_color, cv2.FILLED)
                
                cv2.putText(frame, display_text, (startX + 5, endY - 5), cv2.FONT_HERSHEY_DUPLEX, 0.6, text_color, 1)

        final_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(final_rgb), self.presence_timer > 0

    def release_camera(self):
        self.running = False
        if self.cap.isOpened():
            self.cap.release()