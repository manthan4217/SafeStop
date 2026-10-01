from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user  # type: ignore # pyright: ignore[reportMissingImports]
from app import role_required
from app.tenancy import require_feature
from app.models import db, Driver, Bus, Route, Stop, Trip, Student, Attendance, Alert, Notification, GpsLocation, EmergencyEvent, StudentAbsenceRequest, DriverSafetyTelemetry, User, AuditLog
from app.ai.engine import identify_student_from_face, check_bus_assignment, extract_face_features
from app.gps.tracker import process_gps_update, update_driver_bus_location

driver_bp = Blueprint('driver', __name__)

@driver_bp.route('/dashboard')
@login_required
@role_required('DRIVER')
def dashboard():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        flash('Driver profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    assigned_bus = Bus.query.get(driver.assigned_bus_id) if driver.assigned_bus_id else None
    assigned_route = Route.query.get(driver.assigned_route_id) if driver.assigned_route_id else None

    # Check for active trip
    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()

    # Roster stats
    total_assigned_students = Student.query.filter_by(assigned_bus_id=driver.assigned_bus_id).count() if driver.assigned_bus_id else 0
    boarded_count = 0
    pending_count = total_assigned_students

    if active_trip:
        boarded_count = Attendance.query.filter_by(trip_id=active_trip.id, verification_status='VERIFIED').count()
        pending_count = max(0, total_assigned_students - boarded_count)

    return render_template(
        'driver/dashboard.html',
        driver=driver,
        bus=assigned_bus,
        route=assigned_route,
        active_trip=active_trip,
        total_students=total_assigned_students,
        boarded_count=boarded_count,
        pending_count=pending_count
    )


@driver_bp.route('/trip/start', methods=['POST'])
@login_required
@role_required('DRIVER')
def start_trip():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver or not driver.assigned_bus_id or not driver.assigned_route_id:
        flash('You must have an assigned bus and route to start a trip.', 'warning')
        return redirect(url_for('driver.dashboard'))

    trip_type = request.form.get('trip_type', 'MORNING_PICKUP')

    # Check if there is already an active trip
    existing = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()
    if existing:
        flash('You already have an active trip in progress.', 'info')
        return redirect(url_for('driver.camera_verify'))

    new_trip = Trip(
        institution_id=current_user.institution_id,
        bus_id=driver.assigned_bus_id,
        driver_id=driver.id,
        route_id=driver.assigned_route_id,
        trip_type=trip_type,
        status='IN_PROGRESS',
        start_time=datetime.utcnow()
    )
    db.session.add(new_trip)
    db.session.commit()

    flash(f'Started {trip_type.replace("_", " ")} trip for Bus {driver.assigned_bus.bus_code}.', 'success')
    return redirect(url_for('driver.camera_verify'))


@driver_bp.route('/camera-verify')
@login_required
@role_required('DRIVER')
def camera_verify():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()
    
    if not active_trip:
        flash('Please start a trip first before performing student face verification.', 'warning')
        return redirect(url_for('driver.dashboard'))

    assigned_students = Student.query.filter_by(assigned_bus_id=driver.assigned_bus_id).all()
    
    # Get boarded student IDs
    boarded_attendances = Attendance.query.filter_by(trip_id=active_trip.id).all()
    boarded_student_ids = {a.student_id for a in boarded_attendances}

    # Get active absence requests for today
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    active_absences = StudentAbsenceRequest.query.filter(
        StudentAbsenceRequest.absence_date == today_str,
        StudentAbsenceRequest.status != 'CANCELLED'
    ).all()
    absent_map = {ab.student_id: ab for ab in active_absences}

    return render_template(
        'driver/camera_verify.html',
        driver=driver,
        trip=active_trip,
        students=assigned_students,
        boarded_ids=boarded_student_ids,
        absent_map=absent_map
    )


@driver_bp.route('/api/verify-face', methods=['POST'])
@login_required
@role_required('DRIVER')
def api_verify_face():
    """REST API endpoint called by HTML5 Webcam driver UI."""
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'status': 'ERROR', 'message': 'Driver profile not found'}), 403

    data = request.get_json() or {}
    image_b64 = data.get('image')
    trip_id = data.get('trip_id')

    if not image_b64 or not trip_id:
        return jsonify({'status': 'ERROR', 'message': 'Missing image frame or trip ID'}), 400

    trip = Trip.query.get(trip_id)
    if not trip or trip.status != 'IN_PROGRESS':
        return jsonify({'status': 'ERROR', 'message': 'Active trip session not found'}), 400

    # Authorization Check (C1 / SEC-01): Verify driver owns this trip
    if trip.driver_id != driver.id:
        return jsonify({'status': 'ERROR', 'message': 'Access Denied: You are not authorized for this trip session.'}), 403

    result = identify_student_from_face(image_b64, active_trip_id=trip_id)

    if result['status'] != 'MATCHED':
        return jsonify(result)

    student = result['student']
    confidence = result['confidence']

    # Check wrong bus
    is_correct_bus, bus_reason, assigned_bus_code = check_bus_assignment(student.id, trip.bus_id)

    if not is_correct_bus:
        # WRONG BUS DETECTED!
        alert = Alert(
            institution_id=current_user.institution_id,
            bus_id=trip.bus_id,
            trip_id=trip.id,
            student_id=student.id,
            alert_type='WRONG_BUS',
            risk_score=40,
            severity='CRITICAL',
            description=f"WRONG BUS DETECTED! Student {student.full_name} (Assigned: {assigned_bus_code}) boarded {trip.bus.bus_code}."
        )
        db.session.add(alert)

        if student.parent and student.parent.user:
            n = Notification(
                user_id=student.parent.user.id,
                title="🚨 WRONG BUS ALERT",
                message=f"CRITICAL: Your child {student.full_name} was detected boarding BUS {trip.bus.bus_code} instead of assigned {assigned_bus_code}.",
                category="WRONG_BUS"
            )
            db.session.add(n)

        db.session.commit()

        return jsonify({
            'status': 'WRONG_BUS',
            'student_id': student.id,
            'student_name': student.full_name,
            'assigned_bus': assigned_bus_code,
            'current_bus': trip.bus.bus_code,
            'message': f"WRONG BUS DETECTED! Assigned to {assigned_bus_code}, boarded {trip.bus.bus_code}.",
            'confidence': confidence
        })

    scan_action = data.get('scan_action', 'BOARD').upper()

    # Check duplicate attendance or handle drop scan
    existing_att = Attendance.query.filter_by(student_id=student.id, trip_id=trip.id).first()

    if scan_action == 'DROP':
        if existing_att:
            existing_att.is_dropped_off = True
            existing_att.drop_verification_time = datetime.utcnow()
            existing_att.scan_type = 'DROP'
        else:
            att = Attendance(
                student_id=student.id,
                trip_id=trip.id,
                bus_id=trip.bus_id,
                verification_status='VERIFIED',
                scan_type='DROP',
                is_dropped_off=True,
                drop_verification_time=datetime.utcnow(),
                verified_by_driver_id=trip.driver_id,
                notes=f"AI Face Recognition Drop-off (Confidence: {confidence}%)"
            )
            db.session.add(att)

        if student.parent and student.parent.user:
            n = Notification(
                user_id=student.parent.user.id,
                title="✅ Drop-Off Verified",
                message=f"Your child {student.full_name} was scanned off {trip.bus.bus_code} at drop stop.",
                category="SAFE_DROP"
            )
            db.session.add(n)

        db.session.commit()
        return jsonify({
            'status': 'DROP_VERIFIED',
            'student_id': student.id,
            'student_name': student.full_name,
            'roll_number': student.roll_number,
            'confidence': confidence,
            'message': f"Student Drop Verified: {student.full_name} (BUS {trip.bus.bus_code})"
        })

    if existing_att:
        return jsonify({
            'status': 'ALREADY_BOARDED',
            'student_name': student.full_name,
            'message': f"{student.full_name} is already verified and recorded on this trip."
        })

    # VERIFIED! Record attendance
    att = Attendance(
        student_id=student.id,
        trip_id=trip.id,
        bus_id=trip.bus_id,
        verification_status='VERIFIED',
        scan_type='BOARD',
        verified_by_driver_id=trip.driver_id,
        notes=f"AI Face Recognition (Confidence: {confidence}%)"
    )
    db.session.add(att)

    if student.parent and student.parent.user:
        trip_time_str = datetime.now().strftime("%I:%M %p")
        n = Notification(
            user_id=student.parent.user.id,
            title="🚌 Boarding Confirmed",
            message=f"Your child {student.full_name} has boarded {trip.bus.bus_code} at {trip_time_str}.",
            category="BOARDING"
        )
        db.session.add(n)

    db.session.commit()

    return jsonify({
        'status': 'VERIFIED',
        'student_id': student.id,
        'student_name': student.full_name,
        'roll_number': student.roll_number,
        'confidence': confidence,
        'message': f"Student Verified: {student.full_name} (BUS {trip.bus.bus_code})"
    })


