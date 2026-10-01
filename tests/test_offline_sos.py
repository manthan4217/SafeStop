import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Driver, Bus, Route, Trip, EmergencyEvent, Alert

@pytest.fixture
def sos_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            u_driver = User(email="driver_sos@test.com", role="DRIVER", full_name="SOS Driver")
            u_driver.set_password("pass123")
            db.session.add(u_driver)
            db.session.commit()

            bus = Bus(registration_number="MH-12-SOS-001", bus_code="BUS-SOS1")
            route = Route(name="SOS Route")
            db.session.add_all([bus, route])
            db.session.commit()

            driver = Driver(user_id=u_driver.id, full_name="SOS Driver", phone="9998887776", license_number="LIC-SOS1", assigned_bus_id=bus.id, assigned_route_id=route.id)
            db.session.add(driver)
            db.session.commit()

            trip = Trip(bus_id=bus.id, driver_id=driver.id, route_id=route.id, trip_type="MORNING_PICKUP", status="IN_PROGRESS")
            db.session.add(trip)
            db.session.commit()

            d_user_id = u_driver.id
            t_id = trip.id
            b_id = bus.id

        yield client, d_user_id, t_id, b_id


def test_api_trigger_sos_with_timestamp(sos_client):
    client, user_id, trip_id, bus_id = sos_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    past_time_str = "2026-09-13T10:15:30Z"
    payload = {
        "trip_id": trip_id,
        "latitude": 19.076,
        "longitude": 72.877,
        "description": "Engine Smoke Emergency",
        "triggered_at": past_time_str
    }

    res = client.post('/driver/api/trigger-sos', json=payload)
    assert res.status_code == 200
    assert res.get_json()['status'] == 'SUCCESS'

    with client.application.app_context():
        sos_event = EmergencyEvent.query.filter_by(bus_id=bus_id).first()
        assert sos_event is not None
        assert sos_event.description == "Engine Smoke Emergency"
        assert sos_event.triggered_at is not None
        assert sos_event.triggered_at.strftime('%Y-%m-%d %H:%M:%S') == "2026-09-13 10:15:30"

        alert = Alert.query.filter_by(alert_type='SOS_EMERGENCY').first()
        assert alert is not None
        assert alert.severity == 'CRITICAL'


def test_sync_offline_sos_queue(sos_client):
    client, user_id, trip_id, bus_id = sos_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    past_time_str = "2026-09-13T11:22:33Z"
    sync_payload = {
        "queue": [],
        "sos_queue": [
            {
                "trip_id": trip_id,
                "latitude": 19.080,
                "longitude": 72.880,
                "description": "Offline Breakdown SOS",
                "triggered_at": past_time_str
            }
        ]
    }

    res = client.post('/driver/api/sync-offline-queue', json=sync_payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'SUCCESS'
    assert data['sos_synced_count'] == 1

    with client.application.app_context():
        sos_event = EmergencyEvent.query.filter_by(bus_id=bus_id).first()
        assert sos_event is not None
        assert sos_event.description == "Offline Breakdown SOS"
        assert sos_event.triggered_at.strftime('%Y-%m-%d %H:%M:%S') == "2026-09-13 11:22:33"

        alert = Alert.query.filter_by(alert_type='SOS_EMERGENCY').first()
        assert alert is not None
        assert "Offline Queue Synced" in alert.description
