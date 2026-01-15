# DigitalOcean Deployment Guide
## NLL Fantasy Lacrosse Django Application

**Date**: January 14, 2026  
**Domain**: ShamrockFantasy.com  
**Droplet IP**: 138.68.228.237  
**OS**: Ubuntu 22.04 LTS

---

## 📋 Pre-Deployment Checklist

- [x] SSH keys generated locally
- [x] DigitalOcean droplet created (138.68.228.237)
- [x] SSH key added to droplet
- [x] Production domain ready (ShamrockFantasy.com)
- [ ] GitHub repository access (if needed)
- [ ] All environment variables prepared

---

## 🚀 Phase 1: Initial Server Setup (15 minutes)

### Step 1.1: SSH into your Droplet

```powershell
ssh root@138.68.228.237
```

First time might ask to verify the host key. Type `yes`.

### Step 1.2: Update System Packages

```bash
apt-get update
apt-get upgrade -y
```

### Step 1.3: Install Required Dependencies

```bash
apt-get install -y python3.11 python3.11-venv python3-pip \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    git \
    curl \
    wget \
    build-essential \
    libpq-dev
```

### Step 1.4: Verify Installations

```bash
python3.11 --version
psql --version
redis-cli --version
nginx -v
```

---

## 🗄️ Phase 2: Database Setup (10 minutes)

### Step 2.1: Start PostgreSQL

```bash
systemctl start postgresql
systemctl enable postgresql
```

### Step 2.2: Create Database and User

```bash
sudo -u postgres psql
```

Then in the PostgreSQL prompt:

```sql
CREATE DATABASE nll_fantasy;
CREATE USER fantasy_user WITH PASSWORD 'SECURE_PASSWORD_HERE';
ALTER ROLE fantasy_user SET client_encoding TO 'utf8';
ALTER ROLE fantasy_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE fantasy_user SET default_transaction_deferrable TO on;
ALTER ROLE fantasy_user SET default_transaction_level TO 'read committed';
GRANT ALL PRIVILEGES ON DATABASE nll_fantasy TO fantasy_user;
\q
```

**Save your database password!** You'll need it for `.env`.

---

## ⚙️ Phase 3: Application Setup (20 minutes)

### Step 3.1: Create Application Directory

```bash
mkdir -p /var/www/nll-fantasy
cd /var/www/nll-fantasy
```

### Step 3.2: Clone Your Repository

```bash
git clone https://github.com/YOUR_USERNAME/NLL-Fantasy-1.git .
```

(Replace with your actual GitHub URL)

### Step 3.3: Create Python Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### Step 3.4: Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3.5: Create Production `.env` File

```bash
nano .env
```

Paste this and update with your values:

```dotenv
# Django Settings
SECRET_KEY=django-insecure-YOUR_NEW_SECRET_KEY_HERE
DEBUG=False
ALLOWED_HOSTS=ShamrockFantasy.com,www.ShamrockFantasy.com,138.68.228.237

ENVIRONMENT=production

# Database
DATABASE_URL=postgresql://fantasy_user:SECURE_PASSWORD_HERE@localhost:5432/nll_fantasy

# Email Configuration - SendGrid
EMAIL_BACKEND=anymail.backends.sendgrid.EmailBackend
SENDGRID_API_KEY=SG.YOUR_SENDGRID_KEY_HERE
DEFAULT_FROM_EMAIL=noreply@ShamrockFantasy.com
SERVER_EMAIL=server@ShamrockFantasy.com

# Celery & Redis Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REDIS_URL=redis://127.0.0.1:6379/1

# CORS Configuration
CORS_ALLOWED_ORIGINS=https://ShamrockFantasy.com,https://www.ShamrockFantasy.com

# Sentry Configuration
SENTRY_DSN=https://YOUR_SENTRY_DSN_HERE

# Performance Profiling
ENABLE_SILK_PROFILING=False
```

**Save the file**: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 3.6: Generate New Secret Key

Run this to generate a secure SECRET_KEY:

```bash
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Update your `.env` with this value.

### Step 3.7: Run Database Migrations

```bash
python manage.py migrate
```

### Step 3.8: Create Superuser

```bash
python manage.py createsuperuser
```

Follow the prompts to create an admin account.

### Step 3.9: Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Step 3.10: Test Django App

```bash
python manage.py runserver 0.0.0.0:8000
```

Visit: `http://138.68.228.237:8000`

If it works, press `Ctrl+C` to stop.

---

## 🔄 Phase 4: Gunicorn Setup (10 minutes)

### Step 4.1: Install Gunicorn

```bash
pip install gunicorn
```

### Step 4.2: Create Gunicorn Service File

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

Paste this:

```ini
[Unit]
Description=Gunicorn daemon for NLL Fantasy
After=network.target

[Service]
User=root
Group=www-data
WorkingDirectory=/var/www/nll-fantasy
ExecStart=/var/www/nll-fantasy/venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8001 \
    --timeout 120 \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 4.3: Start Gunicorn

```bash
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```

### Step 4.4: Check Gunicorn Status

```bash
sudo systemctl status gunicorn
```

---

## 🌐 Phase 5: Nginx Configuration (10 minutes)

### Step 5.1: Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/nll-fantasy
```

Paste this:

```nginx
upstream gunicorn {
    server 127.0.0.1:8001;
}

server {
    listen 80;
    server_name ShamrockFantasy.com www.ShamrockFantasy.com;
    client_max_body_size 100M;

    location /static/ {
        alias /var/www/nll-fantasy/static/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/nll-fantasy/media/;
    }

    location / {
        proxy_pass http://gunicorn;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 5.2: Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/nll-fantasy /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
```

### Step 5.3: Test Nginx

```bash
sudo nginx -t
```

