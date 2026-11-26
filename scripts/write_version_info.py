"""Generate installer/version_info.txt (Windows VERSIONINFO resource) from fate_ai.__version__."""
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
ver = re.search(r'__version__ = "([^"]+)"', (root / "fate_ai" / "__init__.py").read_text()).group(1)
parts = [int(x) for x in re.findall(r"\d+", ver)[:3]] + [0]
while len(parts) < 4:
    parts.append(0)
t = tuple(parts[:4])
(root / "installer" / "version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'FATE AI'),
      StringStruct('FileDescription', 'FATE AI Desktop'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'FateAI'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'FateAI.exe'),
      StringStruct('ProductName', 'FATE AI'),
      StringStruct('ProductVersion', '{ver}')])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
""", "utf-8")
print("version", ver)
