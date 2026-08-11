<#
.SYNOPSIS
    停止 start.ps1 启动的看板服务与刷新循环。
#>
$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $Root 'data'

foreach ($pair in @(
        @('server.pid', 'Dashboard'),
        @('loop.pid', 'Refresh loop')
    )) {
    $pidFile = Join-Path $DataDir $pair[0]
    if (Test-Path $pidFile) {
        $pidVal = Get-Content $pidFile
        if ($pidVal) {
            Stop-Process -Id $pidVal -Force
            Write-Host "$($pair[1]) stopped (PID=$pidVal)."
        }
        Remove-Item $pidFile -Force
    }
}

Write-Host 'All services stopped.'
