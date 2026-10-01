import pytest
import json
from app import create_app
from app.models import db, Institution, User, Student, Bus, Driver, DriverDocument, AuditLog

@pytest.fixture
def export_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app

def test_admin_compliance_export_enterprise_granted(export_app):
    client = export_app.test_client()
    with export_app.app_context():
        inst = Institution(name="Enterprise Export School", slug="enterprise-export", plan_tier="ENTERPRISE", subscription_status="ACTIVE")
        db.session.add(inst)
        db.session.commit()

        admin = User(email="ent_admin@test.com", password_hash="hash", role="ADMIN", full_name="Enterprise Admin", institution_id=inst.id)
        admin.set_password("pass123")
        db.session.add(admin)

        driver_user = User(email="driver_exp@test.com", password_hash="hash", role="DRIVER", full_name="John Driver", institution_id=inst.id)
        db.session.add(driver_user)
        db.session.commit()

        driver = Driver(full_name="John Driver", license_number="DL123", phone="555-0100", institution_id=inst.id, user_id=driver_user.id)
        db.session.add(driver)
        db.session.commit()

        doc = DriverDocument(driver_id=driver.id, doc_type="Commercial License", doc_name="License Copy.pdf", file_path="license.pdf")
        bus = Bus(bus_code="BUS-101", registration_number="REG-101", capacity=40, institution_id=inst.id)
        db.session.add_all([doc, bus])
        db.session.commit()

        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    res = client.get('/admin/export/compliance')
    assert res.status_code == 200
    assert 'text/csv' in res.content_type
    assert 'SafeStop Platform Compliance Export Report' in res.get_data(as_text=True)
    assert 'John Driver' in res.get_data(as_text=True)
    assert 'BUS-101' in res.get_data(as_text=True)

def test_admin_compliance_export_starter_forbidden(export_app):
    client = export_app.test_client()
    with export_app.app_context():
        inst = Institution(name="Starter Export School", slug="starter-export", plan_tier="STARTER", subscription_status="ACTIVE")
        db.session.add(inst)
        db.session.commit()

        admin = User(email="starter_admin@test.com", password_hash="hash", role="ADMIN", full_name="Starter Admin", institution_id=inst.id)
        admin.set_password("pass123")
        db.session.add(admin)
        db.session.commit()

        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    res = client.get('/admin/export/compliance')
    assert res.status_code == 403

def test_superadmin_export_institution(export_app):
    client = export_app.test_client()
    with export_app.app_context():
        super_admin = User(email="super_export@safestop.ai", password_hash="hash", role="SUPER_ADMIN", full_name="Super Export Admin", institution_id=None)
        super_admin.set_password("pass123")

        inst = Institution(name="Tenant To Export", slug="tenant-to-export", plan_tier="PROFESSIONAL", subscription_status="ACTIVE")
        db.session.add_all([super_admin, inst])
        db.session.commit()

        student = Student(full_name="Child One", roll_number="ROLL-001", grade_section="5th Grade", institution_id=inst.id)
        bus = Bus(bus_code="BUS-55", registration_number="REG-55", capacity=30, institution_id=inst.id)
        db.session.add_all([student, bus])
        db.session.commit()

        super_id = super_admin.id
        inst_id = inst.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(super_id)
        sess['_fresh'] = True

    res = client.get(f'/superadmin/institutions/{inst_id}/export')
    assert res.status_code == 200
    assert 'application/json' in res.content_type
    payload = json.loads(res.get_data(as_text=True))
    assert payload['institution']['name'] == "Tenant To Export"
    assert len(payload['students']) == 1
    assert payload['students'][0]['full_name'] == "Child One"
    assert len(payload['buses']) == 1

def test_superadmin_offboard_institution(export_app):
    client = export_app.test_client()
    with export_app.app_context():
        super_admin = User(email="super_offboard@safestop.ai", password_hash="hash", role="SUPER_ADMIN", full_name="Super Offboard Admin", institution_id=None)
        super_admin.set_password("pass123")

        inst = Institution(name="Tenant To Offboard", slug="tenant-to-offboard", plan_tier="STARTER", subscription_status="ACTIVE", is_active=True)
        db.session.add_all([super_admin, inst])
        db.session.commit()

        super_id = super_admin.id
        inst_id = inst.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(super_id)
        sess['_fresh'] = True

    res = client.post(f'/superadmin/institutions/{inst_id}/offboard', follow_redirects=True)
    assert res.status_code == 200

    with export_app.app_context():
        inst_db = db.session.get(Institution, inst_id)
        assert inst_db.is_active is False
        assert inst_db.subscription_status == 'CANCELED'

        audit_entry = AuditLog.query.filter_by(institution_id=inst_id, action='TENANT_OFFBOARDED').first()
        assert audit_entry is not None
        assert "offboarded by SuperAdmin" in audit_entry.details
