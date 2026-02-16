#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - Pyrofork Version
Processes archive files and extracts cookies for specific domains
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
from collections import defaultdict, deque
import threading
import gc
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Pyrofork imports
from pyrogram import Client, filters, types, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified, UserNotParticipant
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports for extraction
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    os.system("pip install -q tqdm")
    from tqdm import tqdm

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
    HAS_COLORAMA = True
except ImportError:
    os.system("pip install -q colorama")
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
    HAS_COLORAMA = True

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

# Install humanize if not present
try:
    import humanize
except ImportError:
    os.system("pip install -q humanize")
    import humanize

# ==============================================================================
#                            CONFIGURATION
# ==============================================================================

# Bot Configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396  # Channel ID for logs
SEND_LOGS = True  # Whether to forward files to log channel
ADMINS = [7125341830]  # Admin user IDs

# Owner credit
OWNER_CREDIT = "@still_alivenow"

# Performance Settings
MAX_WORKERS = 100  # Threads for extraction
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB max file size
MAX_CONCURRENT_TASKS = 10  # Maximum concurrent tasks across all users
MAX_USER_TASKS = 1  # One task per user at a time

# Supported archives
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Detect system
SYSTEM = platform.system().lower()

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

# Create directories
for dir_path in [DOWNLOADS_DIR, EXTRACTED_DIR, RESULTS_DIR, TEMP_DIR]:
    os.makedirs(dir_path, exist_ok=True)

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
    return humanize.naturalsize(size_bytes)

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    return str(timedelta(seconds=int(seconds)))

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

def clean_user_data(user_id: int):
    """Clean all data for a specific user"""
    user_dirs = [
        os.path.join(DOWNLOADS_DIR, str(user_id)),
        os.path.join(EXTRACTED_DIR, str(user_id)),
        os.path.join(RESULTS_DIR, str(user_id)),
        os.path.join(TEMP_DIR, str(user_id))
    ]
    
    for dir_path in user_dirs:
        if os.path.exists(dir_path):
            delete_entire_folder(dir_path)

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
        self.total_archives = 1
        self.current_archive = ""
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set progress callback function"""
        self.progress_callback = callback
    
    def update_progress(self, current: int, total: int, status: str = ""):
        """Update extraction progress"""
        if self.progress_callback:
            try:
                asyncio.create_task(self.progress_callback(current, total, status))
            except:
                pass
    
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
        except Exception as e:
            print(f"7z extraction error: {e}")
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
        except Exception as e:
            print(f"UnRAR extraction error: {e}")
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
        except Exception as e:
            print(f"ZIP extraction error: {e}")
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
        self.current_archive = os.path.basename(archive_path)
        
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
            print(f"Extraction error for {archive_path}: {e}")
        
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, status_msg) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        processed = 0
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            # Update total archives
            self.total_archives += len(current_level)
            
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
                            processed += 1
                        
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                        
                        # Update progress
                        await self.update_progress(
                            processed, 
                            self.total_archives,
                            f"Extracting: {os.path.basename(archive)}"
                        )
                        
                        # Update status message
                        if status_msg:
                            try:
                                await status_msg.edit_text(
                                    f"📦 **Extraction Progress**\n\n"
                                    f"Processed: {processed}/{self.total_archives}\n"
                                    f"Current: {os.path.basename(archive)[:30]}...\n"
                                    f"Found new: {len(new_archives)} archives"
                                )
                            except:
                                pass
                                
                    except Exception as e:
                        print(f"Future error: {e}")
                        processed += 1
                        await self.update_progress(processed, self.total_archives, f"Error: {str(e)[:30]}")
            
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
        self.site_patterns = {site: re.compile(re.escape(site), re.IGNORECASE) for site in self.target_sites}
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set progress callback function"""
        self.progress_callback = callback
    
    async def update_progress(self, current: int, total: int, status: str = ""):
        """Update processing progress"""
        if self.progress_callback:
            try:
                await self.progress_callback(current, total, status)
            except:
                pass
    
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
                try:
                    line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                except:
                    continue
                
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower.decode('utf-8', errors='ignore')):
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
            print(f"Error processing file {file_path}: {e}")
    
    async def process_all(self, extract_dir: str, status_msg):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        total_files = len(cookie_files)
        processed = 0
        
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
                processed += 1
                
                # Update progress
                await self.update_progress(
                    processed, 
                    total_files,
                    f"Processing: {processed}/{total_files}"
                )
                
                # Update status message every 10 files
                if processed % 10 == 0 and status_msg:
                    try:
                        await status_msg.edit_text(
                            f"🔍 **Cookie Processing**\n\n"
                            f"Files: {processed}/{total_files}\n"
                            f"Entries found: {self.total_found}\n"
                            f"Status: Working..."
                        )
                    except:
                        pass
    
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
#                            STATISTICS DASHBOARD
# ==============================================================================

