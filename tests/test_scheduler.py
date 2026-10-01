import pytest
from datetime import datetime, timedelta
from app import create_app
from app.models import db, Institution, User, Driver, DriverDocument, Alert, Notification, Bus, Route, Trip, Student
from app.compliance import check_expiring_driver_credentials
from app.driver.routes import run_no_show_check
from app.notifications.service import generate_daily_arrival_digest

@pytest.fixture
def scheduler_app_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Create test institution
            inst = Institution(name="Test Scheduler Academy", slug="test-sched-academy")
            db.session.add(inst)
            db.session.commit()

            # Create admin
            admin = User(
                institution_id=inst.id,
                email="admin@sched.com",
                role="ADMIN",
                full_name="Scheduler Admin",
                phone="+15551234567"
            )
            admin.set_password("pass123")

            # Create driver with expiring document
            u_driver = User(
                institution_id=inst.id,
                email="driver@sched.com",
                role="DRIVER",
                full_name="Expiring Driver"
            )
            u_driver.set_password("pass123")
            db.session.add_all([admin, u_driver])
            db.session.commit()

            driver = Driver(user_id=u_driver.id, institution_id=inst.id, full_name="Expiring Driver", phone="+15559876543", license_number="LIC-EXP-123")
            db.session.add(driver)
            db.session.commit()

            exp_date_str = (datetime.utcnow().date() + timedelta(days=5)).strftime('%Y-%m-%d')
            doc = DriverDocument(
                driver_id=driver.id,
                doc_type="Commercial Driver License",
                doc_name="CDL-999",
                file_path="/uploads/cdl999.pdf",
                expiry_date=exp_date_str
            )
            db.session.add(doc)
            db.session.commit()

            inst_id = inst.id
            driver_id = driver.id

        yield client, inst_id, driver_id


def test_compliance_check_job_generates_alert_and_notification(scheduler_app_client):
    client, inst_id, driver_id = scheduler_app_client

    with client.application.app_context():
        warnings = check_expiring_driver_credentials()
        
        # Verify warnings returned
        assert len(warnings) >= 1
        assert warnings[0]['type'] == 'DOCUMENT_EXPIRING'
        assert warnings[0]['driver_name'] == 'Expiring Driver'

        # Verify Alert created in database
        alerts = Alert.query.filter_by(institution_id=inst_id, alert_type='DRIVER_COMPLIANCE').all()
        assert len(alerts) >= 1
        assert "Commercial Driver License" in alerts[0].description

        # Verify Admin Notification created
        notifs = Notification.query.filter_by(category='EMERGENCY').all()
        assert len(notifs) >= 1
        assert "Expiring Driver" in notifs[0].message


def test_no_show_and_digest_scheduled_job_callbacks(scheduler_app_client):
    client, inst_id, _ = scheduler_app_client

    with client.application.app_context():
        # Setup trip for no-show testing
        bus = Bus(institution_id=inst_id, registration_number="BUS-SCHED-1", bus_code="SCH-1")
        route = Route(institution_id=inst_id, name="Sched Route")
        db.session.add_all([bus, route])
        db.session.commit()

        trip = Trip(
            institution_id=inst_id,
            bus_id=bus.id,
            driver_id=1,
            route_id=route.id,
            trip_type="MORNING_PICKUP",
            status="IN_PROGRESS"
        )
        db.session.add(trip)
        db.session.commit()

        student = Student(
            institution_id=inst_id,
            full_name="Sched Child",
            roll_number="SCH-001",
            assigned_bus_id=bus.id
        )
        db.session.add(student)
        db.session.commit()

        # Run no-show check callback directly
        no_show_alerts = run_no_show_check()
        assert len(no_show_alerts) >= 1
        assert no_show_alerts[0].student_id == student.id

        # Run daily digest callback directly
        digest_notifs = generate_daily_arrival_digest()
        assert isinstance(digest_notifs, list)
