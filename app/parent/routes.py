from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user  # type: ignore # pyright: ignore[reportMissingImports]
from app import role_required
from app.models import db, Parent, Student, Bus, Route, Stop, Trip, Attendance, Alert, Notification, SafeDropConfirmation, GpsLocation, StudentAbsenceRequest, StopProximityLog
from app.gps.tracker import haversine_distance

parent_bp = Blueprint('parent', __name__)

@parent_bp.route('/dashboard')
@login_required
@role_required('PARENT')
def dashboard():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    children = parent.students.all()
    
    # Active safe drop confirmations pending
    pending_safe_drops = SafeDropConfirmation.query.filter_by(
        parent_id=parent.id,
        status='PENDING'
    ).all()

    # Active absence requests for parent's children
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    active_absences = StudentAbsenceRequest.query.filter(
        StudentAbsenceRequest.parent_id == parent.id,
        StudentAbsenceRequest.status != 'CANCELLED'
    ).order_by(StudentAbsenceRequest.created_at.desc()).all()

    # Notifications feed
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()

    # Live Proximity Telemetry for Parent Children
    proximity_map = {}
    for st in children:
        if st.assigned_bus_id:
            active_t = Trip.query.filter_by(bus_id=st.assigned_bus_id, status='IN_PROGRESS').first()
            if active_t and active_t.current_lat and active_t.current_lng:
                target_stop = st.pickup_stop if active_t.trip_type == 'MORNING_PICKUP' else st.drop_stop
                if target_stop:
                    dist = haversine_distance(active_t.current_lat, active_t.current_lng, target_stop.latitude, target_stop.longitude)
                    eta_mins = max(1, round(dist / 500.0))
                    parent_radius = parent.proximity_radius_meters or 500
                    in_proximity = dist <= parent_radius
                    proximity_map[st.id] = {
                        'has_trip': True,
                        'bus_code': active_t.bus.bus_code if active_t.bus else 'N/A',
                        'stop_name': target_stop.stop_name,
                        'distance_m': int(dist),
                        'eta_mins': eta_mins,
                        'in_proximity': in_proximity,
                        'radius_m': parent_radius
                    }

    return render_template(
        'parent/dashboard.html',
        parent=parent,
        children=children,
        pending_safe_drops=pending_safe_drops,
        active_absences=active_absences,
        today_date=today_str,
        notifications=notifications,
        proximity_map=proximity_map
    )


@parent_bp.route('/child/<int:student_id>')
@login_required
@role_required('PARENT')
def child_profile(student_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    student = Student.query.get_or_404(student_id)

    if student.parent_id != parent.id:
        flash('Unauthorized access to student record.', 'danger')
        return redirect(url_for('parent.dashboard'))

    assigned_bus = student.assigned_bus
    assigned_route = student.assigned_route
    driver = assigned_bus.driver if assigned_bus else None

    # Attendance logs
    recent_attendances = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.verification_time.desc()).limit(15).all()

    return render_template(
        'parent/child_profile.html',
        student=student,
        bus=assigned_bus,
        route=assigned_route,
        driver=driver,
        attendances=recent_attendances
    )


