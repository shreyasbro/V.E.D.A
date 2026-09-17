"""
V.E.D.A. Standalone Executable Builder
Portable Python build orchestrator that dynamically detects PROJECT_ROOT,
the Python environment, validates/installs dependencies, and runs PyInstaller.
Can be executed directly from anywhere on any Windows machine.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

REQUIRED_PACKAGES = [
    "customtkinter",
    "pyautogui",
    "pygetwindow",
    "pyperclip",
    "pillow",
    "google-genai",
    "pystray",
    "uiautomation",
    "sounddevice",
    "SpeechRecognition",
    "opencv-python",
    "pycaw",
    "python-dotenv",
    "pyinstaller",
    "pywin32",
    "numpy",
    "azure-cognitiveservices-speech",
    "mediapipe"
]

def print_banner(title: str):
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)

def detect_project_root() -> Path:
    """
    Determines PROJECT_ROOT strictly from this script's own location,
    guaranteeing it never depends on the current working directory (%CD%).
    """
    return Path(__file__).resolve().parent

def _get_pyinstaller_version(py_exe: str) -> str:
    """
    Checks if PyInstaller is importable and returns its version.
    Using 'import PyInstaller' is instant and avoids slow Windows hook discovery.
    """
    try:
        proc = subprocess.run(
            [py_exe, "-c", "import PyInstaller; print(PyInstaller.__version__)"],
            capture_output=True,
            text=True,
            timeout=15
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except Exception:
        pass
    return ""

def detect_python_environment(project_root: Path) -> str:
    """
    Discovers the Python executable following priority:
    1. Project-local virtual environment (.venv/ or venv/)
    2. Active Python runtime running this script
    3. Windows py launcher versions
    4. System PATH python
    """
    candidates = []

    # 1. Project-local venv
    venv1 = project_root / ".venv" / "Scripts" / "python.exe"
    venv2 = project_root / "venv" / "Scripts" / "python.exe"
    if venv1.is_file():
        candidates.append(str(venv1))
    if venv2.is_file():
        candidates.append(str(venv2))

    # 2. Current interpreter running this process
    candidates.append(sys.executable)

    # 3. py launcher discovery
    py_launcher = shutil.which("py")
    if py_launcher:
        try:
            list_proc = subprocess.run(
                [py_launcher, "--list-paths"],
                capture_output=True,
                text=True,
                timeout=5
            )
            for line in list_proc.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[-1].endswith(".exe") and os.path.isfile(parts[-1]):
                    candidates.append(parts[-1])
        except Exception:
            pass

    # 4. PATH python
    p = shutil.which("python")
    if p:
        candidates.append(p)

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        norm = os.path.normcase(os.path.abspath(c))
        if norm not in seen:
            seen.add(norm)
            unique_candidates.append(c)

    # Pick first candidate that has PyInstaller installed
    for c in unique_candidates:
        if _get_pyinstaller_version(c):
            return c

    # Fallback to first available candidate
    return unique_candidates[0] if unique_candidates else sys.executable

def ensure_dependencies(python_exe: str, project_root: Path):
    """
    Verifies that all required packages and PyInstaller exist.
    If any are missing, automatically installs them via python -m pip install.
    """
    print("[V.E.D.A. BUILD] Checking dependencies...")
    req_file = project_root / "requirements.txt"

    # Check PyInstaller first
    if not _get_pyinstaller_version(python_exe):
        print("[V.E.D.A. BUILD] PyInstaller not detected. Installing PyInstaller...")
        subprocess.run(
            [python_exe, "-m", "pip", "install", "pyinstaller"],
            check=False
        )

    # If requirements.txt exists, verify/install
    if req_file.exists():
        print(f"[V.E.D.A. BUILD] Installing dependencies from {req_file.name}...")
        res = subprocess.run(
            [python_exe, "-m", "pip", "install", "-r", str(req_file)],
            check=False
        )
        if res.returncode != 0:
            print("[WARN] pip install returned non-zero. Attempting to proceed with available packages.")

def clean_build_artifacts(project_root: Path):
    """
    Safely cleans only generated temporary build artifacts within PROJECT_ROOT.
    """
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"

    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
            print(f"[CLEAN] Removed temporary build dir: {build_dir}")
        except Exception as e:
            print(f"[WARN] Could not clean build dir: {e}")

    if dist_dir.exists():
        try:
            shutil.rmtree(dist_dir)
            print(f"[CLEAN] Removed previous dist dir: {dist_dir}")
        except Exception as e:
            print(f"[WARN] Could not clean dist dir: {e}")

def run_build():
    project_root = detect_project_root()
    python_exe = detect_python_environment(project_root)
    main_py = project_root / "main.py"
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"

    from veda.version import VERSION, BUILD
    print_banner(f"V.E.D.A. STANDALONE EXE COMPILER v{VERSION} (Build {BUILD})")
    print(f"Project Root:      {project_root}")
    print(f"Python Executable: {python_exe}")
    print(f"V.E.D.A. Version:  {VERSION} (Build {BUILD})")

    # Check Python version
    try:
        py_ver_proc = subprocess.run(
            [python_exe, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        py_version = (py_ver_proc.stdout or py_ver_proc.stderr).strip()
        print(f"Python Version:    {py_version}")
    except Exception as e:
        print(f"[ERROR] Failed to query Python version: {e}")
        sys.exit(1)

    # Ensure dependencies and PyInstaller are installed
    ensure_dependencies(python_exe, project_root)

    # Verify PyInstaller availability
    pi_version = _get_pyinstaller_version(python_exe)
    if not pi_version:
        print("[ERROR] PyInstaller is not installed and automatic installation failed.")
        print(f"Please run manually: {python_exe} -m pip install pyinstaller")
        sys.exit(1)

    print(f"PyInstaller:       {pi_version}")
    print(f"Build Directory:   {build_dir}")
    print(f"Dist Directory:    {dist_dir}")
    print("=" * 60)

    # Validation
    if not main_py.exists():
        print(f"[MISSING] Entry point '{main_py}' not found in project root.")
        sys.exit(1)

    # Step 1: Clean build artifacts
    print("\n[STEP 1/2] Cleaning previous build artifacts...")
    clean_build_artifacts(project_root)

    # Step 2: Compile with PyInstaller
    print("\n[STEP 2/2] Compiling standalone Windows executable...")
    
    cmd = [
        python_exe, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "VEDA",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--collect-all", "customtkinter",
        "--collect-all", "uiautomation",
        "--collect-all", "numpy",
        "--collect-all", "cv2",
        "--collect-all", "azure.cognitiveservices.speech",
        "--collect-all", "mediapipe",
        "--add-data", "veda/models/hand_landmarker.task;veda/models",
        "--hidden-import", "google.genai",
        "--hidden-import", "PIL",
        "--hidden-import", "pyautogui",
        "--hidden-import", "pyperclip",
        "--hidden-import", "pystray",
        "--hidden-import", "sounddevice",
        "--hidden-import", "speech_recognition",
        "--hidden-import", "pycaw",
        "--hidden-import", "win32api",
        "--hidden-import", "win32com.client",
        str(main_py)
    ]

    print("Executing command array:")
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    print("-" * 60)

    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode != 0:
        print("\n[ERROR] Compilation failed with exit code:", result.returncode)
        sys.exit(result.returncode)

    exe_path = dist_dir / "VEDA" / "VEDA.exe"
    if not exe_path.exists():
        print(f"\n[ERROR] Expected output executable '{exe_path}' was not generated.")
        sys.exit(1)

    exe_size_mb = exe_path.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(f"[SUCCESS] Binary created successfully!")
    print(f"Location: {exe_path}")
    print(f"Size:     {exe_size_mb:.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    run_build()
