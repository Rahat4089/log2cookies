#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - PyroFork Version
Telegram bot for extracting cookies from nested archives with per-site filtering
"""

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
import psutil
import platform
import signal
import math
import humanize
from datetime import datetime, timedelta
from typing import List, Set, Dict, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict, deque
import traceback
import gc

# PyroFork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified, MediaEmpty
from pyrogram.file_id import FileId
from pyrogram.enums import ParseMode

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

# Try to import rarfile for password detection
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

# Try to import py7zr
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
#                            CONFIGURATION
# ==============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB max file size
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB chunks for download

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Detect system
SYSTEM = platform.system().lower()

# ==============================================================================
#                            TOOL DETECTION
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
#                            TOOL STATUS
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
#                            UTILITY FUNCTIONS
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
    """Format size to human readable"""
    return humanize.naturalsize(size_bytes, binary=True)

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder in one operation"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        gc.collect()
        
        methods = [
            lambda: shutil.rmtree(folder_path, ignore_errors=True),
            lambda: os.system(f'rmdir /s /q "{folder_path}"' if SYSTEM == 'windows' else f'rm -rf "{folder_path}"'),
        ]
        
        for method in methods:
            try:
                method()
                time.sleep(0.5)
                if not os.path.exists(folder_path):
                    return True
            except:
                continue
        
        return not os.path.exists(folder_path)
    except:
        return False

def format_progress_bar(percentage: float, width: int = 10) -> str:
    """Format progress bar"""
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return bar

# ==============================================================================
#                            PASSWORD DETECTION
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
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'Encrypted' in result.stdout or 'Password' in result.stdout:
                    return True
            except:
                pass
        
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower():
                    return True
            except:
                pass
        
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
                return False
        except:
            return True

# ==============================================================================
#                            ARCHIVE EXTRACTION
# ==============================================================================

class UltimateArchiveExtractor:
    """Ultimate speed archive extraction - best tool for each format"""
    
    def __init__(self, password: Optional[str] = None, progress_callback=None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.progress_callback = progress_callback
    
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
            if ext == '.7z':
                if TOOL_STATUS['7z']:
                    return self.extract_7z_with_7z(archive_path, extract_dir)
                elif HAS_PY7ZR:
                    return self.extract_7z_fallback(archive_path, extract_dir)
            
            elif ext == '.rar':
                if TOOL_STATUS['unrar']:
                    return self.extract_rar_with_unrar(archive_path, extract_dir)
                elif HAS_RARFILE:
                    return self.extract_rar_fallback(archive_path, extract_dir)
            
            elif ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, status_msg: Message) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        
        await status_msg.edit_text(
            f"📦 **Extraction Started**\n\n"
            f"Method: 7z: {'✅' if TOOL_STATUS['7z'] else '❌'} | UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}\n"
            f"Level: 0\n"
            f"Archives found: 1\n"
            f"Status: 🔄 Processing..."
        )
        
        with tqdm(total=total_archives, desc="Extracting", unit="archives") as pbar:
            while current_level and not self.stop_extraction:
                next_level = set()
                level_dir = os.path.join(base_dir, f"L{level}")
                os.makedirs(level_dir, exist_ok=True)
                
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
                                pbar.total = total_archives
                            
                            pbar.update(1)
                            
                            if level % 5 == 0:
                                await status_msg.edit_text(
                                    f"📦 **Extracting...**\n\n"
                                    f"Method: 7z: {'✅' if TOOL_STATUS['7z'] else '❌'} | UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}\n"
                                    f"Level: {level}\n"
                                    f"Archives processed: {self.extracted_count}/{total_archives}\n"
                                    f"Status: 🔄 Working..."
                                )
                        except:
                            pbar.update(1)
                
                current_level = next_level
                level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    """Ultimate speed cookie extraction with per-site filtering"""
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = Lock()
        self.stats_lock = Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
    
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
        
        top_dirs = []
        try:
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path):
                    top_dirs.append(item_path)
        except:
            top_dirs = [extract_dir]
        
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
        """Process a single file"""
        if self.stop_processing:
            return
            
        try:
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            site_matches: Dict[str, List[Tuple[int, str]]] = {site: [] for site in self.target_sites}
            
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        
                        with self.seen_lock:
                            if unique_id not in self.global_seen:
                                self.global_seen.add(unique_id)
                                site_matches[site].append((line_num, line_str))
                                with self.stats_lock:
                                    self.total_found += 1
            
            files_saved = 0
            for site, matches in site_matches.items():
                if matches:
                    matches.sort(key=lambda x: x[0])
                    lines_list = [line for _, line in matches]
                    
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    
                    with open(out_path, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                        f.write('\n'.join(lines_list))
                    
                    with self.seen_lock:
                        self.site_files[site][out_path] = unique_name
                    
                    files_saved += 1
            
            with self.stats_lock:
                self.files_processed += 1
                
        except Exception as e:
            pass
    
    async def process_all(self, extract_dir: str, status_msg: Message):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            await status_msg.edit_text("❌ No cookie files found in extracted archives")
            return
        
        await status_msg.edit_text(
            f"🔍 **Filtering Cookies**\n\n"
            f"Files found: {len(cookie_files)}\n"
            f"Target domains: {', '.join(self.target_sites)}\n"
            f"Threads: {MAX_WORKERS}\n"
            f"Status: 🔄 Processing..."
        )
        
        with tqdm(total=len(cookie_files), desc="Filtering", unit="files") as pbar:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = []
                for file_path, orig_name in cookie_files:
                    if self.stop_processing:
                        break
                    future = executor.submit(self.process_file, file_path, orig_name, extract_dir)
                    futures.append(future)
                
                last_update = time.time()
                for i, future in enumerate(as_completed(futures)):
                    if self.stop_processing:
                        executor.shutdown(wait=False)
                        break
                    future.result()
                    pbar.update(1)
                    
                    if time.time() - last_update > 2:
                        await status_msg.edit_text(
                            f"🔍 **Filtering Cookies**\n\n"
                            f"Files found: {len(cookie_files)}\n"
                            f"Processed: {i + 1}/{len(cookie_files)}\n"
                            f"Entries found: {self.total_found}\n"
                            f"Status: 🔄 Working..."
                        )
                        last_update = time.time()
    
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
#                            USER TASK MANAGER
# ==============================================================================

class UserTask:
    """Represents a user's extraction task"""
    
    def __init__(self, user_id: int, username: str, archive_path: str, archive_size: int):
        self.user_id = user_id
        self.username = username
        self.archive_path = archive_path
        self.archive_size = archive_size
        self.start_time = time.time()
        self.status_msg: Optional[Message] = None
        self.extractor: Optional[UltimateArchiveExtractor] = None
        self.cookie_extractor: Optional[UltimateCookieExtractor] = None
        self.extract_folder: Optional[str] = None
        self.results_folder: Optional[str] = None
        self.password: Optional[str] = None
        self.target_sites: List[str] = []
        self.stage = "waiting"  # waiting, extracting, filtering, zipping, done, cancelled, failed
        self.cancelled = False
        self.failed = False
        self.error_msg = ""
        self.progress = 0
        self.total_files = 0
        self.processed_files = 0
        self.entries_found = 0
        
    def get_info(self) -> str:
        """Get task info for display"""
        elapsed = time.time() - self.start_time
        size_str = format_size(self.archive_size)
        
        status_emoji = {
            "waiting": "⏳",
            "extracting": "📦",
            "filtering": "🔍",
            "zipping": "📁",
            "done": "✅",
            "cancelled": "❌",
            "failed": "💥"
        }.get(self.stage, "⏳")
        
        return (
            f"{status_emoji} **User:** @{self.username} (ID: `{self.user_id}`)\n"
            f"**File:** {os.path.basename(self.archive_path)}\n"
            f"**Size:** {size_str}\n"
            f"**Stage:** {self.stage.upper()}\n"
            f"**Progress:** {self.progress}%\n"
            f"**Time:** {format_time(elapsed)}\n"
            f"**Domains:** {', '.join(self.target_sites) if self.target_sites else 'Not set'}\n"
        )

