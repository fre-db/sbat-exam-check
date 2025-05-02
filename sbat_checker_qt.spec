# -*- mode: python ; coding: utf-8 -*-
import os
import sys
import glob
from PyInstaller.utils.hooks import get_package_paths

# Get PySide6 base path
pyside6_dir = get_package_paths('PySide6')[0] # Get first path found
dylib_files = glob.glob(os.path.join(pyside6_dir, '*.dylib'))
qt_binaries = [(f, '.') for f in dylib_files]
qt_plugins_base_dir = os.path.join(pyside6_dir, 'Qt', 'plugins')
qt_plugins = []

a = Analysis(
    ['sbat_gui_pyside.py'],
    pathex=[],
    binaries=qt_binaries,
    datas=qt_plugins,
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'queue',
        'pytz',
        'configparser',
        'requests',],
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
