import os
import sys
from app import create_app
from app.models import db, User
from app.seed import seed_database

app = create_app()

@app.cli.command("init-db")
def init_db_command():
    """Clear existing data and create all database tables."""
    with app.app_context():
        # Do not drop tables in production
        # db.drop_all()
        db.create_all()
        print("Database tables created/verified successfully.")

@app.cli.command("seed-db")
def seed_db_command():
    """Populate database with baseline real data and demo user profiles."""
    seed_database()
    print("Database seeded successfully.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'init-db':
        with app.app_context():
            db.create_all()
            print("Database initialized successfully.")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == 'seed-db':
        seed_database()
        sys.exit(0)

    with app.app_context():
        # Ensure database tables exist
        db.create_all()

        # Check if database has any users registered
        user_count = User.query.count()
        if user_count == 0:
            print("No existing user accounts found. Seeding initial demonstration dataset...")
            seed_database()

    print("\n=======================================================================")
    print(" SAFERIDE AI -- KARMAVEER BHAURAO PATIL (KBP) COLLEGE, VASHI")
    print(" Smart Student Verification & Transport Safety System")
    print("=======================================================================")
    print(" App is running live on http://127.0.0.1:5000")
    print("\n Management Commands:")
    print(" Initialize Clean DB : python manage_db.py init")
    print(" Create Admin        : python manage_db.py create-admin --email <email> --password <pass>")
    print(" Database Status     : python manage_db.py status")
@app.route('/force-seed-database-secret-url-2026')
def force_seed():
    """A temporary backdoor route to force database initialization since Render Free Tier blocks Shell access."""
    try:
        from app.seed import seed_database

        # 1. Create tables
        db.create_all()

        # 2. Run seed
        seed_database()

        return "SUCCESS! Database tables created and data seeded. You can now login.", 200
    except Exception as e:
        import traceback
        error_msg = f"ERROR: {str(e)}\n\n{traceback.format_exc()}"
        return error_msg, 500

    print("=======================================================================\n")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

