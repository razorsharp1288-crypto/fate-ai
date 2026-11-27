# PyInstaller spec for FATE AI (Windows one-folder build; bundles the Python runtime).
# Build:  pyinstaller --noconfirm fate_ai.spec
import re
from pathlib import Path

root = Path(SPECPATH)
version = re.search(r'__version__ = "([^"]+)"', (root / "fate_ai" / "__init__.py").read_text()).group(1)

excluded_qt = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
               "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick3D",
               "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtQml",
               "PySide6.QtQuick", "PySide6.QtBluetooth", "PySide6.QtLocation", "PySide6.QtPositioning",
               "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtDesigner"]

a = Analysis(
    [str(root / "run_fate_ai.py")],
    pathex=[str(root)],
    datas=[(str(root / "assets"), "assets")],
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtTextToSpeech", "fate_ai.virtualization.backends.windows_sandbox", "fate_ai.database.migrations.v001_initial", "fate_ai.database.migrations.v002_blueprints", "keyring.backends.Windows", "win32ctypes.core", "pygments.lexers", "pygments.formatters.html",
                   "pygments.styles.monokai", "markdown.extensions.tables", "markdown.extensions.sane_lists"],
    excludes=excluded_qt + ["tkinter", "pytest", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FateAI",
    icon=str(root / "assets" / "fate_ai.ico"),
    console=False,
    version=str(root / "installer" / "version_info.txt") if (root / "installer" / "version_info.txt").exists() else None,
    uac_admin=False,  # least privilege: never request elevation
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FateAI")