@driver_bp.route('/api/sync-offline-queue', methods=['POST'])
@login_required
@role_required('DRIVER')
def api_sync_offline_queue():
    """Processes background queued attendance scans and SOS emergencies collected when offline."""
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'status': 'ERROR', 'message': 'Driver profile not found'}), 403

    data = request.get_json() or {}
    queue = data.get('queue', [])
    sos_queue = data.get('sos_queue', [])
    synced_count = 0
    sos_synced_count = 0

    for item in queue:
        if item.get('type') == 'SOS':
            sos_queue.append(item)
            continue

        img_b64 = item.get('image')
        trip_id = item.get('trip_id')
        if img_b64 and trip_id:
            trip = Trip.query.get(trip_id)
            # Authorization Check (C1): Verify driver owns trip
            if trip and trip.driver_id == driver.id and trip.status == 'IN_PROGRESS':
                res = identify_student_from_face(img_b64, active_trip_id=trip.id)
                if res['status'] == 'MATCHED':
                    st = res['student']
                    
                    # Full Wrong-Bus Safety Check during sync (C4 fix)
                    is_correct_bus, bus_reason, assigned_bus_code = check_bus_assignment(st.id, trip.bus_id)
                    if not is_correct_bus:
                        alert = Alert(
                            institution_id=current_user.institution_id,
                            bus_id=trip.bus_id,
                            trip_id=trip.id,
                            student_id=st.id,
                            alert_type='WRONG_BUS',
                            risk_score=40,
                            severity='CRITICAL',
                            description=f"WRONG BUS DETECTED (Offline Sync)! Student {st.full_name} (Assigned: {assigned_bus_code}) boarded {trip.bus.bus_code}."
                        )
                        db.session.add(alert)
                        continue

                    existing = Attendance.query.filter_by(student_id=st.id, trip_id=trip.id).first()
                    if not existing:
                        att = Attendance(
                            student_id=st.id,
                            trip_id=trip.id,
                            bus_id=trip.bus_id,
                            verification_status='VERIFIED',
                            verified_by_driver_id=trip.driver_id,
                            notes=f"AI Face Scan (Offline Queue Auto-Synced)"
                        )
                        db.session.add(att)
                        synced_count += 1

    for sos_item in sos_queue:
        trip_id = sos_item.get('trip_id')
        lat = sos_item.get('latitude')
        lng = sos_item.get('longitude')
        desc = sos_item.get('description', 'Emergency SOS triggered while offline')
        triggered_at_raw = sos_item.get('triggered_at')

        trip = Trip.query.get(trip_id) if trip_id else None
        if trip and trip.driver_id != driver.id:
            continue
        bus_id = trip.bus_id if trip else driver.assigned_bus_id

        triggered_at_dt = None
        if triggered_at_raw:
            try:
                triggered_at_dt = datetime.fromisoformat(str(triggered_at_raw).replace('Z', '+00:00'))
            except Exception:
                triggered_at_dt = datetime.utcnow()
        else:
            triggered_at_dt = datetime.utcnow()

        sos_event = EmergencyEvent(
            bus_id=bus_id,
            trip_id=trip.id if trip else None,
            triggered_by_user_id=current_user.id,
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            description=desc,
            triggered_at=triggered_at_dt
        )
        db.session.add(sos_event)

        bus_code = driver.assigned_bus.bus_code if driver.assigned_bus else 'N/A'
        sos_alert = Alert(
            institution_id=current_user.institution_id,
            bus_id=bus_id,
            trip_id=trip.id if trip else None,
            alert_type='SOS_EMERGENCY',
            risk_score=50,
            severity='CRITICAL',
            description=f"🚨 EMERGENCY SOS TRIGGERED (Offline Queue Synced) by Driver {current_user.full_name} for Bus {bus_code}. Triggered at {triggered_at_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}."
        )
        db.session.add(sos_alert)

        from app.notifications.service import broadcast_admin_notification
        broadcast_admin_notification(
            title="🚨 CRITICAL EMERGENCY SOS (Offline Synced)",
            message=f"Offline SOS Alert synced from Driver {current_user.full_name} on Bus {bus_code} (Triggered at {triggered_at_dt.strftime('%H:%M:%S UTC')}).",
            category="EMERGENCY"
        )
        sos_synced_count += 1

    db.session.commit()
    return jsonify({'status': 'SUCCESS', 'synced_count': synced_count, 'sos_synced_count': sos_synced_count})


