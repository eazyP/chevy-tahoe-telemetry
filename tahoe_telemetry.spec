# Build with: pyinstaller --clean --noconfirm tahoe_telemetry.spec
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("serial")

a = Analysis(
    ["tahoe_telemetry_launcher.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TahoeTelemetry",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
