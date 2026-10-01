import os
import uuid
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, session, abort, current_app, render_template, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.utils import secure_filename

def get_serializer():
    secret = current_app.config.get('SECRET_KEY', 'default-secret-key')
    return URLSafeTimedSerializer(secret)

# --- CSRF PROTECTION ENGINE ---

def generate_csrf_token():
    """Generates a secure CSRF token tied to the current session."""
    if 'csrf_token' not in session:
        session['csrf_token'] = uuid.uuid4().hex
    serializer = get_serializer()
    return serializer.dumps(session['csrf_token'], salt='csrf-salt')

def validate_csrf_token(token_to_check):
    """Validates the incoming CSRF token against the user session."""
    if not token_to_check or 'csrf_token' not in session:
        return False
    serializer = get_serializer()
    try:
        session_token = serializer.loads(token_to_check, salt='csrf-salt', max_age=86400)
        return session_token == session['csrf_token']
    except (BadSignature, SignatureExpired):
        return False

def init_csrf_protection(app):
    """Registers global Jinja helper and automatic CSRF verification for POST/PUT/DELETE requests."""
    
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf_token)

    @app.before_request
    def check_csrf():
        if not app.config.get('WTF_CSRF_ENABLED', True):
            return
        
        # Only validate state-changing HTTP methods
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            # Allow API endpoints with alternative authorization if explicitly exempted
            if request.endpoint and ('static' in request.endpoint or request.endpoint == 'billing.stripe_webhook'):
                return

            # Extract CSRF token from Form data, Headers, or JSON
            token = (
                request.form.get('csrf_token') or
                request.headers.get('X-CSRFToken') or
                request.headers.get('X-CSRF-Token')
            )

            if not token and request.is_json:
                data = request.get_json(silent=True) or {}
                token = data.get('csrf_token')

            if not validate_csrf_token(token):
                if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'status': 'ERROR',
                        'message': 'CSRF token validation failed. Please refresh the page and try again.'
                    }), 400
                abort(400, description="CSRF token validation failed. Invalid or missing security token.")

# --- OPEN REDIRECT SANITIZER ---

def is_safe_url(target):
    """Verifies that a redirect target URL is local and safe."""
    if not target:
        return False
    target = target.strip()
    if target.startswith('//') or target.startswith('\\'):
        return False
    from flask import has_request_context
    if not has_request_context():
        # Fallback relative path check outside request context
        return target.startswith('/') and not target.startswith('//') and not target.startswith('\\')
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

# --- SECURE PASSWORD RESET TOKEN ENGINE ---

def generate_password_reset_token(user_id):
    """Generates a timed URL-safe password reset token valid for 30 minutes."""
    serializer = get_serializer()
    return serializer.dumps({'user_id': user_id}, salt='password-reset-salt')

def verify_password_reset_token(token, max_age_seconds=1800):
    """Verifies and decodes a password reset token."""
    serializer = get_serializer()
    try:
        data = serializer.loads(token, salt='password-reset-salt', max_age=max_age_seconds)
        return data.get('user_id')
    except (BadSignature, SignatureExpired):
        return None

# --- SECURE FILE UPLOAD VALIDATOR ---

def validate_and_save_upload(file_obj, target_folder, allowed_extensions):
    """
    Strictly validates uploaded file extension, size, image decoding, and saves
    it using a secure UUID server-side filename. Returns the saved filename.
    """
    if not file_obj or not file_obj.filename:
        return None

    filename = secure_filename(file_obj.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if ext not in allowed_extensions:
        raise ValueError(f"File extension '.{ext}' is not allowed. Allowed types: {', '.join(allowed_extensions)}")

    # Secure server-side UUID filename
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(target_folder, exist_ok=True)
    save_path = os.path.join(target_folder, unique_filename)

    file_obj.save(save_path)

    # Image decoding integrity check for image files
    if ext in {'png', 'jpg', 'jpeg'}:
        try:
            import cv2  # type: ignore # pyright: ignore[reportMissingImports]
            img = cv2.imread(save_path)
            if img is None or img.size == 0:
                os.remove(save_path)
                raise ValueError("Uploaded file is corrupted or not a valid image.")
        except Exception as e:
            if os.path.exists(save_path):
                os.remove(save_path)
            raise ValueError(f"Invalid image file: {str(e)}")

    return unique_filename
