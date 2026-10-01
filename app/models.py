from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy  # type: ignore # pyright: ignore[reportMissingImports]
from flask_login import UserMixin  # type: ignore # pyright: ignore[reportMissingImports]
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class BaseModel(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class Institution(BaseModel):
    __tablename__ = 'institutions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    contact_email = db.Column(db.String(120), nullable=True)
    plan_tier = db.Column(db.String(20), default='STARTER', nullable=False)  # STARTER, PROFESSIONAL, ENTERPRISE
    stripe_customer_id = db.Column(db.String(100), nullable=True, index=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True, index=True)
    subscription_status = db.Column(db.String(20), default='ACTIVE', nullable=False)  # ACTIVE, PAST_DUE, CANCELED, TRIALING
    invite_code = db.Column(db.String(30), unique=True, nullable=True, index=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='institution', lazy='dynamic')
    buses = db.relationship('Bus', backref='institution', lazy='dynamic')
    routes = db.relationship('Route', backref='institution', lazy='dynamic')
    students = db.relationship('Student', backref='institution', lazy='dynamic')
    trips = db.relationship('Trip', backref='institution', lazy='dynamic')
    alerts = db.relationship('Alert', backref='institution', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='institution', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'contact_email': self.contact_email,
            'plan_tier': self.plan_tier,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class User(UserMixin, BaseModel):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=True, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='PARENT', index=True)  # SUPER_ADMIN, ADMIN, DRIVER, PARENT
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    phone_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def has_valid_phone(self):
        """Validates if user's phone number is present and formatted appropriately for SMS delivery."""
        if not self.phone:
            return False
        digits = [c for c in self.phone if c.isdigit()]
        return len(digits) >= 10

    # Relationships
    parent_profile = db.relationship('Parent', backref='user', uselist=False, cascade='all, delete-orphan')
    driver_profile = db.relationship('Driver', backref='user', uselist=False, cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'full_name': self.full_name,
            'phone': self.phone,
            'is_active': self.is_active
        }


class Parent(BaseModel):
    __tablename__ = 'parents'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    address = db.Column(db.Text, nullable=True)
    emergency_contact = db.Column(db.String(20), nullable=True)
    relationship = db.Column(db.String(50), default='Parent')
    
    proximity_radius_meters = db.Column(db.Integer, default=500)
    
    students = db.relationship('Student', backref='parent', lazy='dynamic')
    safe_drops = db.relationship('SafeDropConfirmation', backref='parent', lazy='dynamic')
    absence_requests = db.relationship('StudentAbsenceRequest', backref='parent', lazy='dynamic')
    proximity_logs = db.relationship('StopProximityLog', backref='parent', lazy='dynamic')


class Student(BaseModel):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    full_name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    grade_section = db.Column(db.String(30), nullable=True)
    gender = db.Column(db.String(10), nullable=True)
    date_of_birth = db.Column(db.String(20), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'), nullable=True, index=True)
    invite_code = db.Column(db.String(30), unique=True, nullable=True, index=True)
    invite_used = db.Column(db.Boolean, default=False, nullable=False)
    
    assigned_bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True, index=True)
    assigned_route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=True, index=True)
    pickup_stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'), nullable=True)
    drop_stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'), nullable=True)
    
    photo_filename = db.Column(db.String(255), default='default_student.png')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def generate_invite_code(self):
        import secrets
        code = f"STU-INV-{secrets.token_hex(4).upper()}"
        self.invite_code = code
        self.invite_used = False
        return code

    # Relationships
    pickup_stop = db.relationship('Stop', foreign_keys=[pickup_stop_id])
    drop_stop = db.relationship('Stop', foreign_keys=[drop_stop_id])
    attendances = db.relationship('Attendance', backref='student', lazy='dynamic')
    alerts = db.relationship('Alert', backref='student', lazy='dynamic')
    face_profile = db.relationship('FaceProfile', backref='student', uselist=False, cascade='all, delete-orphan')
    safe_drops = db.relationship('SafeDropConfirmation', backref='student', lazy='dynamic')
    temp_reassignments = db.relationship('TemporaryBusReassignment', backref='student', lazy='dynamic')
    absence_requests = db.relationship('StudentAbsenceRequest', backref='student', lazy='dynamic')
    escorts = db.relationship('AuthorizedEscort', backref='student', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'roll_number': self.roll_number,
            'grade_section': self.grade_section,
            'assigned_bus': self.assigned_bus.bus_code if self.assigned_bus else 'Unassigned',
            'assigned_bus_id': self.assigned_bus_id,
            'assigned_route': self.assigned_route.name if self.assigned_route else 'Unassigned',
            'pickup_stop': self.pickup_stop.stop_name if self.pickup_stop else 'None',
            'drop_stop': self.drop_stop.stop_name if self.drop_stop else 'None',
            'photo_url': f'/static/uploads/students/{self.photo_filename}' if self.photo_filename else '/static/images/avatar.png'
        }


