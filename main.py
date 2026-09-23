import binascii
import ftplib
import hashlib
import os
import random
import re
import shutil
import socket
import ssl
import string
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

SENSITIVE_PATTERN = re.compile(r'(=password=|=response=)(.+)', re.IGNORECASE)


def mask(word):
    return SENSITIVE_PATTERN.sub(r'\1***', word)


# ---------------------------------------------------------------------------
# RouterOS binary API client (adapted from MikroTik's official reference)
# ---------------------------------------------------------------------------

class ApiRos:
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def random_string(length=6, chars=string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"):
    return ''.join(random.choice(chars) for _ in range(length))


def find_browser():
    candidates = []
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        for name in ("microsoft-edge", "google-chrome", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return c
    return None


def html_to_pdf(html_path, pdf_path):
    browser = find_browser()
    if not browser:
        raise RuntimeError("No Edge/Chrome install found for PDF conversion.")
    file_uri = "file:///" + html_path.replace("\\", "/")
    cmd = [
        browser, "--headless", "--disable-gpu",
        f"--print-to-pdf={pdf_path}", "--no-margins", file_uri
    ]
    subprocess.run(cmd, check=True)


def set_windows_startup(enable, script_path):
    task_name = "RouterVoucherManager"
    if enable:
        pythonw = shutil.which("pythonw") or sys.executable
        cmd = f'schtasks /Create /TN "{task_name}" /TR "\\"{pythonw}\\" \\"{script_path}\\"" /SC ONLOGON /F'
        subprocess.run(cmd, shell=True, check=False)
    else:
        subprocess.run(f'schtasks /Delete /TN "{task_name}" /F', shell=True, check=False)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class VoucherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RouterOS Voucher Manager")
        self.geometry("560x700")
        self.minsize(520, 480)
        self.resizable(True, True)
        self._build_form()

    def _row(self, parent, label, default="", show=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=15, pady=4)
        ttk.Label(frame, text=label, width=22).pack(side="left")
        var = tk.StringVar(value=default)
        entry = ttk.Entry(frame, textvariable=var, show=show)
        entry.pack(side="left", fill="x", expand=True)
        return var

    def _combo_row(self, parent, label, refresh_cmd):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=15, pady=4)
        ttk.Label(frame, text=label, width=22).pack(side="left")
        var = tk.StringVar(value="")
        combo = ttk.Combobox(frame, textvariable=var, values=[], state="readonly")
        combo.pack(side="left", fill="x", expand=True)
        ttk.Button(frame, text="Refresh", width=9, command=refresh_cmd).pack(side="left", padx=(4, 0))
        return var, combo

    def _build_form(self):
        # Pinned to the bottom first, so it always has room regardless of
        # how tall the rest of the form ends up or how small the window is.
        self.btn_run = ttk.Button(self, text="Finalize: Generate Users + Vouchers + PDF",
                                   command=self._finalize_clicked)
        self.btn_run.pack(side="bottom", fill="x", padx=15, pady=15)

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        ttk.Label(body, text="Router connection", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=15, pady=(10, 0))
        self.var_host = self._row(body, "Router IP / Host:", "192.168.88.1")
        self.var_port = self._row(body, "API Port:", "8728")

        ssl_frame = ttk.Frame(body)
        ssl_frame.pack(fill="x", padx=15, pady=4)
        self.var_ssl = tk.BooleanVar(value=False)
        ttk.Checkbutton(ssl_frame, text="Use API-SSL (port 8729)", variable=self.var_ssl,
                         command=self._toggle_ssl_port).pack(side="left")

        self.var_user = self._row(body, "Admin Username:", "admin")
        self.var_pass = self._row(body, "Admin Password:", "", show="*")

        conn_btn_frame = ttk.Frame(body)
        conn_btn_frame.pack(fill="x", padx=15, pady=(2, 4))
        ttk.Button(conn_btn_frame, text="Test Connection", command=self._test_connection_clicked).pack(side="left")
        self.lbl_conn_status = ttk.Label(conn_btn_frame, text="Not tested", foreground="#888")
        self.lbl_conn_status.pack(side="left", padx=(10, 0))

        ttk.Separator(body).pack(fill="x", padx=15, pady=8)
        ttk.Label(body, text="Voucher batch", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=15)
        self.var_count = self._row(body, "Voucher Count:", "10")
        self.var_prefix = self._row(body, "Username Prefix (opt):", "")

        self.var_group = self._row(body, "User Group:", "default")
        self.var_profile, self.combo_profile = self._combo_row(body, "Profile:", self._refresh_profiles_clicked)

        self.var_template = self._row(body, "Voucher Template File:", "printable_vouchers.html")
        self.var_remote_html = self._row(
            body,
            "Router output HTML path:",
            "um5files/PRIVATE/GENERATED/vouchers/gen_printable_vouchers.html"
        )

        ttk.Separator(body).pack(fill="x", padx=15, pady=8)
        save_frame = ttk.Frame(body)
        save_frame.pack(fill="x", padx=15, pady=4)
        ttk.Label(save_frame, text="Save PDF to:", width=22).pack(side="left")
        self.var_savepath = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "vouchers.pdf"))
        ttk.Entry(save_frame, textvariable=self.var_savepath).pack(side="left", fill="x", expand=True)
        ttk.Button(save_frame, text="...", width=3, command=self._browse).pack(side="left", padx=(4, 0))

        startup_frame = ttk.Frame(body)
        startup_frame.pack(fill="x", padx=15, pady=4)
        self.var_startup = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(startup_frame, text="Run this app at Windows login", variable=self.var_startup,
                              command=self._toggle_startup)
        cb.pack(side="left")
        if not sys.platform.startswith("win"):
            cb.state(["disabled"])

        self.txt_log = tk.Text(body, height=6, state="disabled", bg="#111", fg="#0f0")
        self.txt_log.pack(fill="both", padx=15, pady=(10, 5), expand=True)

    # -- small UI helpers ----------------------------------------------

    def _toggle_ssl_port(self):
        self.var_port.set("8729" if self.var_ssl.get() else "8728")

    def _browse(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if path:
            self.var_savepath.set(path)

    def _toggle_startup(self):
        set_windows_startup(self.var_startup.get(), os.path.abspath(__file__))

    def log(self, msg):
        self.after(0, self._log_impl, msg)

    def _log_impl(self, msg):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _get_conn_fields(self):
        return (
            self.var_host.get().strip(),
            int(self.var_port.get().strip()),
            self.var_ssl.get(),
            self.var_user.get().strip(),
            self.var_pass.get(),
        )

    # -- connection test --------------------------------------------------

    def _test_connection_clicked(self):
        self.lbl_conn_status.configure(text="Testing...", foreground="#888")
        threading.Thread(target=self._test_connection_worker, daemon=True).start()

    def _test_connection_worker(self):
        try:
            host, port, use_ssl, user, pwd = self._get_conn_fields()
            sock, api = connect_and_login(host, port, use_ssl, user, pwd, timeout=8)
            sock.close()
            self.after(0, self.lbl_conn_status.configure, {"text": "Connected OK", "foreground": "#0a0"})
        except Exception as e:
            msg = str(e)
            self.after(0, self.lbl_conn_status.configure, {"text": f"Failed: {msg}", "foreground": "#c00"})

    # -- dropdown refresh --------------------------------------------------

    def _refresh_profiles_clicked(self):
        threading.Thread(target=self._refresh_list, args=(
            "/user-manager/profile/print", self.combo_profile, self.var_profile, "profiles"
        ), daemon=True).start()

    def _refresh_list(self, path, combo, var, label):
        try:
            host, port, use_ssl, user, pwd = self._get_conn_fields()
            self.log(f"Fetching {label} from router...")
            sock, api = connect_and_login(host, port, use_ssl, user, pwd, timeout=8)
            names = fetch_names(api, path)
            sock.close()
            self.after(0, self._apply_list_results, combo, var, names, label)
        except Exception as e:
            msg = str(e)
            self.log(f"ERROR fetching {label}: {msg}")
            self.after(0, messagebox.showerror, "Error", f"Could not fetch {label}:\n{msg}")

    def _apply_list_results(self, combo, var, names, label):
        combo["values"] = names
        if names and not var.get():
            var.set(names[0])
        self.log(f"Loaded {len(names)} {label}: {', '.join(names) if names else '(none found)'}")

    # -- main run --------------------------------------------------

    def _finalize_clicked(self):
        try:
            host, port, use_ssl, user, pwd = self._get_conn_fields()
            count = int(self.var_count.get().strip())
            prefix = self.var_prefix.get().strip() or "(none)"
            group = self.var_group.get().strip()
            profile = self.var_profile.get().strip()
            template = self.var_template.get().strip()
            remote_html = self.var_remote_html.get().strip()
            save_path = self.var_savepath.get().strip()
        except ValueError:
            messagebox.showerror("Error", "Voucher Count must be a number.")
            return

        if not (1 <= count <= 500):
            messagebox.showerror("Error", "Voucher count must be between 1 and 500.")
            return
        if not profile:
            messagebox.showerror("Error", "Pick a Profile (use Refresh to load profiles from the router).")
            return

        summary = (
            f"Router:        {host}:{port} ({'API-SSL' if use_ssl else 'API'})\n"
            f"Admin user:    {user}\n\n"
            f"Vouchers to create: {count}\n"
            f"Username prefix:    {prefix}\n"
            f"User group:         {group}\n"
            f"Profile:            {profile}\n"
            f"Voucher template:   {template}\n"
            f"Router output file: {remote_html}\n"
            f"Save PDF to:        {save_path}\n\n"
            f"This will create {count} real user-manager accounts on the router "
            f"and cannot be undone automatically. Proceed?"
        )

        if messagebox.askyesno("Confirm voucher batch", summary):
            self.btn_run.configure(state="disabled")
            threading.Thread(target=self._run_workflow, daemon=True).start()

    def _run_workflow(self):
        try:
            host, port, use_ssl, user, pwd = self._get_conn_fields()
            count = int(self.var_count.get().strip())
            prefix = self.var_prefix.get().strip()
            group = self.var_group.get().strip()
            profile = self.var_profile.get().strip()
            template = self.var_template.get().strip()
            remote_html = self.var_remote_html.get().strip()
            save_path = self.var_savepath.get().strip()

            if not (1 <= count <= 500):
                raise ValueError("Voucher count must be between 1 and 500.")
            if not group:
                raise ValueError("Pick a User Group (use Refresh to load groups from the router).")
            if not profile:
                raise ValueError("Pick a Profile (use Refresh to load profiles from the router).")

            self.log(f"Connecting to {host}:{port} (ssl={use_ssl})...")
            sock, api = connect_and_login(host, port, use_ssl, user, pwd)
            self.log("Logged in.")

            created = []       # usernames, for logging/labels
            created_ids = []   # internal .id refs, required by generate-voucher
            for _ in range(count):
                uname = f"{prefix}-{random_string(5)}" if prefix else random_string(6)
                vpwd = random_string(6)

                resp = api.talk([
                    "/user-manager/user/add",
                    "=name=" + uname,
                    "=password=" + vpwd,
                    "=group=" + group,
                ])
                new_id = None
                for reply, attrs in resp:
                    if reply == '!trap':
                        raise RuntimeError(f"Router rejected user {uname}: {attrs}")
                    if reply == '!done' and '=ret' in attrs:
                        new_id = attrs['=ret']
                if not new_id:
                    raise RuntimeError(f"User {uname} was created but no .id was returned by the router.")

                resp = api.talk([
                    "/user-manager/user-profile/add",
                    "=user=" + uname,
                    "=profile=" + profile,
                ])
                for reply, attrs in resp:
                    if reply == '!trap':
                        raise RuntimeError(f"Could not attach profile to {uname}: {attrs}")

                created.append(uname)
                created_ids.append(new_id)
                self.log(f"Created user {uname} (id {new_id}, profile: {profile})")

            self.log(f"Requesting voucher generation for {len(created)} users...")
            resp = api.talk([
                "/user-manager/user/generate-voucher",
                "=numbers=" + ",".join(created_ids),
                "=voucher-template=" + template,
            ])
            for reply, attrs in resp:
                if reply == '!trap':
                    raise RuntimeError(f"generate-voucher failed: {attrs}")
            self.log("Voucher generation requested.")

            sock.close()

            tmp_html = os.path.join(tempfile.gettempdir(), f"vouchers_{random_string(4)}.html")
            self.log(f"Downloading {remote_html} via FTP...")

            last_err = None
            for attempt in range(1, 6):
                try:
                    with ftplib.FTP() as ftp:
                        ftp.connect(host, 21, timeout=15)
                        ftp.login(user, pwd)
                        with open(tmp_html, "wb") as f:
                            ftp.retrbinary(f"RETR {remote_html}", f.write)
                    last_err = None
                    break
                except ftplib.all_errors as e:
                    last_err = e
                    self.log(f"  attempt {attempt}/5: file not ready yet ({e}), retrying in 2s...")
                    time.sleep(2)
            if last_err is not None:
                raise RuntimeError(f"Could not download {remote_html} after 5 attempts: {last_err}")

            self.log(f"Downloaded to {tmp_html}")

            self.log("Converting to PDF...")
            html_to_pdf(tmp_html, save_path)
            self.log(f"Saved PDF: {save_path}")

            self.after(0, messagebox.showinfo, "Done", f"{len(created)} vouchers created.\nSaved to:\n{save_path}")
        except Exception as e:
            msg = str(e)
            self.log(f"ERROR: {msg}")
            self.after(0, messagebox.showerror, "Error", msg)
        finally:
            self.after(0, self.btn_run.configure, {"state": "normal"})


if __name__ == "__main__":
    VoucherApp().mainloop()