@parent_bp.route('/tracking/<int:student_id>')
@login_required
@role_required('PARENT')
def live_tracking(student_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    student = Student.query.get_or_404(student_id)

    if student.parent_id != parent.id:
        flash('Unauthorized access to live bus tracking.', 'danger')
        return redirect(url_for('parent.dashboard'))

    bus = student.assigned_bus
    if not bus:
        flash('No bus assigned to student.', 'info')
        return redirect(url_for('parent.dashboard'))

    # Child's current location & boarding status
    latest_att = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.verification_time.desc()).first()
    safe_drop = SafeDropConfirmation.query.filter_by(student_id=student.id).order_by(SafeDropConfirmation.created_at.desc()).first()

    child_status = 'WAITING_PICKUP'
    child_status_label = 'Waiting at Pickup Stop'
    if safe_drop and safe_drop.status == 'CONFIRMED':
        child_status = 'DROPPED'
        child_status_label = 'Safely Dropped at Destination'
    elif latest_att and latest_att.verification_status == 'VERIFIED':
        child_status = 'ON_BUS'
        child_status_label = 'On Board Bus (AI Verified)'

    pickup_stop = student.pickup_stop
    drop_stop = student.drop_stop

    route = student.assigned_route or (bus.route if bus else None)
    active_trip = Trip.query.filter_by(bus_id=bus.id, status='IN_PROGRESS').first()

    stops_data = []
    if route:
        stops = route.stops.order_by(Stop.sequence_order).all()
        stops_data = [{
            'id': s.id,
            'name': s.stop_name,
            'sequence': s.sequence_order,
            'lat': s.latitude,
            'lng': s.longitude,
            'pickup_time': s.scheduled_pickup_time,
            'drop_time': s.scheduled_drop_time,
            'is_child_pickup': bool(pickup_stop and pickup_stop.id == s.id),
            'is_child_drop': bool(drop_stop and drop_stop.id == s.id)
        } for s in stops]

    child_info = {
        'id': student.id,
        'name': student.full_name,
        'status': child_status,
        'status_label': child_status_label,
        'pickup_stop_name': pickup_stop.stop_name if pickup_stop else 'Registered Stop',
        'drop_stop_name': drop_stop.stop_name if drop_stop else 'Registered Stop',
        'pickup_lat': pickup_stop.latitude if pickup_stop else (stops_data[0]['lat'] if stops_data else 19.0760),
        'pickup_lng': pickup_stop.longitude if pickup_stop else (stops_data[0]['lng'] if stops_data else 72.8777),
        'drop_lat': drop_stop.latitude if drop_stop else (stops_data[-1]['lat'] if stops_data else 19.0760),
        'drop_lng': drop_stop.longitude if drop_stop else (stops_data[-1]['lng'] if stops_data else 72.8777)
    }

    return render_template(
        'parent/live_tracking.html',
        student=student,
        bus=bus,
        route=route,
        active_trip=active_trip,
        stops_json=stops_data,
        child_info=child_info
    )


