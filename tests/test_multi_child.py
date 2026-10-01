import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from datetime import datetime, timedelta
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Trip, Attendance, Institution

@pytest.fixture
def multi_child_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            inst = Institution(name="MultiChild Inst", slug="multichild-inst")
            db.session.add(inst)
            db.session.commit()

            u_parent = User(institution_id=inst.id, email="parent_multi@test.com", role="PARENT", full_name="Multi Parent")
            u_parent.set_password("pass123")
            db.session.add(u_parent)
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus1 = Bus(registration_number="MH-12-MUL-001", bus_code="BUS-MC1")
            bus2 = Bus(registration_number="MH-12-MUL-002", bus_code="BUS-MC2")
            route1 = Route(name="Route MC1")
            route2 = Route(name="Route MC2")
            db.session.add_all([parent, bus1, bus2, route1, route2])
            db.session.commit()

            s1 = Student(full_name="Child Alpha", roll_number="MC-001", parent_id=parent.id, assigned_bus_id=bus1.id)
            s2 = Student(full_name="Child Beta", roll_number="MC-002", parent_id=parent.id, assigned_bus_id=bus2.id)
            db.session.add_all([s1, s2])
            db.session.commit()

            trip1 = Trip(bus_id=bus1.id, driver_id=1, route_id=route1.id, trip_type="MORNING_PICKUP", status="IN_PROGRESS")
            db.session.add(trip1)
            db.session.commit()

            att1 = Attendance(
                student_id=s1.id,
                trip_id=trip1.id,
                bus_id=bus1.id,
                verification_status="VERIFIED",
                verification_time=datetime.utcnow()
            )
            db.session.add(att1)
            db.session.commit()

            p_id = parent.id
            u_id = u_parent.id

        yield client, p_id, u_id


def test_api_family_status_multi_child(multi_child_client):
    client, parent_id, user_id = multi_child_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    res = client.get('/parent/api/family-status')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'SUCCESS'
    assert data['children_count'] == 2

    children = data['children']
    child_names = [c['full_name'] for c in children]
    assert "Child Alpha" in child_names
    assert "Child Beta" in child_names

    # Check child alpha has active trip and attendance
    c_alpha = next(c for c in children if c['full_name'] == "Child Alpha")
    assert c_alpha['bus']['bus_code'] == "BUS-MC1"
    assert c_alpha['active_trip'] is not None
    assert c_alpha['attendance_today']['verification_status'] == "VERIFIED"

    # Check child beta has bus2 and no active trip currently
    c_beta = next(c for c in children if c['full_name'] == "Child Beta")
    assert c_beta['bus']['bus_code'] == "BUS-MC2"
    assert c_beta['active_trip'] is None
