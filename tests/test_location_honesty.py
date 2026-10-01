import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Trip, GpsLocation, Alert

@pytest.fixture
def location_honesty_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            u_parent = User(email="parent_gps@test.com", role="PARENT", full_name="GPS Parent")
            u_parent.set_password("pass123")
            db.session.add(u_parent)
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-GPS-300", bus_code="BUS-GPS1")
            route = Route(name="GPS Route")
            db.session.add_all([parent, bus, route])
            db.session.commit()

            student = Student(full_name="GPS Child", roll_number="GPS-001", parent_id=parent.id, assigned_bus_id=bus.id)
            db.session.add(student)
            db.session.commit()

            trip = Trip(bus_id=bus.id, driver_id=1, route_id=route.id, trip_type="MORNING_PICKUP", status="IN_PROGRESS")
            db.session.add(trip)
            db.session.commit()

            b_id = bus.id
            t_id = trip.id
            u_id = u_parent.id

        yield client, b_id, t_id, u_id


def test_recent_gps_is_not_stale(location_honesty_client):
    client, bus_id, trip_id, user_id = location_honesty_client

    with client.application.app_context():
        # Add GPS location 30 seconds ago
        gps = GpsLocation(
            trip_id=trip_id,
            bus_id=bus_id,
            latitude=19.076,
            longitude=72.877,
            timestamp=datetime.utcnow() - timedelta(seconds=30)
        )
        db.session.add(gps)
        db.session.commit()

    # Login parent
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    res = client.get(f'/parent/api/live-bus-location/{bus_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ACTIVE'
    assert data['is_stale'] is False
    assert data['seconds_since_last_update'] <= 40


def test_stale_gps_flags_is_stale_true(location_honesty_client):
    client, bus_id, trip_id, user_id = location_honesty_client

    with client.application.app_context():
        # Add GPS location 300 seconds ago (5 minutes ago)
        gps = GpsLocation(
            trip_id=trip_id,
            bus_id=bus_id,
            latitude=19.076,
            longitude=72.877,
            timestamp=datetime.utcnow() - timedelta(seconds=300)
        )
        db.session.add(gps)
        db.session.commit()

    # Login parent
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    res = client.get(f'/parent/api/live-bus-location/{bus_id}')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ACTIVE'
    assert data['is_stale'] is True
    assert data['seconds_since_last_update'] >= 300


def test_highly_stale_gps_triggers_alert(location_honesty_client):
    client, bus_id, trip_id, user_id = location_honesty_client

    with client.application.app_context():
        # Add GPS location 700 seconds ago (11 minutes ago)
        gps = GpsLocation(
            trip_id=trip_id,
            bus_id=bus_id,
            latitude=19.076,
            longitude=72.877,
            timestamp=datetime.utcnow() - timedelta(seconds=700)
        )
        db.session.add(gps)
        db.session.commit()

    # Login parent
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    res = client.get(f'/parent/api/live-bus-location/{bus_id}')
    assert res.status_code == 200

    with client.application.app_context():
        alert = Alert.query.filter_by(trip_id=trip_id, alert_type='GPS_STALE').first()
        assert alert is not None
        assert alert.severity == 'WARNING'
