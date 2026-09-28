#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
pip install -r requirements.txt -q
echo "Starting EngBrain on http://0.0.0.0:8000"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
