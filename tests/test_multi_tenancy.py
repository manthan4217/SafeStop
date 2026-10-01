import pytest  # type: ignore # pyright: ignore[reportMissingImports]
import json
import numpy as np
from app import create_app
from app.models import (
    db, Institution, User, Parent, Student, Driver, Bus, Route, Stop, Trip, Attendance, Alert, AuditLog, FaceProfile
)
from app.ai.engine import identify_student_from_face

@pytest.fixture
def multi_tenant_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Create Institution A and Institution B
            inst_a = Institution(name="Institution A", slug="inst-a")
            inst_b = Institution(name="Institution B", slug="inst-b")
            db.session.add_all([inst_a, inst_b])
            db.session.flush()

            inst_a_id = inst_a.id
            inst_b_id = inst_b.id

            # Users for Institution A
            u_admin_a = User(email="admin_a@test.com", role="ADMIN", full_name="Admin A", institution_id=inst_a_id)
            u_admin_a.set_password("pass123")
            u_driver_a = User(email="driver_a@test.com", role="DRIVER", full_name="Driver A", institution_id=inst_a_id)
            u_driver_a.set_password("pass123")
            u_parent_a = User(email="parent_a@test.com", role="PARENT", full_name="Parent A", institution_id=inst_a_id)
            u_parent_a.set_password("pass123")

            # Users for Institution B
            u_admin_b = User(email="admin_b@test.com", role="ADMIN", full_name="Admin B", institution_id=inst_b_id)
            u_admin_b.set_password("pass123")
            u_driver_b = User(email="driver_b@test.com", role="DRIVER", full_name="Driver B", institution_id=inst_b_id)
            u_driver_b.set_password("pass123")
            u_parent_b = User(email="parent_b@test.com", role="PARENT", full_name="Parent B", institution_id=inst_b_id)
            u_parent_b.set_password("pass123")

            db.session.add_all([u_admin_a, u_driver_a, u_parent_a, u_admin_b, u_driver_b, u_parent_b])
            db.session.flush()

            # Profiles
            p_a = Parent(user_id=u_parent_a.id, institution_id=inst_a_id)
            p_b = Parent(user_id=u_parent_b.id, institution_id=inst_b_id)
            d_a = Driver(user_id=u_driver_a.id, full_name="Driver A", phone="1111111111", license_number="LIC-A", institution_id=inst_a_id)
            d_b = Driver(user_id=u_driver_b.id, full_name="Driver B", phone="2222222222", license_number="LIC-B", institution_id=inst_b_id)
            db.session.add_all([p_a, p_b, d_a, d_b])
            db.session.flush()

            driver_a_id = d_a.id
            driver_b_id = d_b.id

            # Resources for Institution A
            bus_a = Bus(institution_id=inst_a_id, registration_number="MH-01-A-100", bus_code="BUS-A1", driver_id=driver_a_id)
            route_a = Route(institution_id=inst_a_id, name="Route A")
            db.session.add_all([bus_a, route_a])
            db.session.flush()
            d_a.assigned_bus_id = bus_a.id

            bus_a_id = bus_a.id

            student_a = Student(institution_id=inst_a_id, full_name="Student A", roll_number="ST-A1", parent_id=p_a.id, assigned_bus_id=bus_a_id)
            alert_a = Alert(institution_id=inst_a_id, bus_id=bus_a_id, alert_type="BUS_DELAY", description="Delay in A")
            audit_a = AuditLog(institution_id=inst_a_id, user_id=u_admin_a.id, action="LOGIN", details="Admin A Login")
            db.session.add_all([student_a, alert_a, audit_a])
            db.session.flush()

            student_a_id = student_a.id
            alert_a_id = alert_a.id

            # Resources for Institution B
            bus_b = Bus(institution_id=inst_b_id, registration_number="MH-02-B-200", bus_code="BUS-B1", driver_id=driver_b_id)
            route_b = Route(institution_id=inst_b_id, name="Route B")
            db.session.add_all([bus_b, route_b])
            db.session.flush()
            d_b.assigned_bus_id = bus_b.id

            bus_b_id = bus_b.id

            student_b = Student(institution_id=inst_b_id, full_name="Student B", roll_number="ST-B1", parent_id=p_b.id, assigned_bus_id=bus_b_id)
            alert_b = Alert(institution_id=inst_b_id, bus_id=bus_b_id, alert_type="BUS_DELAY", description="Delay in B")
            audit_b = AuditLog(institution_id=inst_b_id, user_id=u_admin_b.id, action="LOGIN", details="Admin B Login")
            db.session.add_all([student_b, alert_b, audit_b])
            db.session.flush()

            student_b_id = student_b.id
            alert_b_id = alert_b.id

            # Face Profiles
            vec_a = [0.5] * 4096
            fp_a = FaceProfile(student_id=student_a_id, feature_vector_json=json.dumps(vec_a), image_path="default_student.png")
            vec_b = [0.9] * 4096
            fp_b = FaceProfile(student_id=student_b_id, feature_vector_json=json.dumps(vec_b), image_path="default_student.png")
            db.session.add_all([fp_a, fp_b])
            db.session.commit()

        yield client, {
            'inst_a': inst_a_id, 'inst_b': inst_b_id,
            'bus_a': bus_a_id, 'bus_b': bus_b_id,
            'student_a': student_a_id, 'student_b': student_b_id,
            'driver_a': driver_a_id, 'driver_b': driver_b_id,
            'alert_a': alert_a_id, 'alert_b': alert_b_id
        }


