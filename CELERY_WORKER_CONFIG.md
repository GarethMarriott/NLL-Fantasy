# Celery Worker Memory Configuration

## Issue Fixed

Your Celery worker process was being **killed with SIGKILL (signal 9)** due to consuming too much memory while processing NLL stats. The `fetch_nll_stats_task` loads large amounts of data in memory without cleaning up, causing the process to grow unbounded.

## Solution Overview

Added two critical configurations to prevent memory exhaustion:

### 1. **Worker Memory Restart** (Automatic Cleanup)
- Workers now restart after consuming ~256MB of memory
- This prevents memory leaks from accumulating
- Configuration: `CELERY_WORKER_MAX_MEMORY_PER_CHILD = 256 * 1024`

### 2. **Sentry Noise Filtering** 
- Filters out Redis heartbeat messages and informational logs
- Prevents Sentry from being flooded with low-value events
- Identifies real errors vs. operational noise

## Deployment Steps

### On Your Production Server (138.68.228.237)

1. **Pull the latest code**:
   ```bash
   cd /opt/shamrock-fantasy
   git pull origin main
   ```

2. **Verify Settings**:
   ```bash
   # Check that settings.py has the new Celery config
   grep "CELERY_WORKER_MAX_MEMORY_PER_CHILD" config/settings.py
   ```

3. **Restart Celery Services**:
   ```bash
   systemctl restart celery-worker celery-beat
   ```

4. **Verify Restart**:
   ```bash
   systemctl status celery-worker celery-beat
   ```

5. **Monitor Logs**:
   ```bash
   # Watch for worker restarts (should happen after task completion)
   journalctl -u celery-worker -f
   ```

## How It Works

### Memory Limit Behavior

**Before**:
```
Worker starts → Fetches large JSON files → Loads all data in memory → 
Process grows to 500MB+ → System kills with SIGKILL → ❌ Error in Sentry
```

**After**:
```
Worker starts → Fetches JSON files → Processes task → Process reaches 256MB limit → 
Worker automatically restarts → Clean process for next task → ✅ Task completes
```

### Sentry Filtering

**Before**: Sentry floods with 100+ Redis heartbeat messages
```
- PUBLISH '/0.celeryev/worker.heartbeat' [Filtered]
- SET 'unacked_mutex' [Filtered]
- ZREVRANGEBYSCORE 'unacked_index' [Filtered]
- ... (repeated 50+ times)
```

**After**: Only real errors and warnings are captured
- Database errors
- Application exceptions
- Timeout errors
- etc.

## Configuration Details

### File: `config/settings.py`

```python
# Memory management: Restart worker after processing ~256MB to prevent memory leaks
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 256 * 1024  # 256 MB
```

This tells Celery to:
1. Monitor memory usage of each worker process
2. Once a worker exceeds 256MB of memory
3. Gracefully finish its current task
4. Restart the worker process
5. Continue processing new tasks

### Sentry Filter Function

The `before_send_sentry()` function:
- Filters out INFO-level logs (operational noise)
- Removes Redis/Celery heartbeat breadcrumbs
- Only sends WARNING and ERROR level events
- Keeps the signal-to-noise ratio high in Sentry

## Monitoring

### Check Worker Memory Usage

```bash
# SSH into server
ssh shamrockfantasy.com

# Monitor Celery worker processes
ps aux | grep celery

# Check memory of each worker
ps -eo pid,comm,rss,vsz | grep celery-worker

# Look for 'RSS' (resident set size) in KB
# Should see workers restart when they hit ~260MB
```

### Sentry Dashboard

1. Go to sentry.io dashboard
2. Filter events to show WARNING and above
3. You should see:
   - ✅ Fewer redis/celery heartbeat entries
   - ✅ Only real application errors
   - ✅ Cleaner error logs

## Expected Task Duration

The `fetch_nll_stats_task` should complete in:
- **Small fetches** (single week): 2-5 minutes
- **Full season refresh**: 10-15 minutes
- **Worker restart**: ~automatic, happens between tasks

If tasks are taking >15 minutes, the task may need further optimization.

## Testing

To verify the configuration works:

1. **Test memory restart**:
   ```bash
   # SSH into server
   ssh shamrockfantasy.com
   
   # Trigger the fetch_nll_stats task manually
   cd /opt/shamrock-fantasy
   source venv/bin/activate
   python manage.py shell
   
   # In Django shell:
   from web.tasks import fetch_nll_stats_task
   fetch_nll_stats_task.delay()  # Queue the task
   
   # Leave shell and monitor:
   exit()
   journalctl -u celery-worker -f  # Watch for restarts
   ps aux | grep celery  # Check processes
   ```

2. **Check Sentry**:
   - Go to sentry.io
   - Verify no Redis heartbeat spam
   - Only see real errors

## Additional Improvements (Optional)

### Further Optimize `fetch_nll_stats` Command

If workers still restart frequently, the command itself could be optimized to use less memory:

1. **Stream JSON processing** instead of loading all at once
2. **Batch database writes** (bulk_create instead of update_or_create in loops)
3. **Chunk processing by game** instead of by season
4. **Explicit garbage collection** between batches

### Increase Memory Limit (If Needed)

If tasks need more time to complete:
```python
# In config/settings.py
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 512 * 1024  # 512 MB (more aggressive restart)
```

**Trade-offs**:
- Higher limit = longer task execution but fewer restarts
- Lower limit = more restarts but guaranteed memory cleanup

Current setting (256MB) is recommended for balance.

## Rollback

If issues occur:

```bash
cd /opt/shamrock-fantasy
git log --oneline  # Find previous working commit
git checkout <commit-hash>
systemctl restart celery-worker celery-beat
```

## Support

For issues:
1. Check logs: `journalctl -u celery-worker -f`
2. Monitor Sentry for new errors
3. Check process memory: `ps -eo pid,comm,rss,vsz | grep celery`

