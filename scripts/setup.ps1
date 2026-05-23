# Atlas one-time setup — run from repo root: .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "=== Atlas setup ===" -ForegroundColor Cyan

# Python venv
if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "Creating venv..."
    python -m venv venv
}

$Py = "venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip

Write-Host "Installing Python packages..."
& $Py -m pip install -r requirements.txt

# llama-cpp-python with CUDA (4090 / CUDA 12.x)
Write-Host "Installing llama-cpp-python (CUDA) — required for local Orpheus TTS..."
& $Py -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
if ($LASTEXITCODE -ne 0) {
    Write-Host "CUDA wheel failed; trying default llama-cpp-python..." -ForegroundColor Yellow
    & $Py -m pip install llama-cpp-python
}

Write-Host "=== Ollama models ===" -ForegroundColor Cyan
$models = @("llama3.2:3b", "nomic-embed-text")
foreach ($m in $models) {
    Write-Host "pull $m ..."
    ollama pull $m
}

if (-not (Test-Path "config.yaml")) {
    Copy-Item "config.example.yaml" "config.yaml"
    Write-Host "Created config.yaml from example"
}
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example — add HF_TOKEN there (optional)"
}

$ggufDir = "models"
New-Item -ItemType Directory -Force -Path $ggufDir | Out-Null
$gguf = Join-Path $ggufDir "Orpheus-3b-FT-Q8_0.gguf"
if (-not (Test-Path $gguf)) {
    if (Test-Path "Orpheus-FastAPI\models\Orpheus-3b-FT-Q8_0.gguf") {
        Copy-Item "Orpheus-FastAPI\models\Orpheus-3b-FT-Q8_0.gguf" $gguf
        Write-Host "Copied existing Orpheus GGUF to models/"
    } else {
        Write-Host "Orpheus GGUF not found. Download from HuggingFace lex-au/Orpheus-3b-FT-Q8_0-GGUF into $ggufDir" -ForegroundColor Yellow
    }
}

Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Start: .\venv\Scripts\python.exe run_atlas.py --check"
Write-Host "Chat:  .\venv\Scripts\python.exe run_atlas.py -i"
