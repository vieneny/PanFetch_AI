$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

uv sync --python 3.12 --system-certs
if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE" }
uv run pytest
if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }
uv run pyinstaller --noconfirm --clean panfetch-ai.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$executable = Join-Path $projectRoot "dist\PanFetch AI.exe"
$package = Join-Path $projectRoot "dist\PanFetch-AI-Windows-x64.zip"
$packageFiles = @(
    $executable,
    (Join-Path $projectRoot "README.md"),
    (Join-Path $projectRoot "README.en-US.md"),
    (Join-Path $projectRoot "LICENSE")
)
Compress-Archive -LiteralPath $packageFiles -DestinationPath $package -CompressionLevel Optimal -Force

Write-Host "Build completed: $executable"
Write-Host "Distribution package: $package"
