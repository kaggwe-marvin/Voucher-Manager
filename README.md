# RouterOS Voucher Manager

A Tkinter GUI for batch-creating MikroTik User Manager hotspot vouchers, generating a printable PDF, and (optionally) running automatically at login.

## What it does

- Talks to RouterOS over the **native binary API** (port `8728`, or `8729` with TLS), using the same wire protocol as MikroTik's official `python_api_fixed.py`.
- **Test Connection** verifies login before you run anything.
- **User Group** and **Profile** are dropdowns populated live from the router (`/user-manager/user-group/print` and `/user-manager/profile/print`) via a **Refresh** button — no more typing in raw validity strings.
- Batch-creates User Manager accounts, attaches each one to the selected profile via `/user-manager/user-profile/add`, then triggers `/user-manager/user/generate-voucher` against exactly those accounts using an existing voucher template on the router.
- Downloads the resulting `.html` file via FTP (default path matches User Manager 5's generated-files location).
- Converts it to PDF using headless Microsoft Edge / Chrome.
- Optional **"run at login"** toggle using Windows Task Scheduler (`schtasks`).

## Requirements

### On the router

- `/ip service enable api` (or `api-ssl` for encrypted, port `8729`)
- `/ip service enable ftp`
- A voucher template already uploaded to Files (e.g. `printable_vouchers.html`)
- At least one User Manager profile and user-group already configured
- A user with API + FTP rights

### On this PC

- Python 3 (standard library only — `socket`, `ssl`, `ftplib`, `tkinter`, `subprocess`)
- Microsoft Edge or Google Chrome installed, for HTML → PDF conversion

## Usage

1. Launch the app and enter your router's address and credentials.
2. Click **Test Connection** to verify login.
3. Click **Refresh** to populate the User Group and Profile dropdowns from the router.
4. Choose the group, profile, and voucher template, then batch-create the vouchers.
5. The app downloads the generated HTML over FTP and converts it to PDF automatically.

## Security note

This tool creates and displays **plaintext router credentials and voucher passwords**. Don't leave generated `.html`/`.pdf` files lying around after vouchers are printed — delete them from both the router and this PC.

## License