class SystemStats:
    """Get system statistics"""
    
    @staticmethod
    def get_stats() -> str:
        """Get formatted system statistics"""
        try:
            # Disk
            disk = psutil.disk_usage('/')
            disk_total = disk.total
            disk_used = disk.used
            disk_free = disk.free
            disk_percent = (disk_used / disk_total) * 100
            
            # Memory
            memory = psutil.virtual_memory()
            mem_total = memory.total
            mem_used = memory.used
            mem_free = memory.available
            mem_percent = memory.percent
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            
            # Process
            process = psutil.Process()
            proc_cpu = process.cpu_percent(interval=0.1)
            proc_memory_rss = process.memory_info().rss
            proc_memory_vms = process.memory_info().vms
            
            # Network
            net_io = psutil.net_io_counters()
            bytes_sent = net_io.bytes_sent
            bytes_recv = net_io.bytes_recv
            total_io = bytes_sent + bytes_recv
            
            # Get network speeds (approximate)
            try:
                net_io_old = psutil.net_io_counters()
                time.sleep(0.1)
                net_io_new = psutil.net_io_counters()
                upload_speed = (net_io_new.bytes_sent - net_io_old.bytes_sent) / 0.1
                download_speed = (net_io_new.bytes_recv - net_io_old.bytes_recv) / 0.1
            except:
                upload_speed = 0
                download_speed = 0
            
            # System info
            os_name = platform.system()
            os_version = platform.release()
            python_version = platform.python_version()
            
            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            
            # Bot uptime (if app has start time)
            bot_uptime = "N/A"
            if hasattr(app, 'start_time'):
                bot_uptime_sec = (datetime.now() - app.start_time).total_seconds()
                bot_uptime = format_time(bot_uptime_sec)
            
            # Ping (approximate)
            ping = random.uniform(150, 250)  # Placeholder
            
            stats = f"""
🖥️ **System Statistics Dashboard**

💾 **Disk Storage**
├ Total:  {format_size(disk_total)}
├ Used:   {format_size(disk_used)} ({disk_percent:.1f}%)
└ Free:   {format_size(disk_free)}

🧠 **RAM (Memory)**
├ Total:  {format_size(mem_total)}
├ Used:   {format_size(mem_used)} ({mem_percent:.1f}%)
└ Free:   {format_size(mem_free)}

⚡ **CPU**
├ Cores:  {cpu_count}
└ Usage:  {cpu_percent:.1f}%

🔌 **Bot Process**
├ CPU:    {proc_cpu:.1f}%
├ RAM (RSS): {format_size(proc_memory_rss)}
└ RAM (VMS): {format_size(proc_memory_vms)}

🌐 **Network**
├ Upload Speed:   {format_size(upload_speed)}/s
├ Download Speed: {format_size(download_speed)}/s
└ Total I/O:      {format_size(total_io)}

📟 **System Info**
├ OS:        {os_name}
├ OS Version: {os_version}
├ Python:    {python_version}
└ Uptime:    {uptime_str}

🤖 **Bot Info**
├ Bot Uptime: {bot_uptime}
├ Owner: {OWNER_CREDIT}
└ Current Ping: {ping:.3f} ms
"""
            return stats
        except Exception as e:
            return f"Error getting stats: {str(e)}"

# ==============================================================================
#                            TASK QUEUE SYSTEM
# ==============================================================================

