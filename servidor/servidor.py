#!/usr/bin/env python3
"""Servidor local mínimo para o protocolo explicitamente especificado."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import logging

HOST = "0.0.0.0"
PORT = 8080
BASE_DIR = Path(__file__).resolve().parent
PEDIDOS_LOG = BASE_DIR / "pedidos.log"


def varint(value: int) -> bytes:
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def campo_varint(numero: int, value: int) -> bytes:
    return varint((numero << 3) | 0) + varint(value)


def campo_texto(numero: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return varint((numero << 3) | 2) + varint(len(data)) + data


def resposta_major_login() -> bytes:
    return b"".join((
        campo_varint(1, 100000001),
        campo_texto(8, "token-local-v1"),
        campo_varint(9, 86400),
        campo_texto(10, "127.0.0.1:9001"),
        campo_varint(21, 0),
    ))


def resposta_login() -> bytes:
    return b"".join((
        campo_varint(1, 100000001),
        campo_texto(14, "127.0.0.1:9001"),
        campo_texto(32, "127.0.0.1:9002"),
    ))


class Handler(BaseHTTPRequestHandler):
    server_version = "ServidorFF/1.0"

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send("servidor ff v1 no ar".encode("utf-8"), "text/plain; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(size)
        with PEDIDOS_LOG.open("ab") as log:
            log.write(self.path.encode("utf-8", "replace") + b"\t" + body + b"\n")
        logging.info("%s tamanho=%d primeiros64=%s", self.path, len(body), body[:64].hex())

        if self.path.endswith("Ping"):
            response = b""
        elif self.path.endswith("MajorLogin"):
            response = resposta_major_login()
        elif self.path.endswith("Login"):
            response = resposta_login()
        else:
            response = b""
        self._send(response, "application/octet-stream")

    def log_message(self, fmt: str, *args) -> None:
        logging.info("HTTP " + fmt, *args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Servidor FF ouvindo em %s:%d", HOST, PORT)
    # TODO: formato da configuração de versão do jogo ainda desconhecido.
    # TODO: etapa de login do SDK ainda desconhecida.
    # TODO: servidor TCP do jogo/lobby ainda não especificado.
    with ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logging.info("Servidor FF encerrado")


if __name__ == "__main__":
    main()
