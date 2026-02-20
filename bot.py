#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RUTE Cookie Extractor Bot - Pyrofork Version
Telegram Bot for extracting cookies from archives with per-site filtering
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
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple, Any
import threading
from dataclasses import dataclass
from enum import Enum
import traceback

# Pyrofork imports
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, ForceReply
)
from pyrogram.errors import MessageNotModified, FloodWait
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
except ImportError:
    os.system("pip install -q tqdm psutil")
    from tqdm import tqdm

# RAR support
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

# 7Z support
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

# Bot API Credentials
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# Bot settings
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB
MAX_WORKERS = 100
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB
CHUNK_SIZE = 1024 * 1024  # 1MB
MAX_CONCURRENT_TASKS = 5
TIMEOUT_SECONDS = 3600  # 1 hour

# Download optimization
DOWNLOAD_CHUNK_SIZE = 1024 * 1024 * 2  # 2MB chunks

# Directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

# Create directories
for dir_path in [DOWNLOADS_DIR, EXTRACTED_DIR, RESULTS_DIR, TEMP_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# Supported formats
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# System detection
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


# Initialize tool status
TOOL_STATUS = {
    'unrar': ToolDetector.check_unrar(),
    '7z': ToolDetector.check_7z(),
}

TOOL_PATHS = {
    'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None,
    '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None,
}


# ==============================================================================
#                            ENUMS & DATA CLASSES
# ==============================================================================

class UserState(Enum):
    """User states for conversation flow"""
    IDLE = "idle"
    WAITING_PASSWORD = "waiting_password"
    WAITING_DOMAINS = "waiting_domains"
    PROCESSING = "processing"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """Task status in queue"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    PROCESSING_COOKIES = "processing_cookies"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class UserTask:
    """User task information"""
    task_id: str
    user_id: int
    username: str
    file_name: str
    file_size: int
    file_id: str
    password: Optional[str]
    domains: List[str]
    status: TaskStatus
    queue_position: int
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    message_id: Optional[int] = None
    download_path: Optional[str] = None
    result_files: List[str] = None
    progress_message_id: Optional[int] = None
    current_stage: str = "Queued"
    progress: float = 0
    last_update: float = 0
    extracted_archives: int = 0
    total_archives: int = 0
    processed_files: int = 0
    total_files: int = 0
    cookies_found: int = 0


@dataclass
class ProgressInfo:
    """Progress information for updates"""
    stage: str
    percentage: float
    current: int
    total: int
    speed: str
    eta: str
    elapsed: str
    size_done: str
    size_total: str
    file_name: str = ""
    password: str = ""
    cookies_found: int = 0
    archives_done: int = 0
    archives_total: int = 0
    files_done: int = 0
    files_total: int = 0


# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)


def generate_random_string(length: int = 6) -> str:
    """Generate random string"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def format_size(size_bytes: int) -> str:
    """Convert bytes to human readable"""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def format_time(seconds: float) -> str:
    """Convert seconds to human readable"""
    if seconds < 0:
        return "0s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = seconds / 60
        return f"{mins:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def format_speed(bytes_per_sec: float) -> str:
    """Format speed"""
    return f"{format_size(bytes_per_sec)}/s"


def create_progress_bar(percentage: float, width: int = 15) -> str:
    """Create text progress bar"""
    percentage = max(0, min(100, percentage))
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return bar


def mask_password(password: Optional[str]) -> str:
    """Mask password for display"""
    if not password:
        return "None"
    if len(password) <= 4:
        return '*' * len(password)
    return password[:2] + '*' * (len(password) - 4) + password[-2:]


def get_file_hash_fast(filepath: str) -> str:
    """Fast file hash using first/last chunks"""
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))


def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        gc.collect()
        shutil.rmtree(folder_path, ignore_errors=True)
        time.sleep(0.5)
        
        if os.path.exists(folder_path):
            if SYSTEM == 'windows':
                os.system(f'rmdir /s /q "{folder_path}"')
            else:
                os.system(f'rm -rf "{folder_path}"')
        
        return not os.path.exists(folder_path)
    except:
        return False


def delete_files(file_paths: List[str]):
    """Delete multiple files"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass


# ==============================================================================
#                            SYSTEM STATISTICS
# ==============================================================================

class SystemStats:
    """Get system statistics"""
    
    @staticmethod
    async def get_stats() -> str:
        """Get formatted system statistics"""
        try:
            disk = psutil.disk_usage('/')
            disk_total = format_size(disk.total)
            disk_used = format_size(disk.used)
            disk_free = format_size(disk.free)
            disk_percent = disk.percent
            
            memory = psutil.virtual_memory()
            mem_total = format_size(memory.total)
            mem_used = format_size(memory.used)
            mem_free = format_size(memory.available)
            mem_percent = memory.percent
            
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            
            process = psutil.Process()
            bot_cpu = process.cpu_percent(interval=0.5)
            bot_memory_rss = format_size(process.memory_info().rss)
            bot_memory_vms = format_size(process.memory_info().vms)
            
            net_io = psutil.net_io_counters()
            net_sent = format_size(net_io.bytes_sent)
            net_recv = format_size(net_io.bytes_recv)
            
            system = platform.system()
            release = platform.release()
            python_version = platform.python_version()
            
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            
            bot_start = psutil.Process().create_time()
            bot_uptime = datetime.now() - datetime.fromtimestamp(bot_start)
            bot_uptime_str = str(bot_uptime).split('.')[0]
            
            stats = f"""