@driver_bp.route('/manual-verify', methods=['POST'])
@login_required
@role_required('DRIVER')
def manual_verify():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    student_id = request.form.get('student_id')
    trip_id = request.form.get('trip_id')
    reason = request.form.get('reason', 'Driver Manual Override')

    student = Student.query.get(student_id)
    trip = Trip.query.get(trip_id)

    if not student or not trip:
        flash('Invalid student or trip reference.', 'danger')
        return redirect(url_for('driver.camera_verify'))

    if trip.driver_id != driver.id:
        flash('Unauthorized access: You cannot verify attendance on another driver\'s trip.', 'danger')
        return redirect(url_for('driver.dashboard'))

    existing = Attendance.query.filter_by(student_id=student.id, trip_id=trip.id).first()
    if not existing:
        att = Attendance(
            student_id=student.id,
            trip_id=trip.id,
            bus_id=trip.bus_id,
            verification_status='MANUAL_OVERRIDE',
            verified_by_driver_id=trip.driver_id,
            notes=reason
        )
        db.session.add(att)

        # AuditLog entry for manual verification override tracking
        audit_log = AuditLog(
            institution_id=current_user.institution_id,
            user_id=current_user.id,
            action="MANUAL_VERIFY_OVERRIDE",
            ip_address=request.remote_addr,
            details=f"Manual verification override performed by Driver {current_user.full_name} for Student {student.full_name} (Trip #{trip.id}, Bus {trip.bus.bus_code}). Reason: {reason}"
        )
        db.session.add(audit_log)

        if student.parent and student.parent.user:
            n = Notification(
                user_id=student.parent.user.id,
                title="🚌 Boarding Confirmed (Driver Verification)",
                message=f"Your child {student.full_name} was manually verified on {trip.bus.bus_code}.",
                category="BOARDING"
            )
            db.session.add(n)

        db.session.commit()
        flash(f'Manual verification recorded for {student.full_name}.', 'success')
    else:
        flash(f'{student.full_name} is already marked present.', 'info')

    return redirect(url_for('driver.camera_verify'))


