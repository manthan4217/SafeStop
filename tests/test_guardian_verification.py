import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, User, Parent, Student, Institution

@pytest.fixture
def guardian_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            inst = Institution(name="Guardian Test Inst", slug="guardian-inst")
            db.session.add(inst)
            db.session.commit()

            # Create unlinked student with generated invite code
            st = Student(
                institution_id=inst.id,
                full_name="Unlinked Student",
                roll_number="GV-001",
                parent_id=None
            )
            code = st.generate_invite_code()
            db.session.add(st)
            db.session.commit()

            st_id = st.id
            inv_code = code

        yield client, st_id, inv_code


def test_registration_fails_without_valid_invite_code(guardian_client):
    client, student_id, valid_code = guardian_client

    # Case A: Missing invite code
    res1 = client.post('/auth/register-parent', data={
        'full_name': 'No Code Parent',
        'email': 'nocode@test.com',
        'phone': '+91 91111 22222',
        'password': 'Password123!',
        'student_invite_code': ''
    }, follow_redirects=True)

    assert res1.status_code == 200
    assert b"Student Invite Code is required" in res1.data

    with client.application.app_context():
        user = User.query.filter_by(email='nocode@test.com').first()
        assert user is None

    # Case B: Invalid invite code
    res2 = client.post('/auth/register-parent', data={
        'full_name': 'Bad Code Parent',
        'email': 'badcode@test.com',
        'phone': '+91 91111 33333',
        'password': 'Password123!',
        'student_invite_code': 'STU-INV-INVALID'
    }, follow_redirects=True)

    assert res2.status_code == 200
    assert b"Invalid Student Invite Code" in res2.data

    with client.application.app_context():
        user = User.query.filter_by(email='badcode@test.com').first()
        assert user is None


def test_registration_succeeds_and_links_student_with_valid_invite_code(guardian_client):
    client, student_id, valid_code = guardian_client

    res = client.post('/auth/register-parent', data={
        'full_name': 'Verified Guardian',
        'email': 'verified_guardian@test.com',
        'phone': '+91 91111 44444',
        'password': 'Password123!',
        'address': '123 Safe St',
        'emergency_contact': '+91 91111 55555',
        'relationship': 'Mother',
        'student_invite_code': valid_code
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Guardian registration successful" in res.data

    with client.application.app_context():
        user = User.query.filter_by(email='verified_guardian@test.com').first()
        assert user is not None
        assert user.role == 'PARENT'
        assert user.parent_profile is not None

        student = db.session.get(Student, student_id)
        assert student.parent_id == user.parent_profile.id
        assert student.invite_used is True


def test_registration_rejects_already_used_invite_code(guardian_client):
    client, student_id, valid_code = guardian_client

    # First registration
    client.post('/auth/register-parent', data={
        'full_name': 'First Parent',
        'email': 'first_parent@test.com',
        'phone': '+91 91111 66666',
        'password': 'Password123!',
        'student_invite_code': valid_code
    }, follow_redirects=True)

    # Second registration using same used code
    res2 = client.post('/auth/register-parent', data={
        'full_name': 'Second Parent',
        'email': 'second_parent@test.com',
        'phone': '+91 91111 77777',
        'password': 'Password123!',
        'student_invite_code': valid_code
    }, follow_redirects=True)

    assert res2.status_code == 200
    assert b"already been used" in res2.data

    with client.application.app_context():
        second_user = User.query.filter_by(email='second_parent@test.com').first()
        assert second_user is None
