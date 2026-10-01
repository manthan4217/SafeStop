import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, User, Parent, Student, Bus, Institution, AuthorizedEscort

@pytest.fixture
def escort_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            inst = Institution(name="Escort Inst", slug="escort-inst")
            db.session.add(inst)
            db.session.commit()

            u_parent = User(institution_id=inst.id, email="parent_escort@test.com", role="PARENT", full_name="Escort Parent")
            u_parent.set_password("pass123")
            db.session.add(u_parent)
            db.session.commit()

            parent = Parent(user_id=u_parent.id)
            bus = Bus(registration_number="MH-12-ESC-001", bus_code="BUS-ESC1")
            db.session.add_all([parent, bus])
            db.session.commit()

            student = Student(full_name="Escort Student", roll_number="ESC-001", parent_id=parent.id, assigned_bus_id=bus.id)
            db.session.add(student)
            db.session.commit()

            st_id = student.id
            u_id = u_parent.id

        yield client, st_id, u_id


def test_add_and_fetch_authorized_escort(escort_client):
    client, student_id, user_id = escort_client

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    # Add authorized escort
    post_res = client.post('/parent/escort/add', data={
        'student_id': str(student_id),
        'full_name': 'Grandma Mary',
        'phone': '9876543210',
        'relationship': 'Grandmother',
        'id_proof_number': 'ID-998877'
    }, follow_redirects=True)
    assert post_res.status_code == 200

    with client.application.app_context():
        escort = AuthorizedEscort.query.filter_by(student_id=student_id).first()
        assert escort is not None
        assert escort.full_name == 'Grandma Mary'
        assert escort.relationship == 'Grandmother'

    # Fetch escorts via API
    api_res = client.get(f'/parent/api/escorts/{student_id}')
    assert api_res.status_code == 200
    data = api_res.get_json()
    assert data['status'] == 'SUCCESS'
    assert data['escorts_count'] == 1
    assert data['escorts'][0]['full_name'] == 'Grandma Mary'
    assert data['escorts'][0]['relationship'] == 'Grandmother'
