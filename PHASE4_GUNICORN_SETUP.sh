#!/bin/bash
# Phase 4: Gunicorn Setup
# Run this on the DigitalOcean server as root

set -e

APP_DIR="/opt/shamrock-fantasy"
APP_USER="www-data"
WORKERS=4
WORKER_CLASS="sync"

echo "=========================================="
echo "Phase 4: Gunicorn Setup"
echo "=========================================="

# Step 1: Install Gunicorn
echo "[1/4] Installing Gunicorn..."
pip3 install --break-system-packages -q gunicorn

# Step 2: Create Gunicorn systemd service
echo "[2/4] Creating Gunicorn systemd service..."
cat > /etc/systemd/system/gunicorn.service << SERVICEOF
[Unit]
Description=Gunicorn application server for Shamrock Fantasy
After=network.target
After=postgresql.service
After=redis.service

[Service]
Type=notify
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=/usr/local/bin/gunicorn \\
    --workers $WORKERS \\
    --worker-class $WORKER_CLASS \\
    --bind unix:$APP_DIR/gunicorn.sock \\
    --timeout 30 \\
    --access-logfile $APP_DIR/logs/gunicorn_access.log \\
    --error-logfile $APP_DIR/logs/gunicorn_error.log \\
    config.wsgi:application

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEOF

# Step 3: Create logs directory
echo "[3/4] Setting up log directories..."
mkdir -p $APP_DIR/logs
touch $APP_DIR/logs/gunicorn_access.log
touch $APP_DIR/logs/gunicorn_error.log
chown -R $APP_USER:$APP_USER $APP_DIR/logs

# Step 4: Enable and start Gunicorn
echo "[4/4] Enabling Gunicorn service..."
systemctl daemon-reload
systemctl enable gunicorn.service
systemctl start gunicorn.service
sleep 2
systemctl status gunicorn.service --no-pager | head -10

echo ""
echo "=========================================="
echo "✅ Phase 4 Complete!"
echo "=========================================="
echo ""
echo "Gunicorn is running. Next: Configure Nginx (Phase 5)"
