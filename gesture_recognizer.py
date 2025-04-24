import cv2
import mediapipe as mp
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

class GestureRecognizer(QThread):
    gesture_detected = pyqtSignal(str)
    frame_ready = pyqtSignal(object)
    status_changed = pyqtSignal(bool)

    def __init__(self, threshold=0.1):  # Lowered threshold from 0.2 to 0.1
        super().__init__()
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False, 
            max_num_hands=1,
            min_detection_confidence=0.3,  # Lowered from 0.5
            min_tracking_confidence=0.3    # Lowered from 0.5
        )
        self.mp_drawing = mp.solutions.drawing_utils
        self.running = True
        self.threshold = threshold
        self.prev_gesture = None
        self.gesture_count = 0
        self.gesture_threshold = 2  # Lowered from 3 to require fewer consistent detections

    def run(self):
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("Error: Could not open camera.")
                self.status_changed.emit(False)
                return

            while self.running:
                success, frame = cap.read()
                if not success:
                    break

                gesture = self.recognize_gesture(frame)
                if gesture and gesture != "NONE":
                    if gesture == self.prev_gesture:
                        self.gesture_count += 1
                    else:
                        self.gesture_count = 1
                    
                    if self.gesture_count >= self.gesture_threshold:
                        self.gesture_detected.emit(gesture)
                        self.gesture_count = 0
                    
                    self.prev_gesture = gesture

                if cv2.waitKey(5) & 0xFF == 27:  # Press 'Esc' to exit
                    break

            cap.release()
            cv2.destroyAllWindows()
            self.status_changed.emit(False)
        except Exception as e:
            print(f"Gesture Recognition Error: {e}")
            self.status_changed.emit(False)

    def stop(self):
        self.running = False

    def recognize_gesture(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.hands.process(rgb_frame)
        
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                self.mp_drawing.draw_landmarks(
                    frame, 
                    hand_landmarks, 
                    self.mp_hands.HAND_CONNECTIONS
                )
                return self.determine_gesture(hand_landmarks)
        
        return "NONE"

    def determine_gesture(self, landmarks):
        def get_landmark_coordinates(landmark):
            return (landmark.x, landmark.y, landmark.z)

        # Get key landmarks
        wrist = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.WRIST])
        thumb_tip = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.THUMB_TIP])
        index_tip = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_TIP])
        middle_tip = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_TIP])
        ring_tip = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.RING_FINGER_TIP])
        pinky_tip = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.PINKY_TIP])

        # Get finger base points for better angle calculation
        index_base = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.INDEX_FINGER_MCP])
        middle_base = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.MIDDLE_FINGER_MCP])
        ring_base = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.RING_FINGER_MCP])
        pinky_base = get_landmark_coordinates(landmarks.landmark[self.mp_hands.HandLandmark.PINKY_MCP])

        # Calculate if fingers are extended with lower threshold
        thumb_open = thumb_tip[1] < wrist[1] - self.threshold
        index_extended = index_tip[1] < index_base[1] - self.threshold * 0.8  # Reduced threshold
        middle_extended = middle_tip[1] < middle_base[1] - self.threshold * 0.8  # Reduced threshold
        ring_extended = ring_tip[1] < ring_base[1] - self.threshold * 0.8  # Reduced threshold
        pinky_extended = pinky_tip[1] < pinky_base[1] - self.threshold * 0.8  # Reduced threshold

        # FORWARD: Index and middle fingers extended, others closed (peace sign)
        if index_extended and middle_extended and not ring_extended and not pinky_extended:
            if index_tip[1] < wrist[1] - self.threshold * 0.8:  # Reduced threshold
                return "FORWARD"

        # BACKWARD: Index and middle fingers pointing down
        if index_tip[1] > index_base[1] + self.threshold * 0.8 and middle_tip[1] > middle_base[1] + self.threshold * 0.8:
            if not ring_extended and not pinky_extended:
                if abs(index_tip[1] - middle_tip[1]) < self.threshold:  # Ensure fingers are roughly aligned
                    return "BACKWARD"

        # Directional controls using thumb position relative to wrist
        # UP: Thumb pointing up
        if thumb_tip[1] < wrist[1] - self.threshold and not any([index_extended, middle_extended, ring_extended, pinky_extended]):
            return "UP"
        
        # DOWN: Thumb pointing down
        if thumb_tip[1] > wrist[1] + self.threshold and not any([index_extended, middle_extended, ring_extended, pinky_extended]):
            return "DOWN"
        
        # LEFT: Thumb pointing left
        if thumb_tip[0] < wrist[0] - self.threshold and not any([index_extended, middle_extended, ring_extended, pinky_extended]):
            return "LEFT"
        
        # RIGHT: Thumb pointing right
        if thumb_tip[0] > wrist[0] + self.threshold and not any([index_extended, middle_extended, ring_extended, pinky_extended]):
            return "RIGHT"

        return "NONE"