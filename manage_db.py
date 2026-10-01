import sys
import argparse
from app import create_app
from app.models import (
    db, Institution, User, Parent, Student, Driver, Bus, Route, Stop, Trip, Attendance, Alert, Notification
)
from app.seed import seed_database

def init_db(app):
    """Create all database tables cleanly without inserting mock seed data."""
    with app.app_context():
        db.create_all()
        print("[OK] Database schema initialized successfully.")

def reset_db(app):
    """Clear existing tables and re-create schema."""
    with app.app_context():
        print("[WARN] Dropping existing database tables...")
        db.drop_all()
        db.create_all()
        print("[OK] Database reset successfully.")

def seed_db():
    """Populate database with demonstration data."""
    print("[+] Seeding demonstration dataset...")
    seed_database()

def create_institution_and_admin(name, slug, admin_email, admin_password, admin_name, admin_phone="", plan_tier="STARTER"):
    """
    Shared domain function to onboard an institution and its first administrator account atomically.
    Raises ValueError on validation failure.
    """
    slug = slug.strip().lower()
    if Institution.query.filter_by(slug=slug).first():
        raise ValueError(f"Institution with slug '{slug}' already exists.")
    if User.query.filter_by(email=admin_email).first():
        raise ValueError(f"User with email '{admin_email}' already exists.")

    inst = Institution(name=name, slug=slug, plan_tier=plan_tier, contact_email=admin_email)
    db.session.add(inst)
    db.session.flush()

    admin_user = User(
        institution_id=inst.id,
        email=admin_email,
        role='ADMIN',
        full_name=admin_name,
        phone=admin_phone
    )
    admin_user.set_password(admin_password)
    db.session.add(admin_user)
    db.session.commit()
    return inst, admin_user


def create_admin(app, email, password, full_name, phone, institution_slug=None, institution_name=None):
    """Create a real system administrator account assigned to an institution."""
    with app.app_context():
        slug = institution_slug or (institution_name.lower().replace(' ', '-') if institution_name else 'default-school')
        name = institution_name or "Default School Institution"
        try:
            inst, admin_user = create_institution_and_admin(
                name=name,
                slug=slug,
                admin_email=email,
                admin_password=password,
                admin_name=full_name,
                admin_phone=phone
            )
            print(f"[OK] Administrator account '{email}' created successfully for institution '{inst.name}' (ID: {inst.id}, Slug: '{inst.slug}').")
            return True
        except ValueError as e:
            print(f"[X] Error: {e}")
            return False


def create_superadmin(app, email, password, full_name="Super Administrator"):
    """Create a global platform SuperAdmin account."""
    with app.app_context():
        existing = User.query.filter_by(email=email).first()
        if existing:
            print(f"[X] User with email '{email}' already exists.")
            return False

        superadmin = User(
            institution_id=None,
            email=email,
            role='SUPER_ADMIN',
            full_name=full_name
        )
        superadmin.set_password(password)
        db.session.add(superadmin)
        db.session.commit()
        print(f"[OK] SuperAdmin account '{email}' created successfully.")
        return True

def db_status(app):
    """Display current database counts and metadata."""
    with app.app_context():
        db.create_all()
        inst_count = Institution.query.count()
        users_count = User.query.count()
        parents_count = Parent.query.count()
        students_count = Student.query.count()
        drivers_count = Driver.query.count()
        buses_count = Bus.query.count()
        routes_count = Route.query.count()
        trips_count = Trip.query.count()

        print("\n==================================================")
        print(" SAFERIDE AI — DATABASE STATUS REPORT")
        print("==================================================")
        print(f" Database URI  : {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f" Institutions  : {inst_count}")
        print(f" Total Users    : {users_count}")
        print(f"  - Admins      : {User.query.filter_by(role='ADMIN').count()}")
        print(f"  - Parents     : {parents_count}")
        print(f"  - Drivers     : {drivers_count}")
        print(f" Total Students : {students_count}")
        print(f" Total Fleet    : {buses_count} Buses")
        print(f" Total Routes   : {routes_count}")
        print(f" Total Trips    : {trips_count}")
        print("==================================================\n")

def main():
    parser = argparse.ArgumentParser(description="SafeStop / SafeRide AI Database Management CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available database commands")

    subparsers.add_parser("init", help="Initialize clean database tables")
    subparsers.add_parser("reset", help="Drop and recreate database tables")
    subparsers.add_parser("seed", help="Seed demonstration data")
    subparsers.add_parser("status", help="Show database record status")

    admin_parser = subparsers.add_parser("create-admin", help="Create a system administrator account")
    admin_parser.add_argument("--email", required=True, help="Admin email address")
    admin_parser.add_argument("--password", required=True, help="Admin password")
    admin_parser.add_argument("--name", default="System Administrator", help="Admin full name")
    admin_parser.add_argument("--phone", default="", help="Admin phone number")
    admin_parser.add_argument("--institution-slug", help="Institution slug identifier (e.g. kbp-vashi)")
    admin_parser.add_argument("--institution-name", help="Institution full name")

    superadmin_parser = subparsers.add_parser("create-superadmin", help="Create a global platform SuperAdmin account")
    superadmin_parser.add_argument("--email", required=True, help="SuperAdmin email address")
    superadmin_parser.add_argument("--password", required=True, help="SuperAdmin password")
    superadmin_parser.add_argument("--name", default="Platform SuperAdmin", help="SuperAdmin full name")

    args = parser.parse_args()

    app = create_app()

    if args.command == "init":
        init_db(app)
    elif args.command == "reset":
        reset_db(app)
    elif args.command == "seed":
        seed_db()
    elif args.command == "status":
        db_status(app)
    elif args.command == "create-admin":
        create_admin(app, args.email, args.password, args.name, args.phone, args.institution_slug, args.institution_name)
    elif args.command == "create-superadmin":
        create_superadmin(app, args.email, args.password, args.name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
