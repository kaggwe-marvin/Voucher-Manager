"""
Ties together routeros.client / routeros.voucher_ops / pdf into the single
end-to-end batch: create users -> attach profile -> generate voucher ->
download HTML -> convert to PDF.

Deliberately has no Tkinter imports, so it can be unit tested or reused by
a non-GUI entry point later. The GUI (app.py) calls run_workflow() from a
worker thread and passes a log callback + the field values it collected.
"""

import os
import tempfile
from dataclasses import dataclass

from app.pdf import html_to_pdf
from app.routeros.client import connect_and_login
from app.routeros.voucher_ops import create_voucher_batch, download_voucher_html
from app.utils import random_string


@dataclass
class WorkflowParams:
    host: str
    port: int
    use_ssl: bool
    admin_user: str
    admin_pass: str
    count: int
    prefix: str
    group: str
    profile: str
    template: str
    remote_html: str
    save_path: str


@dataclass
class WorkflowResult:
    usernames: list
    save_path: str


def _write_created_users_sidecar(save_path, usernames):
    """Write a plain list of created usernames next to the intended PDF path.

    This is the recovery record if FTP download or PDF conversion fails
    after users were already created on the router — see the security note
    in the README about deleting these once vouchers are printed.
    """
    sidecar_path = os.path.splitext(save_path)[0] + "_created_users.txt"
    with open(sidecar_path, "w", encoding="utf-8") as f:
        f.write("\n".join(usernames) + "\n")


def run_workflow(params: WorkflowParams, log=lambda msg: None) -> WorkflowResult:
    """Run the full batch. Raises on any failure; logs progress via `log`."""

    if not (1 <= params.count <= 500):
        raise ValueError("Voucher count must be between 1 and 500.")
    if not params.group:
        raise ValueError("Pick a User Group (use Refresh to load groups from the router).")
    if not params.profile:
        raise ValueError("Pick a Profile (use Refresh to load profiles from the router).")

    log(f"Connecting to {params.host}:{params.port} (ssl={params.use_ssl})...")
    sock, api = connect_and_login(params.host, params.port, params.use_ssl,
                                   params.admin_user, params.admin_pass)
    log("Logged in.")

    def make_username():
        return f"{params.prefix}-{random_string(5)}" if params.prefix else random_string(6)

    try:
        usernames, ids = create_voucher_batch(
            api,
            count=params.count,
            prefix=params.prefix,
            group=params.group,
            profile=params.profile,
            template=params.template,
            make_username=make_username,
            make_password=lambda: random_string(6),
            log=log,
        )
    finally:
        sock.close()

    # Persist the created usernames locally *before* attempting FTP/PDF, so
    # a failure downstream (bad FTP path, no browser found, etc.) never
    # leaves accounts that were actually created on the router with no
    # local record of their names.
    _write_created_users_sidecar(params.save_path, usernames)

    tmp_html = os.path.join(tempfile.gettempdir(), f"vouchers_{random_string(4)}.html")
    log(f"Downloading {params.remote_html} via FTP...")
    download_voucher_html(
        host=params.host,
        ftp_user=params.admin_user,
        ftp_pwd=params.admin_pass,
        remote_path=params.remote_html,
        local_path=tmp_html,
        log=log,
    )
    log(f"Downloaded to {tmp_html}")

    log("Converting to PDF...")
    html_to_pdf(tmp_html, params.save_path)
    log(f"Saved PDF: {params.save_path}")

    return WorkflowResult(usernames=usernames, save_path=params.save_path)
