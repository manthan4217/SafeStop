#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt
python run.py init-db
python run.py seed-db