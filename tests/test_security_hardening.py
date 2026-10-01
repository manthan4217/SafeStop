import os
import importlib
from datetime import datetime
import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, Institution, User, Parent, Driver, Student, Route, Bus, Trip, Attendance, AuditLog

@pytest.fixture
def sec_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            inst = Institution(name="Security Test Inst", slug="sec-inst")
            db.session.add(inst)
            db.session.flush()

            u_admin = User(email="sec_admin@test.com", role="ADMIN", full_name="Sec Admin", institution_id=inst.id)
            u_admin.set_password("pass123")

            u_driver = User(email="sec_driver@test.com", role="DRIVER", full_name="Sec Driver", institution_id=inst.id)
            u_driver.set_password("pass123")

            u_parent = User(email="sec_parent@test.com", role="PARENT", full_name="Sec Parent", institution_id=inst.id)
            u_parent.set_password("pass123")

            db.session.add_all([u_admin, u_driver, u_parent])
            db.session.flush()

            parent = Parent(user_id=u_parent.id, institution_id=inst.id)
            driver = Driver(user_id=u_driver.id, full_name="Sec Driver", phone="1234567890", license_number="LIC-123", institution_id=inst.id)
            route = Route(name="Sec Route", institution_id=inst.id)
            bus = Bus(bus_code="SEC-BUS", registration_number="REG-SEC", institution_id=inst.id)
            db.session.add_all([parent, driver, route, bus])
            db.session.flush()

            bus.driver_id = driver.id
            driver.assigned_bus_id = bus.id

            student = Student(full_name="Sec Student", roll_number="STU-001", parent_id=parent.id, institution_id=inst.id)
            db.session.add(student)
            db.session.flush()

            trip = Trip(
                bus_id=bus.id,
                route_id=route.id,
                driver_id=driver.id,
                status="IN_PROGRESS",
                trip_type="PICKUP",
                institution_id=inst.id,
                start_time=datetime.utcnow()
            )
            db.session.add(trip)
            db.session.commit()

            yield {
                'client': client,
                'app': app,
                'admin_id': u_admin.id,
                'driver_id': u_driver.id,
                'parent_id': u_parent.id,
                'student_id': student.id,
                'trip_id': trip.id,
                'driver_profile_id': driver.id
            }

def test_production_secrets_enforcement(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('WTF_CSRF_SECRET_KEY', raising=False)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        import config
        importlib.reload(config)
    
    # Restore dev environment
    monkeypatch.setenv('FLASK_ENV', 'development')
    import config
    importlib.reload(config)

def test_manual_verify_audit_log(sec_app):
    client = sec_app['client']
    
    # Login as driver
    client.post('/auth/login', data={'email': 'sec_driver@test.com', 'password': 'pass123'}, follow_redirects=True)

    # Perform manual verification
    response = client.post('/driver/manual-verify', data={
        'student_id': sec_app['student_id'],
        'trip_id': sec_app['trip_id'],
        'reason': 'Test manual override'
    }, follow_redirects=True)
    assert response.status_code == 200

    # Check attendance created
    att = Attendance.query.filter_by(student_id=sec_app['student_id'], trip_id=sec_app['trip_id']).first()
    assert att is not None
    assert att.verification_status == 'MANUAL_OVERRIDE'

    # Check AuditLog entry created
    log = AuditLog.query.filter_by(action='MANUAL_VERIFY_OVERRIDE').first()
    assert log is not None
    assert log.user_id == sec_app['driver_id']
    assert "Manual verification override performed by Driver" in log.details

def test_unauthenticated_and_unauthorized_access(sec_app):
    client = sec_app['client']

    # Unauthenticated access to admin dashboard should redirect to login
    res = client.get('/admin/dashboard')
    assert res.status_code == 302
    assert '/auth/login' in res.location

    # Login as parent
    client.post('/auth/login', data={'email': 'sec_parent@test.com', 'password': 'pass123'}, follow_redirects=True)

    # Parent trying to access admin dashboard should be denied (redirected away from admin section)
    res = client.get('/admin/dashboard', follow_redirects=False)
    assert res.status_code == 302
    assert '/parent/dashboard' in res.location

    # Parent trying to access driver dashboard should be denied
    res = client.get('/driver/dashboard', follow_redirects=False)
    assert res.status_code == 302
    assert '/parent/dashboard' in res.location

def test_rate_limiting_configured(sec_app):
    app = sec_app['app']
    assert 'limiter' in app.extensions