class Driver(BaseModel):
    __tablename__ = 'drivers'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=True)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=True)
    profile_photo = db.Column(db.String(255), default='default_driver.png')
    license_number = db.Column(db.String(50), nullable=False)
    license_expiry = db.Column(db.String(20), nullable=True)
    is_verified = db.Column(db.Boolean, default=True)
    
    assigned_bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True, index=True)
    assigned_route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=True, index=True)
    is_online = db.Column(db.Boolean, default=False, nullable=False)
    current_lat = db.Column(db.Float, nullable=True)
    current_lng = db.Column(db.Float, nullable=True)
    last_online_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    assigned_bus = db.relationship('Bus', foreign_keys=[assigned_bus_id])
    assigned_route = db.relationship('Route', foreign_keys=[assigned_route_id])
    documents = db.relationship('DriverDocument', backref='driver', lazy='dynamic', cascade='all, delete-orphan')
    trainings = db.relationship('DriverTraining', backref='driver', lazy='dynamic', cascade='all, delete-orphan')
    trips = db.relationship('Trip', backref='driver', lazy='dynamic')
    telemetry_logs = db.relationship('DriverSafetyTelemetry', backref='driver', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'full_name': self.full_name,
            'phone': self.phone,
            'license_number': self.license_number,
            'is_online': self.is_online,
            'current_lat': self.current_lat,
            'current_lng': self.current_lng,
            'last_online_at': self.last_online_at.isoformat() if self.last_online_at else None,
            'assigned_bus': self.assigned_bus.bus_code if self.assigned_bus else None
        }


class DriverDocument(BaseModel):
    __tablename__ = 'driver_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False, index=True)
    doc_type = db.Column(db.String(50), nullable=False)  # License, ID Proof, Background Verification, Medical
    doc_name = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='VERIFIED')  # PENDING, VERIFIED, EXPIRED
    expiry_date = db.Column(db.String(20), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class DriverTraining(BaseModel):
    __tablename__ = 'driver_trainings'
    
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False, index=True)
    training_name = db.Column(db.String(100), nullable=False)  # Safety, First-Aid, Child-Safety, Emergency Response
    training_date = db.Column(db.String(20), nullable=False)
    certificate_file = db.Column(db.String(255), nullable=True)
    expiry_date = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='COMPLETED')  # COMPLETED, PENDING, EXPIRED


class Bus(BaseModel):
    __tablename__ = 'buses'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    registration_number = db.Column(db.String(30), unique=True, nullable=False, index=True)
    bus_code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # BUS-05, BUS-08
    capacity = db.Column(db.Integer, default=40)
    status = db.Column(db.String(20), default='INACTIVE')  # ACTIVE, INACTIVE, MAINTENANCE
    
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=True, index=True)
    
    current_lat = db.Column(db.Float, nullable=True)
    current_lng = db.Column(db.Float, nullable=True)
    last_location_update = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    driver = db.relationship('Driver', foreign_keys=[driver_id])
    assigned_students = db.relationship('Student', backref='assigned_bus', foreign_keys=[Student.assigned_bus_id], lazy='dynamic')
    trips = db.relationship('Trip', backref='bus', lazy='dynamic')
    alerts = db.relationship('Alert', backref='bus', lazy='dynamic')
    gps_logs = db.relationship('GpsLocation', backref='bus', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'bus_code': self.bus_code,
            'registration_number': self.registration_number,
            'capacity': self.capacity,
            'status': self.status,
            'current_lat': self.current_lat,
            'current_lng': self.current_lng,
            'last_location_update': self.last_location_update.isoformat() if self.last_location_update else None
        }


