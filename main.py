import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QSplitter, QLabel, QHBoxLayout, QMessageBox
from PyQt5.QtCore import Qt, QObject, pyqtSlot, QTimer, QThread
from PyQt5.QtGui import QImage, QPixmap
from map_view import MapView
from street_view import StreetView
from gesture_recognizer import GestureRecognizer
from config import WINDOW_TITLE, WINDOW_SIZE
import cv2
import queue
import time
from styles import MAIN_STYLE, WELCOME_MESSAGE

class CameraThread(QThread):
    def __init__(self, frame_queue):
        super().__init__()
        self.frame_queue = frame_queue
        self.running = True
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise RuntimeError("Could not open camera")
        
    def run(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                if self.frame_queue.qsize() < 2:  # Prevent queue from growing too large
                    self.frame_queue.put(frame)
            time.sleep(0.01)  # Small sleep to prevent thread from hogging CPU
            
    def stop(self):
        self.running = False
        self.cap.release()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setGeometry(100, 100, *WINDOW_SIZE)
        self.setStyleSheet(MAIN_STYLE)

        # Show welcome message
        self.show_welcome_message()

        # Initialize frame queue and camera thread
        self.frame_queue = queue.Queue(maxsize=2)
        self.camera_thread = CameraThread(self.frame_queue)
        self.camera_thread.start()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Left side - Map and Street View (70%)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(15)
        
        # Add title
        title_label = QLabel("Virtual Street Explorer")
        title_label.setProperty('class', 'title-label')
        title_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title_label)

        # Map and Street View splitter
        splitter = QSplitter(Qt.Vertical)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1abc9c;
                height: 2px;
            }
        """)
        
        # Create splitter for map and street view
        self.map_view = MapView()
        splitter.addWidget(self.map_view)
        self.street_view = StreetView()
        splitter.addWidget(self.street_view)
        
        # Connect map view to street view
        self.map_view.destination_selected.connect(
            lambda streetLat, streetLng, destLat, destLng: 
            self.street_view.calculate_route(streetLat, streetLng, destLat, destLng)
        )

        left_layout.addWidget(splitter)
        main_layout.addWidget(left_widget)

        # Right side - Controls and Info (30%)
        right_widget = QWidget()
        right_widget.setProperty('class', 'info-panel')
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(15)

        # Gesture view with title
        gesture_container = QWidget()
        gesture_container.setProperty('class', 'gesture-view')
        gesture_layout = QVBoxLayout(gesture_container)
        
        gesture_title = QLabel("Hand Gesture Tracking")
        gesture_title.setAlignment(Qt.AlignCenter)
        gesture_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1abc9c;")
        gesture_layout.addWidget(gesture_title)
        
        self.gesture_view = QLabel()  # Replace with actual class
        self.gesture_view.setFixedSize(320, 240)
        gesture_layout.addWidget(self.gesture_view, alignment=Qt.AlignCenter)
        
        right_layout.addWidget(gesture_container)

        # Current gesture indicator
        self.current_gesture_label = QLabel("Current Gesture: None")
        self.current_gesture_label.setProperty('class', 'current-gesture')
        self.current_gesture_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.current_gesture_label)

        # Updated gesture controls legend
        legend_label = QLabel(
            """<div style="background-color: rgba(26, 188, 156, 0.1); padding: 20px; border-radius: 10px;">
                <h3 style="color: #1abc9c; margin-bottom: 15px;">Gesture Controls</h3>
                <div style="color: #ecf0f1; line-height: 1.8;">
                    <p><b>Navigation:</b></p>
                    <p> Two fingers up → Move Forward</p>
                    <p> Two fingers down → Move Backward</p>
                    <p><b>View Control:</b></p>
                    <p>👍 Thumb up → Look Up</p>
                    <p>👎 Thumb down → Look Down</p>
                    <p>👈 Thumb left → Turn Left</p>
                    <p>👉 Thumb right → Turn Right</p>
                </div>
            </div>"""
        )
        right_layout.addWidget(legend_label)

        main_layout.addWidget(right_widget)

        # Setup gesture recognizer with debouncing
        self.gesture_recognizer = GestureRecognizer()
        self.gesture_recognizer.gesture_detected.connect(self.handle_gesture)
        self.last_gesture_time = 0
        self.gesture_cooldown = 0.5  # Seconds between gesture processing
        
        # Setup timer for continuous camera feed updates with reduced frequency
        self.camera_timer = QTimer()
        self.camera_timer.timeout.connect(self.update_camera_feed)
        self.camera_timer.start(50)  # Update every 50ms (20 fps) instead of 33ms

    def update_camera_feed(self):
        try:
            if self.frame_queue.empty():
                return

            frame = self.frame_queue.get_nowait()
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channel = rgb_frame.shape
            bytes_per_line = 3 * width

            # Process frame and update gesture view
            processed_frame = rgb_frame.copy()
            
            # Only process gestures if enough time has passed
            current_time = time.time()
            if current_time - self.last_gesture_time >= self.gesture_cooldown:
                if hasattr(self.gesture_recognizer, 'hands') and self.gesture_recognizer.hands:
                    results = self.gesture_recognizer.hands.process(rgb_frame)
                    if results.multi_hand_landmarks:
                        for hand_landmarks in results.multi_hand_landmarks:
                            self.gesture_recognizer.mp_drawing.draw_landmarks(
                                processed_frame,
                                hand_landmarks,
                                self.gesture_recognizer.mp_hands.HAND_CONNECTIONS
                            )
                            gesture = self.gesture_recognizer.determine_gesture(hand_landmarks)
                            if gesture != "NONE":
                                self.handle_gesture(gesture)
                                self.last_gesture_time = current_time

            # Convert and display the processed frame
            processed_q_image = QImage(processed_frame.data, width, height, bytes_per_line, QImage.Format_RGB888)
            processed_pixmap = QPixmap.fromImage(processed_q_image)
            scaled_processed_pixmap = processed_pixmap.scaled(240, 180, Qt.KeepAspectRatio, Qt.FastTransformation)
            self.gesture_view.setPixmap(scaled_processed_pixmap)
            
        except queue.Empty:
            pass
        except Exception as e:
            print(f"Error in camera feed update: {str(e)}")

    def on_destination_selected(self, lat, lng):
        print(f"Destination selected: {lat}, {lng}")
        self.street_view.set_position(lat, lng, is_destination=True)

    def handle_gesture(self, gesture):
        print(f"Gesture detected: {gesture}")
        self.current_gesture_label.setText(f"Current Gesture: {gesture}")
        
        gesture_actions = {
            "FORWARD": self.street_view.move_forward,
            "BACKWARD": self.street_view.move_backward,
            "UP": self.street_view.move_up,
            "DOWN": self.street_view.move_down,
            "LEFT": self.street_view.move_left,
            "RIGHT": self.street_view.move_right
        }
        
        if gesture in gesture_actions:
            gesture_actions[gesture]()

    def closeEvent(self, event):
        print("Closing application...")
        self.camera_timer.stop()
        
        # Stop and clean up camera thread
        if hasattr(self, 'camera_thread'):
            self.camera_thread.stop()
            self.camera_thread.wait()
            print("Camera thread stopped")
            
        # Stop gesture recognizer
        self.gesture_recognizer.stop()
        self.gesture_recognizer.wait()
        print("Gesture recognizer stopped")
        super().closeEvent(event)

    def show_welcome_message(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Welcome")
        msg.setText(WELCOME_MESSAGE)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #2c3e50;
            }
            QPushButton {
                background-color: #1abc9c;
                border: none;
                color: white;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #16a085;
            }
        """)
        msg.exec_()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())