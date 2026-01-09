# Setup Windows Task Scheduler for Automatic Waiver Processing
# Run this script as Administrator to create the scheduled task

$TaskName = "NLL Fantasy - Process Waivers"
$ScriptPath = Join-Path $PSScriptRoot "process_waivers.ps1"
$PythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$ManagePyPath = Join-Path $PSScriptRoot "manage.py"

# Create the scheduled task action
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$ScriptPath`""

# Create the trigger - Every Tuesday at 9:00 AM
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday -At 9:00AM

# Set the task to run whether user is logged in or not
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U -RunLevel Highest

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Register the task
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "Automatically process waiver claims for NLL Fantasy league every Tuesday at 9:00 AM" `
        -Force

    Write-Host "Task '$TaskName' created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "The task will run every Tuesday at 9:00 AM to process waiver claims." -ForegroundColor Cyan
    Write-Host "Logs will be saved to: $PSScriptRoot\logs\waiver_processing.log" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To manage the task:" -ForegroundColor Yellow
    Write-Host "  - Open Task Scheduler (taskschd.msc)" -ForegroundColor Yellow
    Write-Host "  - Look for '$TaskName' in the Task Scheduler Library" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To test manually:" -ForegroundColor Yellow
    Write-Host "  python manage.py process_waivers" -ForegroundColor Yellow
}
catch {
    Write-Host "Error creating scheduled task: $_" -ForegroundColor Red
    Write-Host "Make sure to run this script as Administrator" -ForegroundColor Yellow
}