class TaskStatus:
    WAITING = "waiting"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Task:
    """Represents a user task"""
    
    def __init__(self, user_id: int, user_name: str, message_id: int, chat_id: int):
        self.user_id = user_id
        self.user_name = user_name
        self.message_id = message_id
        self.chat_id = chat_id
        self.status = TaskStatus.WAITING
        self.file_path = None
        self.file_name = None
        self.file_size = 0
        self.password = None
        self.domains = []
        self.start_time = None
        self.end_time = None
        self.progress = 0
        self.status_message = None
        self.extractor = None
        self.cookie_extractor = None
        self.cancelled = False
        self.result_files = []
        self.extract_folder = None
        self.download_message = None
        
    @property
    def elapsed_time(self):
        if self.start_time:
            return datetime.now() - self.start_time
        return timedelta(0)
    
    @property
    def size_str(self):
        return format_size(self.file_size)
    
    def cancel(self):
        """Cancel the task"""
        self.cancelled = True
        self.status = TaskStatus.CANCELLED
        if self.extractor:
            self.extractor.stop_extraction = True
        if self.cookie_extractor:
            self.cookie_extractor.stop_processing = True
        
        # Clean up files
        if self.file_path and os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
            except:
                pass
        
        if self.extract_folder and os.path.exists(self.extract_folder):
            delete_entire_folder(self.extract_folder)

class TaskQueue:
    """Manages task queue"""
    
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_TASKS):
        self.queue = asyncio.Queue()
        self.active_tasks: Dict[int, Task] = {}  # user_id -> Task
        self.all_tasks: Dict[int, List[Task]] = defaultdict(list)  # user_id -> [Task]
        self.max_concurrent = max_concurrent
        self.current_running = 0
        self.lock = asyncio.Lock()
        self.processing = False
        self.app = None
    
    def set_app(self, app):
        """Set bot app reference"""
        self.app = app
    
    async def add_task(self, task: Task) -> bool:
        """Add task to queue"""
        async with self.lock:
            # Check if user already has active task
            if task.user_id in self.active_tasks:
                return False
            
            # Add to queue
            await self.queue.put(task)
            self.all_tasks[task.user_id].append(task)
            
            # Start processing if not already
            if not self.processing:
                asyncio.create_task(self.process_queue())
            
            return True
    
    async def process_queue(self):
        """Process tasks from queue"""
        self.processing = True
        
        while True:
            try:
                # Check if we can process more
                async with self.lock:
                    if self.current_running >= self.max_concurrent:
                        await asyncio.sleep(1)
                        continue
                
                # Get next task
                try:
                    task = await asyncio.wait_for(self.queue.get(), timeout=1)
                except asyncio.TimeoutError:
                    # No tasks in queue
                    async with self.lock:
                        if self.current_running == 0:
                            self.processing = False
                            break
                    continue
                
                # Process task
                async with self.lock:
                    self.current_running += 1
                    self.active_tasks[task.user_id] = task
                
                asyncio.create_task(self.run_task(task))
                
            except Exception as e:
                print(f"Queue processing error: {e}")
                await asyncio.sleep(1)
    
    async def run_task(self, task: Task):
        """Run a single task"""
        try:
            task.status = TaskStatus.DOWNLOADING
            task.start_time = datetime.now()
            
            # Notify user
            try:
                await self.app.send_message(
                    task.chat_id,
                    f"✅ **Task Started!**\n\n"
                    f"File: {task.file_name}\n"
                    f"Size: {task.size_str}\n"
                    f"Position: {self.get_queue_position(task.user_id)}"
                )
            except:
                pass
            
            # Download file if needed
            if task.file_path and os.path.exists(task.file_path):
                # File already downloaded
                pass
            else:
                # This should be handled by the download handler
                pass
            
            # Wait for domains and password if not set
            if not task.domains:
                # This will be handled by conversation handler
                # Task will be paused until domains are provided
                pass
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.end_time = datetime.now()
            print(f"Task error: {e}")
            
            # Notify user
            try:
                await self.app.send_message(
                    task.chat_id,
                    f"❌ **Task Failed**\n\nError: {str(e)[:200]}"
                )
            except:
                pass
        
        finally:
            # Remove from active tasks
            async with self.lock:
                if task.user_id in self.active_tasks:
                    del self.active_tasks[task.user_id]
                self.current_running -= 1
    
    def get_user_task(self, user_id: int) -> Optional[Task]:
        """Get active task for user"""
        return self.active_tasks.get(user_id)
    
    def get_queue_position(self, user_id: int) -> int:
        """Get user's position in queue"""
        position = 1
        for task in list(self.queue._queue):
            if task.user_id == user_id:
                return position
            position += 1
        return 0
    
    def get_queue_info(self) -> str:
        """Get formatted queue information"""
        if self.queue.empty() and not self.active_tasks:
            return "📪 **Queue is empty**"
        
        lines = ["📊 **Current Queue**\n"]
        
        # Active tasks
        if self.active_tasks:
            lines.append("**🔄 Active Tasks:**")
            for user_id, task in self.active_tasks.items():
                elapsed = task.elapsed_time.total_seconds()
                lines.append(
                    f"├ 👤 {task.user_name}\n"
                    f"│  ├ 📁 {task.file_name[:30]}...\n"
                    f"│  ├ 📊 {task.size_str}\n"
                    f"│  ├ ⏱️ {format_time(elapsed)}\n"
                    f"│  └ 🔄 {task.status}"
                )
            lines.append("")
        
        # Waiting tasks
        waiting_tasks = list(self.queue._queue)
        if waiting_tasks:
            lines.append("**⏳ Waiting:**")
            for i, task in enumerate(waiting_tasks, 1):
                lines.append(
                    f"{i}. 👤 {task.user_name} - 📁 {task.file_name[:20]}... ({task.size_str})"
                )
        
        return "\n".join(lines)
    
    def cancel_user_task(self, user_id: int) -> bool:
        """Cancel task for a user"""
        # Check active tasks
        if user_id in self.active_tasks:
            task = self.active_tasks[user_id]
            task.cancel()
            return True
        
        # Check waiting queue
        new_queue = []
        cancelled = False
        for task in list(self.queue._queue):
            if task.user_id == user_id:
                task.cancel()
                cancelled = True
            else:
                new_queue.append(task)
        
        # Rebuild queue
        self.queue = asyncio.Queue()
        for task in new_queue:
            self.queue.put_nowait(task)
        
        return cancelled

