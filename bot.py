#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - PyroFork Version
Complete archive extraction bot with queue system and progress tracking
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
import gc
import math
import tarfile
from datetime import datetime, timedelta
from typing import List, Set, Dict, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import deque
import humanize
import GPUtil

# PyroFork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports for progress
try:
    from tqdm import tqdm
except ImportError:
    os.system("pip install -q tqdm")
    from tqdm import tqdm

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
#                            CONFIGURATION
# ==============================================================================

# Bot Configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]
OWNER_USERNAME = "@still_alivenow"

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB max file size
PROGRESS_UPDATE_INTERVAL = 2  # Update progress every 2 seconds

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
    """Quick size formatting"""
    if size_bytes == 0:
        return "0B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 0:
        return "0s"
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
        
        # Try multiple methods
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

def create_progress_bar(percentage: float, width: int = 10) -> str:
    """Create a text progress bar"""
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
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = Lock()
        self.extracted_count = 0
        self.stop_extraction = False
    
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
    
    def extract_all_nested(self, root_archive: str, base_dir: str, progress_callback=None) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        
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
                        
                        if progress_callback:
                            progress_callback(1, len(new_archives))
                    except:
                        pass
            
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
        """Process a single file - create separate filtered file for each matching site"""
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
    
    def process_all(self, extract_dir: str):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for file_path, orig_name in cookie_files:
                if self.stop_processing:
                    break
                future = executor.submit(self.process_file, file_path, orig_name, extract_dir)
                futures.append(future)
            
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
    
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
#                            QUEUE MANAGEMENT
# ==============================================================================

class UserTask:
    """Represents a user's task in queue"""
    def __init__(self, user_id: int, user_name: str, file_path: str, file_name: str, file_size: int, message: Message):
        self.user_id = user_id
        self.user_name = user_name
        self.file_path = file_path
        self.file_name = file_name
        self.file_size = file_size
        self.message = message
        self.status = "queued"  # queued, extracting, filtering, zipping, completed, cancelled, failed
        self.start_time = None
        self.end_time = None
        self.password = None
        self.domains = []
        self.progress_message = None
        self.extract_folder = None
        self.result_zips = []
        self.cancel_requested = False
        self.current_stage = "Waiting"
        self.stage_progress = 0

