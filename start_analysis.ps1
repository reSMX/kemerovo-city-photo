param([switch]$RetryFailed)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Python environment missing: .venv\Scripts\python.exe' }
if (-not (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)) {
    & (Join-Path $PSScriptRoot 'start_ollama_safe.ps1')
}
$taskReady = $false
$taskDeadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $taskDeadline) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
        $taskReady = $true
        break
    } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $taskReady) { throw 'Ollama did not become ready on localhost:11434' }
$analysisArguments = @('-u', (Join-Path $PSScriptRoot 'run_background.py'), '--config', (Join-Path $PSScriptRoot 'config.full.yaml'), '--workspace', (Join-Path $PSScriptRoot 'work'), '--output', (Join-Path $PSScriptRoot 'output'), '--no-memory-guard')
if ($RetryFailed) { $analysisArguments += @('--retry-failed-only', '--photo-deadline-seconds', '180') }
& $taskPython @analysisArguments
exit $LASTEXITCODE
