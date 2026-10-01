import logging
from datetime import datetime, timedelta
from app.models import db, Driver, DriverDocument, DriverTraining, Alert, AuditLog, Institution

logger = logging.getLogger(__name__)

def check_expiring_driver_credentials(institution_id=None, threshold_days=30):
    """
    Checks for expiring driver documents and safety training certificates within threshold_days.
    Automatically generates system Alerts for school admins and broadcasts admin notifications.
    """
    cutoff_date = datetime.utcnow().date() + timedelta(days=threshold_days)
    today = datetime.utcnow().date()

    from app.notifications.service import broadcast_admin_notification

    if institution_id:
        institutions = Institution.query.filter_by(id=institution_id, is_active=True).all()
    else:
        institutions = Institution.query.filter_by(is_active=True).all()

    all_warnings = []

    for inst in institutions:
        inst_id = inst.id
        inst_warnings = []

        # Check Driver Trainings
        trainings = DriverTraining.query.join(Driver).filter(
            Driver.institution_id == inst_id,
            DriverTraining.expiry_date != None
        ).all()
        for t in trainings:
            if t.expiry_date:
                try:
                    exp_date = datetime.strptime(t.expiry_date, '%Y-%m-%d').date()
                    if today <= exp_date <= cutoff_date:
                        days_left = (exp_date - today).days
                        msg = f"Driver Safety Training '{t.training_name}' for Driver {t.driver.full_name} expires in {days_left} days ({t.expiry_date})."
                        w = {
                            'type': 'TRAINING_EXPIRING',
                            'driver_name': t.driver.full_name,
                            'title': t.training_name,
                            'expiry_date': t.expiry_date,
                            'days_left': days_left,
                            'message': msg,
                            'institution_id': inst_id
                        }
                        inst_warnings.append(w)
                except ValueError:
                    pass

        # Check Driver Documents
        docs = DriverDocument.query.join(Driver).filter(
            Driver.institution_id == inst_id,
            DriverDocument.expiry_date != None
        ).all()
        for d in docs:
            if d.expiry_date:
                try:
                    exp_date = datetime.strptime(d.expiry_date, '%Y-%m-%d').date()
                    if today <= exp_date <= cutoff_date:
                        days_left = (exp_date - today).days
                        doc_title = getattr(d, 'doc_type', 'Document')
                        doc_num = getattr(d, 'doc_name', '')
                        msg = f"Driver Document '{doc_title}' ({doc_num}) for Driver {d.driver.full_name} expires in {days_left} days ({d.expiry_date})."
                        w = {
                            'type': 'DOCUMENT_EXPIRING',
                            'driver_name': d.driver.full_name,
                            'title': doc_title,
                            'expiry_date': d.expiry_date,
                            'days_left': days_left,
                            'message': msg,
                            'institution_id': inst_id
                        }
                        inst_warnings.append(w)
                except ValueError:
                    pass

        # Persist Alerts and broadcast notifications for this institution
        for w in inst_warnings:
            alert = Alert(
                institution_id=inst_id,
                alert_type='DRIVER_COMPLIANCE',
                risk_score=30,
                severity='WARNING',
                description=w['message']
            )
            db.session.add(alert)
            broadcast_admin_notification(
                title=f"⚠️ Compliance Warning: {w['type']}",
                message=w['message'],
                category='EMERGENCY',
                institution_id=inst_id
            )
            all_warnings.append(w)

    db.session.commit()
    return all_warnings