@driver_bp.route('/roster')
@login_required
@role_required('DRIVER')
def roster():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()
    assigned_students = Student.query.filter_by(assigned_bus_id=driver.assigned_bus_id).all()

    boarded_list = []
    pending_list = []

    if active_trip:
        boarded_atts = Attendance.query.filter_by(trip_id=active_trip.id).all()
        boarded_ids = {a.student_id: a for a in boarded_atts}

        for st in assigned_students:
            if st.id in boarded_ids:
                boarded_list.append({'student': st, 'attendance': boarded_ids[st.id]})
            else:
                pending_list.append(st)
    else:
        pending_list = assigned_students

    # Get active absence requests for today
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    active_absences = StudentAbsenceRequest.query.filter(
        StudentAbsenceRequest.absence_date == today_str,
        StudentAbsenceRequest.status != 'CANCELLED'
    ).all()
    absent_map = {ab.student_id: ab for ab in active_absences}

    return render_template(
        'driver/roster.html',
        driver=driver,
        active_trip=active_trip,
        boarded=boarded_list,
        pending=pending_list,
        absent_map=absent_map
    )


@driver_bp.route('/api/toggle-online', methods=['POST'])
@login_required
@role_required('DRIVER')
def api_toggle_online():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'status': 'ERROR', 'message': 'Driver profile not found'}), 403

    data = request.get_json() or {}
    desired_status = data.get('is_online')

    if desired_status is None:
        driver.is_online = not driver.is_online
    else:
        driver.is_online = bool(desired_status)

    now = datetime.utcnow()
    driver.last_online_at = now

    assigned_bus = Bus.query.get(driver.assigned_bus_id) if driver.assigned_bus_id else None

    if driver.is_online:
        if assigned_bus:
            assigned_bus.status = 'ACTIVE'
            assigned_bus.last_location_update = now
        msg = f"Driver is ONLINE. Bus {assigned_bus.bus_code if assigned_bus else 'N/A'} is now ACTIVE."
    else:
        if assigned_bus:
            assigned_bus.status = 'INACTIVE'
        msg = f"Driver is OFFLINE. Bus {assigned_bus.bus_code if assigned_bus else 'N/A'} is now INACTIVE."

    db.session.commit()

    return jsonify({
        'status': 'SUCCESS',
        'is_online': driver.is_online,
        'bus_status': assigned_bus.status if assigned_bus else 'UNASSIGNED',
        'bus_code': assigned_bus.bus_code if assigned_bus else 'N/A',
        'message': msg
    })