class TaskManager:
    """Manages all user tasks"""
    
    def __init__(self):
        self.tasks: Dict[int, UserTask] = {}
        self.queue = deque()
        self.current_task: Optional[int] = None
        self.lock = Lock()
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.extracted_dir = os.path.join(self.base_dir, 'extracted')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.downloads_dir = os.path.join(self.base_dir, 'downloads')
        
        os.makedirs(self.extracted_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)
    
    def add_task(self, user_id: int, username: str, archive_path: str, archive_size: int) -> bool:
        """Add task to queue"""
        with self.lock:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                if task.stage not in ["done", "cancelled", "failed"]:
                    return False
            
            task = UserTask(user_id, username, archive_path, archive_size)
            self.tasks[user_id] = task
            self.queue.append(user_id)
            return True
    
    def remove_task(self, user_id: int):
        """Remove task"""
        with self.lock:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                if task.extract_folder and os.path.exists(task.extract_folder):
                    delete_entire_folder(task.extract_folder)
                if task.results_folder and os.path.exists(task.results_folder):
                    delete_entire_folder(task.results_folder)
                
                del self.tasks[user_id]
            
            if user_id in self.queue:
                self.queue.remove(user_id)
            
            if self.current_task == user_id:
                self.current_task = None
    
    def cancel_task(self, user_id: int) -> bool:
        """Cancel a task"""
        with self.lock:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                task.cancelled = True
                task.stage = "cancelled"
                
                if task.extractor:
                    task.extractor.stop_extraction = True
                if task.cookie_extractor:
                    task.cookie_extractor.stop_processing = True
                
                return True
            return False
    
    def get_next_task(self) -> Optional[int]:
        """Get next task from queue"""
        with self.lock:
            if self.current_task is None and self.queue:
                self.current_task = self.queue.popleft()
                task = self.tasks.get(self.current_task)
                if task:
                    task.stage = "extracting"
                return self.current_task
            return None
    
    def task_done(self, user_id: int):
        """Mark task as done"""
        with self.lock:
            if self.current_task == user_id:
                self.current_task = None
    
    def get_queue_info(self) -> str:
        """Get queue information"""
        with self.lock:
            if not self.tasks:
                return "📊 **Queue is empty**"
            
            lines = ["📊 **Current Queue**\n"]
            
            # Current task
            if self.current_task and self.current_task in self.tasks:
                lines.append("**▶ CURRENT TASK:**")
                lines.append(self.tasks[self.current_task].get_info())
                lines.append("")
            
            # Waiting tasks
            if self.queue:
                lines.append(f"**⏳ WAITING ({len(self.queue)}):**")
                for i, user_id in enumerate(list(self.queue)[:10]):
                    if user_id in self.tasks:
                        task = self.tasks[user_id]
                        lines.append(f"{i+1}. @{task.username} - {format_size(task.archive_size)}")
                
                if len(self.queue) > 10:
                    lines.append(f"... and {len(self.queue) - 10} more")
            else:
                lines.append("⏳ **No waiting tasks**")
            
            return "\n".join(lines)

