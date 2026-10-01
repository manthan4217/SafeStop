import pytest  # type: ignore # pyright: ignore[reportMissingImports]
import json
import numpy as np
from sqlalchemy.exc import IntegrityError  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, User, Parent, Student, Driver, Bus, Route, Stop, Trip, Attendance, Alert, SafeDropConfirmation
from app.ai.engine import extract_face_features, compare_feature_vectors, identify_student_from_face, check_bus_assignment, calculate_explainable_risk_score
from app.gps.tracker import haversine_distance, process_gps_update
from app.security import generate_password_reset_token, verify_password_reset_token, is_safe_url

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            u_admin = User(email='admin_test@test.com', role='ADMIN', full_name='Admin User')
            u_admin.set_password('pass123')
            
            u_driver1 = User(email='driver1_test@test.com', role='DRIVER', full_name='Driver One')
            u_driver1.set_password('pass123')
            
            u_driver2 = User(email='driver2_test@test.com', role='DRIVER', full_name='Driver Two')
            u_driver2.set_password('pass123')

            u_parent1 = User(email='parent1_test@test.com', role='PARENT', full_name='Parent One')
            u_parent1.set_password('pass123')

            u_parent2 = User(email='parent2_test@test.com', role='PARENT', full_name='Parent Two')
            u_parent2.set_password('pass123')
            
            db.session.add_all([u_admin, u_driver1, u_driver2, u_parent1, u_parent2])
            db.session.commit()
            
        yield client


def test_haversine_distance():
    # Distance between Mumbai Gateway of India (18.9220, 72.8347) and Marine Drive (18.9438, 72.8232) ~2.7 km
    dist = haversine_distance(18.9220, 72.8347, 18.9438, 72.8232)
    assert 2400 < dist < 3000


def test_vector_similarity():
    v1 = [0.1, 0.2, 0.3, 0.4]
    v2 = [0.1, 0.2, 0.3, 0.4]
    sim = compare_feature_vectors(v1, v2)
    assert abs(sim - 1.0) < 0.001

    v3 = [-0.1, -0.2, -0.3, -0.4]
    sim_opp = compare_feature_vectors(v1, v3)
    assert abs(sim_opp - (-1.0)) < 0.001

    # Dimension mismatch
    v_diff = [0.1, 0.2]
    assert compare_feature_vectors(v1, v_diff) == 0.0


def test_wrong_bus_detection(client):
    with client.application.app_context():
        parent_u = User.query.filter_by(email='parent1_test@test.com').first()
        p = Parent(user_id=parent_u.id)
        db.session.add(p)
        db.session.flush()

        b1 = Bus(registration_number='MH-99-TEST-9999', bus_code='BUS-99')
        b2 = Bus(registration_number='MH-98-TEST-8888', bus_code='BUS-98')
        db.session.add_all([b1, b2])
        db.session.flush()

        st = Student(full_name='Aryan Test', roll_number='TEST-01', parent_id=p.id, assigned_bus_id=b1.id)
        db.session.add(st)
        db.session.commit()

        is_ok, reason, code = check_bus_assignment(st.id, b1.id)
        assert is_ok is True
        assert code == 'BUS-99'

        is_wrong, reason_wrong, code_assigned = check_bus_assignment(st.id, b2.id)
        assert is_wrong is False
        assert 'BUS-99' in reason_wrong


def test_authorization_parent_bus_location(client):
    """Test Parent IDOR: Parent cannot track unassigned bus location."""
    with client.application.app_context():
        parent1_user = User.query.filter_by(email='parent1_test@test.com').first()
        p1 = Parent(user_id=parent1_user.id)
        db.session.add(p1)

        b1 = Bus(registration_number='MH-01-BUS-1111', bus_code='BUS-01')
        b2 = Bus(registration_number='MH-02-BUS-2222', bus_code='BUS-02')
        db.session.add_all([b1, b2])
        db.session.flush()

        # Child assigned to Bus 1
        st = Student(full_name='Child One', roll_number='CHILD-01', parent_id=p1.id, assigned_bus_id=b1.id)
        db.session.add(st)
        db.session.commit()

        # Log in as Parent 1
        client.post('/auth/login', data={'email': 'parent1_test@test.com', 'password': 'pass123'})

        # Authorized bus tracking (Bus 1) -> HTTP 200
        res_ok = client.get(f'/parent/api/live-bus-location/{b1.id}')
        assert res_ok.status_code == 200

        # Unauthorized bus tracking (Bus 2) -> HTTP 403 Forbidden
        res_forbidden = client.get(f'/parent/api/live-bus-location/{b2.id}')
        assert res_forbidden.status_code == 403
        assert b'Access Denied' in res_forbidden.data