class Route(BaseModel):
    __tablename__ = 'routes'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    name = db.Column(db.String(100), nullable=False)  # Route A - North Campus
    description = db.Column(db.Text, nullable=True)
    distance_km = db.Column(db.Float, default=15.0)
    estimated_duration_mins = db.Column(db.Integer, default=45)
    status = db.Column(db.String(20), default='ACTIVE')
    
    stops = db.relationship('Stop', backref='route', order_by='Stop.sequence_order', lazy='dynamic', cascade='all, delete-orphan')
    buses = db.relationship('Bus', backref='route', lazy='dynamic')
    students = db.relationship('Student', backref='assigned_route', foreign_keys=[Student.assigned_route_id], lazy='dynamic')


class Stop(BaseModel):
    __tablename__ = 'stops'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False, index=True)
    stop_name = db.Column(db.String(100), nullable=False)
    sequence_order = db.Column(db.Integer, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    scheduled_pickup_time = db.Column(db.String(10), nullable=True)  # 07:30 AM
    scheduled_drop_time = db.Column(db.String(10), nullable=True)    # 03:45 PM


class Trip(BaseModel):
    __tablename__ = 'trips'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False, index=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False, index=True)
    
    trip_type = db.Column(db.String(20), nullable=False)  # MORNING_PICKUP, EVENING_DROP
    status = db.Column(db.String(20), default='PLANNED', index=True)  # PLANNED, IN_PROGRESS, COMPLETED, CANCELLED
    
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    
    current_lat = db.Column(db.Float, nullable=True)
    current_lng = db.Column(db.Float, nullable=True)
    current_stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'), nullable=True)
    delay_minutes = db.Column(db.Integer, default=0)
    
    attendances = db.relationship('Attendance', backref='trip', lazy='dynamic')
    gps_locations = db.relationship('GpsLocation', backref='trip', lazy='dynamic')
    alerts = db.relationship('Alert', backref='trip', lazy='dynamic')
    safe_drops = db.relationship('SafeDropConfirmation', backref='trip', lazy='dynamic')


class Attendance(BaseModel):
    __tablename__ = 'attendances'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'trip_id', name='uq_student_trip_attendance'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    
    verification_time = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    verification_status = db.Column(db.String(30), nullable=False, index=True)  # VERIFIED, WRONG_BUS, MANUAL_OVERRIDE, ABSENT
    scan_type = db.Column(db.String(20), default='BOARD', nullable=False)  # BOARD, DROP
    is_dropped_off = db.Column(db.Boolean, default=False, nullable=False)
    drop_verification_time = db.Column(db.DateTime, nullable=True)
    verified_by_driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=True)
    photo_snapshot = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)


class GpsLocation(BaseModel):
    __tablename__ = 'gps_locations'
    
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float, default=0.0)
    heading = db.Column(db.Float, default=0.0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Alert(BaseModel):
    __tablename__ = 'alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=True, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    
    alert_type = db.Column(db.String(40), nullable=False, index=True)  # WRONG_BUS, ROUTE_DEVIATION, BUS_DELAY, SOS_EMERGENCY, UNUSUAL_TIME, SAFE_DROP_PENDING, NO_SHOW, UNSCANNED_DROP
    risk_score = db.Column(db.Integer, default=0)
    severity = db.Column(db.String(20), default='WARNING')  # INFO, WARNING, CRITICAL
    description = db.Column(db.Text, nullable=False)
    is_resolved = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime, nullable=True)


class Notification(BaseModel):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(30), default='INFO')  # BOARDING, ARRIVAL, DELAY, WRONG_BUS, ROUTE_VIOLATION, SAFE_DROP, EMERGENCY, NO_SHOW, UNSCANNED_DROP
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    action_link = db.Column(db.String(255), nullable=True)


class EmergencyEvent(BaseModel):
    __tablename__ = 'emergency_events'
    
    id = db.Column(db.Integer, primary_key=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=True, index=True)
    triggered_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default='ACTIVE', index=True)  # ACTIVE, RESOLVED
    description = db.Column(db.Text, nullable=True)
    triggered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class SafeDropConfirmation(BaseModel):
    __tablename__ = 'safe_drop_confirmations'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'trip_id', 'stop_id', name='uq_safe_drop_confirmation'),
    )
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'), nullable=False, index=True)
    
    bus_arrival_time = db.Column(db.DateTime, default=datetime.utcnow)
    confirmation_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='PENDING', index=True)  # PENDING, CONFIRMED, ESCALATED