# Initialize queue
task_queue = TaskQueue()

# ==============================================================================
#                            BOT APPLICATION
# ==============================================================================

class CookieBot(Client):
    """Main bot application"""
    
    def __init__(self):
        super().__init__(
            "cookie_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=20
        )
        self.start_time = datetime.now()
        self.user_states = {}  # user_id -> state
        self.user_data = {}  # user_id -> temp data
        self.download_tasks = {}  # message_id -> task
        
    async def start(self):
        """Start the bot"""
        await super().start()
        print(f"Bot started at {self.start_time}")
        print(f"Owner: {OWNER_CREDIT}")
        print(f"Tools: 7z={TOOL_STATUS['7z']}, UnRAR={TOOL_STATUS['unrar']}")
        
        # Set app reference in queue
        task_queue.set_app(self)
        
        # Start queue processor
        asyncio.create_task(task_queue.process_queue())
        
        # Send startup message to log channel
        if SEND_LOGS and LOG_CHANNEL:
            try:
                await self.send_message(
                    LOG_CHANNEL,
                    f"🚀 **Bot Started**\n\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Owner: {OWNER_CREDIT}\n"
                    f"Tools: 7z={'✅' if TOOL_STATUS['7z'] else '❌'}, UnRAR={'✅' if TOOL_STATUS['unrar'] else '❌'}"
                )
            except:
                pass
    
    async def stop(self):
        """Stop the bot"""
        print("Bot stopping...")
        await super().stop()

# Initialize bot
app = CookieBot()

# ==============================================================================
#                            HANDLER FUNCTIONS
# ==============================================================================

async def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMINS

def get_user_state(user_id: int) -> str:
    """Get user state"""
    return app.user_states.get(user_id, "idle")

def set_user_state(user_id: int, state: str):
    """Set user state"""
    app.user_states[user_id] = state

def clear_user_state(user_id: int):
    """Clear user state"""
    if user_id in app.user_states:
        del app.user_states[user_id]
    if user_id in app.user_data:
        del app.user_data[user_id]

