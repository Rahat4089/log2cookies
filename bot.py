#!/usr/bin/env python3
import os
import sys
import re
import zipfile
import shutil
import hashlib
import time
import random
import string
import subprocess
import asyncio
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple, Union
import queue
import threading
import platform
import signal
import math
import traceback
from pathlib import Path
import uuid
import mimetypes
from urllib.parse import urlparse
import functools

# Third-party imports
try:
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q tqdm colorama")
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)

# PyroFork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError, MessageNotModified
import aiohttp
import aiofiles
import psutil

# Try to import rarfile for password detection only
try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False
    try:
        os.system("pip install -q rarfile")
        import rarfile
        HAS_RARFILE = True
    except:
        HAS_RARFILE = False

# Try to import py7zr for password detection only
try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
    HAS_PY7ZR = False
    try:
        os.system("pip install -q py7zr")
        import py7zr
        HAS_PY7ZR = True
    except:
        HAS_PY7ZR = False

# ==============================================================================
# CONFIGURATION
# ==============================================================================
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAGXx58l22UiiwIMfyuO41417kH9DyMP1t0"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.tgz', '.tbz2'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Archive signatures (magic bytes)
ARCHIVE_SIGNATURES = {
    b'PK\x03\x04': 'zip',
    b'PK\x05\x06': 'zip',
    b'PK\x07\x08': 'zip',
    b'Rar!\x1a\x07': 'rar',
    b'Rar!\x1a\x07\x00': 'rar',
    b'7z\xbc\xaf\x27\x1c': '7z',
    b'\x1f\x8b': 'gz',
    b'\x42\x5a\x68': 'bz2',
    b'\xfd\x37\x7a\x58\x5a\x00': 'xz',
    b'\x75\x73\x74\x61\x72': 'tar',
    b'\x75\x73\x74\x61\x72\x20': 'tar',
}

# Progress update interval (seconds)
PROGRESS_UPDATE_INTERVAL = 5

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
ERROR_LOGS_DIR = os.path.join(BASE_DIR, 'error_logs')

# Create directories
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EXTRACTED_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(ERROR_LOGS_DIR, exist_ok=True)

# Detect system
SYSTEM = platform.system().lower()

# ==============================================================================
# TOOL DETECTION
# ==============================================================================
class ToolDetector:
    """Detect available external tools"""
    
    @staticmethod
    def check_unrar() -> bool:
        """Check if unrar is available"""
        try:
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\WinRAR\\UnRAR.exe',
                    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
                    'unrar.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                result = subprocess.run(['unrar'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def check_7z() -> bool:
        """Check if 7z is available"""
        try:
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\7-Zip\\7z.exe',
                    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                    '7z.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                result = subprocess.run(['7z'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                result = subprocess.run(['which', '7z'], capture_output=True, text=True)
                if result.returncode != 0:
                    result = subprocess.run(['which', '7zz'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def get_tool_path(tool_name: str) -> Optional[str]:
        """Get full path to tool"""
        if tool_name == 'unrar':
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\WinRAR\\UnRAR.exe',
                    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
                ]
                for path in paths:
                    if os.path.exists(path):
                        return path
                return 'unrar.exe'
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else 'unrar'
        
        elif tool_name == '7z':
            if SYSTEM == 'windows':
                paths = [
                    'C:\\Program Files\\7-Zip\\7z.exe',
                    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                ]
                for path in paths:
                    if os.path.exists(path):
                        return path
                return '7z.exe'
            else:
                for cmd in ['7z', '7zz']:
                    result = subprocess.run(['which', cmd], capture_output=True, text=True)
                    if result.returncode == 0:
                        return result.stdout.strip()
                return '7z'
        
        return tool_name

# ==============================================================================
# TOOL STATUS
# ==============================================================================
TOOL_STATUS = {
    'unrar': ToolDetector.check_unrar(),
    '7z': ToolDetector.check_7z(),
}
TOOL_PATHS = {
    'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None,
    '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None,
}

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================
def sanitize_filename(filename: str) -> str:
    """Quick sanitize for filenames"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    """Generate random string for unique filenames"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_file_hash_fast(filepath: str) -> str:
    """Fast file hash (first/last chunks only)"""
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))

def detect_file_type_from_content(file_path: str) -> Optional[str]:
    """Detect file type by reading magic bytes"""
    try:
        with open(file_path, 'rb') as f:
            header = f.read(1024)
        
        # Check against known signatures
        for signature, file_type in ARCHIVE_SIGNATURES.items():
            if header.startswith(signature):
                return file_type
        
        # Check for tar variants
        if header[257:262] in [b'ustar', b'ustar\x00']:
            return 'tar'
        
        return None
    except:
        return None

def detect_file_type_from_url(url: str) -> Optional[str]:
    """Detect file type from URL extension or content-type"""
    # Try to get extension from URL
    parsed = urlparse(url)
    path = parsed.path.lower()
    
    # Check common extensions
    for ext in SUPPORTED_ARCHIVES:
        if path.endswith(ext):
            return ext[1:]  # Remove the dot
    
    # Try to guess from query parameters
    if '.zip' in path or 'zip' in url:
        return 'zip'
    elif '.rar' in path or 'rar' in url:
        return 'rar'
    elif '.7z' in path or '7z' in url:
        return '7z'
    elif '.tar' in path or 'tar' in url:
        return 'tar'
    elif '.gz' in path or 'gz' in url:
        return 'gz'
    elif '.bz2' in path or 'bz2' in url:
        return 'bz2'
    elif '.xz' in path or 'xz' in url:
        return 'xz'
    
    return None

def format_size(size_bytes: int) -> str:
    """Quick size formatting"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f}TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = seconds // 60
        secs = seconds % 60
        return f"{int(mins)}m {int(secs)}s"
    else:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{int(hours)}h {int(mins)}m"

def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable format"""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def human_readable_time(seconds: int) -> str:
    """Convert seconds to human readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m {seconds%60}s"
    elif seconds < 86400:
        return f"{seconds//3600}h {(seconds%3600)//60}m"
    else:
        return f"{seconds//86400}d {(seconds%86400)//3600}h"

def create_progress_bar(percentage: float, width: int = 20) -> str:
    """Create a cool progress bar"""
    filled = int(percentage * width / 100)
    empty = width - filled
    
    # Different styles for different percentages
    if percentage < 30:
        bar = "🟡" * filled + "⚪" * empty
    elif percentage < 70:
        bar = "🟢" * filled + "⚪" * empty
    else:
        bar = "🔵" * filled + "⚪" * empty
    
    return bar

async def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder in one operation"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        # Force garbage collection to close any open handles
        import gc
        gc.collect()
        
        # Try multiple methods
        def delete_folder():
            shutil.rmtree(folder_path, ignore_errors=True)
        
        await asyncio.get_event_loop().run_in_executor(None, delete_folder)
        await asyncio.sleep(0.5)
        
        if os.path.exists(folder_path):
            if SYSTEM == 'windows':
                os.system(f'rmdir /s /q "{folder_path}"')
            else:
                os.system(f'rm -rf "{folder_path}"')
        
        return not os.path.exists(folder_path)
    except Exception as e:
        return False

async def log_error(user_id: int, error_type: str, error_message: str, traceback_str: str = ""):
    """Log errors to file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(ERROR_LOGS_DIR, f"error_{timestamp}_{user_id}.log")
    
    log_content = f"""Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
User ID: {user_id}
Error Type: {error_type}
Error Message: {error_message}

Traceback:
{traceback_str}
"""
    
    async with aiofiles.open(log_file, 'w', encoding='utf-8') as f:
        await f.write(log_content)
    
    return log_file

