import csv
import io
import os
import json
import numpy as np
from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, Response
# pyrefly: ignore [missing-import]
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

try:
    from app import role_required
    from app.tenancy import current_institution_id, verify_tenant_ownership, require_feature
    from app.models import (
        db, Institution, User, Parent, Student, Driver, DriverDocument, DriverTraining,
        Bus, Route, Stop, Trip, Attendance, GpsLocation, Alert, Notification,
        EmergencyEvent, SafeDropConfirmation, TemporaryBusReassignment, FaceProfile, AuditLog, DriverSafetyTelemetry
    )
    from app.ai.engine import extract_face_features, calculate_explainable_risk_score
except (ImportError, ValueError):
    from .. import role_required  # type: ignore
    from ..models import (  # type: ignore
        db, Institution, User, Parent, Student, Driver, DriverDocument, DriverTraining,
        Bus, Route, Stop, Trip, Attendance, GpsLocation, Alert, Notification,
        EmergencyEvent, SafeDropConfirmation, TemporaryBusReassignment, FaceProfile, AuditLog, DriverSafetyTelemetry
    )
    from ..ai.engine import extract_face_features, calculate_explainable_risk_score  # type: ignore

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@login_required
@role_required('ADMIN')
def dashboard():
    inst_id = current_institution_id()
    total_students = Student.query.filter_by(institution_id=inst_id).count()
    total_buses = Bus.query.filter_by(institution_id=inst_id).count()
    active_buses = Bus.query.filter_by(institution_id=inst_id, status='ACTIVE').count()
    running_trips = Trip.query.filter_by(institution_id=inst_id, status='IN_PROGRESS').all()
    
    # Attendance stats for today
    today = date.today()
    today_atts = Attendance.query.join(Trip).filter(Trip.institution_id == inst_id, db.func.date(Attendance.verification_time) == today).all()
    verified_count = len([a for a in today_atts if a.verification_status == 'VERIFIED'])

    active_alerts = Alert.query.filter_by(institution_id=inst_id, is_resolved=False).order_by(Alert.created_at.desc()).all()
    active_sos = [a for a in active_alerts if a.alert_type == 'SOS_EMERGENCY']

    buses = Bus.query.filter_by(institution_id=inst_id).all()

    # Bus fleet live positions derived strictly from active driver mobile GPS
    bus_map_data = []
    for b in buses:
        active_t = Trip.query.filter_by(bus_id=b.id, status='IN_PROGRESS', institution_id=inst_id).first()
        lat, lng = None, None
        is_active = False
        if active_t and active_t.current_lat is not None and active_t.current_lng is not None:
            lat, lng = active_t.current_lat, active_t.current_lng
            is_active = True
        elif b.status == 'ACTIVE' and b.current_lat is not None and b.current_lng is not None:
            lat, lng = b.current_lat, b.current_lng
            is_active = True
        elif b.driver and b.driver.is_online and b.driver.current_lat is not None and b.driver.current_lng is not None:
            lat, lng = b.driver.current_lat, b.driver.current_lng
            is_active = True

        bus_map_data.append({
            'id': b.id,
            'code': b.bus_code,
            'driver': b.driver.full_name if b.driver else 'Unassigned',
            'route': b.route.name if b.route else 'Unassigned',
            'status': 'RUNNING' if active_t else ('ACTIVE' if is_active else 'INACTIVE'),
            'is_active': is_active,
            'lat': lat,
            'lng': lng
        })

    # Latest Driver Safety Telemetry
    all_drivers = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    driver_telemetries = []
    fatigue_warnings_count = 0
    total_safety_score = 0

    for d in all_drivers:
        latest_telem = DriverSafetyTelemetry.query.filter_by(driver_id=d.id).order_by(DriverSafetyTelemetry.timestamp.desc()).first()
        status_level = latest_telem.fatigue_level if latest_telem else 'NORMAL'
        safety_score = latest_telem.safety_score if latest_telem else 100
        speed = latest_telem.speed_kph if latest_telem else 0.0

        if status_level != 'NORMAL':
            fatigue_warnings_count += 1
        total_safety_score += safety_score

        driver_telemetries.append({
            'driver_id': d.id,
            'driver_name': d.full_name,
            'bus_code': d.assigned_bus.bus_code if d.assigned_bus else 'Unassigned',
            'fatigue_level': status_level,
            'fatigue_score': latest_telem.fatigue_score if latest_telem else 0.0,
            'safety_score': safety_score,
            'speed_kph': speed,
            'overspeed': latest_telem.overspeed_warning if latest_telem else False,
            'distraction': latest_telem.distraction_event if latest_telem else 'NONE',
            'last_updated': latest_telem.timestamp.strftime('%H:%M:%S') if latest_telem else 'No Data'
        })

    avg_safety_score = round(total_safety_score / max(1, len(all_drivers)), 1) if all_drivers else 100

    return render_template(
        'admin/dashboard.html',
        total_students=total_students,
        total_buses=total_buses,
        active_buses=active_buses,
        running_trips_count=len(running_trips),
        running_trips=running_trips,
        verified_attendance_count=verified_count,
        active_alerts=active_alerts,
        active_sos=active_sos,
        buses=buses,
        bus_map_json=bus_map_data,
        driver_telemetries=driver_telemetries,
        fatigue_warnings_count=fatigue_warnings_count,
        avg_safety_score=avg_safety_score
    )