# ==============================================================================
#                            DOWNLOAD MANAGER
# ==============================================================================

class DownloadManager:
    """Handles file downloads with progress"""
    
    def __init__(self):
        self.downloads: Dict[int, Dict] = {}
        self.lock = Lock()
    
    async def download_file(self, client: Client, message: Message, file_id: str, file_size: int) -> Tuple[Optional[str], Optional[str]]:
        """Download file with progress"""
        user_id = message.from_user.id
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_str = generate_random_string(8)
        file_name = f"archive_{timestamp}_{random_str}"
        file_path = os.path.join(TASK_MANAGER.downloads_dir, file_name)
        
        with self.lock:
            self.downloads[user_id] = {
                "file_path": file_path,
                "file_size": file_size,
                "downloaded": 0,
                "start_time": time.time(),
                "last_update": time.time(),
                "message": message,
                "cancelled": False
            }
        
        try:
            progress_msg = await message.reply_text(
                f"📥 **Downloading...**\n\n"
                f"Size: {format_size(file_size)}\n"
                f"Progress: 0%\n"
                f"Speed: --\n"
                f"ETA: --"
            )
            
            async def progress(current, total):
                with self.lock:
                    if user_id not in self.downloads:
                        return False
                    
                    dl_info = self.downloads[user_id]
                    if dl_info["cancelled"]:
                        return False
                    
                    dl_info["downloaded"] = current
                    
                    now = time.time()
                    if now - dl_info["last_update"] > 2:
                        elapsed = now - dl_info["start_time"]
                        speed = current / elapsed if elapsed > 0 else 0
                        
                        if speed > 0:
                            eta = (total - current) / speed
                            eta_str = format_time(eta)
                        else:
                            eta_str = "--"
                        
                        percentage = (current / total) * 100
                        bar = format_progress_bar(percentage)
                        
                        try:
                            asyncio.create_task(
                                progress_msg.edit_text(
                                    f"📥 **Downloading...**\n\n"
                                    f"File: {os.path.basename(file_path)}\n"
                                    f"Size: {format_size(total)}\n"
                                    f"Downloaded: {format_size(current)}\n"
                                    f"Progress: {percentage:.1f}%\n"
                                    f"{bar}\n"
                                    f"Speed: {format_size(speed)}/s\n"
                                    f"ETA: {eta_str}"
                                )
                            )
                        except:
                            pass
                        
                        dl_info["last_update"] = now
                
                return True
            
            # Download the file
            file_path = await client.download_media(
                message,
                file_name=file_path,
                progress=progress,
                block=True
            )
            
            if not file_path:
                raise Exception("Download failed")
            
            await progress_msg.delete()
            return file_path, file_name
            
        except Exception as e:
            await progress_msg.delete()
            return None, None
        finally:
            with self.lock:
                if user_id in self.downloads:
                    del self.downloads[user_id]
    
    def cancel_download(self, user_id: int) -> bool:
        """Cancel ongoing download"""
        with self.lock:
            if user_id in self.downloads:
                self.downloads[user_id]["cancelled"] = True
                return True
            return False

