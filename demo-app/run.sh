#!/bin/bash
# Run the demo app

# Make sure we're in the right directory
cd "$(dirname "$0")"

# Activate virtualenv if it exists
if [ -d "../venv" ]; then
    source ../venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# Run using pyhtml CLI from parent directory
cd ..
exec pyhtml dev --pages-dir demo-app/src/pages --host 127.0.0.1 --port 3000 --reload