def run_in_executor(func):
    """Decorator to run blocking functions in executor"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper

# ==============================================================================
# PASSWORD DETECTION
# ==============================================================================
class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    def check_rar_protected(archive_path: str) -> bool:
        """Check RAR password protection"""
        if not HAS_RARFILE:
            if TOOL_STATUS['unrar']:
                try:
                    cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    return 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower()
                except:
                    pass
            return True
        
        try:
            with rarfile.RarFile(archive_path) as rf:
                return rf.needs_password()
        except:
            return True
    
    @staticmethod
    def check_7z_protected(archive_path: str) -> bool:
        """Check 7z password protection"""
        if not HAS_PY7ZR:
            if TOOL_STATUS['7z']:
                try:
                    cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    return 'Encrypted' in result.stdout or 'Password' in result.stdout
                except:
                    pass
            return True
        
        try:
            with py7zr.SevenZipFile(archive_path, mode='r') as sz:
                return sz.password_protected
        except:
            return True
    
    @staticmethod
    def check_zip_protected(archive_path: str) -> bool:
        """Check ZIP password protection"""
        # Try with 7z first (fastest)
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'Encrypted' in result.stdout or 'Password' in result.stdout:
                    return True
            except:
                pass
        
        # Try with unrar (some ZIP use RAR encryption)
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower():
                    return True
            except:
                pass
        
        # Fallback to Python
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
                return False
        except:
            return True
    
    @staticmethod
    async def check_protection(archive_path: str) -> Tuple[bool, Optional[str]]:
        """Check if archive is password protected and detect its type"""
        ext = os.path.splitext(archive_path)[1].lower()
        
        # Also detect by content
        file_type = await run_in_executor(detect_file_type_from_content)(archive_path)
        if file_type and file_type not in ext:
            ext = f'.{file_type}'
        
        try:
            if ext == '.rar' or file_type == 'rar':
                return await run_in_executor(PasswordDetector.check_rar_protected)(archive_path), 'rar'
            elif ext == '.7z' or file_type == '7z':
                return await run_in_executor(PasswordDetector.check_7z_protected)(archive_path), '7z'
            elif ext in ['.zip', '.jar', '.epub'] or file_type == 'zip':
                return await run_in_executor(PasswordDetector.check_zip_protected)(archive_path), 'zip'
            else:
                # For other formats, assume not protected
                return False, ext[1:] if ext else file_type
        except:
            return True, ext[1:] if ext else 'unknown'

# ==============================================================================
# ARCHIVE EXTRACTION - OPTIMIZED PER TYPE
# ==============================================================================
class UltimateArchiveExtractor:
    """Ultimate speed archive extraction - best tool for each format"""
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.total_archives = 1
        self.current_level = 0
        self.progress_callback = None
        self.error_callback = None
        self.last_progress_time = 0
    
    def set_progress_callback(self, callback):
        """Set progress callback"""
        self.progress_callback = callback
    
    def set_error_callback(self, callback):
        """Set error callback"""
        self.error_callback = callback
    
    @run_in_executor
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Extract .7z using 7z.exe (best for 7z)"""
        try:
            cmd = [TOOL_PATHS['7z'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd.append(f'-o{extract_dir}')
            cmd.append(archive_path)
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files, None
            else:
                error = result.stderr.decode() if result.stderr else "Unknown error"
                return [], f"7z extraction failed: {error}"
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_rar_with_unrar(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Extract .rar using UnRAR.exe (best for RAR)"""
        try:
            cmd = [TOOL_PATHS['unrar'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            else:
                cmd.append('-p-')
            cmd.append(archive_path)
            cmd.append(extract_dir + ('\\' if SYSTEM == 'windows' else '/'))
            
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files, None
            else:
                error = result.stderr.decode() if result.stderr else "Unknown error"
                return [], f"UnRAR extraction failed: {error}"
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_zip_fastest(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Extract .zip using fastest available method"""
        # Priority: 7z.exe > unrar.exe > Python zipfile
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'x', '-y']
                if self.password:
                    cmd.append(f'-p{self.password}')
                cmd.append(f'-o{extract_dir}')
                cmd.append(archive_path)
                
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                
                if result.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files, None
            except Exception as e:
                pass
        
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'x', '-y']
                if self.password:
                    cmd.append(f'-p{self.password}')
                else:
                    cmd.append('-p-')
                cmd.append(archive_path)
                cmd.append(extract_dir + ('\\' if SYSTEM == 'windows' else '/'))
                
                result = subprocess.run(cmd, capture_output=True, timeout=300)
                
                if result.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files, None
            except Exception as e:
                pass
        
        # Fallback to Python
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                if self.password:
                    zf.extractall(extract_dir, pwd=self.password.encode())
                else:
                    zf.extractall(extract_dir)
                return zf.namelist(), None
        except RuntimeError as e:
            if 'Bad password' in str(e):
                return [], "Incorrect password"
            return [], str(e)
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_rar_fallback(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Fallback RAR extraction using rarfile"""
        try:
            with rarfile.RarFile(archive_path) as rf:
                if self.password:
                    rf.setpassword(self.password)
                rf.extractall(extract_dir)
                return rf.namelist(), None
        except rarfile.RarWrongPassword:
            return [], "Incorrect password"
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Fallback 7z extraction using py7zr"""
        try:
            with py7zr.SevenZipFile(archive_path, mode='r', password=self.password) as sz:
                sz.extractall(extract_dir)
                return sz.getnames(), None
        except py7zr.exceptions.PasswordRequired:
            return [], "Password required"
        except py7zr.exceptions.WrongPassword:
            return [], "Incorrect password"
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_tar_fast(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            mode = 'r:*'
            with tarfile.open(archive_path, mode) as tf:
                tf.extractall(extract_dir)
                return tf.getnames(), None
        except Exception as e:
            return [], str(e)
    
    @run_in_executor
    def extract_single(self, archive_path: str, extract_dir: str) -> Tuple[List[str], Optional[str]]:
        """Extract a single archive using best tool for its type"""
        if self.stop_extraction:
            return [], "Cancelled"
        
        # Detect file type by content first
        file_type = detect_file_type_from_content(archive_path)
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            # .7z files -> use 7z.exe
            if file_type == '7z' or ext == '.7z':
                if TOOL_STATUS['7z']:
                    return self.extract_7z_with_7z(archive_path, extract_dir)
                elif HAS_PY7ZR:
                    return self.extract_7z_fallback(archive_path, extract_dir)
            
            # .rar files -> use UnRAR.exe
            elif file_type == 'rar' or ext == '.rar':
                if TOOL_STATUS['unrar']:
                    return self.extract_rar_with_unrar(archive_path, extract_dir)
                elif HAS_RARFILE:
                    return self.extract_rar_fallback(archive_path, extract_dir)
            
            # .zip files -> use fastest available
            elif file_type == 'zip' or ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            
            # GZIP files
            elif file_type == 'gz' or ext == '.gz':
                # Check if it's actually a tar.gz
                if archive_path.endswith('.tar.gz') or archive_path.endswith('.tgz'):
                    return self.extract_tar_fast(archive_path, extract_dir)
                else:
                    # Just a gzip file, extract to same name without .gz
                    try:
                        import gzip
                        output_path = os.path.join(extract_dir, os.path.basename(archive_path)[:-3])
                        with gzip.open(archive_path, 'rb') as f_in:
                            with open(output_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        return [os.path.basename(output_path)], None
                    except Exception as e:
                        return [], str(e)
            
            # BZIP2 files
            elif file_type == 'bz2' or ext == '.bz2':
                if archive_path.endswith('.tar.bz2') or archive_path.endswith('.tbz2'):
                    return self.extract_tar_fast(archive_path, extract_dir)
                else:
                    try:
                        import bz2
                        output_path = os.path.join(extract_dir, os.path.basename(archive_path)[:-4])
                        with bz2.open(archive_path, 'rb') as f_in:
                            with open(output_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        return [os.path.basename(output_path)], None
                    except Exception as e:
                        return [], str(e)
            
            # XZ files
            elif file_type == 'xz' or ext == '.xz':
                if archive_path.endswith('.tar.xz'):
                    return self.extract_tar_fast(archive_path, extract_dir)
                else:
                    try:
                        import lzma
                        output_path = os.path.join(extract_dir, os.path.basename(archive_path)[:-3])
                        with lzma.open(archive_path, 'rb') as f_in:
                            with open(output_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        return [os.path.basename(output_path)], None
                    except Exception as e:
                        return [], str(e)
            
            # TAR files
            elif file_type == 'tar' or ext in ['.tar', '.tgz', '.tbz2']:
                return self.extract_tar_fast(archive_path, extract_dir)
            
            # Unknown format, try tar as fallback
            else:
                return self.extract_tar_fast(archive_path, extract_dir)
        
        except Exception as e:
            return [], str(e)
        
        return [], "No suitable extractor found"
    
    @run_in_executor
    def find_archives_fast(self, directory: str) -> List[str]:
        """Find all archives"""
        archives = []
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Check by extension first
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        archives.append(file_path)
                    else:
                        # Check by content
                        file_type = detect_file_type_from_content(file_path)
                        if file_type:
                            archives.append(file_path)
        except:
            pass
        return archives
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, task_id: str = None) -> Tuple[str, List[str]]:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        errors = []
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            # Process archives in this level
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {}
                for archive in current_level:
                    if archive in self.processed_files or self.stop_extraction:
                        continue
                    
                    archive_name = os.path.splitext(os.path.basename(archive))[0]
                    archive_name = sanitize_filename(archive_name)[:50]
                    extract_subdir = os.path.join(level_dir, archive_name)
                    os.makedirs(extract_subdir, exist_ok=True)
                    
                    # Run extraction in executor
                    future = executor.submit(self.extract_single, archive, extract_subdir)
                    futures[future] = (archive, extract_subdir)
                
                for future in as_completed(futures):
                    if self.stop_extraction:
                        executor.shutdown(wait=False)
                        break
                    
                    archive, extract_subdir = futures[future]
                    try:
                        extracted, error = future.result(timeout=300)
                        
                        if error:
                            errors.append(f"{os.path.basename(archive)}: {error}")
                            if self.error_callback:
                                await self.error_callback(f"Error extracting {os.path.basename(archive)}: {error}")
                        else:
                            with self.lock:
                                self.processed_files.add(archive)
                                self.extracted_count += 1
                            
                            new_archives = await run_in_executor(self.find_archives_fast)(extract_subdir)
                            next_level.update(new_archives)
                            
                            with self.lock:
                                total_archives += len(new_archives)
                        
                        # Update progress every time (throttling handled in callback)
                        if self.progress_callback:
                            progress = (self.extracted_count / max(total_archives, 1)) * 100
                            await self.progress_callback(
                                f"📦 Extracting archives...",
                                progress,
                                details={
                                    'current': self.extracted_count,
                                    'total': total_archives,
                                    'level': level,
                                    'stage': 'extraction'
                                },
                                details_text=f"**Archives:** {self.extracted_count}/{total_archives}"
                            )
                    except Exception as e:
                        errors.append(f"{os.path.basename(archive)}: {str(e)}")
            
            current_level = next_level
            level += 1
        
        return base_dir, errors

# ==============================================================================
# COOKIE EXTRACTION
# ==============================================================================
class UltimateCookieExtractor:
    """Ultimate speed cookie extraction with per-site filtering"""
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        # Store files per site with original names
        self.site_files: Dict[str, Dict[str, str]] = {
            site: {} for site in self.target_sites
        }
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.progress_callback = None
        self.error_callback = None
        self.site_totals = {site: 0 for site in self.target_sites}
        self.last_progress_time = 0
        
        # Pre-compile patterns for each site
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
    
    def set_progress_callback(self, callback):
        """Set progress callback"""
        self.progress_callback = callback
    
    def set_error_callback(self, callback):
        """Set error callback"""
        self.error_callback = callback
    
    @run_in_executor
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str, int]]:
        """Find all cookie files with sizes"""
        cookie_files = []
        
        def scan_worker(start_dir):
            local_files = []
            try:
                for root, _, files in os.walk(start_dir):
                    if any(folder in root for folder in COOKIE_FOLDERS):
                        for file in files:
                            if file.endswith(('.txt', '.txt.bak', '.sqlite', '.db')):
                                file_path = os.path.join(root, file)
                                try:
                                    size = os.path.getsize(file_path)
                                    local_files.append((file_path, file, size))
                                except:
                                    local_files.append((file_path, file, 0))
            except:
                pass
            return local_files
        
        # Get top-level directories
        top_dirs = []
        try:
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path):
                    top_dirs.append(item_path)
        except:
            top_dirs = [extract_dir]
        
        # Scan in parallel
        with ThreadPoolExecutor(max_workers=min(20, len(top_dirs) or 1)) as executor:
            futures = [executor.submit(scan_worker, d) for d in (top_dirs or [extract_dir])]
            for future in as_completed(futures):
                cookie_files.extend(future.result())
        
        return cookie_files
    
    def get_unique_filename(self, site: str, orig_name: str) -> str:
        """Generate unique filename"""
        base, ext = os.path.splitext(orig_name)
        
        with self.seen_lock:
            if orig_name not in self.used_filenames[site]:
                self.used_filenames[site].add(orig_name)
                return orig_name
            else:
                random_str = generate_random_string(6)
                new_name = f"{base}_{random_str}{ext}"
                
                while new_name in self.used_filenames[site]:
                    random_str = generate_random_string(6)
                    new_name = f"{base}_{random_str}{ext}"
                
                self.used_filenames[site].add(new_name)
                return new_name
    
    @run_in_executor
    def process_file(self, file_path: str, orig_name: str, file_size: int, extract_dir: str) -> Dict[str, int]:
        """Process a single file - create separate filtered file for each matching site"""
        if self.stop_processing:
            return {}
        
        site_counts = {}
        
        # Skip binary files that are too large
        if file_size > 50 * 1024 * 1024:  # 50MB limit for text files
            return {}
        
        try:
            # Try to read as text, skip if binary
            lines = []
            
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                # Check if file is binary
                sample = f.read(1024)
                if b'\0' in sample:
                    # Probably binary file (SQLite, etc.)
                    return {}
                
                # Reset and read all
                f.seek(0)
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            
            # For each site, collect ONLY lines that contain that specific site
            site_matches: Dict[str, List[Tuple[int, str]]] = {
                site: [] for site in self.target_sites
            }
            
            # Process each line once
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                # Check each site separately - a line can match multiple sites
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        
                        with self.seen_lock:
                            if unique_id not in self.global_seen:
                                self.global_seen.add(unique_id)
                                site_matches[site].append((line_num, line_str))
                                with self.stats_lock:
                                    self.total_found += 1
                                    site_counts[site] = site_counts.get(site, 0) + 1
                                    self.site_totals[site] = self.site_totals.get(site, 0) + 1
            
            # Save SEPARATE file for EACH site that had matches
            for site, matches in site_matches.items():
                if matches:
                    # Sort by line number to maintain original order
                    matches.sort(key=lambda x: x[0])
                    lines_list = [line for _, line in matches]
                    
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    
                    # Write ONLY lines that contain THIS site
                    with open(out_path, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                        f.write('\n'.join(lines_list))
                    
                    with self.seen_lock:
                        self.site_files[site][out_path] = unique_name
            
            with self.stats_lock:
                self.files_processed += 1
            
            return site_counts
                
        except Exception as e:
            if self.error_callback:
                asyncio.run(self.error_callback(f"Error processing {orig_name}: {str(e)}"))
            return {}
    
    async def process_all(self, extract_dir: str, task_id: str = None) -> Dict[str, int]:
        """Process all files"""
        cookie_files = await run_in_executor(self.find_cookie_files)(extract_dir)
        
        if not cookie_files:
            return {}
        
        total_files = len(cookie_files)
        total_size = sum(size for _, _, size in cookie_files)
        
        if self.progress_callback:
            await self.progress_callback(
                f"🔍 Found {total_files} files (Total: {format_size(total_size)})",
                0,
                details={'files': total_files, 'size': total_size, 'stage': 'scanning'}
            )
        
        site_totals = {site: 0 for site in self.target_sites}
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for file_path, orig_name, file_size in cookie_files:
                if self.stop_processing:
                    break
                # Submit to executor
                future = executor.submit(self.process_file, file_path, orig_name, file_size, extract_dir)
                futures.append(future)
            
            completed = 0
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                
                site_counts = future.result()
                
                # Update site totals
                for site, count in site_counts.items():
                    site_totals[site] = site_totals.get(site, 0) + count
                
                completed += 1
                
                # Update progress regularly
                if self.progress_callback:
                    progress = (completed / total_files) * 100
                    
                    # Create domain stats text
                    domains_text = "\n".join([
                        f"  • **{site}:** {self.site_totals.get(site, 0)} entries"
                        for site in self.target_sites
                        if self.site_totals.get(site, 0) > 0
                    ])
                    
                    if not domains_text:
                        domains_text = "  No matches yet"
                    
                    details_text = f"""
**📊 Progress:** {completed}/{total_files} files
**🔍 Total Entries Found:** {self.total_found}

**📁 Per-Domain Stats:**
{domains_text}
"""
                    
                    await self.progress_callback(
                        f"🔍 Filtering cookies...",
                        progress,
                        details={
                            'files_processed': completed,
                            'total_files': total_files,
                            'entries_found': self.total_found,
                            'site_totals': self.site_totals,
                            'stage': 'filtering'
                        },
                        details_text=details_text
                    )
        
        return site_totals
    
    @run_in_executor
    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, Tuple[str, int]]:
        """Create ZIP archives per site"""
        created_zips = {}
        
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            total_size = 0
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                for file_path, unique_name in files_dict.items():
                    if os.path.exists(file_path):
                        zf.write(file_path, unique_name)
                        total_size += os.path.getsize(file_path)
            
            created_zips[site] = (zip_path, total_size)
        
        return created_zips

# ==============================================================================
# BOT CLASS
# ==============================================================================
class CookieExtractorBot:
    """PyroFork Bot for Cookie Extraction"""
    
    def __init__(self):
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        self.user_tasks = {}  # user_id -> task info
        self.user_states = {}  # user_id -> state
        self.user_data = {}  # user_id -> data
        self.last_progress_update = {}  # user_id -> last update time
        self.active_tasks = {}  # task_id -> asyncio task
        
    async def safe_edit_message(self, message: Message, text: str, **kwargs):
        """Safely edit message with flood wait handling"""
        try:
            await message.edit_text(text, **kwargs)
        except MessageNotModified:
            pass
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await message.edit_text(text, **kwargs)
            except:
                pass
        except Exception:
            pass
    
    async def progress_callback(self, current, total, message: Message, action: str, file_name: str = "", file_size: int = 0):
        """Enhanced progress callback for downloads"""
        try:
            user_id = message.chat.id
            
            # Check if task still exists and not cancelled
            if user_id not in self.user_tasks or self.user_tasks[user_id].get('cancelled'):
                return
            
            # Throttle updates (every 5 seconds)
            current_time = time.time()
            if user_id in self.last_progress_update:
                if current_time - self.last_progress_update[user_id] < PROGRESS_UPDATE_INTERVAL:
                    return
            self.last_progress_update[user_id] = current_time
            
            percent = current * 100 / total if total > 0 else 0
            elapsed = time.time() - self.user_tasks[user_id]['start_time'] if 'start_time' in self.user_tasks[user_id] else 0
            
            # Calculate ETA
            if current > 0 and total > 0:
                speed = current / elapsed if elapsed > 0 else 0
                eta = (total - current) / speed if speed > 0 else 0
            else:
                speed = 0
                eta = 0
            
            # Create progress bar
            bar = create_progress_bar(percent, 15)
            
            # Format text
            text = f"""
**{'📥' if 'Download' in action else '📤'} {action}**

`{bar}`  **{percent:.1f}%**

**📄 File:** `{file_name}`
**📊 Size:** {format_size(current)} / {format_size(total) if total > 0 else 'Unknown'}
**⚡ Speed:** {format_size(speed)}/s
**⏱️ Elapsed:** {format_time(elapsed)}
**⏳ ETA:** {format_time(eta) if eta > 0 and total > 0 else 'Calculating...'}

**To cancel:** `/cancel_{self.user_tasks[user_id]['task_id']}`
"""
            
            await self.safe_edit_message(message, text)
        except Exception:
            pass
    
    async def task_progress_callback(self, user_id: int, text: str, percent: float, details: dict = None, details_text: str = ""):
        """Enhanced task progress callback with per-domain stats"""
        try:
            # Check if task still exists and not cancelled
            if user_id not in self.user_tasks or self.user_tasks[user_id].get('cancelled'):
                return
            
            task_info = self.user_tasks.get(user_id)
            if not task_info or not task_info.get('status_message'):
                return
            
            # Throttle updates (every 5 seconds)
            current_time = time.time()
            if user_id in self.last_progress_update:
                if current_time - self.last_progress_update[user_id] < PROGRESS_UPDATE_INTERVAL:
                    return
            self.last_progress_update[user_id] = current_time
            
            elapsed = time.time() - task_info['start_time'] if 'start_time' in task_info else 0
            
            # Create progress bar
            bar = create_progress_bar(percent, 15)
            
            # Get system info
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            
            # Determine stage and create appropriate display
            stage = details.get('stage', 'unknown') if details else 'unknown'
            
            if stage == 'extraction':
                # Extraction progress
                current_archives = details.get('current', 0)
                total_archives = details.get('total', 1)
                level = details.get('level', 0)
                
                message_text = f"""
**📦 Archive Extraction Progress**

`{bar}`  **{percent:.1f}%**

**📋 Status:** {text}
**📊 Archives:** {current_archives}/{total_archives}
**📁 Level:** {level}
**⏱️ Elapsed:** {format_time(elapsed)}

**💻 System:** CPU: {cpu_percent}% | RAM: {memory.percent}%

**To cancel:** `/cancel_{task_info['task_id']}`
"""
            
            elif stage == 'filtering':
                # Cookie filtering progress with per-domain stats
                files_processed = details.get('files_processed', 0)
                total_files = details.get('total_files', 1)
                entries_found = details.get('entries_found', 0)
                site_totals = details.get('site_totals', {})
                
                # Create domain stats table
                domain_stats = ""
                for site, count in site_totals.items():
                    if count > 0:
                        domain_stats += f"  • **{site}:** {count} entries\n"
                
                if not domain_stats:
                    domain_stats = "  No matches yet"
                
                message_text = f"""
**🔍 Cookie Filtering Progress**

`{bar}`  **{percent:.1f}%**

**📋 Status:** {text}
**📁 Files:** {files_processed}/{total_files}
**🔍 Total Entries:** {entries_found}
**⏱️ Elapsed:** {format_time(elapsed)}

**📊 Per-Domain Stats:**
{domain_stats}

**💻 System:** CPU: {cpu_percent}% | RAM: {memory.percent}%

**To cancel:** `/cancel_{task_info['task_id']}`
"""
            
            else:
                # Generic progress
                message_text = f"""
**{'📦' if 'Extracting' in text else '🔍'} Task Progress**

`{bar}`  **{percent:.1f}%**

**📋 Status:** {text}
**⏱️ Elapsed:** {format_time(elapsed)}

{details_text if details_text else ''}

**💻 System:** CPU: {cpu_percent}% | RAM: {memory.percent}%

**To cancel:** `/cancel_{task_info['task_id']}`
"""
            
            await self.safe_edit_message(task_info['status_message'], message_text)
        except Exception as e:
            print(f"Progress callback error: {e}")
    
    async def error_callback(self, user_id: int, error_text: str):
        """Error callback"""
        try:
            # Check if task still exists
            if user_id not in self.user_tasks:
                return
                
            task_info = self.user_tasks.get(user_id)
            if task_info and task_info.get('status_message'):
                await self.safe_edit_message(
                    task_info['status_message'],
                    f"⚠️ **Warning:** {error_text}"
                )
        except:
            pass
    
    async def send_log(self, text: str, level: str = "INFO"):
        """Send log to log channel"""
        if SEND_LOGS:
            try:
                log_text = f"**{level}** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{text}"
                await self.app.send_message(LOG_CHANNEL, log_text)
            except:
                pass
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = """
**🚀 RUTE COOKIE EXTRACTOR BOT** `v2.0`

Welcome! I can extract cookies from archive files with **ULTIMATE SPEED** using 100 threads and external tools.

**📦 Supported formats:** `.zip` `.rar` `.7z` `.tar` `.gz` `.bz2` `.xz` `.tgz` `.tbz2`

**🎯 How to use:**
1️⃣ Forward me an archive file **OR** send a direct link with `/link <url>`
2️⃣ I'll automatically detect the file type
3️⃣ Tell me if it's password protected
4️⃣ Provide domains to search for (comma-separated)
5️⃣ I'll extract and send you filtered cookies

**📊 Progress Updates:**
• Download progress with ETA and speed
• Extraction progress with archive count
• Cookie filtering with per-domain stats
• Updates every {PROGRESS_UPDATE_INTERVAL} seconds

**🛠️ Commands:**
/start - Show this message
/help - Show detailed help
/cancel - Cancel current task
/link <url> - Process from direct link
/stats - Show bot statistics

**📊 Tools status:**
• 7z: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}
• UnRAR: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}

**Example domains:** `facebook.com, instagram.com, tiktok.com`
"""
        await message.reply_text(welcome_text)
    
    async def help_command(self, client: Client, message: Message):
        """Handle /help command"""
        help_text = f"""
**📚 Detailed Help**

**📦 Supported Archives:**
{', '.join(SUPPORTED_ARCHIVES)}

**🔍 Auto-Detection:**
• Detects file type by content (magic bytes)
• Works even with wrong extensions
• Supports nested archives

**🔐 Password Protected Archives:**
• If archive needs password, I'll ask for it
• You can provide password or try without
• Wrong passwords will be reported

**🎯 Domain Filtering:**
• Provide comma-separated domains
• Example: `google.com, youtube.com, github.com`
• I'll create separate ZIP files for each domain
• Each file contains ONLY lines matching that domain
• Live per-domain stats during filtering

**⚡ Performance:**
• Threads: {MAX_WORKERS} parallel workers
• Buffer: {format_size(BUFFER_SIZE)}
• External tools: {'7z' if TOOL_STATUS['7z'] else ''} {'UnRAR' if TOOL_STATUS['unrar'] else ''}

**📊 Progress Updates:**
• Updates every {PROGRESS_UPDATE_INTERVAL} seconds
• Download: Shows file name, size, speed, ETA
• Extraction: Shows archive count and level
• Filtering: Shows per-domain entry counts

**🛑 Cancel Commands:**
• `/cancel` - Cancel current task
• `/cancel_TASKID` - Cancel specific task

**❌ Error Handling:**
• All errors are logged
• Network issues are retried
• Wrong passwords detected
• Corrupted archives reported
"""
        await message.reply_text(help_text)
    
    async def stats_command(self, client: Client, message: Message):
        """Show bot statistics"""
        # Get disk usage
        downloads_size = 0
        extracted_size = 0
        
        for dirpath, _, filenames in os.walk(DOWNLOADS_DIR):
            for f in filenames:
                file_path = os.path.join(dirpath, f)
                try:
                    downloads_size += os.path.getsize(file_path)
                except:
                    pass
        
        for dirpath, _, filenames in os.walk(EXTRACTED_DIR):
            for f in filenames:
                file_path = os.path.join(dirpath, f)
                try:
                    extracted_size += os.path.getsize(file_path)
                except:
                    pass
        
        # Get active tasks
        active_tasks = len(self.user_tasks)
        
        stats_text = f"""
**📊 Bot Statistics**

**🟢 Active Tasks:** {active_tasks}

**💾 Disk Usage:**
• Downloads: {format_size(downloads_size)}
• Extracted: {format_size(extracted_size)}
• Total: {format_size(downloads_size + extracted_size)}

**⚙️ Performance:**
• Threads: {MAX_WORKERS}
• Buffer: {format_size(BUFFER_SIZE)}
• Progress updates: Every {PROGRESS_UPDATE_INTERVAL}s

**🛠️ Tools:**
• 7z: {'✅' if TOOL_STATUS['7z'] else '❌'}
• UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}
• rarfile: {'✅' if HAS_RARFILE else '❌'}
• py7zr: {'✅' if HAS_PY7ZR else '❌'}
"""
        await message.reply_text(stats_text)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        command_text = message.text.strip()
        
        # Check if it's a specific cancel
        task_id = None
        if len(command_text.split()) > 1:
            task_id = command_text.split()[1]
            if task_id.startswith('cancel_'):
                task_id = task_id[7:]
            
            # Find user with this task
            for uid, task_info in self.user_tasks.items():
                if task_info.get('task_id') == task_id:
                    user_id = uid
                    break
        
        if user_id in self.user_tasks:
            task_info = self.user_tasks[user_id]
            task_info['cancelled'] = True
            
            # Cancel the asyncio task if it exists
            if task_id and task_id in self.active_tasks:
                self.active_tasks[task_id].cancel()
            
            # Stop extractors
            if task_info.get('extractor'):
                task_info['extractor'].stop_extraction = True
            if task_info.get('cookie_extractor'):
                task_info['cookie_extractor'].stop_processing = True
            
            await message.reply_text("✅ **Task cancelled.** Cleaning up...")
            
            # Clean up folders in background
            asyncio.create_task(self.cleanup_task(user_id, task_info))
            
            await self.send_log(f"User {user_id} cancelled task {task_id}")
        else:
            await message.reply_text("❌ **No active task found.**")
    
    async def cleanup_task(self, user_id: int, task_info: dict):
        """Clean up task folders in background"""
        # Clean up folders
        if task_info.get('download_path') and os.path.exists(task_info['download_path']):
            await delete_entire_folder(task_info['download_path'])
        if task_info.get('extract_path') and os.path.exists(task_info['extract_path']):
            await delete_entire_folder(task_info['extract_path'])
        
        # Clean up user data
        self.user_tasks.pop(user_id, None)
        self.user_states.pop(user_id, None)
        self.user_data.pop(user_id, None)
        self.last_progress_update.pop(user_id, None)
    
    async def link_command(self, client: Client, message: Message):
        """Handle /link command"""
        user_id = message.from_user.id
        
        # Check if user has active task
        if user_id in self.user_tasks:
            await message.reply_text("❌ **You already have an active task.** Use /cancel first.")
            return
        
        # Get URL
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("❌ **Please provide a URL.**\nExample: `/link https://example.com/file.zip`")
            return
        
        url = parts[1].strip()
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            await message.reply_text("❌ **Invalid URL.** Must start with http:// or https://")
            return
        
        # Create task
        task_id = generate_random_string(8)
        status_msg = await message.reply_text("🔍 **Analyzing link...**")
        
        self.user_tasks[user_id] = {
            'task_id': task_id,
            'status_message': status_msg,
            'cancelled': False,
            'url': url,
            'start_time': time.time()
        }
        
        self.user_states[user_id] = 'waiting_password_check'
        self.user_data[user_id] = {
            'source': 'link',
            'url': url,
            'task_id': task_id
        }
        
        # Try to detect file type from URL
        detected_type = detect_file_type_from_url(url)
        
        if detected_type:
            file_type_msg = f"\n📁 **Detected type:** `.{detected_type}`"
        else:
            file_type_msg = "\n⚠️ **Could not detect file type from URL**\nI'll detect it after download."
        
        # Ask if password protected
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, it's protected", callback_data=f"protected_yes_{task_id}"),
                InlineKeyboardButton("❌ No password", callback_data=f"protected_no_{task_id}")
            ]
        ])
        
        await status_msg.edit_text(
            f"🔒 **Is this archive password protected?**{file_type_msg}",
            reply_markup=keyboard
        )
    
    async def handle_document(self, client: Client, message: Message):
        """Handle forwarded documents"""
        user_id = message.from_user.id
        
        # Check if user has active task
        if user_id in self.user_tasks:
            await message.reply_text("❌ **You already have an active task.** Use /cancel first.")
            return
        
        # Check if it's a supported archive
        document = message.document
        file_name = document.file_name
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # Check file size (Telegram limit is 2GB)
        if document.file_size > 2 * 1024 * 1024 * 1024:
            await message.reply_text("❌ **File too large.** Maximum size is 2GB.")
            return
        
        # Create task
        task_id = generate_random_string(8)
        status_msg = await message.reply_text("📥 **Received archive...**")
        
        self.user_tasks[user_id] = {
            'task_id': task_id,
            'status_message': status_msg,
            'cancelled': False,
            'message': message,
            'start_time': time.time()
        }
        
        self.user_states[user_id] = 'waiting_password_check'
        self.user_data[user_id] = {
            'source': 'forward',
            'message_id': message.id,
            'file_name': file_name,
            'file_size': document.file_size,
            'task_id': task_id
        }
        
        # Determine file type message
        if file_ext in SUPPORTED_ARCHIVES:
            file_type_msg = f"\n📁 **Type:** `{file_ext}`"
        else:
            file_type_msg = f"\n⚠️ **Extension `{file_ext}` not in supported list**\nI'll try to detect by content."
        
        # Ask if password protected
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, it's protected", callback_data=f"protected_yes_{task_id}"),
                InlineKeyboardButton("❌ No password", callback_data=f"protected_no_{task_id}")
            ]
        ])
        
        await status_msg.edit_text(
            f"**📄 File:** `{file_name}`\n"
            f"**📊 Size:** {human_readable_size(document.file_size)}"
            f"{file_type_msg}\n\n"
            f"🔒 **Is this archive password protected?**",
            reply_markup=keyboard
        )
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        # Verify task ownership
        task_id = data.split('_')[-1]
        if user_id not in self.user_tasks or self.user_tasks[user_id]['task_id'] != task_id:
            await callback_query.answer("❌ This is not your task or it has expired.", show_alert=True)
            return
        
        await callback_query.answer()
        
        try:
            if data.startswith('protected_yes'):
                # Ask for password
                self.user_states[user_id] = 'waiting_password'
                self.user_data[user_id]['protected'] = True
                
                await callback_query.message.edit_text(
                    "🔑 **Please enter the password for this archive:**\n\n"
                    "Send the password as a text message.\n"
                    "To cancel: /cancel"
                )
            
            elif data.startswith('protected_no'):
                self.user_data[user_id]['protected'] = False
                self.user_data[user_id]['password'] = None
                self.user_states[user_id] = 'waiting_domains'
                
                await callback_query.message.edit_text(
                    "🎯 **Please enter the domains to search for (comma-separated):**\n\n"
                    "Example: `facebook.com, instagram.com, tiktok.com`\n\n"
                    "To cancel: /cancel"
                )
        except Exception as e:
            await callback_query.message.edit_text(f"❌ **Error:** {str(e)}")
    
    async def handle_text(self, client: Client, message: Message):
        """Handle text messages (password or domains)"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        try:
            if state == 'waiting_password':
                # Save password
                password = message.text.strip()
                self.user_data[user_id]['password'] = password if password else None
                self.user_states[user_id] = 'waiting_domains'
                
                await message.reply_text(
                    "✅ **Password saved!**\n\n"
                    "🎯 **Please enter the domains to search for (comma-separated):**\n\n"
                    "Example: `facebook.com, instagram.com, tiktok.com`\n\n"
                    "To cancel: /cancel"
                )
            
            elif state == 'waiting_domains':
                # Parse domains
                domains_text = message.text.strip()
                domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
                
                if not domains:
                    await message.reply_text("❌ **Please enter at least one domain.**")
                    return
                
                # Validate domains (basic check)
                valid_domains = []
                invalid_domains = []
                for domain in domains:
                    if re.match(r'^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
                        valid_domains.append(domain)
                    else:
                        invalid_domains.append(domain)
                
                if invalid_domains:
                    await message.reply_text(
                        f"❌ **Invalid domains:** {', '.join(invalid_domains)}\n"
                        f"Please use valid domain names like `example.com`"
                    )
                    return
                
                self.user_data[user_id]['domains'] = valid_domains
                self.user_states[user_id] = 'processing'
                
                # Start processing in background task
                task_id = self.user_data[user_id]['task_id']
                task = asyncio.create_task(self.process_task(user_id, message))
                self.active_tasks[task_id] = task
                
                # Remove from active tasks when done
                def done_callback(fut):
                    if task_id in self.active_tasks:
                        del self.active_tasks[task_id]
                
                task.add_done_callback(done_callback)
        
        except Exception as e:
            await message.reply_text(f"❌ **Error:** {str(e)}")
            await self.send_log(f"Error in text handler for user {user_id}: {str(e)}", "ERROR")
    
    async def process_task(self, user_id: int, message: Message):
        """Process the task (download, extract, filter, send)"""
        task_info = self.user_tasks.get(user_id)
        if not task_info or task_info.get('cancelled'):
            return
        
        data = self.user_data[user_id]
        status_msg = task_info['status_message']
        
        try:
            # Create unique folders
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = f"{user_id}_{timestamp}_{generate_random_string(4)}"
            
            download_path = os.path.join(DOWNLOADS_DIR, unique_id)
            extract_path = os.path.join(EXTRACTED_DIR, unique_id)
            result_folder = os.path.join(RESULTS_DIR, datetime.now().strftime('%Y-%m-%d'))
            
            os.makedirs(download_path, exist_ok=True)
            os.makedirs(extract_path, exist_ok=True)
            os.makedirs(result_folder, exist_ok=True)
            
            # Update task info
            task_info['download_path'] = download_path
            task_info['extract_path'] = extract_path
            
            # STEP 1: Download the file
            await self.safe_edit_message(status_msg, "📥 **Starting download...**")
            
            archive_path = None
            file_name = ""
            file_size = 0
            
            if data['source'] == 'forward':
                # Download from forwarded message
                try:
                    msg = await self.app.get_messages(message.chat.id, data['message_id'])
                    
                    if msg and msg.document:
                        file_name = msg.document.file_name
                        file_size = msg.document.file_size
                        archive_path = os.path.join(download_path, sanitize_filename(file_name))
                        
                        # Download with progress
                        await msg.download(
                            file_name=archive_path,
                            progress=self.progress_callback,
                            progress_args=(status_msg, "Downloading...", file_name, file_size)
                        )
                    else:
                        raise Exception("Original message not found or not a document")
                except Exception as e:
                    raise Exception(f"Download failed: {str(e)}")
            
            else:  # link
                # Download from URL
                url = data['url']
                
                # First, get headers to determine file name and type
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.head(url, allow_redirects=True, timeout=30) as resp:
                            if resp.status != 200:
                                # Some servers don't support HEAD, try GET with range
                                pass
                            else:
                                # Try to get filename from Content-Disposition
                                content_disposition = resp.headers.get('Content-Disposition', '')
                                if 'filename=' in content_disposition:
                                    file_name = content_disposition.split('filename=')[1].strip('"\'')
                                else:
                                    # Get from URL
                                    parsed = urlparse(str(resp.url))
                                    file_name = os.path.basename(parsed.path)
                                
                                file_size = int(resp.headers.get('content-length', 0))
                                content_type = resp.headers.get('content-type', '')
                except:
                    # Fallback to URL parsing
                    parsed = urlparse(url)
                    file_name = os.path.basename(parsed.path)
                    file_size = 0
                
                if not file_name or '.' not in file_name:
                    # Try to detect from content-type or generate name
                    if 'content_type' in locals() and content_type:
                        # Map content-type to extension
                        content_type_map = {
                            'application/zip': '.zip',
                            'application/x-rar-compressed': '.rar',
                            'application/x-7z-compressed': '.7z',
                            'application/x-tar': '.tar',
                            'application/gzip': '.gz',
                            'application/x-bzip2': '.bz2',
                            'application/x-xz': '.xz',
                        }
                        ext = content_type_map.get(content_type, '.bin')
                        file_name = f"archive_{generate_random_string(8)}{ext}"
                    else:
                        file_name = f"archive_{generate_random_string(8)}.bin"
                
                archive_path = os.path.join(download_path, sanitize_filename(file_name))
                
                # Download with aiohttp
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3600)) as resp:
                            if resp.status != 200:
                                raise Exception(f"HTTP {resp.status}")
                            
                            # Update file_size if we got it from headers
                            if file_size == 0:
                                file_size = int(resp.headers.get('content-length', 0))
                            
                            downloaded = 0
                            start_time = time.time()
                            
                            async with aiofiles.open(archive_path, 'wb') as f:
                                async for chunk in resp.content.iter_chunked(1024 * 1024):
                                    if task_info.get('cancelled'):
                                        raise Exception("Cancelled by user")
                                    
                                    await f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    # Update progress every 5 seconds
                                    current_time = time.time()
                                    if user_id not in self.last_progress_update or \
                                       current_time - self.last_progress_update.get(user_id, 0) >= PROGRESS_UPDATE_INTERVAL:
                                        self.last_progress_update[user_id] = current_time
                                        
                                        percent = (downloaded / file_size) * 100 if file_size > 0 else 0
                                        elapsed = current_time - start_time
                                        speed = downloaded / elapsed if elapsed > 0 else 0
                                        eta = (file_size - downloaded) / speed if speed > 0 and file_size > 0 else 0
                                        
                                        bar = create_progress_bar(percent, 15)
                                        
                                        text = f"""
