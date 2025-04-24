import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QProgressBar, QMessageBox, QLabel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtCore import QUrl, QObject, pyqtSlot, Qt
from config import GOOGLE_MAPS_API_KEY

class StreetViewBridge(QObject):
    def __init__(self, street_view):
        super().__init__()
        self._street_view = street_view  # Store reference to StreetView

    @pyqtSlot(float, float)
    def updatePosition(self, lat, lng):
        print(f"Bridge received position: {lat}, {lng}")

    @pyqtSlot(str)
    def routeStatus(self, status):
        print(f"Route status: {status}")

    @pyqtSlot(str)
    def routeCalculated(self, route_points_json):
        """Called when JavaScript has calculated a new route"""
        import json
        route_points = json.loads(route_points_json)
        self._street_view.current_route = route_points
        self._street_view.current_route_index = 0
        self._street_view.has_active_route = True
        print(f"Route calculated with {len(route_points)} points")

class StreetView(QWebEngineView):
    def __init__(self):
        super().__init__()
        self.default_lat = 40.91439
        self.default_lng = -73.12453
        
        # Route tracking variables
        self.current_route = []
        self.current_route_index = -1
        self.has_active_route = False
        
        # Enable web channel
        self.channel = QWebChannel()
        self.bridge = StreetViewBridge(self)  # Pass self as reference
        self.channel.registerObject('streetViewBridge', self.bridge)
        self.page().setWebChannel(self.channel)
        
        # Load initial view at default location
        self.load_street_view(self.default_lat, self.default_lng)
        
        # Add styled progress bar
        self.progress_container = QWidget(self)
        progress_layout = QVBoxLayout(self.progress_container)
        
        self.progress_label = QLabel("Journey Progress")
        self.progress_label.setStyleSheet("""
            color: #1abc9c;
            font-size: 16px;
            font-weight: bold;
        """)
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% Complete")
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_container.setGeometry(10, 10, 300, 60)
        self.progress_container.hide()

    def load_street_view(self, lat, lng):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Street View</title>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}&libraries=geometry"></script>
            <style>
                html, body {{ height: 100%; margin: 0; padding: 0; }}
                #street-view {{ height: 100%; }}
            </style>
        </head>
        <body>
            <div id="street-view"></div>
            <script>
                let panorama;
                let directionsService;
                let routePoints = [];
                let currentRouteIndex = -1;

                function initStreetView() {{
                    // Initialize services
                    directionsService = new google.maps.DirectionsService();
                    
                    // Initialize panorama
                    panorama = new google.maps.StreetViewPanorama(
                        document.getElementById('street-view'),
                        {{
                            position: {{lat: {lat}, lng: {lng}}},
                            pov: {{ heading: 0, pitch: 0 }},
                            zoom: 1,
                            visible: true
                        }}
                    );

                    // Setup WebChannel
                    new QWebChannel(qt.webChannelTransport, function(channel) {{
                        window.bridge = channel.objects.streetViewBridge;
                    }});
                }}

                function calculateRoute(startLat, startLng, destLat, destLng) {{
                    const start = new google.maps.LatLng(startLat, startLng);
                    const end = new google.maps.LatLng(destLat, destLng);

                    directionsService.route(
                        {{
                            origin: start,
                            destination: end,
                            travelMode: google.maps.TravelMode.WALKING
                        }},
                        function(response, status) {{
                            if (status === 'OK') {{
                                routePoints = [];
                                const route = response.routes[0];
                                
                                route.legs[0].steps.forEach(step => {{
                                    routePoints.push(step.start_location);
                                    step.path.forEach(point => {{
                                        routePoints.push(point);
                                    }});
                                }});
                                routePoints.push(route.legs[0].end_location);
                                
                                currentRouteIndex = 0;
                                
                                // Send route to Python but don't move yet
                                if (window.bridge) {{
                                    window.bridge.routeCalculated(JSON.stringify(
                                        routePoints.map(p => [p.lat(), p.lng()])
                                    ));
                                }}
                            }}
                        }}
                    );
                }}

                function moveToRoutePoint(index) {{
                    if (index >= 0 && index < routePoints.length) {{
                        const point = routePoints[index];
                        let heading = panorama.getPov().heading;
                        
                        if (index < routePoints.length - 1) {{
                            heading = google.maps.geometry.spherical.computeHeading(
                                point,
                                routePoints[index + 1]
                            );
                        }}
                        
                        panorama.setPosition(point);
                        panorama.setPov({{
                            heading: heading,
                            pitch: 0
                        }});
                        
                        currentRouteIndex = index;
                        return true;
                    }}
                    return false;
                }}

                // Initialize when page loads
                window.onload = initStreetView;
            </script>
        </body>
        </html>
        """
        self.setHtml(html)

    def calculate_route(self, streetLat, streetLng, destLat, destLng):
        """Calculate route between two points but stay at current position"""
        # Reset route tracking
        self.current_route = []
        self.current_route_index = -1
        self.has_active_route = False
        
        # Calculate route from current position to destination
        js_code = f"""
        if (panorama) {{
            // Store current position
            let currentPosition = panorama.getPosition();
            let currentPov = panorama.getPov();
            
            // Calculate route
            calculateRoute({self.default_lat}, {self.default_lng}, {destLat}, {destLng});
            
            // Return to original position after route calculation
            panorama.setPosition(new google.maps.LatLng({self.default_lat}, {self.default_lng}));
            panorama.setPov(currentPov);
        }}
        """
        self.page().runJavaScript(js_code)
        self.progress_bar.show()
        self.progress_bar.setValue(0)

    def move_forward(self):
        """Move forward along the street or route"""
        if self.has_active_route:
            if self.current_route_index < len(self.current_route) - 1:
                self.current_route_index += 1
                progress = int((self.current_route_index / (len(self.current_route) - 1)) * 100)
                self.progress_bar.setValue(progress)
                
                # Check if destination reached
                if self.current_route_index == len(self.current_route) - 1:
                    self.show_destination_reached()
                    
                lat, lng = self.current_route[self.current_route_index]
                js_code = f"""
                if (panorama) {{
                    let point = new google.maps.LatLng({lat}, {lng});
                    let nextPoint = null;
                    
                    // Calculate heading towards next point if available
                    if ({self.current_route_index} < {len(self.current_route) - 1}) {{
                        let nextLat = {self.current_route[self.current_route_index + 1][0]};
                        let nextLng = {self.current_route[self.current_route_index + 1][1]};
                        nextPoint = new google.maps.LatLng(nextLat, nextLng);
                    }}
                    
                    // Get current heading for smooth transition
                    let currentPov = panorama.getPov();
                    let newHeading = currentPov.heading;
                    
                    if (nextPoint) {{
                        newHeading = google.maps.geometry.spherical.computeHeading(point, nextPoint);
                    }}
                    
                    panorama.setPosition(point);
                    panorama.setPov({{
                        heading: newHeading,
                        pitch: currentPov.pitch
                    }});
                }}
                """
                self.page().runJavaScript(js_code)
                print(f"Moving forward to point {self.current_route_index}/{len(self.current_route)-1}")
        else:
            js_code = """
            if (panorama) {
                let position = panorama.getPosition();
                let pov = panorama.getPov();
                let heading = pov.heading;
                
                // Calculate new position ~10 meters forward in current heading direction
                let latLng = google.maps.geometry.spherical.computeOffset(
                    position,
                    10,  // meters
                    heading
                );
                
                // Create a Street View Service
                let sv = new google.maps.StreetViewService();
                
                // Find nearest panorama
                sv.getPanorama({
                    location: latLng,
                    radius: 50,
                    preference: google.maps.StreetViewPreference.NEAREST
                }, function(data, status) {
                    if (status === 'OK') {
                        panorama.setPosition(data.location.latLng);
                    }
                });
            }
            """
            self.page().runJavaScript(js_code)

    def move_backward(self):
        """Move backward along the street or route"""
        if self.has_active_route:
            if self.current_route_index > 0:
                self.current_route_index -= 1
                progress = int((self.current_route_index / (len(self.current_route) - 1)) * 100)
                self.progress_bar.setValue(progress)
                
                lat, lng = self.current_route[self.current_route_index]
                js_code = f"""
                if (panorama) {{
                    let point = new google.maps.LatLng({lat}, {lng});
                    let nextPoint = null;
                    
                    // Calculate heading towards next point if available
                    if ({self.current_route_index} > 0) {{
                        let nextLat = {self.current_route[self.current_route_index - 1][0]};
                        let nextLng = {self.current_route[self.current_route_index - 1][1]};
                        nextPoint = new google.maps.LatLng(nextLat, nextLng);
                    }}
                    
                    // Get current heading for smooth transition
                    let currentPov = panorama.getPov();
                    let newHeading = currentPov.heading;
                    
                    if (nextPoint) {{
                        newHeading = google.maps.geometry.spherical.computeHeading(point, nextPoint);
                    }}
                    
                    panorama.setPosition(point);
                    panorama.setPov({{
                        heading: newHeading,
                        pitch: currentPov.pitch
                    }});
                }}
                """
                self.page().runJavaScript(js_code)
                print(f"Moving backward to point {self.current_route_index}/{len(self.current_route)-1}")
        else:
            js_code = """
            if (panorama) {
                let position = panorama.getPosition();
                let pov = panorama.getPov();
                let heading = pov.heading;
                
                // Calculate new position ~10 meters backward (opposite of heading)
                let latLng = google.maps.geometry.spherical.computeOffset(
                    position,
                    10,  // meters
                    (heading + 180) % 360  // Opposite direction
                );
                
                // Create a Street View Service
                let sv = new google.maps.StreetViewService();
                
                // Find nearest panorama
                sv.getPanorama({
                    location: latLng,
                    radius: 50,
                    preference: google.maps.StreetViewPreference.NEAREST
                }, function(data, status) {
                    if (status === 'OK') {
                        panorama.setPosition(data.location.latLng);
                    }
                });
            }
            """
            self.page().runJavaScript(js_code)

    def set_position(self, lat, lng, is_destination=False):
        """Set the street view position - only if not a destination"""
        if not is_destination:  # Only move if this isn't a destination point
            js_code = f"""
            if (panorama) {{
                panorama.setPosition(new google.maps.LatLng({lat}, {lng}));
            }}
            """
            self.page().runJavaScript(js_code)

    def move_up(self):
        """Adjust the camera pitch upward with smooth animation"""
        js_code = """
        if (panorama) {
            let pov = panorama.getPov();
            let targetPitch = Math.min(pov.pitch + 10, 90);
            
            // Animate the transition
            let steps = 10;  // Number of animation steps
            let pitchStep = (targetPitch - pov.pitch) / steps;
            let currentStep = 0;
            
            function animate() {
                if (currentStep < steps) {
                    pov.pitch += pitchStep;
                    panorama.setPov({
                        heading: pov.heading,
                        pitch: pov.pitch
                    });
                    currentStep++;
                    requestAnimationFrame(animate);
                }
            }
            
            animate();
        }
        """
        self.page().runJavaScript(js_code)

    def move_down(self):
        """Adjust the camera pitch downward with smooth animation"""
        js_code = """
        if (panorama) {
            let pov = panorama.getPov();
            let targetPitch = Math.max(pov.pitch - 10, -90);
            
            // Animate the transition
            let steps = 10;  // Number of animation steps
            let pitchStep = (targetPitch - pov.pitch) / steps;
            let currentStep = 0;
            
            function animate() {
                if (currentStep < steps) {
                    pov.pitch += pitchStep;
                    panorama.setPov({
                        heading: pov.heading,
                        pitch: pov.pitch
                    });
                    currentStep++;
                    requestAnimationFrame(animate);
                }
            }
            
            animate();
        }
        """
        self.page().runJavaScript(js_code)

    def move_left(self):
        """Rotate the camera view left with smooth animation"""
        js_code = """
        if (panorama) {
            let pov = panorama.getPov();
            let targetHeading = (pov.heading - 10 + 360) % 360;
            
            // Animate the transition
            let steps = 10;  // Number of animation steps
            let headingStep = ((targetHeading - pov.heading + 180) % 360 - 180) / steps;
            let currentStep = 0;
            
            function animate() {
                if (currentStep < steps) {
                    pov.heading = (pov.heading + headingStep + 360) % 360;
                    panorama.setPov({
                        heading: pov.heading,
                        pitch: pov.pitch
                    });
                    currentStep++;
                    requestAnimationFrame(animate);
                }
            }
            
            animate();
        }
        """
        self.page().runJavaScript(js_code)

    def move_right(self):
        """Rotate the camera view right with smooth animation"""
        js_code = """
        if (panorama) {
            let pov = panorama.getPov();
            let targetHeading = (pov.heading + 10) % 360;
            
            // Animate the transition
            let steps = 10;  // Number of animation steps
            let headingStep = ((targetHeading - pov.heading + 180) % 360 - 180) / steps;
            let currentStep = 0;
            
            function animate() {
                if (currentStep < steps) {
                    pov.heading = (pov.heading + headingStep + 360) % 360;
                    panorama.setPov({
                        heading: pov.heading,
                        pitch: pov.pitch
                    });
                    currentStep++;
                    requestAnimationFrame(animate);
                }
            }
            
            animate();
        }
        """
        self.page().runJavaScript(js_code)

    def show_destination_reached(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Destination Reached")
        msg.setText("""
            <div style="text-align: center;">
                <h3 style="color: #1abc9c;">🎉 You've Arrived! 🎉</h3>
                <p style="color: #ecf0f1;">You have successfully reached your destination.</p>
            </div>
        """)
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