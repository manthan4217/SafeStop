import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Trip, Attendance, Alert, Notification, StudentAbsenceRequest
from app.driver.routes import check_trip_no_shows
from app.notifications.providers import ConsoleProvider

@pytest.fixture
def no_show_client():
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

            # Create test entities
            u_parent = User(email="parent_noshow@test.com", role="PARENT", full_name="NoShow Parent", phone="+91 99999 11111")
            u_parent.set_password("pass123")
            u_driver = User(email="driver_noshow@test.com", role="DRIVER", full_name="NoShow Driver")
            u_driver.set_password("pass123")
            db.session.add_all([u_parent, u_driver])
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-NS-100", bus_code="BUS-NS1")
            route = Route(name="NoShow Route")
            db.session.add_all([parent, bus, route])
            db.session.commit()

            # Student 1: Unboarded, No Absence (Should trigger NO_SHOW)
            s1 = Student(full_name="Child One", roll_number="NS-001", parent_id=parent.id, assigned_bus_id=bus.id)
            # Student 2: Unboarded, Has Active Absence (Should NOT trigger NO_SHOW)
            s2 = Student(full_name="Child Two", roll_number="NS-002", parent_id=parent.id, assigned_bus_id=bus.id)
            # Student 3: Boarded (Should NOT trigger NO_SHOW)
            s3 = Student(full_name="Child Three", roll_number="NS-003", parent_id=parent.id, assigned_bus_id=bus.id)
            db.session.add_all([s1, s2, s3])
            db.session.commit()

            # Absence request for s2 for today
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            abs_req = StudentAbsenceRequest(
                student_id=s2.id,
                parent_id=parent.id,
                absence_date=today_str,
                reason="Sick leave",
                status="SUBMITTED"
            )
            db.session.add(abs_req)
            db.session.commit()

            # Trip
            trip = Trip(
                bus_id=bus.id,
                driver_id=1,
                route_id=route.id,
                trip_type="MORNING_PICKUP",
                status="IN_PROGRESS"
            )
            db.session.add(trip)
            db.session.commit()

            # Attendance for s3 (boarded)
            att = Attendance(
                student_id=s3.id,
                trip_id=trip.id,
                bus_id=bus.id,
                verification_status="VERIFIED"
            )
            db.session.add(att)
            db.session.commit()

            # Save integer IDs before app context closes
            t_id = trip.id
            id1 = s1.id
            id2 = s2.id
            id3 = s3.id

        yield client, t_id, id1, id2, id3


def test_no_show_check_triggers_alert_only_for_unexcused_missing_students(no_show_client):
    client, trip_id, s1_id, s2_id, s3_id = no_show_client

    with client.application.app_context():
        trip = db.session.get(Trip, trip_id)
        alerts = check_trip_no_shows(trip)

        # Assert exactly 1 NO_SHOW alert created for s1 (Child One)
        assert len(alerts) == 1
        assert alerts[0].student_id == s1_id
        assert alerts[0].alert_type == "NO_SHOW"
        assert alerts[0].severity == "CRITICAL"

        # Assert Notification created for parent
        notif = Notification.query.filter_by(category="NO_SHOW").first()
        assert notif is not None
        assert "Child One" in notif.message

        # Assert Outbound SMS sent via ConsoleProvider
        assert len(ConsoleProvider.sent_messages) >= 1
        sent_sms = [m for m in ConsoleProvider.sent_messages if m['to'] == "+91 99999 11111"]
        assert len(sent_sms) == 1
        assert "Child One" in sent_sms[0]['message']