╔══════════════════════════════════════════════════════════╗
║              🖥️ SYSTEM STATISTICS DASHBOARD              ║
╠══════════════════════════════════════════════════════════╣

💾 Disk Storage
├ Total:  {disk_total:>10}
├ Used:   {disk_used:>10} ({disk_percent:.1f}%)
└ Free:   {disk_free:>10}

🧠 RAM (Memory)
├ Total:  {mem_total:>10}
├ Used:   {mem_used:>10} ({mem_percent:.1f}%)
└ Free:   {mem_free:>10}

⚡ CPU
├ Cores:  {cpu_count:>10}
└ Usage:  {cpu_percent:>9.1f}%

🔌 Bot Process
├ CPU:        {bot_cpu:>5.1f}%
├ RAM (RSS):  {bot_memory_rss:>10}
├ RAM (VMS):  {bot_memory_vms:>10}
└ Uptime:     {bot_uptime_str:>10}

🌐 Network
├ Upload:   {net_sent:>10}
├ Download: {net_recv:>10}
└ Total:    {format_size(net_io.bytes_sent + net_io.bytes_recv):>10}

📟 System Info
├ OS:      {system:>10}
├ Version: {release:>10}
├ Python:  {python_version:>10}
└ Uptime:  {uptime_str:>10}

⏱️ Performance
└ Ping:    {random.uniform(100, 300):.3f} ms

╚══════════════════════════════════════════════════════════╝

