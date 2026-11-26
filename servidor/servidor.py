#!/usr/bin/env python3
"""HTTP MiddleLogin e transporte TCP TCPSession2 do servidor local."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import logging
import secrets
import socket
import struct
import threading
import time
import urllib.request

HOST = "0.0.0.0"
PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
PEDIDOS_LOG = BASE_DIR / "pedidos.log"
CONFIG_FILE = ROOT_DIR / "config.json"
SESSIONS = {}
SESSIONS_LOCK = threading.RLock()
TCP_STOP = threading.Event()
STARTED_AT = ""


def varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def campo_varint(numero: int, value: int) -> bytes:
    return varint(numero << 3) + varint(value)


def campo_bytes(numero: int, value: bytes) -> bytes:
    return varint((numero << 3) | 2) + varint(len(value)) + value


def campo_texto(numero: int, value: str) -> bytes:
    return campo_bytes(numero, value.encode("utf-8"))


def resposta_major_login(account_id: int, token: str, kts: int, ak: bytes, aiv: bytes, server_url: str) -> bytes:
    return b"".join((campo_varint(1, account_id), campo_texto(8, token), campo_varint(9, 86400), campo_texto(10, server_url), campo_varint(21, kts), campo_bytes(22, ak), campo_bytes(23, aiv)))


def resposta_login(account_id: int, lobby_url: str, chat_url: str) -> bytes:
    return b"".join((campo_varint(1, account_id), campo_texto(14, lobby_url), campo_texto(32, chat_url)))


# AES-128 ECB puro, usado somente no Data c2s do Fluxo A.
SBOX = (
    99,124,119,123,242,107,111,197,48,1,103,43,254,215,171,118,202,130,201,125,250,89,71,240,173,212,162,175,156,164,114,192,
    183,253,147,38,54,63,247,204,52,165,229,241,113,216,49,21,4,199,35,195,24,150,5,154,7,18,128,226,235,39,178,117,
    9,131,44,26,27,110,90,160,82,59,214,179,41,227,47,132,83,209,0,237,32,252,177,91,106,203,190,57,74,76,88,207,208,239,170,251,67,77,51,133,69,249,2,127,80,60,159,168,81,163,64,143,146,157,56,245,188,182,218,33,16,255,243,210,205,12,19,236,95,151,68,23,196,167,126,61,100,93,25,115,96,129,79,220,34,42,144,136,70,238,184,20,222,94,11,219,224,50,58,10,73,6,36,92,194,211,172,98,145,149,228,121,231,200,55,109,141,213,78,169,108,86,244,234,101,122,174,8,186,120,37,46,28,166,180,198,232,221,116,31,75,189,139,138,112,62,181,102,72,3,246,14,97,53,87,185,134,193,29,158,225,248,152,17,105,217,142,148,155,30,135,233,206,85,40,223,140,161,137,13,191,230,66,104,65,153,45,15,176,84,187,22
)
INV_SBOX = [0] * 256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i


def _gmul(a: int, b: int) -> int:
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        a = ((a << 1) ^ (0x11B if a & 0x80 else 0)) & 0xFF
        b >>= 1
    return result


def _round_keys(key: bytes):
    key = bytes(key[:16]).ljust(16, b"\0")
    words = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        word = words[i - 1][:]
        if i % 4 == 0:
            word = [SBOX[x] for x in word[1:] + word[:1]]
            word[0] ^= rcon
            rcon = _gmul(rcon, 2)
        words.append([words[i - 4][j] ^ word[j] for j in range(4)])
    return [sum((words[4 * r + c] for c in range(4)), []) for r in range(11)]


def _add_key(state, key):
    return [a ^ b for a, b in zip(state, key)]


def _shift_rows(state, inverse=False):
    out = [0] * 16
    for row in range(4):
        for col in range(4):
            src = ((col + row) if not inverse else (col - row)) % 4
            out[4 * col + row] = state[4 * src + row]
    return out


def _mix_columns(state, inverse=False):
    out = [0] * 16
    for col in range(4):
        a = state[4 * col:4 * col + 4]
        if not inverse:
            factors = (2, 3, 1, 1)
        else:
            factors = (14, 11, 13, 9)
        for row in range(4):
            out[4 * col + row] = (_gmul(a[row], factors[0]) ^ _gmul(a[(row + 1) % 4], factors[1]) ^ _gmul(a[(row + 2) % 4], factors[2]) ^ _gmul(a[(row + 3) % 4], factors[3]))
    return out


def aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    if len(data) % 16:
        raise ValueError("Data TCP não alinhado em blocos AES")
    keys = _round_keys(key)
    result = bytearray()
    for offset in range(0, len(data), 16):
        state = _add_key(list(data[offset:offset + 16]), keys[10])
        for rnd in range(9, 0, -1):
            state = [INV_SBOX[x] for x in _shift_rows(state, True)]
            state = _add_key(state, keys[rnd])
            state = _mix_columns(state, True)
        state = [INV_SBOX[x] for x in _shift_rows(state, True)]
        result.extend(_add_key(state, keys[0]))
    return bytes(result)


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    except (OSError, ValueError):
        return {}


def save_request(path: str, body: bytes) -> None:
    with PEDIDOS_LOG.open("ab") as log:
        log.write(path.encode("utf-8", "replace") + b"\t" + body + b"\n")
    logging.info("%s tamanho=%d primeiros64=%s", path, len(body), body[:64].hex())


def verify_middle_login(body: bytes) -> tuple[int, str] | None:
    # Os fios do pedido ainda não foram confirmados. Os offsets +0xa8/+0xe0
    # são offsets de objeto IL2CPP, não números de fio protobuf. Recusar aqui
    # evita aceitar um token sem prova e mantém a lacuna explícita.
    logging.warning("MiddleLogin recusado: fios de openID/accessToken do pedido ainda não confirmados; corpo preservado para análise")
    return None


def verify_worker(account_id: int, access_token: str) -> bool:
    config = load_config()
    url = str(config.get("worker_private_url", "")).strip()
    if not url:
        logging.error("Worker não configurado: worker_private_url ausente")
        return False
    request_body = json.dumps({"acao": "verificar-token", "account_id": account_id, "access_token": access_token}).encode("utf-8")
    request = urllib.request.Request(url, data=request_body, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ServidorFF"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        return bool(result.get("success") and result.get("valid") and int(result.get("account_id")) == account_id)
    except Exception as exc:
        logging.error("Falha ao verificar token no Worker: %s", exc)
        return False


def issue_session(account_id: int, access_token: str) -> dict:
    kts = int(time.time())
    session = {"account_id": account_id, "access_token": access_token, "kts": kts, "watermark": 0, "ak": secrets.token_bytes(16), "aiv": secrets.token_bytes(16), "expires": time.time() + 86400}
    with SESSIONS_LOCK:
        SESSIONS[account_id] = session
    return session


class Handler(BaseHTTPRequestHandler):
    server_version = "ServidorFF/1.1"

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send("servidor ff v1 no ar".encode(), "text/plain; charset=utf-8")
        elif self.path == "/ver":
            self._send(b"/ver aberto: formato HTTPVerGet ainda nao confirmado", "text/plain; charset=utf-8", 501)
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        save_request(self.path, body)
        if self.path.endswith("Ping"):
            self._send(b"", "application/octet-stream")
            return
        if self.path.endswith("MajorLogin") or self.path.endswith("Login"):
            credentials = verify_middle_login(body)
            if credentials is None:
                self._send(b"", "application/octet-stream", 401)
                return
            account_id, access_token = credentials
            if not verify_worker(account_id, access_token):
                self._send(b"", "application/octet-stream", 401)
                return
            session = issue_session(account_id, access_token)
            config = load_config()
            public_host = str(config.get("public_host", "")).strip()
            tcp_port = int(config.get("tcp_port", 0) or 0)
            server_url = "%s:%d" % (public_host, tcp_port) if public_host and tcp_port else ""
            if self.path.endswith("MajorLogin"):
                self._send(resposta_major_login(account_id, "token-local-v1", session["kts"], session["ak"], session["aiv"], server_url), "application/octet-stream")
            else:
                self._send(resposta_login(account_id, server_url, server_url), "application/octet-stream")
            return
        self._send(b"", "application/octet-stream")

    def log_message(self, fmt: str, *args) -> None:
        logging.info("HTTP " + fmt, *args)


def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("conexão encerrada")
        data.extend(chunk)
    return bytes(data)


def send_s2c(sock: socket.socket, cmd: int, data: bytes = b"") -> None:
    if cmd == 2:
        sock.sendall(b"\x02")
        return
    sock.sendall(bytes([cmd]) + struct.pack(">I", len(data)) + data)


def handle_tcp_client(sock: socket.socket, address) -> None:
    account_id = None
    try:
        sock.settimeout(15)
        cmd = recv_exact(sock, 1)[0]
        region = recv_exact(sock, 1)[0]
        if not 101 <= cmd <= 150:
            logging.warning("TCP recusado %s: cmd init fora da faixa (%d)", address, cmd)
            return
        init = recv_exact(sock, 16)
        account_id, kts, watermark = struct.unpack(">QII", init)
        with SESSIONS_LOCK:
            session = SESSIONS.get(account_id)
        if not session or session["expires"] < time.time() or session["kts"] != kts:
            logging.warning("TCP recusado %s: sessão não emitida para account_id=%d", address, account_id)
            return
        length = struct.unpack(">I", recv_exact(sock, 4))[0]
        if length > 16 * 1024 * 1024:
            return
        data = recv_exact(sock, length) if length else b""
        if data:
            aes_ecb_decrypt(data, session["ak"])
        logging.info("TCP Fluxo A autorizado account_id=%d region=%d watermark=%d", account_id, region, watermark)
        # O envelope/payload de lobby não foi especificado. Envie apenas o
        # heartbeat documentado e não invente um pacote de lobby.
        send_s2c(sock, 0x02, b"")
        while not TCP_STOP.is_set():
            cmd = recv_exact(sock, 1)[0]
            if cmd == 2:
                recv_exact(sock, 1)
                continue
            length = struct.unpack(">I", recv_exact(sock, 4))[0]
            if length > 16 * 1024 * 1024:
                return
            payload = recv_exact(sock, length) if length else b""
            if 3 <= cmd <= 55 and payload:
                aes_ecb_decrypt(payload, session["ak"])
    except (ConnectionError, OSError, ValueError) as exc:
        logging.info("TCP encerrado account_id=%s motivo=%s", account_id, exc)
    finally:
        try:
            sock.close()
        except OSError:
            pass


def tcp_server(host: str, port: int) -> None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((host, port))
            listener.listen(64)
            listener.settimeout(1)
            logging.info("TCP Fluxo A ouvindo em %s:%d", host, port)
            while not TCP_STOP.is_set():
                try:
                    client, address = listener.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=handle_tcp_client, args=(client, address), daemon=True).start()
    except OSError as exc:
        logging.error("TCP Fluxo A não iniciou: %s", exc)


def status_heartbeat() -> None:
    first = True
    while first or not TCP_STOP.wait(30):
        first = False
        config = load_config()
        url = str(config.get("worker_private_url", "")).strip()
        secret = str(config.get("private_server_status_secret", ""))
        if not url or not secret:
            return
        payload = json.dumps({"acao": "server-status", "status": "online", "started_at": STARTED_AT, "status_secret": secret}).encode()
        try:
            request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "ServidorFF"}, method="POST")
            with urllib.request.urlopen(request, timeout=8) as response:
                if response.status != 200:
                    logging.warning("Aviso de status recusado pelo Worker: HTTP %s", response.status)
        except Exception as exc:
            logging.warning("Aviso de status não enviado: %s", exc)


def main() -> None:
    global STARTED_AT
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    STARTED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config = load_config()
    logging.info("Servidor FF ouvindo em %s:%d", HOST, PORT)
    tcp_port = int(config.get("tcp_port", 0) or 0)
    public_host = str(config.get("public_host", "")).strip()
    if tcp_port and public_host:
        threading.Thread(target=tcp_server, args=(HOST, tcp_port), daemon=True).start()
    else:
        logging.warning("TCP Fluxo A desligado: preencha public_host e tcp_port no config.json")
    threading.Thread(target=status_heartbeat, daemon=True).start()
    # TODO: formato HTTPVerGet do /ver ainda não confirmado.
    # TODO: Fluxo B e seus produtores continuam abertos.
    # TODO: os fios do pedido MiddleLogin ainda precisam de captura real.
    with ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info("Servidor FF encerrado")
        finally:
            TCP_STOP.set()


if __name__ == "__main__":
    main()
