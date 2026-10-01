import json
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import current_user
from app.models import db, Institution, Student, Bus, Driver, User, Route, Alert, AuditLog
from app import role_required
from manage_db import create_institution_and_admin

superadmin_bp = Blueprint('superadmin', __name__)

@superadmin_bp.route('/institutions', methods=['GET'])
@role_required('SUPER_ADMIN')
def institutions_list():
    """List all institutions on the platform with fleet/student stats and tier status."""
    institutions = Institution.query.all()
    stats = []

    for inst in institutions:
        student_count = Student.query.filter_by(institution_id=inst.id).count()
        bus_count = Bus.query.filter_by(institution_id=inst.id).count()
        driver_count = Driver.query.filter_by(institution_id=inst.id).count()
        admin_user = User.query.filter_by(institution_id=inst.id, role='ADMIN').first()
        
        stats.append({
            'institution': inst,
            'student_count': student_count,
            'bus_count': bus_count,
            'driver_count': driver_count,
            'admin_user': admin_user
        })

    return render_template('superadmin/institutions.html', stats=stats)


@superadmin_bp.route('/institutions/new', methods=['POST'])
@role_required('SUPER_ADMIN')
def create_institution():
    """Self-service onboarding: creates new Institution and first ADMIN user in a single step."""
    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip()
    plan_tier = request.form.get('plan_tier', 'STARTER').strip()
    admin_email = request.form.get('admin_email', '').strip()
    admin_password = request.form.get('admin_password', '').strip()
    admin_name = request.form.get('admin_name', '').strip()
    admin_phone = request.form.get('admin_phone', '').strip()

    if not name or not slug or not admin_email or not admin_password or not admin_name:
        flash('All required fields (Name, Slug, Admin Email, Password, Admin Name) must be filled.', 'danger')
        return redirect(url_for('superadmin.institutions_list'))

    try:
        inst, admin_user = create_institution_and_admin(
            name=name,
            slug=slug,
            admin_email=admin_email,
            admin_password=admin_password,
            admin_name=admin_name,
            admin_phone=admin_phone,
            plan_tier=plan_tier
        )
        flash(f"Institution '{inst.name}' and primary admin '{admin_user.email}' onboarded successfully!", 'success')
    except ValueError as e:
        flash(str(e), 'danger')

    return redirect(url_for('superadmin.institutions_list'))


@superadmin_bp.route('/institutions/<int:inst_id>/deactivate', methods=['POST'])
@role_required('SUPER_ADMIN')
def deactivate_institution(inst_id):
    """Soft-deactivates an institution and blocks access for its scoped users."""
    inst = db.session.get(Institution, inst_id)
    if not inst:
        flash('Institution not found.', 'danger')
        return redirect(url_for('superadmin.institutions_list'))

    # Toggle active status
    inst.is_active = not inst.is_active
    db.session.commit()

    status_str = "activated" if inst.is_active else "deactivated"
    flash(f"Institution '{inst.name}' has been {status_str}.", 'warning' if not inst.is_active else 'success')
    return redirect(url_for('superadmin.institutions_list'))


@superadmin_bp.route('/institutions/<int:inst_id>/export', methods=['GET'])
@role_required('SUPER_ADMIN')
def export_institution(inst_id):
    """
    Exports full tenant data (metadata, users, students, buses, routes, alerts) as a JSON download.
    """
    inst = db.session.get(Institution, inst_id)
    if not inst:
        flash('Institution not found.', 'danger')
        return redirect(url_for('superadmin.institutions_list'))

    users = User.query.filter_by(institution_id=inst.id).all()
    students = Student.query.filter_by(institution_id=inst.id).all()
    buses = Bus.query.filter_by(institution_id=inst.id).all()
    routes = Route.query.filter_by(institution_id=inst.id).all()
    alerts = Alert.query.filter_by(institution_id=inst.id).all()

    export_payload = {
        'export_metadata': {
            'generated_at': datetime.utcnow().isoformat(),
            'platform': 'SafeStop Multi-Tenant Platform'
        },
        'institution': inst.to_dict(),
        'users': [{'id': u.id, 'email': u.email, 'full_name': u.full_name, 'role': u.role, 'phone': u.phone} for u in users],
        'students': [s.to_dict() for s in students],
        'buses': [{'id': b.id, 'bus_code': b.bus_code, 'registration_number': b.registration_number, 'capacity': b.capacity, 'status': b.status} for b in buses],
        'routes': [{'id': r.id, 'name': r.name, 'description': r.description} for r in routes],
        'alerts': [{'id': a.id, 'alert_type': a.alert_type, 'severity': a.severity, 'description': a.description, 'is_resolved': a.is_resolved} for a in alerts]
    }

    today_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"tenant_export_{inst.slug}_{today_str}.json"

    return Response(
        json.dumps(export_payload, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@superadmin_bp.route('/institutions/<int:inst_id>/offboard', methods=['POST'])
@role_required('SUPER_ADMIN')
def offboard_institution(inst_id):
    """
    Fully offboards a tenant: deactivates institution, cancels subscription status, and creates an audit entry.
    """
    inst = db.session.get(Institution, inst_id)
    if not inst:
        flash('Institution not found.', 'danger')
        return redirect(url_for('superadmin.institutions_list'))

    inst.is_active = False
    inst.subscription_status = 'CANCELED'

    audit = AuditLog(
        institution_id=inst.id,
        user_id=getattr(current_user, 'id', None),
        action='TENANT_OFFBOARDED',
        details=f"Institution '{inst.name}' (slug: {inst.slug}) was offboarded by SuperAdmin."
    )
    db.session.add(audit)
    db.session.commit()

    flash(f"Institution '{inst.name}' has been offboarded and subscription canceled.", 'warning')
    return redirect(url_for('superadmin.institutions_list'))

