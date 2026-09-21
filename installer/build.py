"""Build the standalone installer:  python installer/build.py

PyInstaller bundles standalone.py with Python, Pillow and requests into
installer/dist/RhinoSpotter/; Inno Setup wraps that folder into
installer/dist/RhinoSpotter-<version>-Setup.exe. Needs `pip install pyinstaller`
and Inno Setup 6 (ISCC.exe). Output folders are gitignored.
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
ISCC = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"]

sys.path.insert(0, ROOT)
from rs_core import update                              # noqa: E402

# Read at run time next to rs_core / rs_ui, as in the plugin folder.
DATA = [("texture", "texture"), ("mining_sheet.json", "."), (os.path.join("docs", "running.png"), "docs")]


def icon():
    """docs/logo.png as a multi-size .ico for the exe and the installer."""
    from PIL import Image
    target = os.path.join(BUILD, "rhinospotter.ico")
    os.makedirs(BUILD, exist_ok=True)
    Image.open(os.path.join(ROOT, "docs", "logo.png")).save(
        target, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def main():
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    ico = icon()
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
            "--name", "RhinoSpotter", "--icon", ico,
            "--distpath", DIST, "--workpath", os.path.join(BUILD, "work"), "--specpath", BUILD]
    for source, target in DATA:
        args += ["--add-data", f"{os.path.join(ROOT, source)}{os.pathsep}{target}"]
    subprocess.run(args + [os.path.join(ROOT, "standalone.py")], check=True, cwd=ROOT)
    iscc = next((path for path in ISCC if os.path.isfile(path)), None)
    if not iscc:
        sys.exit("Inno Setup 6 not found: winget install JRSoftware.InnoSetup")
    subprocess.run([iscc, f"/DVersion={update.VERSION}", f"/DIcon={ico}",
                    f"/DSource={os.path.join(DIST, 'RhinoSpotter')}", f"/O{DIST}",
                    os.path.join(HERE, "RhinoSpotter.iss")], check=True)
    print(os.path.join(DIST, f"RhinoSpotter-{update.VERSION}-Setup.exe"))


if __name__ == "__main__":
    main()
