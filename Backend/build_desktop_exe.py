import shutil
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
ENTRYPOINT = PROJECT_DIR / "Frontend" / "desktop_app.py"
DIST_DIR = BACKEND_DIR / "dist"
BUILD_DIR = BACKEND_DIR / "build"
ROOT_EXE = PROJECT_DIR / "Тестировщик.exe"


def run(command):
    print(" ".join(str(part) for part in command), flush=True)
    subprocess.check_call(command, cwd=PROJECT_DIR)


def ensure_pyinstaller():
    if shutil.which("pyinstaller"):
        return
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build(name="Тестировщик", clean=True):
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BACKEND_DIR),
    ]
    if clean:
        command.append("--clean")
    command.append(str(ENTRYPOINT))
    run(command)


if __name__ == "__main__":
    ensure_pyinstaller()
    build()
    built_exe = DIST_DIR / "Тестировщик.exe"
    print(f"Done: {built_exe}", flush=True)
    try:
        shutil.copy2(built_exe, ROOT_EXE)
    except PermissionError:
        print(f"Root exe is open and could not be replaced: {ROOT_EXE}", flush=True)
        print("Close the running app and copy the file from Backend\\dist manually, or run this build again.", flush=True)
    else:
        print(f"Copied: {ROOT_EXE}", flush=True)
