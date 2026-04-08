# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import glob
from PyInstaller.utils.hooks import get_package_paths

# Get PySide6 base path
pyside6_dir = get_package_paths('PySide6')[0]
dylib_files = glob.glob(os.path.join(pyside6_dir, '*.dylib'))
qt_binaries = [(f, '.') for f in dylib_files]

# Get Playwright driver (Node + Playwright server)
# Playwright uses system Chrome via channel="chrome", so no browser bundle needed
playwright_dir = get_package_paths('playwright')[1]
playwright_driver = os.path.join(playwright_dir, 'driver')

a = Analysis(
    ['sbat_gui_pyside.py'],
    pathex=[],
    binaries=qt_binaries,
    datas=[
        (playwright_driver, 'playwright/driver'),
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'playwright',
        'playwright.sync_api',
        'queue',
        'pytz',
        'requests',
    ],
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
    [],
    exclude_binaries=True,
    name='sbat_checker_qt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='sbat_checker_qt',
)
app = BUNDLE(
    coll,
    name='sbat_checker_qt.app',
    icon=None,
    bundle_identifier=None,
)