@driver_bp.route('/api/gps-update', methods=['POST'])
@login_required
@role_required('DRIVER')
def api_gps_update():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'status': 'ERROR', 'message': 'Driver profile not found'}), 403

    data = request.get_json() or {}
    lat = data.get('latitude')
    lng = data.get('longitude')
    trip_id = data.get('trip_id')

    if lat is None or lng is None:
        return jsonify({'status': 'ERROR', 'message': 'Missing latitude or longitude'}), 400

    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (ValueError, TypeError):
        return jsonify({'status': 'ERROR', 'message': 'Invalid latitude or longitude value'}), 400

    # Always update driver & bus mobile location when GPS coordinates are sent
    update_driver_bus_location(driver, lat_f, lng_f)
    driver.is_online = True  # Streaming GPS implicitly confirms driver online state

    res = {
        'status': 'SUCCESS',
        'lat': lat_f,
        'lng': lng_f,
        'driver_is_online': driver.is_online,
        'bus_code': driver.assigned_bus.bus_code if driver.assigned_bus else 'N/A',
        'bus_status': driver.assigned_bus.status if driver.assigned_bus else 'UNASSIGNED'
    }

    if trip_id:
        trip = Trip.query.get(trip_id)
        if trip and trip.driver_id == driver.id and trip.status == 'IN_PROGRESS':
            trip_res = process_gps_update(trip_id, lat_f, lng_f)
            res.update(trip_res)

    db.session.commit()
    return jsonify(res)


@driver_bp.route('/api/trigger-sos', methods=['POST'])
@login_required
@role_required('DRIVER')
def api_trigger_sos():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'status': 'ERROR', 'message': 'Driver profile not found'}), 403

    data = request.get_json() or {}
    trip_id = data.get('trip_id')
    lat = data.get('latitude')
    lng = data.get('longitude')
    desc = data.get('description', 'Emergency SOS triggered by driver')
    triggered_at_raw = data.get('triggered_at')

    trip = Trip.query.get(trip_id) if trip_id else None
    if trip and trip.driver_id != driver.id:
        return jsonify({'status': 'ERROR', 'message': 'Access Denied: Unauthorized trip reference for SOS alert.'}), 403
    bus_id = trip.bus_id if trip else driver.assigned_bus_id

    triggered_at_dt = None
    if triggered_at_raw:
        try:
            triggered_at_dt = datetime.fromisoformat(str(triggered_at_raw).replace('Z', '+00:00'))
        except Exception:
            triggered_at_dt = datetime.utcnow()
    else:
        triggered_at_dt = datetime.utcnow()

    # Record emergency event
    sos_event = EmergencyEvent(
        bus_id=bus_id,
        trip_id=trip.id if trip else None,
        triggered_by_user_id=current_user.id,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None,
        description=desc,
        triggered_at=triggered_at_dt
    )
    db.session.add(sos_event)

    # Record Alert
    sos_alert = Alert(
        institution_id=current_user.institution_id,
        bus_id=bus_id,
        trip_id=trip.id if trip else None,
        alert_type='SOS_EMERGENCY',
        risk_score=50,
        severity='CRITICAL',
        description=f"🚨 EMERGENCY SOS TRIGGERED by Driver {current_user.full_name} for Bus {driver.assigned_bus.bus_code if driver.assigned_bus else 'N/A'}."
    )
    db.session.add(sos_alert)

    # Broadcast to all Admins
    from app.notifications.service import broadcast_admin_notification
    broadcast_admin_notification(
        title="🚨 CRITICAL EMERGENCY SOS",
        message=f"SOS Alert received from Driver {current_user.full_name} on Bus {driver.assigned_bus.bus_code if driver.assigned_bus else 'N/A'}.",
        category="EMERGENCY"
    )

    db.session.commit()
    return jsonify({'status': 'SUCCESS', 'message': 'EMERGENCY SOS ALERT TRANSMITTED TO SCHOOL ADMIN'})


