import os
import sys
import subprocess
import venv
from pathlib import Path

def print_step(step_num, message):
    print(f"\n[{step_num}/5] \033[94m{message}\033[0m")
    print("-" * 50)

def main():
    backend_dir = Path(__file__).parent.absolute()
    os.chdir(backend_dir)
    print(f"Setting up environment in: {backend_dir}")

    # 1. Create Virtual Environment
    venv_dir = backend_dir / "venv"
    print_step(1, "Creating virtual environment...")
    if not venv_dir.exists():
        venv.create(venv_dir, with_pip=True)
        print("✅ Virtual environment created successfully.")
    else:
        print("✅ Virtual environment already exists. Skipping creation.")

    # Determine paths for pip and python inside venv
    if os.name == 'nt':  # Windows
        pip_exe = str(venv_dir / "Scripts" / "pip.exe")
        python_exe = str(venv_dir / "Scripts" / "python.exe")
    else:  # macOS / Linux
        pip_exe = str(venv_dir / "bin" / "pip")
        python_exe = str(venv_dir / "bin" / "python")

    # 2. Upgrade pip
    print_step(2, "Upgrading pip...")
    subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip"], check=True)
    print("✅ pip is up to date.")

    # 3. Install Requirements
    print_step(3, "Installing python dependencies...")
    req_file = backend_dir / "requirements.txt"
    if req_file.exists():
        subprocess.run([pip_exe, "install", "-r", str(req_file)], check=True)
        print("✅ Dependencies installed successfully.")
    else:
        print(f"❌ Error: {req_file} not found!")
        sys.exit(1)

    # 4. Install Playwright browser binaries
    print_step(4, "Installing Playwright (Chromium)...")
    try:
        subprocess.run([python_exe, "-m", "playwright", "install", "chromium"], check=True)
        print("✅ Playwright Chromium installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Playwright browsers: {e}")

    # 5. Pre-download AI Models from HuggingFace
    print_step(5, "Pre-downloading AI Models...")
    # Using the python executable in the venv to ensure huggingface_hub is available
    download_script = """
import sys
try:
    from huggingface_hub import snapshot_download, hf_hub_download
except ImportError:
    print("huggingface_hub not installed. Installing it...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import snapshot_download, hf_hub_download

print("\\nDownloading DocLayout-YOLO model...")
yolo_path = hf_hub_download(
    repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
    filename="doclayout_yolo_docstructbench_imgsz1024.pt",
)
print(f"✅ DocLayout-YOLO downloaded to: {yolo_path}")

print("\\nDownloading GLM-OCR model (this may take a while)...")
glm_path = snapshot_download(
    repo_id="zai-org/GLM-OCR",
)
print(f"✅ GLM-OCR downloaded to: {glm_path}")
"""
    try:
        subprocess.run([python_exe, "-c", download_script], check=True)
        print("✅ Models downloaded successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to download models: {e}")

    print("\n\033[92m🎉 SETUP COMPLETE! 🎉\033[0m")
    print("\nTo start the application, run:")
    if os.name == 'nt':
        print(f"  cd backend && .\\venv\\Scripts\\activate && uvicorn app.main:app --reload")
    else:
        print(f"  cd backend && source venv/bin/activate && uvicorn app.main:app --reload")

if __name__ == "__main__":
    main()