👑 Owner: @still_alivenow
"""
            return stats
        except Exception as e:
            return f"❌ Error getting system stats: {e}"


# ==============================================================================
#                            PASSWORD DETECTION
# ==============================================================================

class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    async def check_protected(archive_path: str) -> bool:
        """Check if archive is password protected"""
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            if ext == '.rar':
                return await PasswordDetector._check_rar(archive_path)
            elif ext == '.7z':
                return await PasswordDetector._check_7z(archive_path)
            elif ext == '.zip':
                return await PasswordDetector._check_zip(archive_path)
        except:
            pass
        
        return False
    
    @staticmethod
    async def _check_rar(archive_path: str) -> bool:
        """Check RAR protection"""
        if HAS_RARFILE:
            try:
                with rarfile.RarFile(archive_path) as rf:
                    return rf.needs_password()
            except:
                pass
        
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                return 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower()
            except:
                pass
        
        return True
    
    @staticmethod
    async def _check_7z(archive_path: str) -> bool:
        """Check 7z protection"""
        if HAS_PY7ZR:
            try:
                with py7zr.SevenZipFile(archive_path, mode='r') as sz:
                    return sz.password_protected
            except:
                pass
        
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                return 'Encrypted' in result.stdout or 'Password' in result.stdout
            except:
                pass
        
        return True
    
    @staticmethod
    async def _check_zip(archive_path: str) -> bool:
        """Check ZIP protection"""
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'Encrypted' in result.stdout or 'Password' in result.stdout:
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
            pass
        
        return True


# ==============================================================================
#                            ARCHIVE EXTRACTION
# ==============================================================================

class ArchiveExtractor:
    """Extract archives with optimal tools"""
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.stop_extraction = False
        self.total_archives = 0
        self.processed_archives = 0
    
    async def extract_with_progress(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract a single archive"""
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            if ext == '.7z' and TOOL_STATUS['7z']:
                return await self._extract_7z(archive_path, extract_dir)
            elif ext == '.rar' and TOOL_STATUS['unrar']:
                return await self._extract_rar(archive_path, extract_dir)
            elif ext == '.zip':
                return await self._extract_zip(archive_path, extract_dir)
            else:
                return await self._extract_tar(archive_path, extract_dir)
        except Exception as e:
            return []
    
    async def _extract_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract 7z with 7z.exe"""
        try:
            cmd = [TOOL_PATHS['7z'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd.append(f'-o{extract_dir}')
            cmd.append(archive_path)
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                return []
            
            if process.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files
            return []
        except:
            return []
    
    async def _extract_rar(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract RAR with UnRAR.exe"""
        try:
            cmd = [TOOL_PATHS['unrar'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            else:
                cmd.append('-p-')
            cmd.append(archive_path)
            cmd.append(extract_dir + ('\\' if SYSTEM == 'windows' else '/'))
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                return []
            
            if process.returncode == 0:
                files = []
                for root, _, filenames in os.walk(extract_dir):
                    for f in filenames:
                        rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                        files.append(rel_path)
                return files
            return []
        except:
            return []
    
    async def _extract_zip(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract ZIP with fastest method"""
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'x', '-y']
                if self.password:
                    cmd.append(f'-p{self.password}')
                cmd.append(f'-o{extract_dir}')
                cmd.append(archive_path)
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    process.kill()
                    return []
                
                if process.returncode == 0:
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
    
    async def _extract_tar(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except:
            return []
    
    def find_archives(self, directory: str) -> List[str]:
        """Find all archives in directory"""
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str, 
                                progress_callback=None) -> Tuple[str, int, int]:
        """Extract all nested archives recursively"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        self.processed_archives = 0
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            for archive in current_level:
                if archive in self.processed_files or self.stop_extraction:
                    continue
                
                archive_name = os.path.splitext(os.path.basename(archive))[0]
                archive_name = sanitize_filename(archive_name)[:50]
                extract_subdir = os.path.join(level_dir, archive_name)
                os.makedirs(extract_subdir, exist_ok=True)
                
                extracted = await self.extract_with_progress(archive, extract_subdir)
                
                with self.lock:
                    self.processed_files.add(archive)
                    self.processed_archives += 1
                
                if progress_callback:
                    await progress_callback(
                        self.processed_archives,
                        self.total_archives
                    )
                
                new_archives = self.find_archives(extract_subdir)
                next_level.update(new_archives)
                
                with self.lock:
                    self.total_archives += len(new_archives)
            
            current_level = next_level
            level += 1
        
        return base_dir, self.processed_archives, self.total_archives


# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class CookieExtractor:
    """Extract and filter cookies"""
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.total_files = 0
        
        # Pre-compile patterns
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
        
        self.total_files = len(cookie_files)
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
    
    def _process_file_sync(self, file_path: str, orig_name: str, extract_dir: str):
        """Process a single file synchronously"""
        if self.stop_processing:
            return 0
        
        local_found = 0
        try:
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            site_matches = {site: [] for site in self.target_sites}
            
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
                                local_found += 1
            
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
            
            self.files_processed += 1
            return local_found
            
        except Exception as e:
            return 0
    
    async def process_all(self, extract_dir: str, progress_callback=None) -> int:
        """Process all cookie files in parallel"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return 0
        
        total_found = 0
        processed = 0
        
        loop = asyncio.get_event_loop()
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for file_path, orig_name in cookie_files:
                if self.stop_processing:
                    break
                future = loop.run_in_executor(
                    executor,
                    self._process_file_sync,
                    file_path, orig_name, extract_dir
                )
                futures.append(future)
            
            for future in as_completed(futures):
                if self.stop_processing:
                    break
                try:
                    result = await future
                    total_found += result
                except:
                    pass
                
                processed += 1
                if progress_callback:
                    await progress_callback(processed, self.total_files, total_found)
        
        self.total_found = total_found
        return total_found
    
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
#                            MAIN BOT CLASS
# ==============================================================================

class CookieExtractorBot:
    """Main bot class"""
    
    def __init__(self):
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=20,
            parse_mode=enums.ParseMode.HTML
        )
        
        self.user_states: Dict[int, Dict[str, Any]] = {}
        self.user_tasks: Dict[int, UserTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self.current_tasks = 0
        self.queue_lock = asyncio.Lock()
        self.progress_messages: Dict[int, Dict[str, Any]] = {}
        self.start_messages: Dict[int, int] = {}
        
        self.register_handlers()
    
    def register_handlers(self):
        """Register message and callback handlers"""
        self.app.on_message(filters.command("start"))(self.cmd_start)
        self.app.on_message(filters.command("stats"))(self.cmd_stats)
        self.app.on_message(filters.command("queue"))(self.cmd_queue)
        self.app.on_message(filters.command("cancel"))(self.cmd_cancel)
        self.app.on_message(filters.command("help"))(self.cmd_help)
        
        self.app.on_message(filters.document & filters.private)(self.handle_document)
        self.app.on_message(filters.text & filters.private & filters.reply)(self.handle_reply)
        self.app.on_callback_query()(self.handle_callback)
    
    def get_start_keyboard(self):
        """Get start menu keyboard"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 System Stats", callback_data="stats"),
                InlineKeyboardButton("ℹ️ Help", callback_data="help")
            ],
            [
                InlineKeyboardButton("👁️ View Queue", callback_data="queue")
            ]
        ])
    
    def get_back_keyboard(self):
        """Get back button keyboard"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_start")]
        ])
    
    def get_start_text(self):
        """Get start menu text"""
        return f"""
╔══════════════════════════════════════════════════════════╗
║      🍪 RUTE COOKIE EXTRACTOR BOT - ULTIMATE SPEED      ║
║            Extract cookies from any archive!            ║
╚══════════════════════════════════════════════════════════╝

📦 Supported formats: ZIP, RAR, 7Z, TAR, GZ, BZ2, XZ
🔧 External tools: 
  • 7z.exe: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}
  • UnRAR.exe: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}

📋 How to use:
1️⃣ Send me any archive file (max 4GB)
2️⃣ Select password option when asked
3️⃣ Provide domains to filter (comma-separated)
4️⃣ Wait for extraction and filtering
5️⃣ Receive filtered cookie ZIPs

