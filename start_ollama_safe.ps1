$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:LLAMA_ARG_CACHE_RAM='0'
$env:OLLAMA_NUM_PARALLEL='1'
$env:OLLAMA_MAX_LOADED_MODELS='1'
$env:OLLAMA_NO_CLOUD='1'
if (Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Ollama is already running. Quit it before starting this memory-bounded server.'
}
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'work') -Force | Out-Null
$executable=(Get-Command ollama -ErrorAction Stop).Source
Start-Process -FilePath $executable -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'work\ollama_safe.out.log') -RedirectStandardError (Join-Path $PSScriptRoot 'work\ollama_safe.err.log') -PassThru | Select-Object Id,ProcessName