**📥 Downloading...**

`{bar}`  **{percent:.1f}%**

**📄 File:** `{file_name}`
**📊 Size:** {format_size(downloaded)} / {format_size(file_size) if file_size > 0 else 'Unknown'}
**⚡ Speed:** {format_size(speed)}/s
**⏱️ Elapsed:** {format_time(elapsed)}
**⏳ ETA:** {format_time(eta) if eta > 0 and file_size > 0 else 'Calculating...'}

**To cancel:** `/cancel_{task_info['task_id']}`
"""
                                        await self.safe_edit_message(status_msg, text)
                except asyncio.TimeoutError:
                    raise Exception("Download timeout")
                except aiohttp.ClientError as e:
                    raise Exception(f"Network error: {str(e)}")
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            if not os.path.exists(archive_path) or os.path.getsize(archive_path) == 0:
                raise Exception("Download failed: File is empty or missing")
            
            # Detect file type after download
            detected_type = detect_file_type_from_content(archive_path)
            file_ext = os.path.splitext(archive_path)[1].lower()
            
            type_info = f"📁 **Detected type:** "
            if detected_type:
                type_info += f"`.{detected_type}`"
                if file_ext and f".{detected_type}" != file_ext:
                    type_info += f" (extension was `{file_ext}`)"
            else:
                type_info += f"`{file_ext if file_ext else 'Unknown'}`"
            
            await self.safe_edit_message(status_msg, f"✅ **Download complete!**\n{type_info}")
            await self.send_log(f"User {user_id} downloaded {file_name} ({format_size(file_size)})")
            
            # STEP 2: Check if password is correct (quick test)
            if data.get('password'):
                await self.safe_edit_message(status_msg, "🔑 **Verifying password...**")
                
                # Quick test with first archive
                test_extractor = UltimateArchiveExtractor(data['password'])
                test_extractor.stop_extraction = True  # Only test first file
                
                # Test with first few bytes
                try:
                    test_dir = os.path.join(extract_path, "test")
                    os.makedirs(test_dir, exist_ok=True)
                    _, test_error = await run_in_executor(test_extractor.extract_single)(archive_path, test_dir)
                    
                    if test_error and "password" in test_error.lower():
                        raise Exception(f"Incorrect password: {test_error}")
                    
                    # Clean up test dir
                    await delete_entire_folder(test_dir)
                except Exception as e:
                    if "password" in str(e).lower():
                        raise Exception(f"Incorrect password. Please try again with /cancel and restart.")
            
            # STEP 3: Extract archives
            await self.safe_edit_message(status_msg, "📦 **Extracting archives...**")
            
            extractor = UltimateArchiveExtractor(data.get('password'))
            task_info['extractor'] = extractor
            
            # Set progress and error callbacks
            async def extract_progress(text, percent, details=None, details_text=""):
                await self.task_progress_callback(user_id, text, percent, details, details_text)
            
            async def extract_error(error_text):
                await self.error_callback(user_id, error_text)
            
            extractor.set_progress_callback(extract_progress)
            extractor.set_error_callback(extract_error)
            
            extract_dir, extract_errors = await extractor.extract_all_nested(archive_path, extract_path, unique_id)
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            if extract_errors:
                error_summary = "\n".join(extract_errors[:5])
                if len(extract_errors) > 5:
                    error_summary += f"\n... and {len(extract_errors) - 5} more errors"
                await self.error_callback(user_id, f"Extraction warnings:\n{error_summary}")
            
            # STEP 4: Filter cookies
            await self.safe_edit_message(status_msg, "🔍 **Filtering cookies...**")
            
            cookie_extractor = UltimateCookieExtractor(data['domains'])
            task_info['cookie_extractor'] = cookie_extractor
            
            # Set progress and error callbacks
            async def cookie_progress(text, percent, details=None, details_text=""):
                await self.task_progress_callback(user_id, text, percent, details, details_text)
            
            async def cookie_error(error_text):
                await self.error_callback(user_id, error_text)
            
            cookie_extractor.set_progress_callback(cookie_progress)
            cookie_extractor.set_error_callback(cookie_error)
            
            site_totals = await cookie_extractor.process_all(extract_dir, unique_id)
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            # STEP 5: Create ZIPs
            if cookie_extractor.total_found > 0:
                await self.safe_edit_message(status_msg, "📦 **Creating ZIP archives...**")
                
                created_zips = await run_in_executor(cookie_extractor.create_site_zips)(extract_dir, result_folder)
                
                # Send files to user
                for site, (zip_path, zip_size) in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        file_count = len(cookie_extractor.site_files[site])
                        
                        caption = f"""
