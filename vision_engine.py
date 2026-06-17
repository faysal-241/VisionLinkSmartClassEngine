import cv2
import os
import urllib.request
import numpy as np
from PIL import Image
import multiprocessing
import time
import face_recognition

print("[SYSTEM] Loading Pure Human Structure AI Engine (Enterprise Hybrid Tracker)...")

# ==============================================================================
# 🧠 THE DEEP AI BRAIN (Runs on Core 2 - Heavy Identity Scanner)
# ==============================================================================
def ai_worker_core(frame_queue, result_queue, known_encodings, known_names, known_ids):
    while True:
        if frame_queue.empty():
            time.sleep(0.01)
            continue

        # Core 1 থেকে ছোট ভিডিও ফ্রেম এবং বক্সগুলো গ্রহণ করা
        data = frame_queue.get()
        frame = data['frame']
        live_boxes = data['boxes']
        
        if len(live_boxes) > 0:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # face_recognition লাইব্রেরির জন্য বক্সগুলোর স্টাইল ঠিক করা (Top, Right, Bottom, Left)
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
                    except: pass
                result_queue.put(results)
            except Exception:
                pass

# ==============================================================================
# 📷 THE LIVE TRACKER CORE (Runs on Core 1 - Super Fast 60FPS Tracker)
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
        
        # 2টি Core-এর মধ্যে ডেটা আদান-প্রদানের জন্য পাইপ
        self.frame_queue = multiprocessing.Queue(maxsize=1)
        self.result_queue = multiprocessing.Queue(maxsize=1)
        
        # Core 2 (AI Brain) চালু করা হলো
        self.ai_process = multiprocessing.Process(
            target=ai_worker_core,
            args=(self.frame_queue, self.result_queue, self.known_face_encodings, self.known_face_names, self.known_face_ids),
            daemon=True
        )
        self.ai_process.start()
        
        self.latest_identified_faces = []
        self.presence_timer = 0
        self.MAX_TIMER = 90
        print("[SUCCESS] Enterprise Hybrid Tracker Ready!")

    def load_known_faces(self):
        folder_path = "known_faces"
        print("[INFO] Loading Known Faces from folder...")
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
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
                    self.known_face_encodings.append(encodings[0])
                    self.known_face_names.append(student_name)
                    self.known_face_ids.append(student_id)
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

    def change_camera(self, new_source):
        if self.cap.isOpened():
            self.cap.release()
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
            # ১. Core 1-এর অত্যন্ত ফাস্ট লাইভ ট্র্যাকার (Zero Lag)
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

            # ২. Core 2-কে শুধু চেহারা চেনার জন্য পাঠানো
            if len(current_live_boxes) > 0 and self.frame_queue.empty():
                small_f = cv2.resize(frame, (640, 480))
                scale_x = 640 / w
                scale_y = 480 / h
                scaled_boxes = [(int(startX*scale_x), int(startY*scale_y), int(endX*scale_x), int(endY*scale_y)) for (startX, startY, endX, endY) in current_live_boxes]
                try: self.frame_queue.put_nowait({'frame': small_f, 'boxes': scaled_boxes})
                except: pass

            # ৩. Core 2 থেকে রেজাল্ট রিসিভ করা
            if not self.result_queue.empty():
                try: self.latest_identified_faces = self.result_queue.get_nowait()
                except: pass

            # ৪. লাইভ বক্সের সাথে এআই-এর নাম জোড়া লাগানো
            for live_box in current_live_boxes:
                startX, startY, endX, endY = live_box
                display_name = "Scanning..."
                display_id = ""
                box_color = (0, 255, 255)
                
                live_center_x = (startX + endX) / 2
                live_center_y = (startY + endY) / 2
                
                for id_data in self.latest_identified_faces:
                    c_startX, c_startY, c_endX, c_endY = id_data['box']
                    
                    # Core 2-এর স্কেল ঠিক করা
                    orig_c_startX = c_startX * (w / 640)
                    orig_c_endX = c_endX * (w / 640)
                    orig_c_startY = c_startY * (h / 480)
                    orig_c_endY = c_endY * (h / 480)
                    
                    cache_center_x = (orig_c_startX + orig_c_endX) / 2
                    cache_center_y = (orig_c_startY + orig_c_endY) / 2
                    
                    # যদি লাইভ বক্স এবং এআই বক্স কাছাকাছি হয়, তবে নাম সেট হবে
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