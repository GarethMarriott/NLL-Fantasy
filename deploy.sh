#!/bin/bash
# ============================================================
# SHAMROCK FANTASY - COMPLETE DEPLOYMENT SCRIPT
# ============================================================
# Usage: chmod +x deploy.sh && ./deploy.sh
# Run as root on DigitalOcean Ubuntu 22.04 LTS server
# ============================================================

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/shamrock-fantasy"
DB_USER="shamrock"
DB_PASS="ShamrockFantasy2026!"
DB_NAME="shamrock_fantasy"
DOMAIN="${DOMAIN:-shamrockfantasy.com}"
IP="${IP:-138.68.228.237}"

# ============================================================
# Helper Functions
# ============================================================

log_step() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# ============================================================
# Phase 1: Verify System (ALREADY COMPLETE)
# ============================================================

phase_1_verify() {
    log_step "Phase 1: Verifying system..."
    
    python3 --version || log_error "Python3 not found"
    psql --version || log_error "PostgreSQL not found"
    redis-cli --version || log_error "Redis not found"
    nginx -v 2>&1 || log_error "Nginx not found"
    
    log_success "All system dependencies verified"
}

# ============================================================
# Phase 3: Django Application Setup
# ============================================================

phase_3_app_setup() {
    log_step "Phase 3: Setting up Django application..."
    
    if [ ! -d "$APP_DIR" ]; then
        log_error "Application directory not found at $APP_DIR"
    fi
    
    cd $APP_DIR
    
    # Update .env file
    log_step "Generating Django SECRET_KEY..."
    SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
    
    cat > $APP_DIR/.env << ENVEOF
# Django Settings
DEBUG=False
SECRET_KEY=$SECRET_KEY
ALLOWED_HOSTS=$IP,$DOMAIN,www.$DOMAIN

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

    log_success ".env file created"
    
    # Install Python dependencies
    log_step "Installing Python packages..."
    pip3 install --break-system-packages -q -r requirements.txt
    log_success "Python packages installed"
    
    # Run migrations
    log_step "Running database migrations..."
    python3 manage.py migrate --noinput
    log_success "Database migrations completed"
    
    # Collect static files
    log_step "Collecting static files..."
    python3 manage.py collectstatic --noinput
    log_success "Static files collected"
}

# ============================================================
# Phase 4: Gunicorn Setup
# ============================================================

phase_4_gunicorn() {
    log_step "Phase 4: Setting up Gunicorn..."
    
    WORKERS=4
    APP_USER="www-data"
    
    # Install Gunicorn
    pip3 install --break-system-packages -q gunicorn
    log_success "Gunicorn installed"
    
    # Create systemd service
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
ExecStart=/usr/local/bin/gunicorn \\
    --workers $WORKERS \\
    --worker-class sync \\
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

    log_success "Gunicorn systemd service created"
    
    # Setup logs
    mkdir -p $APP_DIR/logs
    touch $APP_DIR/logs/gunicorn_access.log
    touch $APP_DIR/logs/gunicorn_error.log
    chown -R $APP_USER:$APP_USER $APP_DIR/logs
    
    # Enable and start
    systemctl daemon-reload
    systemctl enable gunicorn.service
    systemctl start gunicorn.service
    sleep 2
    
    if systemctl is-active --quiet gunicorn; then
        log_success "Gunicorn service running"
    else
        log_error "Gunicorn service failed to start"
    fi
}

# ============================================================
# Phase 5: Nginx Configuration
# ============================================================

phase_5_nginx() {
    log_step "Phase 5: Configuring Nginx..."
    
    # Create Nginx configuration
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

    log_success "Nginx configuration created"
    
    # Enable site
    ln -sf /etc/nginx/sites-available/shamrock-fantasy /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    # Test and restart
    nginx -t || log_error "Nginx configuration test failed"
    systemctl restart nginx
    
    if systemctl is-active --quiet nginx; then
        log_success "Nginx restarted and running"
    else
        log_error "Nginx failed to start"
    fi
}

# ============================================================
# Phase 6: Redis and Celery
# ============================================================

phase_6_celery() {
    log_step "Phase 6: Configuring Redis and Celery..."
    
    # Start Redis
    systemctl start redis-server
    systemctl enable redis-server
    
    if redis-cli ping | grep -q PONG; then
        log_success "Redis is running"
    else
        log_error "Redis failed to start"
    fi
    
    # Install Celery
    pip3 install --break-system-packages -q celery
    
    # Create Celery systemd service
    cat > /etc/systemd/system/celery.service << SERVICEOF
[Unit]
Description=Celery Service for Shamrock Fantasy
After=network.target
After=redis.service

[Service]
Type=forking
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/celery -A config multi start worker \\
    --loglevel=info --logfile=$APP_DIR/logs/celery.log

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEOF

    systemctl daemon-reload
    systemctl enable celery.service
    systemctl start celery.service
    
    log_success "Celery service configured"
}

# ============================================================
# Phase 7: System Services
# ============================================================

phase_7_services() {
    log_step "Phase 7: Finalizing system services..."
    
    # Ensure all services are enabled
    systemctl enable postgresql
    systemctl enable redis-server
    systemctl enable nginx
    systemctl enable gunicorn
    
    log_success "All services enabled"
}

# ============================================================
# Main Deployment
# ============================================================

main() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   SHAMROCK FANTASY - DEPLOYMENT SCRIPT             ║${NC}"
    echo -e "${GREEN}║   Production Deployment to DigitalOcean             ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
    fi
    
    # Run phases
    phase_1_verify
    phase_3_app_setup
    phase_4_gunicorn
    phase_5_nginx
    phase_6_celery
    phase_7_services
    
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   ✅ DEPLOYMENT COMPLETE!                          ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}NEXT STEPS:${NC}"
    echo "1. Update .env with SendGrid API key: nano $APP_DIR/.env"
    echo "2. Update .env with Sentry DSN: nano $APP_DIR/.env"
    echo "3. Point domain DNS to: $IP"
    echo "4. Run health check: curl http://$IP"
    echo "5. Monitor logs: tail -f $APP_DIR/logs/gunicorn_error.log"
    echo ""
}

# Run main
main "$@"
