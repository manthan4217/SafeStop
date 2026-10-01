#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
flask db upgrade
python run.py seed-db