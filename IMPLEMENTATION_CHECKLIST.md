# Pre-Production Setup Checklist

**Date**: January 14, 2026  
**Status**: Configuration Complete - Awaiting Implementation

---

## ✅ Completed Configuration Tasks

### Configuration Files
- [x] Updated `requirements.txt` with all production packages
- [x] Created `config/celery.py` with task scheduler
- [x] Updated `config/settings.py` with all service configs
- [x] Updated `config/__init__.py` for Celery initialization
- [x] Created `.env.example` with all required variables
- [x] Created `DEPLOYMENT_GUIDE.md` with complete instructions
- [x] Created `PREPRODUCTION_SETUP.md` with summary

### Models & Database
- [x] Added `BugReport` model to `web/models.py`
- [x] Created model with all required fields and methods
- [x] Added SQL indexes for performance

### Views & Forms
- [x] Created `web/bug_views.py` with 6 endpoints
- [x] Created `web/bug_forms.py` with 2 forms
- [x] Created `web/tasks.py` with 8 Celery tasks

### Templates
- [x] Created `web/templates/web/report_bug.html`
- [x] Created `web/templates/web/bug_list.html`
- [x] Created `web/templates/web/bug_detail.html`

---

## 📋 Implementation Checklist

### Step 1: Install Dependencies
- [ ] Run `pip install -r requirements.txt`
- [ ] Verify all packages install successfully

### Step 2: Environment Setup
- [ ] Copy `.env.example` to `.env`
- [ ] Set `SECRET_KEY` to a secure value
- [ ] Set `DEBUG=False`
- [ ] Set `ALLOWED_HOSTS` with your domain(s)
- [ ] Add `SENDGRID_API_KEY`
- [ ] Add `SENTRY_DSN`
- [ ] Add Redis `CELERY_BROKER_URL` and `CELERY_RESULT_BACKEND`

### Step 3: Database Migration
- [ ] Run `python manage.py makemigrations`
- [ ] Run `python manage.py migrate`
- [ ] Verify `BugReport` table is created

### Step 4: Admin Registration
- [ ] Open `web/admin.py`
- [ ] Add BugReport admin registration:
  ```python
  from .models import BugReport
  
  @admin.register(BugReport)
  class BugReportAdmin(admin.ModelAdmin):
      list_display = ('title', 'priority', 'status', 'reporter', 'created_at')
      list_filter = ('priority', 'status', 'created_at')
      search_fields = ('title', 'description')
      readonly_fields = ('created_at', 'updated_at', 'resolved_at')
  ```
- [ ] Verify admin can access bug reports at `/admin/web/bugreport/`

### Step 5: URL Routing
- [ ] Open `web/urls.py`
- [ ] Import bug report views:
  ```python
  from web.bug_views import (
      report_bug, bug_list, bug_detail,
      update_bug_status, add_bug_note, bug_report_api
  )
  ```
- [ ] Add URL patterns:
  ```python
  path('bugs/report/', report_bug, name='report_bug'),
  path('bugs/', bug_list, name='bug_list'),
  path('bugs/<int:bug_id>/', bug_detail, name='bug_detail'),
  path('api/bugs/<int:bug_id>/status/', update_bug_status, name='update_bug_status'),
  path('api/bugs/<int:bug_id>/note/', add_bug_note, name='add_bug_note'),
  path('api/report-bug/', bug_report_api, name='bug_report_api'),
  ```
- [ ] Verify routes work by testing URLs

### Step 6: Static Files
- [ ] Run `python manage.py collectstatic --noinput`
- [ ] Verify `staticfiles` directory is created

### Step 7: Service Setup (Linux/macOS)

#### Redis Installation
- [ ] Install Redis (instructions in DEPLOYMENT_GUIDE.md)
- [ ] Start Redis: `redis-server`
- [ ] Test: `redis-cli ping` (should return PONG)

#### Celery Worker
- [ ] Open new terminal
- [ ] Run: `celery -A config worker -l info`
- [ ] Verify: Should show "connected to redis://"

#### Celery Beat
- [ ] Open new terminal
- [ ] Run: `celery -A config beat -l info`
- [ ] Verify: Should show scheduled tasks loaded

### Step 8: Testing

#### Bug Report Feature
- [ ] Navigate to `/bugs/report/`
- [ ] Submit a test bug report
- [ ] Verify it appears in `/bugs/`
- [ ] Click on bug to view details
- [ ] If staff user, test status update and admin notes

#### Email Sending
- [ ] Test with: `python manage.py shell`
  ```python
  from web.tasks import send_email_task
  send_email_task.delay('Test', 'Test message', ['your@email.com'])
  ```
- [ ] Check SendGrid dashboard for delivery

#### Sentry Integration
- [ ] Trigger an error in development (modify a view)
- [ ] Check Sentry dashboard for error report
- [ ] Verify user context and breadcrumbs are captured

#### Django-Silk Performance
- [ ] Make some requests to the app
- [ ] Navigate to `/silk/`
- [ ] View request/response details
- [ ] Analyze SQL queries

