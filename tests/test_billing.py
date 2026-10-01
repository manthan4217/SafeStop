import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.models import db, Institution, User
from app.tenancy import institution_has_feature

@pytest.fixture
def billing_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['NOTIFICATION_PROVIDER'] = 'console'
    app.config['STRIPE_SECRET_KEY'] = 'sk_test_mock_secret_key'
    app.config['STRIPE_WEBHOOK_SECRET'] = 'whsec_mock_webhook_secret'

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app

def test_create_checkout_session_admin(billing_app):
    client = billing_app.test_client()
    with billing_app.app_context():
        inst = Institution(name="Billing Test School", slug="billing-test", plan_tier="STARTER", subscription_status="ACTIVE")
        db.session.add(inst)
        db.session.commit()

        admin = User(email="billing_admin@test.com", password_hash="hash", role="ADMIN", full_name="Billing Admin", institution_id=inst.id)
        admin.set_password("pass123")
        db.session.add(admin)
        db.session.commit()

        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)
        sess['_fresh'] = True

    mock_session = MagicMock()
    mock_session.id = "cs_test_123"
    mock_session.url = "https://checkout.stripe.com/pay/cs_test_123"

    with patch('stripe.checkout.Session.create', return_value=mock_session):
        res = client.post('/billing/create-checkout-session', json={
            'plan_tier': 'PROFESSIONAL'
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data['status'] == 'SUCCESS'
        assert data['checkout_url'] == "https://checkout.stripe.com/pay/cs_test_123"
        assert data['session_id'] == "cs_test_123"

def test_create_checkout_session_parent_unauthorized(billing_app):
    client = billing_app.test_client()
    with billing_app.app_context():
        inst = Institution(name="Parent Billing School", slug="parent-billing", plan_tier="STARTER")
        db.session.add(inst)
        db.session.commit()

        parent = User(email="billing_parent@test.com", password_hash="hash", role="PARENT", full_name="Billing Parent", institution_id=inst.id)
        parent.set_password("pass123")
        db.session.add(parent)
        db.session.commit()

        parent_id = parent.id

    with client.session_transaction() as sess:
        sess['_user_id'] = str(parent_id)
        sess['_fresh'] = True

    res = client.post('/billing/create-checkout-session', json={
        'plan_tier': 'PROFESSIONAL'
    })
    # role_required redirects (302) or aborts (403) for non-admin
    assert res.status_code in (302, 403)

def test_webhook_checkout_session_completed(billing_app):
    client = billing_app.test_client()
    with billing_app.app_context():
        inst = Institution(name="Webhook Inst", slug="webhook-inst", plan_tier="STARTER", subscription_status="ACTIVE")
        db.session.add(inst)
        db.session.commit()
        inst_id = inst.id

    webhook_payload = {
        'type': 'checkout.session.completed',
        'data': {
            'object': {
                'client_reference_id': str(inst_id),
                'customer': 'cus_test_999',
                'subscription': 'sub_test_888',
                'metadata': {
                    'target_plan_tier': 'ENTERPRISE'
                }
            }
        }
    }

    res = client.post('/billing/webhook', json=webhook_payload)
    assert res.status_code == 200
    assert res.get_json()['status'] == 'success'

    with billing_app.app_context():
        updated_inst = db.session.get(Institution, inst_id)
        assert updated_inst.stripe_customer_id == 'cus_test_999'
        assert updated_inst.stripe_subscription_id == 'sub_test_888'
        assert updated_inst.plan_tier == 'ENTERPRISE'
        assert updated_inst.subscription_status == 'ACTIVE'

def test_webhook_subscription_updated_past_due_blocks_access(billing_app):
    client = billing_app.test_client()
    with billing_app.app_context():
        inst = Institution(
            name="Past Due Inst",
            slug="pastdue-inst",
            plan_tier="ENTERPRISE",
            stripe_customer_id="cus_pastdue",
            stripe_subscription_id="sub_pastdue",
            subscription_status="ACTIVE"
        )
        db.session.add(inst)
        db.session.commit()
        inst_id = inst.id

    # Verify initial feature access
    with billing_app.app_context():
        inst_db = db.session.get(Institution, inst_id)
        assert institution_has_feature(inst_db, 'driver_telemetry') is True

    # Fire webhook sub updated -> past_due
    webhook_payload = {
        'type': 'customer.subscription.updated',
        'data': {
            'object': {
                'id': 'sub_pastdue',
                'customer': 'cus_pastdue',
                'status': 'past_due'
            }
        }
    }

    res = client.post('/billing/webhook', json=webhook_payload)
    assert res.status_code == 200

    with billing_app.app_context():
        inst_db = db.session.get(Institution, inst_id)
        assert inst_db.subscription_status == 'PAST_DUE'
        # Feature access should now be blocked due to PAST_DUE
        assert institution_has_feature(inst_db, 'driver_telemetry') is False

def test_webhook_subscription_deleted_canceled(billing_app):
    client = billing_app.test_client()
    with billing_app.app_context():
        inst = Institution(
            name="Canceled Inst",
            slug="canceled-inst",
            plan_tier="PROFESSIONAL",
            stripe_customer_id="cus_canceled",
            stripe_subscription_id="sub_canceled",
            subscription_status="ACTIVE"
        )
        db.session.add(inst)
        db.session.commit()
        inst_id = inst.id

    webhook_payload = {
        'type': 'customer.subscription.deleted',
        'data': {
            'object': {
                'id': 'sub_canceled',
                'customer': 'cus_canceled'
            }
        }
    }

    res = client.post('/billing/webhook', json=webhook_payload)
    assert res.status_code == 200

    with billing_app.app_context():
        inst_db = db.session.get(Institution, inst_id)
        assert inst_db.subscription_status == 'CANCELED'
        assert institution_has_feature(inst_db, 'analytics_dashboard') is False
