"""Windows double-click bootstrap. Runtime setup uses only Python's standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
URL = "http://127.0.0.1:8000"


def server_running() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return json.load(response).get("name") == "SceneTrace"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def port_occupied() -> bool:
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", 8000)) == 0


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def prepare_environment() -> None:
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required. Install it from https://www.python.org/downloads/")
    if not PYTHON.exists():
        print("[1/3] Creating the local Python environment...", flush=True)
        run([sys.executable, "-m", "venv", str(VENV)])
    requirements = ROOT / "requirements.txt"
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = VENV / ".scenetrace-requirements"
    imports = subprocess.run(
        [str(PYTHON), "-c", "import fastapi,uvicorn,cv2,numpy,PIL,imageio_ffmpeg"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if imports.returncode or not marker.exists() or marker.read_text().strip() != fingerprint:
        print("[2/3] Installing/checking application requirements (first setup needs internet)...", flush=True)
        run([str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)])
        marker.write_text(fingerprint, encoding="utf-8")
    else:
        print("[2/3] Application requirements are ready.", flush=True)
    print("[3/3] Checking computer-vision models...", flush=True)
    run([str(PYTHON), str(ROOT / "setup_model.py")])


def check_local_files() -> int:
    """Read-only check; no installation, server startup, or browser launch."""
    from setup_model import MODELS, DIRECTORY
    required = [ROOT / "app.py", ROOT / "requirements.txt", ROOT / "frontend/index.html", PYTHON]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    invalid_models = [name for name, _, checksum in MODELS
                      if not (DIRECTORY / name).exists()
                      or hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest() != checksum]
    print(json.dumps({"missing_files": missing, "missing_or_invalid_models": invalid_models,
                      "ready": not missing and not invalid_models}, indent=2))
    return int(bool(missing or invalid_models))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up and start SceneTrace locally")
    parser.add_argument("--check", action="store_true", help="Check local files without making changes")
    parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser")
    args = parser.parse_args(argv)
    if args.check:
        return check_local_files()
    print("SceneTrace - local video observation workspace", flush=True)
    if server_running():
        print(f"SceneTrace is already running at {URL}", flush=True)
        if not args.no_browser:
            webbrowser.open(URL, new=0)
        return 0
    if port_occupied():
        raise RuntimeError("Port 8000 is already used by another application. Stop it and try run.bat again.")
    prepare_environment()
    print(f"Starting {URL}. Keep this window open. Press Ctrl+C here to stop.", flush=True)
    process = subprocess.Popen([str(PYTHON), str(ROOT / "app.py")], cwd=ROOT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("The application exited during startup. Review the server error above.")
            if server_running():
                break
            time.sleep(.4)
        else:
            raise RuntimeError("The server did not become ready within 60 seconds.")
        if not args.no_browser:
            webbrowser.open(URL, new=0)
        print(f"Ready: {URL}", flush=True)
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping SceneTrace...", flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print(f"\nSceneTrace could not start: {error}", file=sys.stderr)
        print("Check your internet connection for first setup, then try run.bat again.", file=sys.stderr)
        raise SystemExit(1)
