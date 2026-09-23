"""Tkinter GUI for RouterOS Voucher Manager. Layout and event wiring only —
the actual router/FTP/PDF work lives in workflow.py and the app.* modules
it calls into.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import __version__
from app.gui.workflow import WorkflowParams, run_workflow
from app.routeros.client import connect_and_login, fetch_names



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"RouterOS Voucher Manager {__version__}")
        self.geometry("560x700")
        self.minsize(520, 480)
        self.resizable(True, True)
        self._build_form()

    PAD = 12
    LABEL_COL = 140  # shared label-column width so inputs line up across groups

    def _setup_styles(self):
        style = ttk.Style(self)
        style.configure("Group.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(10, 8))
        style.configure("Link.TLabel", foreground="#0a5fb4")
        style.configure("Status.TLabel", foreground="#888")

    def _group(self, parent, title):
        frame = ttk.LabelFrame(parent, text=title, style="Group.TLabelframe", padding=(10, 6))
        frame.pack(fill="x", padx=self.PAD, pady=(self.PAD, 0))
        frame.columnconfigure(0, minsize=self.LABEL_COL)
        frame.columnconfigure(1, weight=1)
        return frame

    def _row(self, parent, row, label, default="", show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        var = tk.StringVar(value=default)
        ttk.Entry(parent, textvariable=var, show=show).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=3)
        return var

    def _combo_row(self, parent, row, label, refresh_cmd):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        var = tk.StringVar(value="")
        combo = ttk.Combobox(parent, textvariable=var, values=[], state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(parent, text="Refresh", command=refresh_cmd).grid(
            row=row, column=2, sticky="e", padx=(6, 0), pady=3)
        return var, combo

    def _build_form(self):
        self._setup_styles()

        # Pinned to the bottom first, so it always has room regardless of
        # how tall the rest of the form ends up or how small the window is.
        self.btn_run = ttk.Button(self, text="Generate Users, Vouchers and PDF",
                                   style="Primary.TButton", command=self._finalize_clicked)
        self.btn_run.pack(side="bottom", fill="x", padx=self.PAD, pady=self.PAD)

        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        # -- Router connection
        conn = self._group(body, "Router connection")
        self.var_host = self._row(conn, 0, "Host / IP", "192.168.88.1")
        self.var_port = self._row(conn, 1, "API port", "8728")
        self.var_ssl = tk.BooleanVar(value=False)
        ttk.Checkbutton(conn, text="Use API-SSL (port 8729)", variable=self.var_ssl,
                         command=self._toggle_ssl_port).grid(row=2, column=1, columnspan=2, sticky="w", pady=3)
        self.var_user = self._row(conn, 3, "Username", "admin")
        self.var_pass = self._row(conn, 4, "Password", "", show="•")

        test_frame = ttk.Frame(conn)
        test_frame.grid(row=5, column=1, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(test_frame, text="Test Connection", command=self._test_connection_clicked).pack(side="left")
        self.lbl_conn_status = ttk.Label(test_frame, text="Not tested", style="Status.TLabel")
        self.lbl_conn_status.pack(side="left", padx=(10, 0))

        # -- Voucher batch
        batch = self._group(body, "Voucher batch")
        self.var_count = self._row(batch, 0, "Number of vouchers", "10")
        self.var_prefix = self._row(batch, 1, "Username prefix", "")
        self.var_group = self._row(batch, 2, "User group", "default")
        self.var_profile, self.combo_profile = self._combo_row(batch, 3, "Profile", self._refresh_profiles_clicked)

        # -- Output
        out = self._group(body, "Output")
        ttk.Label(out, text="Save PDF to").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=3)
        self.var_savepath = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Desktop", "vouchers.pdf"))
        ttk.Entry(out, textvariable=self.var_savepath).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(out, text="Browse…", command=self._browse).grid(
            row=0, column=2, sticky="e", padx=(6, 0), pady=3)

        self.lbl_advanced = ttk.Label(out, text="Advanced ▸", style="Link.TLabel", cursor="hand2")
        self.lbl_advanced.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.lbl_advanced.bind("<Button-1>", lambda e: self._toggle_advanced())

        self.frm_advanced = ttk.Frame(out)
        self.frm_advanced.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.frm_advanced.columnconfigure(1, weight=1)
        self.var_template = self._row(self.frm_advanced, 0, "Voucher template", "printable_vouchers.html")
        self.var_remote_html = self._row(
            self.frm_advanced, 1,
            "Router output path",
            "um5files/PRIVATE/GENERATED/vouchers/gen_printable_vouchers.html"
        )
        self.frm_advanced.columnconfigure(0, minsize=self.LABEL_COL)
        self.frm_advanced.grid_remove()

        # -- Log
        log_frame = ttk.LabelFrame(body, text="Log", style="Group.TLabelframe", padding=(6, 4))
        log_frame.pack(fill="both", expand=True, padx=self.PAD, pady=(self.PAD, 0))
        self.txt_log = tk.Text(log_frame, height=6, state="disabled", wrap="word",
                               bg="#fafafa", fg="#222", font=("Consolas", 9),
                               relief="flat", borderwidth=0, padx=6, pady=4)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

    # -- small UI helpers ----------------------------------------------

    def _toggle_ssl_port(self):
        self.var_port.set("8729" if self.var_ssl.get() else "8728")

    def _toggle_advanced(self):
        if self.frm_advanced.winfo_ismapped():
            self.frm_advanced.grid_remove()
            self.lbl_advanced.configure(text="Advanced ▸")
        else:
            self.frm_advanced.grid()
            self.lbl_advanced.configure(text="Advanced ▾")

    def _browse(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if path:
            self.var_savepath.set(path)


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
        self.lbl_conn_status.configure(text="Testing…", foreground="#888")
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

    def _collect_params(self):
        host, port, use_ssl, user, pwd = self._get_conn_fields()
        return WorkflowParams(
            host=host,
            port=port,
            use_ssl=use_ssl,
            admin_user=user,
            admin_pass=pwd,
            count=int(self.var_count.get().strip()),
            prefix=self.var_prefix.get().strip(),
            group=self.var_group.get().strip(),
            profile=self.var_profile.get().strip(),
            template=self.var_template.get().strip(),
            remote_html=self.var_remote_html.get().strip(),
            save_path=self.var_savepath.get().strip(),
        )

    def _finalize_clicked(self):
        try:
            params = self._collect_params()
        except ValueError:
            messagebox.showerror("Error", "Number of vouchers must be a whole number.")
            return

        if not (1 <= params.count <= 500):
            messagebox.showerror("Error", "Number of vouchers must be between 1 and 500.")
            return
        if not params.profile:
            messagebox.showerror("Error", "Pick a Profile (use Refresh to load profiles from the router).")
            return

        summary = (
            f"Router:        {params.host}:{params.port} ({'API-SSL' if params.use_ssl else 'API'})\n"
            f"Admin user:    {params.admin_user}\n\n"
            f"Vouchers to create: {params.count}\n"
            f"Username prefix:    {params.prefix or '(none)'}\n"
            f"User group:         {params.group}\n"
            f"Profile:            {params.profile}\n"
            f"Voucher template:   {params.template}\n"
            f"Router output file: {params.remote_html}\n"
            f"Save PDF to:        {params.save_path}\n\n"
            f"This will create {params.count} real user-manager accounts on the router "
            f"and cannot be undone automatically. Proceed?"
        )

        if messagebox.askyesno("Confirm voucher batch", summary):
            self.btn_run.configure(state="disabled")
            threading.Thread(target=self._run_workflow_worker, args=(params,), daemon=True).start()

    def _run_workflow_worker(self, params):
        try:
            result = run_workflow(params, log=self.log)
            self.after(0, messagebox.showinfo, "Done",
                       f"{len(result.usernames)} vouchers created.\nSaved to:\n{result.save_path}")
        except Exception as e:
            msg = str(e)
            self.log(f"ERROR: {msg}")
            self.after(0, messagebox.showerror, "Error", msg)
        finally:
            self.after(0, self.btn_run.configure, {"state": "normal"})


if __name__ == "__main__":
    App().mainloop()
