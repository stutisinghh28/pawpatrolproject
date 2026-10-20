/**
 * PawPatrol Mapping Module
 * Uses OpenStreetMap via Leaflet.js (free, open-source, no API keys required)
 */

const MapModule = {
  pickerMap: null,
  pickerMarker: null,
  dashboardMap: null,
  dashboardMarkersLayer: null,

  defaultCenter: [28.6139, 77.2090], // Default center (can be customized)
  defaultZoom: 13,

  // Initialize interactive location picker on the Report Form
  initPicker(containerId, onLocationSelected) {
    const container = document.getElementById(containerId);
    if (!container || this.pickerMap) return;

    this.pickerMap = L.map(containerId).setView(this.defaultCenter, this.defaultZoom);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.pickerMap);

    this.pickerMarker = L.marker(this.defaultCenter, { draggable: true }).addTo(this.pickerMap);

    this.pickerMarker.on('dragend', (e) => {
      const pos = e.target.getLatLng();
      if (onLocationSelected) onLocationSelected(pos.lat, pos.lng);
    });

    this.pickerMap.on('click', (e) => {
      this.pickerMarker.setLatLng(e.latlng);
      if (onLocationSelected) onLocationSelected(e.latlng.lat, e.latlng.lng);
    });
  },

  // Set the location picker marker position
  setPickerLocation(lat, lng) {
    if (!this.pickerMap || !this.pickerMarker) return;
    const latLng = [lat, lng];
    this.pickerMarker.setLatLng(latLng);
    this.pickerMap.setView(latLng, 16);
  },

  // Try HTML5 Browser Geolocation
  getUserLocation(onSuccess, onError) {
    if (!navigator.geolocation) {
      if (onError) onError('Geolocation is not supported by your browser');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        if (onSuccess) onSuccess(lat, lng);
      },
      (err) => {
        if (onError) onError(err.message || 'Unable to retrieve location');
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  },

  // Initialize the full interactive Dashboard Map
  initDashboardMap(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (this.dashboardMap) {
      this.dashboardMap.invalidateSize();
      return;
    }

    this.dashboardMap = L.map(containerId).setView(this.defaultCenter, 12);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.dashboardMap);

    this.dashboardMarkersLayer = L.layerGroup().addTo(this.dashboardMap);
  },

  // Plot reports onto the Dashboard map
  plotReports(reports) {
    if (!this.dashboardMap || !this.dashboardMarkersLayer) return;

    this.dashboardMarkersLayer.clearLayers();
    const bounds = [];

    reports.forEach((rep) => {
      if (rep.latitude && rep.longitude) {
        const lat = parseFloat(rep.latitude);
        const lng = parseFloat(rep.longitude);

        if (!isNaN(lat) && !isNaN(lng)) {
          bounds.push([lat, lng]);

          // Marker color based on risk level
          const colorMap = {
            'CRITICAL': '#ef4444',
            'HIGH': '#f97316',
            'MEDIUM': '#eab308',
            'LOW': '#10b981'
          };
          const color = colorMap[rep.risk_level] || '#2563eb';

          const markerIcon = L.divIcon({
            className: 'custom-map-pin',
            html: `<div style="
              background-color: ${color};
              width: 26px;
              height: 26px;
              border-radius: 50%;
              border: 3px solid #ffffff;
              box-shadow: 0 2px 5px rgba(0,0,0,0.3);
              display: flex;
              align-items: center;
              justify-content: center;
              color: #ffffff;
              font-size: 13px;
              font-weight: bold;
            ">🐾</div>`,
            iconSize: [26, 26],
            iconAnchor: [13, 13]
          });

          const marker = L.marker([lat, lng], { icon: markerIcon });
          
          const popupContent = `
            <div style="min-width: 180px; font-family: system-ui, sans-serif;">
              <div style="font-size: 11px; font-weight: bold; color: ${color}; text-transform: uppercase;">
                ${rep.risk_level || 'UNKNOWN'} RISK
              </div>
              <div style="font-weight: 700; font-size: 14px; margin: 2px 0;">
                ${rep.animal_type || 'Animal'} Rescue
              </div>
              <div style="font-size: 12px; color: #475569; margin-bottom: 6px;">
                ${rep.location_address || 'Location provided'}
              </div>
              <div style="font-size: 11px; margin-bottom: 6px;">
                <strong>Status:</strong> ${rep.status || 'REPORTED'}
              </div>
              <button onclick="window.viewReportModal('${rep.report_id}')" style="
                background: #2563eb;
                color: #ffffff;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                cursor: pointer;
                width: 100%;
              ">View Full Details</button>
            </div>
          `;

          marker.bindPopup(popupContent);
          this.dashboardMarkersLayer.addLayer(marker);
        }
      }
    });

    if (bounds.length > 0) {
      this.dashboardMap.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
    }
  }
};

window.MapModule = MapModule;
