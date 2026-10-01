import pytest
from app import create_app
from app.models import db, Institution, User, Driver
from app.tenancy import institution_has_feature, PLAN_FEATURES

@pytest.fixture
def plan_app_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            # Create STARTER institution
            inst_starter = Institution(name="Starter Academy", slug="starter-acad", plan_tier="STARTER")
            db.session.add(inst_starter)
            db.session.commit()

            admin_starter = User(
                institution_id=inst_starter.id,
                email="admin@starter.com",
                role="ADMIN",
                full_name="Starter Admin"
            )
            admin_starter.set_password("pass123")

            u_driver_starter = User(
                institution_id=inst_starter.id,
                email="driver@starter.com",
                role="DRIVER",
                full_name="Starter Driver"
            )
            u_driver_starter.set_password("pass123")
            db.session.add_all([admin_starter, u_driver_starter])
            db.session.commit()

            driver_starter = Driver(
                user_id=u_driver_starter.id,
                institution_id=inst_starter.id,
                full_name="Starter Driver",
                phone="+15551112222",
                license_number="LIC-START"
            )
            db.session.add(driver_starter)
            db.session.commit()

            # Create ENTERPRISE institution
            inst_ent = Institution(name="Enterprise Tech", slug="ent-tech", plan_tier="ENTERPRISE")
            db.session.add(inst_ent)
            db.session.commit()

            admin_ent = User(
                institution_id=inst_ent.id,
                email="admin@enterprise.com",
                role="ADMIN",
                full_name="Enterprise Admin"
            )
            admin_ent.set_password("pass123")

            u_driver_ent = User(
                institution_id=inst_ent.id,
                email="driver@enterprise.com",
                role="DRIVER",
                full_name="Enterprise Driver"
            )
            u_driver_ent.set_password("pass123")
            db.session.add_all([admin_ent, u_driver_ent])
            db.session.commit()

            driver_ent = Driver(
                user_id=u_driver_ent.id,
                institution_id=inst_ent.id,
                full_name="Enterprise Driver",
                phone="+15553334444",
                license_number="LIC-ENT"
            )
            db.session.add(driver_ent)
            db.session.commit()

            starter_inst_id = inst_starter.id
            ent_inst_id = inst_ent.id

        yield client, starter_inst_id, ent_inst_id


def test_plan_feature_mapping_logic():
    assert PLAN_FEATURES['STARTER']['analytics_dashboard'] is False
    assert PLAN_FEATURES['PROFESSIONAL']['analytics_dashboard'] is True
    assert PLAN_FEATURES['ENTERPRISE']['driver_telemetry'] is True


def test_starter_institution_feature_gating_403(plan_app_client):
    client, starter_inst_id, _ = plan_app_client

    # Admin of STARTER institution -> 403 on analytics
    client.post('/auth/login', data={'email': 'admin@starter.com', 'password': 'pass123'})
    resp = client.get('/admin/analytics')
    assert resp.status_code == 403
    client.get('/auth/logout')

    # Driver of STARTER institution -> 403 on telemetry simulate
    client.post('/auth/login', data={'email': 'driver@starter.com', 'password': 'pass123'})
    resp = client.post('/driver/telemetry/simulate', data={'sim_type': 'DROWSINESS'})
    assert resp.status_code == 403


def test_enterprise_institution_access_granted(plan_app_client):
    client, _, ent_inst_id = plan_app_client

    # Admin of ENTERPRISE institution -> 200 on analytics
    client.post('/auth/login', data={'email': 'admin@enterprise.com', 'password': 'pass123'})
    resp = client.get('/admin/analytics')
    assert resp.status_code == 200
    client.get('/auth/logout')

    # Driver of ENTERPRISE institution -> 200 on telemetry simulate
    client.post('/auth/login', data={'email': 'driver@enterprise.com', 'password': 'pass123'})
    resp = client.post('/driver/telemetry/simulate', data={'sim_type': 'DROWSINESS'}, follow_redirects=True)
    assert resp.status_code == 200


def test_dynamic_plan_tier_upgrade_immediately_updates_access(plan_app_client):
    client, starter_inst_id, _ = plan_app_client

    # 1. STARTER admin is 403 initially
    client.post('/auth/login', data={'email': 'admin@starter.com', 'password': 'pass123'})
    resp = client.get('/admin/analytics')
    assert resp.status_code == 403

    # 2. Upgrade plan_tier to PROFESSIONAL in DB
    with client.application.app_context():
        inst = db.session.get(Institution, starter_inst_id)
        inst.plan_tier = 'PROFESSIONAL'
        db.session.commit()

    # 3. Next request immediately grants access (200 OK)
    resp = client.get('/admin/analytics')
    assert resp.status_code == 200
