# Pre-Production Deployment Guide

This guide covers all the pre-production configurations added to your Django application.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the project root:
```bash
cp .env.example .env
```

Edit `.env` with your production settings:
- `SECRET_KEY`: Generate a new secure key
- `DEBUG`: Set to `False` in production
- `ALLOWED_HOSTS`: Add your domain(s)
- API keys for SendGrid, Sentry, etc.

### 3. Database Migration
```bash
python manage.py migrate
```

### 4. Static Files
```bash
python manage.py collectstatic --noinput
```

---

## 📋 Features Added

### 1. **Sentry - Error Tracking** 🐛
- **What it does**: Captures all application errors and sends them to Sentry dashboard
- **Setup**: 
  1. Create account at https://sentry.io/
  2. Create a new project (Django)
  3. Copy DSN to `.env` file as `SENTRY_DSN`
- **Usage**: Errors are automatically captured; view on Sentry dashboard
- **Features**:
  - Real-time error notifications
  - User context and breadcrumbs
  - Performance monitoring (10% sample rate)
  - Session replay (if enabled)

### 2. **SendGrid Email** 📧
- **What it does**: Sends emails reliably through SendGrid
- **Setup**:
  1. Create account at https://sendgrid.com/
  2. Create API key in Settings
  3. Add to `.env`:
     ```
     SENDGRID_API_KEY=SG.your-key-here
     DEFAULT_FROM_EMAIL=noreply@yourdomain.com
     ```
- **Usage**:
  ```python
  from web.tasks import send_email_task
  send_email_task.delay(
      'Subject',
      'Message body',
      ['user@example.com'],
      html_message='<html>...</html>'
  )
  ```

### 3. **Argon2 Password Hashing** 🔐
- **What it does**: Uses modern Argon2 algorithm instead of default PBKDF2
- **Why it's better**: 
  - Resistant to GPU/ASIC attacks
  - Memory-hard hashing
  - Industry standard for password hashing
- **Automatic**: All new passwords use Argon2; old PBKDF2 hashes still work

### 4. **Django-Silk Performance Monitoring** 📊
- **What it does**: Real-time profiling and request monitoring
- **Access**: Visit `http://yourdomain.com/silk/`
- **Features**:
  - Request/response inspection
  - SQL query analysis
  - Python profiling
  - Database time breakdown
- **Configure**:
  ```python
  SILKY_PYTHON_PROFILER = True
  SILKY_IGNORE_PATHS = ['/admin/', '/silk/']
  ```

### 5. **Celery + Redis - Async Tasks** ⚡
- **What it does**: Runs long-running tasks in background
- **Setup**:
  1. Install Redis: 
     - Windows: Use Windows Subsystem for Linux or Redis MSI installer
     - Linux: `sudo apt-get install redis-server`
     - macOS: `brew install redis`
  
  2. Start Redis:
     ```bash
     redis-server
     ```
  
  3. Start Celery Worker:
     ```bash
     celery -A config worker -l info
     ```
  
  4. Start Celery Beat (scheduler):
     ```bash
     celery -A config beat -l info
     ```

- **Available Tasks** (see `web/tasks.py`):
  - `send_email_task`: Send emails asynchronously
  - `process_waivers`: Process waivers at scheduled time
  - `check_league_status`: Update league statuses
  - `cleanup_old_sessions`: Clean expired sessions
  - `send_league_notification`: Notify league members
  - `generate_performance_stats`: Generate stats asynchronously
  - `archive_old_leagues`: Archive completed leagues

- **Usage**:
  ```python
  from web.tasks import send_email_task
  send_email_task.delay('subject', 'message', ['email@example.com'])
  ```

### 6. **Caching with Redis** 💾
- **What it does**: Speed up page loads with in-memory caching
- **Configure**:
  ```python
  CACHES = {
      'default': {
          'BACKEND': 'django.core.cache.backends.redis.RedisCache',
          'LOCATION': 'redis://127.0.0.1:6379/1',
      }
  }
  ```
- **Usage**:
  ```python
  from django.core.cache import cache
  cache.set('key', value, 3600)  # 1 hour
  value = cache.get('key')
  ```

### 7. **Bug Reporting System** 🐞
- **What it does**: Users can report bugs with priority levels and tracking
- **Features**:
  - User-submitted bug reports
  - Priority levels (Low, Medium, High, Critical)
  - Status tracking (New, Acknowledged, In Progress, Resolved)
  - Admin notes and comments
  - Performance stats (SQL indexes on status/priority)

- **Models**:
  - `BugReport`: Main bug report model
    - Fields: title, description, priority, status, page_url, browser_info, error_message, admin_notes
    - Methods: `mark_resolved()`, automatic timestamps

