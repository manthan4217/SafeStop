import pytest
from app import create_app
from app.models import db, User, Parent, Student, Bus, Route, Stop, Trip, Notification, StopProximityLog
from app.gps.tracker import process_gps_update

@pytest.fixture
def test_app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(test_app):
    return test_app.test_client()

def test_stop_proximity_log_model(test_app):
    with test_app.app_context():
        u = User(email='parent_prox@test.com', role='PARENT', full_name='Proximity Parent')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()

        p = Parent(user_id=u.id, proximity_radius_meters=500)
        b = Bus(registration_number='MH-43-PX-100', bus_code='BUS-PX1')
        r = Route(name='Proximity Route', distance_km=5.0)
        db.session.add_all([p, b, r])
        db.session.commit()

        s_pickup = Stop(route_id=r.id, stop_name='Vashi Station', sequence_order=1, latitude=19.0760, longitude=72.8777)
        db.session.add(s_pickup)
        db.session.commit()

        st = Student(full_name='Aarav Prox', roll_number='PROX-001', parent_id=p.id, assigned_bus_id=b.id, pickup_stop_id=s_pickup.id)
        t = Trip(bus_id=b.id, driver_id=1, route_id=r.id, trip_type='MORNING_PICKUP', status='IN_PROGRESS')
        db.session.add_all([st, t])
        db.session.commit()

        prox = StopProximityLog(
            trip_id=t.id,
            bus_id=b.id,
            stop_id=s_pickup.id,
            student_id=st.id,
            parent_id=p.id,
            distance_meters=350.0,
            estimated_eta_mins=2
        )
        db.session.add(prox)
        db.session.commit()

        fetched = StopProximityLog.query.filter_by(student_id=st.id).first()
        assert fetched is not None
        assert fetched.distance_meters == 350.0
        assert fetched.estimated_eta_mins == 2

def test_gps_proximity_geo_fence_alert(test_app):
    with test_app.app_context():
        pu = User(email='parent_geo@test.com', role='PARENT', full_name='Geo Parent')
        pu.set_password('pass123')
        db.session.add(pu)
        db.session.commit()

        p = Parent(user_id=pu.id, proximity_radius_meters=500)
        b = Bus(registration_number='MH-43-GEO-200', bus_code='BUS-GEO2')
        r = Route(name='Geo Route', distance_km=8.0)
        db.session.add_all([p, b, r])
        db.session.commit()

        # Stop at coordinates (19.0760, 72.8777)
        s = Stop(route_id=r.id, stop_name='Nerul Sector 15', sequence_order=1, latitude=19.0760, longitude=72.8777)
        db.session.add(s)
        db.session.commit()

        st = Student(full_name='Rohan Geo', roll_number='GEO-002', parent_id=p.id, assigned_bus_id=b.id, pickup_stop_id=s.id)
        t = Trip(bus_id=b.id, driver_id=1, route_id=r.id, trip_type='MORNING_PICKUP', status='IN_PROGRESS')
        db.session.add_all([st, t])
        db.session.commit()

        trip_id = t.id
        parent_user_id = pu.id

        # Update GPS to position ~300 meters away from stop (19.0735, 72.8777)
        res = process_gps_update(trip_id, 19.0735, 72.8777, speed=30.0)
        assert res['status'] == 'SUCCESS'

        # Verify StopProximityLog & Notification generated
        prox = StopProximityLog.query.filter_by(trip_id=trip_id).first()
        assert prox is not None
        assert prox.distance_meters <= 500.0

        n = Notification.query.filter_by(user_id=parent_user_id).first()
        assert n is not None
        assert 'PROXIMITY ALERT' in n.title
        assert 'Rohan Geo' in n.message

def test_update_proximity_preferences_route(test_app, client):
    with test_app.app_context():
        u = User(email='parent_pref@test.com', role='PARENT', full_name='Pref Parent')
        u.set_password('parentpass')
        db.session.add(u)
        db.session.commit()

        p = Parent(user_id=u.id, proximity_radius_meters=500)
        db.session.add(p)
        db.session.commit()
        parent_id = p.id

    client.post('/auth/login', data={'email': 'parent_pref@test.com', 'password': 'parentpass'}, follow_redirects=True)
    res = client.post('/parent/proximity-preferences', data={'proximity_radius_meters': '1000'}, follow_redirects=True)
    assert res.status_code == 200

    with test_app.app_context():
        parent_updated = db.session.get(Parent, parent_id)
        assert parent_updated.proximity_radius_meters == 1000
