# SSH Key Setup for Deployment

## Overview
This file documents the SSH key setup for deploying to shamrockfantasy.com production server.

## Key Information

**Server**: shamrockfantasy.com (138.68.228.237)  
**User**: cgnec (deployment user) / root (admin access)  
**SSH Key Location**: `~/.ssh/id_rsa`  
**SSH Config**: `~/.ssh/config` (pre-configured)

## Key Fingerprint
```
SHA256:wxtebAcOMOPXJUyQddM33Guy793jqoUd15HiaZASEMg
```

## Setup Status
✅ Public key authorized on server 2026-04-10  
✅ SSH authentication working  
✅ Saved to `/root/.ssh/authorized_keys` on production server

## Quick Deploy Commands

### Connect via SSH
```bash
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237
# or with config:
ssh shamrockfantasy.com
```

### Pull & Deploy
```bash
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "cd /opt/shamrock-fantasy && git pull origin main"
```

### Restart Services
```bash
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "systemctl restart gunicorn celery-worker celery-beat"
```

## Full Deployment Script
```bash
# 1. Pull latest code
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "cd /opt/shamrock-fantasy && git stash && git pull origin main"

# 2. Restart services
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "systemctl restart gunicorn celery-worker celery-beat"

# 3. Check status
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "systemctl status gunicorn celery-worker celery-beat --no-pager"
```

## Server Access Details

**Installation Path**: `/opt/shamrock-fantasy`  
**Virtual Environment**: `/opt/shamrock-fantasy/venv`  
**Gunicorn Socket**: `/opt/shamrock-fantasy/gunicorn.sock`  
**Logs**:
- Gunicorn: `/opt/shamrock-fantasy/logs/gunicorn_*.log`
- Celery: `journalctl -u celery-worker -f` / `journalctl -u celery-beat -f`

## Services Managed by Systemd
- `gunicorn` - Web application server (4 workers)
- `celery-worker` - Background task worker
- `celery-beat` - Scheduled task scheduler

## Last Deployment
**Date**: April 10, 2026 00:27 UTC  
**Commit**: a864875  
**Changes**: Code cleanup, documentation consolidation  
**Status**: ✅ All services running

## Troubleshooting

### SSH Permission Denied
If you get "Permission denied (publickey)", the public key may not be in `authorized_keys`:
```bash
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "cat ~/.ssh/authorized_keys"
```

Add your key if missing:
```bash
$pubkey = Get-Content $env:USERPROFILE\.ssh\id_rsa.pub
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

### Services Not Starting
Check logs:
```bash
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "journalctl -u gunicorn -n 50"
ssh -i $env:USERPROFILE\.ssh\id_rsa root@138.68.228.237 "journalctl -u celery-worker -n 50"
```

## Related Files
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Full deployment documentation
- [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) - Deployment history
