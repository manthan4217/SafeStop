import os
import sys

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Environment Configuration
    ENV = os.environ.get('FLASK_ENV', os.environ.get('APP_ENV', 'development')).lower()
    
    # Security Configuration
    if ENV == 'production':
        _secret = os.environ.get('SECRET_KEY')
        if not _secret:
            raise ValueError("CRITICAL SECURITY ERROR: 'SECRET_KEY' environment variable MUST be explicitly configured in production mode!")
        SECRET_KEY = _secret

        _csrf_secret = os.environ.get('WTF_CSRF_SECRET_KEY')
        if not _csrf_secret:
            raise ValueError("CRITICAL SECURITY ERROR: 'WTF_CSRF_SECRET_KEY' environment variable MUST be explicitly configured in production mode!")
        WTF_CSRF_SECRET_KEY = _csrf_secret
    else:
        SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-insecure-secret-key-do-not-use-in-production-2026'
        WTF_CSRF_SECRET_KEY = os.environ.get('WTF_CSRF_SECRET_KEY') or 'dev-insecure-csrf-key-do-not-use-in-production-2026'

    WTF_CSRF_ENABLED = True
    
    # Database Configuration
    _is_testing = ENV == 'testing' or 'pytest' in sys.modules or 'pytest' in sys.argv[0]
    _db_url = os.environ.get('DATABASE_URL')
    if _db_url and _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = _db_url or ('sqlite:///:memory:' if _is_testing else f"sqlite:///{os.path.join(BASE_DIR, 'saferide.db')}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Settings & Security Constraints
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload size
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    ALLOWED_DOCUMENT_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    STUDENT_PHOTOS = os.path.join(UPLOAD_FOLDER, 'students')
    DRIVER_DOCS = os.path.join(UPLOAD_FOLDER, 'drivers')
    ATTENDANCE_SNAPSHOTS = os.path.join(UPLOAD_FOLDER, 'attendance')
    
    # Safety Thresholds
    ROUTE_DEVIATION_THRESHOLD_METERS = float(os.environ.get('ROUTE_DEVIATION_THRESHOLD', 500.0))
    DELAY_THRESHOLD_MINUTES = int(os.environ.get('DELAY_THRESHOLD_MINUTES', 10))
    SAFE_DROP_ESCALATION_MINUTES = int(os.environ.get('SAFE_DROP_ESCALATION_MINUTES', 15))
    ABSENCE_CUTOFF_HOUR = int(os.environ.get('ABSENCE_CUTOFF_HOUR', 7))
    ABSENCE_CUTOFF_MINUTE = int(os.environ.get('ABSENCE_CUTOFF_MINUTE', 30))
    
    # AI Feature Matching Thresholds
    FACE_MATCH_SIMILARITY_THRESHOLD = 0.55  # Synchronized cosine distance threshold
    FACE_MIN_BOUNDING_BOX_SIZE = 60  # Minimum width/height in pixels for valid face region

    # Outbound Notification Provider Settings
    NOTIFICATION_PROVIDER = os.environ.get('NOTIFICATION_PROVIDER', 'console')  # 'console' or 'twilio'
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER') or os.environ.get('TWILIO_PHONE_NUMBER')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER') or TWILIO_FROM_NUMBER
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')

    # Categories default enabled for outbound SMS/WhatsApp dispatch
    OUTBOUND_SMS_CATEGORIES = {'BOARDING', 'ARRIVAL', 'SAFE_DROP', 'EMERGENCY', 'WRONG_BUS', 'NO_SHOW', 'UNSCANNED_DROP'}

    # Stripe Billing Configuration
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_mock_secret_key_2026')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', 'pk_test_mock_publishable_key_2026')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_mock_webhook_secret_2026')
    STRIPE_PRICE_ID_STARTER = os.environ.get('STRIPE_PRICE_ID_STARTER', 'price_starter_tier_2026')
    STRIPE_PRICE_ID_PROFESSIONAL = os.environ.get('STRIPE_PRICE_ID_PROFESSIONAL', 'price_professional_tier_2026')
    STRIPE_PRICE_ID_ENTERPRISE = os.environ.get('STRIPE_PRICE_ID_ENTERPRISE', 'price_enterprise_tier_2026')

