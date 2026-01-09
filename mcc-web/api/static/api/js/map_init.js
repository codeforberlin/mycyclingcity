// Create this file at: mcc/api/static/api/js/map_init.js

(function($) {
    // Only execute the code once the document is fully loaded
    $(document).ready(function() {
        const mapContainer = document.getElementById('leaflet_map');
        
        // Check if the map div exists (only present on the edit page)
        if (!mapContainer) {
            return;
        }

        const latInput = document.getElementById('id_lat');
        const lonInput = document.getElementById('id_lon');

        // Default view (e.g., Berlin, if no values present)
        const defaultLat = 52.52;
        const defaultLon = 13.40;
        const defaultZoom = 10;

        // Current values or defaults
        const initialLat = parseFloat(latInput.value) || defaultLat;
        const initialLon = parseFloat(lonInput.value) || defaultLon;
        
        // 1. Initialize map
        const map = L.map('leaflet_map').setView([initialLat, initialLon], defaultZoom);

        // Add OSM layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        // 2. Create marker and set to draggable
        const marker = L.marker([initialLat, initialLon], {
            draggable: true
        }).addTo(map);

        // Function to update input fields
        function updateFields(latlng) {
            latInput.value = latlng.lat.toFixed(6);  // 6 decimal places
            lonInput.value = latlng.lng.toFixed(6);
        }

        // Set current values on load
        updateFields(marker.getLatLng());


        // 3. Marker drag event
        marker.on('dragend', function(e) {
            updateFields(marker.getLatLng());
        });
        
        // 4. Map click event
        map.on('click', function(e) {
            marker.setLatLng(e.latlng);
            updateFields(e.latlng);
        });

        // 5. When input field values change, move marker (useful for manual entry)
        $(latInput).on('change', function() {
            const newLat = parseFloat(latInput.value);
            const newLon = parseFloat(lonInput.value);
            if (!isNaN(newLat) && !isNaN(newLon)) {
                marker.setLatLng([newLat, newLon]);
                map.setView([newLat, newLon], map.getZoom());
            }
        });
        
        $(lonInput).on('change', function() {
             // It's sufficient to only implement the latInput change handler,
             // since it checks both fields and updates the view.
             $(latInput).trigger('change');
        });

    });
})(django.jQuery);