# ==============================================================================
#                            STATISTICS
# ==============================================================================

class StatsCollector:
    """Collect system statistics"""
    
    @staticmethod
    def get_system_stats() -> str:
        """Get system statistics"""
        try:
            # Disk
            disk = psutil.disk_usage('/')
            disk_total = disk.total
            disk_used = disk.used
            disk_free = disk.free
            disk_percent = disk.used / disk.total * 100
            
            # Memory
            memory = psutil.virtual_memory()
            mem_total = memory.total
            mem_used = memory.used
            mem_percent = memory.percent
            
            # CPU
            cpu_count = psutil.cpu_count()
            cpu_percent = psutil.cpu_percent(interval=0.5)
            
            # Process
            process = psutil.Process()
            cpu_proc = process.cpu_percent(interval=0.5)
            mem_proc_rss = process.memory_info().rss
            mem_proc_vms = process.memory_info().vms
            
            # Network
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            total_io = bytes_sent + bytes_recv
            
            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            
            # System info
            os_name = platform.system()
            os_version = platform.release()
            python_version = platform.python_version()
            
            # Bot uptime
            bot_uptime = datetime.now() - bot_start_time
            bot_uptime_str = str(bot_uptime).split('.')[0]
            
            stats = f"""
🖥️ **System Statistics Dashboard**

💾 **Disk Storage**
├ Total:  {format_size(disk_total)}
├ Used:   {format_size(disk_used)} ({disk_percent:.1f}%)
└ Free:   {format_size(disk_free)}

🧠 **RAM (Memory)**
├ Total:  {format_size(mem_total)}
├ Used:   {format_size(mem_used)} ({mem_percent:.1f}%)
└ Free:   {format_size(mem_free if 'mem_free' in locals() else mem_total - mem_used)}

⚡ **CPU**
├ Cores:  {cpu_count}
└ Usage:  {cpu_percent:.1f}%

🔌 **Bot Process**
├ CPU:   {cpu_proc:.1f}%
├ RAM (RSS):  {format_size(mem_proc_rss)}
└ RAM (VMS):  {format_size(mem_proc_vms)}

🌐 **Network**
├ Upload Speed:   -- (requires sampling)
├ Download Speed: -- (requires sampling)
└ Total I/O:   {format_size(total_io)}

📟 **System Info**
├ OS:  {os_name}
├ OS Version:  {os_version}
├ Python:  {python_version}
└ Uptime:  {uptime_str}

🤖 **Bot Info**
├ Uptime:  {bot_uptime_str}
├ Active Tasks: {len(TASK_MANAGER.tasks)}
├ Queue Length: {len(TASK_MANAGER.queue)}
└ Current Task: {'Yes' if TASK_MANAGER.current_task else 'No'}

⏱️ **Performance**
└ Current Ping:  (check via /ping)

👑 **Owner:** @still_alivenow
"""
            return stats
        except Exception as e:
            return f"❌ Error getting stats: {str(e)}"

# ==============================================================================
#                            BOT INITIALIZATION
# ==============================================================================

bot_start_time = datetime.now()
TASK_MANAGER = TaskManager()
DOWNLOAD_MANAGER = DownloadManager()

