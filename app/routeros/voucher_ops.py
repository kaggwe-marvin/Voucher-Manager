"""
The actual business logic of this tool: creating User Manager accounts,
attaching them to a profile, generating vouchers for them, and pulling the
resulting HTML off the router via FTP.

Kept independent of Tkinter so it can be tested/driven headlessly (e.g. a
future CLI or scheduled-task mode) — the GUI layer just calls into this.
"""

import ftplib
import time


def noop_log(_msg):
    """Default no-op logger used when the caller doesn't care about progress output."""
    pass


def create_user(api, username, password, group):
    """Create a single user-manager account. Returns its router .id."""
    resp = api.talk([
        "/user-manager/user/add",
        "=name=" + username,
        "=password=" + password,
        "=group=" + group,
    ])
    new_id = None
    for reply, attrs in resp:
        if reply == '!trap':
            raise RuntimeError(f"Router rejected user {username}: {attrs}")
        if reply == '!done' and '=ret' in attrs:
            new_id = attrs['=ret']
    if not new_id:
        raise RuntimeError(f"User {username} was created but no .id was returned by the router.")
    return new_id


def attach_profile(api, username, profile):
    """Attach an existing user-manager account to a profile."""
    resp = api.talk([
        "/user-manager/user-profile/add",
        "=user=" + username,
        "=profile=" + profile,
    ])
    for reply, attrs in resp:
        if reply == '!trap':
            raise RuntimeError(f"Could not attach profile to {username}: {attrs}")


def generate_voucher(api, ids, template):
    """Trigger voucher generation for a list of user .ids using an existing template."""
    resp = api.talk([
        "/user-manager/user/generate-voucher",
        "=numbers=" + ",".join(ids),
        "=voucher-template=" + template,
    ])
    for reply, attrs in resp:
        if reply == '!trap':
            raise RuntimeError(f"generate-voucher failed: {attrs}")


def create_voucher_batch(api, count, prefix, group, profile, template, make_username, make_password, log=noop_log):
    """
    Create `count` users, attach them to `profile`, and request voucher
    generation for exactly those accounts.

    make_username()/make_password() are injected so callers control the
    random-string scheme (keeps this module free of randomness policy).

    Returns (usernames, ids) for everything successfully created — even on
    a later failure, the caller gets back what was already created on the
    router so nothing is silently orphaned.
    """
    created = []
    created_ids = []
    for _ in range(count):
        uname = make_username()
        vpwd = make_password()

        new_id = create_user(api, uname, vpwd, group)
        attach_profile(api, uname, profile)

        created.append(uname)
        created_ids.append(new_id)
        log(f"Created user {uname} (id {new_id}, profile: {profile})")

    log(f"Requesting voucher generation for {len(created)} users...")
    generate_voucher(api, created_ids, template)
    log("Voucher generation requested.")

    return created, created_ids


def download_voucher_html(host, ftp_user, ftp_pwd, remote_path, local_path,
                           retries=5, delay_seconds=2, log=noop_log):
    """
    Download the router-generated voucher HTML via FTP, retrying a few times
    since the file may not be written yet immediately after generate-voucher
    returns.
    """
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with ftplib.FTP() as ftp:
                ftp.connect(host, 21, timeout=15)
                ftp.login(ftp_user, ftp_pwd)
                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {remote_path}", f.write)
            return
        except ftplib.all_errors as e:
            last_err = e
            log(f"  attempt {attempt}/{retries}: file not ready yet ({e}), retrying in {delay_seconds}s...")
            time.sleep(delay_seconds)
    raise RuntimeError(f"Could not download {remote_path} after {retries} attempts: {last_err}")
