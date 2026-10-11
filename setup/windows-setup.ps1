# Awaaz - Windows side setup. Run in PowerShell:
#   powershell -ExecutionPolicy Bypass -File setup\windows-setup.ps1
# Safe to re-run: every step checks before it acts.

$ErrorActionPreference = 'Stop'
$Model = 'gemma4:e4b'
$Workspace = 'C:\AgentWork'

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step 'Checking this PC'
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$freeGB = [math]::Round((Get-PSDrive C).Free / 1GB)
Write-Host "RAM: $ramGB GB   Free on C: $freeGB GB"
if ($ramGB -lt 15) { $Model = 'qwen3:4b'; Write-Warning "Under 16 GB RAM: using the smaller model $Model." }
if ($freeGB -lt 40) { throw "Need at least 40 GB free on C: (have $freeGB GB). Free some space and re-run." }
$gpu = (Get-CimInstance Win32_VideoController | Where-Object Name -match 'NVIDIA').Name
if ($gpu) { Write-Host "NVIDIA GPU found: $gpu (models will run faster)" } else { Write-Host 'No NVIDIA GPU: models run on CPU.' }

Step 'Installing Ollama (official winget package)'
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host 'Ollama already installed.'
} else {
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

Step "Pulling model $Model (several GB, one time)"
ollama pull $Model
$reply = ollama run $Model 'Reply with exactly: LOCAL OK'
Write-Host "Model says: $reply"

Step "Creating the shared workspace $Workspace"
New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
if (-not (Test-Path "$Workspace\reminders.md")) {
    "# Reminders`n`n- $(Get-Date -Format 'yyyy-MM-dd') Try the daily brief" | Set-Content "$Workspace\reminders.md" -Encoding UTF8
}

Step 'Letting WSL reach Ollama on localhost (mirrored networking)'
$wslConfig = "$env:USERPROFILE\.wslconfig"
if (-not (Test-Path $wslConfig) -or -not (Select-String -Path $wslConfig -Pattern 'networkingMode' -Quiet)) {
    Add-Content $wslConfig "[wsl2]`nnetworkingMode=mirrored"
    Write-Host "Added mirrored networking to $wslConfig"
} else {
    Write-Host '.wslconfig already sets networkingMode; leaving it alone.'
}

Step 'Installing WSL2 + Ubuntu (needs admin; may ask for a restart)'
$wslReady = $false
try { wsl -l -q 2>$null | Out-Null; $wslReady = ($LASTEXITCODE -eq 0) } catch {}
if ($wslReady) {
    Write-Host 'WSL already installed.'
    wsl --shutdown
} else {
    try {
        Start-Process wsl -ArgumentList '--install' -Verb RunAs -Wait
    } catch {
        throw 'WSL install needs your OK: re-run this setup and click Yes on the Windows admin prompt (it can hide behind other windows; check the taskbar).'
    }
    Write-Host 'Restart Windows if asked, open Ubuntu once to create your user, then run setup/wsl-setup.sh inside it.'
}

Write-Host "`nDone. Next: in the Ubuntu shell run:  bash setup/wsl-setup.sh $Model" -ForegroundColor Green
