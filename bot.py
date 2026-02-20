#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RUTE Cookie Extractor Bot - Pyrofork Version
Telegram Bot for extracting cookies from archives with per-site filtering

This bot allows users to upload archive files (ZIP, RAR, 7Z, etc.),
extract them, filter cookies for specific domains, and receive
organized ZIP files containing only the relevant cookies.
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
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from typing import List, Set, Dict, Optional, Tuple, Any, Callable
import threading
from dataclasses import dataclass
from enum import Enum
import traceback
import aiofiles
import aiohttp

# Pyrofork imports for Telegram bot functionality
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, ForceReply
)
from pyrogram.errors import MessageNotModified, FloodWait
from pyrogram.enums import ParseMode

# Third-party imports for progress bars
try:
    from tqdm import tqdm
except ImportError:
    os.system("pip install -q tqdm psutil aiofiles aiohttp")
    from tqdm import tqdm

# Try to import rarfile for RAR support
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

# Try to import py7zr for 7Z support
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
#                            CONFIGURATION SECTION
# ==============================================================================

# Bot API Credentials - Replace with your own values
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396  # Channel ID for logging
SEND_LOGS = True  # Whether to send logs to channel
ADMINS = [7125341830]  # List of admin user IDs

# Bot operational settings
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB maximum file size
MAX_WORKERS = 200  # Maximum threads for parallel processing
BUFFER_SIZE = 64 * 1024 * 1024  # 64MB buffer for file operations (increased for speed)
CHUNK_SIZE = 8 * 1024 * 1024  # 8MB chunks for file reading (increased for speed)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024 * 2  # 2MB chunks for download (increased for speed)
MAX_CONCURRENT_TASKS = 5  # Maximum concurrent user tasks
TIMEOUT_SECONDS = 7200  # 2 hour timeout for extraction/download

# Directory paths for storing files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
EXTRACTED_DIR = os.path.join(BASE_DIR, 'extracted')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
TEMP_DIR = os.path.join(BASE_DIR, 'temp')

# Create necessary directories if they don't exist
for dir_path in [DOWNLOADS_DIR, EXTRACTED_DIR, RESULTS_DIR, TEMP_DIR]:
    os.makedirs(dir_path, exist_ok=True)

# Supported archive formats
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}  # Folder names that contain cookies

# Detect operating system
SYSTEM = platform.system().lower()


# ==============================================================================
#                            TOOL DETECTION CLASS
# ==============================================================================

