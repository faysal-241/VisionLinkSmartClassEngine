import cv2
import os
import urllib.request
import numpy as np
from PIL import Image
import multiprocessing
import time
try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False
    print("[SYSTEM] face_recognition package not found. Activating Zero-Dependency Mock Mode.")
    class MockFaceRecognition:
        @staticmethod
        def load_image_file(image_path):
            return cv2.imread(image_path)
            
        @staticmethod
        def face_encodings(image, face_locations=None):
            if face_locations is None:
                # Load whole image (known face template)
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
                gray = cv2.resize(gray, (80, 80))
                gray = cv2.equalizeHist(gray)
                mean, std = cv2.meanStdDev(gray)
                normalized = (gray.astype(np.float32) - mean[0][0]) / (std[0][0] + 1e-5)
                return [normalized.flatten()]
            
            encodings = []
            h, w = image.shape[:2]
            for (top, right, bottom, left) in face_locations:
                # Crop face box safely
                top, right, bottom, left = max(0, top), min(w, right), min(h, bottom), max(0, left)
                if bottom - top > 10 and right - left > 10:
                    crop = image[top:bottom, left:right]
                    # Check if BGR or RGB
                    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if len(crop.shape) == 3 else crop
                    gray = cv2.resize(gray, (80, 80))
                    gray = cv2.equalizeHist(gray)
                    mean, std = cv2.meanStdDev(gray)
                    normalized = (gray.astype(np.float32) - mean[0][0]) / (std[0][0] + 1e-5)
                    encodings.append(normalized.flatten())
                else:
                    encodings.append(np.zeros(6400, dtype=np.float32))
            return encodings
            
        @staticmethod
        def compare_faces(known_encodings, face_encoding, tolerance=0.45):
            if not known_encodings:
                return []
            distances = MockFaceRecognition.face_distance(known_encodings, face_encoding)
            # Correlation threshold: distance < 0.65 means correlation > 0.35 (Pearson Correlation)
            return [dist < 0.65 for dist in distances]
            
        @staticmethod
        def face_distance(known_encodings, face_encoding):
            if not known_encodings:
                return np.array([])
            
            distances = []
            for known in known_encodings:
                # Both are flat 6400-element normalized vectors
                # Correlation: dot product divided by norms
                dot_product = np.sum(face_encoding * known)
                norm_face = np.linalg.norm(face_encoding)
                norm_known = np.linalg.norm(known)
                correlation = dot_product / (norm_face * norm_known + 1e-5)
                
                # Convert correlation (-1 to 1) to distance (0 to 2)
                # If they are identical, correlation = 1.0, distance = 0.0
                # If they are opposite, correlation = -1.0, distance = 2.0
                distance = 1.0 - correlation
                distances.append(distance)
                
            return np.array(distances)
            
    face_recognition = MockFaceRecognition

print("[SYSTEM] Loading Pure Human Structure AI Engine (Enterprise Hybrid Tracker)...")

# ==============================================================================
#  🧠  THE DEEP AI BRAIN (Runs on Core 2 - Heavy Identity Scanner)
# ==============================================================================
def ai_worker_core(frame_queue, result_queue, known_encodings, known_names, known_ids):
    while True:
        try:
            data = frame_queue.get(timeout=0.05)
        except Exception:
            continue
            
        frame = data['frame']
        live_boxes = data['boxes']

        if len(live_boxes) > 0:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Format boxes for face_recognition library (Top, Right, Bottom, Left)
            fr_boxes = [(startY, endX, endY, startX) for (startX, startY, endX, endY) in live_boxes]
            
            results = []
            try:
                face_encodings = face_recognition.face_encodings(rgb_frame, fr_boxes)
                for box, face_encoding in zip(live_boxes, face_encodings):
                    matches = face_recognition.compare_faces(known_encodings, face_encoding, tolerance=0.45)
                    name = "Unknown"
                    student_id = ""
                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            name = known_names[best_match_index]
                            student_id = known_ids[best_match_index]
                            
                    results.append({'box': box, 'name': name, 'id': student_id})
                    
                if not result_queue.empty():
                    try: result_queue.get_nowait()
                    except Exception: pass
                result_queue.put(results)
            except Exception as e:
                print(f"[AI CORE ERROR] {e}")

