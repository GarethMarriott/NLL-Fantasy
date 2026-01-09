# NLL Fantasy - Automated Waiver Processing

## Setup Instructions

### Automatic Setup (Recommended)

1. **Run the setup script as Administrator:**
   - Right-click PowerShell and select "Run as Administrator"
   - Navigate to the project directory:
     ```powershell
     cd "C:\Users\cgnec\OneDrive\Documents\Fantasy\NLL-Fantasy-1"
     ```
   - Run the setup script:
     ```powershell
     .\setup_waiver_scheduler.ps1
     ```

2. **Verify the task was created:**
   - Press `Win + R`, type `taskschd.msc` and press Enter
   - Look for "NLL Fantasy - Process Waivers" in the Task Scheduler Library
   - Verify it's set to run every Tuesday at 9:00 AM

### Manual Testing

To test the waiver processing manually before the scheduled time:

```powershell
python manage.py process_waivers
```

Or run the PowerShell script directly:

```powershell
.\process_waivers.ps1
```

### Logs

All waiver processing activity is logged to:
```
C:\Users\cgnec\OneDrive\Documents\Fantasy\NLL-Fantasy-1\logs\waiver_processing.log
```

### Manual Setup (Alternative)

If you prefer to set up the scheduled task manually:

1. Open Task Scheduler (`Win + R` → `taskschd.msc`)
2. Click "Create Task" (not Basic Task)
3. **General tab:**
   - Name: `NLL Fantasy - Process Waivers`
   - Description: `Automatically process waiver claims every Tuesday at 9:00 AM`
   - Select "Run whether user is logged on or not"
   - Check "Run with highest privileges"

4. **Triggers tab:**
   - Click "New"
   - Begin the task: "On a schedule"
   - Settings: Weekly
   - Days: Tuesday
   - Start time: 9:00:00 AM
   - Click OK

5. **Actions tab:**
   - Click "New"
   - Action: "Start a program"
   - Program/script: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\cgnec\OneDrive\Documents\Fantasy\NLL-Fantasy-1\process_waivers.ps1"`
   - Click OK

6. **Conditions tab:**
   - Uncheck "Start the task only if the computer is on AC power"
   - Check "Start the task only if the following network connection is available: Any connection"

7. **Settings tab:**
   - Check "Allow task to be run on demand"
   - Check "Run task as soon as possible after a scheduled start is missed"
   - If task fails, restart every: 1 minute (up to 3 times)

8. Click OK to save

### Troubleshooting

**Task doesn't run:**
- Check Windows Event Viewer for Task Scheduler errors
- Verify the Python path in `process_waivers.ps1` is correct
- Ensure the task is enabled in Task Scheduler

**Waiver processing fails:**
- Check the log file at `logs\waiver_processing.log`
- Run manually to see error output: `python manage.py process_waivers`
- Verify database migrations are up to date: `python manage.py migrate`

### Disable Automatic Processing

To stop automatic waiver processing:

1. Open Task Scheduler
2. Find "NLL Fantasy - Process Waivers"
3. Right-click → Disable (or Delete)

Or run in PowerShell:
```powershell
Unregister-ScheduledTask -TaskName "NLL Fantasy - Process Waivers" -Confirm:$false
```