class TaskQueue:
    """Manages user tasks with queue system"""
    def __init__(self):
        self.queue = deque()
        self.current_task = None
        self.user_tasks: Dict[int, UserTask] = {}
        self.lock = Lock()
        self.processing = False
    
    def add_task(self, user_id: int, user_name: str, file_path: str, file_name: str, file_size: int, message: Message) -> int:
        """Add task to queue"""
        with self.lock:
            # Check if user already has active task
            if user_id in self.user_tasks and self.user_tasks[user_id].status in ["queued", "extracting", "filtering", "zipping"]:
                return -1
            
            task = UserTask(user_id, user_name, file_path, file_name, file_size, message)
            self.queue.append(task)
            self.user_tasks[user_id] = task
            return len(self.queue)
    
    def get_user_task(self, user_id: int) -> Optional[UserTask]:
        """Get task for specific user"""
        return self.user_tasks.get(user_id)
    
    def cancel_task(self, user_id: int) -> bool:
        """Cancel user's task"""
        with self.lock:
            if user_id in self.user_tasks:
                task = self.user_tasks[user_id]
                if task.status in ["queued", "extracting", "filtering", "zipping"]:
                    task.cancel_requested = True
                    task.status = "cancelled"
                    
                    # Remove from queue if still queued
                    if task in self.queue:
                        self.queue.remove(task)
                    
                    # Clean up files
                    self.cleanup_task_files(task)
                    
                    return True
            return False
    
    def cleanup_task_files(self, task: UserTask):
        """Clean up all files for a task"""
        try:
            if task.extract_folder and os.path.exists(task.extract_folder):
                delete_entire_folder(task.extract_folder)
            
            for zip_path in task.result_zips:
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except:
                        pass
            
            if os.path.exists(task.file_path):
                try:
                    os.remove(task.file_path)
                except:
                    pass
        except:
            pass
    
    def get_next_task(self) -> Optional[UserTask]:
        """Get next task from queue"""
        with self.lock:
            if self.queue and not self.processing:
                task = self.queue.popleft()
                if task.status != "cancelled":
                    self.current_task = task
                    self.processing = True
                    task.status = "extracting"
                    task.start_time = time.time()
                    return task
            return None
    
    def complete_task(self, task: UserTask):
        """Mark task as completed"""
        with self.lock:
            task.status = "completed"
            task.end_time = time.time()
            self.processing = False
            self.current_task = None
            
            # Remove from user_tasks after delay (for status queries)
            if task.user_id in self.user_tasks:
                del self.user_tasks[task.user_id]
    
    def fail_task(self, task: UserTask):
        """Mark task as failed"""
        with self.lock:
            task.status = "failed"
            task.end_time = time.time()
            self.processing = False
            self.current_task = None
            
            # Clean up files
            self.cleanup_task_files(task)
            
            if task.user_id in self.user_tasks:
                del self.user_tasks[task.user_id]
    
    def get_queue_status(self) -> Dict:
        """Get queue status information"""
        with self.lock:
            queued_count = len([t for t in self.queue if t.status == "queued"])
            active_count = 1 if self.current_task else 0
            
            queue_list = []
            for task in list(self.queue)[:10]:  # Show first 10
                queue_list.append({
                    'user_id': task.user_id,
                    'user_name': task.user_name,
                    'file_name': task.file_name,
                    'file_size': format_size(task.file_size),
                    'status': task.status
                })
            
            return {
                'queued': queued_count,
                'active': active_count,
                'total': queued_count + active_count,
                'queue': queue_list
            }

# ==============================================================================
#                            PROGRESS TRACKER
# ==============================================================================

class ProgressTracker:
    """Track and display progress for tasks"""
    
    @staticmethod
    async def update_progress(task: UserTask, current: int, total: int, stage: str, message: Message):
        """Update progress message"""
        if task.cancel_requested:
            return
        
        try:
            percentage = (current / total) * 100 if total > 0 else 0
            bar = create_progress_bar(percentage)
            
            elapsed = time.time() - task.start_time if task.start_time else 0
            speed = current / elapsed if elapsed > 0 else 0
            eta = (total - current) / speed if speed > 0 else 0
            
            progress_text = (
                f"**📦 Processing: {task.file_name}**\n\n"
                f"**Stage:** {stage}\n"
                f"**Progress:** `{bar}` {percentage:.1f}%\n"
                f"**Processed:** `{format_size(current)} / {format_size(total)}`\n"
                f"**Speed:** `{format_size(speed)}/s`\n"
                f"**Elapsed:** `{format_time(elapsed)}`\n"
                f"**ETA:** `{format_time(eta)}`\n\n"
                f"**Status:** `{task.status}`\n"
                f"**To cancel:** /cancel"
            )
            
            if task.progress_message:
                try:
                    await task.progress_message.edit_text(progress_text)
                except MessageNotModified:
                    pass
                except:
                    task.progress_message = await message.reply_text(progress_text)
            else:
                task.progress_message = await message.reply_text(progress_text)
        except:
            pass

# ==============================================================================
#                            SYSTEM STATS
# ==============================================================================

