import logging
from flask import current_app
from app.models import db, Notification, User
from app.notifications.providers import get_notification_provider

logger = logging.getLogger(__name__)

def send_notification(user_id, title, message, category='INFO', action_link=None):
    """
    Create and persist in-app notification for a specific user, 
    and send outbound SMS/WhatsApp for high-priority safety categories.
    """
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        action_link=action_link
    )
    db.session.add(notif)
    db.session.commit()

    # Outbound Real Notification Delivery
    outbound_categories = getattr(current_app, 'config', {}).get(
        'OUTBOUND_SMS_CATEGORIES', 
        {'BOARDING', 'ARRIVAL', 'SAFE_DROP', 'EMERGENCY', 'WRONG_BUS'}
    )

    if category in outbound_categories:
        try:
            user = db.session.get(User, user_id)
            if user and user.has_valid_phone():
                provider = get_notification_provider()
                provider.send_sms(user.phone, f"{title}: {message}")
        except Exception as e:
            logger.error(f"Outbound notification delivery failed for user {user_id}: {e}")

    return notif


def broadcast_admin_notification(title, message, category='EMERGENCY', institution_id=None):
    """Broadcast notification to all active school admins (optionally scoped by institution)."""
    query = User.query.filter_by(role='ADMIN', is_active=True)
    if institution_id is not None:
        query = query.filter_by(institution_id=institution_id)

    admins = query.all()
    notifs = []
    
    outbound_categories = getattr(current_app, 'config', {}).get(
        'OUTBOUND_SMS_CATEGORIES', 
        {'BOARDING', 'ARRIVAL', 'SAFE_DROP', 'EMERGENCY', 'WRONG_BUS'}
    )
    provider = get_notification_provider() if category in outbound_categories else None

    for admin in admins:
        n = Notification(
            user_id=admin.id,
            title=title,
            message=message,
            category=category
        )
        db.session.add(n)
        notifs.append(n)

        if provider and admin.has_valid_phone():
            try:
                provider.send_sms(admin.phone, f"{title}: {message}")
            except Exception as e:
                logger.error(f"Outbound admin notification delivery failed for admin {admin.id}: {e}")

    db.session.commit()
    return notifs


def generate_daily_arrival_digest(parent_id=None):
    """
    Generates a daily safe-arrival summary digest for specified parent_id or all parents.
    Summarizes today's boarding, drop-off, or absence status for each student.
    Returns list of created Notification objects.
    """
    from app.models import Parent, Student, Attendance, StudentAbsenceRequest, Trip
    from datetime import datetime

    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    query = Parent.query
    if parent_id:
        query = query.filter_by(id=parent_id)
    parents = query.all()

    created_notifs = []
    for parent in parents:
        if not parent.user_id:
            continue

        students = Student.query.filter_by(parent_id=parent.id).all()
        if not students:
            continue

        student_summaries = []
        for st in students:
            # Check absence
            absence = StudentAbsenceRequest.query.filter_by(student_id=st.id, absence_date=today_str).filter(StudentAbsenceRequest.status != 'CANCELLED').first()
            if absence:
                student_summaries.append(f"• {st.full_name}: Excused Absence ({absence.reason or 'Recorded'})")
                continue

            # Check attendance today
            attendances = Attendance.query.join(Trip).filter(
                Attendance.student_id == st.id,
                db.func.date(Attendance.verification_time) == today_str
            ).all()

            if not attendances:
                student_summaries.append(f"• {st.full_name}: No transit activity recorded today")
            else:
                statuses = []
                for att in attendances:
                    board_time = att.verification_time.strftime('%H:%M') if att.verification_time else 'N/A'
                    if att.is_dropped_off and att.drop_verification_time:
                        drop_time = att.drop_verification_time.strftime('%H:%M')
                        statuses.append(f"Boarded at {board_time}, Dropped off at {drop_time}")
                    else:
                        statuses.append(f"Boarded at {board_time} (In Transit / Drop Pending)")
                student_summaries.append(f"• {st.full_name}: " + "; ".join(statuses))

        digest_body = f"SafeStop Daily Digest ({today_str}):\n" + "\n".join(student_summaries)
        notif = send_notification(
            user_id=parent.user_id,
            title="📊 Daily Safe-Arrival Digest",
            message=digest_body,
            category="SAFE_DROP"
        )
        created_notifs.append(notif)

    return created_notifs
