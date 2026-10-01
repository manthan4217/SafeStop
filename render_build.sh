#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
# Check if DB needs setup or just migration
flask db upgrade || echo "Migrations failed. Ensure DB is properly initialized."
python run.py init-db || echo "Skipping init-db (tables may already exist)."
python run.py seed-db