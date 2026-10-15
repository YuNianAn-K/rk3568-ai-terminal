param([switch]$Check)
$ErrorActionPreference = 'Stop'
$mqttRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$mqttLocal = Join-Path $mqttRoot 'local\mqtt\manual'
$mqttRuntime = Get-Content -LiteralPath (Join-Path $mqttLocal 'runtime.json') -Raw | ConvertFrom-Json
if ($Check) { & $mqttRuntime.python (Join-Path $PSScriptRoot 'session.py') --check; exit $LASTEXITCODE }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$script:mqttWorker = $null
$script:mqttStateFile = $null
$mqttForm = New-Object Windows.Forms.Form
$mqttForm.Text = 'RK3568 · MQTT 控制台'
$mqttForm.ClientSize = New-Object Drawing.Size(620,360)
$mqttForm.StartPosition = 'CenterScreen'
$mqttForm.FormBorderStyle = 'FixedDialog'
$mqttForm.MaximizeBox = $false
$mqttHint = New-Object Windows.Forms.Label
$mqttHint.Text = "先确认板端当前 IP，再输入 device-rk3568-01 的 MQTT 密码。`r`n密码不保存。关闭此窗口会停止本次服务；单次最长 8 小时。"
$mqttHint.SetBounds(20,20,580,50)
$mqttForm.Controls.Add($mqttHint)
$mqttIpLabel = New-Object Windows.Forms.Label
$mqttIpLabel.Text = '板端当前 IPv4'
$mqttIpLabel.SetBounds(20,85,185,25)
$mqttForm.Controls.Add($mqttIpLabel)
$mqttIp = New-Object Windows.Forms.TextBox
$mqttIp.SetBounds(210,82,380,27)
$mqttForm.Controls.Add($mqttIp)
$mqttPasswordLabel = New-Object Windows.Forms.Label
$mqttPasswordLabel.Text = '设备 MQTT 密码'
$mqttPasswordLabel.SetBounds(20,128,185,25)
$mqttForm.Controls.Add($mqttPasswordLabel)
$mqttPassword = New-Object Windows.Forms.TextBox
$mqttPassword.UseSystemPasswordChar = $true
$mqttPassword.SetBounds(210,125,380,27)
$mqttForm.Controls.Add($mqttPassword)
$mqttStart = New-Object Windows.Forms.Button
$mqttStart.Text = '启动'
$mqttStart.SetBounds(210,170,180,38)
$mqttForm.Controls.Add($mqttStart)
$mqttStop = New-Object Windows.Forms.Button
$mqttStop.Text = '停止'
$mqttStop.Enabled = $false
$mqttStop.SetBounds(410,170,180,38)
$mqttForm.Controls.Add($mqttStop)
$mqttStatus = New-Object Windows.Forms.Label
$mqttStatus.Text = '尚未启动。手机连接时使用 phone-owner 的密码。'
$mqttStatus.SetBounds(20,225,580,50)
$mqttForm.Controls.Add($mqttStatus)
$mqttUrl = New-Object Windows.Forms.TextBox
$mqttUrl.ReadOnly = $true
$mqttUrl.SetBounds(20,290,570,30)
$mqttForm.Controls.Add($mqttUrl)
function Stop-MqttSession {
    if ($script:mqttWorker -and !$script:mqttWorker.HasExited) {
        try { $script:mqttWorker.StandardInput.WriteLine('{"action":"stop"}'); $script:mqttWorker.StandardInput.Close() } catch { }
    }
    $mqttStop.Enabled = $false
}
$mqttStart.Add_Click({
    if (!$mqttIp.Text.Trim() -or !$mqttPassword.Text) { $mqttStatus.Text='请填写板端当前 IP 和设备 MQTT 密码。'; return }
    if ($script:mqttWorker -and !$script:mqttWorker.HasExited) { return }
    try {
        $mqttSessionId = [Guid]::NewGuid().ToString('N')
        $script:mqttStateFile = Join-Path $mqttLocal ($mqttSessionId + '.json')
        $mqttInfo = New-Object Diagnostics.ProcessStartInfo
        $mqttInfo.FileName = $mqttRuntime.python
        $mqttInfo.Arguments = '"' + (Join-Path $PSScriptRoot 'session.py') + '" --session ' + $mqttSessionId
        $mqttInfo.WorkingDirectory = $mqttRoot
        $mqttInfo.UseShellExecute = $false
        $mqttInfo.CreateNoWindow = $true
        $mqttInfo.RedirectStandardInput = $true
        $mqttInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE']='1'
        $script:mqttWorker = New-Object Diagnostics.Process
        $script:mqttWorker.StartInfo = $mqttInfo
        $null = $script:mqttWorker.Start()
        $mqttPayload = @{ip=$mqttIp.Text.Trim();password=$mqttPassword.Text} | ConvertTo-Json -Compress
        $script:mqttWorker.StandardInput.WriteLine($mqttPayload)
        $mqttPayload = $null; $mqttPassword.Clear()
        $mqttStart.Enabled=$false; $mqttStop.Enabled=$true; $mqttIp.Enabled=$false
        $mqttUrl.Clear(); $mqttStatus.Text='正在启动，请稍候。'
    } catch { $mqttPassword.Clear(); Stop-MqttSession; $mqttStatus.Text='启动失败，请检查本机运行路径。密码未记录。' }
})
$mqttStop.Add_Click({Stop-MqttSession; $mqttStatus.Text='正在停止，请稍候。'})
$mqttTimer = New-Object Windows.Forms.Timer
$mqttTimer.Interval = 500
$mqttTimer.Add_Tick({
    if ($script:mqttStateFile -and (Test-Path -LiteralPath $script:mqttStateFile)) {
        try {
            $mqttState = Get-Content -LiteralPath $script:mqttStateFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $mqttStatus.Text=$mqttState.message
            if ($mqttState.phone_url) { $mqttUrl.Text=$mqttState.phone_url }
        } catch { }
    }
    if ($script:mqttWorker -and $script:mqttWorker.HasExited) {
        $mqttStart.Enabled=$true; $mqttStop.Enabled=$false; $mqttIp.Enabled=$true
        if (!(Test-Path -LiteralPath $script:mqttStateFile)) { $mqttStatus.Text='启动进程已退出，请检查本机配置。' }
    }
})
$mqttForm.Add_FormClosing({Stop-MqttSession; if ($script:mqttWorker) {$null=$script:mqttWorker.WaitForExit(15000)}})
$mqttTimer.Start()
try { $null=$mqttForm.ShowDialog() } finally { Stop-MqttSession; $mqttTimer.Stop(); $mqttTimer.Dispose(); $mqttForm.Dispose() }