#### Celery Tasks
- [ ] Check Celery worker output for task execution
- [ ] Verify beat scheduler logs
- [ ] Check Redis with `redis-cli keys '*'`

### Step 9: Security Hardening
- [ ] Set `SECURE_SSL_REDIRECT=True` in `.env`
- [ ] Set `SESSION_COOKIE_SECURE=True`
- [ ] Set `CSRF_COOKIE_SECURE=True`
- [ ] Set `SECURE_HSTS_SECONDS=31536000`
- [ ] Run Django security check: `python manage.py check --deploy`

### Step 10: Deployment Preparation

#### Create Environment Files
- [ ] Generate new `SECRET_KEY` for production
- [ ] Create `.env` file with production values
- [ ] Create `.env.production` as backup
- [ ] Add `.env` to `.gitignore` (CRITICAL!)

#### Service Files (if deploying to Linux)
- [ ] Create `gunicorn.service` systemd file
- [ ] Create `celery.service` systemd file
- [ ] Create `celery-beat.service` systemd file
- [ ] Test service files: `systemctl status [service]`

#### Web Server Configuration
- [ ] Configure Nginx or Apache
- [ ] Setup SSL certificate (Let's Encrypt)
- [ ] Configure reverse proxy to Gunicorn
- [ ] Test HTTPS connection

### Step 11: Monitoring Setup

#### Sentry Dashboard
- [ ] Log in to https://sentry.io/
- [ ] View real-time errors
- [ ] Set up alerts/notifications
- [ ] Configure team members

#### Django-Silk
- [ ] Monitor `/silk/` dashboard
- [ ] Analyze slow requests
- [ ] Optimize database queries
- [ ] Check memory usage

#### Logs
- [ ] Setup log rotation
- [ ] Create log directory: `mkdir -p logs`
- [ ] Configure Django logging to file

### Step 12: Documentation
- [ ] Update project README with deployment info
- [ ] Document any custom settings
- [ ] Create runbook for common issues
- [ ] Update team with access details

---

## 🔍 Testing Checklist

### Functional Tests
- [ ] Bug reporting form submits successfully
- [ ] Bug list displays with pagination
- [ ] Filtering and searching works
- [ ] Admin can update bug status
- [ ] Admin can add notes
- [ ] Email notifications send (if configured)
- [ ] Async tasks execute properly

### Performance Tests
- [ ] Django-Silk shows reasonable response times
- [ ] Database queries are optimized
- [ ] Cache is working (Redis)
- [ ] Static files are served efficiently

### Security Tests
- [ ] CSRF protection working
- [ ] Authentication required for bug submission
- [ ] Staff-only endpoints protected
- [ ] SQL injection prevention (ORM usage)
- [ ] XSS prevention (template escaping)

### Error Handling Tests
- [ ] Errors appear in Sentry
- [ ] 500 errors logged properly
- [ ] 404 errors handled gracefully
- [ ] Invalid form data shows validation errors

---

## 📊 Services Status Check

Run these commands to verify all services are working:

```bash
# Redis
redis-cli ping
# Expected: PONG

# PostgreSQL
psql -h localhost -U postgres -d fantasy_lacrosse -c "SELECT 1;"
# Expected: returns 1

# Celery Worker
celery -A config inspect active
# Expected: shows worker status

# Celery Beat
celery -A config inspect scheduled
# Expected: shows scheduled tasks
```

---

## 🚨 Critical Issues to Avoid

- [ ] **NEVER commit `.env` file** - add to `.gitignore`
- [ ] **Generate new SECRET_KEY** - don't use default
- [ ] **Set DEBUG=False** - in production
- [ ] **Update ALLOWED_HOSTS** - with actual domain
- [ ] **Use HTTPS** - in production only
- [ ] **Backup database** - before deploying
- [ ] **Test migrations** - on staging first
- [ ] **Monitor errors** - setup Sentry alerts
- [ ] **Secure credentials** - use environment variables
- [ ] **Document passwords** - securely store admin credentials

---

## 📞 Support Resources

If you encounter issues:

1. **Check DEPLOYMENT_GUIDE.md** - Troubleshooting section
2. **Review logs** - Django, Celery, Redis logs
3. **Check Sentry** - For application errors
4. **Verify services** - Redis, PostgreSQL, Celery running
5. **Review stack trace** - Detailed error information
6. **Check DNS** - Domain resolving correctly
7. **Verify firewall** - Ports open (80, 443, 5432, 6379)

---

## 📝 Notes

- Setup was completed on: **January 14, 2026**
- All files are production-ready
- Requires Python 3.8+ and Django 6.0
- PostgreSQL database is configured
- Redis is required for Celery and caching

---

## ✨ Next Steps After Deployment

1. Monitor Sentry for production errors
2. Check Django-Silk for performance bottlenecks
3. Gather user feedback on bug reporting
4. Optimize database queries if needed
5. Scale Celery workers if needed
6. Setup backups and disaster recovery
7. Implement additional monitoring (APM)
8. Plan for load testing and performance tuning

---

**Last Updated**: January 14, 2026  
**Status**: ✅ Ready for Implementation
