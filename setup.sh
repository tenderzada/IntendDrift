#!/bin/bash
# IntentDrift-SWE setup script for Ubuntu server
set -e

echo "=== IntentDrift-SWE Setup ==="

# Install Python deps
pip install -r requirements.txt

# Verify
python -c "import openai; print(f'openai {openai.__version__}')"
python -c "import flask; print(f'flask {flask.__version__}')"
python -c "import pytest; print(f'pytest {pytest.__version__}')"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Quick start:"
echo "  # Set your API key:"
echo "  export DASHSCOPE_API_KEY=sk-xxx"
echo ""
echo "  # Run one task locally:"
echo "  cd pilot && python run.py --task T1-001 --model qwen"
echo ""
echo "  # Run with Daytona sandbox:"
echo "  export DAYTONA_API_KEY=xxx"
echo "  cd pilot && python run.py --task T1-001 --model qwen --sandbox daytona"
echo ""
echo "  # List all tasks:"
echo "  cd pilot && python run.py --list"