class FaceProfile(BaseModel):
    __tablename__ = 'face_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, unique=True, index=True)
    feature_vector_json = db.Column(db.Text, nullable=False, default='[]')
    image_path = db.Column(db.String(255), nullable=False, default='default_student.png')
    # Biometric Data Governance & Consent
    parental_consent_given = db.Column(db.Boolean, default=False, nullable=False, index=True)
    consent_given_at = db.Column(db.DateTime, nullable=True)
    consent_given_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_archived = db.Column(db.Boolean, default=False, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def grant_consent(self, user_id=None):
        self.parental_consent_given = True
        self.consent_given_at = datetime.utcnow()
        if user_id:
            self.consent_given_by_user_id = user_id
        self.is_archived = False

    def revoke_consent(self):
        self.parental_consent_given = False
        self.is_archived = True
        self.archived_at = datetime.utcnow()


    def get_vector(self):
        try:
            return json.loads(self.feature_vector_json)
        except Exception:
            return []

    def set_vector(self, vector_list):
        self.feature_vector_json = json.dumps(vector_list)


class TemporaryBusReassignment(BaseModel):
    __tablename__ = 'temporary_bus_reassignments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    original_bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    temporary_bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False)
    start_date = db.Column(db.String(20), nullable=False)
    end_date = db.Column(db.String(20), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)


class AuditLog(BaseModel):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey('institutions.id'), nullable=False, index=True, default=1)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    ip_address = db.Column(db.String(50), nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class StudentAbsenceRequest(BaseModel):
    __tablename__ = 'student_absence_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'), nullable=False, index=True)
    absence_date = db.Column(db.String(20), nullable=False, index=True)  # YYYY-MM-DD
    session_type = db.Column(db.String(30), default='FULL_DAY')  # FULL_DAY, MORNING_PICKUP, EVENING_DROP
    reason = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='SUBMITTED', index=True)  # SUBMITTED, ACKNOWLEDGED, CANCELLED
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class DriverSafetyTelemetry(BaseModel):
    __tablename__ = 'driver_safety_telemetries'

    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('drivers.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=True, index=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=True, index=True)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    fatigue_score = db.Column(db.Float, default=0.0)  # 0.0 (Normal) to 1.0 (Critical Fatigue)
    fatigue_level = db.Column(db.String(30), default='NORMAL', index=True)  # NORMAL, MILD_DROWSINESS, CRITICAL_DROWSINESS
    eye_closure_sec = db.Column(db.Float, default=0.0)
    yawn_count = db.Column(db.Integer, default=0)
    distraction_event = db.Column(db.String(40), default='NONE')  # NONE, EYES_OFF_ROAD, PHONE_USAGE
    speed_kph = db.Column(db.Float, default=35.0)
    overspeed_warning = db.Column(db.Boolean, default=False)
    harsh_braking_warning = db.Column(db.Boolean, default=False)
    safety_score = db.Column(db.Integer, default=100)  # 0 to 100


class StopProximityLog(BaseModel):
    __tablename__ = 'stop_proximity_logs'
    __table_args__ = (
        db.UniqueConstraint('trip_id', 'student_id', 'stop_id', name='uq_trip_student_stop_proximity'),
    )

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey('trips.id'), nullable=False, index=True)
    bus_id = db.Column(db.Integer, db.ForeignKey('buses.id'), nullable=False, index=True)
    stop_id = db.Column(db.Integer, db.ForeignKey('stops.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'), nullable=False, index=True)

    distance_meters = db.Column(db.Float, nullable=False)
    estimated_eta_mins = db.Column(db.Integer, default=3)
    notified_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class AuthorizedEscort(BaseModel):
    __tablename__ = 'authorized_escorts'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id'), nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    relationship = db.Column(db.String(50), nullable=False, default='Relative')
    id_proof_number = db.Column(db.String(50), nullable=True)
    photo_path = db.Column(db.String(255), default='default_escort.png')
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)