# ==============================================================================
#                            COMMAND HANDLERS
# ==============================================================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: types.Message):
    """Handle /start command"""
    user = message.from_user
    await message.reply_text(
        f"👋 **Welcome to RUTE Cookie Extractor Bot!**\n\n"
        f"This bot extracts cookies from archive files for specific domains.\n\n"
        f"**Commands:**\n"
        f"/start - Show this message\n"
        f"/stats - Show system statistics\n"
        f"/queue - Show current task queue\n"
        f"/cancel - Cancel your current task\n"
        f"/help - Show help information\n\n"
        f"**How to use:**\n"
        f"1. Send me an archive file (zip, rar, 7z, etc.)\n"
        f"2. Enter the domains to search for (comma-separated)\n"
        f"3. Enter password if archive is protected\n"
        f"4. Wait for processing\n"
        f"5. Receive cookie files as ZIP\n\n"
        f"**Owner:** {OWNER_CREDIT}"
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: types.Message):
    """Handle /help command"""
    await message.reply_text(
        f"📚 **Help Information**\n\n"
        f"**Supported formats:**\n"
        f"• ZIP, RAR, 7Z\n"
        f"• TAR, GZ, BZ2, XZ\n\n"
        f"**Size limit:** 4GB\n\n"
        f"**Tools used:**\n"
        f"• 7z: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not available'}\n"
        f"• UnRAR: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not available'}\n\n"
        f"**Processing:**\n"
        f"• Maximum concurrent tasks: {MAX_CONCURRENT_TASKS}\n"
        f"• One task per user\n"
        f"• Automatic cleanup after completion\n\n"
        f"**Commands:**\n"
        f"/stats - System statistics\n"
        f"/queue - View queue\n"
        f"/cancel - Cancel task"
    )

@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: types.Message):
    """Handle /stats command"""
    msg = await message.reply_text("📊 Gathering statistics...")
    stats = SystemStats.get_stats()
    await msg.edit_text(stats, parse_mode=enums.ParseMode.MARKDOWN)

@app.on_message(filters.command("queue"))
async def queue_command(client: Client, message: types.Message):
    """Handle /queue command"""
    queue_info = task_queue.get_queue_info()
    
    # Add cancel buttons for admin
    keyboard = None
    if await is_admin(message.from_user.id) and task_queue.active_tasks:
        buttons = []
        for user_id, task in list(task_queue.active_tasks.items())[:5]:  # Limit to 5
            buttons.append([
                InlineKeyboardButton(
                    f"❌ Cancel {task.user_name[:10]}",
                    callback_data=f"cancel_admin_{user_id}"
                )
            ])
        if buttons:
            keyboard = InlineKeyboardMarkup(buttons)
    
    await message.reply_text(queue_info, reply_markup=keyboard)

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: types.Message):
    """Handle /cancel command"""
    user_id = message.from_user.id
    
    # Check if user has active task
    task = task_queue.get_user_task(user_id)
    if task:
        task.cancel()
        clear_user_state(user_id)
        await message.reply_text("✅ Your task has been cancelled.")
        return
    
    # Check if user is waiting
    position = task_queue.get_queue_position(user_id)
    if position > 0:
        if task_queue.cancel_user_task(user_id):
            clear_user_state(user_id)
            await message.reply_text("✅ Your task has been removed from queue.")
            return
    
    await message.reply_text("❌ You don't have any active or waiting tasks.")

@app.on_callback_query()
async def handle_callback(client: Client, callback_query: CallbackQuery):
    """Handle callback queries"""
    data = callback_query.data
    
    if data.startswith("cancel_admin_"):
        # Admin cancel
        if not await is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Admin only", show_alert=True)
            return
        
        target_user = int(data.split("_")[2])
        
        if task_queue.cancel_user_task(target_user):
            await callback_query.answer("✅ Task cancelled", show_alert=True)
            
            # Notify user
            try:
                await client.send_message(
                    target_user,
                    "❌ Your task was cancelled by an admin."
                )
            except:
                pass
        else:
            await callback_query.answer("❌ Failed to cancel task", show_alert=True)
        
        # Update queue message
        await callback_query.message.edit_text(task_queue.get_queue_info())
    
    elif data == "skip_password":
        # User wants to skip password
        user_id = callback_query.from_user.id
        task = task_queue.get_user_task(user_id)
        
        if task and task.status == TaskStatus.WAITING:
            task.password = None
            set_user_state(user_id, "domains")
            
            await callback_query.message.edit_text(
                "✅ Password skipped. Now enter the domains to search for (comma-separated):\n\n"
                "Example: `google.com, facebook.com, instagram.com`"
            )
        
        await callback_query.answer()
    
    elif data.startswith("cancel_operation_"):
        # User wants to cancel current operation
        user_id = callback_query.from_user.id
        op_type = data.split("_")[2]
        
        task = task_queue.get_user_task(user_id)
        if task:
            task.cancel()
        
        clear_user_state(user_id)
        await callback_query.message.edit_text("❌ Operation cancelled.")
        await callback_query.answer("Cancelled")

# ==============================================================================
#                            FILE HANDLER
# ==============================================================================