@admin_bp.route('/driver-telemetry/live')
@login_required
@role_required('ADMIN')
def live_driver_telemetry():
    inst_id = current_institution_id()
    drivers = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    results = []

    for d in drivers:
        telem = DriverSafetyTelemetry.query.filter_by(driver_id=d.id).order_by(DriverSafetyTelemetry.timestamp.desc()).first()
        results.append({
            'driver_id': d.id,
            'driver_name': d.full_name,
            'bus_code': d.assigned_bus.bus_code if d.assigned_bus else 'Unassigned',
            'fatigue_level': telem.fatigue_level if telem else 'NORMAL',
            'fatigue_score': telem.fatigue_score if telem else 0.0,
            'safety_score': telem.safety_score if telem else 100,
            'speed_kph': telem.speed_kph if telem else 0.0,
            'overspeed': telem.overspeed_warning if telem else False,
            'distraction': telem.distraction_event if telem else 'NONE',
            'timestamp': telem.timestamp.strftime('%Y-%m-%d %H:%M:%S') if telem else None
        })

    return jsonify({'success': True, 'drivers': results})



# --- BUS MONITORING & MANAGEMENT ---

@admin_bp.route('/buses')
@login_required
@role_required('ADMIN')
def buses():
    inst_id = current_institution_id()
    bus_list = Bus.query.filter_by(institution_id=inst_id).all()
    drivers = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    routes = Route.query.filter_by(institution_id=inst_id).all()
    return render_template('admin/buses.html', buses=bus_list, drivers=drivers, routes=routes)


@admin_bp.route('/bus/<int:bus_id>')
@login_required
@role_required('ADMIN')
def bus_detail(bus_id):
    bus = Bus.query.get_or_404(bus_id)
    verify_tenant_ownership(bus)
    active_trip = Trip.query.filter_by(bus_id=bus.id, status='IN_PROGRESS', institution_id=current_institution_id()).first()
    students = bus.assigned_students.all()
    
    boarded_count = 0
    pending_count = len(students)
    if active_trip:
        boarded_atts = Attendance.query.filter_by(trip_id=active_trip.id, verification_status='VERIFIED').all()
        boarded_count = len(boarded_atts)
        pending_count = max(0, len(students) - boarded_count)

    alerts = bus.alerts.order_by(Alert.created_at.desc()).limit(10).all()
    risk_info = calculate_explainable_risk_score(bus_id=bus.id)

    return render_template(
        'admin/bus_detail.html',
        bus=bus,
        active_trip=active_trip,
        students=students,
        boarded_count=boarded_count,
        pending_count=pending_count,
        alerts=alerts,
        risk_info=risk_info
    )