@parent_bp.route('/api/live-bus-location/<int:bus_id>')
@login_required
@role_required('PARENT')
def api_live_bus_location(bus_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        return jsonify({'status': 'ERROR', 'message': 'Parent profile not found.'}), 403

    bus = Bus.query.get_or_404(bus_id)

    # Authorization Check (C1 / SEC-01): Verify parent has a child assigned to this bus
    child = next((s for s in parent.students if s.assigned_bus_id == bus.id), None)
    if not child:
        return jsonify({'status': 'ERROR', 'message': 'Access Denied: You are not authorized to track this bus location.'}), 403

    active_trip = Trip.query.filter_by(bus_id=bus.id, status='IN_PROGRESS').first()

    latest_att = Attendance.query.filter_by(student_id=child.id).order_by(Attendance.verification_time.desc()).first()
    safe_drop = SafeDropConfirmation.query.filter_by(student_id=child.id).order_by(SafeDropConfirmation.bus_arrival_time.desc()).first()

    child_status = 'WAITING_PICKUP'
    child_status_label = 'Waiting at Pickup Stop'
    if safe_drop and safe_drop.status == 'CONFIRMED':
        child_status = 'DROPPED'
        child_status_label = 'Safely Dropped at Destination'
    elif latest_att and latest_att.verification_status == 'VERIFIED':
        child_status = 'ON_BUS'
        child_status_label = 'On Board Bus (AI Verified)'

    pickup_lat = child.pickup_stop.latitude if child.pickup_stop else (bus.route.stops.first().latitude if bus.route and bus.route.stops.first() else 19.0760)
    pickup_lng = child.pickup_stop.longitude if child.pickup_stop else (bus.route.stops.first().longitude if bus.route and bus.route.stops.first() else 72.8777)
    drop_lat = child.drop_stop.latitude if child.drop_stop else pickup_lat
    drop_lng = child.drop_stop.longitude if child.drop_stop else pickup_lng

    if not active_trip:
        if (bus.status == 'ACTIVE' or (bus.driver and bus.driver.is_online)) and bus.current_lat is not None and bus.current_lng is not None:
            return jsonify({
                'status': 'ACTIVE',
                'is_active': True,
                'message': f"Bus {bus.bus_code} is ACTIVE. Mobile GPS streaming live from driver device.",
                'lat': bus.current_lat,
                'lng': bus.current_lng,
                'speed': 0,
                'delay_minutes': 0,
                'child_status': child_status,
                'child_status_label': child_status_label,
                'child_name': child.full_name,
                'child_lat': bus.current_lat,
                'child_lng': bus.current_lng
            })
        c_lat, c_lng = (drop_lat, drop_lng) if child_status == 'DROPPED' else (pickup_lat, pickup_lng)
        return jsonify({
            'status': 'INACTIVE',
            'is_active': False,
            'message': f"Bus {bus.bus_code} is currently off-duty/inactive. Driver is offline.",
            'lat': None,
            'lng': None,
            'speed': 0,
            'delay_minutes': 0,
            'child_status': child_status,
            'child_status_label': child_status_label,
            'child_name': child.full_name,
            'child_lat': c_lat,
            'child_lng': c_lng
        })

    # Latest GPS location & Staleness Calculation derived strictly from driver's mobile device
    latest_gps = GpsLocation.query.filter_by(trip_id=active_trip.id).order_by(GpsLocation.timestamp.desc()).first()

    lat = latest_gps.latitude if latest_gps else active_trip.current_lat
    lng = latest_gps.longitude if latest_gps else active_trip.current_lng
    speed = latest_gps.speed if latest_gps else 0.0

    if lat is None or lng is None:
        c_lat, c_lng = (drop_lat, drop_lng) if child_status == 'DROPPED' else (pickup_lat, pickup_lng)
        return jsonify({
            'status': 'WAITING_GPS',
            'is_active': True,
            'message': f"Driver has started trip for Bus {bus.bus_code}. Awaiting first GPS location fix from mobile device...",
            'lat': None,
            'lng': None,
            'speed': 0,
            'delay_minutes': active_trip.delay_minutes,
            'child_status': child_status,
            'child_status_label': child_status_label,
            'child_name': child.full_name,
            'child_lat': c_lat,
            'child_lng': c_lng
        })

    now = datetime.utcnow()
    ref_time = latest_gps.timestamp if (latest_gps and latest_gps.timestamp) else (active_trip.start_time or now)
    seconds_since_last_update = int((now - ref_time).total_seconds())
    seconds_since_last_update = max(0, seconds_since_last_update)
    is_stale = seconds_since_last_update > 120

    if seconds_since_last_update >= 60:
        last_updated_formatted = f"{seconds_since_last_update // 60}m ago"
    else:
        last_updated_formatted = f"{seconds_since_last_update}s ago"

    # Raise internal GPS_STALE alert if staleness exceeds 10 minutes (600s)
    if seconds_since_last_update > 600:
        existing_stale_alert = Alert.query.filter_by(
            trip_id=active_trip.id,
            alert_type='GPS_STALE',
            is_resolved=False
        ).first()

        if not existing_stale_alert:
            stale_alert = Alert(
                institution_id=active_trip.institution_id,
                bus_id=active_trip.bus_id,
                trip_id=active_trip.id,
                alert_type='GPS_STALE',
                risk_score=25,
                severity='WARNING',
                description=f"GPS SIGNAL STALE: Bus {bus.bus_code} (Trip #{active_trip.id}) has not transmitted GPS updates for {seconds_since_last_update // 60} minutes."
            )
            db.session.add(stale_alert)
            db.session.commit()

    if child_status == 'ON_BUS':
        c_lat, c_lng = lat, lng
    elif child_status == 'DROPPED':
        c_lat, c_lng = drop_lat, drop_lng
    else:
        c_lat, c_lng = pickup_lat, pickup_lng

    return jsonify({
        'status': 'ACTIVE',
        'is_active': True,
        'trip_id': active_trip.id,
        'trip_type': active_trip.trip_type,
        'bus_code': bus.bus_code,
        'lat': lat,
        'lng': lng,
        'speed': speed,
        'delay_minutes': active_trip.delay_minutes,
        'seconds_since_last_update': seconds_since_last_update,
        'is_stale': is_stale,
        'last_updated_formatted': last_updated_formatted,
        'child_status': child_status,
        'child_status_label': child_status_label,
        'child_name': child.full_name,
        'child_lat': c_lat,
        'child_lng': c_lng
    })


@parent_bp.route('/safe-drop/confirm/<int:confirmation_id>', methods=['POST'])
@login_required
@role_required('PARENT')
def confirm_safe_drop(confirmation_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    safe_drop = SafeDropConfirmation.query.get_or_404(confirmation_id)

    if safe_drop.parent_id != parent.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('parent.dashboard'))

    safe_drop.status = 'CONFIRMED'
    safe_drop.confirmation_time = datetime.utcnow()

    # Create notification confirmation
    n = Notification(
        user_id=current_user.id,
        title="✅ Safe Drop Confirmed",
        message=f"Safe drop confirmation recorded for {safe_drop.student.full_name}.",
        category="SAFE_DROP"
    )
    db.session.add(n)
    db.session.commit()

    flash(f"Safe arrival confirmed for {safe_drop.student.full_name}. Thank you!", "success")
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/notifications')
@login_required
@role_required('PARENT')
def notifications():
    user_notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    
    # Mark as read
    for n in user_notifs:
        n.is_read = True
    db.session.commit()

    return render_template('parent/notifications.html', notifications=user_notifs)


@parent_bp.route('/profile/update', methods=['POST'])
@login_required
@role_required('PARENT')
def update_profile():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    emergency_contact = request.form.get('emergency_contact', '').strip()
    relationship = request.form.get('relationship', 'Parent')

    if phone:
        current_user.phone = phone
    if address:
        parent.address = address
    if emergency_contact:
        parent.emergency_contact = emergency_contact
    if relationship:
        parent.relationship = relationship

    db.session.commit()
    flash('Your parent profile details have been updated in the database.', 'success')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/child/add', methods=['POST'])
@login_required
@role_required('PARENT')
def add_child():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    full_name = request.form.get('full_name', '').strip()
    roll_number = request.form.get('roll_number', '').strip()
    grade_section = request.form.get('grade_section', '').strip()

    if not full_name or not roll_number:
        flash('Student full name and roll number are required.', 'warning')
        return redirect(url_for('parent.dashboard'))

    existing = Student.query.filter_by(roll_number=roll_number).first()
    if existing:
        flash('A student with this roll number already exists.', 'danger')
        return redirect(url_for('parent.dashboard'))

    new_child = Student(
        full_name=full_name,
        roll_number=roll_number,
        grade_section=grade_section,
        parent_id=parent.id,
        photo_filename='default_student.png'
    )
    db.session.add(new_child)
    db.session.flush()

    # Generate face vector
    import numpy as np, json
    from app.models import FaceProfile
    vec = (np.random.rand(4096) / 100.0).tolist()
    fp = FaceProfile(student_id=new_child.id, feature_vector_json=json.dumps(vec), image_path=new_child.photo_filename)
    fp.set_vector(vec)
    db.session.add(fp)

    db.session.commit()
    flash(f'Child {full_name} registered successfully under your account.', 'success')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/absence-request/add', methods=['POST'])
@login_required
@role_required('PARENT')
def add_absence_request():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    raw_student_id = request.form.get('student_id')
    if not raw_student_id:
        flash('Please select a valid child student for the absence request.', 'warning')
        return redirect(url_for('parent.dashboard'))
    try:
        student_id = int(raw_student_id)
    except (ValueError, TypeError):
        flash('Invalid student selection.', 'danger')
        return redirect(url_for('parent.dashboard'))

    absence_date = request.form.get('absence_date', datetime.utcnow().strftime('%Y-%m-%d')).strip()
    session_type = request.form.get('session_type', 'FULL_DAY')
    reason = request.form.get('reason', 'Sick Leave').strip()

    student = Student.query.get_or_404(student_id)
    if student.parent_id != parent.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('parent.dashboard'))

    now = datetime.utcnow()
    today_str = now.strftime('%Y-%m-%d')
    
    cutoff_hour = getattr(current_app, 'config', {}).get('ABSENCE_CUTOFF_HOUR', 7)
    cutoff_minute = getattr(current_app, 'config', {}).get('ABSENCE_CUTOFF_MINUTE', 30)
    
    is_late = False
    if absence_date == today_str:
        if now.hour > cutoff_hour or (now.hour == cutoff_hour and now.minute >= cutoff_minute):
            is_late = True

    status_str = 'SUBMITTED_LATE' if is_late else 'SUBMITTED'

    # Check if request already submitted for this date
    existing = StudentAbsenceRequest.query.filter_by(
        student_id=student.id,
        absence_date=absence_date
    ).filter(StudentAbsenceRequest.status != 'CANCELLED').first()

    if existing:
        flash(f'{student.full_name} is already marked absent for {absence_date}.', 'info')
        return redirect(url_for('parent.dashboard'))

    absence_req = StudentAbsenceRequest(
        student_id=student.id,
        parent_id=parent.id,
        absence_date=absence_date,
        session_type=session_type,
        reason=reason,
        status=status_str
    )
    db.session.add(absence_req)

    # Notify driver if student is assigned to a bus
    if student.assigned_bus:
        from app.models import Driver
        driver = student.assigned_bus.driver or Driver.query.filter_by(assigned_bus_id=student.assigned_bus_id).first()
        if driver and driver.user_id:
            from app.notifications.service import send_notification
            send_notification(
                user_id=driver.user_id,
                title="🚌 Absence Update Received",
                message=f"{'⚠️ LATE ' if is_late else ''}Absence logged for {student.full_name} on {absence_date} ({reason}).",
                category="INFO"
            )

    # Send Notification confirmation to Parent
    n_parent = Notification(
        user_id=current_user.id,
        title="🤒 Absence Request Filed" + (" (Late)" if is_late else ""),
        message=f"Leave request recorded for {student.full_name} on {absence_date} ({reason}).{' Note: Submitted after cutoff.' if is_late else ''}",
        category="LEAVE"
    )
    db.session.add(n_parent)

    db.session.commit()

    if is_late:
        flash(f'Absence request submitted for {student.full_name} (Submitted past the {cutoff_hour:02d}:{cutoff_minute:02d} cutoff time). Bus driver updated urgently.', 'warning')
    else:
        flash(f'Absence request submitted for {student.full_name} on {absence_date}. Bus driver has been updated.', 'success')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/absence-request/cancel/<int:request_id>', methods=['POST'])