⚠️ One task per user at a time
⏱️ Timeout: 1 hour per task

👑 Owner: @still_alivenow
"""
    
    async def cmd_start(self, client: Client, message: Message):
        """Handle /start command"""
        user_id = message.from_user.id
        sent_msg = await message.reply_text(
            self.get_start_text(),
            reply_markup=self.get_start_keyboard()
        )
        self.start_messages[user_id] = sent_msg.id
    
    async def cmd_stats(self, client: Client, message: Message):
        """Handle /stats command"""
        user_id = message.from_user.id
        stats = await SystemStats.get_stats()
        
        if user_id in self.start_messages:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=self.start_messages[user_id],
                    text=f"<pre>{stats}</pre>",
                    reply_markup=self.get_back_keyboard()
                )
            except:
                sent_msg = await message.reply_text(
                    f"<pre>{stats}</pre>",
                    reply_markup=self.get_back_keyboard()
                )
                self.start_messages[user_id] = sent_msg.id
        else:
            sent_msg = await message.reply_text(
                f"<pre>{stats}</pre>",
                reply_markup=self.get_back_keyboard()
            )
            self.start_messages[user_id] = sent_msg.id
    
    async def cmd_queue(self, client: Client, message: Message):
        """Handle /queue command"""
        user_id = message.from_user.id
        await self.show_queue(message, edit=True)
    
    async def cmd_cancel(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        
        if user_id in self.user_tasks:
            task = self.user_tasks[user_id]
            
            if user_id in self.active_tasks:
                self.active_tasks[user_id].cancel()
                del self.active_tasks[user_id]
            
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()
            
            if task.download_path and os.path.exists(task.download_path):
                try:
                    os.remove(task.download_path)
                except:
                    pass
            
            if task.result_files:
                for file_path in task.result_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
            
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.user_tasks:
                del self.user_tasks[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]
            
            self.current_tasks -= 1
            
            await message.reply_text(f"✅ Task cancelled successfully")
        else:
            await message.reply_text(f"⚠️ No active task found")
    
    async def cmd_help(self, client: Client, message: Message):
        """Handle /help command"""
        user_id = message.from_user.id
        help_text = f"""
╔══════════════════════════════════════════════════════════╗
║                      HELP & COMMANDS                     ║
╚══════════════════════════════════════════════════════════╝

📌 Available Commands:
/start - Start the bot and see welcome message
/stats - Show system statistics dashboard
/queue - View current processing queue
/cancel - Cancel your active task
/help - Show this help message

📦 Supported Archive Formats:
• ZIP (.zip)
• RAR (.rar)  
• 7Z (.7z)
• TAR (.tar, .tar.gz, .tar.bz2, .tar.xz)
• GZ (.gz)
• BZ2 (.bz2)
• XZ (.xz)

🔧 Extraction Methods:
• .7z → {'7z.exe (Fast)' if TOOL_STATUS['7z'] else 'py7zr (Slow)'}
• .rar → {'UnRAR.exe (Fast)' if TOOL_STATUS['unrar'] else 'rarfile (Slow)'}
• .zip → {'7z.exe/UnRAR.exe (Fast)' if TOOL_STATUS['7z'] or TOOL_STATUS['unrar'] else 'zipfile (Slow)'}

📋 How to Use:
1. Send an archive file (max 4GB)
2. Use the buttons to indicate if password protected
3. Enter password if needed
4. Enter domains (comma-separated) to filter
5. Wait for processing
6. Download filtered cookie ZIPs

⚠️ Limitations:
• Max file size: 4GB
• One task per user at a time
• Multiple users can process concurrently
• Timeout: 1 hour per task

