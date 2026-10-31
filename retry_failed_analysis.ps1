$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'start_analysis.ps1') -RetryFailed
exit $LASTEXITCODE