@login_required
@role_required('PARENT')
def cancel_absence_request(request_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    absence_req = StudentAbsenceRequest.query.get_or_404(request_id)

    if absence_req.parent_id != parent.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('parent.dashboard'))

    absence_req.status = 'CANCELLED'
    db.session.commit()

    flash(f'Absence request for {absence_req.student.full_name} has been cancelled.', 'info')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/proximity-preferences', methods=['POST'])
@login_required
@role_required('PARENT')
def update_proximity_preferences():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('auth.login'))

    try:
        radius = int(request.form.get('proximity_radius_meters', 500))
        parent.proximity_radius_meters = radius
        db.session.commit()
        flash(f'Proximity alert threshold updated to {radius} meters.', 'success')
    except Exception:
        flash('Invalid proximity radius value.', 'danger')

    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/dsar/export/<int:student_id>')
@login_required
@role_required('PARENT')
def dsar_export(student_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    student = db.session.get(Student, student_id)
    if not student or student.parent_id != parent.id:
        flash('Unauthorized access or student not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    from app.ai.governance import export_student_dsar_data
    data = export_student_dsar_data(student.id)
    return jsonify(data)


@parent_bp.route('/dsar/delete-biometrics/<int:student_id>', methods=['POST'])
@login_required
@role_required('PARENT')
def dsar_delete_biometrics(student_id):
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    student = db.session.get(Student, student_id)
    if not student or student.parent_id != parent.id:
        flash('Unauthorized access or student not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    from app.ai.governance import delete_student_biometrics
    success, msg = delete_student_biometrics(student.id, user_id=current_user.id)
    if success:
        flash(msg, 'success')
    else:
        flash(msg, 'danger')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/api/daily-digest', methods=['POST', 'GET'])
@login_required
@role_required('PARENT')
def api_daily_digest():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        return jsonify({'status': 'ERROR', 'message': 'Parent profile not found'}), 403

    from app.notifications.service import generate_daily_arrival_digest
    notifs = generate_daily_arrival_digest(parent_id=parent.id)
    digest_msg = notifs[0].message if notifs else "No digest generated"
    return jsonify({
        'status': 'SUCCESS',
        'message': 'Daily digest generated successfully',
        'digest': digest_msg
    })


@parent_bp.route('/api/family-status')
@login_required
@role_required('PARENT')
def api_family_status():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        return jsonify({'status': 'ERROR', 'message': 'Parent profile not found'}), 403

    children = parent.students.all()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    family_data = []
    for st in children:
        bus_info = {
            'bus_id': st.assigned_bus_id,
            'bus_code': st.assigned_bus.bus_code if st.assigned_bus else None,
            'registration_number': st.assigned_bus.registration_number if st.assigned_bus else None
        }

        # Current active trip for student's bus
        active_trip = None
        if st.assigned_bus_id:
            trip_obj = Trip.query.filter_by(bus_id=st.assigned_bus_id, status='IN_PROGRESS').first()
            if trip_obj:
                active_trip = {
                    'trip_id': trip_obj.id,
                    'trip_type': trip_obj.trip_type,
                    'status': trip_obj.status,
                    'current_lat': trip_obj.current_lat,
                    'current_lng': trip_obj.current_lng
                }

        # Latest attendance today
        latest_att = Attendance.query.filter(
            Attendance.student_id == st.id,
            db.func.date(Attendance.verification_time) == today_str
        ).order_by(Attendance.verification_time.desc()).first()

        att_data = None
        if latest_att:
            att_data = {
                'verification_status': latest_att.verification_status,
                'scan_type': latest_att.scan_type,
                'is_dropped_off': latest_att.is_dropped_off,
                'verification_time': latest_att.verification_time.isoformat() if latest_att.verification_time else None,
                'drop_verification_time': latest_att.drop_verification_time.isoformat() if latest_att.drop_verification_time else None
            }

        # Absence today
        absence = StudentAbsenceRequest.query.filter(
            StudentAbsenceRequest.student_id == st.id,
            StudentAbsenceRequest.absence_date == today_str,
            StudentAbsenceRequest.status != 'CANCELLED'
        ).first()

        absence_data = None
        if absence:
            absence_data = {
                'reason': absence.reason,
                'status': absence.status,
                'session_type': absence.session_type
            }

        family_data.append({
            'student_id': st.id,
            'full_name': st.full_name,
            'roll_number': st.roll_number,
            'bus': bus_info,
            'active_trip': active_trip,
            'attendance_today': att_data,
            'absence_today': absence_data
        })

    return jsonify({
        'status': 'SUCCESS',
        'children_count': len(family_data),
        'children': family_data
    })


@parent_bp.route('/escort/add', methods=['POST'])
@login_required
@role_required('PARENT')
def add_authorized_escort():
    parent = Parent.query.filter_by(user_id=current_user.id).first()
    if not parent:
        flash('Parent profile not found.', 'danger')
        return redirect(url_for('parent.dashboard'))

    student_id = request.form.get('student_id')
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    relationship = request.form.get('relationship', 'Relative').strip()
    id_proof = request.form.get('id_proof_number', '').strip()

    if not student_id or not full_name or not phone:
        flash('Please fill in all required fields (Student, Full Name, Phone).', 'warning')
        return redirect(url_for('parent.dashboard'))

    student = db.session.get(Student, int(student_id))
    if not student or student.parent_id != parent.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('parent.dashboard'))

    from app.models import AuthorizedEscort
    escort = AuthorizedEscort(
        student_id=student.id,
        parent_id=parent.id,
        full_name=full_name,
        phone=phone,
        relationship=relationship,
        id_proof_number=id_proof,
        is_active=True
    )
    db.session.add(escort)
    db.session.commit()

    flash(f'Authorized escort {full_name} added for {student.full_name}.', 'success')
    return redirect(url_for('parent.dashboard'))


@parent_bp.route('/api/escorts/<int:student_id>')
@login_required
def api_get_student_escorts(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'status': 'ERROR', 'message': 'Student not found'}), 404

    from app.models import AuthorizedEscort
    escorts = AuthorizedEscort.query.filter_by(student_id=student.id, is_active=True).all()
    data = [{
        'id': e.id,
        'full_name': e.full_name,
        'phone': e.phone,
        'relationship': e.relationship,
        'id_proof_number': e.id_proof_number,
        'photo_url': f'/static/uploads/escorts/{e.photo_path}' if e.photo_path else '/static/images/avatar.png'
    } for e in escorts]

    return jsonify({
        'status': 'SUCCESS',
        'student_id': student.id,
        'escorts_count': len(data),
        'escorts': data
    })




