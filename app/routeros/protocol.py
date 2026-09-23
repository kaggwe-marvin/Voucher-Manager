"""
RouterOS binary API wire protocol.

Adapted from MikroTik's official python_api_fixed.py reference client.
This module should stay a faithful implementation of the wire protocol
(length-prefixed words, sentence framing, login handshake) and generally
shouldn't need to change — application logic belongs in client.py /
voucher_ops.py instead.
"""

import binascii
import hashlib
import socket
import ssl


class ApiRos:
    """Low-level RouterOS API session: word/sentence framing over a socket."""

    def __init__(self, sock):
        self.sk = sock

    def login(self, username, pwd):
        for reply, attrs in self.talk(["/login", "=name=" + username, "=password=" + pwd]):
            if reply == '!trap':
                return False
            if '=ret' in attrs:
                # Legacy pre-6.43 challenge/response auth
                chal = binascii.unhexlify(attrs['=ret'].encode('utf-8'))
                md = hashlib.md5()
                md.update(b'\x00')
                md.update(pwd.encode('utf-8'))
                md.update(chal)
                for reply2, _ in self.talk(
                    ["/login", "=name=" + username,
                     "=response=00" + binascii.hexlify(md.digest()).decode('utf-8')]):
                    if reply2 == '!trap':
                        return False
        return True

    def talk(self, words):
        if self.write_sentence(words) == 0:
            return []
        r = []
        while True:
            i = self.read_sentence()
            if not i:
                continue
            reply = i[0]
            attrs = {}
            for w in i[1:]:
                j = w.find('=', 1)
                if j == -1:
                    attrs[w] = ''
                else:
                    attrs[w[:j]] = w[j + 1:]
            r.append((reply, attrs))
            if reply in ('!done', '!trap'):
                return r

    def write_sentence(self, words):
        n = 0
        for w in words:
            self.write_word(w)
            n += 1
        self.write_word('')
        return n

    def read_sentence(self):
        r = []
        while True:
            w = self.read_word()
            if w == '':
                return r
            r.append(w)

    def write_word(self, w):
        data = w.encode('utf-8')
        self.write_len(len(data))
        self.write_bytes(data)

    def read_word(self):
        return self.read_str(self.read_len())

    def write_len(self, length):
        if length < 0x80:
            self.write_bytes(length.to_bytes(1, 'big'))
        elif length < 0x4000:
            self.write_bytes((length | 0x8000).to_bytes(2, 'big'))
        elif length < 0x200000:
            self.write_bytes((length | 0xC00000).to_bytes(3, 'big'))
        elif length < 0x10000000:
            self.write_bytes((length | 0xE0000000).to_bytes(4, 'big'))
        else:
            self.write_bytes(b'\xF0' + length.to_bytes(4, 'big'))

    def read_len(self):
        c = ord(self.read_bytes(1))
        if (c & 0x80) == 0x00:
            pass
        elif (c & 0xC0) == 0x80:
            c &= ~0xC0
            c = (c << 8) + ord(self.read_bytes(1))
        elif (c & 0xE0) == 0xC0:
            c &= ~0xE0
            c = (c << 8) + ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
        elif (c & 0xF0) == 0xE0:
            c &= ~0xF0
            c = (c << 8) + ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
        else:
            c = ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
            c = (c << 8) + ord(self.read_bytes(1))
        return c

    def write_bytes(self, data):
        n = 0
        while n < len(data):
            r = self.sk.send(data[n:])
            if r == 0:
                raise RuntimeError("connection closed by remote end")
            n += r

    def read_bytes(self, length):
        ret = b''
        while len(ret) < length:
            s = self.sk.recv(length - len(ret))
            if s == b'':
                raise RuntimeError("connection closed by remote end")
            ret += s
        return ret

    def read_str(self, length):
        return self.read_bytes(length).decode('utf-8', errors='replace') if length else ''


def open_socket(host, port, secure=False, verify_ssl=False, timeout=10):
    """Open a TCP (optionally TLS-wrapped) socket to the router's API service."""
    res = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    af, socktype, proto, _, sockaddr = res[0]
    s = socket.socket(af, socktype, proto)
    s.settimeout(timeout)
    try:
        if secure:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            if verify_ssl:
                ctx.verify_mode = ssl.CERT_REQUIRED
                ctx.load_default_certs()
            else:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=host)
        s.connect(sockaddr)
        s.settimeout(None)
        return s
    except Exception:
        s.close()
        raise