def test_multi_tenant_admin_isolation(multi_tenant_app):
    client, entities = multi_tenant_app

    # Login as Admin A (Institution A)
    client.post('/auth/login', data={'email': 'admin_a@test.com', 'password': 'pass123'})

    # 1. Dashboard View
    res_dash = client.get('/admin/dashboard')
    assert res_dash.status_code == 200
    assert b'BUS-A1' in res_dash.data
    assert b'BUS-B1' not in res_dash.data

    # 2. Bus Roster View
    res_buses = client.get('/admin/buses')
    assert res_buses.status_code == 200
    assert b'BUS-A1' in res_buses.data
    assert b'BUS-B1' not in res_buses.data

    # 3. Direct Bus Access to Tenant B -> 403 Forbidden
    res_bus_b = client.get(f"/admin/bus/{entities['bus_b']}")
    assert res_bus_b.status_code == 403

    # 4. Student Roster View
    res_students = client.get('/admin/students')
    assert res_students.status_code == 200
    assert b'Student A' in res_students.data
    assert b'Student B' not in res_students.data

    # 5. Delete Student from Tenant B -> 403 Forbidden
    res_del_st = client.post(f"/admin/student/delete/{entities['student_b']}")
    assert res_del_st.status_code == 403

    # 6. Delete Driver from Tenant B -> 403 Forbidden
    res_del_dr = client.post(f"/admin/driver/delete/{entities['driver_b']}")
    assert res_del_dr.status_code == 403

    # 7. Resolve Alert from Tenant B -> 403 Forbidden
    res_res_alt = client.post(f"/admin/alert/resolve/{entities['alert_b']}")
    assert res_res_alt.status_code == 403

    # 8. Audit Logs View
    res_logs = client.get('/admin/audit-logs')
    assert res_logs.status_code == 200
    assert b'Admin A Login' in res_logs.data
    assert b'Admin B Login' not in res_logs.data


def test_face_recognition_tenant_isolation(multi_tenant_app):
    client, entities = multi_tenant_app

    with client.application.app_context():
        # Active Trip for Bus A (Institution A)
        trip_a = Trip(
            institution_id=entities['inst_a'],
            bus_id=entities['bus_a'],
            driver_id=entities['driver_a'],
            route_id=1,
            trip_type='MORNING_PICKUP',
            status='IN_PROGRESS'
        )
        db.session.add(trip_a)
        db.session.commit()

        # Mock camera frame base64
        dummy_img_b64 = "data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

        # Call with active_trip_id=trip_a.id, search should ONLY scan profiles for Institution A (Student A), ignoring Student B
        res = identify_student_from_face(dummy_img_b64, active_trip_id=trip_a.id)
        if res.get('status') == 'MATCHED':
            assert res['student'].institution_id == entities['inst_a']
            assert res['student'].id != entities['student_b']


def test_parent_cross_tenant_isolation(multi_tenant_app):
    client, entities = multi_tenant_app

    # Login as Parent A (Institution A)
    client.post('/auth/login', data={'email': 'parent_a@test.com', 'password': 'pass123'})

    # Try tracking Bus B (Institution B) -> 403 Forbidden
    res_track = client.get(f"/parent/api/live-bus-location/{entities['bus_b']}")
    assert res_track.status_code == 403

    # Try viewing Student B profile -> Redirected or 403
    res_child = client.get(f"/parent/child/{entities['student_b']}")
    assert res_child.status_code in [302, 403]
