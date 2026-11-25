$ErrorActionPreference = "Stop"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ServidorFF launcher.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou com código $LASTEXITCODE" }
Copy-Item -Recurse -Force servidor dist\servidor
Get-ChildItem dist\servidor -Filter pedidos.log -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem dist\servidor -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Copy-Item -Force versao.txt dist\versao.txt
Write-Host "Gerado: dist\ServidorFF.exe"
