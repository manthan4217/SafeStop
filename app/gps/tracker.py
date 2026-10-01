import math
import logging
from datetime import datetime, timedelta
from config import Config
from app.models import db, Trip, Bus, Route, Stop, GpsLocation, Alert, Notification, SafeDropConfirmation, Student, StopProximityLog

logger = logging.getLogger(__name__)

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth in meters using Haversine formula.
    """
    R = 6371000  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    meters = R * c
    return meters


def min_distance_to_route_stops(lat, lng, stops):
    """Calculate minimum distance in meters from point (lat, lng) to any stop in route."""
    if not stops:
        return 0.0
    min_dist = float('inf')
    for stop in stops:
        dist = haversine_distance(lat, lng, stop.latitude, stop.longitude)
        if dist < min_dist:
            min_dist = dist
    return min_dist


def check_and_escalate_pending_safe_drops():
    """Checks pending safe drops exceeding SAFE_DROP_ESCALATION_MINUTES and triggers administrative escalation alerts."""
    escalation_mins = getattr(Config, 'SAFE_DROP_ESCALATION_MINUTES', 15)
    cutoff = datetime.utcnow() - timedelta(minutes=escalation_mins)
    
    pending_drops = SafeDropConfirmation.query.filter(
        SafeDropConfirmation.status == 'PENDING',
        SafeDropConfirmation.bus_arrival_time <= cutoff
    ).all()

    for drop in pending_drops:
        drop.status = 'ESCALATED'
        
        escalated_alert = Alert(
            institution_id=drop.trip.institution_id if drop.trip else 1,
            bus_id=drop.trip.bus_id if drop.trip else None,
            trip_id=drop.trip_id,
            student_id=drop.student_id,
            alert_type='SAFE_DROP_PENDING',
            risk_score=35,
            severity='CRITICAL',
            description=f"UNCONFIRMED SAFE DROP ESCALATION! Parent confirmation pending for {drop.student.full_name} for >{escalation_mins} minutes."
        )
        db.session.add(escalated_alert)

        from app.notifications.service import broadcast_admin_notification
        broadcast_admin_notification(
            title="⚠️ UNCONFIRMED SAFE DROP ESCALATION",
            message=f"Parent confirmation pending for {drop.student.full_name} (> {escalation_mins} mins).",
            category="EMERGENCY"
        )
    
    if pending_drops:
        db.session.commit()


def update_driver_bus_location(driver, lat, lng, speed=0.0, heading=0.0):
    """
    Ingest driver smartphone GPS point when driver is online.
    Updates Driver and assigned Bus real-time coordinates directly.
    """
    now = datetime.utcnow()
    driver.is_online = True
    driver.current_lat = lat
    driver.current_lng = lng
    driver.last_online_at = now

    if driver.assigned_bus:
        driver.assigned_bus.current_lat = lat
        driver.assigned_bus.current_lng = lng
        driver.assigned_bus.last_location_update = now
        driver.assigned_bus.status = 'ACTIVE'


def process_gps_update(trip_id, lat, lng, speed=25.0, heading=0.0):
    """
    Ingest driver smartphone GPS point during an active trip.
    Performs real-time safety checks:
    1. Log GPS point in DB
    2. Update active trip, Bus, and Driver location
    3. Check Route Deviation
    4. Check Geofence Drop-Stop Arrival for Safe Drop trigger
    5. Calculate ETA & Delay
    6. Process Safe Drop Escalations
    """
    trip = db.session.get(Trip, trip_id)
    if not trip or trip.status != 'IN_PROGRESS':
        return {'status': 'INACTIVE_TRIP', 'message': 'Trip is not currently active'}

    now = datetime.utcnow()
    # 1. Update trip position
    trip.current_lat = lat
    trip.current_lng = lng

    # Update assigned Bus and Driver position
    if trip.bus:
        trip.bus.current_lat = lat
        trip.bus.current_lng = lng
        trip.bus.last_location_update = now
        trip.bus.status = 'ACTIVE'

    if trip.driver:
        trip.driver.current_lat = lat
        trip.driver.current_lng = lng
        trip.driver.last_online_at = now
        trip.driver.is_online = True

    # Log GPS point
    gps_entry = GpsLocation(
        trip_id=trip.id,
        bus_id=trip.bus_id,
        latitude=lat,
        longitude=lng,
        speed=speed,
        heading=heading,
        timestamp=now
    )
    db.session.add(gps_entry)

    alerts_generated = []

    # 2. Route Deviation Check
    route = db.session.get(Route, trip.route_id)
    if route:
        stops = route.stops.all()
        min_dist = min_distance_to_route_stops(lat, lng, stops)
        
        threshold = getattr(Config, 'ROUTE_DEVIATION_THRESHOLD_METERS', 500.0)
        if min_dist > threshold:
            existing_alert = Alert.query.filter_by(
                trip_id=trip.id,
                alert_type='ROUTE_DEVIATION',
                is_resolved=False
            ).first()

            if not existing_alert:
                dev_alert = Alert(
                    institution_id=trip.institution_id,
                    bus_id=trip.bus_id,
                    trip_id=trip.id,
                    alert_type='ROUTE_DEVIATION',
                    risk_score=30,
                    severity='CRITICAL',
                    description=f"Bus {trip.bus.bus_code} has deviated {int(min_dist)} meters from planned route {route.name}."
                )
                db.session.add(dev_alert)
                alerts_generated.append('ROUTE_DEVIATION')

                # Notify parents & admin
                bus_students = Student.query.filter_by(assigned_bus_id=trip.bus_id).all()
                for st in bus_students:
                    if st.parent and st.parent.user:
                        n = Notification(
                            user_id=st.parent.user.id,
                            title="⚠️ Route Deviation Alert",
                            message=f"Bus {trip.bus.bus_code} carrying your child {st.full_name} has significantly deviated from its planned route.",
                            category="ROUTE_VIOLATION"
                        )
                        db.session.add(n)

    # 3. Geofence Safe-Drop Detection (Evening Drop Trips)
    if trip.trip_type == 'EVENING_DROP' and route:
        stops = route.stops.all()
        for stop in stops:
            dist = haversine_distance(lat, lng, stop.latitude, stop.longitude)
            if dist <= 80.0:  # Within 80 meters geofence of stop
                students_at_stop = Student.query.filter_by(assigned_bus_id=trip.bus_id, drop_stop_id=stop.id).all()
                for student in students_at_stop:
                    existing_drop = SafeDropConfirmation.query.filter_by(
                        student_id=student.id,
                        trip_id=trip.id,
                        stop_id=stop.id
                    ).first()

                    if not existing_drop:
                        safe_drop = SafeDropConfirmation(
                            student_id=student.id,
                            trip_id=trip.id,
                            stop_id=stop.id,
                            parent_id=student.parent_id,
                            bus_arrival_time=datetime.utcnow(),
                            status='PENDING'
                        )
                        db.session.add(safe_drop)

                        if student.parent and student.parent.user:
                            n = Notification(
                                user_id=student.parent.user.id,
                                title="🚌 Safe Drop Arrival Notification",
                                message=f"Bus {trip.bus.bus_code} has reached {stop.stop_name} drop stop for {student.full_name}. Please confirm safe arrival.",
                                category="SAFE_DROP",
                                action_link=f"/parent/safe-drop/confirm/{safe_drop.id}"
                            )
                            db.session.add(n)

                        alerts_generated.append(f'SAFE_DROP_PENDING_{student.full_name}')

    # 3.5 Parent ETA Proximity Geo-fence Check
    if route:
        assigned_students = Student.query.filter_by(assigned_bus_id=trip.bus_id).all()
        for st in assigned_students:
            target_stop = st.pickup_stop if trip.trip_type == 'MORNING_PICKUP' else st.drop_stop
            if target_stop:
                dist = haversine_distance(lat, lng, target_stop.latitude, target_stop.longitude)
                parent_radius = st.parent.proximity_radius_meters if (st.parent and st.parent.proximity_radius_meters) else 500
                
                if dist <= parent_radius:
                    existing_prox = StopProximityLog.query.filter_by(
                        trip_id=trip.id,
                        student_id=st.id,
                        stop_id=target_stop.id
                    ).first()

                    if not existing_prox:
                        eta_mins = max(1, round(dist / 500.0))
                        prox_log = StopProximityLog(
                            trip_id=trip.id,
                            bus_id=trip.bus_id,
                            stop_id=target_stop.id,
                            student_id=st.id,
                            parent_id=st.parent_id,
                            distance_meters=dist,
                            estimated_eta_mins=eta_mins,
                            notified_at=datetime.utcnow()
                        )
                        db.session.add(prox_log)

                        if st.parent and st.parent.user:
                            n = Notification(
                                user_id=st.parent.user.id,
                                title="🚌 PROXIMITY ALERT: Bus Approaching Stop!",
                                message=f"Bus {trip.bus.bus_code if trip.bus else 'N/A'} is {int(dist)}m (~{eta_mins} mins) away from {target_stop.stop_name} for {st.full_name}. Please proceed to stop.",
                                category="BOARDING" if trip.trip_type == 'MORNING_PICKUP' else "ARRIVAL"
                            )
                            db.session.add(n)

                        alerts_generated.append(f'PROXIMITY_ALERT_{st.full_name}')

    # 4. Check Safe Drop Escalation Timeouts
    check_and_escalate_pending_safe_drops()

    # 5. ETA & Delay Calculation
    if trip.start_time:
        elapsed_mins = (datetime.utcnow() - trip.start_time).total_seconds() / 60.0
        expected_duration = route.estimated_duration_mins if route else 45
        delay_threshold = getattr(Config, 'DELAY_THRESHOLD_MINUTES', 10)
        
        if elapsed_mins > (expected_duration + delay_threshold):
            trip.delay_minutes = int(elapsed_mins - expected_duration)
            existing_delay_alert = Alert.query.filter_by(
                trip_id=trip.id,
                alert_type='BUS_DELAY',
                is_resolved=False
            ).first()

            if not existing_delay_alert:
                delay_alert = Alert(
                    bus_id=trip.bus_id,
                    trip_id=trip.id,
                    alert_type='BUS_DELAY',
                    risk_score=20,
                    severity='WARNING',
                    description=f"Bus {trip.bus.bus_code} trip is currently delayed by {trip.delay_minutes} minutes."
                )
                db.session.add(delay_alert)
                alerts_generated.append('BUS_DELAY')

    db.session.commit()
    return {
        'status': 'SUCCESS',
        'trip_id': trip.id,
        'bus_code': trip.bus.bus_code if trip.bus else 'N/A',
        'lat': lat,
        'lng': lng,
        'alerts_generated': alerts_generated
    }
