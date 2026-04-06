# Deployment Guide - SSH & Production Access

## Server Information

**Host**: shamrockfantasy.com / 138.68.228.237  
**User**: cgnec (SSH) / root (current access)  
**SSH Key**: `~/.ssh/id_rsa`  
**SSH Config**: `~/.ssh/config` (pre-configured)

## Quick Deployment Steps

1. **SSH into server**:
   ```bash
   ssh shamrockfantasy.com
   # or
   ssh cgnec@138.68.228.237
   ```

2. **Pull latest code**:
   ```bash
   cd /opt/shamrock-fantasy
   git pull origin main
   ```

3. **Restart services**:
   ```bash
   systemctl restart gunicorn
   systemctl restart celery-worker celery-beat
   ```

## Systemd Services

| Service | Command | Purpose |
|---------|---------|---------|
| Gunicorn | `systemctl restart gunicorn` | Web server |
| Celery Worker | `systemctl restart celery-worker` | Background tasks |
| Celery Beat | `systemctl restart celery-beat` | Scheduled tasks |

## Check Service Status

```bash
systemctl status gunicorn celery-worker celery-beat
```

## Recent Deployments

### 2026-04-06 - Standings View Fix
- **Commit**: `887247f`
- **Issue**: ValueError in standings - "too many values to unpack"
- **Fix**: Handle playoff matchups (4-element tuples) separately from regular season matchups (2-element tuples)
- **Deployment**: ✅ Complete
  - Code pulled
  - Gunicorn restarted
  - Celery services restarted

## Logs

```bash
# Gunicorn logs
journalctl -u gunicorn -f

# Celery logs
journalctl -u celery-worker -f
journalctl -u celery-beat -f
```

## Rollback

If issues occur:
```bash
cd /opt/shamrock-fantasy
git log --oneline  # Find commit to rollback to
git checkout <commit-hash>
systemctl restart gunicorn celery-worker celery-beat
```

## Database

PostgreSQL is running on the server. Access Django shell:
```bash
cd /opt/shamrock-fantasy
source venv/bin/activate
python manage.py shell
```

## Cache & Redis

```bash
redis-cli
> INFO  # Check Redis status
> FLUSHALL  # Clear cache if needed
```
