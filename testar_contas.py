#!/usr/bin/env python3
"""Testes do sistema de contas do Servidor FF.

Sobe uma CÓPIA temporária da pasta servidor/ numa porta de teste e
verifica os endpoints /private/*, /health e Ping com urllib.
Somente biblioteca padrão.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PORTA = 18080
BASE = "http://127.0.0.1:%d" % PORTA

falhas = []
total = 0


def caso(nome, condicao, detalhe=""):
    global total
    total += 1
    if condicao:
        print("PASS  %s" % nome)
    else:
        print("FAIL  %s  %s" % (nome, detalhe))
        falhas.append(nome)


def post_json(caminho, dados):
    req = urllib.request.Request(
        BASE + caminho,
        data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8")
        try:
            return e.code, json.loads(corpo)
        except ValueError:
            return e.code, {}


def post_raw(caminho, dados=b""):
    req = urllib.request.Request(BASE + caminho, data=dados, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def get(caminho):
    try:
        with urllib.request.urlopen(BASE + caminho, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def esperar_no_ar(proc, limite=15.0):
    fim = time.time() + limite
    while time.time() < fim:
        if proc.poll() is not None:
            return False
        try:
            status, _ = get("/health")
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def main():
    tmp = Path(tempfile.mkdtemp(prefix="servidor_ff_teste_"))
    proc = None
    try:
        destino = tmp / "servidor"
        shutil.copytree(
            RAIZ / "servidor",
            destino,
            ignore=shutil.ignore_patterns("contas.json", "pedidos.log", "__pycache__"),
        )
        # Porta de teste só na cópia temporária.
        alvo = destino / "servidor.py"
        texto = alvo.read_text(encoding="utf-8")
        assert "PORT = 8080" in texto, "linha PORT nao encontrada na copia"
        alvo.write_text(texto.replace("PORT = 8080", "PORT = %d" % PORTA), encoding="utf-8")

        proc = subprocess.Popen(
            [sys.executable, "servidor.py"],
            cwd=str(destino),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not esperar_no_ar(proc):
            print("FAIL  servidor de teste nao subiu")
            return 1

        # /health e Ping continuam respondendo
        status, corpo = get("/health")
        caso("health responde", status == 200 and b"servidor ff v1 no ar" in corpo, str(status))
        status, corpo = post_raw("/Ping")
        caso("Ping responde vazio", status == 200 and corpo == b"", str(status))

        # Criar conta
        status, d = post_json("/private/criar-conta", {"usuario": "jogador1", "senha": "senha123"})
        caso("criar conta ok", status == 200 and d.get("ok") is True and d.get("account_id") == 100000001, str((status, d)))
        id1 = d.get("account_id")

        status, d = post_json("/private/criar-conta", {"usuario": "JOGADOR1", "senha": "outra"})
        caso("criar duplicada recusa", status == 400 and d.get("ok") is False, str((status, d)))

        status, d = post_json("/private/criar-conta", {"usuario": "", "senha": "x"})
        caso("criar sem usuario recusa", status == 400 and d.get("ok") is False, str((status, d)))

        # Login
        status, d = post_json("/private/login", {"usuario": "jogador1", "senha": "senha123"})
        caso("login senha certa aceita", status == 200 and d.get("ok") is True and d.get("account_id") == id1 and d.get("nick") is None, str((status, d)))

        status, d = post_json("/private/login", {"usuario": "jogador1", "senha": "errada"})
        caso("login senha errada 401", status == 401 and d.get("erro") == "credenciais_invalidas", str((status, d)))

        # Access token: login emite, verificar-token aceita o emitido e recusa outro
        status, d = post_json("/private/login", {"usuario": "jogador1", "senha": "senha123"})
        token1 = d.get("access_token")
        caso("login devolve access_token nao-vazio", status == 200 and isinstance(token1, str) and len(token1) >= 16, str((status, d)))

        status, d = post_json("/private/verificar-token", {"account_id": id1, "access_token": token1})
        caso("verificar-token aceita o token emitido", status == 200 and d.get("ok") is True, str((status, d)))

        status, d = post_json("/private/verificar-token", {"account_id": id1, "access_token": "token-errado"})
        caso("verificar-token recusa token errado", status == 401 and d.get("ok") is False, str((status, d)))

        # Novo login substitui o token anterior
        status, d = post_json("/private/login", {"usuario": "jogador1", "senha": "senha123"})
        token2 = d.get("access_token")
        caso("novo login emite token novo", status == 200 and isinstance(token2, str) and token2 != token1, str((status, d)))

        status, d = post_json("/private/verificar-token", {"account_id": id1, "access_token": token1})
        caso("token antigo nao vale mais", status == 401 and d.get("ok") is False, str((status, d)))

        status, d = post_json("/private/verificar-token", {"account_id": id1, "access_token": token2})
        caso("verificar-token aceita o token novo", status == 200 and d.get("ok") is True, str((status, d)))

        # Nick válido
        status, d = post_json("/private/definir-nick", {"account_id": id1, "nick": "CapitaoFF"})
        caso("nick valido ok", status == 200 and d.get("ok") is True, str((status, d)))

        status, d = post_json("/private/login", {"usuario": "jogador1", "senha": "senha123"})
        caso("login devolve nick", status == 200 and d.get("nick") == "CapitaoFF", str((status, d)))

        # Nick curto / longo / só dígitos
        status, d = post_json("/private/definir-nick", {"account_id": id1, "nick": "ab"})
        caso("nick 2 caracteres recusa 'curto'", status == 400 and d.get("erro") == "curto", str((status, d)))

        status, d = post_json("/private/definir-nick", {"account_id": id1, "nick": "a" * 13})
        caso("nick 13 caracteres recusa 'longo'", status == 400 and d.get("erro") == "longo", str((status, d)))

        status, d = post_json("/private/definir-nick", {"account_id": id1, "nick": "12345"})
        caso("nick so digitos recusa", status == 400 and d.get("erro") == "so_digitos", str((status, d)))

        # Segunda conta: nick com espaços é limpo e aceito; repetir nick da outra recusa
        status, d = post_json("/private/criar-conta", {"usuario": "jogador2", "senha": "senha456"})
        id2 = d.get("account_id")
        caso("segunda conta criada", status == 200 and id2 == 100000002, str((status, d)))

        status, d = post_json("/private/definir-nick", {"account_id": id2, "nick": " Meu Nick "})
        caso("nick com espacos limpo e aceito", status == 200 and d.get("ok") is True, str((status, d)))

        status, d = post_json("/private/login", {"usuario": "jogador2", "senha": "senha456"})
        caso("nick limpo foi guardado", status == 200 and d.get("nick") == "MeuNick", str((status, d)))

        status, d = post_json("/private/definir-nick", {"account_id": id2, "nick": "capitaoff"})
        caso("nick igual ao de outra conta recusa 'duplicado'", status == 400 and d.get("erro") == "duplicado", str((status, d)))

        status, d = post_json("/private/definir-nick", {"account_id": 999999999, "nick": "Qualquer1"})
        caso("conta inexistente recusa", status == 400 and d.get("erro") == "conta_inexistente", str((status, d)))

        # Senha não fica em texto puro no contas.json da cópia de teste
        contas_json = (destino / "contas.json").read_text(encoding="utf-8")
        caso("senha nao esta em texto puro", "senha123" not in contas_json and "senha456" not in contas_json)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if falhas:
        print("FALHARAM %d de %d casos:" % (len(falhas), total))
        for nome in falhas:
            print(" -", nome)
        return 1
    print("OK: todos os %d casos passaram" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