def check_trip_no_shows(trip):
    """
    Evaluates trip completion for unboarded students who have no absence request on file today.
    Creates CRITICAL NO_SHOW alert and dispatches parent notification via Phase 1 pipeline.
    """
    if not trip or not trip.bus_id:
        return []

    from app.notifications.service import send_notification
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    assigned_students = Student.query.filter_by(assigned_bus_id=trip.bus_id).all()

    active_absences = StudentAbsenceRequest.query.filter(
        StudentAbsenceRequest.absence_date == today_str,
        StudentAbsenceRequest.status != 'CANCELLED'
    ).all()
    absent_student_ids = {ab.student_id for ab in active_absences}

    trip_attendances = Attendance.query.filter_by(trip_id=trip.id).all()
    boarded_student_ids = {att.student_id for att in trip_attendances}

    no_show_alerts = []
    bus_code = trip.bus.bus_code if trip.bus else 'N/A'

    for student in assigned_students:
        if student.id not in boarded_student_ids and student.id not in absent_student_ids:
            alert = Alert(
                institution_id=trip.institution_id,
                bus_id=trip.bus_id,
                trip_id=trip.id,
                student_id=student.id,
                alert_type='NO_SHOW',
                risk_score=45,
                severity='CRITICAL',
                description=f"NO-SHOW ALERT: Student {student.full_name} (Roll #{student.roll_number}) was expected for Trip #{trip.id} on Bus {bus_code} but never boarded and has no active absence request."
            )
            db.session.add(alert)
            no_show_alerts.append(alert)

            if student.parent and student.parent.user:
                send_notification(
                    user_id=student.parent.user.id,
                    title="🚨 NO-SHOW ALERT",
                    message=f"URGENT: Your child {student.full_name} did not board assigned Bus {bus_code} for today's trip and no absence was reported.",
                    category="NO_SHOW"
                )

    return no_show_alerts


def run_no_show_check():
    """
    Evaluates all currently in-progress trips across all institutions for missing/unboarded students.
    """
    active_trips = Trip.query.filter_by(status='IN_PROGRESS').all()
    all_alerts = []
    for trip in active_trips:
        all_alerts.extend(check_trip_no_shows(trip))
    return all_alerts


def check_unscanned_drop_offs(trip, stop_id=None):
    """
    Checks for students who boarded the trip but were not scanned off at their assigned drop stop.
    Triggers CRITICAL UNSCANNED_DROP alert and notifies parent and school admin.
    """
    if not trip or not trip.bus_id:
        return []

    from app.notifications.service import send_notification, broadcast_admin_notification

    query = Student.query.filter_by(assigned_bus_id=trip.bus_id)
    if stop_id:
        query = query.filter_by(drop_stop_id=stop_id)
    target_students = query.all()

    unscanned_alerts = []
    bus_code = trip.bus.bus_code if trip.bus else 'N/A'

    for student in target_students:
        att = Attendance.query.filter_by(student_id=student.id, trip_id=trip.id).first()
        # Student boarded (VERIFIED or MANUAL_OVERRIDE) but was NOT scanned off at drop stop
        if att and att.verification_status in ('VERIFIED', 'MANUAL_OVERRIDE') and not att.is_dropped_off:
            existing_alert = Alert.query.filter_by(
                trip_id=trip.id,
                student_id=student.id,
                alert_type='UNSCANNED_DROP',
                is_resolved=False
            ).first()

            if not existing_alert:
                stop_name = student.drop_stop.stop_name if student.drop_stop else 'assigned drop stop'
                alert = Alert(
                    institution_id=trip.institution_id,
                    bus_id=trip.bus_id,
                    trip_id=trip.id,
                    student_id=student.id,
                    alert_type='UNSCANNED_DROP',
                    risk_score=50,
                    severity='CRITICAL',
                    description=f"UNSCANNED DROP-OFF ALERT: Student {student.full_name} (Roll #{student.roll_number}) boarded Trip #{trip.id} but was NOT scanned off at {stop_name}."
                )
                db.session.add(alert)
                unscanned_alerts.append(alert)

                if student.parent and student.parent.user:
                    send_notification(
                        user_id=student.parent.user.id,
                        title="🚨 UNSCANNED DROP-OFF ALERT",
                        message=f"CRITICAL: Your child {student.full_name} was boarded on Bus {bus_code} but was not scanned off at drop stop {stop_name}.",
                        category="UNSCANNED_DROP"
                    )

                broadcast_admin_notification(
                    title="🚨 UNSCANNED DROP-OFF ALERT",
                    message=f"Driver on Bus {bus_code} concluded trip without scanning off boarded student {student.full_name} at drop stop {stop_name}.",
                    category="EMERGENCY"
                )

    return unscanned_alerts


