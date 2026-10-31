param(
    [Parameter(Mandatory=$true)][string]$ExpectedStartedAt,
    [ValidateRange(1,60)][int]$PollSeconds = 10
)
$ErrorActionPreference = 'Stop'
$taskWork = Join-Path $PSScriptRoot 'work'
$taskAnalysisPath = Join-Path $taskWork 'analysis_status.json'
$taskSchedulePath = Join-Path $taskWork 'retry_schedule.json'
$taskCancelPath = Join-Path $taskWork 'cancel_retry_schedule.request'
$taskPathHash = [System.Security.Cryptography.SHA256]::Create()
$taskHash = [BitConverter]::ToString($taskPathHash.ComputeHash([Text.Encoding]::UTF8.GetBytes($PSScriptRoot.ToLowerInvariant()))).Replace('-','').Substring(0,16)
$taskPathHash.Dispose()
$taskRetryMutex = New-Object System.Threading.Mutex($false, ('Local\KemerovoRetry_' + $taskHash))
$taskOwnMutex = $false
$taskAwake = $false
$taskSchedule = [ordered]@{pid=$PID; state='waiting'; target_started_at=$ExpectedStartedAt; queued_at=[DateTime]::UtcNow.ToString('o'); photo_deadline_seconds=180}
function Publish-RetrySchedule {
    $taskSchedule['updated_at'] = [DateTime]::UtcNow.ToString('o')
    $taskTemp = $taskSchedulePath + '.tmp'
    [IO.File]::WriteAllText($taskTemp, ($taskSchedule | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $taskTemp -Destination $taskSchedulePath -Force
}
try {
    try { $taskOwnMutex = $taskRetryMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $taskOwnMutex = $true }
    if (-not $taskOwnMutex) { throw 'A retry scheduler is already running for this workspace.' }
    Add-Type @'
using System.Runtime.InteropServices;
public static class RetrySchedulePower {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint flags);
}
'@
    $taskAwake = [RetrySchedulePower]::SetThreadExecutionState([uint32]2147483649) -ne 0
    Publish-RetrySchedule
    Write-Output 'Waiting for the current analysis to complete before retrying failures.'
    $taskReadFailures = 0
    while ($true) {
        if (Test-Path -LiteralPath $taskCancelPath) {
            $taskSchedule['state'] = 'cancelled'
            $taskSchedule['reason'] = 'Cancellation requested.'
            Publish-RetrySchedule
            break
        }
        try {
            $taskCurrent = Get-Content -LiteralPath $taskAnalysisPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $taskReadFailures = 0
        } catch {
            $taskReadFailures++
            if ($taskReadFailures -ge 6) { throw 'Cannot read the current analysis status.' }
            Start-Sleep -Seconds $PollSeconds
            continue
        }
        if ($taskCurrent.started_at -ne $ExpectedStartedAt) {
            $taskSchedule['state'] = 'superseded'
            $taskSchedule['reason'] = 'A different analysis was started; no duplicate retry will be launched.'
            Publish-RetrySchedule
            break
        }
        if ($taskCurrent.state -eq 'running') {
            Start-Sleep -Seconds $PollSeconds
            continue
        }
        if ($taskCurrent.state -ne 'completed') {
            $taskSchedule['state'] = 'cancelled'
            $taskSchedule['reason'] = 'The current analysis stopped before completion.'
            Publish-RetrySchedule
            break
        }
        if ($taskCurrent.pid) {
            $taskCompletedProcess = Get-Process -Id ([int]$taskCurrent.pid) -ErrorAction SilentlyContinue
            if ($taskCompletedProcess) { Wait-Process -InputObject $taskCompletedProcess -Timeout 30 }
        }
        $taskSchedule['state'] = 'retrying'
        $taskSchedule['retry_started_at'] = [DateTime]::UtcNow.ToString('o')
        Publish-RetrySchedule
        & (Join-Path $PSScriptRoot 'retry_failed_analysis.ps1')
        $taskSchedule['exit_code'] = $LASTEXITCODE
        $taskSchedule['state'] = if ($LASTEXITCODE -eq 0) { 'completed' } else { 'error' }
        Publish-RetrySchedule
        break
    }
} catch {
    if ($taskOwnMutex) {
        $taskSchedule['state'] = 'error'
        $taskSchedule['reason'] = $_.Exception.Message
        Publish-RetrySchedule
    }
    throw
} finally {
    if ($taskAwake) { [RetrySchedulePower]::SetThreadExecutionState([uint32]2147483648) | Out-Null }
    if ($taskOwnMutex) { $taskRetryMutex.ReleaseMutex() }
    $taskRetryMutex.Dispose()
}