- **Views** (in `web/bug_views.py`):
  - `report_bug`: Submit a new bug
  - `bug_list`: View all bugs with filtering
  - `bug_detail`: View bug details
  - `update_bug_status`: AJAX endpoint (staff only)
  - `add_bug_note`: AJAX for admin notes
  - `bug_report_api`: JavaScript API for client-side errors

- **Forms** (in `web/bug_forms.py`):
  - `BugReportForm`: For submitting bugs
  - `BugReportFilterForm`: For filtering bugs

---

## 🔧 Required Migrations

Generate migration:
```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 📝 URLs Configuration

Add to `web/urls.py`:
```python
from web.bug_views import (
    report_bug,
    bug_list,
    bug_detail,
    update_bug_status,
    add_bug_note,
    bug_report_api,
)

urlpatterns = [
    # ... existing patterns ...
    
    # Bug reporting
    path('bugs/report/', report_bug, name='report_bug'),
    path('bugs/', bug_list, name='bug_list'),
    path('bugs/<int:bug_id>/', bug_detail, name='bug_detail'),
    path('api/bugs/<int:bug_id>/status/', update_bug_status, name='update_bug_status'),
    path('api/bugs/<int:bug_id>/note/', add_bug_note, name='add_bug_note'),
    path('api/report-bug/', bug_report_api, name='bug_report_api'),
]
```

---

## 🚀 Production Deployment Steps

### 1. **Security Settings** (in `.env`)
```
DEBUG=False
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

### 2. **Run Migrations**
```bash
python manage.py migrate
```

### 3. **Collect Static Files**
```bash
python manage.py collectstatic --noinput
```

### 4. **Start Services**
On a production server (use systemd/supervisor):

**Gunicorn** (WSGI Server):
```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

**Celery Worker**:
```bash
celery -A config worker -l info --concurrency=4
```

**Celery Beat** (Task Scheduler):
```bash
celery -A config beat -l info
```

### 5. **Nginx Configuration** (Example)
```nginx
upstream gunicorn {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com;
    
    client_max_body_size 10M;
    
    location /static/ {
        alias /path/to/staticfiles/;
    }
    
    location /media/ {
        alias /path/to/media/;
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

### 6. **Systemd Service Files** (Linux)

Create `/etc/systemd/system/gunicorn.service`:
```ini
[Unit]
Description=Gunicorn Application Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/path/to/project
ExecStart=/path/to/venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000

[Install]
WantedBy=multi-user.target
```

---

## 🔍 Monitoring & Debugging

### View Sentry Errors
1. Go to https://sentry.io/
2. Log in to your organization
3. View real-time error tracking

### View Performance Stats (Django-Silk)
1. Visit: `http://yourdomain.com/silk/`
2. View request details, SQL queries, profiling

### Check Celery Tasks
```bash
# Monitor tasks in real-time
celery -A config events

# Purge tasks (use with caution)
celery -A config purge
```

### View Logs
```bash
# Django logs
tail -f logs/django.log

# Celery logs
tail -f logs/celery.log
```

---

## 📊 Performance Optimization Tips

1. **Enable Caching**: Cache frequently accessed data with Redis
2. **Use Celery for Long Tasks**: Move heavy operations to background
3. **Database Indexes**: Already added to BugReport model
4. **MinifyJS/CSS**: Use WhiteNoise which handles compression
5. **CDN**: Serve static files from CDN for faster delivery
6. **Database Optimization**: 
   - Use `select_related()` for ForeignKeys
   - Use `prefetch_related()` for reverse relations
   - Profile with `django-silk`

---

## ⚠️ Important Notes

- **Redis**: Required for Celery, Caching, and Sessions
- **PostgreSQL**: Ensure database is accessible from server
- **SendGrid Account**: Free tier available (100 emails/day)
- **Sentry Account**: Free tier available (limited events)
- **Update ALLOWED_HOSTS**: Critical for production security
- **Change SECRET_KEY**: Generate new key for production

---

## 🆘 Troubleshooting

### Celery tasks not running?
- Check Redis is running: `redis-cli ping`
- Check Celery worker is running
- Check logs for errors

### Emails not sending?
- Verify SendGrid API key
- Check email format is valid
- Look at Sentry for error details

### Performance issues?
- Use Django-Silk to profile requests
- Check database queries
- Enable caching
- Increase Celery workers

### Database connection errors?
- Verify database credentials in `.env`
- Check PostgreSQL is running
- Test connection: `psql -h localhost -U user -d dbname`

---

## 📚 Additional Resources

- [Django Deployment Checklist](https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/)
- [Sentry Documentation](https://docs.sentry.io/)
- [Celery Documentation](https://docs.celeryproject.org/)
- [Django-Silk Documentation](https://silk.readthedocs.io/)
- [SendGrid Python Documentation](https://sendgrid.com/docs/for-developers/sending-email/django/)

---

**Last Updated**: January 14, 2026
