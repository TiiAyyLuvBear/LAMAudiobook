param(
    [int]$ApiPort = 8000,
    [int]$UiPort = 8501,
    [string]$HostAddress = "127.0.0.1",
    [string]$PythonPath = ".\.venv\Scripts\python.exe",
    [string]$CloudflaredPath = "cloudflared",
    [switch]$NoStartApps
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Test-HttpOk {
    param(
        [string]$Url,
        [int]$TimeoutSec = 5
    )
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

function Resolve-CommandPath {
    param(
        [string]$CommandName,
        [string]$InstallHint
    )
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$CommandName not found. $InstallHint"
    }
    return $command.Source
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [string]$StdOut,
        [string]$StdErr
    )
    Write-Host "Starting $Name..."
    return Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdOut `
        -RedirectStandardError $StdErr `
        -PassThru
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$storageDir = Join-Path $repoRoot "storage"
New-Item -ItemType Directory -Force -Path $storageDir | Out-Null

if (-not (Test-Path $PythonPath)) {
    throw "Python venv not found at $PythonPath. Create/activate .venv or pass -PythonPath."
}

$cloudflared = Resolve-CommandPath `
    -CommandName $CloudflaredPath `
    -InstallHint "Install Cloudflare Tunnel first: winget install --id Cloudflare.cloudflared"

$apiUrl = "http://${HostAddress}:${ApiPort}"
$uiUrl = "http://${HostAddress}:${UiPort}"
$startedProcesses = @()
$tunnelProcess = $null

try {
    if (-not $NoStartApps) {
        if (-not (Test-HttpOk "$apiUrl/health")) {
            $apiOut = Join-Path $storageDir "share_fastapi.log"
            $apiErr = Join-Path $storageDir "share_fastapi.err"
            $startedProcesses += Start-ManagedProcess `
                -Name "FastAPI" `
                -FilePath $PythonPath `
                -ArgumentList @("-m", "uvicorn", "src.app:app", "--host", $HostAddress, "--port", "$ApiPort") `
                -WorkingDirectory $repoRoot `
                -StdOut $apiOut `
                -StdErr $apiErr
            Start-Sleep -Seconds 8
        }

        if (-not (Test-HttpOk "$apiUrl/health")) {
            throw "FastAPI is not healthy at $apiUrl/health. Check storage/share_fastapi.err"
        }

        if (-not (Test-HttpOk "$uiUrl/_stcore/health")) {
            $streamlitOut = Join-Path $storageDir "share_streamlit.log"
            $streamlitErr = Join-Path $storageDir "share_streamlit.err"
            $env:API_BASE_URL = $apiUrl
            $startedProcesses += Start-ManagedProcess `
                -Name "Streamlit" `
                -FilePath $PythonPath `
                -ArgumentList @("-m", "streamlit", "run", "streamlit_app.py", "--server.port", "$UiPort", "--server.address", $HostAddress, "--server.headless", "true") `
                -WorkingDirectory $repoRoot `
                -StdOut $streamlitOut `
                -StdErr $streamlitErr
            Start-Sleep -Seconds 8
        }

        if (-not (Test-HttpOk "$uiUrl/_stcore/health")) {
            throw "Streamlit is not healthy at $uiUrl/_stcore/health. Check storage/share_streamlit.err"
        }
    }

    Write-Host "Opening Cloudflare quick tunnel for $uiUrl ..."
    Write-Host "Keep this window open. Press Ctrl+C to stop sharing."

    $tunnelLog = Join-Path $storageDir "share_cloudflared.log"
    $tunnelErr = Join-Path $storageDir "share_cloudflared.err"
    if (Test-Path $tunnelLog) { Remove-Item $tunnelLog -Force }
    if (Test-Path $tunnelErr) { Remove-Item $tunnelErr -Force }

    $tunnelProcess = Start-Process `
        -FilePath $cloudflared `
        -ArgumentList @("tunnel", "--url", $uiUrl, "--no-autoupdate") `
        -WorkingDirectory $repoRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $tunnelLog `
        -RedirectStandardError $tunnelErr `
        -PassThru

    $urlPattern = "https://[-a-zA-Z0-9.]+\.trycloudflare\.com"
    $publicUrl = $null
    $deadline = (Get-Date).AddSeconds(90)

    while ((Get-Date) -lt $deadline -and -not $publicUrl) {
        foreach ($path in @($tunnelLog, $tunnelErr)) {
            if (Test-Path $path) {
                $content = Get-Content -Path $path -Raw -ErrorAction SilentlyContinue
                if ($content) {
                    $match = [regex]::Match($content, $urlPattern)
                    if ($match.Success) {
                        $publicUrl = $match.Value
                        break
                    }
                }
            }
        }
        if ($tunnelProcess.HasExited) {
            $logs = @()
            if (Test-Path $tunnelLog) { $logs += Get-Content -Path $tunnelLog -Tail 40 }
            if (Test-Path $tunnelErr) { $logs += Get-Content -Path $tunnelErr -Tail 40 }
            throw "cloudflared exited early with code $($tunnelProcess.ExitCode)`n$($logs -join "`n")"
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $publicUrl) {
        throw "Could not find Cloudflare public URL in cloudflared output. Check $tunnelLog and $tunnelErr"
    }

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "Share this Streamlit URL with teammates:"
    Write-Host $publicUrl
    Write-Host "Local UI: $uiUrl"
    Write-Host "Local API: $apiUrl"
    Write-Host "============================================================"
    Write-Host ""

    while (-not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 2
    }
}
finally {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) {
        $tunnelProcess.Kill()
    }
    foreach ($proc in $startedProcesses) {
        if ($proc -and -not $proc.HasExited) {
            try { $proc.Kill() } catch {}
        }
    }
}
