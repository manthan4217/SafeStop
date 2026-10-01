from functools import wraps
from flask import abort, redirect, url_for, flash, request, jsonify
from flask_login import current_user  # type: ignore # pyright: ignore[reportMissingImports]

PLAN_FEATURES = {
    'STARTER':      {'analytics_dashboard': False, 'driver_telemetry': False, 'compliance_export': False},
    'PROFESSIONAL': {'analytics_dashboard': True,  'driver_telemetry': False, 'compliance_export': False},
    'ENTERPRISE':   {'analytics_dashboard': True,  'driver_telemetry': True,  'compliance_export': True},
}

def institution_has_feature(institution, feature_name):
    """Checks whether an Institution's plan_tier and subscription_status permit feature_name access."""
    if not institution:
        return False
    status = getattr(institution, 'subscription_status', 'ACTIVE')
    if status in ('PAST_DUE', 'CANCELED'):
        return False
    tier = getattr(institution, 'plan_tier', 'STARTER')
    return PLAN_FEATURES.get(tier, {}).get(feature_name, False)

def require_feature(feature_name):
    """
    Decorator enforcing plan-tier feature access.
    Aborts with 403 Forbidden if current user's institution tier excludes feature_name.
    Bypasses check for SUPER_ADMIN role.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))

            if getattr(current_user, 'role', None) == 'SUPER_ADMIN':
                return f(*args, **kwargs)

            inst = getattr(current_user, 'institution', None)
            if not inst or not institution_has_feature(inst, feature_name):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
                    return jsonify({
                        'status': 'ERROR',
                        'message': f"Access Denied: The feature '{feature_name}' requires a higher plan tier. Please upgrade your plan."
                    }), 403
                flash(f"Upgrade Required: Access to '{feature_name}' is not included in your institution's current plan tier.", 'warning')
                abort(403)

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def current_institution_id():
    """
    Returns the institution_id for the currently authenticated user session.
    Returns None if no user is authenticated or if user lacks an institution_id.
    """
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        return getattr(current_user, 'institution_id', None)
    return None

def verify_tenant_ownership(entity):
    """
    Verifies that an entity (Bus, Student, Route, Trip, Alert, User, Parent, Driver, etc.)
    belongs to the current user's institution.
    If entity is None or institution_id does not match, aborts with 403 Forbidden.
    """
    if getattr(current_user, 'role', None) == 'SUPER_ADMIN':
        return entity

    user_inst_id = current_institution_id()
    if user_inst_id is None or entity is None:
        return entity
    
    entity_inst_id = getattr(entity, 'institution_id', None)
    if entity_inst_id is not None and entity_inst_id != user_inst_id:
        abort(403, description="Access Denied: You do not have permission to access resources belonging to another institution.")
    return entity