app = Client(
    "rute_cookie_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==============================================================================
#                            HELPER FUNCTIONS
#==============================================================================

async def safe_edit(msg: Message, text: str, **kwargs):
    """Safely edit message with error handling"""
    try:
        await msg.edit_text(text, **kwargs)
    except (MessageNotModified, FloodWait) as e:
        if isinstance(e, FloodWait):
            await asyncio.sleep(e.value)
            try:
                await msg.edit_text(text, **kwargs)
            except:
                pass
    except:
        pass

async def forward_to_logs(client: Client, message: Message, file_path: str = None):
    """Forward message and file to logs channel"""
    if not SEND_LOGS:
        return
    
    try:
        if file_path and os.path.exists(file_path):
            caption = (
                f"#EXTRACTED\n"
                f"User: @{message.from_user.username or 'NoUsername'} (ID: `{message.from_user.id}`)\n"
                f"File: {os.path.basename(file_path)}\n"
                f"Size: {format_size(os.path.getsize(file_path))}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await client.send_document(
                LOG_CHANNEL,
                file_path,
                caption=caption
            )
        else:
            await client.forward_messages(
                LOG_CHANNEL,
                message.chat.id,
                [message.id]
            )
    except Exception as e:
        print(f"Log forwarding error: {e}")

# ==============================================================================
#                            COMMAND HANDLERS
# ==============================================================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Start command handler"""
    await message.reply_text(
        "👋 **Welcome to RUTE Cookie Extractor Bot!**\n\n"
        "I can extract cookies from deeply nested archives with lightning speed.\n\n"
        "**How to use:**\n"
        "1. Send me any archive file (.zip, .rar, .7z, etc.)\n"
        "2. I'll download it (max 4GB)\n"
        "3. Tell me which domains to filter (e.g., google, facebook)\n"
        "4. If password protected, provide the password\n"
        "5. I'll extract everything and give you filtered cookie files\n\n"
        "**Commands:**\n"
        "/start - Show this message\n"
        "/stats - System statistics\n"
        "/queue - View current queue\n"
        "/cancel - Cancel your current task\n"
        "/ping - Check bot latency\n\n"
        "**Owner:** @still_alivenow"
    )

@app.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    """Ping command handler"""
    start = time.time()
    msg = await message.reply_text("🏓 Pong!")
    end = time.time()
    ping = (end - start) * 1000
    await msg.edit_text(f"🏓 **Pong!**\n`{ping:.1f}ms`")

@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    """Stats command handler"""
    msg = await message.reply_text("📊 Gathering statistics...")
    stats = StatsCollector.get_system_stats()
    await msg.edit_text(stats)

@app.on_message(filters.command("queue"))
async def queue_command(client: Client, message: Message):
    """Queue command handler"""
    queue_info = TASK_MANAGER.get_queue_info()
    
    keyboard = []
    if TASK_MANAGER.current_task:
        task = TASK_MANAGER.tasks.get(TASK_MANAGER.current_task)
        if task:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Cancel Current ({task.username})",
                    callback_data=f"cancel_{task.user_id}"
                )
            ])
    
    for user_id in list(TASK_MANAGER.queue)[:5]:
        if user_id in TASK_MANAGER.tasks:
            task = TASK_MANAGER.tasks[user_id]
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Cancel @{task.username}",
                    callback_data=f"cancel_{user_id}"
                )
            ])
    
    await message.reply_text(
        queue_info,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Cancel command handler"""
    user_id = message.from_user.id
    
    # Check if user has download
    if DOWNLOAD_MANAGER.cancel_download(user_id):
        await message.reply_text("✅ Download cancelled")
        return
    
    # Check if user has task
    if TASK_MANAGER.cancel_task(user_id):
        await message.reply_text("✅ Task cancelled")
    else:
        await message.reply_text("❌ No active task found")

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback queries"""
    data = callback_query.data
    
    if data.startswith("cancel_"):
        user_id = int(data.split("_")[1])
        
        # Check if admin or own task
        if callback_query.from_user.id not in ADMINS and callback_query.from_user.id != user_id:
            await callback_query.answer("❌ You can only cancel your own tasks", show_alert=True)
            return
        
        if TASK_MANAGER.cancel_task(user_id):
            await callback_query.answer("✅ Task cancelled", show_alert=True)
        else:
            await callback_query.answer("❌ Task not found", show_alert=True)
        
        # Update queue message
        await callback_query.message.edit_text(
            TASK_MANAGER.get_queue_info()
        )

@app.on_message(filters.document)
async def handle_document(client: Client, message: Message):
    """Handle document uploads"""
    user_id = message.from_user.id
    document = message.document
    
    # Check file size
    if document.file_size > MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ File too large! Maximum size: {format_size(MAX_FILE_SIZE)}"
        )
        return
    
    # Check if user already has task
    if user_id in TASK_MANAGER.tasks:
        task = TASK_MANAGER.tasks[user_id]
        if task.stage not in ["done", "cancelled", "failed"]:
            await message.reply_text(
                "❌ You already have an active task!\n"
                "Use /cancel to cancel it first."
            )
            return
    
    # Forward to logs
    await forward_to_logs(client, message)
    
    # Download file
    status_msg = await message.reply_text("📥 Starting download...")
    
    file_path, file_name = await DOWNLOAD_MANAGER.download_file(
        client, message, document.file_id, document.file_size
    )
    
    if not file_path:
        await status_msg.edit_text("❌ Download failed or cancelled")
        return
    
    # Add to queue
    username = message.from_user.username or f"User{user_id}"
    if not TASK_MANAGER.add_task(user_id, username, file_path, document.file_size):
        await status_msg.edit_text("❌ Failed to add task to queue")
        os.unlink(file_path)
        return
    
    await status_msg.edit_text(
        f"✅ **File downloaded!**\n\n"
        f"File: {file_name}\n"
        f"Size: {format_size(document.file_size)}\n"
        f"Position: {len(TASK_MANAGER.queue)}\n\n"
        f"Now, please send me the domains to filter (comma-separated)\n"
        f"Example: `google, facebook, twitter`"
    )
    
    # Start processing if no current task
    asyncio.create_task(process_queue())

