// SafeRide AI Leaflet Interactive Live Bus Tracker

class BusTrackerMap {
    constructor(mapContainerId, initialLat = 19.0760, initialLng = 72.8777, zoom = 13) {
        this.map = L.map(mapContainerId).setView([initialLat, initialLng], zoom);
        
        // High quality crisp tile layer
        L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; SafeRide AI | OpenStreetMap',
            maxZoom: 19
        }).addTo(this.map);

        this.busMarkers = {};
        this.stopMarkers = [];
        this.childMarker = null;
        this.routePolyline = null;
    }

    renderRoute(stops) {
        if (!stops || stops.length === 0) return;

        // Clear existing markers
        this.stopMarkers.forEach(m => this.map.removeLayer(m));
        this.stopMarkers = [];
        if (this.routePolyline) this.map.removeLayer(this.routePolyline);

        const latLngs = [];
        stops.forEach(s => {
            const point = [s.lat, s.lng];
            latLngs.push(point);

            let stopBg = '#2563eb';
            let labelPrefix = '';
            if (s.is_child_pickup) {
                stopBg = '#10b981';
                labelPrefix = '📍 [Child Pickup] ';
            } else if (s.is_child_drop) {
                stopBg = '#8b5cf6';
                labelPrefix = '🏠 [Child Drop] ';
            }

            // Custom Stop Icon
            const stopIcon = L.divIcon({
                className: 'custom-stop-pin',
                html: `<div style="background:${stopBg}; color:#ffffff; border-radius:50%; width:28px; height:28px; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:12px; border:2px solid #ffffff; box-shadow:0 2px 6px rgba(0,0,0,0.25);">${s.sequence}</div>`,
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });

            const marker = L.marker(point, { icon: stopIcon }).addTo(this.map);
            marker.bindPopup(`
                <div style="font-family:sans-serif;">
                    <b style="color:${stopBg};">${labelPrefix}Stop ${s.sequence}: ${s.name}</b><br>
                    <small>Pickup: ${s.pickup_time || 'N/A'} | Drop: ${s.drop_time || 'N/A'}</small>
                </div>
            `);
            this.stopMarkers.push(marker);
        });

        // Draw Route Polyline
        this.routePolyline = L.polyline(latLngs, {
            color: '#2563eb',
            weight: 5,
            opacity: 0.85,
            dashArray: '8, 8'
        }).addTo(this.map);

        this.map.fitBounds(this.routePolyline.getBounds(), { padding: [40, 40] });
    }

    updateBusLocation(busId, busCode, lat, lng, speed = 0, status = 'ACTIVE', isStale = false, lastUpdatedText = '', isActive = true) {
        if (!isActive || lat === null || lng === null || status === 'INACTIVE' || status === 'WAITING_GPS') {
            if (this.busMarkers[busId]) {
                this.map.removeLayer(this.busMarkers[busId]);
                delete this.busMarkers[busId];
            }
            return;
        }

        const point = [lat, lng];

        let bgStyle = '#059669';
        let statusBadgeText = `🚌 ${busCode}`;
        if (isStale) {
            bgStyle = '#6b7280';
            statusBadgeText = `⚠️ ${busCode} (${lastUpdatedText || 'Stale'})`;
        }

        const busIconHtml = `
            <div style="background:${bgStyle}; color:#ffffff; border-radius:8px; padding:4px 8px; font-weight:700; font-size:11px; display:flex; align-items:center; gap:4px; border:2px solid #ffffff; box-shadow:0 2px 8px rgba(0,0,0,0.4);">
                ${statusBadgeText}
            </div>
        `;

        const busIcon = L.divIcon({
            className: 'custom-bus-marker',
            html: busIconHtml,
            iconSize: [isStale ? 160 : 70, 30],
            iconAnchor: [isStale ? 80 : 35, 15]
        });

        if (this.busMarkers[busId]) {
            this.busMarkers[busId].setLatLng(point);
            this.busMarkers[busId].setIcon(busIcon);
        } else {
            const marker = L.marker(point, { icon: busIcon }).addTo(this.map);
            marker.bindPopup(`
                <div style="font-family:sans-serif;">
                    <b>Bus ${busCode}</b><br>
                    Status: <span class="badge ${isStale ? 'bg-secondary' : 'bg-success'}">${isStale ? 'STALE GPS' : status}</span><br>
                    Current Speed: ${speed} km/h<br>
                    ${isStale ? `<span style="color:#ef4444; font-weight:bold;">⚠️ Signal Stale (${lastUpdatedText})</span>` : ''}
                </div>
            `);
            this.busMarkers[busId] = marker;
        }

        this.map.panTo(point);
    }

    updateChildLocation(childName, lat, lng, status, statusLabel) {
        if (!lat || !lng) return;
        const point = [lat, lng];
        let badgeColor = '#0284c7';
        let iconSymbol = '🧒';

        if (status === 'ON_BUS') {
            badgeColor = '#059669';
            iconSymbol = '🧒🚌';
        } else if (status === 'DROPPED') {
            badgeColor = '#7c3aed';
            iconSymbol = '🏠🧒';
        } else {
            badgeColor = '#d97706';
            iconSymbol = '📍🧒';
        }

        const childIconHtml = `
            <div style="background:${badgeColor}; color:#ffffff; border-radius:20px; padding:4px 10px; font-weight:700; font-size:12px; display:flex; align-items:center; gap:5px; border:2px solid #ffffff; box-shadow:0 0 12px ${badgeColor}; white-space:nowrap;">
                ${iconSymbol} ${childName}
            </div>
        `;

        const childIcon = L.divIcon({
            className: 'custom-child-marker',
            html: childIconHtml,
            iconSize: [140, 32],
            iconAnchor: [70, 16]
        });

        if (this.childMarker) {
            this.childMarker.setLatLng(point);
            this.childMarker.setIcon(childIcon);
        } else {
            this.childMarker = L.marker(point, { icon: childIcon, zIndexOffset: 1000 }).addTo(this.map);
            this.childMarker.bindPopup(`
                <div style="font-family:sans-serif; text-align:center; padding:4px;">
                    <b style="color:${badgeColor}; font-size:13px;">${childName}'s Live Position</b><br>
                    <small style="color:#666;">Status: ${statusLabel || status}</small>
                </div>
            `);
        }
    }
}
