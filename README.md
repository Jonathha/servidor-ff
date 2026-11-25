# servidor-ff

Servidor local pessoal para um jogador. O servidor e o painel web local usam apenas a biblioteca padrão do Python. O executável abre um painel em português no navegador, inicia o servidor HTTP em `0.0.0.0:8080` e verifica atualizações do código do servidor em segundo plano.

## Gerar o `.exe`

Instale Python no Windows e o PyInstaller apenas na máquina de build:

```powershell
python -m pip install pyinstaller
./build.ps1
```

O resultado fica em `dist/ServidorFF.exe`, junto com `dist/servidor/` e `dist/versao.txt`. Em runtime não há dependências Python externas.

## Publicar a Release

Crie o repositório privado `servidor-ff`, publique o conteúdo deste repositório, e crie a Release `v1` com o asset `servidor.zip`. Esse ZIP deve conter os arquivos da pasta `servidor/` (incluindo `servidor.py`). Para atualização, altere `versao.txt`, gere outro `servidor.zip`, faça uma nova Release e anexe o asset com esse mesmo nome. A atualização usa exclusivamente a API/Release do GitHub; R2 não faz parte deste projeto.

Na primeira abertura, o aplicativo pede um token de leitura do GitHub e o repositório. Os dados ficam em `config.json` ao lado do EXE para não solicitar novamente. Esse arquivo nunca deve ser versionado. O painel usa uma porta local aleatória e só aceita conexões do próprio notebook.

## Escopo do protocolo

Somente os endpoints e campos descritos na especificação são implementados. Configuração de versão do jogo, login do SDK e servidor TCP do jogo/lobby permanecem TODO, sem formatos inventados.
