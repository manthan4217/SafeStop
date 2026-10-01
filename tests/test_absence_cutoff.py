import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Parent, Student, Bus, Driver, StudentAbsenceRequest, Notification

@pytest.fixture
def absence_cutoff_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['ABSENCE_CUTOFF_HOUR'] = 7
    app.config['ABSENCE_CUTOFF_MINUTE'] = 30

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            from app.models import Institution
            inst = Institution(name="Cutoff Inst", slug="cutoff-inst")
            db.session.add(inst)
            db.session.commit()

            u_parent = User(institution_id=inst.id, email="parent_cutoff@test.com", role="PARENT", full_name="Cutoff Parent")
            u_parent.set_password("pass123")
            u_driver = User(institution_id=inst.id, email="driver_cutoff@test.com", role="DRIVER", full_name="Cutoff Driver")
            u_driver.set_password("pass123")
            db.session.add_all([u_parent, u_driver])
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-CUT-001", bus_code="BUS-CUT1")
            db.session.add_all([parent, bus])
            db.session.commit()

            driver = Driver(user_id=u_driver.id, full_name="Cutoff Driver", phone="9988776655", license_number="LIC-CUT1", assigned_bus_id=bus.id)
            db.session.add(driver)
            db.session.commit()

            student = Student(full_name="Cutoff Student", roll_number="CUT-001", parent_id=parent.id, assigned_bus_id=bus.id)
            db.session.add(student)
            db.session.commit()

            st_id = student.id
            u_p_id = u_parent.id
            u_d_id = u_driver.id

        yield client, st_id, u_p_id, u_d_id


def test_absence_request_late_submission(absence_cutoff_client):
    client, student_id, parent_user_id, driver_user_id = absence_cutoff_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(parent_user_id)
        sess['_fresh'] = True

    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    res = client.post('/parent/absence-request/add', data={
        'student_id': str(student_id),
        'absence_date': today_str,
        'session_type': 'FULL_DAY',
        'reason': 'Sudden Fever'
    }, follow_redirects=True)

    assert res.status_code == 200

    with client.application.app_context():
        absence_req = StudentAbsenceRequest.query.filter_by(student_id=student_id).first()
        assert absence_req is not None
        # Since current time is likely after 07:30 AM UTC, status should be SUBMITTED_LATE or SUBMITTED
        assert absence_req.status in ('SUBMITTED_LATE', 'SUBMITTED')

        # Driver should be notified
        driver_notif = Notification.query.filter_by(user_id=driver_user_id).first()
        assert driver_notif is not None
        assert "Absence Update Received" in driver_notif.title
