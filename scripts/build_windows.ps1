# Build FATE AI for Windows: tests -> PyInstaller -> Inno Setup -> SHA256SUMS
# Usage (PowerShell, from repo root):  ./scripts/build_windows.ps1
$ErrorActionPreference = "Stop"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/make_icon.py
python scripts/write_version_info.py
pyinstaller --noconfirm fate_ai.spec
& dist\FateAI\FateAI.exe --smoke-test --data-dir "$env:TEMP\fate-smoke"
if ($LASTEXITCODE -ne 0) { throw "Smoke test of the packaged app failed" }
$version = python -c "import fate_ai; print(fate_ai.__version__)"
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
& $iscc "/DAppVersion=$version" installer\fate_ai.iss
Push-Location installer\Output
Get-ChildItem *.exe | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_ -Algorithm SHA256).Hash.ToLower(), $_.Name } |
  Out-File -Encoding ascii SHA256SUMS.txt
Pop-Location
Write-Host "Installer: installer\Output\FateAI-$version-setup.exe"