**✅ {site} Cookies**

📊 **Files:** {file_count}
🔍 **Entries:** site_totals.get(site, 0)
📦 **Size:** {format_size(zip_size)}

#Cookies #{site.replace('.', '_')}
"""
                        
                        try:
                            await message.reply_document(
                                document=zip_path,
                                caption=caption,
                                file_name=f"{site}_cookies.zip"
                            )
                        except Exception as e:
                            await self.error_callback(user_id, f"Failed to send {site}: {str(e)}")
                
                # Summary
                total_files = sum(len(files) for files in cookie_extractor.site_files.values())
                
                summary = f"""
**✅ Extraction Complete!**

**📊 Statistics:**
• Files processed: {cookie_extractor.files_processed}
• Total entries: {cookie_extractor.total_found}
• ZIP archives: {len(created_zips)}
• Total files: {total_files}

**📁 Per-domain results:**
"""
                
                for site in data['domains']:
                    if site in cookie_extractor.site_files:
                        files_count = len(cookie_extractor.site_files[site])
                        entries = site_totals.get(site, 0)
                        if files_count > 0:
                            summary += f"\n• **{site}:** {files_count} files | {entries} entries"
                
                elapsed = time.time() - task_info['start_time']
                summary += f"\n\n**⏱️ Total time:** {format_time(elapsed)}"
                
                await self.safe_edit_message(status_msg, summary)
                
                # Log to channel
                log_text = f"""
