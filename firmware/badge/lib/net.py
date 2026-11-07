"""Small HTTPS GET for apps (no `requests`: it crashed the badge reading
image bodies). Same client as apps/xkcd.py, which still has its own copy
that raises SkipComic.
"""

import socket
import ssl

USER_AGENT = b"BillboardBadge/1.0 (MicroPython)"


def https_get(url, max_bytes=65536, redirects=3):
    """Minimal HTTPS GET returning the body as a bytearray.

    MicroPython's requests crashed the badge reading image bodies, so this
    talks to the socket directly: the size comes from Content-Length and the
    body is read into one buffer allocated up front.
    """
    if not url.startswith("https://"):
        raise ValueError("not https: " + url)
    host, _, path = url[8:].partition("/")
    addr = socket.getaddrinfo(host, 443)[0][-1]
    sock = socket.socket()
    try:
        sock.settimeout(20)
        sock.connect(addr)
        sock = ssl.wrap_socket(sock, server_hostname=host)
        sock.write(
            b"GET /" + path.encode() + b" HTTP/1.0\r\nHost: " + host.encode()
            + b"\r\nUser-Agent: " + USER_AGENT + b"\r\nConnection: close\r\n\r\n"
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = sock.read(512)
            if not chunk:
                raise OSError("connection closed in headers")
            head += chunk
            if len(head) > 16384:
                raise OSError("headers too long")
        split = head.index(b"\r\n\r\n")
        body_start, head = head[split + 4:], head[:split].decode()
        lines = head.split("\r\n")
        status = int(lines[0].split(" ")[1])
        fields = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            fields[k.strip().lower()] = v.strip()
        if status in (301, 302, 303, 307, 308) and redirects and "location" in fields:
            sock.close()
            return https_get(fields["location"], max_bytes, redirects - 1)
        if status != 200:
            raise OSError("HTTP %d for %s" % (status, url))

        length = int(fields.get("content-length", "-1"))
        if length > max_bytes:
            raise ValueError("too big: %d bytes" % length)
        if length >= 0:
            body = bytearray(length)
            body[:len(body_start)] = body_start
            mv = memoryview(body)
            got = len(body_start)
            while got < length:
                n = sock.readinto(mv[got:])
                if not n:
                    raise OSError("connection closed after %d of %d bytes" % (got, length))
                got += n
            return body
        body = bytearray(body_start)  # no Content-Length: read to EOF
        while True:
            chunk = sock.read(4096)
            if not chunk:
                return body
            body.extend(chunk)
            if len(body) > max_bytes:
                raise ValueError("too big: over %d bytes" % max_bytes)
    finally:
        sock.close()
