$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ServidorFF launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou com código $LASTEXITCODE" }
if (Test-Path dist\servidor) { Remove-Item -LiteralPath dist\servidor -Recurse -Force }
New-Item -ItemType Directory -Force dist\servidor | Out-Null
Copy-Item -Force servidor\servidor.py dist\servidor\servidor.py
Copy-Item -Force versao.txt dist\versao.txt
Write-Host "Gerado: dist\ServidorFF.exe"
