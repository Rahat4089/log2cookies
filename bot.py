#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - PyroFork Version
A Telegram bot for extracting cookies from nested archives with per-site filtering
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
from pathlib import Path
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import gc
import traceback

# PyroFork imports
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, ForceReply
)
from pyrogram.errors import FloodWait, MessageNotModified, UserIsBlocked
from pyrogram.file_id import FileId
import pyrogram

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
    colorama.init(autoreset=True)
    import humanize
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

# Bot Settings
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB for downloads

# Archive Settings
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

# Create directories
for dir_path in [DOWNLOADS_DIR, EXTRACTED_DIR, RESULTS_DIR, TEMP_DIR]:
    os.makedirs(dir_path, exist_ok=True)

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
                    result = subprocess.run(['which', 'cmd'], capture_output=True, text=True)
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
    if size_bytes < 0:
        return "0 B"
    return humanize.naturalsize(size_bytes, binary=True)

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 0:
        return "0s"
    return humanize.naturaldelta(timedelta(seconds=seconds))

def format_speed(bytes_per_second: float) -> str:
    """Format speed to human readable"""
    if bytes_per_second < 0:
        return "0 B/s"
    return f"{humanize.naturalsize(bytes_per_second, binary=True)}/s"

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

def get_file_name_from_message(message: Message) -> str:
    """Extract filename from message"""
    if message.document:
        return message.document.file_name or f"document_{message.id}"
    return f"file_{message.id}"

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
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.total_archives = 0
        self.current_archive = ""
        self.status_message = ""
    
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
        except Exception as e:
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
        except Exception as e:
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
        
        except Exception as e:
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, progress_callback=None) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            while current_level and not self.stop_extraction:
                next_level = set()
                level_dir = os.path.join(base_dir, f"L{level}")
                os.makedirs(level_dir, exist_ok=True)
                
                futures = {}
                for archive in current_level:
                    if archive in self.processed_files or self.stop_extraction:
                        continue
                    
                    archive_name = os.path.splitext(os.path.basename(archive))[0]
                    archive_name = sanitize_filename(archive_name)[:50]
                    extract_subdir = os.path.join(level_dir, archive_name)
                    os.makedirs(extract_subdir, exist_ok=True)
                    
                    self.current_archive = os.path.basename(archive)
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
                            self.total_archives += len(new_archives)
                        
                        if progress_callback:
                            progress = (self.extracted_count / max(self.total_archives, 1)) * 100
                            await progress_callback(
                                progress,
                                f"Extracting: {os.path.basename(archive)}",
                                f"Found {len(new_archives)} new archives"
                            )
                    except Exception as e:
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
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
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
            
            site_matches: Dict[str, List[Tuple[int, str]]] = {
                site: [] for site in self.target_sites
            }
            
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
                
        except Exception as e:
            pass
    
    async def process_all(self, extract_dir: str, progress_callback=None):
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
            
            completed = 0
            total = len(futures)
            
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
                completed += 1
                
                if progress_callback and completed % 10 == 0:
                    progress = (completed / total) * 100
                    await progress_callback(
                        progress,
                        f"Processing cookies: {completed}/{total} files",
                        f"Found {self.total_found} entries"
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
#                            STATS COLLECTOR
# ==============================================================================

class StatsCollector:
    """Collect system statistics"""
    
    @staticmethod
    def get_system_stats():
        """Get comprehensive system statistics"""
        stats = {}
        
        # Disk
        disk = psutil.disk_usage('/')
        stats['disk_total'] = disk.total
        stats['disk_used'] = disk.used
        stats['disk_free'] = disk.free
        stats['disk_percent'] = disk.percent
        
        # RAM
        ram = psutil.virtual_memory()
        stats['ram_total'] = ram.total
        stats['ram_used'] = ram.used
        stats['ram_free'] = ram.available
        stats['ram_percent'] = ram.percent
        
        # CPU
        stats['cpu_cores'] = psutil.cpu_count()
        stats['cpu_percent'] = psutil.cpu_percent(interval=0.5)
        
        # Process
        process = psutil.Process()
        stats['process_cpu'] = process.cpu_percent(interval=0.5)
        stats['process_memory_rss'] = process.memory_info().rss
        stats['process_memory_vms'] = process.memory_info().vms
        
        # Network
        net = psutil.net_io_counters()
        stats['net_sent'] = net.bytes_sent
        stats['net_recv'] = net.bytes_recv
        
        # System
        stats['os'] = platform.system()
        stats['os_version'] = platform.release()
        stats['python_version'] = platform.python_version()
        stats['boot_time'] = psutil.boot_time()
        
        return stats
    
    @staticmethod
    def format_stats(stats, ping):
        """Format stats as beautiful table"""
        uptime_seconds = time.time() - stats['boot_time']
        uptime_hours = uptime_seconds / 3600
        uptime_str = f"{int(uptime_hours)}h {int((uptime_seconds % 3600)/60)}m {int(uptime_seconds % 60)}s"
        
        stats_text = f"""
🖥️ **System Statistics Dashboard**

💾 **Disk Storage**
├ Total:  {format_size(stats['disk_total'])}
├ Used:   {format_size(stats['disk_used'])} ({stats['disk_percent']:.1f}%)
└ Free:   {format_size(stats['disk_free'])}

🧠 **RAM (Memory)**
├ Total:  {format_size(stats['ram_total'])}
├ Used:   {format_size(stats['ram_used'])} ({stats['ram_percent']:.1f}%)
└ Free:   {format_size(stats['ram_free'])}

⚡ **CPU**
├ Cores:  {stats['cpu_cores']}
└ Usage:  {stats['cpu_percent']:.1f}%

🔌 **Bot Process**
├ CPU:    {stats['process_cpu']:.1f}%
├ RAM (RSS): {format_size(stats['process_memory_rss'])}
└ RAM (VMS): {format_size(stats['process_memory_vms'])}

🌐 **Network**
├ Upload Speed:   {format_size(stats.get('upload_speed', 0))}/s
├ Download Speed: {format_size(stats.get('download_speed', 0))}/s
└ Total I/O:      {format_size(stats['net_sent'] + stats['net_recv'])}

📟 **System Info**
├ OS:        {stats['os']}
├ OS Version: {stats['os_version']}
├ Python:    {stats['python_version']}
└ Uptime:    {uptime_str}

⏱️ **Performance**
└ Current Ping: {ping:.3f} ms

👤 **Owner:** {OWNER_USERNAME}
"""
        return stats_text

# ==============================================================================
#                            QUEUE MANAGEMENT
# ==============================================================================

class TaskStatus:
    WAITING = "waiting"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class UserTask:
    """Represents a user's processing task"""
    
    def __init__(self, user_id: int, chat_id: int, message_id: int, file_path: str, file_name: str, file_size: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.file_path = file_path
        self.file_name = file_name
        self.file_size = file_size
        self.status = TaskStatus.WAITING
        self.progress = 0
        self.status_message = ""
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.password = None
        self.target_sites = []
        self.result_files = []
        self.cancelled = False
        self.task_id = generate_random_string(8)
        
    @property
    def wait_time(self):
        if self.started_at:
            return (self.started_at - self.created_at).total_seconds()
        return (datetime.now() - self.created_at).total_seconds()
    
    @property
    def processing_time(self):
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        if self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0
    
    def cancel(self):
        self.cancelled = True
        self.status = TaskStatus.CANCELLED

class TaskQueue:
    """Manages user tasks"""
    
    def __init__(self):
        self.queue = deque()
        self.current_task = None
        self.user_tasks = {}  # user_id -> task
        self.lock = asyncio.Lock()
        self.processing = False
    
    async def add_task(self, user_id: int, chat_id: int, message_id: int, file_path: str, file_name: str, file_size: int) -> UserTask:
        """Add task to queue"""
        async with self.lock:
            # Check if user already has a task
            if user_id in self.user_tasks and self.user_tasks[user_id].status in [TaskStatus.WAITING, TaskStatus.DOWNLOADING, TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
                return None
            
            task = UserTask(user_id, chat_id, message_id, file_path, file_name, file_size)
            self.queue.append(task)
            self.user_tasks[user_id] = task
            return task
    
    async def get_next_task(self) -> Optional[UserTask]:
        """Get next task from queue"""
        async with self.lock:
            if self.queue and not self.processing:
                self.current_task = self.queue.popleft()
                self.current_task.status = TaskStatus.PROCESSING
                self.current_task.started_at = datetime.now()
                self.processing = True
                return self.current_task
            return None
    
    async def complete_task(self, task: UserTask):
        """Mark task as completed"""
        async with self.lock:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            if self.current_task and self.current_task.task_id == task.task_id:
                self.current_task = None
                self.processing = False
            if task.user_id in self.user_tasks:
                del self.user_tasks[task.user_id]
    
    async def fail_task(self, task: UserTask, error: str = ""):
        """Mark task as failed"""
        async with self.lock:
            task.status = TaskStatus.FAILED
            task.status_message = error
            task.completed_at = datetime.now()
            if self.current_task and self.current_task.task_id == task.task_id:
                self.current_task = None
                self.processing = False
            if task.user_id in self.user_tasks:
                del self.user_tasks[task.user_id]
    
    async def cancel_task(self, user_id: int) -> bool:
        """Cancel user's task"""
        async with self.lock:
            if user_id in self.user_tasks:
                task = self.user_tasks[user_id]
                task.cancel()
                
                # Remove from queue if waiting
                if task.status == TaskStatus.WAITING:
                    self.queue = deque([t for t in self.queue if t.user_id != user_id])
                    del self.user_tasks[user_id]
                
                return True
            return False
    
    async def get_queue_info(self) -> str:
        """Get formatted queue information"""
        async with self.lock:
            if not self.queue and not self.current_task:
                return "📪 **Queue is empty**"
            
            lines = ["📊 **Current Queue**\n"]
            
            if self.current_task:
                user_info = f"User {self.current_task.user_id}"
                try:
                    # Try to get username if available (would need client reference)
                    pass
                except:
                    pass
                
                lines.append(f"**▶ Currently Processing:**")
                lines.append(f"├ User: `{user_info}`")
                lines.append(f"├ File: `{self.current_task.file_name}`")
                lines.append(f"├ Size: {format_size(self.current_task.file_size)}")
                lines.append(f"├ Status: `{self.current_task.status}`")
                lines.append(f"├ Progress: {self.current_task.progress:.1f}%")
                lines.append(f"└ Wait Time: {format_time(self.current_task.wait_time)}\n")
            
            if self.queue:
                lines.append(f"**⏳ Waiting ({len(self.queue)} tasks):**")
                for i, task in enumerate(self.queue, 1):
                    user_info = f"User {task.user_id}"
                    lines.append(f"{i}. `{user_info}` - `{task.file_name}` ({format_size(task.file_size)}) - Waiting: {format_time(task.wait_time)}")
            else:
                lines.append("**⏳ No waiting tasks**")
            
            return "\n".join(lines)

# ==============================================================================
#                            PROGRESS MANAGER
# ==============================================================================

class ProgressManager:
    """Manages progress messages"""
    
    def __init__(self, client, chat_id: int, message_id: int):
        self.client = client
        self.chat_id = chat_id
        self.message_id = message_id
        self.last_update = 0
        self.last_text = ""
        self.update_interval = 1  # seconds
    
    def create_progress_bar(self, percentage: float, width: int = 10) -> str:
        """Create a text progress bar"""
        filled = int(width * percentage / 100)
        bar = "█" * filled + "░" * (width - filled)
        return bar
    
    async def update(self, current: int, total: int, status: str, extra: str = ""):
        """Update progress message"""
        now = time.time()
        if now - self.last_update < self.update_interval and current < total:
            return
        
        self.last_update = now
        percentage = (current / total) * 100 if total > 0 else 0
        bar = self.create_progress_bar(percentage)
        
        # Calculate speed and ETA
        elapsed = now - getattr(self, 'start_time', now)
        if elapsed > 0 and current > 0:
            speed = current / elapsed
            eta = (total - current) / speed if speed > 0 else 0
        else:
            speed = 0
            eta = 0
        
        text = f"""
**{status}**

{bar} `{percentage:.1f}%`

**📦 Progress:** {format_size(current)} / {format_size(total)}
**⚡ Speed:** {format_speed(speed)}
**⏱️ Elapsed:** {format_time(elapsed)}
**⏳ ETA:** {format_time(eta)}

{extra}
"""
        
        try:
            if text != self.last_text:
                await self.client.edit_message_text(
                    self.chat_id,
                    self.message_id,
                    text,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                self.last_text = text
        except MessageNotModified:
            pass
        except Exception as e:
            pass
    
    async def update_extraction(self, progress: float, current: str, extra: str):
        """Update extraction progress"""
        now = time.time()
        if now - self.last_update < self.update_interval and progress < 100:
            return
        
        self.last_update = now
        bar = self.create_progress_bar(progress)
        
        elapsed = now - getattr(self, 'extract_start', now)
        
        text = f"""
**📦 Extracting Archives**

{bar} `{progress:.1f}%`

**📄 Current:** `{current}`
**{extra}**

**⏱️ Elapsed:** {format_time(elapsed)}
"""
        
        try:
            if text != self.last_text:
                await self.client.edit_message_text(
                    self.chat_id,
                    self.message_id,
                    text,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                self.last_text = text
        except:
            pass

# ==============================================================================
#                            BOT CLASS
# ==============================================================================

class RUTEBot:
    """Main bot class"""
    
    def __init__(self):
        self.app = Client(
            "rute_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        self.queue = TaskQueue()
        self.user_states = {}  # user_id -> state
        self.download_semaphore = asyncio.Semaphore(3)  # Max 3 concurrent downloads
        self.start_time = time.time()
        self.net_io_start = psutil.net_io_counters()
        self.net_time_start = time.time()
    
    async def get_network_speed(self):
        """Calculate current network speed"""
        net_io = psutil.net_io_counters()
        time_diff = time.time() - self.net_time_start
        
        if time_diff > 0:
            upload_speed = (net_io.bytes_sent - self.net_io_start.bytes_sent) / time_diff
            download_speed = (net_io.bytes_recv - self.net_io_start.bytes_recv) / time_diff
        else:
            upload_speed = download_speed = 0
        
        return upload_speed, download_speed
    
    async def reset_network_stats(self):
        """Reset network stats for speed calculation"""
        self.net_io_start = psutil.net_io_counters()
        self.net_time_start = time.time()
    
    async def forward_to_logs(self, message: Message, caption: str = ""):
        """Forward message to log channel"""
        if not SEND_LOGS or not LOG_CHANNEL:
            return
        
        try:
            await message.forward(LOG_CHANNEL)
            
            if caption:
                await self.app.send_message(LOG_CHANNEL, caption)
        except Exception as e:
            print(f"Error forwarding to logs: {e}")
    
    async def send_log_message(self, text: str):
        """Send text message to log channel"""
        if not SEND_LOGS or not LOG_CHANNEL:
            return
        
        try:
            await self.app.send_message(LOG_CHANNEL, text)
        except Exception as e:
            print(f"Error sending log: {e}")
    
    async def cleanup_user_files(self, user_id: int):
        """Delete all files for a user"""
        try:
            # Delete download
            user_download = os.path.join(DOWNLOADS_DIR, str(user_id))
            if os.path.exists(user_download):
                delete_entire_folder(user_download)
            
            # Delete extract
            user_extract = os.path.join(EXTRACTED_DIR, str(user_id))
            if os.path.exists(user_extract):
                delete_entire_folder(user_extract)
            
            # Delete results
            user_result = os.path.join(RESULTS_DIR, str(user_id))
            if os.path.exists(user_result):
                delete_entire_folder(user_result)
        except Exception as e:
            print(f"Error cleaning up user {user_id} files: {e}")
    
    async def download_file(self, message: Message, progress_manager: ProgressManager) -> Optional[str]:
        """Download file from Telegram"""
        try:
            file = message.document or message.video or message.audio or message.photo
            if not file:
                return None
            
            file_size = getattr(file, 'file_size', 0)
            if file_size > MAX_FILE_SIZE:
                await message.reply(f"❌ File too large! Maximum size: {format_size(MAX_FILE_SIZE)}")
                return None
            
            user_id = message.from_user.id
            file_name = get_file_name_from_message(message)
            
            # Create user download directory
            user_dir = os.path.join(DOWNLOADS_DIR, str(user_id))
            os.makedirs(user_dir, exist_ok=True)
            
            file_path = os.path.join(user_dir, file_name)
            
            # Download with progress
            progress_manager.start_time = time.time()
            
            async def progress(current, total):
                await progress_manager.update(current, total, "📥 Downloading...")
            
            await message.download(file_name=file_path, progress=progress)
            
            return file_path
            
        except Exception as e:
            await message.reply(f"❌ Download failed: {str(e)}")
            return None
    
    async def process_task(self, task: UserTask):
        """Process a user task"""
        user_id = task.user_id
        chat_id = task.chat_id
        
        try:
            # Send initial status
            status_msg = await self.app.send_message(
                chat_id,
                f"✅ File received!\n"
                f"📄 **File:** `{task.file_name}`\n"
                f"📦 **Size:** {format_size(task.file_size)}\n"
                f"⏳ **Queue Position:** {len(self.queue.queue) + 1}\n\n"
                f"Please enter the domains to filter (comma-separated):",
                reply_markup=ForceReply(selective=True)
            )
            
            # Wait for domains
            def check_domains(_, m):
                return m.reply_to_message_id == status_msg.id and m.from_user.id == user_id
            
            try:
                domains_msg = await self.app.listen(chat_id, filters=filters.text, timeout=300)
                task.target_sites = [s.strip().lower() for s in domains_msg.text.split(',') if s.strip()]
                
                if not task.target_sites:
                    await self.app.send_message(chat_id, "❌ No domains specified. Task cancelled.")
                    await self.queue.fail_task(task, "No domains")
                    return
                
                await self.app.send_message(
                    chat_id,
                    f"✅ Domains received: {', '.join(task.target_sites)}\n"
                    f"🔍 Checking password protection..."
                )
            except asyncio.TimeoutError:
                await self.app.send_message(chat_id, "⏰ Timeout waiting for domains. Task cancelled.")
                await self.queue.fail_task(task, "Timeout")
                return
            
            # Check password
            ext = os.path.splitext(task.file_path)[1].lower()
            is_protected = False
            
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(task.file_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(task.file_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(task.file_path)
            
            if is_protected:
                await self.app.send_message(
                    chat_id,
                    "🔒 Archive is password protected!\n"
                    "Please enter the password (or /cancel to skip):",
                    reply_markup=ForceReply(selective=True)
                )
                
                try:
                    password_msg = await self.app.listen(chat_id, filters=filters.text, timeout=120)
                    if password_msg.text.startswith('/'):
                        await self.app.send_message(chat_id, "❌ Password input cancelled.")
                        await self.queue.fail_task(task, "Password cancelled")
                        return
                    task.password = password_msg.text
                    await self.app.send_message(chat_id, "✅ Password received, starting extraction...")
                except asyncio.TimeoutError:
                    await self.app.send_message(chat_id, "⏰ Timeout waiting for password. Task cancelled.")
                    await self.queue.fail_task(task, "Timeout")
                    return
            
            # Create progress manager
            progress_msg = await self.app.send_message(chat_id, "🔄 Starting extraction...")
            progress_manager = ProgressManager(self.app, chat_id, progress_msg.id)
            progress_manager.extract_start = time.time()
            
            # Create extractor
            extractor = UltimateArchiveExtractor(task.password)
            
            # Create directories
            extract_dir = os.path.join(EXTRACTED_DIR, str(user_id), generate_random_string())
            os.makedirs(extract_dir, exist_ok=True)
            
            # Extract archives
            async def extraction_progress(progress, current, extra):
                await progress_manager.update_extraction(progress, current, extra)
            
            await extractor.extract_all_nested(
                task.file_path,
                extract_dir,
                extraction_progress
            )
            
            if task.cancelled:
                return
            
            # Create cookie extractor
            cookie_extractor = UltimateCookieExtractor(task.target_sites)
            
            # Process cookies
            await progress_manager.update(0, 100, "🔍 Processing cookies...")
            
            async def cookie_progress(progress, current, extra):
                await progress_manager.update(
                    int(progress * cookie_extractor.files_processed / 100),
                    cookie_extractor.files_processed,
                    current,
                    extra
                )
            
            await cookie_extractor.process_all(extract_dir, cookie_progress)
            
            if task.cancelled:
                return
            
            # Create results
            if cookie_extractor.total_found > 0:
                result_dir = os.path.join(RESULTS_DIR, str(user_id), generate_random_string())
                os.makedirs(result_dir, exist_ok=True)
                
                created_zips = cookie_extractor.create_site_zips(extract_dir, result_dir)
                
                # Send results to user
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        await self.app.send_document(
                            chat_id,
                            zip_path,
                            caption=f"✅ Cookies for **{site}**\n"
                                    f"📊 Entries: {cookie_extractor.total_found}\n"
                                    f"📦 Size: {format_size(os.path.getsize(zip_path))}\n\n"
                                    f"👤 Owner: {OWNER_USERNAME}"
                        )
                        
                        # Forward to logs
                        await self.forward_to_logs(
                            await self.app.get_messages(chat_id, (await self.app.get_history(chat_id, 1))[0].id),
                            f"User: {user_id}\nSite: {site}\nEntries: {cookie_extractor.total_found}"
                        )
                
                # Send summary
                elapsed = time.time() - progress_manager.extract_start
                await self.app.send_message(
                    chat_id,
                    f"✅ **Processing Complete!**\n\n"
                    f"📊 **Statistics:**\n"
                    f"├ Files processed: {cookie_extractor.files_processed}\n"
                    f"├ Entries found: {cookie_extractor.total_found}\n"
                    f"├ ZIP archives: {len(created_zips)}\n"
                    f"└ Time taken: {format_time(elapsed)}\n\n"
                    f"👤 Owner: {OWNER_USERNAME}"
                )
            else:
                await self.app.send_message(
                    chat_id,
                    f"⚠️ No matching cookies found for domains: {', '.join(task.target_sites)}"
                )
            
            # Mark task as completed
            await self.queue.complete_task(task)
            
            # Cleanup user files
            await self.cleanup_user_files(user_id)
            
        except Exception as e:
            error_trace = traceback.format_exc()
            await self.app.send_message(
                chat_id,
                f"❌ **Error processing file:**\n`{str(e)}`\n\nPlease try again later."
            )
            await self.send_log_message(f"Error for user {user_id}:\n```{error_trace}```")
            await self.queue.fail_task(task, str(e))
            await self.cleanup_user_files(user_id)
    
    async def queue_processor(self):
        """Background task to process queue"""
        while True:
            try:
                task = await self.queue.get_next_task()
                if task:
                    await self.process_task(task)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Queue processor error: {e}")
                await asyncio.sleep(5)
    
    async def start(self):
        """Start the bot"""
        await self.app.start()
        
        # Start queue processor
        asyncio.create_task(self.queue_processor())
        
        # Set bot commands
        await self.app.set_bot_commands([
            {"command": "start", "description": "Start the bot"},
            {"command": "help", "description": "Show help"},
            {"command": "stats", "description": "Show system statistics"},
            {"command": "queue", "description": "Show current queue"},
            {"command": "cancel", "description": "Cancel your current task"},
            {"command": "ping", "description": "Check bot latency"}
        ])
        
        print(f"Bot started! @{(await self.app.get_me()).username}")
        await self.send_log_message(f"🚀 **Bot Started**\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    async def stop(self):
        """Stop the bot"""
        await self.app.stop()
        print("Bot stopped!")
    
    def run(self):
        """Run the bot"""
        try:
            self.app.run(self.start())
        except KeyboardInterrupt:
            asyncio.create_task(self.stop())

# ==============================================================================
#                            BOT HANDLERS
# ==============================================================================

bot = RUTEBot()

@bot.app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    """Start command handler"""
    await message.reply_text(
        f"👋 **Welcome to RUTE Cookie Extractor Bot!**\n\n"
        f"Send me any archive file (ZIP, RAR, 7Z, etc.) and I'll extract cookies from it.\n\n"
        f"**Features:**\n"
        f"• Supports nested archives\n"
        f"• Per-site filtering\n"
        f"• Password protected archives\n"
        f"• Maximum file size: {format_size(MAX_FILE_SIZE)}\n"
        f"• Queue system for multiple users\n\n"
        f"**Commands:**\n"
        f"/help - Show detailed help\n"
        f"/stats - System statistics\n"
        f"/queue - View queue\n"
        f"/cancel - Cancel your task\n"
        f"/ping - Check latency\n\n"
        f"👤 Owner: {OWNER_USERNAME}"
    )

@bot.app.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    """Help command handler"""
    await message.reply_text(
        f"📚 **RUTE Cookie Extractor - Help**\n\n"
        f"**How to use:**\n"
        f"1. Send an archive file (ZIP, RAR, 7Z, etc.)\n"
        f"2. Enter the domains to filter (comma-separated)\n"
        f"3. If password protected, enter the password\n"
        f"4. Wait for processing\n"
        f"5. Receive filtered cookie files\n\n"
        f"**Supported formats:**\n"
        f"{', '.join(SUPPORTED_ARCHIVES)}\n\n"
        f"**Cookie folders:**\n"
        f"{', '.join(COOKIE_FOLDERS)}\n\n"
        f"**Queue system:**\n"
        f"• One task per user at a time\n"
        f"• Check queue status with /queue\n"
        f"• Cancel with /cancel\n\n"
        f"**Statistics:**\n"
        f"• View system stats with /stats\n"
        f"• Check ping with /ping\n\n"
        f"👤 Owner: {OWNER_USERNAME}"
    )

@bot.app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: Message):
    """Ping command handler"""
    start = time.time()
    msg = await message.reply_text("🏓 Pinging...")
    end = time.time()
    ping = (end - start) * 1000
    await msg.edit_text(f"🏓 **Pong!**\nLatency: `{ping:.2f} ms`")

@bot.app.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    """Stats command handler"""
    msg = await message.reply_text("📊 Collecting statistics...")
    
    try:
        stats = StatsCollector.get_system_stats()
        
        # Get network speed
        upload_speed, download_speed = await bot.get_network_speed()
        stats['upload_speed'] = upload_speed
        stats['download_speed'] = download_speed
        
        # Get ping
        start = time.time()
        await client.get_me()
        ping = (time.time() - start) * 1000
        
        stats_text = StatsCollector.format_stats(stats, ping)
        
        await msg.edit_text(stats_text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        await msg.edit_text(f"❌ Error getting stats: {str(e)}")

@bot.app.on_message(filters.command("queue") & filters.private)
async def queue_command(client: Client, message: Message):
    """Queue command handler"""
    queue_info = await bot.queue.get_queue_info()
    await message.reply_text(queue_info, parse_mode=enums.ParseMode.MARKDOWN)

@bot.app.on_message(filters.command("cancel") & filters.private)
async def cancel_command(client: Client, message: Message):
    """Cancel command handler"""
    user_id = message.from_user.id
    
    if await bot.queue.cancel_task(user_id):
        await message.reply_text("✅ Your task has been cancelled.")
        await bot.cleanup_user_files(user_id)
    else:
        await message.reply_text("❌ No active task found to cancel.")

@bot.app.on_message(filters.document | filters.video | filters.audio | filters.photo)
async def handle_file(client: Client, message: Message):
    """Handle file messages"""
    user_id = message.from_user.id
    
    # Check if user already has a task
    if user_id in bot.queue.user_tasks:
        task = bot.queue.user_tasks[user_id]
        if task.status in [TaskStatus.WAITING, TaskStatus.DOWNLOADING, TaskStatus.EXTRACTING, TaskStatus.PROCESSING]:
            await message.reply_text(
                f"❌ You already have a task in queue!\n"
                f"Status: `{task.status}`\n"
                f"Use /cancel to cancel it first."
            )
            return
    
    # Get file info
    file = message.document or message.video or message.audio
    if not file:
        await message.reply_text("❌ Unsupported file type")
        return
    
    file_name = get_file_name_from_message(message)
    file_size = file.file_size
    
    # Check extension
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in SUPPORTED_ARCHIVES:
        await message.reply_text(
            f"❌ Unsupported archive format!\n"
            f"Supported: {', '.join(SUPPORTED_ARCHIVES)}"
        )
        return
    
    # Check file size
    if file_size > MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ File too large!\n"
            f"Maximum size: {format_size(MAX_FILE_SIZE)}\n"
            f"Your file: {format_size(file_size)}"
        )
        return
    
    # Send acknowledgment
    status_msg = await message.reply_text(
        f"📥 **File received!**\n\n"
        f"📄 **Name:** `{file_name}`\n"
        f"📦 **Size:** {format_size(file_size)}\n"
        f"🔍 **Type:** {ext}\n\n"
        f"⏳ Adding to queue..."
    )
    
    # Create progress manager for download
    progress_manager = ProgressManager(client, message.chat.id, status_msg.id)
    
    # Download file
    file_path = await bot.download_file(message, progress_manager)
    
    if not file_path:
        return
    
    # Add to queue
    task = await bot.queue.add_task(
        user_id,
        message.chat.id,
        status_msg.id,
        file_path,
        file_name,
        file_size
    )
    
    if task:
        position = len(bot.queue.queue)
        await status_msg.edit_text(
            f"✅ **File added to queue!**\n\n"
            f"📄 **File:** `{file_name}`\n"
            f"📦 **Size:** {format_size(file_size)}\n"
            f"🎯 **Position:** #{position}\n\n"
            f"You will be notified when processing starts."
        )
        
        # Forward to logs
        await bot.forward_to_logs(
            message,
            f"User: {user_id}\nFile: {file_name}\nSize: {format_size(file_size)}"
        )
    else:
        await status_msg.edit_text("❌ Failed to add task to queue. Please try again.")

@bot.app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback queries"""
    data = callback_query.data
    
    if data.startswith("cancel_"):
        user_id = int(data.split("_")[1])
        
        if callback_query.from_user.id == user_id or callback_query.from_user.id in ADMINS:
            if await bot.queue.cancel_task(user_id):
                await callback_query.answer("Task cancelled!")
                await callback_query.message.edit_text("✅ Task cancelled successfully.")
                await bot.cleanup_user_files(user_id)
            else:
                await callback_query.answer("No active task found!", show_alert=True)
        else:
            await callback_query.answer("You can only cancel your own tasks!", show_alert=True)

@bot.app.on_message(filters.command("admin") & filters.user(ADMINS))
async def admin_command(client: Client, message: Message):
    """Admin commands"""
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply_text(
            "🔧 **Admin Commands:**\n\n"
            "/admin stats - Show detailed stats\n"
            "/admin queue - Manage queue\n"
            "/admin cancel [user_id] - Cancel user task\n"
            "/admin broadcast [message] - Broadcast to all users\n"
            "/admin cleanup - Clean up old files"
        )
        return
    
    command = args[1].lower()
    
    if command == "stats":
        stats = StatsCollector.get_system_stats()
        upload_speed, download_speed = await bot.get_network_speed()
        
        # Queue stats
        queue_size = len(bot.queue.queue)
        current_task = bot.queue.current_task
        
        stats_text = f"""
📊 **Admin Statistics**

**System:**
├ CPU: {stats['cpu_percent']:.1f}%
├ RAM: {format_size(stats['ram_used'])} / {format_size(stats['ram_total'])} ({stats['ram_percent']:.1f}%)
└ Disk: {format_size(stats['disk_used'])} / {format_size(stats['disk_total'])} ({stats['disk_percent']:.1f}%)

**Queue:**
├ Waiting: {queue_size}
├ Processing: {'Yes' if current_task else 'No'}
└ Current User: {current_task.user_id if current_task else 'None'}

**Network:**
├ Upload: {format_speed(upload_speed)}
├ Download: {format_speed(download_speed)}
└ Total I/O: {format_size(stats['net_sent'] + stats['net_recv'])}

**Bot Uptime:** {format_time(time.time() - bot.start_time)}
"""
        await message.reply_text(stats_text)
    
    elif command == "queue":
        queue_info = await bot.queue.get_queue_info()
        await message.reply_text(queue_info + "\n\nUse /admin cancel [user_id] to cancel tasks")
    
    elif command == "cancel" and len(args) >= 3:
        try:
            user_id = int(args[2])
            if await bot.queue.cancel_task(user_id):
                await message.reply_text(f"✅ Cancelled task for user {user_id}")
                await bot.cleanup_user_files(user_id)
            else:
                await message.reply_text(f"❌ No task found for user {user_id}")
        except ValueError:
            await message.reply_text("❌ Invalid user ID")
    
    elif command == "cleanup":
        await message.reply_text("🧹 Cleaning up old files...")
        
        # Clean old downloads (> 1 hour)
        cutoff = time.time() - 3600
        cleaned = 0
        
        for folder in [DOWNLOADS_DIR, EXTRACTED_DIR, RESULTS_DIR]:
            for user_folder in os.listdir(folder):
                user_path = os.path.join(folder, user_folder)
                if os.path.isdir(user_path):
                    try:
                        mod_time = os.path.getmtime(user_path)
                        if mod_time < cutoff:
                            delete_entire_folder(user_path)
                            cleaned += 1
                    except:
                        pass
        
        await message.reply_text(f"✅ Cleaned up {cleaned} old folders")

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    print("Starting RUTE Cookie Extractor Bot...")
    print(f"System: {SYSTEM}")
    print(f"Tools: 7z={TOOL_STATUS['7z']}, UnRAR={TOOL_STATUS['unrar']}")
    print(f"Owner: {OWNER_USERNAME}")
    print("=" * 50)
    
    bot.run()
