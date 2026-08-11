<#
.SYNOPSIS
    一键启动 Edict-Codex 看板服务与数据刷新循环。
.DESCRIPTION
    后台启动 dashboard/server.py（端口默认 7891）与 scripts/run_loop.ps1，
    分别记录 PID 到 data/server.pid 与 data/loop.pid，日志写到 data/logs/。
    用 stop.ps1 停止。
#>
param(
    [int]$Port = 7891
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $Root 'data'
$LogDir = Join-Path $DataDir 'logs'
$ServerPidFile = Join-Path $DataDir 'server.pid'
$LoopPidFile = Join-Path $DataDir 'loop.pid'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Test-Running($PidFile, $Name) {
    if (Test-Path $PidFile) {
        $old = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
            Write-Host "$Name already running (PID=$old)."
            return $true
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    return $false
}

$serverRunning = Test-Running $ServerPidFile 'Dashboard'
$loopRunning = Test-Running $LoopPidFile 'Refresh loop'

if (-not $serverRunning) {
    $serverLog = Join-Path $LogDir 'server.log'
    $server = Start-Process -FilePath 'python' `
        -ArgumentList @('dashboard/server.py', '--port', "$Port") `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput $serverLog -RedirectStandardError "$serverLog.err" `
        -PassThru
    $server.Id | Out-File $ServerPidFile
    Write-Host "Dashboard started (PID=$($server.Id)) -> http://127.0.0.1:$Port"
}

if (-not $loopRunning) {
    $loopLog = Join-Path $LogDir 'loop.log'
    $loop = Start-Process -FilePath 'powershell' `
        -ArgumentList @('-ExecutionPolicy', 'Bypass', '-File', 'scripts/run_loop.ps1') `
        -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput $loopLog -RedirectStandardError "$loopLog.err" `
        -PassThru
    $loop.Id | Out-File $LoopPidFile
    Write-Host "Refresh loop started (PID=$($loop.Id))."
}

Start-Sleep -Seconds 2
Write-Host 'Open http://127.0.0.1:7891 in your browser (or --Port to change).'
Write-Host 'Stop with: .\stop.ps1'
