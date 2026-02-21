#!/usr/bin/env python3
"""
Setup script for Cookie Extractor Bot
This script helps you configure and test the bot setup.
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_success(text):
    print(f"✅ {text}")

def print_error(text):
    print(f"❌ {text}")

def print_warning(text):
    print(f"⚠️  {text}")

def check_python():
    """Check Python version"""
    print_header("Checking Python Version")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python 3.9+ required (found {version.major}.{version.minor})")
        return False

def check_pip():
    """Check pip installation"""
    print_header("Checking pip")
    try:
        result = subprocess.run(['pip', '--version'], capture_output=True, text=True)
        print_success(result.stdout.strip())
        return True
    except:
        print_error("pip not found")
        return False

def install_system_tools():
    """Install system tools"""
    print_header("Installing System Tools")
    system = platform.system().lower()
    
    if system == 'windows':
        print_warning("Windows detected")
        print("Please install manually:")
        print("1. 7-Zip: https://www.7-zip.org/download.html")
        print("2. WinRAR: https://www.rarlab.com/rar_add.htm")
        return False
    
    elif system == 'linux':
        print("Linux detected - Installing p7zip and unrar...")
        try:
            subprocess.run(['sudo', 'apt-get', 'update'], check=False, capture_output=True)
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'p7zip-full', 'unrar'], 
                         check=False, capture_output=True)
            print_success("System tools installed")
            return True
        except Exception as e:
            print_error(f"Failed to install: {e}")
            return False
    
    elif system == 'darwin':
        print("macOS detected - Using Homebrew...")
        try:
            subprocess.run(['brew', 'install', 'p7zip', 'unrar'], 
                         check=False, capture_output=True)
            print_success("System tools installed")
            return True
        except Exception as e:
            print_error(f"Failed to install: {e}")
            return False
    
    return False

def install_python_deps():
    """Install Python dependencies"""
    print_header("Installing Python Dependencies")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                      check=True)
        print_success("Dependencies installed")
        return True
    except Exception as e:
        print_error(f"Failed to install dependencies: {e}")
        return False

def check_external_tools():
    """Check for 7z and unrar"""
    print_header("Checking External Tools")
    
    system = platform.system().lower()
    tools_found = True
    
    # Check 7z
    try:
        if system == 'windows':
            paths = [
                'C:\\Program Files\\7-Zip\\7z.exe',
                'C:\\Program Files (x86)\\7-Zip\\7z.exe',
            ]
            found = False
            for path in paths:
                if os.path.exists(path):
                    print_success(f"7z.exe found: {path}")
                    found = True
                    break
            if not found:
                print_warning("7z.exe not found in standard paths")
                tools_found = False
        else:
            result = subprocess.run(['which', '7z'], capture_output=True, text=True)
            if result.returncode == 0:
                print_success(f"7z found: {result.stdout.strip()}")
            else:
                print_warning("7z not found")
                tools_found = False
    except:
        print_warning("7z not found")
        tools_found = False
    
    # Check unrar
    try:
        if system == 'windows':
            paths = [
                'C:\\Program Files\\WinRAR\\UnRAR.exe',
                'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
            ]
            found = False
            for path in paths:
                if os.path.exists(path):
                    print_success(f"UnRAR.exe found: {path}")
                    found = True
                    break
            if not found:
                print_warning("UnRAR.exe not found in standard paths")
        else:
            result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
            if result.returncode == 0:
                print_success(f"unrar found: {result.stdout.strip()}")
            else:
                print_warning("unrar not found")
    except:
        print_warning("unrar not found")
    
    return tools_found

def create_directories():
    """Create required directories"""
    print_header("Creating Directories")
    
    dirs = ['downloads', 'extracted', 'results', 'logs']
    for d in dirs:
        Path(d).mkdir(exist_ok=True)
        print_success(f"Directory '{d}' ready")

def check_config():
    """Check bot configuration"""
    print_header("Checking Bot Configuration")
    
    try:
        with open('cookie_extractor_bot.py', 'r') as f:
            content = f.read()
            
        if 'API_ID = 23933044' in content:
            print_warning("API_ID not configured - using default")
        else:
            print_success("API_ID configured")
        
        if 'BOT_TOKEN = "8315539700:' in content:
            print_warning("BOT_TOKEN not configured - using default")
        else:
            print_success("BOT_TOKEN configured")
        
        if 'LOG_CHANNEL = -1003747061396' in content:
            print_warning("LOG_CHANNEL not configured - using default")
        else:
            print_success("LOG_CHANNEL configured")
        
        return True
    except:
        print_error("Could not read bot configuration")
        return False

def test_imports():
    """Test Python imports"""
    print_header("Testing Python Imports")
    
    packages = {
        'pyrogram': 'Pyrogram',
        'tgcrypto': 'TGCrypto',
        'aiohttp': 'aiohttp'
    }
    
    all_ok = True
    for package, name in packages.items():
        try:
            __import__(package)
            print_success(f"{name} imported successfully")
        except ImportError:
            print_error(f"{name} not installed")
            all_ok = False
    
    return all_ok

def show_next_steps():
    """Show next steps"""
    print_header("Next Steps")
    
    print("1. Update bot credentials:")
    print("   Edit: cookie_extractor_bot.py")
    print("   Update: API_ID, API_HASH, BOT_TOKEN, LOG_CHANNEL, ADMINS")
    print()
    print("2. (Optional) Configure advanced settings:")
    print("   Edit: config.py")
    print()
    print("3. Run the bot:")
    print("   python cookie_extractor_bot.py")
    print()
    print("4. Or use Docker:")
    print("   docker-compose up -d")

def main():
    """Main setup flow"""
    print("\n")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🍪 Cookie Extractor Bot - Setup Script                 ║")
    print("║   Version 1.0.0                                          ║")
    print("╚══════════════════════════════════════════════════════════╝")
    
    checks = [
        ("Python Version", check_python),
        ("pip Package Manager", check_pip),
        ("Create Directories", create_directories),
        ("Python Dependencies", install_python_deps),
        ("Python Imports", test_imports),
        ("External Tools", check_external_tools),
        ("Bot Configuration", check_config),
    ]
    
    results = []
    for name, check in checks:
        try:
            result = check()
            results.append((name, result))
        except Exception as e:
            print_error(f"Error during {name}: {e}")
            results.append((name, False))
    
    # Summary
    print_header("Setup Summary")
    
    for name, result in results:
        status = "✅" if result else "⚠️"
        print(f"{status} {name}")
    
    critical_ok = all(r[1] for r in results[:5])
    
    if critical_ok:
        print_success("Setup completed successfully!")
        show_next_steps()
        return 0
    else:
        print_error("Some critical checks failed")
        print("\nPlease fix the issues above and run setup again.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
