param(
    [ValidateSet('doctor','prepare','sample','all','update','export','review','retry')]
    [string]$Action = 'doctor',
    [string]$InputFolder = 'D:\map_photos',
    [string]$Workspace = 'work',
    [string]$OutputFolder = 'output',
    [string]$Config = 'config.example.yaml'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$PythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
function Invoke-CityPhoto {
    & $PythonExe -m city_photo @args
    if ($LASTEXITCODE -ne 0) { throw "city-photo failed: $LASTEXITCODE" }
}
switch ($Action) {
    'doctor' { Invoke-CityPhoto doctor --config $Config }
    'prepare' {
        Invoke-CityPhoto init --workspace $Workspace --config $Config
        Invoke-CityPhoto import --input $InputFolder --workspace $Workspace --config $Config
    }
    'sample' {
        Invoke-CityPhoto analyze --workspace $Workspace --config $Config --limit 20 --resume
        Invoke-CityPhoto export --workspace $Workspace --config $Config --output $OutputFolder
    }
    'all' {
        Invoke-CityPhoto analyze --workspace $Workspace --config $Config --resume
        Invoke-CityPhoto export --workspace $Workspace --config $Config --output $OutputFolder
    }
    'update' {
        Invoke-CityPhoto import --input $InputFolder --workspace $Workspace --config $Config
        Invoke-CityPhoto analyze --workspace $Workspace --config $Config --resume
        Invoke-CityPhoto export --workspace $Workspace --config $Config --output $OutputFolder
    }
    'retry' {
        Invoke-CityPhoto analyze --workspace $Workspace --config $Config --resume --retry-errors
        Invoke-CityPhoto export --workspace $Workspace --config $Config --output $OutputFolder
    }
    'export' { Invoke-CityPhoto export --workspace $Workspace --config $Config --output $OutputFolder }
    'review' { Invoke-CityPhoto review-export --workspace $Workspace --config $Config --output $OutputFolder --limit 100 }
}
