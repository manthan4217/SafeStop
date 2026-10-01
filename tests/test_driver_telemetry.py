import pytest
from datetime import datetime
from app import create_app
from app.models import db, User, Driver, Bus, Route, Trip, Alert, Notification, DriverSafetyTelemetry, Institution

@pytest.fixture
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(test_app):
    return test_app.test_client()

def test_driver_safety_telemetry_model(test_app):
    with test_app.app_context():
        u = User(email='driver_telem@test.com', role='DRIVER', full_name='Telemetry Driver')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()

        d = Driver(user_id=u.id, full_name='Telemetry Driver', phone='9988776655', license_number='LIC-TELEM-1')
        db.session.add(d)
        db.session.commit()

        b = Bus(registration_number='MH-43-TL-1001', bus_code='BUS-TL1', driver_id=d.id)
        db.session.add(b)
        db.session.commit()

        d.assigned_bus_id = b.id
        db.session.commit()

        t = DriverSafetyTelemetry(
            driver_id=d.id,
            bus_id=b.id,
            fatigue_score=0.88,
            fatigue_level='CRITICAL_DROWSINESS',
            eye_closure_sec=2.8,
            yawn_count=3,
            distraction_event='EYES_OFF_ROAD',
            speed_kph=48.5,
            overspeed_warning=False,
            harsh_braking_warning=False,
            safety_score=40
        )
        db.session.add(t)
        db.session.commit()

        fetched = DriverSafetyTelemetry.query.filter_by(driver_id=d.id).first()
        assert fetched is not None
        assert fetched.fatigue_level == 'CRITICAL_DROWSINESS'
        assert fetched.safety_score == 40
        assert fetched.driver.full_name == 'Telemetry Driver'

def test_driver_telemetry_log_endpoint(test_app, client):
    with test_app.app_context():
        inst = Institution(name="Enterprise Test Inst", slug="ent-test-inst", plan_tier="ENTERPRISE")
        db.session.add(inst)
        db.session.commit()

        admin_u = User(institution_id=inst.id, email='admin_telem@test.com', role='ADMIN', full_name='Admin Telem')
        admin_u.set_password('adminpass')
        db.session.add(admin_u)

        driver_u = User(institution_id=inst.id, email='driver_api@test.com', role='DRIVER', full_name='Driver Api')
        driver_u.set_password('driverpass')
        db.session.add(driver_u)
        db.session.commit()

        d = Driver(institution_id=inst.id, user_id=driver_u.id, full_name='Driver Api', phone='9900112233', license_number='LIC-API-1')
        db.session.add(d)
        db.session.commit()

        b = Bus(institution_id=inst.id, registration_number='MH-43-API-2002', bus_code='BUS-API2', driver_id=d.id)
        r = Route(institution_id=inst.id, name='Route API', distance_km=10.0)
        db.session.add_all([b, r])
        db.session.commit()

        d.assigned_bus_id = b.id
        d.assigned_route_id = r.id
        bus_id = b.id
        db.session.commit()

    # Login driver
    client.post('/auth/login', data={'email': 'driver_api@test.com', 'password': 'driverpass'}, follow_redirects=True)

    # Post telemetry payload (Critical Drowsiness)
    payload = {
        'fatigue_score': 0.95,
        'fatigue_level': 'CRITICAL_DROWSINESS',
        'eye_closure_sec': 3.2,
        'yawn_count': 5,
        'distraction_event': 'EYES_OFF_ROAD',
        'speed_kph': 55.0,
        'overspeed_warning': False,
        'harsh_braking_warning': False
    }

    res = client.post('/driver/telemetry/log', json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['alert_created'] is True
    assert data['safety_score'] < 50

    # Verify Alert created in DB
    with test_app.app_context():
        alert = Alert.query.filter_by(alert_type='DRIVER_FATIGUE').first()
        assert alert is not None
        assert alert.severity == 'CRITICAL'
        assert alert.bus_id == bus_id

def test_admin_live_telemetry_endpoint(test_app, client):
    with test_app.app_context():
        admin_u = User(email='admin_live@test.com', role='ADMIN', full_name='Admin Live')
        admin_u.set_password('adminpass')
        db.session.add(admin_u)
        db.session.commit()

    # Login admin
    client.post('/auth/login', data={'email': 'admin_live@test.com', 'password': 'adminpass'}, follow_redirects=True)

    res = client.get('/admin/driver-telemetry/live')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'drivers' in data
