# Automated Waiver Processing Script
# Runs every Tuesday at 9:00 AM via Windows Task Scheduler

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Activate virtual environment and run the command
& "$ScriptDir\.venv\Scripts\python.exe" "$ScriptDir\manage.py" process_waivers

# Log the execution
$LogFile = "$ScriptDir\logs\waiver_processing.log"
$LogDir = Split-Path -Parent $LogFile
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LogFile -Value "$Timestamp - Waiver processing completed"