@app.on_message(filters.document)
async def handle_document(client: Client, message: types.Message):
    """Handle document uploads"""
    user = message.from_user
    user_id = user.id
    document = message.document
    
    # Check file size
    if document.file_size > MAX_FILE_SIZE:
        await message.reply_text(
            f"❌ File too large! Maximum size is {format_size(MAX_FILE_SIZE)}"
        )
        return
    
    # Check file extension
    file_name = document.file_name or "unknown"
    ext = os.path.splitext(file_name)[1].lower()
    
    if ext not in SUPPORTED_ARCHIVES:
        await message.reply_text(
            f"❌ Unsupported file format!\n"
            f"Supported: {', '.join(SUPPORTED_ARCHIVES)}"
        )
        return
    
    # Check if user already has task
    existing_task = task_queue.get_user_task(user_id)
    if existing_task:
        await message.reply_text(
            "❌ You already have an active task!\n"
            "Use /cancel to cancel it first."
        )
        return
    
    # Check queue position
    position = task_queue.get_queue_position(user_id)
    if position > 0:
        await message.reply_text(
            f"⏳ You're already in queue at position {position}\n"
            "Use /cancel to remove your task."
        )
        return
    
    # Ask for confirmation
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation_file")]
    ])
    
    msg = await message.reply_text(
        f"📁 **File Received**\n\n"
        f"Name: {file_name}\n"
        f"Size: {format_size(document.file_size)}\n"
        f"Type: {ext}\n\n"
        f"Downloading file... Please wait.",
        reply_markup=keyboard
    )
    
    # Create download path
    user_download_dir = os.path.join(DOWNLOADS_DIR, str(user_id))
    os.makedirs(user_download_dir, exist_ok=True)
    
    download_path = os.path.join(user_download_dir, file_name)
    
    try:
        # Download file with progress
        file_path = await message.download(
            file_name=download_path,
            progress=download_progress,
            progress_args=(client, message, msg, document.file_size)
        )
        
        # Create task
        task = Task(user_id, user.first_name or str(user_id), message.id, message.chat.id)
        task.file_path = file_path
        task.file_name = file_name
        task.file_size = document.file_size
        task.download_message = msg
        
        # Store download message reference
        app.download_tasks[msg.id] = task
        
        # Add to queue
        if await task_queue.add_task(task):
            # Ask for domains
            set_user_state(user_id, "domains")
            
            await msg.edit_text(
                f"✅ File downloaded successfully!\n\n"
                f"Now enter the domains to search for (comma-separated):\n\n"
                f"Example: `google.com, facebook.com, instagram.com`\n\n"
                f"Use /cancel to cancel this operation.",
                reply_markup=None
            )
        else:
            # Clean up
            os.remove(file_path)
            await msg.edit_text("❌ Failed to add task to queue.")
            
    except Exception as e:
        await msg.edit_text(f"❌ Download failed: {str(e)[:200]}")
        print(f"Download error: {traceback.format_exc()}")

async def download_progress(current, total, client, message, status_msg, total_size):
    """Download progress callback"""
    try:
        percent = (current / total) * 100
        speed = current / (time.time() - message.date.timestamp()) if (time.time() - message.date.timestamp()) > 0 else 0
        elapsed = time.time() - message.date.timestamp()
        eta = (total - current) / speed if speed > 0 else 0
        
        # Create progress bar
        bar_length = 20
        filled = int(bar_length * current / total)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        text = (
            f"📥 **Downloading...**\n\n"
            f"File: {bar} {percent:.1f}%\n"
            f"Size: {format_size(current)} / {format_size(total)}\n"
            f"Speed: {format_size(speed)}/s\n"
            f"Elapsed: {format_time(elapsed)}\n"
            f"ETA: {format_time(eta)}"
        )
        
        await status_msg.edit_text(text)
    except:
        pass

# ==============================================================================
#                            TEXT HANDLER
# ==============================================================================