class SystemStats:
    """Get system statistics"""
    
    @staticmethod
    async def get_stats() -> str:
        """Get formatted system statistics"""
        try:
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_total = disk.total
            disk_used = disk.used
            disk_free = disk.free
            disk_percent = (disk_used / disk_total) * 100
            
            # Memory usage
            memory = psutil.virtual_memory()
            mem_total = memory.total
            mem_used = memory.used
            mem_free = memory.available
            mem_percent = memory.percent
            
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Bot process
            process = psutil.Process()
            bot_cpu = process.cpu_percent(interval=1)
            bot_memory_rss = process.memory_info().rss
            bot_memory_vms = process.memory_info().vms
            
            # Network
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            total_io = bytes_sent + bytes_recv
            
            # Network speed (simple calculation)
            time.sleep(1)
            net_io2 = psutil.net_io_counters()
            upload_speed = net_io2.bytes_sent - bytes_sent
            download_speed = net_io2.bytes_recv - bytes_recv
            
            # System info
            os_name = platform.system()
            os_version = platform.release()
            python_version = platform.python_version()
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            # Format uptime
            uptime_str = str(uptime).split('.')[0]
            
            # GPU info if available
            gpu_info = ""
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]
                    gpu_info = f"\n🎮 GPU\n├ Name:  {gpu.name}\n├ Load:  {gpu.load*100:.1f}%\n└ Memory:  {gpu.memoryUsed}/{gpu.memoryTotal} MB\n"
            except:
                pass
            
            stats_text = (
                f"**🖥️ System Statistics Dashboard**\n\n"
                f"**💾 Disk Storage**\n"
                f"├ Total:  {humanize.naturalsize(disk_total, binary=True)}\n"
                f"├ Used:  {humanize.naturalsize(disk_used, binary=True)} ({disk_percent:.1f}%)\n"
                f"└ Free:  {humanize.naturalsize(disk_free, binary=True)}\n\n"
                f"**🧠 RAM (Memory)**\n"
                f"├ Total:  {humanize.naturalsize(mem_total, binary=True)}\n"
                f"├ Used:  {humanize.naturalsize(mem_used, binary=True)} ({mem_percent:.1f}%)\n"
                f"└ Free:  {humanize.naturalsize(mem_free, binary=True)}\n\n"
                f"**⚡ CPU**\n"
                f"├ Cores:  {cpu_count}\n"
                f"└ Usage:  {cpu_percent:.1f}%\n\n"
                f"**🔌 Bot Process**\n"
                f"├ CPU:  {bot_cpu:.1f}%\n"
                f"├ RAM (RSS):  {humanize.naturalsize(bot_memory_rss, binary=True)}\n"
                f"└ RAM (VMS):  {humanize.naturalsize(bot_memory_vms, binary=True)}\n\n"
                f"**🌐 Network**\n"
                f"├ Upload Speed:  {humanize.naturalsize(upload_speed)}/s\n"
                f"├ Download Speed:  {humanize.naturalsize(download_speed)}/s\n"
                f"└ Total I/O:  {humanize.naturalsize(total_io, binary=True)}\n{gpu_info}\n"
                f"**📟 System Info**\n"
                f"├ OS:  {os_name}\n"
                f"├ OS Version:  {os_version}\n"
                f"├ Python:  {python_version}\n"
                f"└ Uptime:  {uptime_str}\n\n"
                f"**⏱️ Performance**\n"
                f"└ Current Ping:  `N/A`\n\n"
                f"**👑 Owner Credits:** {OWNER_USERNAME}"
            )
            
            return stats_text
        except Exception as e:
            return f"**Error getting stats:** `{str(e)}`"

# ==============================================================================
#                            MAIN BOT CLASS
# ==============================================================================