Should output:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Step 5.4: Start Nginx

```bash
sudo systemctl start nginx
sudo systemctl enable nginx
```

### Step 5.5: Verify Nginx Status

```bash
sudo systemctl status nginx
```

---

## 🔒 Phase 6: SSL/HTTPS Setup (Let's Encrypt) (10 minutes)

### Step 6.1: Install Certbot

```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

### Step 6.2: Get SSL Certificate

```bash
sudo certbot certonly --nginx -d ShamrockFantasy.com -d www.ShamrockFantasy.com
```

Follow the prompts and enter your email.

### Step 6.3: Update Nginx for SSL

```bash
sudo nano /etc/nginx/sites-available/nll-fantasy
```

Replace the entire file with this:

```nginx
upstream gunicorn {
    server 127.0.0.1:8001;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name ShamrockFantasy.com www.ShamrockFantasy.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name ShamrockFantasy.com www.ShamrockFantasy.com;
    client_max_body_size 100M;

    ssl_certificate /etc/letsencrypt/live/ShamrockFantasy.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ShamrockFantasy.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location /static/ {
        alias /var/www/nll-fantasy/static/;
        expires 30d;
    }

    location /media/ {
        alias /var/www/nll-fantasy/media/;
    }

    location / {
        proxy_pass http://gunicorn;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 6.4: Test & Reload Nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

---

## 💌 Phase 7: Background Services (Celery & Redis)

### Step 7.1: Start Redis

```bash
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### Step 7.2: Create Celery Worker Service

```bash
sudo nano /etc/systemd/system/celery.service
```

Paste this:

```ini
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=root
Group=www-data
WorkingDirectory=/var/www/nll-fantasy
ExecStart=/var/www/nll-fantasy/venv/bin/celery -A config worker \
    -l info \
    --logfile=/var/log/celery.log \
    --pidfile=/var/run/celery.pid \
    --detach

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 7.3: Create Celery Beat Service

```bash
sudo nano /etc/systemd/system/celery-beat.service
```

Paste this:

```ini
[Unit]
Description=Celery Beat Service
After=network.target

[Service]
Type=simple
User=root
Group=www-data
WorkingDirectory=/var/www/nll-fantasy
ExecStart=/var/www/nll-fantasy/venv/bin/celery -A config beat \
    -l info \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler

[Install]
WantedBy=multi-user.target
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

### Step 7.4: Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl start celery
sudo systemctl enable celery
sudo systemctl start celery-beat
sudo systemctl enable celery-beat
```

### Step 7.5: Check Service Status

```bash
sudo systemctl status celery
sudo systemctl status celery-beat
```

---

## 🌍 Phase 8: Domain DNS Configuration

Update your domain registrar's DNS records to point to DigitalOcean:

**Add these DNS records:**

| Type | Name | Value |
|------|------|-------|
| A | @ | 138.68.228.237 |
| A | www | 138.68.228.237 |

Wait 5-15 minutes for DNS to propagate.

Test: `nslookup ShamrockFantasy.com`

---

## ✅ Phase 9: Final Verification

### Step 9.1: Check All Services Running

```bash
sudo systemctl status nginx
sudo systemctl status gunicorn
sudo systemctl status postgresql
sudo systemctl status redis-server
sudo systemctl status celery
sudo systemctl status celery-beat
```

### Step 9.2: Test Website

Visit: https://ShamrockFantasy.com

You should see your NLL Fantasy app!

### Step 9.3: Test Admin Panel

Visit: https://ShamrockFantasy.com/admin

Log in with the superuser you created.

### Step 9.4: Test Email

Go to `/admin/` → Web → Bug reports → Submit test bug

Check your email to verify SendGrid is working.

### Step 9.5: Check Sentry Dashboard

Trigger a test error:

```bash
cd /var/www/nll-fantasy
source venv/bin/activate
python manage.py shell -c "raise Exception('Production test error')"
```

Visit your Sentry dashboard to verify it was captured.

---

## 🔧 Troubleshooting

### Django not starting?

```bash
cd /var/www/nll-fantasy
source venv/bin/activate
python manage.py check
```

### Check Gunicorn logs:

```bash
sudo journalctl -u gunicorn -n 50 -f
```

### Check Nginx errors:

```bash
sudo tail -f /var/log/nginx/error.log
```

### Check Celery logs:

```bash
sudo tail -f /var/log/celery.log
```

### Database connection issues?

```bash
psql -h localhost -U fantasy_user -d nll_fantasy
```

### Redis not working?

```bash
redis-cli ping
# Should return: PONG
```

---

## 📚 Useful Commands

### SSH into server:
```powershell
ssh root@138.68.228.237
```

### View logs:
```bash
# Nginx errors
sudo tail -f /var/log/nginx/error.log

# Gunicorn
sudo journalctl -u gunicorn -f

# Celery
sudo tail -f /var/log/celery.log
```

### Restart services:
```bash
sudo systemctl restart nginx
sudo systemctl restart gunicorn
sudo systemctl restart celery
```

### Update code:
```bash
cd /var/www/nll-fantasy
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
```

---

## 🎉 Deployment Complete!

Your NLL Fantasy application is now **live on DigitalOcean**!

**Live URL**: https://ShamrockFantasy.com

**Admin Panel**: https://ShamrockFantasy.com/admin

**Bug Reports**: https://ShamrockFantasy.com/bugs/report/

**Monitor**: Check Sentry, SendGrid, and server logs regularly.

---

## 📞 Support

If you encounter issues:
1. Check logs (see Troubleshooting section)
2. Verify all services are running
3. Check DigitalOcean Dashboard for droplet health
4. Review DNS configuration if domain not resolving

**Document Created**: January 14, 2026
