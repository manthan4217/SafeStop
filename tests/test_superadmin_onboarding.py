import pytest
from app import create_app
from app.models import db, Institution, User
from manage_db import create_superadmin, create_institution_and_admin

@pytest.fixture
def superadmin_app_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Create SuperAdmin user
            super_user = User(
                institution_id=None,
                email="super@safestop.ai",
                role="SUPER_ADMIN",
                full_name="Global SuperAdmin"
            )
            super_user.set_password("superpass123")

            # Create standard institution & admin
            inst = Institution(name="Pilot School", slug="pilot-school")
            db.session.add_all([super_user, inst])
            db.session.commit()

            admin_user = User(
                institution_id=inst.id,
                email="admin@pilot.edu",
                role="ADMIN",
                full_name="Pilot Admin"
            )
            admin_user.set_password("adminpass123")

            parent_user = User(
                institution_id=inst.id,
                email="parent@pilot.edu",
                role="PARENT",
                full_name="Pilot Parent"
            )
            parent_user.set_password("parentpass123")

            db.session.add_all([admin_user, parent_user])
            db.session.commit()

            super_id = super_user.id
            inst_id = inst.id
            admin_id = admin_user.id
            parent_id = parent_user.id

        yield client, super_id, inst_id, admin_id, parent_id


def test_create_superadmin_cli_and_domain_helper(superadmin_app_client):
    client, _, _, _, _ = superadmin_app_client
    app = client.application

    with app.app_context():
        res = create_superadmin(app, "cli_super@test.com", "pass123", "CLI SuperAdmin")
        assert res is True
        s = User.query.filter_by(email="cli_super@test.com").first()
        assert s is not None
        assert s.role == "SUPER_ADMIN"
        assert s.institution_id is None

        inst, new_admin = create_institution_and_admin(
            name="New Tech College",
            slug="new-tech",
            admin_email="admin@newtech.edu",
            admin_password="pass1234",
            admin_name="Tech Admin"
        )
        assert inst.id is not None
        assert inst.slug == "new-tech"
        assert new_admin.institution_id == inst.id


def test_superadmin_routes_authorization(superadmin_app_client):
    client, _, _, _, _ = superadmin_app_client

    # 1. Anonymous user gets redirected to login
    resp = client.get('/superadmin/institutions')
    assert resp.status_code == 302

    # 2. Login as regular ADMIN -> 403 Forbidden
    client.post('/auth/login', data={'email': 'admin@pilot.edu', 'password': 'adminpass123'})
    resp = client.get('/superadmin/institutions')
    assert resp.status_code == 403
    client.get('/auth/logout')

    # 3. Login as SUPER_ADMIN -> 200 OK
    client.post('/auth/login', data={'email': 'super@safestop.ai', 'password': 'superpass123'})
    resp = client.get('/superadmin/institutions')
    assert resp.status_code == 200
    assert b"Platform Institutions" in resp.data


def test_superadmin_onboard_institution_http(superadmin_app_client):
    client, _, _, _, _ = superadmin_app_client

    # Login as SUPER_ADMIN
    client.post('/auth/login', data={'email': 'super@safestop.ai', 'password': 'superpass123'})

    # Onboard institution via HTTP POST
    post_data = {
        'name': "Greenwood Academy",
        'slug': "greenwood",
        'plan_tier': "PROFESSIONAL",
        'admin_name': "Greenwood Admin",
        'admin_email': "admin@greenwood.edu",
        'admin_password': "greenwoodpass123",
        'admin_phone': "+15554321098"
    }
    resp = client.post('/superadmin/institutions/new', data=post_data, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Greenwood Academy" in resp.data

    with client.application.app_context():
        inst = Institution.query.filter_by(slug="greenwood").first()
        assert inst is not None
        assert inst.plan_tier == "PROFESSIONAL"
        admin = User.query.filter_by(email="admin@greenwood.edu").first()
        assert admin is not None
        assert admin.institution_id == inst.id


def test_deactivate_institution_blocks_user_access(superadmin_app_client):
    client, _, inst_id, admin_id, _ = superadmin_app_client

    # SuperAdmin deactivates institution
    client.post('/auth/login', data={'email': 'super@safestop.ai', 'password': 'superpass123'})
    resp = client.post(f'/superadmin/institutions/{inst_id}/deactivate', follow_redirects=True)
    assert resp.status_code == 200
    client.get('/auth/logout')

    with client.application.app_context():
        inst = db.session.get(Institution, inst_id)
        assert inst.is_active is False

    # Attempt login as admin of deactivated institution -> Rejected
    resp = client.post('/auth/login', data={'email': 'admin@pilot.edu', 'password': 'adminpass123'})
    assert resp.status_code == 200
    assert b"institution has been deactivated" in resp.data.lower() or b"deactivated" in resp.data.lower()
