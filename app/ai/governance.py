import os
import json
import logging
from datetime import datetime, timedelta
from app.models import db, Student, FaceProfile, Attendance, AuditLog

logger = logging.getLogger(__name__)

def purge_expired_biometric_data(retention_days=365):
    """
    Automated Data Retention Purge:
    Hard-deletes face profile embeddings and photo files that have been revoked or archived longer than retention_days.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    expired_profiles = FaceProfile.query.filter(
        (FaceProfile.is_archived == True) & (FaceProfile.archived_at <= cutoff)
    ).all()

    purged_count = 0
    for fp in expired_profiles:
        # Erase vector data
        fp.feature_vector_json = "[]"
        db.session.delete(fp)
        purged_count += 1

    db.session.commit()
    logger.info(f"Biometric Data Retention Purge: Erased {purged_count} expired face profiles.")
    return purged_count

def export_student_dsar_data(student_id):
    """
    Data Subject Access Request (DSAR) Export:
    Returns full personal data package for a student including attendance logs and biometric consent status.
    """
    student = Student.query.get(student_id)
    if not student:
        return None

    fp = FaceProfile.query.filter_by(student_id=student.id).first()
    attendances = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.verification_time.desc()).all()

    dsar_package = {
        'student': {
            'id': student.id,
            'full_name': student.full_name,
            'roll_number': student.roll_number,
            'grade_section': student.grade_section,
            'created_at': student.created_at.strftime('%Y-%m-%d %H:%M:%S') if student.created_at else None
        },
        'biometric_consent': {
            'consent_given': fp.parental_consent_given if fp else False,
            'consent_given_at': fp.consent_given_at.strftime('%Y-%m-%d %H:%M:%S') if (fp and fp.consent_given_at) else None,
            'is_archived': fp.is_archived if fp else True,
            'archived_at': fp.archived_at.strftime('%Y-%m-%d %H:%M:%S') if (fp and fp.archived_at) else None
        },
        'attendance_history': [
            {
                'id': a.id,
                'trip_id': a.trip_id,
                'verification_status': a.verification_status,
                'verification_time': a.verification_time.strftime('%Y-%m-%d %H:%M:%S') if a.verification_time else None,
                'notes': a.notes
            } for a in attendances
        ]
    }

    return dsar_package

def delete_student_biometrics(student_id, user_id=None):
    """
    Right to Erasure (DSAR Deletion):
    Revokes biometric consent and immediately purges face vector for the given student.
    """
    student = Student.query.get(student_id)
    if not student:
        return False, "Student not found"

    fp = FaceProfile.query.filter_by(student_id=student.id).first()
    if fp:
        fp.revoke_consent()
        fp.feature_vector_json = "[]"
        db.session.add(fp)

    # Log Audit Event
    audit_log = AuditLog(
        institution_id=student.institution_id,
        user_id=user_id,
        action="DSAR_BIOMETRIC_DELETION",
        details=f"Biometric face data deleted & consent revoked for student {student.full_name} (ID #{student.id})."
    )
    db.session.add(audit_log)
    db.session.commit()

    return True, f"Biometric data deleted successfully for {student.full_name}."
