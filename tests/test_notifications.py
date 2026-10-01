import pytest  # type: ignore # pyright: ignore[reportMissingImports]
from app import create_app
from app.models import db, User, Parent, Notification
from app.notifications.service import send_notification, broadcast_admin_notification
from app.notifications.providers import ConsoleProvider, TwilioProvider

@pytest.fixture
def notif_client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'

    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()

            ConsoleProvider.clear_sent_messages()

            u_parent = User(email="parent_notif@test.com", role="PARENT", full_name="Parent Notif", phone="+91 98200 99999")
            u_parent.set_password("pass123")
            u_admin = User(email="admin_notif@test.com", role="ADMIN", full_name="Admin Notif", phone="+91 98200 88888")
            u_admin.set_password("pass123")
            db.session.add_all([u_parent, u_admin])
            db.session.flush()

            p = Parent(user_id=u_parent.id)
            db.session.add(p)
            db.session.commit()

            user_id = u_parent.id
            admin_id = u_admin.id

        yield client, user_id, admin_id


def test_high_priority_notification_triggers_outbound_sms(notif_client):
    client, parent_user_id, admin_id = notif_client
    ConsoleProvider.clear_sent_messages()

    with client.application.app_context():
        # Triggers SAFE_DROP notification
        notif = send_notification(
            user_id=parent_user_id,
            title="Safe Drop Confirmed",
            message="Your student was safely dropped at Stop 2",
            category="SAFE_DROP"
        )

        # 1. In-app row check
        assert notif.id is not None
        db_notif = Notification.query.get(notif.id)
        assert db_notif.category == "SAFE_DROP"

        # 2. Outbound SMS check
        assert len(ConsoleProvider.sent_messages) == 1
        sent = ConsoleProvider.sent_messages[0]
        assert sent['type'] == 'SMS'
        assert sent['to'] == "+91 98200 99999"
        assert "Safe Drop Confirmed" in sent['message']


def test_low_urgency_category_skips_outbound_sms(notif_client):
    client, parent_user_id, admin_id = notif_client
    ConsoleProvider.clear_sent_messages()

    with client.application.app_context():
        # Triggers low-urgency DELAY notification
        notif = send_notification(
            user_id=parent_user_id,
            title="Minor Delay",
            message="Bus is 5 minutes late due to traffic",
            category="DELAY"
        )

        # 1. In-app row check
        assert notif.id is not None

        # 2. Outbound SMS check (Should be empty for DELAY category)
        assert len(ConsoleProvider.sent_messages) == 0


def test_broadcast_admin_notification_outbound_sms(notif_client):
    client, parent_user_id, admin_id = notif_client
    ConsoleProvider.clear_sent_messages()

    with client.application.app_context():
        # Triggers EMERGENCY admin broadcast
        notifs = broadcast_admin_notification(
            title="🚨 CRITICAL EMERGENCY",
            message="SOS button pressed by Driver",
            category="EMERGENCY"
        )

        assert len(notifs) >= 1
        assert len(ConsoleProvider.sent_messages) >= 1
        sent = ConsoleProvider.sent_messages[0]
        assert sent['to'] == "+91 98200 88888"
        assert "CRITICAL EMERGENCY" in sent['message']


def test_provider_failure_graceful_handling(notif_client, monkeypatch):
    client, parent_user_id, admin_id = notif_client
    ConsoleProvider.clear_sent_messages()

    # Mock provider to raise exception
    def failing_send_sms(self, to_phone, message):
        raise Exception("Network connection timeout")

    monkeypatch.setattr(ConsoleProvider, "send_sms", failing_send_sms)

    with client.application.app_context():
        # Call notification service during simulated provider outage
        notif = send_notification(
            user_id=parent_user_id,
            title="🚨 WRONG BUS ALERT",
            message="Student boarded wrong bus",
            category="WRONG_BUS"
        )

        # In-app notification must still succeed cleanly despite SMS provider failure
        assert notif.id is not None
        db_notif = Notification.query.get(notif.id)
        assert db_notif is not None