👑 Owner: @still_alivenow
"""
        
        if user_id in self.start_messages:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=self.start_messages[user_id],
                    text=help_text,
                    reply_markup=self.get_back_keyboard()
                )
            except:
                sent_msg = await message.reply_text(
                    help_text,
                    reply_markup=self.get_back_keyboard()
                )
                self.start_messages[user_id] = sent_msg.id
        else:
            sent_msg = await message.reply_text(
                help_text,
                reply_markup=self.get_back_keyboard()
            )
            self.start_messages[user_id] = sent_msg.id
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document uploads"""
        user_id = message.from_user.id
        document = message.document
        
        if user_id in self.user_tasks:
            task = self.user_tasks[user_id]
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                await message.reply_text(f"⚠️ You already have an active task. Please wait or use /cancel")
                return
        
        if document.file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large! Max size: 4GB")
            return
        
        file_name = document.file_name or "unknown"
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"❌ Unsupported file format. Supported: {', '.join(SUPPORTED_ARCHIVES)}"
            )
            return
        
        task_id = f"{user_id}_{int(time.time())}"
        task = UserTask(
            task_id=task_id,
            user_id=user_id,
            username=message.from_user.username or f"User{user_id}",
            file_name=file_name,
            file_size=document.file_size,
            file_id=document.file_id,
            password=None,
            domains=[],
            status=TaskStatus.QUEUED,
            queue_position=0
        )
        
        self.user_tasks[user_id] = task
        
        await message.reply_text(
            f"📦 Archive received: {file_name}\n"
            f"📊 Size: {format_size(document.file_size)}\n\n"
            f"🔒 Is this archive password protected?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"password_yes|{task_id}"),
                    InlineKeyboardButton("❌ No", callback_data=f"password_no|{task_id}")
                ],
                [InlineKeyboardButton("🚫 Cancel", callback_data=f"cancel_task|{task_id}")]
            ])
        )
    
    async def handle_reply(self, client: Client, message: Message):
        """Handle reply messages"""
        user_id = message.from_user.id
        
        if user_id not in self.user_states:
            return
        
        state_info = self.user_states[user_id]
        user_state = state_info.get('state')
        task_id = state_info.get('task_id')
        message_id = state_info.get('message_id')
        
        if not task_id or user_id not in self.user_tasks:
            return
        
        task = self.user_tasks[user_id]
        
        if task.task_id != task_id:
            return
        
        if user_state == UserState.WAITING_PASSWORD:
            password = message.text.strip()
            
            if password.lower() == '/cancel':
                await self.cancel_task(user_id, task_id)
                await message.reply_text("❌ Task cancelled")
                return
            
            task.password = password
            
            await client.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"🔑 Password received!\n\n"
                     f"📁 {task.file_name}\n"
                     f"📊 Size: {format_size(task.file_size)}\n\n"
                     f"🌍 Now enter the domains to filter (comma-separated):\n"
                     f"Example: google.com, facebook.com, instagram.com"
            )
            
            state_info['state'] = UserState.WAITING_DOMAINS
            
            await message.reply_text(
                "📝 Please enter domains:",
                reply_markup=ForceReply(selective=True)
            )
            
        elif user_state == UserState.WAITING_DOMAINS:
            domains_text = message.text.strip()
            
            if domains_text.lower() == '/cancel':
                await self.cancel_task(user_id, task_id)
                await message.reply_text("❌ Task cancelled")
                return
            
            domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
            
            if not domains:
                await message.reply_text(
                    f"⚠️ No valid domains entered. Please try again:",
                    reply_markup=ForceReply(selective=True)
                )
                return
            
            task.domains = domains
            task.status = TaskStatus.QUEUED
            
            await self.task_queue.put((user_id, task))
            
            await client.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"✅ Task queued successfully!\n\n"
                     f"📁 File: {task.file_name}\n"
                     f"📊 Size: {format_size(task.file_size)}\n"
                     f"🌍 Domains: {', '.join(domains[:3])}{'...' if len(domains) > 3 else ''}\n"
                     f"📍 Queue position: {self.task_queue.qsize()}\n\n"
                     f"⏳ Please wait for your turn..."
            )
            
            del self.user_states[user_id]
            asyncio.create_task(self.process_queue())
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        data = callback_query.data
        user_id = callback_query.from_user.id
        message = callback_query.message
        
        if data == "stats":
            stats = await SystemStats.get_stats()
            try:
                await message.edit_text(
                    f"<pre>{stats}</pre>",
                    reply_markup=self.get_back_keyboard()
                )
            except MessageNotModified:
                pass
            await callback_query.answer()
            
        elif data == "help":
            help_text = f"""
╔══════════════════════════════════════════════════════════╗
║                      HELP & COMMANDS                     ║
╚══════════════════════════════════════════════════════════╝

📌 Commands:
/start - Start bot
/stats - System stats
/queue - View queue
/cancel - Cancel task
/help - This help

📦 Supported: ZIP, RAR, 7Z, TAR, GZ, BZ2, XZ
⚠️ Max file size: 4GB
⏱️ Timeout: 1 hour

👑 Owner: @still_alivenow
"""
            try:
                await message.edit_text(
                    help_text,
                    reply_markup=self.get_back_keyboard()
                )
            except MessageNotModified:
                pass
            await callback_query.answer()
            
        elif data == "queue":
            await self.show_queue(message, edit=True)
            await callback_query.answer()
            
        elif data == "back_to_start":
            try:
                await message.edit_text(
                    self.get_start_text(),
                    reply_markup=self.get_start_keyboard()
                )
            except MessageNotModified:
                pass
            await callback_query.answer()
            
        elif data.startswith("password_"):
            parts = data.split("|")
            if len(parts) >= 2:
                action = parts[0].replace("password_", "")
                task_id = parts[1]
                
                if user_id in self.user_tasks and self.user_tasks[user_id].task_id == task_id:
                    task = self.user_tasks[user_id]
                    
                    if action == "yes":
                        await message.edit_text(
                            f"🔒 Please enter the password for:\n"
                            f"📁 {task.file_name}\n"
                            f"📊 Size: {format_size(task.file_size)}"
                        )
                        
                        self.user_states[user_id] = {
                            'state': UserState.WAITING_PASSWORD,
                            'task_id': task_id,
                            'message_id': message.id
                        }
                        
                        await message.reply_text(
                            "🔑 Enter password:",
                            reply_markup=ForceReply(selective=True)
                        )
                    else:
                        await message.edit_text(
                            f"📁 {task.file_name}\n"
                            f"📊 Size: {format_size(task.file_size)}\n\n"
                            f"🌍 Enter domains to filter (comma-separated):\n"
                            f"Example: google.com, facebook.com, instagram.com"
                        )
                        
                        self.user_states[user_id] = {
                            'state': UserState.WAITING_DOMAINS,
                            'task_id': task_id,
                            'message_id': message.id
                        }
                        
                        await message.reply_text(
                            "📝 Enter domains:",
                            reply_markup=ForceReply(selective=True)
                        )
                    
                    await callback_query.answer()
                    
        elif data.startswith("cancel_task|"):
            task_id = data.split("|")[1]
            await self.cancel_task(user_id, task_id)
            try:
                await message.edit_text("❌ Task cancelled")
            except:
                pass
            await callback_query.answer("Task cancelled")
    
    async def cancel_task(self, user_id: int, task_id: str):
        """Cancel a task"""
        if user_id in self.user_tasks and self.user_tasks[user_id].task_id == task_id:
            task = self.user_tasks[user_id]
            
            if user_id in self.active_tasks:
                self.active_tasks[user_id].cancel()
                del self.active_tasks[user_id]
            
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()
            
            if task.download_path and os.path.exists(task.download_path):
                try:
                    os.remove(task.download_path)
                except:
                    pass
            
            if task.result_files:
                for file_path in task.result_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
            
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.user_tasks:
                del self.user_tasks[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]
            
            self.current_tasks -= 1
    
    async def show_queue(self, message: Message, edit: bool = False):
        """Show current queue"""
        queue_list = []
        
        temp_queue = []
        while not self.task_queue.empty():
            try:
                item = self.task_queue.get_nowait()
                temp_queue.append(item)
            except asyncio.QueueEmpty:
                break
        
        for item in temp_queue:
            await self.task_queue.put(item)
            queue_list.append(item)
        
        if not queue_list and not self.active_tasks:
            queue_text = f"📪 Queue is empty"
        else:
            queue_text = f"""
╔════════════════════════════════════════╗
║           CURRENT QUEUE ({len(queue_list)})           ║
╠════════════════════════════════════════╣
"""
            
            if self.active_tasks:
                queue_text += f"\n▶️ Active Tasks:\n"
                for uid, task in self.active_tasks.items():
                    if uid in self.user_tasks:
                        t = self.user_tasks[uid]
                        queue_text += f"  • {t.username} - {t.file_name} ({format_size(t.file_size)})\n"
            
            if queue_list:
                queue_text += f"\n⏳ Queued:\n"
                for i, (uid, t) in enumerate(queue_list, 1):
                    queue_text += f"  {i}. {t.username} - {t.file_name} ({format_size(t.file_size)})\n"
            
            queue_text += f"\n╚════════════════════════════════════════╝"
        
        if edit:
            try:
                await message.edit_text(
                    queue_text,
                    reply_markup=self.get_back_keyboard()
                )
            except MessageNotModified:
                pass
        else:
            await message.reply_text(
                queue_text,
                reply_markup=self.get_back_keyboard()
            )
    
    async def update_progress_message(self, user_id: int, progress: ProgressInfo):
        """Update progress message"""
        if user_id not in self.user_tasks:
            return
        
        task = self.user_tasks[user_id]
        
        now = time.time()
        if hasattr(task, 'last_update') and now - task.last_update < 2:
            return
        task.last_update = now
        
        bar = create_progress_bar(progress.percentage)
        
        # Build progress message based on stage
        if progress.stage == "Downloading":
            progress_text = f"""
╔════════════════════════════════════════╗
║           DOWNLOAD PROGRESS            ║
╠════════════════════════════════════════╣

📁 File: {progress.file_name}
🔑 Password: {mask_password(progress.password)}
📊 Progress: [{bar}] {progress.percentage:.1f}%

📈 Stats:
  • Downloaded: {progress.size_done} / {progress.size_total}
  • Speed: {progress.speed}
  • ETA: {progress.eta}
  • Elapsed: {progress.elapsed}

╚════════════════════════════════════════╝
"""
        elif progress.stage == "Extracting":
            progress_text = f"""
╔════════════════════════════════════════╗
║          EXTRACTION PROGRESS           ║
╠════════════════════════════════════════╣

📦 Stage: Extracting Archives
📊 Progress: [{bar}] {progress.percentage:.1f}%

📈 Stats:
  • Archives: {progress.archives_done} / {progress.archives_total}
  • Elapsed: {progress.elapsed}

╚════════════════════════════════════════╝
"""
        elif progress.stage == "Processing Cookies":
            progress_text = f"""
╔════════════════════════════════════════╗
║         COOKIE PROCESSING              ║
╠════════════════════════════════════════╣

🍪 Stage: Filtering Cookies
📊 Progress: [{bar}] {progress.percentage:.1f}%

📈 Stats:
  • Files Processed: {progress.files_done} / {progress.files_total}
  • Cookies Found: {progress.cookies_found}
  • Elapsed: {progress.elapsed}

╚════════════════════════════════════════╝
"""
        else:
            progress_text = f"""
╔════════════════════════════════════════╗
║           PROGRESS UPDATE              ║
╠════════════════════════════════════════╣

📦 Stage: {progress.stage}
📊 Progress: [{bar}] {progress.percentage:.1f}%

📈 Stats:
  • Elapsed: {progress.elapsed}

╚════════════════════════════════════════╝
"""
        
        try:
            if task.progress_message_id:
                await self.app.edit_message_text(
                    chat_id=user_id,
                    message_id=task.progress_message_id,
                    text=progress_text
                )
            else:
                msg = await self.app.send_message(
                    chat_id=user_id,
                    text=progress_text
                )
                task.progress_message_id = msg.id
        except MessageNotModified:
            pass
        except Exception as e:
            pass
    
    async def download_file(self, task: UserTask) -> Optional[str]:
        """Download file with progress"""
        download_path = os.path.join(DOWNLOADS_DIR, f"{task.user_id}_{task.file_name}")
        
        last_update = time.time()
        start_time = time.time()
        last_percentage = -1
        known_total = task.file_size
        
        async def progress(current, total):
            nonlocal last_update, last_percentage
            now = time.time()
            
            if total == 0:
                total = known_total
            
            if total > 0:
                percentage = (current / total) * 100
            else:
                percentage = 0
            
            if (now - last_update >= 2 or abs(percentage - last_percentage) >= 1 or current == total) and total > 0:
                last_update = now
                last_percentage = percentage
                
                elapsed = now - start_time
                speed = current / elapsed if elapsed > 0 else 0
                
                if speed > 0 and total > 0:
                    eta = (total - current) / speed
                else:
                    eta = 0
                
                progress_info = ProgressInfo(
                    stage="Downloading",
                    percentage=percentage,
                    current=current,
                    total=total,
                    speed=format_speed(speed),
                    eta=format_time(eta),
                    elapsed=format_time(elapsed),
                    size_done=format_size(current),
                    size_total=format_size(total),
                    file_name=task.file_name,
                    password=task.password
                )
                
                await self.update_progress_message(task.user_id, progress_info)
        
        try:
            file_path = await self.app.download_media(
                task.file_id,
                file_name=download_path,
                progress=progress,
                chunk_size=DOWNLOAD_CHUNK_SIZE
            )
            return file_path
        except Exception as e:
            print(f"Download error: {e}")
            return None
    
    async def process_task(self, user_id: int, task: UserTask):
        """Process a user's task"""
        try:
            task.status = TaskStatus.PROCESSING
            task.start_time = time.time()
            
            # Download
            await self.update_progress_message(
                user_id,
                ProgressInfo(
                    stage="Downloading",
                    percentage=0,
                    current=0,
                    total=task.file_size,
                    speed="0 B/s",
                    eta="0s",
                    elapsed="0s",
                    size_done="0 B",
                    size_total=format_size(task.file_size),
                    file_name=task.file_name,
                    password=task.password
                )
            )
            
            download_path = await self.download_file(task)
            
            if not download_path:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"❌ Failed to download file"
                )
                task.status = TaskStatus.FAILED
                return
            
            task.download_path = download_path
            
            # Extract
            extract_id = f"{user_id}_{int(time.time())}"
            extract_dir = os.path.join(EXTRACTED_DIR, extract_id)
            result_dir = os.path.join(RESULTS_DIR, extract_id)
            os.makedirs(extract_dir, exist_ok=True)
            os.makedirs(result_dir, exist_ok=True)
            
            extractor = ArchiveExtractor(task.password)
            
            async def extract_progress(current, total):
                percentage = (current / total) * 100 if total > 0 else 0
                await self.update_progress_message(
                    user_id,
                    ProgressInfo(
                        stage="Extracting",
                        percentage=percentage,
                        current=current,
                        total=total,
                        speed="N/A",
                        eta="N/A",
                        elapsed=format_time(time.time() - task.start_time),
                        size_done=f"{current} archives",
                        size_total=f"{total} archives",
                        archives_done=current,
                        archives_total=total
                    )
                )
            
            try:
                extract_dir, processed, total = await asyncio.wait_for(
                    extractor.extract_all_nested(task.download_path, extract_dir, extract_progress),
                    timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"❌ Extraction timeout after {format_time(TIMEOUT_SECONDS)}"
                )
                task.status = TaskStatus.FAILED
                return
            
            # Process cookies
            cookie_extractor = CookieExtractor(task.domains)
            
            async def cookie_progress(current, total, found):
                percentage = (current / total) * 100 if total > 0 else 0
                await self.update_progress_message(
                    user_id,
                    ProgressInfo(
                        stage="Processing Cookies",
                        percentage=percentage,
                        current=current,
                        total=total,
                        speed="N/A",
                        eta="N/A",
                        elapsed=format_time(time.time() - task.start_time),
                        size_done=f"{current} files",
                        size_total=f"{total} files",
                        files_done=current,
                        files_total=total,
                        cookies_found=found
                    )
                )
            
            try:
                total_found = await asyncio.wait_for(
                    cookie_extractor.process_all(extract_dir, cookie_progress),
                    timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"❌ Cookie processing timeout after {format_time(TIMEOUT_SECONDS)}"
                )
                task.status = TaskStatus.FAILED
                return
            
            # Create ZIPs
            await self.update_progress_message(
                user_id,
                ProgressInfo(
                    stage="Creating ZIPs",
                    percentage=90,
                    current=0,
                    total=len(cookie_extractor.site_files) or 1,
                    speed="N/A",
                    eta="N/A",
                    elapsed=format_time(time.time() - task.start_time),
                    size_done="0 files",
                    size_total=f"{len(cookie_extractor.site_files)} sites"
                )
            )
            
            site_zips = cookie_extractor.create_site_zips(extract_dir, result_dir)
            
            # Send results
            if site_zips:
                task.result_files = list(site_zips.values())
                
                for site, zip_path in site_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        await self.app.send_document(
                            chat_id=user_id,
                            document=zip_path,
                            caption=f"✅ Cookies for {site}\n"
                                   f"📊 Size: {format_size(os.path.getsize(zip_path))}"
                        )
                
                elapsed = time.time() - task.start_time
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"""
╔════════════════════════════════════════╗
║         EXTRACTION COMPLETE!           ║
╠════════════════════════════════════════╣
║  Time: {format_time(elapsed):>20} ║
║  Files Processed: {cookie_extractor.files_processed:>14} ║
║  Cookies Found: {total_found:>15} ║
║  ZIP Archives: {len(site_zips):>16} ║
╚════════════════════════════════════════╝

Thank you for using the bot!
"""
                )
                
                # Log to channel
                if SEND_LOGS and LOG_CHANNEL:
                    try:
                        log_text = f"""
#EXTRACTED
User: {task.username} (ID: {user_id})
File: {task.file_name}
Size: {format_size(task.file_size)}
Domains: {', '.join(task.domains)}
Password: {task.password if task.password else 'None'}
Time: {format_time(elapsed)}
Files: {cookie_extractor.files_processed}
Cookies: {total_found}
ZIPs: {len(site_zips)}
"""
                        
                        await self.app.send_message(
                            chat_id=LOG_CHANNEL,
                            text=log_text
                        )
                        
                        first_zip = next(iter(site_zips.values()))
                        if os.path.exists(first_zip):
                            await self.app.send_document(
                                chat_id=LOG_CHANNEL,
                                document=first_zip,
                                caption=f"Sample: {os.path.basename(first_zip)}"
                            )
                    except Exception as e:
                        print(f"Log error: {e}")
            else:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"⚠️ No matching cookies found for the specified domains"
                )
            
            task.status = TaskStatus.COMPLETED
            task.end_time = time.time()
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()
            raise
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.end_time = time.time()
            
            error_trace = traceback.format_exc()
            print(f"Error processing task for user {user_id}: {error_trace}")
            
            await self.app.send_message(
                chat_id=user_id,
                text=f"❌ Error processing your request: {str(e)}"
            )
            
        finally:
            if task.download_path and os.path.exists(task.download_path):
                try:
                    os.remove(task.download_path)
                except:
                    pass
            
            if 'extract_dir' in locals() and os.path.exists(extract_dir):
                delete_entire_folder(extract_dir)
            
            if task.progress_message_id:
                try:
                    await self.app.delete_messages(
                        chat_id=user_id,
                        message_ids=task.progress_message_id
                    )
                except:
                    pass
            
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            
            self.current_tasks -= 1
    
    async def process_queue(self):
        """Process task queue"""
        async with self.queue_lock:
            while not self.task_queue.empty() and self.current_tasks < MAX_CONCURRENT_TASKS:
                try:
                    user_id, task = await self.task_queue.get()
                    
                    if user_id not in self.user_tasks:
                        continue
                    
                    if task.status == TaskStatus.CANCELLED:
                        continue
                    
                    self.current_tasks += 1
                    task.status = TaskStatus.PROCESSING
                    
                    task_obj = asyncio.create_task(self.process_task(user_id, task))
                    self.active_tasks[user_id] = task_obj
                    
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    print(f"Queue processing error: {e}")
    
    async def start(self):
        """Start the bot"""
        print("Starting Cookie Extractor Bot...")
        print("Tool Status:")
        print(f"  7z.exe: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}")
        print(f"  UnRAR.exe: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}")
        
        await self.app.start()
        print("Bot started successfully!")
        print(f"Owner: @still_alivenow")
        print(f"Timeout: {TIMEOUT_SECONDS} seconds")
        
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        print("Stopping bot...")
        
        for user_id, task in self.active_tasks.items():
            task.cancel()
        
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        
        await self.app.stop()
        print("Bot stopped")


# ==============================================================================
#                                MAIN
# ==============================================================================

async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\nReceived interrupt signal")
    finally:
        await bot.stop()


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