@driver_bp.route('/trip/end', methods=['POST'])
@login_required
@role_required('DRIVER')
def end_trip():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()

    if not active_trip:
        flash('No active trip to conclude.', 'warning')
        return redirect(url_for('driver.dashboard'))

    active_trip.status = 'COMPLETED'
    active_trip.end_time = datetime.utcnow()

    # Trigger automated safety checks
    check_trip_no_shows(active_trip)
    check_unscanned_drop_offs(active_trip)

    # If morning pickup trip, notify arrival at school
    if active_trip.trip_type == 'MORNING_PICKUP':
        assigned_students = Student.query.filter_by(assigned_bus_id=driver.assigned_bus_id).all()
        for st in assigned_students:
            if st.parent and st.parent.user:
                n = Notification(
                    user_id=st.parent.user.id,
                    title="🏫 School Arrival Confirmed",
                    message=f"Bus {driver.assigned_bus.bus_code} has safely arrived at school.",
                    category="ARRIVALS"
                )
                db.session.add(n)

    db.session.commit()

    flash(f'Trip completed successfully for Bus {driver.assigned_bus.bus_code}.', 'success')
    return redirect(url_for('driver.dashboard'))


@driver_bp.route('/telemetry/log', methods=['POST'])
@login_required
@role_required('DRIVER')
@require_feature('driver_telemetry')
def log_telemetry():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        return jsonify({'error': 'Driver profile not found'}), 404

    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()
    data = request.get_json() or {}

    fatigue_score = float(data.get('fatigue_score', 0.0))
    fatigue_level = str(data.get('fatigue_level', 'NORMAL'))
    eye_closure_sec = float(data.get('eye_closure_sec', 0.0))
    yawn_count = int(data.get('yawn_count', 0))
    distraction_event = str(data.get('distraction_event', 'NONE'))
    speed_kph = float(data.get('speed_kph', 35.0))
    overspeed_warning = bool(data.get('overspeed_warning', False))
    harsh_braking_warning = bool(data.get('harsh_braking_warning', False))

    # Calculate dynamic safety score
    safety_score = 100
    if fatigue_level == 'MILD_DROWSINESS':
        safety_score -= 25
    elif fatigue_level == 'CRITICAL_DROWSINESS':
        safety_score -= 60

    if overspeed_warning:
        safety_score -= 20
    if harsh_braking_warning:
        safety_score -= 15
    if distraction_event != 'NONE':
        safety_score -= 20

    safety_score = max(0, min(100, safety_score))

    telemetry = DriverSafetyTelemetry(
        driver_id=driver.id,
        bus_id=driver.assigned_bus_id,
        trip_id=active_trip.id if active_trip else None,
        fatigue_score=fatigue_score,
        fatigue_level=fatigue_level,
        eye_closure_sec=eye_closure_sec,
        yawn_count=yawn_count,
        distraction_event=distraction_event,
        speed_kph=speed_kph,
        overspeed_warning=overspeed_warning,
        harsh_braking_warning=harsh_braking_warning,
        safety_score=safety_score,
        timestamp=datetime.utcnow()
    )
    db.session.add(telemetry)

    alert_created = False
    assigned_bus = Bus.query.get(driver.assigned_bus_id) if driver.assigned_bus_id else None
    bus_code = assigned_bus.bus_code if assigned_bus else 'N/A'

    if fatigue_level == 'CRITICAL_DROWSINESS' or overspeed_warning or distraction_event == 'EYES_OFF_ROAD':
        alert_type = 'DRIVER_FATIGUE' if fatigue_level == 'CRITICAL_DROWSINESS' else ('OVERSPEEDING' if overspeed_warning else 'DISTRACTED_DRIVING')
        desc = f"⚠️ HIGH RISK ALERT: Driver {driver.full_name} (Bus {bus_code}) - {fatigue_level.replace('_', ' ')} (Score: {fatigue_score:.2f}, Speed: {speed_kph:.1f} km/h)"
        
        # Check if an unresolved alert of this type exists in the last 5 minutes to avoid flood
        existing_alert = Alert.query.filter_by(
            bus_id=driver.assigned_bus_id,
            alert_type=alert_type,
            is_resolved=False
        ).first()

        if not existing_alert:
            new_alert = Alert(
                institution_id=current_user.institution_id,
                bus_id=driver.assigned_bus_id,
                trip_id=active_trip.id if active_trip else None,
                alert_type=alert_type,
                risk_score=95 if fatigue_level == 'CRITICAL_DROWSINESS' else 85,
                severity='CRITICAL',
                description=desc
            )
            db.session.add(new_alert)
            alert_created = True

            # Notify admins
            admin_users = User.query.filter_by(role='ADMIN').all()
            for admin_u in admin_users:
                n = Notification(
                    user_id=admin_u.id,
                    title=f"🚨 CRITICAL DRIVER ALERT: {driver.full_name}",
                    message=desc,
                    category="EMERGENCY"
                )
                db.session.add(n)

    db.session.commit()

    return jsonify({
        'success': True,
        'telemetry_id': telemetry.id,
        'fatigue_level': fatigue_level,
        'safety_score': safety_score,
        'alert_created': alert_created
    })


