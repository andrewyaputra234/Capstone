"""
Quick Start & Verification Script
Run this after installing dependencies to verify CrewAI setup
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def check_python_version():
    """Verify Python version is 3.10-3.13"""
    version = sys.version_info
    print(f"\n{BLUE}Checking Python version...{RESET}")
    print(f"Current: Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major == 3 and 10 <= version.minor <= 13:
        print(f"{GREEN}[OK] Python version OK{RESET}")
        return True
    else:
        print(f"{RED}[ERROR] Python 3.10-3.13 required (found {version.major}.{version.minor}){RESET}")
        return False


def check_imports():
    """Check if all required packages are installed"""
    required_packages = {
        "crewai": "CrewAI",
        "langchain": "LangChain",
        "langchain_openai": "LangChain OpenAI",
        "streamlit": "Streamlit",
        "chromadb": "ChromaDB",
        "dotenv": "Python Dotenv"
    }
    
    print(f"\n{BLUE}Checking installed packages...{RESET}")
    all_ok = True
    
    for package, name in required_packages.items():
        try:
            __import__(package)
            print(f"{GREEN}[OK] {name}{RESET}")
        except ImportError:
            print(f"{RED}[ERROR] {name} not installed{RESET}")
            all_ok = False
    
    return all_ok


def check_env_file():
    """Check if .env file exists and has OpenAI API key"""
    print(f"\n{BLUE}Checking environment configuration...{RESET}")
    
    env_path = Path(".env")
    
    if env_path.exists():
        print(f"{GREEN}[OK] .env file found{RESET}")
        
        with open(env_path, "r") as f:
            content = f.read()
            if "OPENAI_API_KEY" in content:
                print(f"{GREEN}[OK] OPENAI_API_KEY configured{RESET}")
                return True
            else:
                print(f"{RED}[ERROR] OPENAI_API_KEY not found in .env{RESET}")
                return False
    else:
        print(f"{YELLOW}[WARN] .env file not found{RESET}")
        print("Create a .env file with: OPENAI_API_KEY=your_key_here")
        return False


def check_crew_files():
    """Check if CrewAI files are present"""
    print(f"\n{BLUE}Checking project files...{RESET}")
    
    files_to_check = {
        "src/crew_orchestrator.py": "Crew Orchestrator",
        "streamlit_app.py": "Streamlit App",
        "CREWAI_SETUP_GUIDE.md": "Setup Guide"
    }
    
    all_ok = True
    for filepath, name in files_to_check.items():
        if Path(filepath).exists():
            print(f"{GREEN}[OK] {name}{RESET}")
        else:
            print(f"{RED}[ERROR] {name} missing{RESET}")
            all_ok = False
    
    return all_ok


def test_crew_initialization():
    """Test basic crew initialization"""
    print(f"\n{BLUE}Testing CrewAI initialization...{RESET}")
    
    try:
        from env_fix import apply_runtime_fixes
        apply_runtime_fixes()
        from crew_orchestrator import EducationCrew
        
        # This will attempt to initialize (may fail if API key invalid)
        crew = EducationCrew(subject="math", rubric_name="primary_math", verbose=False)
        print(f"{GREEN}[OK] Crew initialized successfully{RESET}")
        print(f"   - Subject: math")
        print(f"   - Rubric: primary_math")
        print(f"   - Agents: 5 (Ingestion, Questions, Dialogue, Grading, Feedback)")
        return True
        
    except Exception as e:
        print(f"{YELLOW}[WARN] Crew initialization test skipped{RESET}")
        print(f"   Reason: {str(e)[:100]}")
        print(f"   This is normal if OpenAI API key is invalid or unreachable")
        return False


def print_summary(results):
    """Print summary of all checks"""
    print(f"\n{BLUE}{'='*50}")
    print("VERIFICATION SUMMARY")
    print(f"{'='*50}{RESET}\n")
    
    checks = [
        ("Python Version", results.get("python", False)),
        ("Packages", results.get("imports", False)),
        ("Environment", results.get("env", False)),
        ("Project Files", results.get("files", False)),
        ("Crew Initialization", results.get("crew", False))
    ]
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    for check_name, result in checks:
        status = f"{GREEN}[OK] PASS{RESET}" if result else f"{YELLOW}[WARN] WARN{RESET}"
        print(f"{check_name:.<30} {status}")
    
    print(f"\n{BLUE}Overall: {passed}/{total} checks passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}All systems ready! You can now use CrewAI.{RESET}")
        print(f"\n{YELLOW}Next steps:{RESET}")
        print("1. Review CREWAI_SETUP_GUIDE.md for detailed instructions")
        print("2. Start the Streamlit app: streamlit run streamlit_app.py")
        print("3. Upload a document to test the ingestion workflow")
    else:
        print(f"\n{YELLOW}Some checks did not pass. See above for details.{RESET}")


def main():
    """Run all verification checks"""
    print(f"\n{BLUE}{'='*50}")
    print("CREWAI SYSTEM VERIFICATION")
    print(f"{'='*50}{RESET}")
    
    results = {
        "python": check_python_version(),
        "imports": check_imports(),
        "env": check_env_file(),
        "files": check_crew_files(),
        "crew": test_crew_initialization()
    }
    
    print_summary(results)
    
    print(f"\n{BLUE}{'='*50}{RESET}\n")


if __name__ == "__main__":
    main()
