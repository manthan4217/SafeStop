import stripe  # type: ignore # pyright: ignore[reportMissingImports]
from flask import Blueprint, request, jsonify, redirect, url_for, current_app, abort
from flask_login import login_required, current_user
from app.models import db, Institution
from app.__init__ import role_required

billing_bp = Blueprint('billing', __name__)

@billing_bp.route('/create-checkout-session', methods=['POST'])
@login_required
@role_required('ADMIN', 'SUPER_ADMIN')
def create_checkout_session():
    """
    Creates a Stripe Checkout Session for subscription purchasing/upgrading.
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form

    target_tier = data.get('plan_tier', 'PROFESSIONAL').upper()
    if target_tier not in ('STARTER', 'PROFESSIONAL', 'ENTERPRISE'):
        return jsonify({'status': 'ERROR', 'message': 'Invalid plan tier specified.'}), 400

    price_map = {
        'STARTER': current_app.config.get('STRIPE_PRICE_ID_STARTER'),
        'PROFESSIONAL': current_app.config.get('STRIPE_PRICE_ID_PROFESSIONAL'),
        'ENTERPRISE': current_app.config.get('STRIPE_PRICE_ID_ENTERPRISE')
    }
    price_id = price_map.get(target_tier)

    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY')

    inst_id = getattr(current_user, 'institution_id', None)
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            customer_email=current_user.email,
            client_reference_id=str(inst_id) if inst_id else None,
            metadata={
                'institution_id': str(inst_id or ''),
                'target_plan_tier': target_tier
            },
            success_url=url_for('admin.dashboard', _external=True) + '?billing=success',
            cancel_url=url_for('admin.dashboard', _external=True) + '?billing=cancel',
        )
    except Exception as e:
        return jsonify({'status': 'ERROR', 'message': f"Stripe Checkout error: {str(e)}"}), 500

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'SUCCESS',
            'checkout_url': getattr(session, 'url', None) or session.get('url'),
            'session_id': getattr(session, 'id', None) or session.get('id')
        }), 200

    checkout_url = getattr(session, 'url', None) or session.get('url')
    if checkout_url:
        return redirect(checkout_url)
    return redirect(url_for('admin.dashboard'))

@billing_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """
    Handles Stripe asynchronous webhook events (CSRF exempted).
    """
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')

    event = None

    if sig_header and endpoint_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, endpoint_secret
            )
        except ValueError:
            return jsonify({'status': 'ERROR', 'message': 'Invalid payload'}), 400
        except stripe.error.SignatureVerificationError:  # type: ignore
            return jsonify({'status': 'ERROR', 'message': 'Invalid signature'}), 400
    else:
        # Fallback for testing environments without webhook signing
        try:
            event = request.get_json(force=True)
        except Exception:
            return jsonify({'status': 'ERROR', 'message': 'Invalid JSON body'}), 400

    if not event or not isinstance(event, dict):
        return jsonify({'status': 'ERROR', 'message': 'Malformed event payload'}), 400

    event_type = event.get('type')
    event_data = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        inst_id_str = event_data.get('client_reference_id') or event_data.get('metadata', {}).get('institution_id')
        customer_id = event_data.get('customer')
        subscription_id = event_data.get('subscription')
        target_tier = event_data.get('metadata', {}).get('target_plan_tier')

        inst = None
        if inst_id_str and str(inst_id_str).isdigit():
            inst = db.session.get(Institution, int(inst_id_str))
        if not inst and customer_id:
            inst = Institution.query.filter_by(stripe_customer_id=customer_id).first()

        if inst:
            if customer_id:
                inst.stripe_customer_id = customer_id
            if subscription_id:
                inst.stripe_subscription_id = subscription_id
            if target_tier and target_tier in ('STARTER', 'PROFESSIONAL', 'ENTERPRISE'):
                inst.plan_tier = target_tier
            inst.subscription_status = 'ACTIVE'
            db.session.commit()

    elif event_type in ('customer.subscription.updated', 'customer.subscription.created'):
        sub_id = event_data.get('id')
        customer_id = event_data.get('customer')
        raw_status = event_data.get('status', 'active').lower()

        status_mapping = {
            'active': 'ACTIVE',
            'past_due': 'PAST_DUE',
            'canceled': 'CANCELED',
            'unpaid': 'PAST_DUE',
            'trialing': 'TRIALING'
        }
        mapped_status = status_mapping.get(raw_status, 'ACTIVE')

        inst = None
        if sub_id:
            inst = Institution.query.filter_by(stripe_subscription_id=sub_id).first()
        if not inst and customer_id:
            inst = Institution.query.filter_by(stripe_customer_id=customer_id).first()

        if inst:
            inst.subscription_status = mapped_status
            db.session.commit()

    elif event_type == 'customer.subscription.deleted':
        sub_id = event_data.get('id')
        customer_id = event_data.get('customer')

        inst = None
        if sub_id:
            inst = Institution.query.filter_by(stripe_subscription_id=sub_id).first()
        if not inst and customer_id:
            inst = Institution.query.filter_by(stripe_customer_id=customer_id).first()

        if inst:
            inst.subscription_status = 'CANCELED'
            db.session.commit()

    return jsonify({'status': 'success'}), 200
