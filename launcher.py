#!/usr/bin/env python3
"""Painel local do Servidor FF, implementado apenas com a biblioteca padrão."""

from datetime import datetime
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile

APP_NAME = "Servidor FF"
MAX_LOG_LINES = 30
HTML = r'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Servidor FF</title>
<style>
:root{color-scheme:dark;--bg:#25282d;--panel:#30343a;--panel2:#383d44;--line:#484e56;--text:#eceff2;--muted:#aeb5bd;--accent:#7ba7d8;--green:#74c69d;--red:#e08c8c}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px "Segoe UI",Arial,sans-serif}.layout{display:flex;min-height:100vh}.side{width:220px;padding:26px 16px;background:#292d32;border-right:1px solid var(--line)}.brand{font-size:20px;font-weight:700;padding:0 10px 26px}.nav{display:grid;gap:8px}.nav button,.action{border:0;border-radius:8px;padding:12px 14px;text-align:left;color:var(--muted);background:transparent;font:inherit;cursor:pointer}.nav button.active,.nav button:hover{background:var(--panel2);color:var(--text)}main{width:min(100%,1050px);padding:34px;margin:auto}.top{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:24px}.top h1{font-size:24px;margin:0}.badge{border-radius:99px;padding:7px 12px;background:var(--panel2);font-size:13px}.badge.on{color:var(--green)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px}.label{color:var(--muted);font-size:13px}.value{font-size:20px;margin-top:10px;overflow-wrap:anywhere}.action{background:var(--accent);color:#17212c;font-weight:650;margin-top:16px;text-align:center;min-width:125px}.action:disabled{opacity:.55;cursor:wait}.tabs{display:flex;gap:8px;border-bottom:1px solid var(--line);margin-bottom:16px}.tab{border:0;background:none;color:var(--muted);padding:10px 13px;font:inherit;cursor:pointer}.tab.active{color:var(--text);border-bottom:2px solid var(--accent)}.logs{height:390px;overflow:auto;background:#202328;border:1px solid var(--line);border-radius:9px;padding:14px;font:12px Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.note{color:var(--muted);font-size:13px;margin-top:12px}.hidden{display:none}@media(max-width:700px){.layout{display:block}.side{width:100%;padding:14px;border:0;border-bottom:1px solid var(--line)}.brand{padding:4px 8px 12px}.nav{display:flex}.nav button{flex:1;text-align:center}main{padding:22px 16px}.grid{grid-template-columns:1fr}.top{align-items:flex-start}}
</style><div class="layout"><aside class="side"><div class="brand">Servidor FF</div><nav class="nav"><button class="active" data-page="home">Visão geral</button><button data-page="logs">Registros</button></nav></aside><main><div class="top"><h1 id="heading">Visão geral</h1><span id="status" class="badge">Carregando…</span></div>
<section id="home"><div class="grid"><div class="card"><div class="label">Estado do servidor</div><div class="value" id="state">Iniciando</div><button class="action" id="toggle">Aguarde…</button></div><div class="card"><div class="label">Endereço na rede local</div><div class="value" id="address">—</div><div class="note">Conecte o celular à mesma rede Wi-Fi.</div></div><div class="card"><div class="label">Atualizações</div><div class="value" id="version">Verificando</div><div class="note" id="update-note">O servidor inicia mesmo sem internet.</div></div><div class="card"><div class="label">Painel</div><div class="value">Disponível somente neste computador</div><div class="note">Esta página é servida localmente pelo aplicativo.</div></div></div></section>
<section id="logs" class="hidden"><div class="tabs"><button class="tab active" data-logtab="live">Ao vivo</button><button class="tab" data-logtab="info">Sobre</button></div><pre class="logs" id="logtext"></pre><p class="note" id="about">Os últimos 30 registros são mantidos na tela.</p></section></main></div>
<script>
const $=s=>document.querySelector(s);document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-page]').forEach(x=>x.classList.toggle('active',x===b));$('#home').classList.toggle('hidden',b.dataset.page!=='home');$('#logs').classList.toggle('hidden',b.dataset.page!=='logs');$('#heading').textContent=b.dataset.page==='home'?'Visão geral':'Registros'});document.querySelectorAll('[data-logtab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-logtab]').forEach(x=>x.classList.toggle('active',x===b));$('#logtext').classList.toggle('hidden',b.dataset.logtab!=='live');$('#about').classList.toggle('hidden',b.dataset.logtab!=='info')});
async function refresh(){try{let r=await fetch('/api/state',{cache:'no-store'}),d=await r.json();$('#state').textContent=d.running?'LIGADO':'DESLIGADO';$('#status').textContent=d.running?'● LIGADO':'● DESLIGADO';$('#status').classList.toggle('on',d.running);$('#address').textContent=d.ip+':8080';$('#version').textContent=d.version||'Local';$('#update-note').textContent=d.update||'Atualizações automáticas ativadas.';$('#toggle').textContent=d.running?'Desligar':'Ligar';$('#toggle').disabled=false;$('#logtext').textContent=(d.logs||[]).join('\n');$('#logtext').scrollTop=$('#logtext').scrollHeight}catch(e){$('#status').textContent='Painel reconectando…'}}$('#toggle').onclick=async()=>{let b=$('#toggle');b.disabled=true;try{await fetch('/api/toggle',{method:'POST'})}finally{setTimeout(refresh,250)}};refresh();setInterval(refresh,1200);
</script></html>'''


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


BASE = app_dir()
SERVER_DIR = BASE / "servidor"
CONFIG_FILE = BASE / "config.json"
LOCAL_VERSION_FILE = BASE / "versao.txt"
LOGS = deque(maxlen=MAX_LOG_LINES)
LOCK = threading.RLock()
SERVER_PROCESS = None
UPDATE_STATE = "Preparando atualização…"
UPDATE_VERSION = "Local"
LOCAL_IP = "127.0.0.1"


def log(message: str) -> None:
    line = "%s  %s" % (datetime.now().strftime("%H:%M:%S"), str(message).rstrip())
    with LOCK:
        LOGS.append(line)
    print(line, flush=True)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if data.get("github_token") and data.get("repo"):
                return data
        except (OSError, ValueError):
            pass
    import tkinter as tk
    from tkinter import simpledialog, messagebox
    root = tk.Tk()
    root.withdraw()
    token = simpledialog.askstring(APP_NAME, "Cole seu token de acesso somente leitura do GitHub. Ele será salvo neste computador para as próximas aberturas:", parent=root, show="*")
    repo = simpledialog.askstring(APP_NAME, "Repositório GitHub (proprietário/servidor-ff):", initialvalue="Jonathha/servidor-ff", parent=root)
    root.destroy()
    if not token or not repo:
        raise RuntimeError("Configuração do GitHub cancelada")
    CONFIG_FILE.write_text(json.dumps({"github_token": token.strip(), "repo": repo.strip()}, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass
    return {"github_token": token.strip(), "repo": repo.strip()}


def github_get(url: str, token: str, accept: str = "application/vnd.github+json") -> bytes:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token, "Accept": accept, "User-Agent": "ServidorFF"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read()


def update_server() -> None:
    global UPDATE_STATE, UPDATE_VERSION
    try:
        config = load_config()
        repo = config["repo"]
        token = config["github_token"]
        version_url = "https://raw.githubusercontent.com/%s/main/versao.txt" % repo
        remote = int(github_get(version_url, token, "text/plain").decode("utf-8").strip())
        local = int(LOCAL_VERSION_FILE.read_text(encoding="utf-8").strip()) if LOCAL_VERSION_FILE.exists() else 0
        if remote > local:
            release = json.loads(github_get("https://api.github.com/repos/%s/releases/latest" % repo, token))
            asset = next(item for item in release.get("assets", []) if item.get("name") == "servidor.zip")
            archive_bytes = github_get(asset["url"], token, "application/octet-stream")
            with tempfile.TemporaryDirectory(prefix="servidor_ff_") as temp_name:
                temp = Path(temp_name)
                archive_path = temp / "servidor.zip"
                archive_path.write_bytes(archive_bytes)
                extracted = temp / "servidor"
                extracted.mkdir()
                with zipfile.ZipFile(archive_path) as archive:
                    root = extracted.resolve()
                    for item in archive.infolist():
                        dest = (extracted / item.filename).resolve()
                        if root not in dest.parents:
                            raise ValueError("Arquivo inválido no pacote de atualização")
                    archive.extractall(extracted)
                if not (extracted / "servidor.py").is_file():
                    raise ValueError("O pacote não contém servidor.py")
                backup = BASE / ("servidor.backup-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"))
                if SERVER_DIR.exists():
                    shutil.move(str(SERVER_DIR), str(backup))
                try:
                    shutil.move(str(extracted), str(SERVER_DIR))
                except Exception:
                    if backup.exists() and not SERVER_DIR.exists():
                        shutil.move(str(backup), str(SERVER_DIR))
                    raise
            LOCAL_VERSION_FILE.write_text(str(remote) + "\n", encoding="utf-8")
            log("Servidor atualizado para a versão %d." % remote)
        UPDATE_VERSION = str(max(remote, local))
        UPDATE_STATE = "Atualizado" if remote > local else "Atualizações automáticas ativadas."
    except Exception as exc:
        UPDATE_STATE = "Sem atualização agora; usando arquivos locais."
        UPDATE_VERSION = "Local"
        log("Atualização ignorada (%s); iniciando a versão local." % exc)


def startup_server() -> None:
    update_server()
    start_server()


def start_server() -> bool:
    global SERVER_PROCESS
    with LOCK:
        if SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None:
            return True
        script = SERVER_DIR / "servidor.py"
        if not script.is_file():
            log("Não encontrei servidor/servidor.py junto ao aplicativo.")
            return False
        try:
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--run-server", str(script)]
            else:
                command = [sys.executable, str(script)]
            SERVER_PROCESS = subprocess.Popen(command, cwd=str(SERVER_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            threading.Thread(target=read_server_logs, args=(SERVER_PROCESS,), daemon=True).start()
            log("Servidor iniciado em %s:8080." % LOCAL_IP)
            return True
        except OSError as exc:
            log("Falha ao iniciar servidor: %s" % exc)
            return False


def read_server_logs(process) -> None:
    if process.stdout:
        for line in process.stdout:
            log(line)


def stop_server() -> None:
    global SERVER_PROCESS
    with LOCK:
        process = SERVER_PROCESS
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            log("Servidor desligado.")
        SERVER_PROCESS = None


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/":
            body, content = HTML.encode("utf-8"), "text/html; charset=utf-8"
        elif self.path == "/api/state":
            with LOCK:
                running = SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None
                body = json.dumps({"running": running, "ip": LOCAL_IP, "logs": list(LOGS), "version": UPDATE_VERSION, "update": UPDATE_STATE}, ensure_ascii=False).encode("utf-8")
            content = "application/json; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        if self.path != "/api/toggle":
            self.send_error(404)
            return
        with LOCK:
            running = SERVER_PROCESS is not None and SERVER_PROCESS.poll() is None
        threading.Thread(target=stop_server if running else start_server, daemon=True).start()
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        return


def run_server_mode() -> None:
    import runpy
    script = Path(sys.argv[sys.argv.index("--run-server") + 1])
    sys.argv = [str(script)]
    runpy.run_path(str(script), run_name="__main__")


def main() -> None:
    global LOCAL_IP
    LOCAL_IP = local_ip()
    try:
        load_config()
    except Exception as exc:
        log("Configuração do GitHub não concluída: %s" % exc)
    if not (SERVER_DIR / "servidor.py").is_file():
        log("Pasta servidor ausente ou incompleta.")
    panel = ThreadingHTTPServer(("127.0.0.1", 0), DashboardHandler)
    threading.Thread(target=panel.serve_forever, daemon=True).start()
    panel_url = "http://127.0.0.1:%d/" % panel.server_address[1]
    webbrowser.open(panel_url)
    log("Painel local aberto no navegador: %s" % panel_url)
    threading.Thread(target=startup_server, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop_server()
        panel.shutdown()


if __name__ == "__main__":
    if "--run-server" in sys.argv:
        run_server_mode()
    else:
        main()