**Task Completed**
User: `{user_id}`
Domains: {', '.join(data['domains'])}
Files processed: {cookie_extractor.files_processed}
Entries found: {cookie_extractor.total_found}
Time: {format_time(elapsed)}
"""
                await self.send_log(log_text)
            
            else:
                await self.safe_edit_message(status_msg, "❌ **No matching cookies found.**")
                await self.send_log(f"User {user_id}: No cookies found for {', '.join(data['domains'])}")
            
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            
            # Log error
            log_file = await log_error(user_id, type(e).__name__, error_msg, tb)
            
            # Send error message to user
            if "Cancelled" in error_msg:
                await self.safe_edit_message(status_msg, "✅ **Task cancelled.**")
            elif "Incorrect password" in error_msg:
                await self.safe_edit_message(
                    status_msg,
                    "❌ **Incorrect password.** Please try again with the correct password.\n"
                    "Use /cancel and restart."
                )
            elif "Password required" in error_msg:
                await self.safe_edit_message(
                    status_msg,
                    "❌ **Password required.** This archive needs a password.\n"
                    "Use /cancel and restart with password."
                )
            else:
                await self.safe_edit_message(
                    status_msg,
                    f"❌ **Error:** {error_msg}\n\nError has been logged."
                )
            
            # Send error log to admin
            if user_id in ADMINS:
                try:
                    await message.reply_document(
                        document=log_file,
                        caption=f"❌ Error log for user {user_id}"
                    )
                except:
                    pass
            
            await self.send_log(f"Error for user {user_id}: {error_msg}", "ERROR")
        
        finally:
            # Cleanup
            if 'download_path' in task_info and os.path.exists(task_info['download_path']):
                await delete_entire_folder(task_info['download_path'])
            if 'extract_path' in task_info and os.path.exists(task_info['extract_path']):
                await delete_entire_folder(task_info['extract_path'])
            
            # Remove user data
            self.user_tasks.pop(user_id, None)
            self.user_states.pop(user_id, None)
            self.user_data.pop(user_id, None)
            self.last_progress_update.pop(user_id, None)
    
    async def run(self):
        """Run the bot"""
        print(f"""