@driver_bp.route('/telemetry/simulate', methods=['POST'])
@login_required
@role_required('DRIVER')
@require_feature('driver_telemetry')
def simulate_telemetry():
    driver = Driver.query.filter_by(user_id=current_user.id).first()
    if not driver:
        flash('Driver profile not found.', 'danger')
        return redirect(url_for('driver.dashboard'))

    active_trip = Trip.query.filter_by(driver_id=driver.id, status='IN_PROGRESS').first()
    sim_type = request.form.get('sim_type', 'DROWSINESS')

    if sim_type == 'DROWSINESS':
        fatigue_score = 0.92
        fatigue_level = 'CRITICAL_DROWSINESS'
        eye_closure = 3.5
        yawn_cnt = 4
        distraction = 'EYES_OFF_ROAD'
        speed = 52.0
        overspeed = False
        harsh_brake = False
    elif sim_type == 'OVERSPEED':
        fatigue_score = 0.35
        fatigue_level = 'NORMAL'
        eye_closure = 0.2
        yawn_cnt = 0
        distraction = 'NONE'
        speed = 78.5
        overspeed = True
        harsh_brake = True
    else:
        fatigue_score = 0.05
        fatigue_level = 'NORMAL'
        eye_closure = 0.1
        yawn_cnt = 0
        distraction = 'NONE'
        speed = 38.0
        overspeed = False
        harsh_brake = False

    safety_score = 40 if sim_type == 'DROWSINESS' else (65 if sim_type == 'OVERSPEED' else 98)

    telemetry = DriverSafetyTelemetry(
        driver_id=driver.id,
        bus_id=driver.assigned_bus_id,
        trip_id=active_trip.id if active_trip else None,
        fatigue_score=fatigue_score,
        fatigue_level=fatigue_level,
        eye_closure_sec=eye_closure,
        yawn_count=yawn_cnt,
        distraction_event=distraction,
        speed_kph=speed,
        overspeed_warning=overspeed,
        harsh_braking_warning=harsh_brake,
        safety_score=safety_score,
        timestamp=datetime.utcnow()
    )
    db.session.add(telemetry)

    if sim_type in ['DROWSINESS', 'OVERSPEED']:
        desc = f"⚠️ SIMULATED SAFETY ALERT: Driver {driver.full_name} - {sim_type} triggered (Speed: {speed} km/h)"
        new_alert = Alert(
            institution_id=current_user.institution_id,
            bus_id=driver.assigned_bus_id,
            trip_id=active_trip.id if active_trip else None,
            alert_type='DRIVER_FATIGUE' if sim_type == 'DROWSINESS' else 'OVERSPEEDING',
            risk_score=95,
            severity='CRITICAL',
            description=desc
        )
        db.session.add(new_alert)

    db.session.commit()

    flash(f"Simulated telemetry event '{sim_type}' logged successfully. Safety Score: {safety_score}%.", "warning" if sim_type != 'NORMAL' else "success")
    return redirect(request.referrer or url_for('driver.dashboard'))