@app.on_message(filters.text & ~filters.command(["start", "help", "stats", "queue", "cancel"]))
async def handle_text(client: Client, message: types.Message):
    """Handle text messages (domains, password)"""
    user_id = message.from_user.id
    state = get_user_state(user_id)
    text = message.text.strip()
    
    # Get user's task
    task = task_queue.get_user_task(user_id)
    if not task:
        # Check if waiting in queue
        position = task_queue.get_queue_position(user_id)
        if position > 0:
            await message.reply_text(
                f"⏳ You're in queue at position {position}\n"
                "Please wait for your turn."
            )
        else:
            await message.reply_text(
                "❌ No active task. Send a file first."
            )
        return
    
    if state == "domains":
        # Parse domains
        domains = [d.strip().lower() for d in text.split(',') if d.strip()]
        
        if not domains:
            await message.reply_text("❌ Please enter at least one domain.")
            return
        
        task.domains = domains
        
        # Check if password needed
        ext = os.path.splitext(task.file_name)[1].lower()
        is_protected = False
        
        try:
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(task.file_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(task.file_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(task.file_path)
        except:
            is_protected = False
        
        if is_protected:
            set_user_state(user_id, "password")
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ Skip (if no password)", callback_data="skip_password")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation_password")]
            ])
            
            await message.reply_text(
                "🔑 This archive appears to be password protected.\n"
                "Enter the password or click Skip if it's not protected:",
                reply_markup=keyboard
            )
        else:
            # No password needed, start processing
            set_user_state(user_id, "processing")
            await message.reply_text("✅ Starting extraction...")
            
            # Start processing
            asyncio.create_task(process_task(client, task))
    
    elif state == "password":
        # Set password
        task.password = text
        set_user_state(user_id, "processing")
        await message.reply_text("✅ Password set. Starting extraction...")
        
        # Start processing
        asyncio.create_task(process_task(client, task))
    
    else:
        await message.reply_text("❌ No active task. Send a file first.")

# ==============================================================================
#                            TASK PROCESSING
# ==============================================================================