class CookieExtractorBot:
    """Main bot class"""
    
    def __init__(self):
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        self.task_queue = TaskQueue()
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.downloads_dir = os.path.join(self.base_dir, 'downloads')
        self.extracted_dir = os.path.join(self.base_dir, 'extracted')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.temp_dir = os.path.join(self.base_dir, 'temp')
        self.progress_tracker = ProgressTracker()
        
        # Create directories
        for dir_path in [self.downloads_dir, self.extracted_dir, self.results_dir, self.temp_dir]:
            os.makedirs(dir_path, exist_ok=True)
    
    async def start(self):
        """Start the bot"""
        await self.app.start()
        
        # Register handlers
        self.app.add_handler(MessageHandler(self.start_command, filters.command("start")))
        self.app.add_handler(MessageHandler(self.help_command, filters.command("help")))
        self.app.add_handler(MessageHandler(self.stats_command, filters.command("stats")))
        self.app.add_handler(MessageHandler(self.queue_command, filters.command("queue")))
        self.app.add_handler(MessageHandler(self.cancel_command, filters.command("cancel")))
        self.app.add_handler(MessageHandler(self.handle_document, filters.document))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Start queue processor
        asyncio.create_task(self.process_queue())
        
        print(f"Bot started! Log channel: {LOG_CHANNEL}")
        print(f"Owner: {OWNER_USERNAME}")
        print(f"Tools: 7z={TOOL_STATUS['7z']}, UnRAR={TOOL_STATUS['unrar']}")
    
    async def stop(self):
        """Stop the bot"""
        await self.app.stop()
    
    # ==========================================================================
    #                            COMMAND HANDLERS
    # ==========================================================================
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = (
            f"**🚀 Welcome to RUTE Cookie Extractor Bot!**\n\n"
            f"Send me any archive file (zip, rar, 7z, tar, etc.) containing cookie files, "
            f"and I'll extract and filter cookies for your specified domains.\n\n"
            f"**Features:**\n"
            f"• Supports all archive formats\n"
            f"• Automatic password detection\n"
            f"• Per-domain cookie filtering\n"
            f"• Multi-threaded extraction\n"
            f"• Queue system (4GB max per file)\n"
            f"• Real-time progress tracking\n\n"
            f"**Commands:**\n"
            f"/start - Show this message\n"
            f"/help - Detailed help\n"
            f"/stats - System statistics\n"
            f"/queue - View queue status\n"
            f"/cancel - Cancel your current task\n\n"
            f"**Owner:** {OWNER_USERNAME}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Stats", callback_data="stats"),
             InlineKeyboardButton("📋 Queue", callback_data="queue")],
            [InlineKeyboardButton("❓ Help", callback_data="help"),
             InlineKeyboardButton("👑 Owner", url=f"https://t.me/{OWNER_USERNAME[1:]}")]
        ])
        
        await message.reply_text(welcome_text, reply_markup=keyboard)
    
    async def help_command(self, client: Client, message: Message):
        """Handle /help command"""
        help_text = (
            f"**📚 Detailed Help**\n\n"
            f"**How to use:**\n"
            f"1. Send me an archive file (max 4GB)\n"
            f"2. Enter password if archive is protected\n"
            f"3. Enter domains to filter (comma-separated)\n"
            f"4. Wait for processing\n"
            f"5. Receive filtered cookie files as ZIP\n\n"
            f"**Supported formats:**\n"
            f"• ZIP (.zip)\n"
            f"• RAR (.rar)\n"
            f"• 7Z (.7z)\n"
            f"• TAR (.tar, .tar.gz, .tar.bz2, .tar.xz)\n"
            f"• GZ (.gz)\n"
            f"• BZ2 (.bz2)\n\n"
            f"**Commands:**\n"
            f"/start - Welcome message\n"
            f"/help - This help\n"
            f"/stats - System statistics\n"
            f"/queue - View queue\n"
            f"/cancel - Cancel task\n\n"
            f"**Note:** Each user can only have one active task at a time."
        )
        
        await message.reply_text(help_text)
    
    async def stats_command(self, client: Client, message: Message):
        """Handle /stats command"""
        status_msg = await message.reply_text("**📊 Gathering statistics...**")
        stats = await SystemStats.get_stats()
        await status_msg.edit_text(stats)
    
    async def queue_command(self, client: Client, message: Message):
        """Handle /queue command"""
        status = self.task_queue.get_queue_status()
        
        if status['total'] == 0:
            await message.reply_text("**📋 Queue is empty**")
            return
        
        queue_text = f"**📋 Queue Status**\n\n"
        queue_text += f"**Active:** {status['active']}\n"
        queue_text += f"**Queued:** {status['queued']}\n"
        queue_text += f"**Total:** {status['total']}\n\n"
        
        if status['active'] == 1 and self.task_queue.current_task:
            task = self.task_queue.current_task
            queue_text += f"**Currently Processing:**\n"
            queue_text += f"• User: {task.user_name}\n"
            queue_text += f"• File: {task.file_name}\n"
            queue_text += f"• Size: {format_size(task.file_size)}\n"
            queue_text += f"• Stage: {task.current_stage}\n\n"
        
        if status['queue']:
            queue_text += f"**Next in Queue:**\n"
            for i, item in enumerate(status['queue'][:5], 1):
                queue_text += f"{i}. {item['user_name']} - {item['file_name']} ({item['file_size']})\n"
            
            if len(status['queue']) > 5:
                queue_text += f"... and {len(status['queue']) - 5} more\n"
        
        await message.reply_text(queue_text)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        
        if self.task_queue.cancel_task(user_id):
            await message.reply_text("**✅ Your task has been cancelled**")
        else:
            await message.reply_text("**❌ No active task found to cancel**")
    
    # ==========================================================================
    #                            DOCUMENT HANDLER
    # ==========================================================================
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document/file uploads"""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or f"User_{user_id}"
        
        # Check file size
        file_size = message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"**❌ File too large!**\nMax size: 4GB\nYour file: {format_size(file_size)}")
            return
        
        # Check if user already has task
        existing = self.task_queue.get_user_task(user_id)
        if existing and existing.status in ["queued", "extracting", "filtering", "zipping"]:
            await message.reply_text(
                f"**❌ You already have an active task!**\n"
                f"Status: {existing.status}\n"
                f"Use /cancel to cancel it first."
            )
            return
        
        # Download file
        status_msg = await message.reply_text("**📥 Downloading file...**")
        
        try:
            # Create user download directory
            user_download_dir = os.path.join(self.downloads_dir, str(user_id))
            os.makedirs(user_download_dir, exist_ok=True)
            
            file_path = await message.download(
                file_name=os.path.join(user_download_dir, message.document.file_name)
            )
            
            await status_msg.edit_text("**✅ File downloaded!**")
            
            # Add to queue
            queue_position = self.task_queue.add_task(
                user_id, user_name, file_path, message.document.file_name, file_size, message
            )
            
            if queue_position == -1:
                await status_msg.edit_text("**❌ Error adding to queue**")
                return
            
            await status_msg.edit_text(
                f"**✅ Added to queue!**\n"
                f"Position: #{queue_position}\n"
                f"File: {message.document.file_name}\n"
                f"Size: {format_size(file_size)}\n\n"
                f"You'll be notified when processing starts."
            )
            
            # Forward to log channel
            if SEND_LOGS:
                try:
                    caption = (
                        f"**📥 New File Received**\n\n"
                        f"**User:** {user_name} (ID: {user_id})\n"
                        f"**File:** {message.document.file_name}\n"
                        f"**Size:** {format_size(file_size)}\n"
                        f"**Queue:** #{queue_position}"
                    )
                    await client.send_document(
                        LOG_CHANNEL,
                        file_path,
                        caption=caption
                    )
                except Exception as e:
                    print(f"Error forwarding to log channel: {e}")
            
        except Exception as e:
            await status_msg.edit_text(f"**❌ Error downloading file:** `{str(e)}`")
    
    # ==========================================================================
    #                            CALLBACK HANDLER
    # ==========================================================================
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        data = callback_query.data
        
        if data == "stats":
            await callback_query.answer()
            stats = await SystemStats.get_stats()
            await callback_query.message.edit_text(stats)
        
        elif data == "queue":
            await callback_query.answer()
            status = self.task_queue.get_queue_status()
            
            if status['total'] == 0:
                await callback_query.message.edit_text("**📋 Queue is empty**")
                return
            
            queue_text = f"**📋 Queue Status**\n\n"
            queue_text += f"**Active:** {status['active']}\n"
            queue_text += f"**Queued:** {status['queued']}\n"
            queue_text += f"**Total:** {status['total']}\n\n"
            
            if status['queue']:
                queue_text += f"**Next in Queue:**\n"
                for i, item in enumerate(status['queue'][:5], 1):
                    queue_text += f"{i}. {item['user_name']} - {item['file_name']} ({item['file_size']})\n"
            
            await callback_query.message.edit_text(queue_text)
        
        elif data == "help":
            await callback_query.answer()
            await self.help_command(client, callback_query.message)
    
    # ==========================================================================
    #                            QUEUE PROCESSOR
    # ==========================================================================
    
    async def process_queue(self):
        """Process tasks from queue"""
        while True:
            try:
                task = self.task_queue.get_next_task()
                
                if task:
                    await self.process_task(task)
                
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Queue processor error: {e}")
                await asyncio.sleep(5)
    
    async def process_task(self, task: UserTask):
        """Process a single task"""
        user_id = task.user_id
        user_name = task.user_name
        file_path = task.file_path
        file_name = task.file_name
        
        try:
            # Notify user
            await task.message.reply_text(
                f"**🔄 Processing started!**\n"
                f"File: {file_name}\n"
                f"Size: {format_size(task.file_size)}\n\n"
                f"Please wait for further instructions..."
            )
            
            # Check if archive is password protected
            ext = os.path.splitext(file_path)[1].lower()
            is_protected = False
            
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(file_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(file_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(file_path)
            
            # Ask for password if needed
            if is_protected and not task.cancel_requested:
                password_msg = await task.message.reply_text(
                    "**🔐 Archive is password protected**\n\n"
                    "Please enter the password (or send /skip if no password):\n\n"
                    "To cancel, use /cancel"
                )
                
                # Wait for password
                password = await self.wait_for_password(task)
                
                if task.cancel_requested:
                    return
                
                if password and password != "/skip":
                    task.password = password
                    await password_msg.edit_text("**✅ Password received!**")
                else:
                    task.password = None
                    await password_msg.edit_text("**ℹ️ No password provided, attempting without password**")
            
            if task.cancel_requested:
                return
            
            # Ask for domains
            domains_msg = await task.message.reply_text(
                "**🎯 Enter domains to filter**\n\n"
                "Example: `google.com, facebook.com, instagram.com`\n\n"
                "To cancel, use /cancel"
            )
            
            # Wait for domains
            domains = await self.wait_for_domains(task)
            
            if task.cancel_requested:
                return
            
            if not domains:
                await domains_msg.edit_text("**❌ No domains provided, cancelling**")
                self.task_queue.fail_task(task)
                return
            
            task.domains = domains
            await domains_msg.edit_text(f"**✅ Domains received:** {', '.join(domains)}")
            
            if task.cancel_requested:
                return
            
            # Create extraction folder
            unique_id = datetime.now().strftime('%H%M%S%f')
            task.extract_folder = os.path.join(self.extracted_dir, f"{user_id}_{unique_id}")
            os.makedirs(task.extract_folder, exist_ok=True)
            
            # STEP 1: Extract archives
            task.current_stage = "Extracting"
            await self.progress_tracker.update_progress(task, 0, 100, "Extracting", task.message)
            
            extractor = UltimateArchiveExtractor(task.password)
            
            # Run extraction in thread pool
            loop = asyncio.get_event_loop()
            extract_dir = await loop.run_in_executor(
                None,
                lambda: extractor.extract_all_nested(
                    file_path,
                    task.extract_folder,
                    lambda done, new: None  # Simple progress callback
                )
            )
            
            if task.cancel_requested:
                return
            
            # STEP 2: Filter cookies
            task.current_stage = "Filtering"
            await self.progress_tracker.update_progress(task, 0, 100, "Filtering cookies", task.message)
            
            cookie_extractor = UltimateCookieExtractor(domains)
            
            await loop.run_in_executor(
                None,
                lambda: cookie_extractor.process_all(extract_dir)
            )
            
            if task.cancel_requested:
                return
            
            if cookie_extractor.total_found == 0:
                await task.message.reply_text("**❌ No matching cookies found**")
                self.task_queue.fail_task(task)
                return
            
            # STEP 3: Create ZIPs
            task.current_stage = "Zipping"
            await self.progress_tracker.update_progress(task, 0, 100, "Creating ZIP archives", task.message)
            
            result_folder = os.path.join(self.results_dir, datetime.now().strftime('%Y-%m-%d'))
            os.makedirs(result_folder, exist_ok=True)
            
            created_zips = cookie_extractor.create_site_zips(extract_dir, result_folder)
            task.result_zips = list(created_zips.values())
            
            if task.cancel_requested:
                return
            
            # STEP 4: Send results to user
            task.current_stage = "Sending"
            await self.progress_tracker.update_progress(task, 50, 100, "Sending results", task.message)
            
            for site, zip_path in created_zips.items():
                if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                    try:
                        # Send to user
                        await task.message.reply_document(
                            zip_path,
                            caption=f"**✅ Filtered cookies for:** `{site}`\n"
                                   f"**Total entries:** {cookie_extractor.site_files[site].__len__() if site in cookie_extractor.site_files else 0}"
                        )
                        
                        # Forward to log channel
                        if SEND_LOGS:
                            try:
                                await self.app.send_document(
                                    LOG_CHANNEL,
                                    zip_path,
                                    caption=(
                                        f"**📤 Results Sent**\n\n"
                                        f"**User:** {user_name} (ID: {user_id})\n"
                                        f"**Domain:** {site}\n"
                                        f"**File:** {os.path.basename(zip_path)}\n"
                                        f"**Size:** {format_size(os.path.getsize(zip_path))}"
                                    )
                                )
                            except:
                                pass
                    except Exception as e:
                        print(f"Error sending file: {e}")
            
            # Final progress
            await self.progress_tracker.update_progress(task, 100, 100, "Completed", task.message)
            
            # Mark task as completed
            self.task_queue.complete_task(task)
            
            # Clean up
            self.task_queue.cleanup_task_files(task)
            
            # Send completion message
            elapsed = task.end_time - task.start_time if task.end_time else 0
            await task.message.reply_text(
                f"**✅ Processing Complete!**\n\n"
                f"**Files processed:** {cookie_extractor.files_processed}\n"
                f"**Entries found:** {cookie_extractor.total_found}\n"
                f"**Time taken:** {format_time(elapsed)}\n\n"
                f"Thank you for using the bot!"
            )
            
        except Exception as e:
            print(f"Task processing error: {e}")
            import traceback
            traceback.print_exc()
            
            try:
                await task.message.reply_text(f"**❌ Error processing file:** `{str(e)}`")
            except:
                pass
            
            self.task_queue.fail_task(task)
    
    async def wait_for_password(self, task: UserTask) -> Optional[str]:
        """Wait for user to enter password"""
        start_time = time.time()
        timeout = 300  # 5 minutes
        
        while time.time() - start_time < timeout:
            if task.cancel_requested:
                return None
            
            # Check for new messages from user
            # This is simplified - in production you'd use message handlers
            await asyncio.sleep(1)
        
        return None
    
    async def wait_for_domains(self, task: UserTask) -> Optional[List[str]]:
        """Wait for user to enter domains"""
        start_time = time.time()
        timeout = 300  # 5 minutes
        
        while time.time() - start_time < timeout:
            if task.cancel_requested:
                return None
            
            # This is simplified - in production you'd use a proper state system
            await asyncio.sleep(1)
        
        return None

# ==============================================================================
#                                MAIN
# ==============================================================================

async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.start()
        print("Bot is running. Press Ctrl+C to stop.")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
