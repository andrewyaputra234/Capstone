"""
Virtual Environment Setup Script
Creates and configures a Python 3.13 virtual environment for the Capstone project
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and report status."""
    print(f"\n{'='*60}")
    print(f"➤ {description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}\n")
    
    try:
        result = subprocess.run(cmd, shell=True, check=True)
        print(f"✅ {description} - SUCCESS\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} - FAILED (exit code: {e.returncode})\n")
        return False

def main():
    python313_path = r"C:\Users\SwiftX\AppData\Local\Programs\Python\Python313\python.exe"
    project_root = Path(__file__).parent
    venv_path = project_root / "venv"
    
    print(f"""
╔══════════════════════════════════════════════════════════╗
║          CAPSTONE PROJECT - VENV SETUP                    ║
║         Python 3.13 Virtual Environment                  ║
╚══════════════════════════════════════════════════════════╝

Project Root: {project_root}
Python 3.13: {python313_path}
Venv Path: {venv_path}
    """)
    
    # Check if Python 3.13 exists
    if not Path(python313_path).exists():
        print(f"❌ ERROR: Python 3.13 not found at {python313_path}")
        print("Please install Python 3.13 from https://www.python.org/downloads/")
        return False
    
    print(f"✅ Python 3.13 found\n")
    
    # Remove old venv if it exists
    if venv_path.exists():
        print(f"🗑️  Removing existing venv at {venv_path}...")
        import shutil
        shutil.rmtree(venv_path)
        print(f"✅ Old venv removed\n")
    
    # Create venv
    if not run_command(
        f'"{python313_path}" -m venv venv',
        "Creating Python 3.13 virtual environment"
    ):
        return False
    
    # Get paths for activation
    if sys.platform == "win32":
        activate_cmd = str(venv_path / "Scripts" / "activate.bat")
        pip_path = str(venv_path / "Scripts" / "pip.exe")
        python_path = str(venv_path / "Scripts" / "python.exe")
    else:
        activate_cmd = str(venv_path / "bin" / "activate")
        pip_path = str(venv_path / "bin" / "pip")
        python_path = str(venv_path / "bin" / "python")
    
    print(f"\n✅ Virtual environment created successfully!")
    print(f"\n{'='*60}")
    print("ACTIVATION INSTRUCTIONS")
    print(f"{'='*60}")
    
    if sys.platform == "win32":
        print(f"\nFor PowerShell:")
        print(f"  {venv_path}\\Scripts\\Activate.ps1")
        print(f"\nFor Command Prompt:")
        print(f"  {venv_path}\\Scripts\\activate.bat")
    else:
        print(f"\nFor Linux/macOS:")
        print(f"  source {venv_path}/bin/activate")
    
    print(f"\n{'='*60}")
    print("INSTALLATION INSTRUCTIONS")
    print(f"{'='*60}")
    print(f"\n1. Activate the virtual environment (see above)")
    print(f"\n2. Upgrade pip:")
    print(f"   python -m pip install --upgrade pip")
    print(f"\n3. Install dependencies:")
    print(f"   pip install -r requirements.txt")
    print(f"\n4. Run Streamlit:")
    print(f"   streamlit run streamlit_app.py")
    
    print(f"\n{'='*60}")
    print("✅ Setup complete! Follow the instructions above.")
    print(f"{'='*60}\n")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
