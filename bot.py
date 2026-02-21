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
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple, Union
import queue
import threading
import platform
import signal
import math
from pathlib import Path

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
from pyrogram.errors import FloodWait
import aiohttp
import aiofiles

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
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')

# Create directories
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EXTRACTED_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

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

def format_size(size_bytes: int) -> str:
    """Quick size formatting"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

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
    except:
        return False

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
    
    def set_progress_callback(self, callback):
        """Set progress callback"""
        self.progress_callback = callback
    
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
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
                return files
            return []
        except:
            return []
    
    def extract_rar_with_unrar(self, archive_path: str, extract_dir: str) -> List[str]:
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
                return files
            return []
        except:
            return []
    
    def extract_zip_fastest(self, archive_path: str, extract_dir: str) -> List[str]:
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
                    return files
            except:
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
                    return files
            except:
                pass
        
        # Fallback to Python
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                if self.password:
                    zf.extractall(extract_dir, pwd=self.password.encode())
                else:
                    zf.extractall(extract_dir)
                return zf.namelist()
        except:
            return []
    
    def extract_rar_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback RAR extraction using rarfile"""
        try:
            with rarfile.RarFile(archive_path) as rf:
                if self.password:
                    rf.setpassword(self.password)
                rf.extractall(extract_dir)
                return rf.namelist()
        except:
            return []
    
    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback 7z extraction using py7zr"""
        try:
            with py7zr.SevenZipFile(archive_path, mode='r', password=self.password) as sz:
                sz.extractall(extract_dir)
                return sz.getnames()
        except:
            return []
    
    def extract_tar_fast(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except:
            return []
    
    def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract a single archive using best tool for its type"""
        if self.stop_extraction:
            return []
        
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            # .7z files -> use 7z.exe
            if ext == '.7z':
                if TOOL_STATUS['7z']:
                    return self.extract_7z_with_7z(archive_path, extract_dir)
                elif HAS_PY7ZR:
                    return self.extract_7z_fallback(archive_path, extract_dir)
            
            # .rar files -> use UnRAR.exe
            elif ext == '.rar':
                if TOOL_STATUS['unrar']:
                    return self.extract_rar_with_unrar(archive_path, extract_dir)
                elif HAS_RARFILE:
                    return self.extract_rar_fallback(archive_path, extract_dir)
            
            # .zip files -> use fastest available (7z.exe > unrar.exe > Python)
            elif ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            
            # Other formats (tar, gz, etc.)
            else:
                return self.extract_tar_fast(archive_path, extract_dir)
        
        except:
            pass
        
        return []
    
    def find_archives_fast(self, directory: str) -> List[str]:
        """Find all archives"""
        archives = []
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        archives.append(os.path.join(root, file))
        except:
            pass
        return archives
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, task_id: str = None) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        
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
                    
                    future = executor.submit(self.extract_single, archive, extract_subdir)
                    futures[future] = (archive, extract_subdir)
                
                for future in as_completed(futures):
                    if self.stop_extraction:
                        executor.shutdown(wait=False)
                        break
                    
                    archive, extract_subdir = futures[future]
                    try:
                        extracted = future.result(timeout=60)
                        with self.lock:
                            self.processed_files.add(archive)
                            self.extracted_count += 1
                        
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                        
                        with self.lock:
                            total_archives += len(new_archives)
                        
                        if self.progress_callback:
                            progress = (self.extracted_count / total_archives) * 100
                            await self.progress_callback(
                                f"📦 Extracting archives... ({self.extracted_count}/{total_archives})",
                                progress
                            )
                    except:
                        pass
            
            current_level = next_level
            level += 1
        
        return base_dir

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
        
        # Pre-compile patterns for each site
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
    
    def set_progress_callback(self, callback):
        """Set progress callback"""
        self.progress_callback = callback
    
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
        """Find all cookie files"""
        cookie_files = []
        
        def scan_worker(start_dir):
            local_files = []
            try:
                for root, _, files in os.walk(start_dir):
                    if any(folder in root for folder in COOKIE_FOLDERS):
                        for file in files:
                            if file.endswith(('.txt', '.txt.bak')):
                                local_files.append((os.path.join(root, file), file))
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
    
    def process_file(self, file_path: str, orig_name: str, extract_dir: str):
        """Process a single file - create separate filtered file for each matching site"""
        if self.stop_processing:
            return
            
        try:
            # Read file
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
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
            
            # Save SEPARATE file for EACH site that had matches
            files_saved = 0
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
                    
                    files_saved += 1
            
            with self.stats_lock:
                self.files_processed += 1
                
        except Exception as e:
            pass
    
    async def process_all(self, extract_dir: str, task_id: str = None):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        if self.progress_callback:
            await self.progress_callback(f"🔍 Found {len(cookie_files)} files to process", 0)
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for file_path, orig_name in cookie_files:
                if self.stop_processing:
                    break
                future = executor.submit(self.process_file, file_path, orig_name, extract_dir)
                futures.append(future)
            
            completed = 0
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
                completed += 1
                
                if self.progress_callback and completed % 10 == 0:
                    progress = (completed / len(cookie_files)) * 100
                    await self.progress_callback(
                        f"🔍 Filtering cookies... ({completed}/{len(cookie_files)} files, {self.total_found} entries)",
                        progress
                    )
    
    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        """Create ZIP archives per site"""
        created_zips = {}
        
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                for file_path, unique_name in files_dict.items():
                    if os.path.exists(file_path):
                        zf.write(file_path, unique_name)
            
            created_zips[site] = zip_path
        
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
        
    async def progress_callback(self, current, total, message: Message, action: str):
        """Progress callback for downloads"""
        try:
            percent = current * 100 / total
            progress = f"[{'=' * int(percent/5)}{' ' * (20 - int(percent/5))}]"
            
            text = f"**{action}**\n"
            text += f"{progress} {percent:.1f}%\n"
            text += f"📊 {human_readable_size(current)} / {human_readable_size(total)}"
            
            await message.edit_text(text)
        except:
            pass
    
    async def task_progress_callback(self, user_id: int, text: str, percent: float):
        """Task progress callback"""
        try:
            task_info = self.user_tasks.get(user_id)
            if task_info and task_info.get('status_message'):
                progress = f"[{'=' * int(percent/5)}{' ' * (20 - int(percent/5))}]"
                
                message_text = f"**📦 Task Progress**\n\n"
                message_text += f"{text}\n"
                message_text += f"{progress} {percent:.1f}%\n\n"
                message_text += f"**To cancel:** `/cancel_{task_info['task_id']}`"
                
                await task_info['status_message'].edit_text(message_text)
        except:
            pass
    
    async def send_log(self, text: str):
        """Send log to log channel"""
        if SEND_LOGS:
            try:
                await self.app.send_message(LOG_CHANNEL, text)
            except:
                pass
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = """
**🚀 RUTE COOKIE EXTRACTOR BOT**

Welcome! I can extract cookies from archive files (.zip, .rar, .7z, etc.)

**How to use:**
1. Forward me an archive file OR send a direct link with `/link <url>`
2. Tell me if it's password protected
3. Provide domains to search for (comma-separated)
4. I'll extract and send you the filtered cookies

**Commands:**
/start - Show this message
/help - Show help
/cancel - Cancel current task
/link <url> - Process from direct link

**Example domains:** `facebook.com, instagram.com, tiktok.com`
"""
        await message.reply_text(welcome_text)
    
    async def help_command(self, client: Client, message: Message):
        """Handle /help command"""
        help_text = """
**📚 Help & Commands**

**Supported formats:** .zip, .rar, .7z, .tar, .gz, .bz2, .xz

**Password protected archives:**
- If archive needs password, I'll ask for it
- You can provide password or try without

**Domains:**
- Provide comma-separated domains
- Example: `google.com, youtube.com, github.com`
- I'll create separate files for each domain

**Cancel:**
- Use `/cancel` to stop current task
- Or `/cancel_TASKID` with specific task ID

**Speed:**
- Using {MAX_WORKERS} threads
- External tools: {TOOL_STATUS['7z'] and '✓ 7z' or '✗ 7z'} | {TOOL_STATUS['unrar'] and '✓ UnRAR' or '✗ UnRAR'}
""".format(
    MAX_WORKERS=MAX_WORKERS,
    TOOL_STATUS=TOOL_STATUS
)
        await message.reply_text(help_text)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        
        # Check if it's a specific cancel
        if len(message.text.split()) > 1:
            task_id = message.text.split()[1]
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
            
            # Stop extractors
            if task_info.get('extractor'):
                task_info['extractor'].stop_extraction = True
            if task_info.get('cookie_extractor'):
                task_info['cookie_extractor'].stop_processing = True
            
            await message.reply_text("✅ Task cancelled. Cleaning up...")
            
            # Clean up folders
            if task_info.get('download_path') and os.path.exists(task_info['download_path']):
                await delete_entire_folder(task_info['download_path'])
            if task_info.get('extract_path') and os.path.exists(task_info['extract_path']):
                await delete_entire_folder(task_info['extract_path'])
            
            # Clean up user data
            self.user_tasks.pop(user_id, None)
            self.user_states.pop(user_id, None)
            self.user_data.pop(user_id, None)
        else:
            await message.reply_text("❌ No active task found.")
    
    async def link_command(self, client: Client, message: Message):
        """Handle /link command"""
        user_id = message.from_user.id
        
        # Check if user has active task
        if user_id in self.user_tasks:
            await message.reply_text("❌ You already have an active task. Use /cancel first.")
            return
        
        # Get URL
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("❌ Please provide a URL. Example: `/link https://example.com/file.zip`")
            return
        
        url = parts[1].strip()
        
        # Create task
        task_id = generate_random_string(8)
        status_msg = await message.reply_text("📥 **Starting download...**")
        
        self.user_tasks[user_id] = {
            'task_id': task_id,
            'status_message': status_msg,
            'cancelled': False,
            'url': url
        }
        
        self.user_states[user_id] = 'waiting_password_check'
        self.user_data[user_id] = {
            'source': 'link',
            'url': url,
            'task_id': task_id
        }
        
        # Ask if password protected
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, it's protected", callback_data=f"protected_yes_{task_id}"),
                InlineKeyboardButton("❌ No password", callback_data=f"protected_no_{task_id}")
            ]
        ])
        
        await status_msg.edit_text(
            "🔒 **Is this archive password protected?**",
            reply_markup=keyboard
        )
    
    async def handle_document(self, client: Client, message: Message):
        """Handle forwarded documents"""
        user_id = message.from_user.id
        
        # Check if user has active task
        if user_id in self.user_tasks:
            await message.reply_text("❌ You already have an active task. Use /cancel first.")
            return
        
        # Check if it's a supported archive
        document = message.document
        file_name = document.file_name
        file_ext = os.path.splitext(file_name)[1].lower()
        
        if file_ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"❌ Unsupported file format. Supported: {', '.join(SUPPORTED_ARCHIVES)}"
            )
            return
        
        # Create task
        task_id = generate_random_string(8)
        status_msg = await message.reply_text("📥 **Received archive...**")
        
        self.user_tasks[user_id] = {
            'task_id': task_id,
            'status_message': status_msg,
            'cancelled': False,
            'message': message
        }
        
        self.user_states[user_id] = 'waiting_password_check'
        self.user_data[user_id] = {
            'source': 'forward',
            'message_id': message.id,
            'file_name': file_name,
            'file_size': document.file_size,
            'task_id': task_id
        }
        
        # Ask if password protected
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, it's protected", callback_data=f"protected_yes_{task_id}"),
                InlineKeyboardButton("❌ No password", callback_data=f"protected_no_{task_id}")
            ]
        ])
        
        await status_msg.edit_text(
            f"📄 **File:** `{file_name}`\n📊 **Size:** {human_readable_size(document.file_size)}\n\n🔒 **Is this archive password protected?**",
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
    
    async def handle_text(self, client: Client, message: Message):
        """Handle text messages (password or domains)"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states:
            return
        
        state = self.user_states[user_id]
        
        if state == 'waiting_password':
            # Save password
            password = message.text.strip()
            self.user_data[user_id]['password'] = password if password else None
            self.user_states[user_id] = 'waiting_domains'
            
            await message.reply_text(
                "✅ Password saved!\n\n"
                "🎯 **Please enter the domains to search for (comma-separated):**\n\n"
                "Example: `facebook.com, instagram.com, tiktok.com`\n\n"
                "To cancel: /cancel"
            )
        
        elif state == 'waiting_domains':
            # Parse domains
            domains_text = message.text.strip()
            domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
            
            if not domains:
                await message.reply_text("❌ Please enter at least one domain.")
                return
            
            self.user_data[user_id]['domains'] = domains
            self.user_states[user_id] = 'processing'
            
            # Start processing
            await self.process_task(user_id, message)
    
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
            await status_msg.edit_text("📥 **Downloading file...**")
            
            archive_path = None
            
            if data['source'] == 'forward':
                # Download from forwarded message
                msg = await self.app.get_messages(message.chat.id, data['message_id'])
                
                if msg.document:
                    archive_path = os.path.join(download_path, msg.document.file_name)
                    
                    # Download with progress
                    await msg.download(
                        file_name=archive_path,
                        progress=self.progress_callback,
                        progress_args=(status_msg, "📥 Downloading...")
                    )
                else:
                    raise Exception("Original message not found or not a document")
            
            else:  # link
                # Download from URL
                url = data['url']
                file_name = url.split('/')[-1].split('?')[0]
                if not file_name or '.' not in file_name:
                    file_name = f"archive_{generate_random_string(8)}.zip"
                
                archive_path = os.path.join(download_path, file_name)
                
                # Download with aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            raise Exception(f"HTTP {resp.status}")
                        
                        total_size = int(resp.headers.get('content-length', 0))
                        downloaded = 0
                        
                        async with aiofiles.open(archive_path, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(1024 * 1024):
                                if task_info.get('cancelled'):
                                    raise Exception("Cancelled by user")
                                
                                await f.write(chunk)
                                downloaded += len(chunk)
                                
                                if total_size:
                                    percent = (downloaded / total_size) * 100
                                    progress = f"[{'=' * int(percent/5)}{' ' * (20 - int(percent/5))}]"
                                    
                                    await status_msg.edit_text(
                                        f"**📥 Downloading...**\n"
                                        f"{progress} {percent:.1f}%\n"
                                        f"📊 {human_readable_size(downloaded)} / {human_readable_size(total_size)}"
                                    )
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            # STEP 2: Extract archives
            await status_msg.edit_text("📦 **Extracting archives...**")
            
            extractor = UltimateArchiveExtractor(data.get('password'))
            task_info['extractor'] = extractor
            
            # Set progress callback
            async def extract_progress(text, percent):
                await self.task_progress_callback(user_id, text, percent)
            
            extractor.set_progress_callback(extract_progress)
            
            extract_dir = await extractor.extract_all_nested(archive_path, extract_path, unique_id)
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            # STEP 3: Filter cookies
            await status_msg.edit_text("🔍 **Filtering cookies...**")
            
            cookie_extractor = UltimateCookieExtractor(data['domains'])
            task_info['cookie_extractor'] = cookie_extractor
            
            # Set progress callback
            async def cookie_progress(text, percent):
                await self.task_progress_callback(user_id, text, percent)
            
            cookie_extractor.set_progress_callback(cookie_progress)
            
            await cookie_extractor.process_all(extract_dir, unique_id)
            
            if task_info.get('cancelled'):
                raise Exception("Cancelled by user")
            
            # STEP 4: Create ZIPs
            if cookie_extractor.total_found > 0:
                await status_msg.edit_text("📦 **Creating ZIP archives...**")
                
                created_zips = cookie_extractor.create_site_zips(extract_dir, result_folder)
                
                # Send files to user
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        caption = f"**{site}**\n"
                        caption += f"📊 {cookie_extractor.site_files[site].__len__()} files | {cookie_extractor.total_found} entries"
                        
                        await message.reply_document(
                            document=zip_path,
                            caption=caption,
                            file_name=f"{site}_cookies.zip"
                        )
                
                # Summary
                summary = f"**✅ Extraction Complete!**\n\n"
                summary += f"📊 **Files processed:** {cookie_extractor.files_processed}\n"
                summary += f"🔍 **Entries found:** {cookie_extractor.total_found}\n"
                summary += f"📦 **ZIP archives:** {len(created_zips)}\n\n"
                
                for site in data['domains']:
                    if site in cookie_extractor.site_files:
                        files_count = len(cookie_extractor.site_files[site])
                        if files_count > 0:
                            summary += f"✓ **{site}:** {files_count} files\n"
                
                await status_msg.edit_text(summary)
                
                # Log to channel
                log_text = f"**Task Completed**\n"
                log_text += f"User: {user_id}\n"
                log_text += f"Domains: {', '.join(data['domains'])}\n"
                log_text += f"Files: {cookie_extractor.files_processed}\n"
                log_text += f"Entries: {cookie_extractor.total_found}"
                await self.send_log(log_text)
            
            else:
                await status_msg.edit_text("❌ No matching cookies found.")
            
        except Exception as e:
            if str(e) == "Cancelled by user":
                # Already handled in cancel
                pass
            else:
                await status_msg.edit_text(f"❌ **Error:** {str(e)}")
                await self.send_log(f"Error for user {user_id}: {str(e)}")
        
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
    
    async def run(self):
        """Run the bot"""
        print(f"Starting Cookie Extractor Bot...")
        print(f"API ID: {API_ID}")
        print(f"Bot Token: {BOT_TOKEN[:10]}...")
        print(f"Log Channel: {LOG_CHANNEL}")
        print(f"Admins: {ADMINS}")
        print(f"Tools: 7z={TOOL_STATUS['7z']}, UnRAR={TOOL_STATUS['unrar']}")
        
        # Register handlers
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.start_command(client, message)
        
        @self.app.on_message(filters.command("help"))
        async def help_handler(client, message):
            await self.help_command(client, message)
        
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
        print("Bot is running!")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        await self.app.stop()

# ==============================================================================
# MAIN
# ==============================================================================
async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await bot.stop()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
