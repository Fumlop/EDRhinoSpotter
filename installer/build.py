"""Build the standalone installer:  python installer/build.py

PyInstaller, run from installer/.venv (requirements.txt only: Pillow, requests,
PyInstaller, pinned), bundles standalone.py into installer/dist/RhinoSpotter/;
Inno Setup wraps that folder into installer/dist/RhinoSpotter-<version>-Setup.exe.
The venv is made on first use and made again when requirements.txt is newer
than it. Needs Pillow in the Python running this (the icon) and Inno Setup 6
(ISCC.exe). Output folders and the venv are gitignored.
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
VENV = os.path.join(HERE, ".venv")
REQUIREMENTS = os.path.join(HERE, "requirements.txt")
ISCC = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"]

sys.path.insert(0, ROOT)
from rs_core import update                              # noqa: E402

# Read at run time next to rs_core / rs_ui, as in the plugin folder.
DATA = [("texture", "texture"), ("mining_sheet.json", "."), (os.path.join("docs", "running.png"), "docs")]
# In the venv only as PyInstaller's dependency; pulled in through urllib3's
# optional `backports.zstd` import, which resolves to setuptools' vendored copy.
EXCLUDE = ("setuptools", "pkg_resources")


def icon():
    """docs/logo.png as a multi-size .ico for the exe and the installer."""
    from PIL import Image
    target = os.path.join(BUILD, "rhinospotter.ico")
    os.makedirs(BUILD, exist_ok=True)
    Image.open(os.path.join(ROOT, "docs", "logo.png")).save(
        target, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return target


def venv_python():
    """installer/.venv's python with requirements.txt installed, and nothing else."""
    python = os.path.join(VENV, "Scripts", "python.exe")
    stamp = os.path.join(VENV, "requirements.stamp")
    if not os.path.isfile(stamp) or os.path.getmtime(stamp) < os.path.getmtime(REQUIREMENTS):
        shutil.rmtree(VENV, ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
        subprocess.run([python, "-m", "pip", "install", "--disable-pip-version-check",
                        "-r", REQUIREMENTS], check=True)
        open(stamp, "w").close()
    return python


def main():
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    ico = icon()
    python = venv_python()
    print(f"PyInstaller from {python}")
    args = [python, "-m", "PyInstaller", "--noconfirm", "--windowed", "--onedir",
            "--name", "RhinoSpotter", "--icon", ico,
            "--distpath", DIST, "--workpath", os.path.join(BUILD, "work"), "--specpath", BUILD]
    for module in EXCLUDE:
        args += ["--exclude-module", module]
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
