param(
    [string]$ProjectRoot = "C:\Projects\nl2sql-mvp",
    [int]$TimeoutSeconds = 240,
    [int]$MaxRetries = 2
)

$ErrorActionPreference = "Stop"

$BackendDir = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $BackendDir "venv\Scripts\python.exe"

if (-not (Test-Path $BackendDir)) {
    throw "Backend directory not found: $BackendDir"
}

if (-not (Test-Path $PythonExe)) {
    throw "Virtual-environment Python not found: $PythonExe"
}

Set-Location $BackendDir

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $BackendDir "benchmarks\final_evaluation\sql\reports\overnight_$Stamp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$BackendOut = Join-Path $LogDir "backend_stdout.log"
$BackendErr = Join-Path $LogDir "backend_stderr.log"
$RunnerLog = Join-Path $LogDir "sql_2000_console.log"

$BackendProcess = $null
$StartedBackend = $false

function Test-BackendReady {
    try {
        Invoke-WebRequest `
            -Uri "http://127.0.0.1:8000/docs" `
            -UseBasicParsing `
            -TimeoutSec 3 | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

try {
    if (Test-BackendReady) {
        Write-Host "SpiderSQL backend is already running on port 8000."
    }
    else {
        Write-Host "Starting SpiderSQL backend..."
        $BackendProcess = Start-Process `
            -FilePath $PythonExe `
            -ArgumentList @(
                "-m", "uvicorn", "app:app",
                "--host", "127.0.0.1",
                "--port", "8000"
            ) `
            -WorkingDirectory $BackendDir `
            -RedirectStandardOutput $BackendOut `
            -RedirectStandardError $BackendErr `
            -PassThru

        $StartedBackend = $true

        $Ready = $false
        for ($Attempt = 1; $Attempt -le 60; $Attempt++) {
            Start-Sleep -Seconds 2
            if (Test-BackendReady) {
                $Ready = $true
                break
            }

            if ($BackendProcess.HasExited) {
                throw "Backend exited before becoming ready. Check $BackendErr"
            }
        }

        if (-not $Ready) {
            throw "Backend did not become ready within 120 seconds. Check $BackendErr"
        }

        Write-Host "Backend is ready."
    }

    Write-Host ""
    Write-Host "Starting all 2,000 SQL benchmark cases..."
    Write-Host "Output prefix: full"
    Write-Host "Resume mode: enabled"
    Write-Host "Console log: $RunnerLog"
    Write-Host ""

    & $PythonExe `
        -m benchmarks.final_evaluation.sql.runners.run_sql_benchmark `
        --output-prefix full `
        --resume `
        --timeout $TimeoutSeconds `
        --max-retries $MaxRetries `
        2>&1 | Tee-Object -FilePath $RunnerLog

    $RunnerExitCode = $LASTEXITCODE

    Write-Host ""
    Write-Host "SQL benchmark process finished with exit code $RunnerExitCode."
    Write-Host "Results:"
    Write-Host "  $BackendDir\benchmarks\final_evaluation\sql\results"
    Write-Host "Reports:"
    Write-Host "  $BackendDir\benchmarks\final_evaluation\sql\reports"
    Write-Host "Overnight log:"
    Write-Host "  $RunnerLog"

    exit $RunnerExitCode
}
finally {
    if ($StartedBackend -and $null -ne $BackendProcess -and -not $BackendProcess.HasExited) {
        Write-Host "Stopping the backend process started by this script..."
        Stop-Process -Id $BackendProcess.Id -Force
    }
}
