#!/bin/bash
# Phase 3: Django Application Setup
# Run this on the DigitalOcean server as root

set -e  # Exit on any error

APP_DIR="/opt/shamrock-fantasy"
DB_USER="shamrock"
DB_PASS="ShamrockFantasy2026!"
DB_NAME="shamrock_fantasy"

echo "=========================================="
echo "Phase 3: Django Application Setup"
echo "=========================================="

# Step 1: Verify dependencies
echo "[1/5] Verifying dependencies..."
python3 --version
psql --version
redis-cli --version
nginx -v

# Step 2: Update .env file with production settings
echo "[2/5] Configuring production environment..."
cat > $APP_DIR/.env << ENVEOF
# Django Settings
DEBUG=False
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
ALLOWED_HOSTS=138.68.228.237,shamrockfantasy.com,www.shamrockfantasy.com

# Database
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME

# Email
EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
SENDGRID_API_KEY=your-sendgrid-api-key-here
DEFAULT_FROM_EMAIL=shamrockfantasy@gmail.com

# Sentry
SENTRY_DSN=your-sentry-dsn-here

# Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Features
ENABLE_SILK_PROFILING=False
ENABLE_DEBUG_TOOLBAR=False
ENVEOF

echo ".env file created at $APP_DIR/.env"

# Step 3: Install Python dependencies
echo "[3/5] Installing Python packages..."
pip3 install --break-system-packages -q -r $APP_DIR/requirements.txt
echo "Python packages installed"

# Step 4: Run Django migrations
echo "[4/5] Running Django migrations..."
cd $APP_DIR
python3 manage.py migrate --noinput

# Step 5: Collect static files
echo "[5/5] Collecting static files..."
python3 manage.py collectstatic --noinput

echo ""
echo "=========================================="
echo "✅ Phase 3 Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Update .env file with your SendGrid API key and Sentry DSN"
echo "2. Run: nano $APP_DIR/.env"
echo "3. Then proceed to Phase 4 (Gunicorn setup)"