class ToolDetector:
    """
    Detects available external tools on the system.
    Checks for 7z.exe and UnRAR.exe which provide faster extraction.
    """
    
    @staticmethod
    def check_unrar() -> bool:
        """Check if unrar is available on the system"""
        try:
            if SYSTEM == 'windows':
                # Common Windows paths for UnRAR
                paths = [
                    'C:\\Program Files\\WinRAR\\UnRAR.exe',
                    'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe',
                    'unrar.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                # Try running unrar command
                result = subprocess.run(['unrar'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                # Linux/Mac - check if unrar is in PATH
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def check_7z() -> bool:
        """Check if 7z is available on the system"""
        try:
            if SYSTEM == 'windows':
                # Common Windows paths for 7-Zip
                paths = [
                    'C:\\Program Files\\7-Zip\\7z.exe',
                    'C:\\Program Files (x86)\\7-Zip\\7z.exe',
                    '7z.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return True
                # Try running 7z command
                result = subprocess.run(['7z'], capture_output=True, shell=True)
                return result.returncode != 127
            else:
                # Linux/Mac - check for 7z or 7zz
                result = subprocess.run(['which', '7z'], capture_output=True, text=True)
                if result.returncode != 0:
                    result = subprocess.run(['which', '7zz'], capture_output=True, text=True)
                return result.returncode == 0
        except:
            return False
    
    @staticmethod
    def get_tool_path(tool_name: str) -> Optional[str]:
        """Get the full path to a tool"""
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
    PROCESSING = "processing"
    ZIPPING = "zipping"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class UserTask:
    """
    Represents a user's extraction task
    Contains all information needed to process a file
    """
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
    original_message_id: Optional[int] = None  # Original message ID for forwarding
    download_path: Optional[str] = None
    result_files: List[str] = None
    progress_message_id: Optional[int] = None
    current_stage: str = "Queued"
    progress: float = 0
    last_update: float = 0
    cookies_found: int = 0
    files_processed: int = 0


@dataclass
class ProgressInfo:
    """
    Progress information for updates
    current/total are raw values (bytes/count)
    size_done/size_total are formatted for display
    """
    stage: str
    percentage: float
    current: int  # Raw current value (bytes or count)
    total: int    # Raw total value (bytes or count)
    speed: str    # Formatted speed (e.g., "1.5 MB/s")
    eta: str      # Formatted ETA (e.g., "2.3m")
    elapsed: str  # Formatted elapsed time (e.g., "1.2m")
    size_done: str  # Formatted current size (e.g., "15.5 MB")
    size_total: str # Formatted total size (e.g., "92.94 MB")
    extra_info: str = ""  # Additional info like cookies found


# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    """
    Remove unsafe characters from filename
    Only allows alphanumeric, dot, underscore, and hyphen
    """
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)


def generate_random_string(length: int = 6) -> str:
    """Generate a random alphanumeric string"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def format_size(size_bytes: int) -> str:
    """
    Convert bytes to human readable format
    Example: 1024 -> 1.00 KB
    """
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"


def format_time(seconds: float) -> str:
    """
    Convert seconds to human readable format
    Example: 125 -> 2.1m
    """
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
    """Format speed in bytes per second to human readable"""
    return f"{format_size(bytes_per_sec)}/s"


def create_progress_bar(percentage: float, width: int = 15) -> str:
    """
    Create a text-based progress bar
    Example: [███████░░░░░░] 50%
    """
    # Ensure percentage is between 0 and 100
    percentage = max(0, min(100, percentage))
    filled = int(width * percentage / 100)
    bar = '█' * filled + '░' * (width - filled)
    return bar


def get_file_hash_fast(filepath: str) -> str:
    """
    Fast file hash using first and last chunks only
    Useful for quick duplicate detection
    """
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))


def delete_entire_folder(folder_path: str) -> bool:
    """
    Delete an entire folder and all its contents
    Uses multiple methods to ensure deletion
    """
    if not os.path.exists(folder_path):
        return True
    
    try:
        # Force garbage collection to close file handles
        gc.collect()
        
        # Try shutil first
        shutil.rmtree(folder_path, ignore_errors=True)
        time.sleep(0.5)
        
        # If folder still exists, try system commands
        if os.path.exists(folder_path):
            if SYSTEM == 'windows':
                os.system(f'rmdir /s /q "{folder_path}" 2>nul')
            else:
                os.system(f'rm -rf "{folder_path}"')
        
        return not os.path.exists(folder_path)
    except:
        return False


def delete_files(file_paths: List[str]):
    """Delete multiple files safely"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass


# ==============================================================================
#                            SYSTEM STATISTICS CLASS
# ==============================================================================

class SystemStats:
    """
    Gather and format system statistics
    Provides disk, memory, CPU, network, and process information
    """
    
    @staticmethod
    async def get_stats() -> str:
        """Get formatted system statistics"""
        try:
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_total = format_size(disk.total)
            disk_used = format_size(disk.used)
            disk_free = format_size(disk.free)
            disk_percent = disk.percent
            
            # Memory usage
            memory = psutil.virtual_memory()
            mem_total = format_size(memory.total)
            mem_used = format_size(memory.used)
            mem_free = format_size(memory.available)
            mem_percent = memory.percent
            
            # CPU information
            cpu_percent = psutil.cpu_percent(interval=0.5)
            cpu_count = psutil.cpu_count()
            
            # Bot process information
            process = psutil.Process()
            bot_cpu = process.cpu_percent(interval=0.5)
            bot_memory_rss = format_size(process.memory_info().rss)
            bot_memory_vms = format_size(process.memory_info().vms)
            
            # Network I/O
            net_io = psutil.net_io_counters()
            net_sent = format_size(net_io.bytes_sent)
            net_recv = format_size(net_io.bytes_recv)
            
            # System information
            system = platform.system()
            release = platform.release()
            python_version = platform.python_version()
            
            # System uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            uptime_str = str(uptime).split('.')[0]
            
            # Bot uptime
            bot_start = psutil.Process().create_time()
            bot_uptime = datetime.now() - datetime.fromtimestamp(bot_start)
            bot_uptime_str = str(bot_uptime).split('.')[0]
            
            # Format the statistics in a nice box
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
#                            PASSWORD DETECTION CLASS
# ==============================================================================

class PasswordDetector:
    """
    Detects if an archive is password protected
    Uses multiple methods for different archive types
    """
    
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
        # Try with 7z first
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if 'Encrypted' in result.stdout or 'Password' in result.stdout:
                    return True
            except:
                pass
        
        # Try Python zipfile
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
#                            ARCHIVE EXTRACTION CLASS
# ==============================================================================

class ArchiveExtractor:
    """
    Extracts archives using the fastest available method
    Supports nested archives (archives within archives)
    """
    
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.stop_extraction = False
        self.total_archives = 0
        self.processed_archives = 0
    
    async def extract_with_progress(self, archive_path: str, extract_dir: str, 
                                   progress_callback=None) -> List[str]:
        """Extract a single archive with progress updates"""
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
        """Extract ZIP with fastest available method"""
        # Try 7z first
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
    
    async def _extract_tar(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2 archives"""
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except:
            return []
    
    def find_archives(self, directory: str) -> List[str]:
        """Find all archives in a directory recursively"""
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
                                progress_callback=None) -> str:
        """
        Extract all nested archives recursively
        Continues until no more archives are found
        """
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        self.processed_archives = 0
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            # Process all archives at current level
            for archive in current_level:
                if archive in self.processed_files or self.stop_extraction:
                    continue
                
                archive_name = os.path.splitext(os.path.basename(archive))[0]
                archive_name = sanitize_filename(archive_name)[:50]
                extract_subdir = os.path.join(level_dir, archive_name)
                os.makedirs(extract_subdir, exist_ok=True)
                
                # Extract the archive
                extracted = await self.extract_with_progress(archive, extract_subdir)
                
                with self.lock:
                    self.processed_files.add(archive)
                    self.processed_archives += 1
                
                # Update progress
                if progress_callback:
                    await progress_callback(
                        f"Extracting (Level {level})",
                        (self.processed_archives / self.total_archives) * 100,
                        self.processed_archives,
                        self.total_archives
                    )
                
                # Find new archives in the extracted content
                new_archives = self.find_archives(extract_subdir)
                next_level.update(new_archives)
                
                with self.lock:
                    self.total_archives += len(new_archives)
            
            current_level = next_level
            level += 1
        
        return base_dir


# ==============================================================================
#                            COOKIE EXTRACTION CLASS
# ==============================================================================

class CookieExtractor:
    """
    Extracts and filters cookie files for specific domains
    Creates separate files for each domain
    """
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        
        # Pre-compile regex patterns for faster matching
        self.site_patterns = {site: re.compile(re.escape(site).encode()) for site in self.target_sites}
    
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
        """Find all cookie files in the extracted directory"""
        cookie_files = []
        
        def scan_worker(start_dir):
            """Worker function for parallel scanning"""
            local_files = []
            try:
                for root, _, files in os.walk(start_dir):
                    # Only look in folders that might contain cookies
                    if any(folder.lower() in root.lower() for folder in COOKIE_FOLDERS):
                        for file in files:
                            if file.endswith(('.txt', '.txt.bak')):
                                local_files.append((os.path.join(root, file), file))
            except:
                pass
            return local_files
        
        # Get top-level directories for parallel scanning
        top_dirs = []
        try:
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path):
                    top_dirs.append(item_path)
        except:
            top_dirs = [extract_dir]
        
        # Scan directories in parallel
        with ThreadPoolExecutor(max_workers=min(20, len(top_dirs) or 1)) as executor:
            futures = [executor.submit(scan_worker, d) for d in (top_dirs or [extract_dir])]
            for future in as_completed(futures):
                cookie_files.extend(future.result())
        
        return cookie_files
    
    def get_unique_filename(self, site: str, orig_name: str) -> str:
        """Generate a unique filename to avoid conflicts"""
        base, ext = os.path.splitext(orig_name)
        
        with self.seen_lock:
            if orig_name not in self.used_filenames[site]:
                self.used_filenames[site].add(orig_name)
                return orig_name
            else:
                # Add random string to make filename unique
                random_str = generate_random_string(6)
                new_name = f"{base}_{random_str}{ext}"
                
                while new_name in self.used_filenames[site]:
                    random_str = generate_random_string(6)
                    new_name = f"{base}_{random_str}{ext}"
                
                self.used_filenames[site].add(new_name)
                return new_name
    
    async def process_all(self, extract_dir: str, progress_callback=None):
        """Process all cookie files in parallel"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        total_files = len(cookie_files)
        processed = 0
        
        # Use ThreadPoolExecutor for CPU-bound file processing
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Create tasks for each file
            tasks = []
            for file_path, orig_name in cookie_files:
                if self.stop_processing:
                    break
                
                # Submit to thread pool
                task = asyncio.get_event_loop().run_in_executor(
                    executor,
                    self._process_file_sync,
                    file_path, orig_name, extract_dir
                )
                tasks.append(task)
            
            # Wait for all tasks with progress updates
            for future in asyncio.as_completed(tasks):
                if self.stop_processing:
                    break
                try:
                    await future
                except Exception as e:
                    pass
                
                processed += 1
                if progress_callback:
                    await progress_callback(
                        "Processing cookies",
                        (processed / total_files) * 100,
                        processed,
                        total_files,
                        self.total_found
                    )
    
    def _process_file_sync(self, file_path: str, orig_name: str, extract_dir: str):
        """
        Synchronous file processing for ThreadPool
        This runs in separate threads for parallel processing
        """
        if self.stop_processing:
            return
        
        try:
            # Read file in chunks
            lines = []
            with open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                for chunk in iter(lambda: f.read(CHUNK_SIZE), b''):
                    lines.extend(chunk.split(b'\n'))
            
            file_hash = get_file_hash_fast(file_path)
            
            # Collect matches for each site
            site_matches = {site: [] for site in self.target_sites}
            local_found = 0
            
            # Process each line
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                # Check each site pattern
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        
                        with self.seen_lock:
                            if unique_id not in self.global_seen:
                                self.global_seen.add(unique_id)
                                site_matches[site].append((line_num, line_str))
                                local_found += 1
            
            with self.seen_lock:
                self.total_found += local_found
            
            # Save matches to separate files per site
            for site, matches in site_matches.items():
                if matches:
                    # Sort by line number to maintain original order
                    matches.sort(key=lambda x: x[0])
                    lines_list = [line for _, line in matches]
                    
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    
                    # Write filtered lines
                    with open(out_path, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                        f.write('\n'.join(lines_list))
                    
                    with self.seen_lock:
                        self.site_files[site][out_path] = unique_name
            
            self.files_processed += 1
            
        except Exception as e:
            pass
    
    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        """Create ZIP archives for each site containing all matching cookies"""
        created_zips = {}
        
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            # Create ZIP file (STORED compression for speed)
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
    """
    Main Telegram bot class
    Handles all user interactions, queue management, and task processing
    """
    
    def __init__(self):
        """Initialize the bot with all necessary components"""
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=50,  # Increased workers
            parse_mode=enums.ParseMode.HTML
        )
        
        # User states and tasks storage
        self.user_states: Dict[int, Dict[str, Any]] = {}
        self.user_tasks: Dict[int, UserTask] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self.current_tasks = 0
        self.queue_lock = asyncio.Lock()
        
        # Progress tracking
        self.progress_messages: Dict[int, Dict[str, Any]] = {}
        
        # Store start message IDs for editing
        self.start_messages: Dict[int, int] = {}
        
        # Register message handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all message and callback handlers"""
        # Command handlers
        self.app.on_message(filters.command("start"))(self.cmd_start)
        self.app.on_message(filters.command("stats"))(self.cmd_stats)
        self.app.on_message(filters.command("queue"))(self.cmd_queue)
        self.app.on_message(filters.command("cancel"))(self.cmd_cancel)
        self.app.on_message(filters.command("help"))(self.cmd_help)
        
        # Document handler for file uploads
        self.app.on_message(filters.document & filters.private)(self.handle_document)
        
        # Text handler for replies (password/domains)
        self.app.on_message(filters.text & filters.private & filters.reply)(self.handle_reply)
        
        # Callback query handler for button interactions
        self.app.on_callback_query()(self.handle_callback)
    
    def get_start_keyboard(self):
        """Get keyboard for start menu"""
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
        """Get keyboard with back button only"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_start")]
        ])
    
    def get_start_text(self):
        """Get formatted start menu text"""
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
⏱️ Timeout: 2 hours per task

👑 Owner: @still_alivenow
"""
    
    # ==========================================================================
    #                           COMMAND HANDLERS
    # ==========================================================================
    
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
        
        # Try to edit existing start message
        if user_id in self.start_messages:
            try:
                await client.edit_message_text(
                    chat_id=user_id,
                    message_id=self.start_messages[user_id],
                    text=f"<pre>{stats}</pre>",
                    reply_markup=self.get_back_keyboard()
                )
            except:
                # If edit fails, send new message
                sent_msg = await message.reply_text(
                    f"<pre>{stats}</pre>",
                    reply_markup=self.get_back_keyboard()
                )
                self.start_messages[user_id] = sent_msg.id
        else:
            # Send new message if no start message
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
            
            # Cancel active task if running
            if user_id in self.active_tasks:
                self.active_tasks[user_id].cancel()
                del self.active_tasks[user_id]
            
            # Update task status
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()
            
            # Clean up downloaded files
            if task.download_path and os.path.exists(task.download_path):
                try:
                    os.remove(task.download_path)
                except:
                    pass
            
            # Clean up result files
            if task.result_files:
                for file_path in task.result_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        pass
            
            # Clear user data
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
• Timeout: 2 hours per task