async def process_queue():
    """Process tasks from queue"""
    while True:
        user_id = TASK_MANAGER.get_next_task()
        if not user_id:
            await asyncio.sleep(1)
            continue
        
        task = TASK_MANAGER.tasks.get(user_id)
        if not task:
            TASK_MANAGER.task_done(user_id)
            continue
        
        try:
            await process_user_task(user_id)
        except Exception as e:
            print(f"Error processing task for {user_id}: {e}")
            traceback.print_exc()
            
            if task and task.status_msg:
                await task.status_msg.edit_text(
                    f"❌ **Error:** {str(e)[:200]}"
                )
            
            if task:
                task.stage = "failed"
                task.failed = True
                task.error_msg = str(e)
        
        TASK_MANAGER.task_done(user_id)

async def process_user_task(user_id: int):
    """Process a single user task"""
    task = TASK_MANAGER.tasks[user_id]
    
    # Get domains
    def check_domains(client, message):
        return message.from_user.id == user_id and message.text and not message.text.startswith('/')
    
    try:
        # Ask for domains
        domains_msg = await task.status_msg.reply_text(
            f"@{task.username}, please send the domains to filter (comma-separated):\n"
            f"Example: `google, facebook, twitter`\n\n"
            f"Use /cancel to cancel this operation."
        )
        
        # Wait for response
        domains_response = await app.listen(chat_id=user_id, filters=check_domains, timeout=300)
        
        if not domains_response or domains_response.text.startswith('/cancel'):
            await domains_msg.edit_text("❌ Operation cancelled")
            TASK_MANAGER.remove_task(user_id)
            return
        
        domains_text = domains_response.text.strip()
        task.target_sites = [s.strip().lower() for s in domains_text.split(',') if s.strip()]
        
        if not task.target_sites:
            await domains_msg.edit_text("❌ No valid domains provided")
            TASK_MANAGER.remove_task(user_id)
            return
        
        await domains_msg.delete()
        
        # Check password
        is_protected = False
        ext = os.path.splitext(task.archive_path)[1].lower()
        
        if ext == '.rar':
            is_protected = PasswordDetector.check_rar_protected(task.archive_path)
        elif ext == '.7z':
            is_protected = PasswordDetector.check_7z_protected(task.archive_path)
        elif ext == '.zip':
            is_protected = PasswordDetector.check_zip_protected(task.archive_path)
        
        if is_protected:
            pass_msg = await task.status_msg.reply_text(
                f"🔒 This archive is password protected.\n"
                f"Please send the password (or send /skip if no password):"
            )
            
            pass_response = await app.listen(chat_id=user_id, filters=check_domains, timeout=120)
            
            if pass_response and not pass_response.text.startswith('/skip'):
                task.password = pass_response.text.strip()
            
            await pass_msg.delete()
        
        # Create folders
        unique_id = datetime.now().strftime('%H%M%S')
        task.extract_folder = os.path.join(TASK_MANAGER.extracted_dir, f"x{unique_id}_{user_id}")
        task.results_folder = os.path.join(TASK_MANAGER.results_dir, datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(task.extract_folder, exist_ok=True)
        os.makedirs(task.results_folder, exist_ok=True)
        
        # Update status
        await task.status_msg.edit_text(
            f"🚀 **Processing started**\n\n"
            f"User: @{task.username}\n"
            f"File: {os.path.basename(task.archive_path)}\n"
            f"Size: {format_size(task.archive_size)}\n"
            f"Domains: {', '.join(task.target_sites)}\n"
            f"Password: {'Yes' if task.password else 'No'}\n"
            f"Status: 📦 Extracting..."
        )
        
        # Extract archives
        task.stage = "extracting"
        task.extractor = UltimateArchiveExtractor(task.password)
        await task.extractor.extract_all_nested(
            task.archive_path,
            task.extract_folder,
            task.status_msg
        )
        
        if task.cancelled:
            await task.status_msg.edit_text("❌ Task cancelled")
            TASK_MANAGER.remove_task(user_id)
            return
        
        # Filter cookies
        task.stage = "filtering"
        task.cookie_extractor = UltimateCookieExtractor(task.target_sites)
        await task.cookie_extractor.process_all(task.extract_folder, task.status_msg)
        
        if task.cancelled:
            await task.status_msg.edit_text("❌ Task cancelled")
            TASK_MANAGER.remove_task(user_id)
            return
        
        # Create ZIPs
        if task.cookie_extractor.total_found > 0:
            task.stage = "zipping"
            await task.status_msg.edit_text(
                f"📦 **Creating ZIP archives...**\n\n"
                f"Entries found: {task.cookie_extractor.total_found}\n"
                f"Files processed: {task.cookie_extractor.files_processed}\n"
                f"Status: 🔄 Compressing..."
            )
            
            created_zips = task.cookie_extractor.create_site_zips(
                task.extract_folder,
                task.results_folder
            )
            
            # Send results
            task.stage = "done"
            elapsed = time.time() - task.start_time
            
            await task.status_msg.edit_text(
                f"✅ **Extraction Complete!**\n\n"
                f"Time: {format_time(elapsed)}\n"
                f"Files processed: {task.cookie_extractor.files_processed}\n"
                f"Entries found: {task.cookie_extractor.total_found}\n"
                f"ZIP archives: {len(created_zips)}\n\n"
                f"Sending files..."
            )
            
            # Send each ZIP
            for site, zip_path in created_zips.items():
                await client.send_document(
                    user_id,
                    zip_path,
                    caption=f"✅ Cookies for {site}\nFound: {task.cookie_extractor.total_found} entries"
                )
                
                # Forward to logs
                await forward_to_logs(client, await client.get_messages(user_id, 1), zip_path)
            
            # Cleanup
            TASK_MANAGER.remove_task(user_id)
            
        else:
            await task.status_msg.edit_text(
                f"❌ No matching cookies found for domains: {', '.join(task.target_sites)}"
            )
            TASK_MANAGER.remove_task(user_id)
        
    except asyncio.TimeoutError:
        await task.status_msg.edit_text(
            "❌ Operation timed out. Please start again."
        )
        TASK_MANAGER.remove_task(user_id)
    except Exception as e:
        await task.status_msg.edit_text(
            f"❌ **Error:** {str(e)[:200]}"
        )
        TASK_MANAGER.remove_task(user_id)

# ==============================================================================
#                            MAIN
# ==============================================================================

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════════════════╗
║     🚀 RUTE COOKIE EXTRACTOR BOT - PyroFork Version     ║
╠══════════════════════════════════════════════════════════╣
║  Tools: 7z: {TOOL_STATUS['7z']} | UnRAR: {TOOL_STATUS['unrar']}                     ║
║  Max Workers: {MAX_WORKERS} | Max File: 4GB                ║
║  Log Channel: {LOG_CHANNEL}                               ║
║  Owner: @still_alivenow                                   ║
╚══════════════════════════════════════════════════════════╝
    """)
    
    app.run()
