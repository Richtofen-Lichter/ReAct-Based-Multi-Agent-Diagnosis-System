# ============================================================
# Multi-Agent AIOps Platform - Windows launcher
# ============================================================
# Startup order:
#   1. Start / check Milvus container
#   2. Start / check Redis container (Celery broker + RAG Chat session memory)
#   3. Start Celery worker (background)
#   4. Start MCP servers in background
#   5. Wait for MCP ports
#   6. Start FastAPI by uvicorn in foreground
#
# Usage:
#   .\run.ps1
#   .\run.ps1 -NoMcp
#   .\run.ps1 -NoMilvus
#   .\run.ps1 -NoRedis
#   .\run.ps1 -NoCelery
#   .\run.ps1 -Stop
# ============================================================

param(
    [switch]$NoMcp,
    [switch]$NoMilvus,
    [switch]$NoRedis,
    [switch]$NoCelery,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Get-EnvValue {
    param(
        [string]$Name,
        [string]$DefaultValue = ""
    )
    $envPath = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path $envPath)) {
        return $DefaultValue
    }
    $line = Get-Content $envPath -Encoding UTF8 | Where-Object {
        $_ -match "^\s*$([regex]::Escape($Name))\s*="
    } | Select-Object -First 1
    if (-not $line) {
        return $DefaultValue
    }
    return (($line -split "=", 2)[1]).Trim()
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
        if ($ok) {
            $client.EndConnect($iar)
        }
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