# ==============================================================================
#  📷  THE LIVE TRACKER CORE (Runs on Core 1 - Super Fast 60FPS Tracker)
# ==============================================================================
class VisionEngine:
    def __init__(self, camera_source=0):
        print("[SYSTEM] Connecting to Camera...")
        self.camera_source = camera_source
        self.running = True
        
        self.cap = cv2.VideoCapture(camera_source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.cap.isOpened() and camera_source == 0:
            self.cap = cv2.VideoCapture(1)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        if self.cap.isOpened():
            print("[SUCCESS] Camera Connected!")
        else:
            print("[ERROR] No Camera Access!")
            
        self.known_face_encodings = []
        self.known_face_names = []
        self.known_face_ids = []
        
        self.download_models()
        self.face_net = cv2.dnn.readNetFromCaffe(self.face_proto, self.face_model)
        self.body_net = cv2.dnn.readNetFromCaffe(self.body_proto, self.body_model)
        
        self.load_known_faces()
        
        # Pipes for data communication between the 2 Cores
        self.frame_queue = multiprocessing.Queue(maxsize=1)
        self.result_queue = multiprocessing.Queue(maxsize=1)
        
        # Start Core 2 (AI Brain)
        self.ai_process = multiprocessing.Process(
            target=ai_worker_core,
            args=(self.frame_queue, self.result_queue, self.known_face_encodings, self.known_face_names, self.known_face_ids),
            daemon=True
        )
        self.ai_process.start()
        
        self.latest_identified_faces = []
        self.presence_timer = 0
        self.MAX_TIMER = 150
        print("[SUCCESS] Enterprise Hybrid Tracker Ready!")

    def load_known_faces(self):
        folder_path = "known_faces"
        print("[INFO] Loading Known Faces from folder...")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            return
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(".jpg") or filename.lower().endswith(".png"):
                # Remove all extensions (handles double .jpg.jpg)
                base_name = filename
                while '.' in base_name:
                    base_name = base_name.rsplit('.', 1)[0]
                
                # Split ID from name: '241-15-582_Saif_1' -> ID='241-15-582', Name='Saif'
                first_underscore = base_name.find('_')
                if first_underscore == -1:
                    continue
                student_id = base_name[:first_underscore]
                remaining = base_name[first_underscore+1:]
                # Remove trailing number suffix (e.g., '_1', '_2')
                name_parts = remaining.rsplit('_', 1)
                student_name = name_parts[0] if len(name_parts) > 1 and name_parts[1].isdigit() else remaining
                
                image_path = os.path.join(folder_path, filename)
                try:
                    image = face_recognition.load_image_file(image_path)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) > 0:
                        self.known_face_encodings.append(encodings[0])
                        self.known_face_names.append(student_name)
                        self.known_face_ids.append(student_id)
                        print(f"  [OK] Loaded: {student_id} - {student_name}")
                except Exception as e:
                    print(f"  [WARN] Failed to load {filename}: {e}")
        print(f"[SUCCESS] Total {len(self.known_face_names)} faces loaded successfully!")

    def download_models(self):
        self.model_dir = "ai_models"
        os.makedirs(self.model_dir, exist_ok=True)
        self.face_proto = os.path.join(self.model_dir, "deploy.prototxt")
        self.face_model = os.path.join(self.model_dir, "res10_300x300_ssd_iter_140000.caffemodel")
        self.body_proto = os.path.join(self.model_dir, "MobileNetSSD_deploy.prototxt")
        self.body_model = os.path.join(self.model_dir, "MobileNetSSD_deploy.caffemodel")
        
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        
        def safe_download(url, path, name):
            if not os.path.exists(path):
                try:
                    print(f"[DOWNLOAD] Fetching {name}...")
                    urllib.request.urlretrieve(url, path)
                    print(f"[DOWNLOAD] {name} OK")
                except Exception as e:
                    print(f"[DOWNLOAD ERROR] Failed to download {name}: {e}")
        
        safe_download("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt", self.face_proto, "Face Proto")
        safe_download("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel", self.face_model, "Face Model")
        safe_download("https://raw.githubusercontent.com/PINTO0309/MobileNet-SSD-RealSense/master/caffemodel/MobileNetSSD/MobileNetSSD_deploy.prototxt", self.body_proto, "Body Proto")
        
        if not os.path.exists(self.body_model):
            urls = [
                "https://raw.githubusercontent.com/PINTO0309/MobileNet-SSD-RealSense/master/caffemodel/MobileNetSSD/MobileNetSSD_deploy.caffemodel",
                "https://huggingface.co/spaces/Imran606/cds/resolve/main/MobileNetSSD_deploy.caffemodel"
            ]
            for url in urls:
                try:
                    print(f"[DOWNLOAD] Fetching Body Model...")
                    urllib.request.urlretrieve(url, self.body_model)
                    print(f"[DOWNLOAD] Body Model OK")
                    break
                except Exception as e:
                    print(f"[DOWNLOAD WARN] {e}, trying next URL...")

    def change_camera(self, new_source):
        if self.cap.isOpened():
            self.cap.release()
        if isinstance(new_source, str) and new_source.isdigit():
            new_source = int(new_source)
        self.camera_source = new_source
        self.cap = cv2.VideoCapture(new_source)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def get_frame(self, ai_active=True, scan_mode="energy"):
        if not self.cap.isOpened():
            return None, False
            
        ret, frame = self.cap.read()
        if not ret:
            return None, False
            
        if isinstance(self.camera_source, str):
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            
        h, w = frame.shape[:2]
        
        if not ai_active:
            self.presence_timer = 0
            self._last_timer_val = 0
            self.last_presence_time = time.time()
            final_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(final_rgb), False
            
        if scan_mode == "energy":
            blob_body = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
            self.body_net.setInput(blob_body)
            body_detections = self.body_net.forward()
            
            human_found_now = False
            for i in range(body_detections.shape[2]):
                confidence = body_detections[0, 0, i, 2]
                class_id = int(body_detections[0, 0, i, 1])
                if class_id == 15 and confidence > 0.40:
                    box = body_detections[0, 0, i, 3:7] * [w, h, w, h]
                    (startX, startY, endX, endY) = box.astype("int")
                    cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 255), 2, cv2.LINE_AA)
                    cv2.putText(frame, f"Human Body: {int(confidence*100)}%", (startX, startY-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
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
                        cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2, cv2.LINE_AA)
                        cv2.putText(frame, f"Face Target: {int(confidence*100)}%", (startX, startY-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)
                        human_found_now = True
                        
            if not hasattr(self, 'last_presence_time'):
                self.last_presence_time = time.time()
                self._last_timer_val = self.presence_timer
                
            if self.presence_timer != self._last_timer_val:
                self.last_presence_time = time.time() - (5.0 - (self.presence_timer / 30.0))

            if human_found_now:
                self.last_presence_time = time.time()
                self.presence_timer = 150.0
            else:
                elapsed = time.time() - self.last_presence_time
                self.presence_timer = max(0.0, (5.0 - elapsed) * 30.0)
                
            self._last_timer_val = self.presence_timer
            
            # Visual feedback: green border glow when human detected
            if human_found_now:
                cv2.rectangle(frame, (2, 2), (w-2, h-2), (16, 185, 129), 3, cv2.LINE_AA)
                # Confidence badge in top-right corner
                badge_text = "HUMAN DETECTED"
                badge_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
                badge_x = w - badge_size[0] - 15
                overlay_badge = frame.copy()
                cv2.rectangle(overlay_badge, (badge_x - 8, 8), (w - 8, 35), (16, 185, 129), -1)
                cv2.addWeighted(overlay_badge, 0.7, frame, 0.3, 0, frame)
                cv2.putText(frame, badge_text, (badge_x, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            
            # Progress bar at the bottom showing countdown
            if self.presence_timer > 0 and self.presence_timer < self.MAX_TIMER:
                bar_ratio = self.presence_timer / self.MAX_TIMER
                bar_h = 6
                bar_y = h - bar_h
                bar_filled_w = int(w * bar_ratio)
                # Background bar
                cv2.rectangle(frame, (0, bar_y), (w, h), (30, 40, 55), -1)
                # Filled bar - green to orange to red based on ratio
                if bar_ratio > 0.5:
                    bar_color = (16, 185, 129)  # Green
                elif bar_ratio > 0.2:
                    bar_color = (11, 158, 245)  # Orange (BGR)
                else:
                    bar_color = (94, 63, 244)  # Red (BGR)
                cv2.rectangle(frame, (0, bar_y), (bar_filled_w, h), bar_color, -1)

            if not human_found_now:
                sec_left = max(0, int(self.presence_timer / 30))
                alert_text = f"NO HUMAN! SLEEPING IN: {sec_left}s"
                
                overlay = frame.copy()
                card_w, card_h = 360, 50
                card_x1 = (w - card_w) // 2
                card_y1 = h // 2 - card_h // 2
                card_x2 = (w + card_w) // 2
                card_y2 = h // 2 + card_h // 2
                
                cv2.rectangle(overlay, (card_x1, card_y1), (card_x2, card_y2), (10, 15, 26), -1)
                cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
                
                cv2.rectangle(frame, (card_x1, card_y1), (card_x2, card_y2), (0, 229, 255), 1, cv2.LINE_AA)
                
                text_size = cv2.getTextSize(alert_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                text_x = (w - text_size[0]) // 2
                text_y = h // 2 + text_size[1] // 2
                cv2.putText(frame, alert_text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 229, 255), 2, cv2.LINE_AA)
                
        elif scan_mode == "attendance":
            # 1. Ultra-fast live tracker of Core 1 (Zero Lag)
            blob_face = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.face_net.setInput(blob_face)
            face_detections = self.face_net.forward()
            
            current_live_boxes = []
            for i in range(face_detections.shape[2]):
                confidence = face_detections[0, 0, i, 2]
                if confidence > 0.50:
                    box = face_detections[0, 0, i, 3:7] * [w, h, w, h]
                    (startX, startY, endX, endY) = box.astype("int")
                    startX, startY = max(0, startX), max(0, startY)
                    endX, endY = min(w, endX), min(h, endY)
                    if endX - startX > 20 and endY - startY > 20:
                        current_live_boxes.append((startX, startY, endX, endY))
                        
            # 2. Send to Core 2 only for face recognition
            if len(current_live_boxes) > 0 and self.frame_queue.empty():
                small_f = cv2.resize(frame, (640, 480))
                scale_x = 640 / w
                scale_y = 480 / h
                scaled_boxes = [(int(startX*scale_x), int(startY*scale_y), int(endX*scale_x), int(endY*scale_y)) for (startX, startY, endX, endY) in current_live_boxes]
                try: self.frame_queue.put_nowait({'frame': small_f, 'boxes': scaled_boxes})
                except Exception: pass
                
            # 3. Receive results from Core 2
            if not self.result_queue.empty():
                try: self.latest_identified_faces = self.result_queue.get_nowait()
                except Exception: pass
                
            # 4. Map AI names with live boxes
            for live_box in current_live_boxes:
                startX, startY, endX, endY = live_box
                display_name = "Scanning..."
                display_id = ""
                box_color = (0, 255, 255)
                
                live_center_x = (startX + endX) / 2
                live_center_y = (startY + endY) / 2
                
                for id_data in self.latest_identified_faces:
                    c_startX, c_startY, c_endX, c_endY = id_data['box']
                    
                    # Adjust Core 2 scaling
                    orig_c_startX = c_startX * (w / 640)
                    orig_c_endX = c_endX * (w / 640)
                    orig_c_startY = c_startY * (h / 480)
                    orig_c_endY = c_endY * (h / 480)
                    
                    cache_center_x = (orig_c_startX + orig_c_endX) / 2
                    cache_center_y = (orig_c_startY + orig_c_endY) / 2
                    
                    # If live box and AI box are close, set the name
                    if abs(live_center_x - cache_center_x) < 120 and abs(live_center_y - cache_center_y) < 120:
                        display_name = id_data['name']
                        display_id = id_data['id']
                        if display_name != "Unknown":
                            box_color = (255, 215, 0)
                        else:
                            box_color = (0, 0, 255)
                        break
                        
                display_text = f"{display_id} {display_name}" if display_id != "" else display_name
                text_color = (0, 0, 0) if display_name != "Unknown" and display_name != "Scanning..." else (255, 255, 255)
                (text_width, text_height), _ = cv2.getTextSize(display_text, cv2.FONT_HERSHEY_DUPLEX, 0.6, 1)
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