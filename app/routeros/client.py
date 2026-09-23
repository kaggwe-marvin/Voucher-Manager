"""
Thin convenience layer on top of protocol.ApiRos: connecting, logging in,
and running simple /.../print queries. Nothing here is voucher-specific.
"""

from .protocol import ApiRos, open_socket


def connect_and_login(host, port, use_ssl, user, pwd, timeout=10):
    """Open a socket + ApiRos + login in one call. Caller must close the socket."""
    sock = open_socket(host, port, secure=use_ssl, verify_ssl=False, timeout=timeout)
    api = ApiRos(sock)
    if not api.login(user, pwd):
        sock.close()
        raise RuntimeError("Login failed — check username/password/API service.")
    return sock, api


def fetch_names(api, path, name_key="=name"):
    """Run a /.../print and return the list of =name values from the response."""
    resp = api.talk([path])
    names = []
    for reply, attrs in resp:
        if reply == '!trap':
            raise RuntimeError(f"{path} failed: {attrs}")
        if reply == '!re' and name_key in attrs:
            names.append(attrs[name_key])
    return names