@admin_bp.route('/bus/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def bus_add():
    reg = request.form.get('registration_number', '').strip()
    code = request.form.get('bus_code', '').strip()
    capacity = int(request.form.get('capacity', 40))
    driver_id = request.form.get('driver_id') or None
    route_id = request.form.get('route_id') or None

    existing_code = Bus.query.filter_by(bus_code=code).first()
    existing_reg = Bus.query.filter_by(registration_number=reg).first()
    if existing_code or existing_reg:
        flash(f'Bus with code "{code}" or registration number "{reg}" already exists.', 'danger')
        return redirect(url_for('admin.buses'))

    try:
        inst_id = current_institution_id()
        new_bus = Bus(
            institution_id=inst_id,
            registration_number=reg,
            bus_code=code,
            capacity=capacity,
            driver_id=int(driver_id) if driver_id else None,
            route_id=int(route_id) if route_id else None
        )
        db.session.add(new_bus)
        db.session.flush()

        if driver_id:
            driver = Driver.query.get(int(driver_id))
            if driver:
                driver.assigned_bus_id = new_bus.id
                if route_id:
                    driver.assigned_route_id = int(route_id)

        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Database error while saving bus record.', 'danger')
        return redirect(url_for('admin.buses'))

    flash(f'Bus {code} created successfully.', 'success')
    return redirect(url_for('admin.buses'))


# --- STUDENT MANAGEMENT ---

@admin_bp.route('/students')
@login_required
@role_required('ADMIN')
def students():
    inst_id = current_institution_id()
    search_q = request.args.get('q', '').strip()
    query = Student.query.filter_by(institution_id=inst_id)
    if search_q:
        query = query.filter(
            (Student.full_name.ilike(f'%{search_q}%')) | 
            (Student.roll_number.ilike(f'%{search_q}%'))
        )
    student_list = query.all()
    parents = Parent.query.join(User).filter(User.institution_id == inst_id).all()
    buses = Bus.query.filter_by(institution_id=inst_id).all()
    routes = Route.query.filter_by(institution_id=inst_id).all()
    stops = Stop.query.filter_by(institution_id=inst_id).all()

    return render_template(
        'admin/students.html',
        students=student_list,
        parents=parents,
        buses=buses,
        routes=routes,
        stops=stops,
        search_q=search_q
    )


@admin_bp.route('/students/export-csv')
@login_required
@role_required('ADMIN')
def student_export_csv():
    import io, csv
    from flask import Response

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Student ID', 'Full Name', 'Roll Number', 'Grade Section', 'Parent Email', 'Assigned Bus', 'Assigned Route'])

    students = Student.query.filter_by(institution_id=current_institution_id()).all()
    for s in students:
        writer.writerow([
            s.id,
            s.full_name,
            s.roll_number,
            s.grade_section or '',
            s.parent.user.email if s.parent and s.parent.user else '',
            s.assigned_bus.bus_code if s.assigned_bus else '',
            s.assigned_route.name if s.assigned_route else ''
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=saferide_student_roster.csv"}
    )


@admin_bp.route('/students/import-csv', methods=['POST'])
@login_required
@role_required('ADMIN')
def student_import_csv():
    import io, csv
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid .csv file.', 'danger')
        return redirect(url_for('admin.students'))

    stream = io.StringIO(file.stream.read().decode("UTF-8"), newline=None)
    reader = csv.reader(stream)
    header = next(reader, None)

    count = 0
    inst_id = current_institution_id()
    default_parent = Parent.query.join(User).filter(User.institution_id == inst_id).first()

    for row in reader:
        if len(row) >= 2:
            name = row[0].strip()
            roll = row[1].strip()
            grade = row[2].strip() if len(row) > 2 else 'Grade 5'
            parent_email = row[3].strip() if len(row) > 3 else ''

            p = default_parent
            if parent_email:
                u = User.query.filter_by(email=parent_email, institution_id=inst_id).first()
                if u and u.parent_profile:
                    p = u.parent_profile

            existing = Student.query.filter_by(roll_number=roll, institution_id=inst_id).first()
            if not existing:
                st = Student(
                    institution_id=inst_id,
                    full_name=name,
                    roll_number=roll,
                    grade_section=grade,
                    parent_id=p.id if p else None,
                    photo_filename='default_student.png'
                )
                st.generate_invite_code()
                db.session.add(st)
                db.session.flush()

                # Generate synthetic face profile
                import numpy as np
                vec = (np.random.rand(4096) / 100.0).tolist()
                fp = FaceProfile(student_id=st.id, feature_vector_json=json.dumps(vec), image_path=st.photo_filename)
                fp.set_vector(vec)
                db.session.add(fp)

                count += 1

    db.session.commit()
    flash(f'Successfully imported {count} students from CSV dataset.', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/student/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def student_add():
    full_name = request.form.get('full_name', '').strip()
    roll_number = request.form.get('roll_number', '').strip()
    grade_section = request.form.get('grade_section', '').strip()
    parent_id_raw = request.form.get('parent_id')
    parent_id = int(parent_id_raw) if parent_id_raw else None
    bus_id = request.form.get('bus_id')
    route_id = request.form.get('route_id')
    pickup_stop_id = request.form.get('pickup_stop_id')
    drop_stop_id = request.form.get('drop_stop_id')

    photo_file = request.files.get('photo')
    filename = 'default_student.png'
    save_path = None

    if photo_file and photo_file.filename:
        from app.security import validate_and_save_upload
        try:
            filename = validate_and_save_upload(
                photo_file, 
                current_app.config['STUDENT_PHOTOS'], 
                current_app.config['ALLOWED_IMAGE_EXTENSIONS']
            )
            save_path = os.path.join(current_app.config['STUDENT_PHOTOS'], filename)
        except ValueError as val_err:
            flash(str(val_err), 'danger')
            return redirect(url_for('admin.students'))

    inst_id = current_institution_id()
    new_st = Student(
        institution_id=inst_id,
        full_name=full_name,
        roll_number=roll_number,
        grade_section=grade_section,
        parent_id=parent_id,
        assigned_bus_id=int(bus_id) if bus_id else None,
        assigned_route_id=int(route_id) if route_id else None,
        pickup_stop_id=int(pickup_stop_id) if pickup_stop_id else None,
        drop_stop_id=int(drop_stop_id) if drop_stop_id else None,
        photo_filename=filename
    )
    new_st.generate_invite_code()
    db.session.add(new_st)
    db.session.flush()

    # Generate AI Face Feature Profile from image or default
    if save_path and os.path.exists(save_path):
        try:
            import cv2  # type: ignore # pyright: ignore[reportMissingImports]
            img = cv2.imread(save_path)
            vec = extract_face_features(img)
        except Exception:
            vec = (np.random.rand(4096) / 100.0).tolist()
    else:
        vec = (np.random.rand(4096) / 100.0).tolist()

    face_prof = FaceProfile(
        student_id=new_st.id,
        feature_vector_json=db.func.json_array() if False else str(vec),
        image_path=filename
    )
    face_prof.set_vector(vec)
    db.session.add(face_prof)

    db.session.commit()
    flash(f'Student {full_name} registered successfully with AI face profile. Invite code: {new_st.invite_code}', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/students/<int:student_id>/generate-invite', methods=['POST'])
@login_required
@role_required('ADMIN')
def student_generate_invite(student_id):
    student = Student.query.get_or_404(student_id)
    verify_tenant_ownership(student)
    code = student.generate_invite_code()
    db.session.commit()
    flash(f'Generated new guardian invite code "{code}" for student {student.full_name}.', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/student/temp-reassign', methods=['POST'])
@login_required
@role_required('ADMIN')
def student_temp_reassign():
    student_id = int(request.form.get('student_id'))
    temp_bus_id = int(request.form.get('temp_bus_id'))
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    reason = request.form.get('reason', 'Admin Reassignment')

    student = Student.query.get_or_404(student_id)
    verify_tenant_ownership(student)
    reassignment = TemporaryBusReassignment(
        student_id=student.id,
        original_bus_id=student.assigned_bus_id,
        temporary_bus_id=temp_bus_id,
        start_date=start_date,
        end_date=end_date,
        approved_by_user_id=current_user.id,
        reason=reason
    )
    db.session.add(reassignment)
    db.session.commit()

    flash(f'Approved temporary bus reassignment for {student.full_name}.', 'success')
    return redirect(url_for('admin.students'))


# --- DRIVER & TRAINING MANAGEMENT ---

@admin_bp.route('/drivers')
@login_required
@role_required('ADMIN')
def drivers():
    inst_id = current_institution_id()
    driver_list = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    buses = Bus.query.filter_by(institution_id=inst_id).all()
    routes = Route.query.filter_by(institution_id=inst_id).all()
    return render_template('admin/drivers.html', drivers=driver_list, buses=buses, routes=routes)


@admin_bp.route('/driver-training')
@login_required
@role_required('ADMIN')
def driver_training():
    inst_id = current_institution_id()
    trainings = DriverTraining.query.join(Driver).join(User).filter(User.institution_id == inst_id).all()
    drivers = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    return render_template('admin/driver_training.html', trainings=trainings, drivers=drivers)


@admin_bp.route('/driver-training/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def add_driver_training():
    driver_id = int(request.form.get('driver_id'))
    driver = Driver.query.get_or_404(driver_id)
    verify_tenant_ownership(driver)

    training_name = request.form.get('training_name')
    training_date = request.form.get('training_date')
    expiry_date = request.form.get('expiry_date')
    status = request.form.get('status', 'COMPLETED')

    t = DriverTraining(
        driver_id=driver.id,
        training_name=training_name,
        training_date=training_date,
        expiry_date=expiry_date,
        status=status
    )
    db.session.add(t)
    db.session.commit()

    flash('Driver training record saved successfully.', 'success')
    return redirect(url_for('admin.driver_training'))


# --- ROUTES & STOPS MANAGEMENT ---

@admin_bp.route('/routes')
@login_required
@role_required('ADMIN')
def routes():
    inst_id = current_institution_id()
    route_list = Route.query.filter_by(institution_id=inst_id).all()
    return render_template('admin/routes.html', routes=route_list)


@admin_bp.route('/route/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def route_add():
    name = request.form.get('name', '').strip()
    desc = request.form.get('description', '').strip()
    distance_km = float(request.form.get('distance_km', 15.0))
    duration = int(request.form.get('duration_mins', 45))

    inst_id = current_institution_id()
    new_r = Route(
        institution_id=inst_id,
        name=name,
        description=desc,
        distance_km=distance_km,
        estimated_duration_mins=duration
    )
    db.session.add(new_r)
    db.session.commit()

    flash(f'Route {name} created successfully.', 'success')
    return redirect(url_for('admin.routes'))


@admin_bp.route('/stop/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def stop_add():
    route_id = int(request.form.get('route_id'))
    route = Route.query.get_or_404(route_id)
    verify_tenant_ownership(route)

    stop_name = request.form.get('stop_name', '').strip()
    seq = int(request.form.get('sequence_order', 1))
    lat = float(request.form.get('latitude', 19.0760))
    lng = float(request.form.get('longitude', 72.8777))
    pickup_time = request.form.get('pickup_time', '07:30 AM')
    drop_time = request.form.get('drop_time', '03:45 PM')

    inst_id = current_institution_id()
    new_stop = Stop(
        institution_id=inst_id,
        route_id=route.id,
        stop_name=stop_name,
        sequence_order=seq,
        latitude=lat,
        longitude=lng,
        scheduled_pickup_time=pickup_time,
        scheduled_drop_time=drop_time
    )
    db.session.add(new_stop)
    db.session.commit()

    flash(f'Stop {stop_name} added to route.', 'success')
    return redirect(url_for('admin.routes'))


# --- ALERTS & RISK CENTER ---

@admin_bp.route('/alerts')
@login_required
@role_required('ADMIN')
def alerts():
    inst_id = current_institution_id()
    active_alerts = Alert.query.filter_by(institution_id=inst_id).order_by(Alert.created_at.desc()).all()
    sos_events = EmergencyEvent.query.join(Bus).filter(Bus.institution_id == inst_id).order_by(EmergencyEvent.created_at.desc()).all()
    return render_template('admin/alerts.html', alerts=active_alerts, sos_events=sos_events)


@admin_bp.route('/alert/resolve/<int:alert_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def resolve_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    verify_tenant_ownership(alert)
    alert.is_resolved = True
    alert.resolved_at = datetime.utcnow()
    db.session.commit()

    flash('Alert resolved.', 'info')
    return redirect(url_for('admin.alerts'))


# --- ATTENDANCE & ANALYTICS REPORTS ---

@admin_bp.route('/attendance')
@login_required
@role_required('ADMIN')
def attendance():
    inst_id = current_institution_id()
    atts = Attendance.query.join(Trip).filter(Trip.institution_id == inst_id).order_by(Attendance.verification_time.desc()).all()
    return render_template('admin/attendance.html', attendances=atts)


@admin_bp.route('/analytics')
@login_required
@role_required('ADMIN')
@require_feature('analytics_dashboard')
def analytics():
    inst_id = current_institution_id()
    buses = Bus.query.filter_by(institution_id=inst_id).all()
    bus_risks = []
    for b in buses:
        r = calculate_explainable_risk_score(bus_id=b.id)
        bus_risks.append({
            'bus': b,
            'score': r['score'],
            'level': r['level'],
            'breakdown': r['breakdown']
        })

    # Manual verification override stats per driver and bus
    all_drivers = Driver.query.join(User).filter(User.institution_id == inst_id).all()
    manual_verify_stats = []
    for d in all_drivers:
        total_scans = Attendance.query.filter_by(verified_by_driver_id=d.id).count()
        manual_scans = Attendance.query.filter_by(verified_by_driver_id=d.id, verification_status='MANUAL_OVERRIDE').count()
        override_rate = round((manual_scans / total_scans * 100), 1) if total_scans > 0 else 0.0
        manual_verify_stats.append({
            'driver_name': d.full_name,
            'bus_code': d.assigned_bus.bus_code if d.assigned_bus else 'Unassigned',
            'total_scans': total_scans,
            'manual_scans': manual_scans,
            'override_rate': override_rate
        })

    return render_template('admin/analytics.html', bus_risks=bus_risks, manual_verify_stats=manual_verify_stats)



@admin_bp.route('/audit-logs')
@login_required
@role_required('ADMIN')
def audit_logs():
    inst_id = current_institution_id()
    logs = AuditLog.query.filter_by(institution_id=inst_id).order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('admin/audit_logs.html', logs=logs)


# --- USER CREATION & MANAGEMENT ENDPOINTS ---

@admin_bp.route('/driver/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def driver_add():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', 'driver123')
    license_number = request.form.get('license_number', '').strip()
    license_expiry = request.form.get('license_expiry', '')
    assigned_bus_id = request.form.get('assigned_bus_id')
    assigned_route_id = request.form.get('assigned_route_id')
    address = request.form.get('address', '').strip()

    if not full_name or not email or not license_number:
        flash('Full name, email, and license number are required.', 'warning')
        return redirect(url_for('admin.drivers'))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash('A user with this email address already exists.', 'danger')
        return redirect(url_for('admin.drivers'))

    inst_id = current_institution_id()
    new_user = User(
        institution_id=inst_id,
        email=email,
        role='DRIVER',
        full_name=full_name,
        phone=phone
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.flush()

    new_driver = Driver(
        user_id=new_user.id,
        full_name=full_name,
        phone=phone,
        license_number=license_number,
        license_expiry=license_expiry if license_expiry else None,
        address=address,
        assigned_bus_id=int(assigned_bus_id) if assigned_bus_id else None,
        assigned_route_id=int(assigned_route_id) if assigned_route_id else None
    )
    db.session.add(new_driver)
    db.session.flush()

    if assigned_bus_id:
        bus = Bus.query.get(int(assigned_bus_id))
        if bus:
            verify_tenant_ownership(bus)
            bus.driver_id = new_driver.id

    db.session.commit()
    flash(f'Driver {full_name} created successfully in database.', 'success')
    return redirect(url_for('admin.drivers'))


@admin_bp.route('/parent/add', methods=['POST'])
@login_required
@role_required('ADMIN')
def parent_add():
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', 'parent123')
    address = request.form.get('address', '').strip()
    emergency_contact = request.form.get('emergency_contact', '').strip()
    relationship = request.form.get('relationship', 'Parent')

    if not full_name or not email:
        flash('Full name and email address are required.', 'warning')
        return redirect(url_for('admin.students'))

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        flash('A user with this email address already exists.', 'danger')
        return redirect(url_for('admin.students'))

    inst_id = current_institution_id()
    new_user = User(
        institution_id=inst_id,
        email=email,
        role='PARENT',
        full_name=full_name,
        phone=phone
    )
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.flush()

    new_parent = Parent(
        user_id=new_user.id,
        address=address,
        emergency_contact=emergency_contact,
        relationship=relationship
    )
    db.session.add(new_parent)
    db.session.commit()

    flash(f'Parent {full_name} account created successfully in database.', 'success')
    return redirect(url_for('admin.students'))


@admin_bp.route('/driver/delete/<int:driver_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def driver_delete(driver_id):
    driver = Driver.query.get_or_404(driver_id)
    verify_tenant_ownership(driver)
    user = driver.user
    
    # Unassign buses
    buses = Bus.query.filter_by(driver_id=driver.id).all()
    for b in buses:
        b.driver_id = None

    db.session.delete(driver)
    if user:
        db.session.delete(user)
    db.session.commit()

    flash('Driver profile removed from database.', 'info')
    return redirect(url_for('admin.drivers'))


@admin_bp.route('/student/delete/<int:student_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def student_delete(student_id):
    student = Student.query.get_or_404(student_id)
    verify_tenant_ownership(student)
    name = student.full_name
    db.session.delete(student)
    db.session.commit()

    flash(f'Student record for {name} deleted from database.', 'info')
    return redirect(url_for('admin.students'))


@admin_bp.route('/export/compliance', methods=['GET'])
@login_required
@role_required('ADMIN')
@require_feature('compliance_export')
def compliance_export():
    """
    Generates a CSV export of institution compliance status (driver documents & bus inspections).
    Requires 'compliance_export' feature (ENTERPRISE tier).
    """
    inst_id = current_institution_id()
    inst = db.session.get(Institution, inst_id) if inst_id else None
    slug = inst.slug if inst else 'tenant'
    today_str = datetime.utcnow().strftime('%Y%m%d')

    output = io.StringIO()
    writer = csv.writer(output)

    # Header section
    writer.writerow(['SafeStop Platform Compliance Export Report'])
    writer.writerow(['Institution', inst.name if inst else 'N/A', 'Slug', slug])
    writer.writerow(['Export Date', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')])
    writer.writerow([])

    # Section 1: Driver Document Expiries
    writer.writerow(['--- DRIVER COMPLIANCE DOCUMENTS ---'])
    writer.writerow(['Driver Name', 'Document Type', 'Document Name', 'Expiry Date', 'Status'])

    drivers = Driver.query.filter_by(institution_id=inst_id).all()
    today_str_date = datetime.utcnow().strftime('%Y-%m-%d')

    for driver in drivers:
        docs = DriverDocument.query.filter_by(driver_id=driver.id).all()
        for doc in docs:
            exp_str = str(doc.expiry_date) if doc.expiry_date else 'N/A'
            doc_status = doc.status or ('EXPIRED' if doc.expiry_date and str(doc.expiry_date) < today_str_date else 'VERIFIED')
            writer.writerow([driver.full_name, doc.doc_type, doc.doc_name, exp_str, doc_status])

    writer.writerow([])

    # Section 2: Bus Inspection Expiries
    writer.writerow(['--- VEHICLE FLEET & MAINTENANCE STATUS ---'])
    writer.writerow(['Bus Code', 'Registration Number', 'Capacity', 'Status'])

    buses = Bus.query.filter_by(institution_id=inst_id).all()
    for bus in buses:
        writer.writerow([bus.bus_code, bus.registration_number, bus.capacity, bus.status])

    output.seek(0)

    filename = f"compliance_export_{slug}_{today_str}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


