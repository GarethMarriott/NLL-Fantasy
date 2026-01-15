# DigitalOcean Deployment Guide - Complete Instructions

## Current Status

✅ **Completed on Server (138.68.228.237):**
- Python 3.12.3
- PostgreSQL 16.11 with database `shamrock_fantasy` and user `shamrock`
- Redis 7.0.15
- Nginx 1.24.0
- Application cloned to `/opt/shamrock-fantasy`

---

## Deployment Steps

### Step 1: Access Your Server via SSH

```bash
ssh root@138.68.228.237
```

When prompted for a password, use the one from DigitalOcean email. Alternatively, if you added your SSH key:

```bash
ssh -i ~/.ssh/id_rsa root@138.68.228.237
```

---

### Step 2: Download and Run the Deployment Script

Once connected to the server, run:

```bash
cd /opt/shamrock-fantasy

# Download the deployment script (or you can create it manually)
curl -O https://raw.githubusercontent.com/GarethMarriott/NLL-Fantasy/main/deploy.sh

# Or copy it from your local machine
# scp deploy.sh root@138.68.228.237:/opt/shamrock-fantasy/

# Make it executable
chmod +x deploy.sh

# Run the deployment
sudo ./deploy.sh
```

**What this script does:**
1. ✅ Verifies all system dependencies
2. ✅ Generates Django SECRET_KEY and creates .env
3. ✅ Installs Python packages
4. ✅ Runs database migrations
5. ✅ Collects static files
6. ✅ Sets up Gunicorn application server
7. ✅ Configures Nginx reverse proxy
8. ✅ Starts Redis and Celery
9. ✅ Enables all services for auto-start

---

### Step 3: Configure Environment Variables

After the script completes, edit the .env file with your credentials:

```bash
nano /opt/shamrock-fantasy/.env
```

Update these values:
```env
SENDGRID_API_KEY=your-actual-sendgrid-key
SENTRY_DSN=your-actual-sentry-dsn
DEFAULT_FROM_EMAIL=shamrockfantasy@gmail.com
```

Save (Ctrl+X, then Y, then Enter)

---

### Step 4: Restart Services to Load New Environment

```bash
systemctl restart gunicorn
systemctl restart celery
```

---

### Step 5: Configure DNS

Point your domain DNS records to the server IP: **138.68.228.237**

For shamrockfantasy.com:
- Add **A Record**: `@` → `138.68.228.237`
- Add **A Record**: `www` → `138.68.228.237`

DNS propagation may take 5-30 minutes.

---

### Step 6: Test the Deployment

```bash
# Test HTTP connection
curl http://138.68.228.237

# Once DNS is configured
curl http://shamrockfantasy.com

# Check application logs
tail -f /opt/shamrock-fantasy/logs/gunicorn_error.log
```

---

### Step 7: Set Up SSL Certificate (Recommended)

Once your domain is live, install Let's Encrypt SSL:

```bash
apt-get install -y certbot python3-certbot-nginx
certbot --nginx -d shamrockfantasy.com -d www.shamrockfantasy.com
```

Follow the prompts to set up automatic renewal.

---

## Monitoring and Troubleshooting

### Check Service Status

```bash
# Gunicorn
systemctl status gunicorn
tail -f /opt/shamrock-fantasy/logs/gunicorn_error.log

# Nginx
systemctl status nginx
tail -f /opt/shamrock-fantasy/logs/nginx_error.log

# Celery
systemctl status celery
tail -f /opt/shamrock-fantasy/logs/celery.log

# Redis
redis-cli ping  # Should return PONG

# PostgreSQL
psql -U shamrock -d shamrock_fantasy -c "SELECT 1"
```

### Restart Services

```bash
# Restart all services
systemctl restart gunicorn nginx celery

# Or individually
systemctl restart gunicorn
systemctl restart nginx
systemctl restart celery
```

### View Application Logs

```bash
# Gunicorn access logs
tail -f /opt/shamrock-fantasy/logs/gunicorn_access.log

# Gunicorn errors
tail -f /opt/shamrock-fantasy/logs/gunicorn_error.log

# Nginx access
tail -f /opt/shamrock-fantasy/logs/nginx_access.log

# Nginx errors
tail -f /opt/shamrock-fantasy/logs/nginx_error.log
```

---

## Database Backup

Create a backup of your database:

