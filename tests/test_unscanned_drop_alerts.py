import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Stop, Trip, Attendance, Alert, Notification
from app.driver.routes import check_unscanned_drop_offs
from app.notifications.providers import ConsoleProvider

@pytest.fixture
def unscanned_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            ConsoleProvider.clear_sent_messages()

            u_parent = User(email="parent_unscanned@test.com", role="PARENT", full_name="Unscanned Parent", phone="+91 98888 22222")
            u_parent.set_password("pass123")
            u_admin = User(email="admin_unscanned@test.com", role="ADMIN", full_name="Admin Unscanned", phone="+91 98888 33333")
            u_admin.set_password("pass123")
            db.session.add_all([u_parent, u_admin])
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-UD-200", bus_code="BUS-UD1")
            route = Route(name="Unscanned Route")
            db.session.add_all([parent, bus, route])
            db.session.commit()

            stop_drop = Stop(route_id=route.id, stop_name="Sector 17 Vashi Drop Stop", sequence_order=1, latitude=19.07, longitude=72.99)
            db.session.add(stop_drop)
            db.session.commit()

            # Student 1: Boarded but NOT scanned off (Should trigger UNSCANNED_DROP)
            s1 = Student(full_name="Unscanned Child", roll_number="UD-001", parent_id=parent.id, assigned_bus_id=bus.id, drop_stop_id=stop_drop.id)
            # Student 2: Boarded AND scanned off (Should NOT trigger UNSCANNED_DROP)
            s2 = Student(full_name="Scanned-Off Child", roll_number="UD-002", parent_id=parent.id, assigned_bus_id=bus.id, drop_stop_id=stop_drop.id)
            db.session.add_all([s1, s2])
            db.session.commit()

            trip = Trip(bus_id=bus.id, driver_id=1, route_id=route.id, trip_type="EVENING_DROP", status="IN_PROGRESS")
            db.session.add(trip)
            db.session.commit()

            # s1 Attendance: Boarded, is_dropped_off=False
            att1 = Attendance(student_id=s1.id, trip_id=trip.id, bus_id=bus.id, verification_status="VERIFIED", is_dropped_off=False)
            # s2 Attendance: Boarded AND dropped off, is_dropped_off=True
            att2 = Attendance(student_id=s2.id, trip_id=trip.id, bus_id=bus.id, verification_status="VERIFIED", is_dropped_off=True, drop_verification_time=datetime.utcnow())
            db.session.add_all([att1, att2])
            db.session.commit()

            t_id = trip.id
            s1_id = s1.id
            s2_id = s2.id
            stop_id = stop_drop.id

        yield client, t_id, s1_id, s2_id, stop_id


def test_unscanned_drop_off_triggers_critical_alert(unscanned_client):
    client, trip_id, s1_id, s2_id, stop_id = unscanned_client

    with client.application.app_context():
        trip = db.session.get(Trip, trip_id)
        alerts = check_unscanned_drop_offs(trip, stop_id=stop_id)

        # Assert exactly 1 UNSCANNED_DROP alert created for s1 (Unscanned Child)
        assert len(alerts) == 1
        assert alerts[0].student_id == s1_id
        assert alerts[0].alert_type == "UNSCANNED_DROP"
        assert alerts[0].severity == "CRITICAL"

        # Assert Notification created for parent
        notif = Notification.query.filter_by(category="UNSCANNED_DROP").first()
        assert notif is not None
        assert "Unscanned Child" in notif.message

        # Assert Outbound SMS sent via ConsoleProvider to parent
        sent_sms = [m for m in ConsoleProvider.sent_messages if m['to'] == "+91 98888 22222"]
        assert len(sent_sms) >= 1
        assert "Unscanned Child" in sent_sms[0]['message']
