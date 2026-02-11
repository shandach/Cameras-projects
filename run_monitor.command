#!/bin/bash

# Get directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Activate virtual environment if it exists (assuming standard names)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the monitoring app
echo "🚀 Starting Workplace Monitoring..."
python3 main.py

# Keep window open if it crashes
echo "Press Enter to close..."
read
