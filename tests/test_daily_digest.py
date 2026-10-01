import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Trip, Attendance, StudentAbsenceRequest, Notification
from app.notifications.service import generate_daily_arrival_digest

@pytest.fixture
def digest_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            u_parent = User(email="parent_digest@test.com", role="PARENT", full_name="Digest Parent")
            u_parent.set_password("pass123")
            db.session.add(u_parent)
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-DIG-001", bus_code="BUS-DIG1")
            route = Route(name="Digest Route")
            db.session.add_all([parent, bus, route])
            db.session.commit()

            s1 = Student(full_name="Child One", roll_number="DIG-001", parent_id=parent.id, assigned_bus_id=bus.id)
            s2 = Student(full_name="Child Two", roll_number="DIG-002", parent_id=parent.id, assigned_bus_id=bus.id)
            db.session.add_all([s1, s2])
            db.session.commit()

            trip = Trip(bus_id=bus.id, driver_id=1, route_id=route.id, trip_type="MORNING_PICKUP", status="COMPLETED")
            db.session.add(trip)
            db.session.commit()

            # s1 was boarded and dropped off today
            att = Attendance(
                student_id=s1.id,
                trip_id=trip.id,
                bus_id=bus.id,
                verification_status="VERIFIED",
                verification_time=datetime.utcnow() - timedelta(hours=2),
                is_dropped_off=True,
                drop_verification_time=datetime.utcnow() - timedelta(hours=1)
            )

            # s2 has an excused absence today
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            absence = StudentAbsenceRequest(
                student_id=s2.id,
                parent_id=parent.id,
                absence_date=today_str,
                reason="Doctor Appointment",
                status="SUBMITTED"
            )

            db.session.add_all([att, absence])
            db.session.commit()

            p_id = parent.id
            u_id = u_parent.id

        yield client, p_id, u_id


def test_generate_daily_arrival_digest(digest_client):
    client, parent_id, user_id = digest_client

    with client.application.app_context():
        notifs = generate_daily_arrival_digest(parent_id=parent_id)
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif.user_id == user_id
        assert "Daily Safe-Arrival Digest" in notif.title
        assert "Child One" in notif.message
        assert "Boarded at" in notif.message
        assert "Dropped off at" in notif.message
        assert "Child Two" in notif.message
        assert "Doctor Appointment" in notif.message


def test_parent_api_daily_digest(digest_client):
    client, parent_id, user_id = digest_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    res = client.post('/parent/api/daily-digest')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'SUCCESS'
    assert "SafeStop Daily Digest" in data['digest']
