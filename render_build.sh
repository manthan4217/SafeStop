#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

# Reset the database completely to clear corrupted tables
# We downgrade to base to wipe everything, then upgrade back to head
flask db downgrade base || echo "Downgrade failed, moving on..."
flask db upgrade

# Re-seed the clean database
python run.py init-db || echo "Skipping init-db"
python run.py seed-db