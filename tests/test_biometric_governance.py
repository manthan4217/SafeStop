from datetime import datetime, timedelta
import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, Institution, User, Parent, Student, FaceProfile, AuditLog
from app.ai.governance import purge_expired_biometric_data, export_student_dsar_data, delete_student_biometrics

@pytest.fixture
def bio_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            inst = Institution(name="Bio Governance Inst", slug="bio-inst")
            db.session.add(inst)
            db.session.flush()

            u_parent = User(email="bio_parent@test.com", role="PARENT", full_name="Bio Parent", institution_id=inst.id)
            u_parent.set_password("pass123")
            db.session.add(u_parent)
            db.session.flush()

            parent = Parent(user_id=u_parent.id, institution_id=inst.id)
            db.session.add(parent)
            db.session.flush()

            student = Student(full_name="Bio Student", roll_number="BIO-001", parent_id=parent.id, institution_id=inst.id)
            db.session.add(student)
            db.session.flush()

            fp = FaceProfile(student_id=student.id, feature_vector_json="[0.1, 0.2, 0.3]", image_path="bio_student.png")
            fp.grant_consent(user_id=u_parent.id)
            db.session.add(fp)
            db.session.commit()

            yield {
                'client': client,
                'app': app,
                'inst_id': inst.id,
                'parent_user_id': u_parent.id,
                'parent_id': parent.id,
                'student_id': student.id,
                'face_profile_id': fp.id
            }

def test_consent_grant_and_revoke(bio_app):
    fp = FaceProfile.query.get(bio_app['face_profile_id'])
    assert fp.parental_consent_given is True
    assert fp.consent_given_by_user_id == bio_app['parent_user_id']
    assert fp.is_archived is False

    fp.revoke_consent()
    db.session.commit()

    fp_reloaded = FaceProfile.query.get(bio_app['face_profile_id'])
    assert fp_reloaded.parental_consent_given is False
    assert fp_reloaded.is_archived is True
    assert fp_reloaded.archived_at is not None

def test_dsar_export_utility(bio_app):
    dsar = export_student_dsar_data(bio_app['student_id'])
    assert dsar is not None
    assert dsar['student']['full_name'] == "Bio Student"
    assert dsar['biometric_consent']['consent_given'] is True

def test_dsar_deletion_utility(bio_app):
    success, msg = delete_student_biometrics(bio_app['student_id'], user_id=bio_app['parent_user_id'])
    assert success is True
    assert "deleted successfully" in msg

    fp = FaceProfile.query.get(bio_app['face_profile_id'])
    assert fp.parental_consent_given is False
    assert fp.feature_vector_json == "[]"

    audit = AuditLog.query.filter_by(action="DSAR_BIOMETRIC_DELETION").first()
    assert audit is not None
    assert audit.user_id == bio_app['parent_user_id']

def test_biometric_data_retention_purge(bio_app):
    fp = FaceProfile.query.get(bio_app['face_profile_id'])
    fp.revoke_consent()
    # Backdate archived_at to 400 days ago
    fp.archived_at = datetime.utcnow() - timedelta(days=400)
    db.session.commit()

    purged = purge_expired_biometric_data(retention_days=365)
    assert purged == 1

    fp_check = FaceProfile.query.get(bio_app['face_profile_id'])
    assert fp_check is None

def test_parent_dsar_http_endpoints(bio_app):
    client = bio_app['client']
    # Login as parent
    client.post('/auth/login', data={'email': 'bio_parent@test.com', 'password': 'pass123'}, follow_redirects=True)

    # Export DSAR
    res = client.get(f"/parent/dsar/export/{bio_app['student_id']}")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data['student']['roll_number'] == "BIO-001"

    # Delete Biometrics
    res_del = client.post(f"/parent/dsar/delete-biometrics/{bio_app['student_id']}", follow_redirects=True)
    assert res_del.status_code == 200

    fp = FaceProfile.query.get(bio_app['face_profile_id'])
    assert fp.parental_consent_given is False
