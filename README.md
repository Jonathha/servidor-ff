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

Na primeira abertura, o aplicativo pede um token de leitura do GitHub e o repositório. Os dados ficam em `config.json` ao lado do EXE para não solicitar novamente. Esse arquivo nunca deve ser versionado. Para habilitar o Fluxo A, preencha também `worker_private_url`, `private_server_status_secret`, `public_host` e `tcp_port`; com `public_host` vazio ou `tcp_port` igual a zero, o listener TCP permanece desligado. O mesmo `public_host:tcp_port` é usado nas respostas de login e no bind público do TCP.

## Escopo do protocolo

O Fluxo A `TCPSession2` tem framing, validação de sessão e AES-128 ECB manual. O `/ver` continua aberto com HTTPVerGet desconhecido, e o Fluxo B continua aberto; nenhum dos dois foi inventado. Os fios do pedido MiddleLogin também continuam explicitamente não confirmados: enquanto não houver captura/documentação, o servidor registra o corpo e recusa o login antes de emitir uma sessão.
