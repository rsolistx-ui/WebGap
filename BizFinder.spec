# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for WebGap
# Produces a single .exe with no console window.

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle the Jinja2 templates into the exe
        ('templates', 'templates'),
    ],
    hiddenimports=[
        # App modules
        'scoring',
        'database',
        # Flask / Werkzeug internals PyInstaller misses
        'flask',
        'flask.templating',
        'werkzeug',
        'werkzeug.routing',
        'werkzeug.exceptions',
        'werkzeug.serving',
        'jinja2',
        'jinja2.ext',
        'jinja2.environment',
        # dnspython — all submodules needed for MX lookups
        'dns',
        'dns.resolver',
        'dns.exception',
        'dns.name',
        'dns.rdatatype',
        'dns.rdataclass',
        'dns.rdata',
        'dns.rdataset',
        'dns.rdatalist',
        'dns.message',
        'dns.flags',
        'dns.query',
        'dns.inet',
        'dns.ipv4',
        'dns.ipv6',
        'dns.tokenizer',
        'dns.zone',
        'dns.rdtypes',
        'dns.rdtypes.ANY',
        'dns.rdtypes.ANY.MX',
        'dns.rdtypes.ANY.NS',
        'dns.rdtypes.ANY.SOA',
        'dns.rdtypes.ANY.TXT',
        'dns.rdtypes.IN',
        'dns.rdtypes.IN.A',
        'dns.rdtypes.IN.AAAA',
        # requests / urllib3
        'requests',
        'requests.adapters',
        'requests.auth',
        'requests.cookies',
        'requests.models',
        'requests.sessions',
        'urllib3',
        'urllib3.util',
        'certifi',
        'charset_normalizer',
        'idna',
        # python-dotenv
        'dotenv',
        # pywebview internals for Windows
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
        'clr',
        'pythonnet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'scipy',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WebGap',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no black terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='webgap.ico',
)
