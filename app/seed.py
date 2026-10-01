import json
from datetime import datetime, timedelta
import numpy as np
from app import create_app
from app.models import (
    db, Institution, User, Parent, Student, Driver, DriverDocument, DriverTraining,
    Bus, Route, Stop, Trip, Attendance, GpsLocation, Alert, Notification,
    EmergencyEvent, SafeDropConfirmation, FaceProfile, AuditLog
)

def seed_database():
    app = create_app()
    with app.app_context():
        # Do NOT use db.drop_all() -> db.create_all() here.
        # Render/Alembic migrations will handle schema creation.
        print("Bypassing manual table drop/create for production environment.")

        # Check if already seeded to prevent duplication
        if Institution.query.count() > 0:
            print("Database already seeded. Skipping.")
            return

        print("Seeding Multi-Tenant Institutions...")
        inst_kbp = Institution(
            name='Karmaveer Bhaurao Patil (KBP) College, Vashi',
            slug='kbp-vashi',
            contact_email='contact@kbp-vashi.edu',
            plan_tier='ENTERPRISE',
            invite_code='KBP2026',
            is_active=True
        )
        inst_stx = Institution(
            name="St. Xavier's International School",
            slug='st-xaviers',
            contact_email='contact@stxaviers.edu',
            plan_tier='STARTER',
            invite_code='STX2026',
            is_active=True
        )
        db.session.add_all([inst_kbp, inst_stx])
        db.session.flush()

        print("Seeding Institutional Administration & Staff for KBP College Vashi...")
        # 1. School Admin User for KBP College Vashi
        admin_user = User(
            institution_id=inst_kbp.id,
            email='admin@saferide.ai',
            role='ADMIN',
            full_name='Dr. Rajesh Sharma (Director of Transport, KBP College)',
            phone='+91 98200 11223'
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)

        # 2. Driver Users
        driver1_user = User(institution_id=inst_kbp.id, email='driver1@saferide.ai', role='DRIVER', full_name='Ramesh Kumar', phone='+91 98765 43210')
        driver1_user.set_password('driver123')

        driver2_user = User(institution_id=inst_kbp.id, email='driver2@saferide.ai', role='DRIVER', full_name='Suresh Yadav', phone='+91 98765 43211')
        driver2_user.set_password('driver123')

        driver3_user = User(institution_id=inst_kbp.id, email='driver3@saferide.ai', role='DRIVER', full_name='Mahesh Patil', phone='+91 98765 43212')
        driver3_user.set_password('driver123')

        db.session.add_all([driver1_user, driver2_user, driver3_user])

        print("Seeding 15 Real Student Parent Users (Navi Mumbai Residential Contacts)...")
        parent_configs = [
            ('parent1@saferide.ai', 'Dr. Ashok Patil', '+91 98201 55443', 'Flat 402, Shivam Apartments, Sector 17, Vashi, Navi Mumbai 400703', 'Father'),
            ('parent2@saferide.ai', 'Priya Sharma', '+91 99887 76656', 'B-201, Palm Beach Residency, Sector 19A, Nerul, Navi Mumbai 400706', 'Mother'),
            ('parent3@saferide.ai', 'Amit Verma', '+91 99887 76657', 'House No. 45, Gulmohar Society, Sector 11, Kopar Khairane, Navi Mumbai 400709', 'Father'),
            ('parent4@saferide.ai', 'Kavita Gupta', '+91 99887 76658', 'Flat 104, Sai Heritage, Sector 4, CBD Belapur, Navi Mumbai 400614', 'Mother'),
            ('parent5@saferide.ai', 'Suresh Deshmukh', '+91 98200 12301', 'Flat 301, Sagar Darshan, Sector 21, Nerul, Navi Mumbai 400706', 'Father'),
            ('parent6@saferide.ai', 'Rajesh Kulkarni', '+91 98200 12302', 'B-504, Sunshine Towers, Sector 1, Juinagar, Navi Mumbai 400705', 'Father'),
            ('parent7@saferide.ai', 'Milind Shinde', '+91 98200 12303', 'Flat 102, Gokul Heights, Sector 17, Vashi, Navi Mumbai 400703', 'Father'),
            ('parent8@saferide.ai', 'Sunita More', '+91 98200 12304', 'House 88, Sector 9, Vashi Market, Navi Mumbai 400703', 'Mother'),
            ('parent9@saferide.ai', 'Nitin Joshi', '+91 98200 12305', 'Flat 202, Moraj Residency, Sector 14, Kopar Khairane, Navi Mumbai 400709', 'Father'),
            ('parent10@saferide.ai', 'Dipak Bhosale', '+91 98200 12306', 'Flat 601, Sector 3, CBD Belapur, Navi Mumbai 400614', 'Father'),
            ('parent11@saferide.ai', 'Vilas Pawar', '+91 98200 12307', 'Plot 44, Sector 22, Nerul West, Navi Mumbai 400706', 'Father'),
            ('parent12@saferide.ai', 'Ramesh Nambiar', '+91 98200 12308', 'Flat 503, Juinagar Heights, Sector 11, Juinagar, Navi Mumbai 400705', 'Father'),
            ('parent13@saferide.ai', 'Arvind Chavan', '+91 98200 12309', 'Flat 101, Vashi Plaza Complex, Sector 17, Vashi, Navi Mumbai 400703', 'Father'),
            ('parent14@saferide.ai', 'Sanjay Thorat', '+91 98200 12310', 'B-102, Vegetable Market Road, Sector 9, Vashi, Navi Mumbai 400703', 'Father'),
            ('parent15@saferide.ai', 'Prakash Kadam', '+91 98200 12311', 'Flat 304, Green Park Society, Sector 15, Kopar Khairane, Navi Mumbai 400709', 'Father'),
        ]

        parent_models = []
        parent_users = []
        for email, name, phone, address, rel in parent_configs:
            u = User(institution_id=inst_kbp.id, email=email, role='PARENT', full_name=name, phone=phone)
            u.set_password('parent123')
            db.session.add(u)
            parent_users.append((u, address, phone, rel))

        db.session.flush()

        for u, address, phone, rel in parent_users:
            p = Parent(institution_id=inst_kbp.id, user_id=u.id, address=address, emergency_contact=phone, relationship=rel)
            db.session.add(p)
            parent_models.append(p)

        db.session.flush()

        print("Seeding Routes & Real Navi Mumbai Stops for KBP College Vashi...")
        # Route A: Vashi - Kopar Khairane Express
        r_a = Route(
            institution_id=inst_kbp.id,
            name='Route A — Vashi - Kopar Khairane Express',
            description='Serves Sector 17 Vashi Plaza, Sector 9 Vashi Market, Kopar Khairane Circle, and KBP College Main Gate',
            distance_km=12.5,
            estimated_duration_mins=35
        )
        # Route B: Belapur - Nerul Coastal Loop
        r_b = Route(
            institution_id=inst_kbp.id,
            name='Route B — Belapur - Nerul Coastal Loop',
            description='Serves CBD Belapur Station, Nerul LP Junction, Juinagar Station West, and KBP College Main Gate',
            distance_km=16.8,
            estimated_duration_mins=45
        )
        db.session.add_all([r_a, r_b])
        db.session.flush()

        # Real GPS Coordinates for KBP College Vashi Campus: 19.0772 N, 72.9984 E
        # Stops for Route A
        st_a1 = Stop(institution_id=inst_kbp.id, route_id=r_a.id, stop_name='Stop 1: Sector 17 Vashi Plaza (Home Pickup/Drop)', sequence_order=1, latitude=19.0645, longitude=72.9976, scheduled_pickup_time='07:15 AM', scheduled_drop_time='03:30 PM')
        st_a2 = Stop(institution_id=inst_kbp.id, route_id=r_a.id, stop_name='Stop 2: Sector 9 Vashi Market (Home Pickup/Drop)', sequence_order=2, latitude=19.0720, longitude=72.9930, scheduled_pickup_time='07:30 AM', scheduled_drop_time='03:45 PM')
        st_a3 = Stop(institution_id=inst_kbp.id, route_id=r_a.id, stop_name='Stop 3: Kopar Khairane Station Circle (Home Pickup/Drop)', sequence_order=3, latitude=19.0965, longitude=73.0078, scheduled_pickup_time='07:45 AM', scheduled_drop_time='04:00 PM')
        st_a4 = Stop(institution_id=inst_kbp.id, route_id=r_a.id, stop_name='KBP College Main Campus Gate, Sector 15-A Vashi (College Destination)', sequence_order=4, latitude=19.0772, longitude=72.9984, scheduled_pickup_time='08:15 AM', scheduled_drop_time='03:15 PM')

        # Stops for Route B
        st_b1 = Stop(institution_id=inst_kbp.id, route_id=r_b.id, stop_name='Stop 1: CBD Belapur Station Complex (Home Pickup/Drop)', sequence_order=1, latitude=19.0180, longitude=73.0400, scheduled_pickup_time='07:10 AM', scheduled_drop_time='03:35 PM')
        st_b2 = Stop(institution_id=inst_kbp.id, route_id=r_b.id, stop_name='Stop 2: Nerul LP Junction Sector 21 (Home Pickup/Drop)', sequence_order=2, latitude=19.0335, longitude=73.0185, scheduled_pickup_time='07:25 AM', scheduled_drop_time='03:50 PM')
        st_b3 = Stop(institution_id=inst_kbp.id, route_id=r_b.id, stop_name='Stop 3: Juinagar Station West (Home Pickup/Drop)', sequence_order=3, latitude=19.0550, longitude=73.0130, scheduled_pickup_time='07:40 AM', scheduled_drop_time='04:05 PM')
        st_b4 = Stop(institution_id=inst_kbp.id, route_id=r_b.id, stop_name='KBP College Main Campus Gate, Sector 15-A Vashi (College Destination)', sequence_order=4, latitude=19.0772, longitude=72.9984, scheduled_pickup_time='08:20 AM', scheduled_drop_time='03:15 PM')

        db.session.add_all([st_a1, st_a2, st_a3, st_a4, st_b1, st_b2, st_b3, st_b4])
        db.session.flush()

        print("Seeding Drivers & Official Vehicle Fleet...")
        d1 = Driver(
            user_id=driver1_user.id,
            full_name='Ramesh Kumar',
            age=42,
            phone='+91 98765 43210',
            address='Flat 12, Mhatre Building, Turbhe Gaon, Navi Mumbai 400705',
            license_number='DL-MH43-2015-09881',
            license_expiry='2029-12-31',
            is_verified=True,
            is_online=True,
            current_lat=19.0760,
            current_lng=72.8777,
            assigned_route_id=r_a.id
        )
        d2 = Driver(
            user_id=driver2_user.id,
            full_name='Suresh Yadav',
            age=38,
            phone='+91 98765 43211',
            address='House 34, Sector 1, Sanpada, Navi Mumbai 400705',
            license_number='DL-MH43-2018-77123',
            license_expiry='2030-05-15',
            is_verified=True,
            is_online=False,
            assigned_route_id=r_b.id
        )
        d3 = Driver(
            user_id=driver3_user.id,
            full_name='Mahesh Patil',
            age=45,
            phone='+91 98765 43212',
            address='88 Village Road, Ghansoli, Navi Mumbai 400701',
            license_number='DL-MH43-2012-44109',
            license_expiry='2028-08-20',
            is_verified=True,
            is_online=False
        )
        db.session.add_all([d1, d2, d3])
        db.session.flush()

        # Driver Training Records
        dt1 = DriverTraining(driver_id=d1.id, training_name='First Aid & Emergency Medical Care', training_date='2026-01-15', expiry_date='2027-01-15', status='COMPLETED')
        dt2 = DriverTraining(driver_id=d1.id, training_name='Student Safety & Transport Protocols', training_date='2026-02-10', expiry_date='2027-02-10', status='COMPLETED')
        dt3 = DriverTraining(driver_id=d2.id, training_name='Defensive Driving & Heavy Vehicle Safety', training_date='2025-11-20', expiry_date='2026-11-20', status='COMPLETED')

        db.session.add_all([dt1, dt2, dt3])

        print("Seeding Buses for KBP College Vashi...")
        bus_05 = Bus(institution_id=inst_kbp.id, registration_number='MH-43-CL-5005', bus_code='BUS-05', capacity=40, status='ACTIVE', current_lat=19.0760, current_lng=72.8777, driver_id=d1.id, route_id=r_a.id)
        bus_08 = Bus(institution_id=inst_kbp.id, registration_number='MH-43-CL-8008', bus_code='BUS-08', capacity=40, status='INACTIVE', driver_id=d2.id, route_id=r_b.id)
        bus_12 = Bus(institution_id=inst_kbp.id, registration_number='MH-43-CL-1212', bus_code='BUS-12', capacity=35, status='MAINTENANCE', driver_id=d3.id)

        db.session.add_all([bus_05, bus_08, bus_12])
        db.session.flush()

        # Back link bus to driver
        d1.assigned_bus_id = bus_05.id
        d2.assigned_bus_id = bus_08.id
        d3.assigned_bus_id = bus_12.id

        print("Seeding 15 Real Student Profiles for KBP College Vashi (Home <-> KBP College)...")
        students_data = [
            ('Manthan Patil', 'KBP-2026-CS501', 'B.Sc Computer Science (Third Year)', parent_models[0].id, bus_05.id, r_a.id, st_a1.id, st_a4.id, 'manthan_patil.png'),
            ('Ananya Sharma', 'KBP-2026-102', 'B.Com (First Year)', parent_models[1].id, bus_05.id, r_a.id, st_a2.id, st_a4.id, 'ananya_sharma.png'),
            ('Rohan Verma', 'KBP-2026-103', 'B.Sc Information Technology (Third Year)', parent_models[2].id, bus_05.id, r_a.id, st_a3.id, st_a4.id, 'rohan_verma.png'),
            ('Ishita Gupta', 'KBP-2026-104', 'BBA (Second Year)', parent_models[3].id, bus_08.id, r_b.id, st_b1.id, st_b4.id, 'ishita_gupta.png'),
            ('Aarav Deshmukh', 'KBP-2026-105', 'B.Sc Data Science (Second Year)', parent_models[4].id, bus_08.id, r_b.id, st_b2.id, st_b4.id, 'aarav_deshmukh.png'),
            ('Sanya Kulkarni', 'KBP-2026-106', 'M.Sc Computer Science (First Year)', parent_models[5].id, bus_08.id, r_b.id, st_b3.id, st_b4.id, 'sanya_kulkarni.png'),
            ('Aditya Shinde', 'KBP-2026-107', 'B.Tech Artificial Intelligence (First Year)', parent_models[6].id, bus_05.id, r_a.id, st_a1.id, st_a4.id, 'aditya_shinde.png'),
            ('Riya More', 'KBP-2026-108', 'B.A. Mass Communication (Third Year)', parent_models[7].id, bus_05.id, r_a.id, st_a2.id, st_a4.id, 'riya_more.png'),
            ('Kabir Joshi', 'KBP-2026-109', 'B.Sc Biotechnology (Second Year)', parent_models[8].id, bus_05.id, r_a.id, st_a3.id, st_a4.id, 'kabir_joshi.png'),
            ('Tanvi Bhosale', 'KBP-2026-110', 'B.Com Accounting & Finance (First Year)', parent_models[9].id, bus_08.id, r_b.id, st_b1.id, st_b4.id, 'tanvi_bhosale.png'),
            ('Yash Pawar', 'KBP-2026-111', 'B.Sc MicroBiology (Third Year)', parent_models[10].id, bus_08.id, r_b.id, st_b2.id, st_b4.id, 'yash_pawar.png'),
            ('Prisha Nambiar', 'KBP-2026-112', 'BMS Business Management (Second Year)', parent_models[11].id, bus_08.id, r_b.id, st_b3.id, st_b4.id, 'prisha_nambiar.png'),
            ('Siddharth Chavan', 'KBP-2026-113', 'B.Sc Cyber Security (First Year)', parent_models[12].id, bus_05.id, r_a.id, st_a1.id, st_a4.id, 'siddharth_chavan.png'),
            ('Neha Thorat', 'KBP-2026-114', 'M.Com Finance (Second Year)', parent_models[13].id, bus_05.id, r_a.id, st_a2.id, st_a4.id, 'neha_thorat.png'),
            ('Varun Kadam', 'KBP-2026-115', 'B.Sc Chemistry (Third Year)', parent_models[14].id, bus_05.id, r_a.id, st_a3.id, st_a4.id, 'varun_kadam.png'),
        ]

        created_students = []
        for name, roll, grade, p_id, b_id, r_id, pick_id, drop_id, photo in students_data:
            st = Student(
                institution_id=inst_kbp.id,
                full_name=name,
                roll_number=roll,
                grade_section=grade,
                parent_id=p_id,
                assigned_bus_id=b_id,
                assigned_route_id=r_id,
                pickup_stop_id=pick_id,
                drop_stop_id=drop_id,
                photo_filename=photo
            )
            db.session.add(st)
            created_students.append(st)

        db.session.flush()

        print("Seeding AI Face Feature Profiles for all 15 Students...")
        for st in created_students:
            v = np.zeros(64*64, dtype=np.float32)
            v[st.id * 25:(st.id + 1) * 25] = 0.5
            norm = np.linalg.norm(v)
            if norm > 0:
                v = v / norm

            fp = FaceProfile(student_id=st.id, feature_vector_json=json.dumps(v.tolist()), image_path=st.photo_filename)
            db.session.add(fp)

        print("Seeding Active Morning Trip & Boarding Attendance...")
        # Active Morning Trip for BUS-05 heading to KBP College Vashi
        t_active = Trip(
            institution_id=inst_kbp.id,
            bus_id=bus_05.id,
            driver_id=d1.id,
            route_id=r_a.id,
            trip_type='MORNING_PICKUP',
            status='IN_PROGRESS',
            start_time=datetime.utcnow() - timedelta(minutes=25),
            current_lat=19.0720,
            current_lng=72.9930
        )
        db.session.add(t_active)
        db.session.flush()

        # Verified Attendance entries for BUS-05 students
        for st in created_students[:4]:
            if st.assigned_bus_id == bus_05.id:
                att = Attendance(
                    student_id=st.id,
                    trip_id=t_active.id,
                    bus_id=bus_05.id,
                    verification_status='VERIFIED',
                    verified_by_driver_id=d1.id,
                    notes=f'AI Face Recognition Verified for {st.full_name}'
                )
                db.session.add(att)

                n = Notification(
                    user_id=st.parent.user.id,
                    title='🚌 Boarding Confirmed',
                    message=f'Your student {st.full_name} has boarded BUS-05 at 07:48 AM heading to KBP College Vashi.',
                    category='BOARDING'
                )
                db.session.add(n)

        # Active Safety Alert
        al1 = Alert(
            institution_id=inst_kbp.id,
            bus_id=bus_05.id,
            trip_id=t_active.id,
            alert_type='BUS_DELAY',
            risk_score=20,
            severity='WARNING',
            description='BUS-05 is running 8 minutes behind scheduled pickup at Sector 9 Vashi due to Palm Beach Road traffic.'
        )
        db.session.add(al1)

        print("Seeding Secondary Institution Data (St. Xavier's International School)...")
        # Admin for St. Xavier's
        admin_stx = User(
            institution_id=inst_stx.id,
            email='admin@stxaviers.edu',
            role='ADMIN',
            full_name='Father Francis (Principal, St. Xavier\'s)',
            phone='+91 98200 99887'
        )
        admin_stx.set_password('admin123')
        db.session.add(admin_stx)

        # Driver for St. Xavier's
        driver_stx_u = User(
            institution_id=inst_stx.id,
            email='driver@stxaviers.edu',
            role='DRIVER',
            full_name='Joseph D\'Souza',
            phone='+91 98765 99881'
        )
        driver_stx_u.set_password('driver123')
        db.session.add(driver_stx_u)
        db.session.flush()

        driver_stx = Driver(
            user_id=driver_stx_u.id,
            full_name='Joseph D\'Souza',
            phone='+91 98765 99881',
            license_number='DL-MH43-2020-55443',
            license_expiry='2031-12-31'
        )
        db.session.add(driver_stx)

        # Parent for St. Xavier's
        parent_stx_u = User(
            institution_id=inst_stx.id,
            email='parent@stxaviers.edu',
            role='PARENT',
            full_name='David D\'Silva',
            phone='+91 98200 55441'
        )
        parent_stx_u.set_password('parent123')
        db.session.add(parent_stx_u)
        db.session.flush()

        parent_stx = Parent(institution_id=inst_stx.id, user_id=parent_stx_u.id, address='Seawoods, Navi Mumbai')
        db.session.add(parent_stx)
        db.session.flush()

        # Route & Bus for St. Xavier's
        route_stx = Route(institution_id=inst_stx.id, name='St. Xavier Route 1', distance_km=8.0)
        db.session.add(route_stx)
        db.session.flush()

        bus_stx = Bus(institution_id=inst_stx.id, registration_number='MH-43-STX-1010', bus_code='BUS-STX-01', driver_id=driver_stx.id, route_id=route_stx.id)
        db.session.add(bus_stx)
        db.session.flush()
        driver_stx.assigned_bus_id = bus_stx.id

        # Student for St. Xavier's
        student_stx = Student(
            institution_id=inst_stx.id,
            full_name='Leo Xavier',
            roll_number='STX-2026-001',
            grade_section='Grade 6-A',
            parent_id=parent_stx.id,
            assigned_bus_id=bus_stx.id,
            assigned_route_id=route_stx.id
        )
        db.session.add(student_stx)
        db.session.flush()

        v_stx = np.zeros(64*64, dtype=np.float32)
        v_stx[0:100] = 0.8
        norm_stx = np.linalg.norm(v_stx)
        if norm_stx > 0:
            v_stx = v_stx / norm_stx

        fp_stx = FaceProfile(student_id=student_stx.id, feature_vector_json=json.dumps(v_stx.tolist()), image_path='default_student.png')
        db.session.add(fp_stx)

        db.session.commit()
        print("Database successfully seeded with multi-tenant institutions (KBP College Vashi & St. Xavier's)!")

if __name__ == '__main__':
    seed_database()
