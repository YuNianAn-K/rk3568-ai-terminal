param([switch]$Check, [switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$monitorRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$monitorLocal = Join-Path $monitorRoot 'local\ecs-monitor'
$monitorRuntime = Get-Content -LiteralPath (Join-Path $monitorLocal 'runtime.json') -Raw | ConvertFrom-Json
$monitorScript = Join-Path $PSScriptRoot 'monitor.py'
if ($Check) {
    if (!(Test-Path -LiteralPath $monitorRuntime.python) -or !(Test-Path -LiteralPath $monitorScript)) { throw 'Monitor runtime missing' }
    $env:PYTHONPATH = Join-Path $monitorLocal 'deps'
    & $monitorRuntime.python -c 'import aliyunsdkcore; print(aliyunsdkcore.__version__)'
    exit $LASTEXITCODE
}
# Reopen only a process owned by this exact entry point, never take over a port.
$monitorSessionFile = Join-Path $monitorLocal 'session.json'
if (Test-Path -LiteralPath $monitorSessionFile) {
    $monitorSession = Get-Content -LiteralPath $monitorSessionFile -Raw | ConvertFrom-Json
    $monitorExisting = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$monitorSession.pid)
    if ($monitorExisting -and $monitorExisting.CommandLine -and $monitorExisting.CommandLine.Contains($monitorScript)) {
        if (!$NoOpen) { Start-Process -FilePath $monitorRuntime.edge -ArgumentList ('--app=' + $monitorSession.url) -WindowStyle Hidden }
        exit 0
    }
}
$monitorInfo = New-Object Diagnostics.ProcessStartInfo
$monitorInfo.FileName = $monitorRuntime.python
$monitorInfo.Arguments = '"' + $monitorScript + '"' + $(if ($NoOpen) { ' --no-open' } else { '' })
$monitorInfo.WorkingDirectory = $monitorRoot
$monitorInfo.UseShellExecute = $false
$monitorInfo.CreateNoWindow = $true
$monitorInfo.EnvironmentVariables['PYTHONPATH'] = Join-Path $monitorLocal 'deps'
$monitorInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'
$monitorProcess = New-Object Diagnostics.Process
$monitorProcess.StartInfo = $monitorInfo
$null = $monitorProcess.Start()
# Startup exit is visible through the normal error dialog; no credentials logged.
if ($monitorProcess.WaitForExit(1200)) { throw 'Monitor exited. Check port 8796 and local configuration.' }
