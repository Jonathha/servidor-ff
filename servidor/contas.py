#!/usr/bin/env python3
"""Contas locais do servidor privado FF.

Armazena as contas em contas.json, na mesma pasta deste módulo.
A senha nunca é guardada em texto puro: só o hash SHA-256 com salt
individual por conta, no formato "salt$hash" dentro de senha_hash.
Somente biblioteca padrão.
"""

import hashlib
import hmac
import json
import secrets
import threading
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "contas.json"
PRIMEIRO_ACCOUNT_ID = 100000001
_LOCK = threading.RLock()


def _carregar() -> list:
    if not ARQUIVO.exists():
        return []
    try:
        dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return dados if isinstance(dados, list) else []


def _salvar(contas: list) -> None:
    ARQUIVO.write_text(json.dumps(contas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _hash(salt: str, senha: str) -> str:
    return hashlib.sha256((salt + senha).encode("utf-8")).hexdigest()


def _novo_senha_hash(senha: str) -> str:
    salt = secrets.token_hex(16)
    return salt + "$" + _hash(salt, senha)


def _confere(senha_hash: str, senha: str) -> bool:
    try:
        salt, esperado = senha_hash.split("$", 1)
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(_hash(salt, senha), esperado)


def _buscar_por_usuario(contas: list, usuario: str):
    alvo = usuario.lower()
    for conta in contas:
        if str(conta.get("usuario", "")).lower() == alvo:
            return conta
    return None


def _buscar_por_id(contas: list, account_id):
    for conta in contas:
        if conta.get("account_id") == account_id:
            return conta
    return None


def criar_conta(usuario, senha):
    """Cria a conta. Retorna (ok, erro): erro é None em caso de sucesso."""
    if not usuario or not str(usuario).strip():
        return False, "usuario_vazio"
    if not senha:
        return False, "senha_vazia"
    usuario = str(usuario).strip()
    with _LOCK:
        contas = _carregar()
        if _buscar_por_usuario(contas, usuario) is not None:
            return False, "usuario_duplicado"
        proximo = PRIMEIRO_ACCOUNT_ID
        for conta in contas:
            try:
                proximo = max(proximo, int(conta.get("account_id", 0)) + 1)
            except (TypeError, ValueError):
                continue
        contas.append({
            "usuario": usuario,
            "senha_hash": _novo_senha_hash(str(senha)),
            "account_id": proximo,
            "nick": None,
        })
        _salvar(contas)
    return True, None


def verificar(usuario, senha):
    """Retorna o account_id se usuário/senha conferem, senão None."""
    if not usuario or senha is None:
        return None
    with _LOCK:
        conta = _buscar_por_usuario(_carregar(), str(usuario).strip())
    if conta is None:
        return None
    if _confere(str(conta.get("senha_hash", "")), str(senha)):
        return conta.get("account_id")
    return None


def emitir_token(account_id):
    """Gera um access_token novo pra conta, guardando no lugar do anterior.

    Retorna o token, ou None se a conta não existe. É este token que o
    login PRIVATE-NV entrega ao jogo como accessToken do LoginResp.
    """
    token = secrets.token_hex(16)
    with _LOCK:
        contas = _carregar()
        conta = _buscar_por_id(contas, account_id)
        if conta is None:
            return None
        conta["access_token"] = token
        _salvar(contas)
    return token


def verificar_token(account_id, token) -> bool:
    """True se o token é o access_token atual da conta."""
    if not token or not isinstance(token, str):
        return False
    with _LOCK:
        conta = _buscar_por_id(_carregar(), account_id)
    if conta is None:
        return False
    atual = conta.get("access_token")
    if not atual or not isinstance(atual, str):
        return False
    return hmac.compare_digest(atual, token)


def obter_conta(account_id):
    """Retorna uma cópia da conta (sem uso externo do hash) ou None."""
    with _LOCK:
        conta = _buscar_por_id(_carregar(), account_id)
    return dict(conta) if conta is not None else None


def listar_contas() -> list:
    """Lista pública das contas: usuário, account_id e nick (sem hash)."""
    with _LOCK:
        contas = _carregar()
    return [
        {"usuario": c.get("usuario"), "account_id": c.get("account_id"), "nick": c.get("nick")}
        for c in contas
    ]


def limpar_nick(nick) -> str:
    """Regra do cliente original: espaços e quebras de linha são removidos."""
    if nick is None:
        return ""
    return str(nick).replace(" ", "").replace("\n", "").replace("\r", "")


def definir_nick(account_id, nick):
    """Define o nick da conta. Retorna (ok, codigo_erro).

    Regras provadas no cliente OB55: nick limpo (sem espaços/\\n) antes de
    validar; mínimo 3, máximo 12; não pode ser só dígitos; não pode repetir
    o nick de outra conta.
    """
    with _LOCK:
        contas = _carregar()
        conta = _buscar_por_id(contas, account_id)
        if conta is None:
            return False, "conta_inexistente"
        nick = limpar_nick(nick)
        if not nick:
            return False, "vazio"
        if len(nick) < 3:
            return False, "curto"
        if len(nick) > 12:
            return False, "longo"
        if nick.isdigit():
            return False, "so_digitos"
        alvo = nick.lower()
        for outra in contas:
            if outra.get("account_id") == account_id:
                continue
            nick_outra = outra.get("nick")
            if nick_outra and str(nick_outra).lower() == alvo:
                return False, "duplicado"
        conta["nick"] = nick
        _salvar(contas)
    return True, None
