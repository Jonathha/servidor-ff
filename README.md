# servidor-ff

Servidor local pessoal para um jogador, conforme a especificação do projeto. O servidor é Python puro e usa apenas a biblioteca padrão. O executável é uma casca Windows com Tkinter: atualiza `servidor/` pela Release do GitHub e então inicia o servidor HTTP em `0.0.0.0:8080`.

## Gerar o `.exe`

Instale Python no Windows e o PyInstaller apenas na máquina de build:

```powershell
python -m pip install pyinstaller
./build.ps1
```

O resultado fica em `dist/ServidorFF.exe`, junto com `dist/servidor/` e `dist/versao.txt`. Em runtime não há dependências Python externas.

## Publicar a Release

Crie o repositório privado `servidor-ff`, publique o conteúdo deste repositório, e crie a Release `v1` com o asset `servidor.zip`. Esse ZIP deve conter os arquivos da pasta `servidor/` (incluindo `servidor.py`). Para atualização, altere `versao.txt`, gere outro `servidor.zip`, faça uma nova Release e anexe o asset com esse mesmo nome. A atualização usa exclusivamente a API/Release do GitHub; R2 não faz parte deste projeto.

O `config.json` ao lado do EXE deve conter `github_token` (token somente leitura) e `repo` (`usuario/servidor-ff`). Ele nunca deve ser versionado.

## Escopo do protocolo

Somente os endpoints e campos descritos na especificação são implementados. Configuração de versão do jogo, login do SDK e servidor TCP do jogo/lobby permanecem TODO, sem formatos inventados.