```bash
# Backup the database
pg_dump -U shamrock shamrock_fantasy > shamrock_fantasy_backup_$(date +%Y%m%d).sql

# Restore from backup
psql -U shamrock shamrock_fantasy < shamrock_fantasy_backup_20260115.sql
```

---

## Updating the Application

When you need to deploy code changes:

```bash
cd /opt/shamrock-fantasy

# Pull latest changes
git pull origin main

# Install new dependencies (if any)
pip3 install --break-system-packages -q -r requirements.txt

# Run migrations (if any)
python3 manage.py migrate --noinput

# Collect static files
python3 manage.py collectstatic --noinput

# Restart services
systemctl restart gunicorn celery
```

---

## Manual Deployment (If Deploy Script Doesn't Work)

If you prefer to run the phases manually:

### Phase 3: Django Setup
```bash
cd /opt/shamrock-fantasy

# Generate SECRET_KEY
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Edit .env with your settings
nano .env

# Install packages
pip3 install --break-system-packages -q -r requirements.txt

# Run migrations
python3 manage.py migrate --noinput

# Collect static files
python3 manage.py collectstatic --noinput
```

### Phase 4: Gunicorn Setup
```bash
pip3 install --break-system-packages -q gunicorn

# Create systemd service (see deploy.sh for full config)
systemctl start gunicorn
systemctl enable gunicorn
```

### Phase 5: Nginx Setup
```bash
# Configure Nginx (see deploy.sh for full config)
systemctl restart nginx
systemctl enable nginx
```

---

## Performance Monitoring

### Check Server Resources

```bash
# CPU and Memory usage
top

# Disk usage
df -h

# PostgreSQL connections
psql -U shamrock -d shamrock_fantasy -c "SELECT count(*) FROM pg_stat_activity;"

# Redis memory usage
redis-cli INFO memory
```

### Application Performance

Enable the built-in performance monitoring (if needed):

```bash
# In .env, set:
ENABLE_SILK_PROFILING=True

# Access at: http://shamrockfantasy.com/silk/
# (Be careful: this has a performance impact)
```

---

## Troubleshooting Common Issues

### "502 Bad Gateway" Error
- Check if Gunicorn is running: `systemctl status gunicorn`
- Check Gunicorn logs: `tail -f /opt/shamrock-fantasy/logs/gunicorn_error.log`
- Restart Gunicorn: `systemctl restart gunicorn`

### Application Won't Start
- Check .env file exists: `test -f /opt/shamrock-fantasy/.env && echo "✅ .env found" || echo "❌ .env missing"`
- Check database connection: `psql -U shamrock -d shamrock_fantasy -c "SELECT 1"`
- Check logs: `tail -50 /opt/shamrock-fantasy/logs/gunicorn_error.log`

### Static Files Not Loading
- Re-collect static files: `python3 manage.py collectstatic --noinput`
- Check permissions: `ls -la /opt/shamrock-fantasy/web/static/`
- Check Nginx config: `nginx -t`

### Database Connection Failed
- Verify PostgreSQL is running: `systemctl status postgresql`
- Check credentials in .env
- Test connection: `psql -U shamrock -d shamrock_fantasy`

---

## Helpful Commands

```bash
# SSH to server
ssh root@138.68.228.237

# View all services
systemctl list-units --type=service --state=running

# Monitor real-time logs
journalctl -u gunicorn -f

# Check open ports
netstat -tuln

# View SSL certificate expiry
certbot certificates

# Manual SSL renewal
certbot renew --dry-run

# Update system packages
apt-get update && apt-get upgrade -y
```

---

## Security Notes

1. **Change Database Password**: Current password in README is example-only
2. **Update SendGrid Key**: Never commit credentials to git
3. **Enable Firewall**: 
   ```bash
   ufw enable
   ufw allow 22/tcp
   ufw allow 80/tcp
   ufw allow 443/tcp
   ```
4. **Regular Backups**: Schedule daily database backups
5. **Monitor Logs**: Watch for suspicious activity

---

## Support & Questions

For issues or questions:
1. Check the logs (see "Monitoring" section)
2. Review Nginx error logs
3. Check Django debug mode (.env DEBUG=False, use Sentry for errors)
4. Consult DigitalOcean documentation for server-level issues

---

**Last Updated:** January 15, 2026  
**Deployment Status:** Ready for Production
