"""Convert the router-generated voucher HTML into a PDF using headless Edge/Chrome."""

import os
import shutil
import subprocess
import sys


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