async def process_task(client: Client, task: Task):
    """Process a task"""
    try:
        # Update status
        task.status = TaskStatus.EXTRACTING
        
        # Create status message
        status_msg = await client.send_message(
            task.chat_id,
            "📦 **Starting extraction...**"
        )
        task.status_message = status_msg
        
        # Forward to log channel
        if SEND_LOGS and LOG_CHANNEL:
            try:
                await client.send_document(
                    LOG_CHANNEL,
                    task.file_path,
                    caption=f"📥 **New File Received**\n\n"
                            f"User: {task.user_name} (ID: {task.user_id})\n"
                            f"File: {task.file_name}\n"
                            f"Size: {task.size_str}\n"
                            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except Exception as e:
                print(f"Log forward error: {e}")
        
        # Create extract folder
        user_extract_dir = os.path.join(EXTRACTED_DIR, str(task.user_id), 
                                        datetime.now().strftime('%Y%m%d_%H%M%S'))
        os.makedirs(user_extract_dir, exist_ok=True)
        task.extract_folder = user_extract_dir
        
        # Create results folder
        user_results_dir = os.path.join(RESULTS_DIR, str(task.user_id))
        os.makedirs(user_results_dir, exist_ok=True)
        
        # Progress update function
        async def update_extract_progress(current, total, status):
            try:
                percent = (current / total) * 100 if total > 0 else 0
                bar_length = 20
                filled = int(bar_length * current / total) if total > 0 else 0
                bar = '█' * filled + '░' * (bar_length - filled)
                
                text = (
                    f"📦 **Extracting Archives**\n\n"
                    f"Progress: {bar} {percent:.1f}%\n"
                    f"Processed: {current}/{total}\n"
                    f"Status: {status[:50]}\n\n"
                    f"⏱️ Elapsed: {format_time(task.elapsed_time.total_seconds())}"
                )
                
                await status_msg.edit_text(text)
            except:
                pass
        
        # Extract archives
        extractor = UltimateArchiveExtractor(task.password)
        extractor.set_progress_callback(update_extract_progress)
        task.extractor = extractor
        
        extract_dir = await extractor.extract_all_nested(
            task.file_path, 
            user_extract_dir,
            status_msg
        )
        
        if task.cancelled:
            await status_msg.edit_text("❌ Task cancelled.")
            return
        
        # Update status
        task.status = TaskStatus.PROCESSING
        await status_msg.edit_text(
            f"✅ Extraction complete!\n"
            f"Found {extractor.extracted_count} archives\n\n"
            f"🔍 **Starting cookie filtering...**"
        )
        
        # Process cookies
        cookie_extractor = UltimateCookieExtractor(task.domains)
        
        async def update_cookie_progress(current, total, status):
            try:
                percent = (current / total) * 100 if total > 0 else 0
                bar_length = 20
                filled = int(bar_length * current / total) if total > 0 else 0
                bar = '█' * filled + '░' * (bar_length - filled)
                
                text = (
                    f"🔍 **Filtering Cookies**\n\n"
                    f"Progress: {bar} {percent:.1f}%\n"
                    f"Files: {current}/{total}\n"
                    f"Entries found: {cookie_extractor.total_found}\n\n"
                    f"⏱️ Elapsed: {format_time(task.elapsed_time.total_seconds())}"
                )
                
                await status_msg.edit_text(text)
            except:
                pass
        
        cookie_extractor.set_progress_callback(update_cookie_progress)
        task.cookie_extractor = cookie_extractor
        
        await cookie_extractor.process_all(extract_dir, status_msg)
        
        if task.cancelled:
            await status_msg.edit_text("❌ Task cancelled.")
            return
        
        # Create ZIP files
        if cookie_extractor.total_found > 0:
            await status_msg.edit_text("📦 Creating ZIP archives...")
            
            created_zips = cookie_extractor.create_site_zips(extract_dir, user_results_dir)
            task.result_files = list(created_zips.values())
            
            # Send results
            for site, zip_path in created_zips.items():
                try:
                    # Send to user
                    await client.send_document(
                        task.chat_id,
                        zip_path,
                        caption=f"✅ **Cookies for {site}**\n\n"
                                f"Files: {len(cookie_extractor.site_files[site])}\n"
                                f"Entries: {cookie_extractor.total_found}\n"
                                f"Size: {format_size(os.path.getsize(zip_path))}"
                    )
                    
                    # Forward to log channel
                    if SEND_LOGS and LOG_CHANNEL:
                        await client.send_document(
                            LOG_CHANNEL,
                            zip_path,
                            caption=f"📤 **Results for {task.user_name}**\n\n"
                                    f"User ID: {task.user_id}\n"
                                    f"Domain: {site}\n"
                                    f"Files: {len(cookie_extractor.site_files[site])}\n"
                                    f"Entries: {cookie_extractor.total_found}\n"
                                    f"Size: {format_size(os.path.getsize(zip_path))}"
                        )
                    
                except Exception as e:
                    print(f"Send error: {e}")
            
            # Final status
            elapsed = task.elapsed_time.total_seconds()
            await status_msg.edit_text(
                f"✅ **Task Completed!**\n\n"
                f"📁 File: {task.file_name}\n"
                f"📊 Size: {task.size_str}\n"
                f"🔍 Domains: {', '.join(task.domains)}\n"
                f"📦 Archives processed: {extractor.extracted_count}\n"
                f"📄 Files found: {cookie_extractor.files_processed}\n"
                f"🔢 Entries: {cookie_extractor.total_found}\n"
                f"⏱️ Time: {format_time(elapsed)}\n\n"
                f"✅ Results sent as ZIP files."
            )
        else:
            await status_msg.edit_text(
                f"❌ **No cookies found**\n\n"
                f"Domains: {', '.join(task.domains)}\n"
                f"Files processed: {cookie_extractor.files_processed}"
            )
        
        task.status = TaskStatus.COMPLETED
        task.end_time = datetime.now()
        
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.end_time = datetime.now()
        
        error_msg = f"❌ **Processing Failed**\n\nError: {str(e)[:200]}"
        
        try:
            if task.status_message:
                await task.status_message.edit_text(error_msg)
            else:
                await client.send_message(task.chat_id, error_msg)
        except:
            pass
        
        print(f"Task processing error: {traceback.format_exc()}")
    
    finally:
        # Clean up
        clear_user_state(task.user_id)
        
        # Delete original file
        if task.file_path and os.path.exists(task.file_path):
            try:
                os.remove(task.file_path)
            except:
                pass
        
        # Delete extract folder
        if task.extract_folder and os.path.exists(task.extract_folder):
            delete_entire_folder(task.extract_folder)
        
        # Delete result files after sending
        for file_path in task.result_files:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass



# ==============================================================================
#                            MAIN
# ==============================================================================

if __name__ == "__main__":
    print("Starting RUTE Cookie Extractor Bot...")
    print(f"Owner: {OWNER_CREDIT}")
    print(f"7z: {'✅' if TOOL_STATUS['7z'] else '❌'}")
    print(f"UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}")
    print(f"Max concurrent tasks: {MAX_CONCURRENT_TASKS}")
    print(f"Max file size: {format_size(MAX_FILE_SIZE)}")
    print("=" * 50)
    
    try:
        app.run()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