function Wait-TcpPort {
    param(
        [string]$Name,
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSec = 30
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-Host "[ready] $Name is listening on $HostName`:$Port" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "[warn] $Name did not become ready on $HostName`:$Port within ${TimeoutSec}s" -ForegroundColor Yellow
    return $false
}

function Start-PythonServer {
    param(
        [string]$Name,
        [string]$Script,
        [int]$Port
    )
    if (-not (Test-Path $Script)) {
        Write-Host "[skip] $Name script not found: $Script" -ForegroundColor DarkYellow
        return
    }
    if (Test-TcpPort -HostName "127.0.0.1" -Port $Port) {
        Write-Host "[skip] $Name already listening on port $Port" -ForegroundColor DarkYellow
        return
    }

    $base = [System.IO.Path]::GetFileNameWithoutExtension($Script)
    $outLog = Join-Path $LogDir "$base.out.log"
    $errLog = Join-Path $LogDir "$base.err.log"

    Write-Host "[start] MCP $Name (port $Port)..." -ForegroundColor Cyan
    Start-Process -FilePath $Python `
        -ArgumentList @("`"$Script`"") `
        -WindowStyle Hidden `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog

    $ok = Wait-TcpPort -Name "MCP $Name" -HostName "127.0.0.1" -Port $Port -TimeoutSec 25
    if (-not $ok) {
        Write-Host "       stdout: $outLog" -ForegroundColor Yellow
        Write-Host "       stderr: $errLog" -ForegroundColor Yellow
    }
}

function Stop-PortProcess {
    param(
        [int]$Port
    )
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        $pidToStop = $conn.OwningProcess
        if ($pidToStop -and $pidToStop -ne $PID) {
            try {
                Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
                Write-Host "[stop] port=$Port pid=$pidToStop" -ForegroundColor DarkYellow
            } catch {
                try {
                    taskkill /PID $pidToStop /F /T | Out-Null
                    Write-Host "[stop] port=$Port pid=$pidToStop" -ForegroundColor DarkYellow
                } catch {
                }
            }
        }
    }
}

function Test-HttpReady {
    param(
        [int]$Port
    )
    try {
        $resp = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/v1/health/ready" -TimeoutSec 2
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
    } catch {
        return $false
    }
}

if ($Stop) {
    Write-Host "[stop] stopping multi_agent services..." -ForegroundColor Yellow

    # 先杀所有 celery worker (避免旧版本残留)
    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -like "*celery*worker*"
    } | ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[stop] celery pid=$($_.ProcessId)" -ForegroundColor DarkYellow
        } catch {}
    }

    Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and (
            $_.CommandLine -like "*$ProjectRoot*" -or
            $_.CommandLine -like "*mcp_servers*" -or
            $_.CommandLine -like "*uvicorn app.main:app*"
        )
    } | ForEach-Object {
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[stop] pid=$($_.ProcessId) $($_.Name)" -ForegroundColor DarkYellow
        } catch {
        }
    }
    8005,8006,8008,8009,8011,9900 | ForEach-Object {
        Stop-PortProcess -Port $_
    }
    Write-Host "[stop] done" -ForegroundColor Green
    exit 0
}

# 按优先级查找 Python:
#   1. CONDA_PREFIX (conda 已激活的非 base 环境, 最可靠)
#   2. 常见 conda env 路径扫描 (兜底, CONDA_PREFIX 可能指向 base 或未设置)
#   3. 项目 .venv
#   4. 系统 PATH 里的 python (最后兜底, 需自行确保依赖齐全)

function Find-CondaEnvPython {
    param([string]$EnvName)
    $searchDirs = @(
        "$env:USERPROFILE\.conda\envs\$EnvName\python.exe"
        "D:\Anaconda\envs\$EnvName\python.exe"
        "C:\Anaconda\envs\$EnvName\python.exe"
        "$env:USERPROFILE\Anaconda\envs\$EnvName\python.exe"
        "$env:ProgramData\Anaconda\envs\$EnvName\python.exe"
    )
    foreach ($dir in $searchDirs) {
        if (Test-Path $dir) { return $dir }
    }
    return $null
}

$Python = $null

# 1. CONDA_PREFIX 指向的非 base 环境 (路径中含 envs\ 才算命名环境)
if ($env:CONDA_PREFIX -and $env:CONDA_PREFIX -match "\\envs\\" -and (Test-Path "$env:CONDA_PREFIX\python.exe")) {
    $Python = "$env:CONDA_PREFIX\python.exe"
    Write-Host "[hint] using activated conda env: $env:CONDA_PREFIX" -ForegroundColor Green
}

# 2. 扫描常见 conda env 位置 (适配 README 推荐的 multi_rag / multi-rag)
if (-not $Python) {
    foreach ($name in @("multi-rag", "multi_rag")) {
        $found = Find-CondaEnvPython -EnvName $name
        if ($found) {
            $Python = $found
            Write-Host "[hint] conda env '$name' detected at $Python" -ForegroundColor Green
            break
        }
    }
}

# 3. 项目 .venv
if (-not $Python -and (Test-Path "$ProjectRoot\.venv\Scripts\python.exe")) {
    $Python = "$ProjectRoot\.venv\Scripts\python.exe"
    Write-Host "[hint] using project .venv" -ForegroundColor Green
}

# 4. 系统 PATH 兜底
if (-not $Python) {
    $Python = "python"
    Write-Host "[warn] no conda env or venv found, using system python. Ensure dependencies are installed." -ForegroundColor Yellow
}

Write-Host "[start] Python: $Python" -ForegroundColor Cyan

if (-not (Test-Path "$ProjectRoot\.env")) {
    Write-Host "[error] .env not found. Please create .env first." -ForegroundColor Red
    exit 1
}

$AppPortText = Get-EnvValue -Name "PORT" -DefaultValue "9900"
$AppPort = [int]$AppPortText

if (-not $NoMilvus) {
    Write-Host "[check] Milvus (localhost:19530)..." -ForegroundColor Cyan
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 19530)) {
        try {
            Write-Host "[start] docker compose up -d standalone..." -ForegroundColor Cyan
            docker compose up -d standalone
        } catch {
            Write-Host "[warn] Docker is not available or docker compose failed. Milvus may be unavailable." -ForegroundColor Yellow
        }
    }
    Wait-TcpPort -Name "Milvus" -HostName "127.0.0.1" -Port 19530 -TimeoutSec 90 | Out-Null
} else {
    Write-Host "[skip] Milvus auto-start disabled by -NoMilvus" -ForegroundColor DarkYellow
}

if (-not $NoRedis) {
    Write-Host "[check] Redis (localhost:6379)..." -ForegroundColor Cyan
    if (-not (Test-TcpPort -HostName "127.0.0.1" -Port 6379)) {
        try {
            Write-Host "[start] docker compose up -d redis..." -ForegroundColor Cyan
            docker compose up -d redis
        } catch {
            Write-Host "[warn] Docker not available or docker compose failed. Redis session memory will be disabled." -ForegroundColor Yellow
        }
    }
    if (Wait-TcpPort -Name "Redis" -HostName "127.0.0.1" -Port 6379 -TimeoutSec 30) {
        $memFlag = Get-EnvValue -Name "RAG_CHAT_MEMORY_ENABLED" -DefaultValue "false"
        if ($memFlag -notmatch '^(?i)true$') {
            Write-Host "[hint] Redis running, but .env RAG_CHAT_MEMORY_ENABLED=$memFlag. Set it to 'true' to enable session memory." -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[skip] Redis auto-start disabled by -NoRedis" -ForegroundColor DarkYellow
}

# --- Celery Worker ---
if (-not $NoCelery) {
    $CeleryLogOut = Join-Path $LogDir "celery_worker.out.log"
    $CeleryLogErr = Join-Path $LogDir "celery_worker.err.log"
    Write-Host "[start] Celery worker (background)..." -ForegroundColor Cyan
    Start-Process -FilePath $Python `
        -ArgumentList "-m celery -A celery_worker:celery_app worker --concurrency=1 --loglevel=warning --pool=threads" `
        -WindowStyle Hidden `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $CeleryLogOut `
        -RedirectStandardError $CeleryLogErr
    Write-Host "[start] Celery worker started (logs: $CeleryLogOut)" -ForegroundColor Green
    Start-Sleep -Seconds 2
} else {
    Write-Host "[skip] Celery worker auto-start disabled by -NoCelery" -ForegroundColor DarkYellow
}

if (-not $NoMcp) {
    Start-PythonServer -Name "system_server" -Script "$ProjectRoot\mcp_servers\system_server.py" -Port 8005
    Start-PythonServer -Name "websearch_server" -Script "$ProjectRoot\mcp_servers\websearch_server.py" -Port 8006
    Start-PythonServer -Name "winlog_server" -Script "$ProjectRoot\mcp_servers\winlog_server.py" -Port 8008
    Start-PythonServer -Name "network_server" -Script "$ProjectRoot\mcp_servers\network_server.py" -Port 8009
    Start-PythonServer -Name "docker_server" -Script "$ProjectRoot\mcp_servers\docker_server.py" -Port 8011
} else {
    Write-Host "[skip] MCP auto-start disabled by -NoMcp" -ForegroundColor DarkYellow
}

if (Test-TcpPort -HostName "127.0.0.1" -Port $AppPort) {
    if (Test-HttpReady -Port $AppPort) {
        Write-Host "[ready] FastAPI main service is already running on port $AppPort" -ForegroundColor Green
        Write-Host "        Web UI:  http://localhost:$AppPort" -ForegroundColor Green
        Write-Host "        API Doc: http://localhost:$AppPort/docs" -ForegroundColor Green
        exit 0
    }
    Write-Host "[warn] port $AppPort is already in use, but health check failed." -ForegroundColor Yellow
    Write-Host "       Close the old terminal/window, or run: .\run.ps1 -Stop" -ForegroundColor Yellow
    exit 1
}

Write-Host "[start] FastAPI main service (port $AppPort)..." -ForegroundColor Green
Write-Host "        Web UI:  http://localhost:$AppPort" -ForegroundColor Green
Write-Host "        API Doc: http://localhost:$AppPort/docs" -ForegroundColor Green
Write-Host ""

& $Python -m uvicorn app.main:app `
    --host 0.0.0.0 `
    --port $AppPort `
    --reload `
    --reload-dir "$ProjectRoot\app"