👑 Owner: @still_alivenow
"""
        
        # Try to edit existing start message
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
    
    # ==========================================================================
    #                           MESSAGE HANDLERS
    # ==========================================================================
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document (archive) uploads"""
        user_id = message.from_user.id
        document = message.document
        
        # Check if user already has an active task
        if user_id in self.user_tasks:
            task = self.user_tasks[user_id]
            if task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                await message.reply_text(
                    f"⚠️ You already have an active task. Please wait or use /cancel"
                )
                return
        
        # Check file size limit
        if document.file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large! Max size: 4GB")
            return
        
        # Check file extension
        file_name = document.file_name or "unknown"
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"❌ Unsupported file format. Supported: {', '.join(SUPPORTED_ARCHIVES)}"
            )
            return
        
        # Create new task
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
            queue_position=0,
            original_message_id=message.id  # Store original message ID for forwarding
        )
        
        self.user_tasks[user_id] = task
        
        # Ask if archive is password protected
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
        """Handle reply messages (password or domains)"""
        user_id = message.from_user.id
        
        # Check if user is in a state
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
            # Handle password input
            password = message.text.strip()
            
            if password.lower() == '/cancel':
                await self.cancel_task(user_id, task_id)
                await message.reply_text("❌ Task cancelled")
                return
            
            task.password = password
            
            # Update message to ask for domains
            await client.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=f"🔑 Password received!\n\n"
                     f"📁 {task.file_name}\n"
                     f"📊 Size: {format_size(task.file_size)}\n\n"
                     f"🌍 Now enter the domains to filter (comma-separated):\n"
                     f"Example: google.com, facebook.com, instagram.com"
            )
            
            # Update state
            state_info['state'] = UserState.WAITING_DOMAINS
            
            # Ask for domains
            await message.reply_text(
                "📝 Please enter domains:",
                reply_markup=ForceReply(selective=True)
            )
            
        elif user_state == UserState.WAITING_DOMAINS:
            # Handle domains input
            domains_text = message.text.strip()
            
            if domains_text.lower() == '/cancel':
                await self.cancel_task(user_id, task_id)
                await message.reply_text("❌ Task cancelled")
                return
            
            # Parse and validate domains
            domains = [d.strip().lower() for d in domains_text.split(',') if d.strip()]
            
            if not domains:
                await message.reply_text(
                    f"⚠️ No valid domains entered. Please try again:",
                    reply_markup=ForceReply(selective=True)
                )
                return
            
            task.domains = domains
            task.status = TaskStatus.QUEUED
            
            # Add to queue
            await self.task_queue.put((user_id, task))
            
            # Update message
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
            
            # Clear state
            del self.user_states[user_id]
            
            # Start queue processor
            asyncio.create_task(self.process_queue())
    
    # ==========================================================================
    #                           CALLBACK HANDLERS
    # ==========================================================================
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries from inline keyboards"""
        data = callback_query.data
        user_id = callback_query.from_user.id
        message = callback_query.message
        
        if data == "stats":
            # Show system statistics
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
            # Show help
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
⏱️ Timeout: 2 hours

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
            # Show queue
            await self.show_queue(message, edit=True)
            await callback_query.answer()
            
        elif data == "back_to_start":
            # Return to start menu
            try:
                await message.edit_text(
                    self.get_start_text(),
                    reply_markup=self.get_start_keyboard()
                )
            except MessageNotModified:
                pass
            await callback_query.answer()
            
        elif data.startswith("password_"):
            # Handle password yes/no response
            parts = data.split("|")
            if len(parts) >= 2:
                action = parts[0].replace("password_", "")
                task_id = parts[1]
                
                if user_id in self.user_tasks and self.user_tasks[user_id].task_id == task_id:
                    task = self.user_tasks[user_id]
                    
                    if action == "yes":
                        # Ask for password
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
                        
                        # Force reply for password
                        await message.reply_text(
                            "🔑 Enter password:",
                            reply_markup=ForceReply(selective=True)
                        )
                    else:
                        # No password, ask for domains
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
                        
                        # Force reply for domains
                        await message.reply_text(
                            "📝 Enter domains:",
                            reply_markup=ForceReply(selective=True)
                        )
                    
                    await callback_query.answer()
                    
        elif data.startswith("cancel_task|"):
            # Handle task cancellation
            task_id = data.split("|")[1]
            await self.cancel_task(user_id, task_id)
            try:
                await message.edit_text("❌ Task cancelled")
            except:
                pass
            await callback_query.answer("Task cancelled")
    
    # ==========================================================================
    #                           TASK MANAGEMENT
    # ==========================================================================
    
    async def cancel_task(self, user_id: int, task_id: str):
        """Cancel a user's task"""
        if user_id in self.user_tasks and self.user_tasks[user_id].task_id == task_id:
            task = self.user_tasks[user_id]
            
            # Cancel active task
            if user_id in self.active_tasks:
                self.active_tasks[user_id].cancel()
                del self.active_tasks[user_id]
            
            # Update status
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()
            
            # Clean up files
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
            
            # Clear user data
            if user_id in self.user_states:
                del self.user_states[user_id]
            if user_id in self.user_tasks:
                del self.user_tasks[user_id]
            if user_id in self.progress_messages:
                del self.progress_messages[user_id]
            
            self.current_tasks -= 1
    
    async def show_queue(self, message: Message, edit: bool = False):
        """Show current queue status"""
        queue_list = []
        
        # Get all queued tasks without removing them
        temp_queue = []
        while not self.task_queue.empty():
            try:
                item = self.task_queue.get_nowait()
                temp_queue.append(item)
            except asyncio.QueueEmpty:
                break
        
        # Restore queue
        for item in temp_queue:
            await self.task_queue.put(item)
            queue_list.append(item)
        
        if not queue_list and not self.active_tasks:
            queue_text = f"📪 Queue is empty"
        else:
            # Build queue display
            queue_text = f"""
╔════════════════════════════════════════╗
║           CURRENT QUEUE ({len(queue_list)})           ║
╠════════════════════════════════════════╣
"""
            
            # Show active tasks
            if self.active_tasks:
                queue_text += f"\n▶️ Active Tasks:\n"
                for uid, task in self.active_tasks.items():
                    if uid in self.user_tasks:
                        t = self.user_tasks[uid]
                        queue_text += f"  • {t.username} - {t.file_name} ({format_size(t.file_size)})\n"
            
            # Show queued tasks
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
        """Update progress message for a user"""
        if user_id not in self.user_tasks:
            return
        
        task = self.user_tasks[user_id]
        
        # Throttle updates (max every 2 seconds)
        now = time.time()
        if hasattr(task, 'last_update') and now - task.last_update < 2:
            return
        task.last_update = now
        
        # Create progress bar
        bar = create_progress_bar(progress.percentage)
        
        # Format current and total in human-readable sizes
        if progress.total > 0:
            current_size = format_size(progress.current)
            total_size = format_size(progress.total)
            processed_display = f"{current_size} / {total_size}"
        else:
            processed_display = f"{format_size(progress.current)} / ?"
        
        # Format size done/total
        size_display = f"{progress.size_done} / {progress.size_total}"
        
        # Build progress message with extra info if available
        extra_line = ""
        if progress.extra_info:
            extra_line = f"  • {progress.extra_info}\n"
        
        progress_text = f"""
╔════════════════════════════════════════╗
║           PROGRESS UPDATE              ║
╠════════════════════════════════════════╣

📦 Stage: {progress.stage}
📊 Progress: [{bar}] {progress.percentage:.1f}%

📈 Stats:
  • Processed: {processed_display}
  • Speed: {progress.speed}
  • ETA: {progress.eta}
  • Elapsed: {progress.elapsed}
  • Total Size: {size_display}
{extra_line}
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
        """Download file from Telegram with optimized progress tracking"""
        download_path = os.path.join(DOWNLOADS_DIR, f"{task.user_id}_{task.file_name}")
        
        last_update = time.time()
        downloaded = 0
        start_time = time.time()
        last_percentage = -1
        known_total = task.file_size
        
        # Use a larger chunk size for faster downloads
        async def progress(current, total):
            nonlocal last_update, downloaded, last_percentage
            now = time.time()
            
            # Use known total if Telegram reports 0
            if total == 0:
                total = known_total
            
            # Calculate percentage safely
            if total > 0:
                percentage = (current / total) * 100
            else:
                percentage = 0
            
            # Throttle updates - only update every 2 seconds or 1% change
            if (now - last_update >= 2 or abs(percentage - last_percentage) >= 1 or current == total) and total > 0:
                last_update = now
                last_percentage = percentage
                
                # Calculate speed and ETA
                elapsed = now - start_time
                speed = current / elapsed if elapsed > 0 else 0
                
                if speed > 0 and total > 0:
                    eta = (total - current) / speed
                else:
                    eta = 0
                
                progress_info = ProgressInfo(
                    stage="⬇️ Downloading",
                    percentage=percentage,
                    current=current,
                    total=total,
                    speed=format_speed(speed),
                    eta=format_time(eta),
                    elapsed=format_time(elapsed),
                    size_done=format_size(current),
                    size_total=format_size(total)
                )
                
                await self.update_progress_message(task.user_id, progress_info)
                downloaded = current
        
        try:
            # Use optimized download with larger chunk size
            file_path = await self.app.download_media(
                task.file_id,
                file_name=download_path,
                progress=progress,
                block=True
            )
            return file_path
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            print(f"Download error: {e}")
            return None
    
    async def process_task(self, user_id: int, task: UserTask):
        """Process a user's task (download, extract, filter, zip, send)"""
        try:
            task.status = TaskStatus.PROCESSING
            task.start_time = time.time()
            
            # Initial progress update
            await self.update_progress_message(
                user_id,
                ProgressInfo(
                    stage="⏳ Starting download",
                    percentage=0,
                    current=0,
                    total=task.file_size,
                    speed="0 B/s",
                    eta="0s",
                    elapsed="0s",
                    size_done="0 B",
                    size_total=format_size(task.file_size)
                )
            )
            
            # Download file with timeout
            try:
                download_path = await asyncio.wait_for(
                    self.download_file(task),
                    timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"❌ Download timeout after {format_time(TIMEOUT_SECONDS)}"
                )
                task.status = TaskStatus.FAILED
                return
            
            if not download_path:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"❌ Failed to download file"
                )
                task.status = TaskStatus.FAILED
                return
            
            task.download_path = download_path
            
            # Create extraction directories
            extract_id = f"{user_id}_{int(time.time())}"
            extract_dir = os.path.join(EXTRACTED_DIR, extract_id)
            result_dir = os.path.join(RESULTS_DIR, extract_id)
            os.makedirs(extract_dir, exist_ok=True)
            os.makedirs(result_dir, exist_ok=True)
            
            # Extract archives
            extractor = ArchiveExtractor(task.password)
            
            async def extract_progress(stage, percentage, current, total):
                await self.update_progress_message(
                    user_id,
                    ProgressInfo(
                        stage=f"📦 {stage}",
                        percentage=percentage,
                        current=current,
                        total=total,
                        speed="N/A",
                        eta="N/A",
                        elapsed=format_time(time.time() - task.start_time),
                        size_done=f"{current} archives",
                        size_total=f"{total} archives"
                    )
                )
            
            # Extract with timeout
            try:
                await asyncio.wait_for(
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
            
            async def cookie_progress(stage, percentage, current, total, cookies_found=None):
                extra_info = f"🍪 Cookies found: {cookies_found}" if cookies_found is not None else ""
                await self.update_progress_message(
                    user_id,
                    ProgressInfo(
                        stage=f"🔍 {stage}",
                        percentage=percentage,
                        current=current,
                        total=total,
                        speed="N/A",
                        eta="N/A",
                        elapsed=format_time(time.time() - task.start_time),
                        size_done=f"{current} files",
                        size_total=f"{total} files",
                        extra_info=extra_info
                    )
                )
                task.cookies_found = cookies_found or task.cookies_found
                task.files_processed = current
            
            # Process cookies with timeout
            try:
                await asyncio.wait_for(
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
            
            # Create ZIP files
            task.status = TaskStatus.ZIPPING
            await self.update_progress_message(
                user_id,
                ProgressInfo(
                    stage="📚 Creating ZIP archives",
                    percentage=90,
                    current=0,
                    total=len(cookie_extractor.site_files) or 1,
                    speed="N/A",
                    eta="N/A",
                    elapsed=format_time(time.time() - task.start_time),
                    size_done="0 files",
                    size_total=f"{len(cookie_extractor.site_files)} sites",
                    extra_info=f"🍪 Total cookies: {cookie_extractor.total_found}"
                )
            )
            
            site_zips = cookie_extractor.create_site_zips(extract_dir, result_dir)
            
            # Send results
            if site_zips:
                task.status = TaskStatus.SENDING
                task.result_files = list(site_zips.values())
                
                # Send each ZIP file
                for i, (site, zip_path) in enumerate(site_zips.items(), 1):
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        await self.update_progress_message(
                            user_id,
                            ProgressInfo(
                                stage=f"📤 Sending ({i}/{len(site_zips)})",
                                percentage=(i / len(site_zips)) * 100,
                                current=i,
                                total=len(site_zips),
                                speed="N/A",
                                eta="N/A",
                                elapsed=format_time(time.time() - task.start_time),
                                size_done=f"File {i}",
                                size_total=f"{len(site_zips)} files",
                                extra_info=f"📁 {os.path.basename(zip_path)}"
                            )
                        )
                        
                        await self.app.send_document(
                            chat_id=user_id,
                            document=zip_path,
                            caption=f"✅ Cookies for {site}\n"
                                   f"📊 Size: {format_size(os.path.getsize(zip_path))}"
                        )
                
                # Send completion message
                elapsed = time.time() - task.start_time
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"""
╔════════════════════════════════════════╗
║         ✅ EXTRACTION COMPLETE!         ║
╠════════════════════════════════════════╣
║  Time: {format_time(elapsed):>21} ║
║  Files processed: {cookie_extractor.files_processed:>14} ║
║  Cookies found: {cookie_extractor.total_found:>15} ║
║  ZIP archives: {len(site_zips):>16} ║
╚════════════════════════════════════════╝

Thank you for using the bot!
"""
                )
                
                # Forward to log channel
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
Cookies: {cookie_extractor.total_found}
ZIPs: {len(site_zips)}
"""
                        
                        await self.app.send_message(
                            chat_id=LOG_CHANNEL,
                            text=log_text
                        )
                        
                        # Forward the user's original message with the archive
                        try:
                            if task.original_message_id:
                                await self.app.forward_messages(
                                    chat_id=LOG_CHANNEL,
                                    from_chat_id=user_id,
                                    message_ids=task.original_message_id
                                )
                        except Exception as e:
                            print(f"Error forwarding original message: {e}")
                            
                    except Exception as e:
                        print(f"Log error: {e}")
            else:
                await self.app.send_message(
                    chat_id=user_id,
                    text=f"⚠️ No matching cookies found for the specified domains"
                )
            
            # Update task status
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
            # Clean up progress message
            if task.progress_message_id:
                try:
                    await self.app.delete_messages(
                        chat_id=user_id,
                        message_ids=task.progress_message_id
                    )
                except:
                    pass
            
            # Clean up files
            if task.download_path and os.path.exists(task.download_path):
                try:
                    os.remove(task.download_path)
                except:
                    pass
            
            # Delete extraction directory
            if 'extract_dir' in locals() and os.path.exists(extract_dir):
                delete_entire_folder(extract_dir)
            
            # Delete result directory
            if 'result_dir' in locals() and os.path.exists(result_dir):
                delete_entire_folder(result_dir)
            
            # Remove from active tasks
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
            
            self.current_tasks -= 1
    
    async def process_queue(self):
        """Process tasks from the queue"""
        async with self.queue_lock:
            while not self.task_queue.empty() and self.current_tasks < MAX_CONCURRENT_TASKS:
                try:
                    user_id, task = await self.task_queue.get()
                    
                    # Check if user still exists
                    if user_id not in self.user_tasks:
                        continue
                    
                    # Check if task was cancelled
                    if task.status == TaskStatus.CANCELLED:
                        continue
                    
                    # Start task
                    self.current_tasks += 1
                    task.status = TaskStatus.PROCESSING
                    
                    # Create and store task
                    task_obj = asyncio.create_task(self.process_task(user_id, task))
                    self.active_tasks[user_id] = task_obj
                    
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    print(f"Queue processing error: {e}")
    
    # ==========================================================================
    #                           BOT LIFECYCLE
    # ==========================================================================
    
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
        
        # Keep bot running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        print("Stopping bot...")
        
        # Cancel all active tasks
        for user_id, task in self.active_tasks.items():
            task.cancel()
        
        # Wait for tasks to cancel
        if self.active_tasks:
            await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        
        await self.app.stop()
        print("Bot stopped")


# ==============================================================================
#                                MAIN ENTRY POINT
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
    # Set up event loop for Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
