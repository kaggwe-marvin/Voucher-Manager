# -*- mode: python ; coding: utf-8 -*-
# Build with:  poetry run pyinstaller VoucherManager.spec   (or: make build-exe)

import sys
import tomllib

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)

sys.path.insert(0, SPECPATH)  # so `app` is importable from the project root
from app import __version__

with open('pyproject.toml', 'rb') as f:
    _project_version = tomllib.load(f)['project']['version']
if _project_version != __version__:
    raise SystemExit(
        f"Version mismatch: pyproject.toml has {_project_version}, "
        f"app/__init__.py has {__version__}. Update both before building."
    )

_ver = tuple(int(p) for p in __version__.split('.')) + (0,)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Kaggwe Marvin Victor'),
            StringStruct('FileDescription', 'RouterOS Voucher Manager'),
            StringStruct('FileVersion', __version__),
            StringStruct('InternalName', 'VoucherManager'),
            StringStruct('LegalCopyright', 'Copyright (c) 2026 Kaggwe Marvin Victor. MIT License.'),
            StringStruct('OriginalFilename', 'VoucherManager.exe'),
            StringStruct('ProductName', 'RouterOS Voucher Manager'),
            StringStruct('ProductVersion', __version__),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ],
)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VoucherManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX-packed PyInstaller exes are a common antivirus false positive.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
    icon='assets/icon.ico',
)
