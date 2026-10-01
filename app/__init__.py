import os
from flask import Flask, redirect, url_for, flash, jsonify
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from functools import wraps
from config import Config
from app.models import db, User
from app.security import init_csrf_protection

login_manager = LoginManager()
migrate = Migrate()

def role_required(*roles):
    """Decorator to enforce role-based access control (RBAC)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if roles == ('SUPER_ADMIN',) and current_user.role != 'SUPER_ADMIN':
                from flask import abort
                abort(403)
            if current_user.role == 'SUPER_ADMIN':
                return f(*args, **kwargs)
            if current_user.institution and not current_user.institution.is_active:
                flash('Access denied: Your institution has been deactivated.', 'danger')
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('Access denied: You do not have permission to view this section.', 'danger')
                if current_user.role == 'ADMIN':
                    return redirect(url_for('admin.dashboard'))
                elif current_user.role == 'DRIVER':
                    return redirect(url_for('driver.dashboard'))
                elif current_user.role == 'PARENT':
                    return redirect(url_for('parent.dashboard'))
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def create_app(config_class=Config):
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(config_class)

    # Ensure upload directories exist
    os.makedirs(app.config['STUDENT_PHOTOS'], exist_ok=True)
    os.makedirs(app.config['DRIVER_DOCS'], exist_ok=True)
    os.makedirs(app.config['ATTENDANCE_SNAPSHOTS'], exist_ok=True)

    # Initialize extensions & security layers
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please login to access SafeRide AI.'
    login_manager.login_message_category = 'warning'

    init_csrf_protection(app)

    from app.limiter import limiter
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        if user and user.role != 'SUPER_ADMIN' and user.institution and not user.institution.is_active:
            return None
        return user

    # Security Response Headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response

    # Error Handlers
    @app.errorhandler(400)
    def bad_request_error(e):
        return jsonify({'status': 'ERROR', 'message': str(e.description or e)}), 400

    @app.errorhandler(403)
    def forbidden_error(e):
        return jsonify({'status': 'ERROR', 'message': 'Access Denied: Unauthorized resource access.'}), 403

    # Context processors for navbar alerts & counts & feature flags
    @app.context_processor
    def inject_global_data():
        if current_user.is_authenticated:
            from app.models import Notification
            from app.tenancy import institution_has_feature
            unread_count = current_user.notifications.filter_by(is_read=False).count() if hasattr(current_user, 'notifications') and current_user.notifications else 0
            user_notifs = current_user.notifications.order_by(Notification.id.desc()).limit(5).all() if hasattr(current_user, 'notifications') and current_user.notifications else []
            inst = getattr(current_user, 'institution', None)

            def has_feature(feat_name):
                if getattr(current_user, 'role', None) == 'SUPER_ADMIN':
                    return True
                return institution_has_feature(inst, feat_name)

            return {
                'unread_notifications_count': unread_count,
                'header_notifications': user_notifs,
                'has_feature': has_feature
            }
        return {
            'unread_notifications_count': 0,
            'header_notifications': [],
            'has_feature': lambda f: False
        }

    # Register Blueprints
    from app.auth.routes import auth_bp
    from app.parent.routes import parent_bp
    from app.driver.routes import driver_bp
    from app.admin.routes import admin_bp
    from app.superadmin.routes import superadmin_bp
    from app.billing.routes import billing_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(parent_bp, url_prefix='/parent')
    app.register_blueprint(driver_bp, url_prefix='/driver')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(superadmin_bp, url_prefix='/superadmin')
    app.register_blueprint(billing_bp, url_prefix='/billing')

    # Root redirect
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.role == 'SUPER_ADMIN':
                return redirect(url_for('superadmin.institutions_list'))
            elif current_user.role == 'ADMIN':
                return redirect(url_for('admin.dashboard'))
            elif current_user.role == 'DRIVER':
                return redirect(url_for('driver.dashboard'))
            elif current_user.role == 'PARENT':
                return redirect(url_for('parent.dashboard'))
        return redirect(url_for('auth.login'))

    # Initialize scheduler if not in testing mode and not in reloader parent process
    if not app.config.get('TESTING'):
        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            from app.scheduler import init_scheduler
            init_scheduler(app)

    return app

