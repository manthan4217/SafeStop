import sys, os
sys.path.insert(0, os.path.abspath('.'))

import pytest
from app import create_app
from app.models import db, Driver, Bus, User
from app.gps.tracker import update_driver_bus_location

@pytest.fixture
def driver_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
        yield client


def test_driver_online_and_bus_activation(driver_client):
    client = driver_client
    with client.application.app_context():
        bus = Bus(registration_number="MH-43-TEST-100", bus_code="BUS-TEST", capacity=40, status="INACTIVE")
        db.session.add(bus)
        db.session.commit()

        user = User(email="testdriver@test.com", role="DRIVER", full_name="Test Driver", phone="+91 9999999999")
        user.set_password("pass123")
        db.session.add(user)
        db.session.commit()

        driver = Driver(user_id=user.id, full_name="Test Driver", phone="+91 9999999999", license_number="DL-TEST-001", assigned_bus_id=bus.id, is_online=False)
        db.session.add(driver)
        db.session.commit()

        bus.driver_id = driver.id
        db.session.commit()

        # Test location update & online state
        test_lat, test_lng = 19.0760, 72.8777
        update_driver_bus_location(driver, test_lat, test_lng)
        db.session.commit()

        assert driver.is_online is True
        assert driver.current_lat == test_lat
        assert driver.current_lng == test_lng
        assert bus.status == 'ACTIVE'
        assert bus.current_lat == test_lat
        assert bus.current_lng == test_lng
