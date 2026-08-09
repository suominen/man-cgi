#!/usr/bin/env python3
"""Minimal FastCGI responder for cache-revalidation experiments.

Listens on 127.0.0.1:9481 (the port also appears in nginx-base.conf
and drive; keep the three files in sync). Speaks just enough FastCGI
for nginx: BEGIN_REQUEST / PARAMS / STDIN in, STDOUT / END_REQUEST
out.

Behavior: emits a fixed Last-Modified and short Cache-Control.
If HTTP_IF_MODIFIED_SINCE matches the Last-Modified exactly, answers
304 with no body. Every completed request appends a line to
requests.log:
    <serial> <method> <uri> ims=<value-or-dash> -> <status>

requests.log is opened in append mode; the drive script removes it
at the start of each variant. Keep those two sides coupled.
"""

import socket
import struct
import sys

LM = "Fri, 02 Jan 2026 13:14:15 GMT"
MAX_AGE = 2

FCGI_BEGIN_REQUEST = 1
FCGI_END_REQUEST = 3
FCGI_PARAMS = 4
FCGI_STDIN = 5
FCGI_STDOUT = 6


def read_record(conn):
    hdr = b""
    while len(hdr) < 8:
        chunk = conn.recv(8 - len(hdr))
        if not chunk:
            return None
        hdr += chunk
    version, rtype, req_id, clen, plen, _ = struct.unpack(">BBHHBB", hdr)
    content = b""
    while len(content) < clen + plen:
        chunk = conn.recv(clen + plen - len(content))
        if not chunk:
            return None
        content += chunk
    return rtype, req_id, content[:clen]


def parse_params(blob):
    # latin-1 is byte-transparent: parameter values never raise.
    params = {}
    i = 0
    while i < len(blob):
        lengths = []
        for _ in range(2):
            n = blob[i]
            if n & 0x80:
                n = struct.unpack(">I", blob[i:i + 4])[0] & 0x7FFFFFFF
                i += 4
            else:
                i += 1
            lengths.append(n)
        klen, vlen = lengths
        params[blob[i:i + klen].decode("latin-1")] = \
            blob[i + klen:i + klen + vlen].decode("latin-1")
        i += klen + vlen
    return params


def send_record(conn, rtype, req_id, content):
    conn.sendall(struct.pack(">BBHHBB", 1, rtype, req_id, len(content), 0, 0)
                 + content)


def handle(conn, logf, state):
    params = {}
    req_id = 1
    complete = False
    while True:
        rec = read_record(conn)
        if rec is None:
            break
        rtype, req_id, content = rec
        if rtype == FCGI_PARAMS and content:
            params.update(parse_params(content))
        elif rtype == FCGI_STDIN and not content:
            complete = True
            break
    if not complete:
        # Aborted or stray connection: no response, no log line.
        conn.close()
        return
    state["serial"] += 1
    serial = state["serial"]
    ims = params.get("HTTP_IF_MODIFIED_SINCE", "")
    uri = params.get("REQUEST_URI", "?")
    method = params.get("REQUEST_METHOD", "?")
    if ims == LM:
        status = 304
        payload = (
            "Status: 304 Not Modified\r\n"
            f"Last-Modified: {LM}\r\n"
            f"Cache-Control: public, max-age={MAX_AGE}\r\n"
            "\r\n"
        ).encode()
    else:
        status = 200
        body = f"body serial={serial}\n"
        payload = (
            "Status: 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            f"Last-Modified: {LM}\r\n"
            f"Cache-Control: public, max-age={MAX_AGE}\r\n"
            "\r\n" + body
        ).encode()
    logf.write(f"{serial} {method} {uri} ims={ims or '-'} -> {status}\n")
    send_record(conn, FCGI_STDOUT, req_id, payload)
    send_record(conn, FCGI_STDOUT, req_id, b"")
    send_record(conn, FCGI_END_REQUEST, req_id,
                struct.pack(">IBBBB", 0, 0, 0, 0, 0))
    conn.close()


def main():
    logf = open("requests.log", "a", buffering=1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 9481))
    srv.listen(16)
    state = {"serial": 0}
    while True:
        conn, _ = srv.accept()
        try:
            handle(conn, logf, state)
        except (OSError, ValueError, IndexError, struct.error):
            # One bad connection must not end the run.
            try:
                conn.close()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
