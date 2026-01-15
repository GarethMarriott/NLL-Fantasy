#!/bin/bash
# Phase 5: Nginx Configuration
# Run this on the DigitalOcean server as root

set -e

APP_DIR="/opt/shamrock-fantasy"
DOMAIN="shamrockfantasy.com"
IP="138.68.228.237"

echo "=========================================="
echo "Phase 5: Nginx Configuration"
echo "=========================================="

# Step 1: Create Nginx configuration
echo "[1/4] Creating Nginx configuration..."
cat > /etc/nginx/sites-available/shamrock-fantasy << NGINXEOF
upstream shamrock_app {
    server unix:$APP_DIR/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN $IP;
    client_max_body_size 20M;

    access_log $APP_DIR/logs/nginx_access.log;
    error_log $APP_DIR/logs/nginx_error.log;

    location /static/ {
        alias $APP_DIR/web/static/;
        expires 30d;
    }

    location /media/ {
        alias $APP_DIR/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://shamrock_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_read_timeout 30s;
    }
}
NGINXEOF

# Step 2: Enable the Nginx site
echo "[2/4] Enabling Nginx site..."
ln -sf /etc/nginx/sites-available/shamrock-fantasy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Step 3: Test Nginx configuration
echo "[3/4] Testing Nginx configuration..."
nginx -t

# Step 4: Restart Nginx
echo "[4/4] Restarting Nginx..."
systemctl restart nginx
systemctl status nginx --no-pager | head -10

echo ""
echo "=========================================="
echo "✅ Phase 5 Complete!"
echo "=========================================="
echo ""
echo "Nginx is configured and running!"
echo ""
echo "Next steps:"
echo "1. Point your domain DNS to: 138.68.228.237"
echo "2. Install SSL certificate (Phase 6)"
echo "3. Test the application at: http://$DOMAIN"
