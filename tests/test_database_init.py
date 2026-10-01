import pytest
from app import create_app
from app.models import (
    db, User, Parent, Student, Driver, Bus, Route, Stop, Trip, Attendance, Alert
)
from manage_db import init_db, create_admin, db_status
from sqlalchemy.exc import IntegrityError

@pytest.fixture
def clean_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_database_init_tables(clean_app):
    with clean_app.app_context():
        # Verify table initialization
        assert User.query.count() == 0
        assert Student.query.count() == 0
        assert Bus.query.count() == 0

def test_create_admin_cli(clean_app):
    with clean_app.app_context():
        res = create_admin(clean_app, 'real_admin@college.edu', 'SecurePass2026!', 'Principal Admin', '+91 99000 11111')
        assert res is True

        user = User.query.filter_by(email='real_admin@college.edu').first()
        assert user is not None
        assert user.role == 'ADMIN'
        assert user.check_password('SecurePass2026!') is True

        # Duplicate create_admin must fail gracefully
        res_dup = create_admin(clean_app, 'real_admin@college.edu', 'AnotherPass', 'Duplicate Admin', '')
        assert res_dup is False

def test_real_user_data_relations(clean_app):
    with clean_app.app_context():
        # 1. Create Parent User & Profile
        u_parent = User(email='real_parent@gmail.com', role='PARENT', full_name='Sunita Patil', phone='+91 98200 44556')
        u_parent.set_password('parentpass')
        db.session.add(u_parent)
        db.session.flush()

        parent = Parent(user_id=u_parent.id, address='Sector 15, Vashi, Navi Mumbai', emergency_contact='+91 98200 44556')
        db.session.add(parent)

        # 2. Create Driver User & Profile
        u_driver = User(email='real_driver@gmail.com', role='DRIVER', full_name='Ramesh K', phone='+91 98765 11111')
        u_driver.set_password('driverpass')
        db.session.add(u_driver)
        db.session.flush()

        driver = Driver(user_id=u_driver.id, full_name='Ramesh K', phone='+91 98765 11111', license_number='DL-MH43-2026')
        db.session.add(driver)

        # 3. Create Bus & Route
        route = Route(name='Route 1 - Vashi Express', distance_km=10.5)
        db.session.add(route)
        db.session.flush()

        bus = Bus(registration_number='MH-43-CS-1001', bus_code='BUS-101', driver_id=driver.id, route_id=route.id)
        db.session.add(bus)
        db.session.flush()

        # 4. Create Student assigned to Parent and Bus
        student = Student(
            full_name='Aarav Patil',
            roll_number='KBP-2026-CS999',
            grade_section='B.Sc CS',
            parent_id=parent.id,
            assigned_bus_id=bus.id,
            assigned_route_id=route.id
        )
        db.session.add(student)
        db.session.commit()

        # Verify Query Retrievals
        saved_student = Student.query.filter_by(roll_number='KBP-2026-CS999').first()
        assert saved_student is not None
        assert saved_student.parent.user.email == 'real_parent@gmail.com'
        assert saved_student.assigned_bus.bus_code == 'BUS-101'
        assert saved_student.assigned_bus.driver.full_name == 'Ramesh K'

def test_unique_constraints(clean_app):
    with clean_app.app_context():
        u1 = User(email='duplicate@test.com', role='PARENT', full_name='User One')
        u1.set_password('pass')
        db.session.add(u1)
        db.session.commit()

        with pytest.raises(IntegrityError):
            u2 = User(email='duplicate@test.com', role='DRIVER', full_name='User Two')
            u2.set_password('pass')
            db.session.add(u2)
            db.session.commit()
