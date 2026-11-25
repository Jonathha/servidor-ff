#!/usr/bin/env python3
"""Casca Windows: atualização GitHub e execução do servidor local."""

from datetime import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import urllib.error
import urllib.request
import zipfile

APP_NAME = "Servidor FF"
SERVER_DIR_NAME = "servidor"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("720x460")
        self.root.minsize(560, 360)
        self.base = Path(sys_executable_dir())
        self.server_dir = self.base / SERVER_DIR_NAME
        self.config_path = self.base / "config.json"
        self.process = None
        self.lines = queue.Queue()
        self.status = tk.StringVar(value="DESLIGADO")
        self.endpoint = tk.StringVar(value="IP local: descobrindo...")
        self._build_ui()
        self.root.after(100, self._drain_log)
        threading.Thread(target=self._startup, daemon=True).start()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.status, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(8, 0))
        ttk.Label(frame, textvariable=self.endpoint).pack(anchor="w")
        self.toggle = ttk.Button(frame, text="Ligar", command=self.toggle_server)
        self.toggle.pack(anchor="w", pady=10)
        self.log = tk.Text(frame, state="disabled", height=18, wrap="none")
        self.log.pack(fill="both", expand=True)

    def write_log(self, text: str) -> None:
        self.lines.put(text.rstrip())

    def _drain_log(self) -> None:
        try:
            while True:
                line = self.lines.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log)

    def _startup(self) -> None:
        try:
            self._ensure_config()
            self._update()
        except Exception as exc:
            self.write_log("Atualização ignorada: %s" % exc)
        self.root.after(0, self.start_server)

    def _ensure_config(self) -> None:
        if self.config_path.exists():
            return
        self.write_log("config.json não encontrado; aguardando dados da primeira abertura.")
        result = {}
        event = threading.Event()
        def ask() -> None:
            token = simpledialog.askstring(APP_NAME, "Token GitHub somente leitura:", parent=self.root, show="*")
            repo = simpledialog.askstring(APP_NAME, "Nome do repositório (ex.: usuario/servidor-ff):", parent=self.root)
            if token and repo:
                result.update(github_token=token, repo=repo)
            event.set()
        self.root.after(0, ask)
        event.wait()
        if not result:
            raise RuntimeError("configuração não preenchida")
        self.config_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    def _headers(self, token: str) -> dict:
        return {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "ServidorFF"}

    def _get(self, url: str, token: str) -> bytes:
        req = urllib.request.Request(url, headers=self._headers(token))
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read()

    def _update(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        token, repo = config["github_token"], config["repo"]
        if not token or not repo:
            raise RuntimeError("github_token/repo ausentes")
        remote_version = int(self._get("https://raw.githubusercontent.com/%s/main/versao.txt" % repo, token).decode().strip())
        local_file = self.base / "versao.txt"
        local_version = int(local_file.read_text(encoding="utf-8").strip()) if local_file.exists() else 0
        self.write_log("Versão local %d; remota %d." % (local_version, remote_version))
        if remote_version <= local_version:
            return
        release = json.loads(self._get("https://api.github.com/repos/%s/releases/latest" % repo, token).decode("utf-8"))
        asset = next((a for a in release.get("assets", []) if a.get("name") == "servidor.zip"), None)
        if not asset:
            raise RuntimeError("asset servidor.zip não encontrado na Release")
        zip_data = self._get(asset["url"], token)
        with tempfile.TemporaryDirectory(prefix="servidor_ff_") as temp:
            zip_path = Path(temp) / "servidor.zip"
            zip_path.write_bytes(zip_data)
            extracted = Path(temp) / "extraido"
            extracted.mkdir()
            with zipfile.ZipFile(zip_path) as archive:
                for member in archive.infolist():
                    target = (extracted / member.filename).resolve()
                    if extracted.resolve() not in target.parents:
                        raise RuntimeError("zip inválido")
                archive.extractall(extracted)
            backup = self.base / ("servidor.backup-%s" % datetime.now().strftime("%Y%m%d-%H%M%S"))
            if self.server_dir.exists():
                shutil.move(str(self.server_dir), str(backup))
            shutil.move(str(extracted), str(self.server_dir))
        local_file.write_text(str(remote_version) + "\n", encoding="utf-8")
        self.write_log("Atualizado para versão %d; backup criado." % remote_version)

    def start_server(self) -> None:
        if self.process and self.process.poll() is None:
            return
        script = self.server_dir / "servidor.py"
        if not script.exists():
            self.write_log("Servidor local não encontrado: %s" % script)
            return
        self.process = subprocess.Popen([sys_executable(), str(script)], cwd=str(self.server_dir), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        threading.Thread(target=self._read_process_log, daemon=True).start()
        self.status.set("LIGADO")
        self.toggle.configure(text="Desligar")
        self.write_log("Servidor iniciado em %s" % self.endpoint.get())

    def _read_process_log(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.write_log(line)

    def stop_server(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.status.set("DESLIGADO")
        self.toggle.configure(text="Ligar")

    def toggle_server(self) -> None:
        if self.process and self.process.poll() is None:
            self.stop_server()
        else:
            self.start_server()

    def close(self) -> None:
        self.stop_server()
        self.root.destroy()


def sys_executable_dir() -> str:
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def sys_executable() -> str:
    import sys
    return sys.executable


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    app.endpoint.set("IP local: %s:8080" % local_ip())
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
