from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import pyqtSignal, QUrl, QTimer, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from config import GOOGLE_MAPS_API_KEY

class MapView(QWebEngineView):
    destination_selected = pyqtSignal(float, float, float, float)

    def __init__(self):
        super().__init__()
        # Stony Brook University coordinates
        self.default_lat = 40.9156
        self.default_lng = -73.1228
        
        # Setup web channel for communication
        self.channel = QWebChannel()
        self.page().setWebChannel(self.channel)
        self.channel.registerObject('mapBridge', self)
        
        # Add a timer to throttle map updates
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.setInterval(100)  # 100ms throttle
        self.update_timer.timeout.connect(self.load_map)
        
        # Initial map load
        self.load_map()
        self.destination_selected_flag = False

    def load_map(self):
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Map</title>
            <script async defer src="https://maps.googleapis.com/maps/api/js?key={GOOGLE_MAPS_API_KEY}&libraries=geometry&callback=initMap"></script>
            <style>
                #map {{ height: 100%; width: 100%; }}
                html, body {{ height: 100%; margin: 0; padding: 0; }}
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map;
                var marker;
                var streetViewService;
                var clickTimeout = null;
                
                async function initMap() {{
                    try {{
                        await loadQWebChannel();
                        
                        map = new google.maps.Map(document.getElementById('map'), {{
                            center: {{lat: {self.default_lat}, lng: {self.default_lng}}},
                            zoom: 15,
                            gestureHandling: 'cooperative'  // Improve scrolling behavior
                        }});

                        streetViewService = new google.maps.StreetViewService();

                        // Throttle click events
                        map.addListener('click', function(e) {{
                            if (clickTimeout) {{
                                clearTimeout(clickTimeout);
                            }}
                            clickTimeout = setTimeout(function() {{
                                findNearestStreetView(e.latLng);
                            }}, 300);  // 300ms debounce
                        }});
                    }} catch (error) {{
                        console.error('Error initializing map:', error);
                    }}
                }}

                function findNearestStreetView(latLng) {{
                    if (window.destinationSelected) {{
                        console.log('Destination already selected');
                        return;
                    }}
                    
                    streetViewService.getPanorama({{
                        location: latLng,
                        radius: 50,
                        source: google.maps.StreetViewSource.OUTDOOR
                    }}, function(data, status) {{
                        if (status === google.maps.StreetViewStatus.OK) {{
                            window.destinationSelected = true;  // Set flag
                            const nearestLatLng = data.location.latLng;
                            requestAnimationFrame(() => {{
                                setDestination(latLng.lat(), latLng.lng(), nearestLatLng.lat(), nearestLatLng.lng());
                            }});
                        }} else {{
                            console.error('Street View not available at this location');
                        }}
                    }});
                }}

                function setDestination(destLat, destLng, streetLat, streetLng) {{
                    // Remove existing marker if any
                    if (marker) {{
                        marker.setMap(null);
                    }}
                    
                    try {{
                        // Create markers using traditional Marker API for now
                        marker = new google.maps.Marker({{
                            map: map,
                            position: {{lat: destLat, lng: destLng}},
                            title: 'Destination'
                        }});

                        // Street view start marker
                        new google.maps.Marker({{
                            map: map,
                            position: {{lat: streetLat, lng: streetLng}},
                            icon: {{
                                path: google.maps.SymbolPath.CIRCLE,
                                scale: 8,
                                fillColor: '#4285F4',
                                fillOpacity: 1,
                                strokeColor: '#ffffff',
                                strokeWeight: 2
                            }},
                            title: 'Street View Start'
                        }});

                        // Draw path from street view to destination
                        new google.maps.Polyline({{
                            path: [
                                {{lat: streetLat, lng: streetLng}},
                                {{lat: destLat, lng: destLng}}
                            ],
                            geodesic: true,
                            strokeColor: '#4285F4',
                            strokeOpacity: 1.0,
                            strokeWeight: 2,
                            map: map
                        }});

                        // Notify Qt using the bridge
                        if (typeof qt !== 'undefined' && qt.webChannelTransport) {{
                            new QWebChannel(qt.webChannelTransport, function(channel) {{
                                if (channel.objects.mapBridge && typeof channel.objects.mapBridge.destinationSelected === 'function') {{
                                    channel.objects.mapBridge.destinationSelected(streetLat, streetLng, destLat, destLng);
                                }} else {{
                                    console.error('Bridge or destinationSelected function not available');
                                }}
                            }});
                        }} else {{
                            console.error('Qt WebChannel not available');
                        }}
                    }} catch (error) {{
                        console.error('Error in setDestination:', error);
                    }}
                }}

                // Add QWebChannel script dynamically and wait for it to load
                function loadQWebChannel() {{
                    return new Promise((resolve, reject) => {{
                        const script = document.createElement('script');
                        script.src = 'qrc:///qtwebchannel/qwebchannel.js';
                        script.onload = resolve;
                        script.onerror = reject;
                        document.head.appendChild(script);
                    }});
                }}
            </script>
        </body>
        </html>
        """
        self.setHtml(html)

    @pyqtSlot(float, float, float, float)
    def destinationSelected(self, streetLat, streetLng, destLat, destLng):
        """Slot to receive destination coordinates from JavaScript"""
        print(f"Destination selected: {streetLat}, {streetLng} to {destLat}, {destLng}")
        self.destination_selected.emit(streetLat, streetLng, destLat, destLng)