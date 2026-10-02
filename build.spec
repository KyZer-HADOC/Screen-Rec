# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller --noconfirm build.spec
# Produces a onedir build at dist/SmartScreenRecorder/ which installer.iss
# then packages into a Setup.exe installer.

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=[
        'pyaudiowpatch',
        'keyboard',
        'pynput.mouse._win32',
        'pynput.keyboard._win32',
        # numpy.random (a compiled Cython module) imports these, but
        # PyInstaller can't see inside it, so list them explicitly.
        'secrets', 'hmac', 'hashlib', 'base64', 'binascii',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Modules the app never uses - keeping them out shrinks the build.
    excludes=[
        'tkinter', '_tkinter', 'test', 'pydoc_data', 'lib2to3',
        'matplotlib', 'scipy', 'pandas', 'PIL', 'IPython', 'pytest',
        'PyQt5.QtNetwork', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtSvg',
        'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebChannel',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtSql',
        'PyQt5.QtTest', 'PyQt5.QtXml', 'PyQt5.QtOpenGL', 'PyQt5.QtBluetooth',
        'PyQt5.QtPositioning', 'PyQt5.QtSensors', 'PyQt5.QtDesigner',
        'PyQt5.QtHelp', 'PyQt5.QtPrintSupport', 'PyQt5.QtSerialPort',
    ],
    noarchive=False,
    cipher=block_cipher,
)

# Drop big Qt files a widgets-only app never loads (software OpenGL,
# QML/Quick runtimes, translations, shader compiler).
_DROP_BIN = ('opengl32sw', 'd3dcompiler', 'qt5quick', 'qt5qml', 'qt5pdf',
             'qt5virtualkeyboard', 'qt5websockets', 'qt5network', 'qt5svg')
a.binaries = [b for b in a.binaries
              if not any(k in b[0].lower() for k in _DROP_BIN)]
a.datas = [d for d in a.datas
           if 'translations' not in d[0].lower().replace('\\', '/')]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SmartScreenRecorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SmartScreenRecorder',
)