def test_open_redirect_sanitizer():
    assert is_safe_url('/parent/dashboard') is True
    assert is_safe_url('/admin/dashboard') is True
    assert is_safe_url('https://evil.com') is False
    assert is_safe_url('//evil.com') is False


def test_password_reset_token_flow(client):
    with client.application.app_context():
        user = User.query.filter_by(email='admin_test@test.com').first()
        token = generate_password_reset_token(user.id)
        recovered_id = verify_password_reset_token(token)
        assert recovered_id == user.id


def test_attendance_uniqueness_constraint(client):
    with client.application.app_context():
        parent_u = User.query.filter_by(email='parent1_test@test.com').first()
        p = Parent(user_id=parent_u.id)
        db.session.add(p)

        driver_u = User.query.filter_by(email='driver1_test@test.com').first()
        d = Driver(user_id=driver_u.id, full_name='Driver Test', phone='9999999999', license_number='LIC-100')
        db.session.add(d)

        b = Bus(registration_number='MH-03-BUS-3333', bus_code='BUS-03')
        r = Route(name='Test Route')
        db.session.add_all([b, r])
        db.session.flush()

        st = Student(full_name='Child Unique', roll_number='CHILD-UNIQ', parent_id=p.id, assigned_bus_id=b.id)
        t = Trip(bus_id=b.id, driver_id=d.id, route_id=r.id, trip_type='MORNING_PICKUP', status='IN_PROGRESS')
        db.session.add_all([st, t])
        db.session.commit()

        # First attendance entry
        att1 = Attendance(student_id=st.id, trip_id=t.id, bus_id=b.id, verification_status='VERIFIED')
        db.session.add(att1)
        db.session.commit()

        # Duplicate attendance entry must raise IntegrityError
        with pytest.raises(IntegrityError):
            att2 = Attendance(student_id=st.id, trip_id=t.id, bus_id=b.id, verification_status='VERIFIED')
            db.session.add(att2)
            db.session.commit()


def test_parent_absence_request_flow(client):
    from datetime import datetime
    from app.models import StudentAbsenceRequest

    with client.application.app_context():
        u_p = User(email='p_leave@test.com', role='PARENT', full_name='Parent Leave'); u_p.set_password('pass123')
        u_d = User(email='d_leave@test.com', role='DRIVER', full_name='Driver Leave'); u_d.set_password('pass123')
        db.session.add_all([u_p, u_d])
        db.session.flush()

        p = Parent(user_id=u_p.id)
        db.session.add(p)

        d = Driver(user_id=u_d.id, full_name='Driver Leave', phone='9999999999', license_number='LIC-LEAVE-100')
        db.session.add(d)
        db.session.flush()

        b = Bus(registration_number='MH-09-LEAVE-9999', bus_code='BUS-LEAVE-99', driver_id=d.id)
        db.session.add(b)
        db.session.flush()

        d.assigned_bus_id = b.id

        st = Student(full_name='Child Leave Test', roll_number='CHILD-LEAVE-99', parent_id=p.id, assigned_bus_id=b.id)
        db.session.add(st)
        db.session.commit()

        # 1. Submit Absence Request as Parent
        client.post('/auth/login', data={'email': 'p_leave@test.com', 'password': 'pass123'})
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        res_sub = client.post('/parent/absence-request/add', data={
            'student_id': st.id,
            'absence_date': today_str,
            'session_type': 'FULL_DAY',
            'reason': 'Medical Leave'
        }, follow_redirects=True)
        assert res_sub.status_code == 200

        # Check DB record created
        req = StudentAbsenceRequest.query.filter_by(student_id=st.id, absence_date=today_str).first()
        assert req is not None
        assert req.status in ('SUBMITTED', 'SUBMITTED_LATE')
        assert req.reason == 'Medical Leave'

        # 2. Check Driver Roster View flags student as ON LEAVE
        client.get('/auth/logout')
        client.post('/auth/login', data={'email': 'd_leave@test.com', 'password': 'pass123'})
        res_ros = client.get('/driver/roster')
        assert res_ros.status_code == 200
        assert b'ON LEAVE' in res_ros.data

        # 3. Parent Cancels Absence Request
        client.get('/auth/logout')
        client.post('/auth/login', data={'email': 'p_leave@test.com', 'password': 'pass123'})
        res_can = client.post(f'/parent/absence-request/cancel/{req.id}', follow_redirects=True)
        assert res_can.status_code == 200
        assert req.status == 'CANCELLED'