╔══════════════════════════════════════════════════════════╗
║     🚀 COOKIE EXTRACTOR BOT - ULTIMATE EDITION 🚀       ║
╠══════════════════════════════════════════════════════════╣
║ API ID: {API_ID}                                            ║
║ Bot Token: {BOT_TOKEN[:10]}...                                    ║
║ Log Channel: {LOG_CHANNEL}                                  ║
║ Admins: {ADMINS}                                   ║
╠══════════════════════════════════════════════════════════╣
║ Tools:                                                    ║
║   • 7z: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}                         ║
║   • UnRAR: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}                      ║
║   • rarfile: {'✅ Available' if HAS_RARFILE else '❌ Not found'}                    ║
║   • py7zr: {'✅ Available' if HAS_PY7ZR else '❌ Not found'}                       ║
╠══════════════════════════════════════════════════════════╣
║ Features:                                                 ║
║   • Auto file type detection (magic bytes)               ║
║   • Support for all archive formats                       ║
║   • 100 threads parallel processing                       ║
║   • Live progress updates every {PROGRESS_UPDATE_INTERVAL}s                 ║
║   • Per-domain cookie counts during filtering             ║
╚══════════════════════════════════════════════════════════╝
        """)
        
        # Register handlers
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.start_command(client, message)
        
        @self.app.on_message(filters.command("help"))
        async def help_handler(client, message):
            await self.help_command(client, message)
        
        @self.app.on_message(filters.command("stats"))
        async def stats_handler(client, message):
            await self.stats_command(client, message)
        
        @self.app.on_message(filters.command("cancel"))
        async def cancel_handler(client, message):
            await self.cancel_command(client, message)
        
        @self.app.on_message(filters.command("link"))
        async def link_handler(client, message):
            await self.link_command(client, message)
        
        @self.app.on_message(filters.document)
        async def document_handler(client, message):
            await self.handle_document(client, message)
        
        @self.app.on_message(filters.text & filters.private)
        async def text_handler(client, message):
            await self.handle_text(client, message)
        
        @self.app.on_callback_query()
        async def callback_handler(client, callback_query):
            await self.handle_callback(client, callback_query)
        
        # Start the bot
        await self.app.start()
        print("✅ Bot is running! Press Ctrl+C to stop.")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        print("\n🛑 Shutting down...")
        await self.app.stop()
        print("✅ Bot stopped.")

# ==============================================================================
# MAIN
# ==============================================================================
async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\n👋 Received interrupt signal")
        await bot.stop()
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        traceback.print_exc()
        
        # Log fatal error
        log_file = await log_error(0, "FatalError", str(e), traceback.format_exc())
        print(f"📝 Error logged to: {log_file}")

if __name__ == "__main__":
    asyncio.run(main())
