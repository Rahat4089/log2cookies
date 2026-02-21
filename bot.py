#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import aiohttp
import aiofiles
from datetime import datetime
from typing import List, Set, Dict, Optional, Tuple
import platform
import signal
from pathlib import Path
import math
import gc
import urllib.parse

# Pyrofork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q tqdm colorama aiohttp aiofiles")
    from tqdm import tqdm
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

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# ULTIMATE SPEED SETTINGS
MAX_WORKERS = 50  # 50 threads for bot (reduced for stability)
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for file reading
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB max file size
DOWNLOAD_TIMEOUT = 300  # 5 minutes

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
#                            USER TASK MANAGER
# ==============================================================================

class UserTaskManager:
    """Manage user tasks and cancellations"""
    
    def __init__(self):
        self.user_tasks: Dict[int, Dict] = {}
        self.user_cancelled: Set[int] = set()
        self.lock = asyncio.Lock()
    
    async def register_task(self, user_id: int, task_id: str, data: Dict):
        """Register a user task"""
        async with self.lock:
            self.user_tasks[user_id] = {
                'task_id': task_id,
                'data': data,
                'start_time': time.time(),
                'cancelled': False,
                'progress_messages': []
            }
    
    async def add_progress_message(self, user_id: int, message_id: int):
        """Add progress message to track for cleanup"""
        async with self.lock:
            if user_id in self.user_tasks:
                if 'progress_messages' not in self.user_tasks[user_id]:
                    self.user_tasks[user_id]['progress_messages'] = []
                self.user_tasks[user_id]['progress_messages'].append(message_id)
    
    async def get_task(self, user_id: int) -> Optional[Dict]:
        """Get user task"""
        async with self.lock:
            return self.user_tasks.get(user_id)
    
    async def cancel_task(self, user_id: int, task_id: str = None) -> bool:
        """Cancel user task"""
        async with self.lock:
            if user_id in self.user_tasks:
                # If task_id provided, verify it matches
                if task_id and self.user_tasks[user_id].get('task_id') != task_id:
                    return False
                self.user_tasks[user_id]['cancelled'] = True
                self.user_cancelled.add(user_id)
                return True
            return False
    
    async def is_cancelled(self, user_id: int) -> bool:
        """Check if user cancelled"""
        async with self.lock:
            if user_id in self.user_cancelled:
                return True
            if user_id in self.user_tasks:
                return self.user_tasks[user_id].get('cancelled', False)
            return False
    
    async def clear_task(self, user_id: int):
        """Clear user task"""
        async with self.lock:
            if user_id in self.user_tasks:
                del self.user_tasks[user_id]
            if user_id in self.user_cancelled:
                self.user_cancelled.remove(user_id)
    
    async def cleanup_old_tasks(self, max_age: int = 3600):
        """Cleanup tasks older than max_age seconds"""
        current_time = time.time()
        async with self.lock:
            to_remove = []
            for user_id, task in self.user_tasks.items():
                if current_time - task['start_time'] > max_age:
                    to_remove.append(user_id)
            for user_id in to_remove:
                del self.user_tasks[user_id]
                if user_id in self.user_cancelled:
                    self.user_cancelled.remove(user_id)

# ==============================================================================
#                            PROGRESS TRACKER
# ==============================================================================

class ProgressTracker:
    """Track and update progress messages"""
    
    def __init__(self, message: Message, total: int, description: str = "Progress", task_manager: UserTaskManager = None):
        self.message = message
        self.total = total
        self.current = 0
        self.description = description
        self.last_update = 0
        self.lock = asyncio.Lock()
        self.start_time = time.time()
        self.cancelled = False
        self.task_manager = task_manager
        self.user_id = message.chat.id
        
        # Register progress message
        if task_manager:
            asyncio.create_task(task_manager.add_progress_message(self.user_id, message.id))
    
    async def update(self, amount: int = 1, force: bool = False):
        """Update progress"""
        if self.cancelled:
            return
        
        async with self.lock:
            self.current += amount
            current_time = time.time()
            
            # Update every 2 seconds or if forced
            if force or current_time - self.last_update >= 2:
                await self._send_update()
                self.last_update = current_time
    
    async def set_total(self, total: int):
        """Set total value"""
        async with self.lock:
            self.total = total
            await self._send_update(force=True)
    
    async def _send_update(self, force: bool = False):
        """Send progress update"""
        try:
            percentage = (self.current / self.total * 100) if self.total > 0 else 0
            elapsed = time.time() - self.start_time
            
            # Calculate ETA
            if self.current > 0:
                eta = (elapsed / self.current) * (self.total - self.current)
                eta_str = self._format_time(eta)
            else:
                eta_str = "Calculating..."
            
            # Create progress bar
            bar_length = 20
            filled = int(bar_length * self.current // self.total) if self.total > 0 else 0
            bar = '█' * filled + '░' * (bar_length - filled)
            
            # Format sizes
            current_str = self._format_size(self.current)
            total_str = self._format_size(self.total)
            
            text = (
                f"**{self.description}**\n"
                f"`{bar}` {percentage:.1f}%\n"
                f"📊 {current_str} / {total_str}\n"
                f"⏱️ ETA: {eta_str}\n"
                f"⚡ Elapsed: {self._format_time(elapsed)}\n"
                f"🔴 /cancel_{self.task_manager.user_tasks.get(self.user_id, {}).get('task_id', '') if self.task_manager else ''}"
            )
            
            await self.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        except MessageNotModified:
            pass
        except Exception as e:
            print(f"Progress update error: {e}")
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds to human readable"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"
    
    async def cancel(self):
        """Cancel progress"""
        self.cancelled = True
        try:
            await self.message.edit_text("❌ **Task Cancelled**", parse_mode=ParseMode.MARKDOWN)
        except:
            pass
    
    async def complete(self, text: str):
        """Mark as complete"""
        try:
            await self.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    """Quick sanitize for filenames"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    """Generate random string for unique filenames"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_filename_from_url(url: str) -> str:
    """Extract filename from URL"""
    try:
        # Parse URL
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        
        # Get filename from path
        filename = os.path.basename(path)
        
        # If no filename, generate one
        if not filename or filename == '/':
            # Try to get from Content-Disposition later
            return f"download_{generate_random_string(8)}.zip"
        
        # Remove query parameters
        filename = filename.split('?')[0]
        
        # Sanitize
        return sanitize_filename(filename)
    except:
        return f"download_{generate_random_string(8)}.zip"

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
        gc.collect()
        
        # Try multiple methods
        if SYSTEM == 'windows':
            os.system(f'rmdir /s /q "{folder_path}" 2>nul')
        else:
            os.system(f'rm -rf "{folder_path}"')
        
        # Wait a bit
        await asyncio.sleep(1)
        
        # If still exists, try shutil
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
        
        return not os.path.exists(folder_path)
    except:
        return False

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
#                            ARCHIVE EXTRACTION - OPTIMIZED PER TYPE
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
        self.progress = None
        self.task_manager = None
        self.user_id = None
    
    def set_progress(self, progress, task_manager=None, user_id=None):
        """Set progress tracker"""
        self.progress = progress
        self.task_manager = task_manager
        self.user_id = user_id
    
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        
        if self.progress:
            await self.progress.set_total(self.total_archives)
        
        while current_level and not self.stop_extraction:
            # Check cancellation
            if self.task_manager and self.user_id:
                if await self.task_manager.is_cancelled(self.user_id):
                    self.stop_extraction = True
                    break
            
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            # Process archives in this level
            extract_tasks = []
            for archive in current_level:
                if archive in self.processed_files or self.stop_extraction:
                    continue
                
                archive_name = os.path.splitext(os.path.basename(archive))[0]
                archive_name = sanitize_filename(archive_name)[:50]
                extract_subdir = os.path.join(level_dir, archive_name)
                os.makedirs(extract_subdir, exist_ok=True)
                
                # Extract in thread pool (since extraction is CPU/IO bound)
                loop = asyncio.get_event_loop()
                task = loop.run_in_executor(
                    None, 
                    self._extract_and_find, 
                    archive, extract_subdir
                )
                extract_tasks.append(task)
            
            # Wait for all extractions
            if extract_tasks:
                results = await asyncio.gather(*extract_tasks)
                for new_archives in results:
                    next_level.update(new_archives)
                    if self.progress:
                        await self.progress.update(1)
            
            current_level = next_level
            level += 1
        
        return base_dir
    
    def _extract_and_find(self, archive: str, extract_dir: str) -> Set[str]:
        """Extract and find new archives (runs in thread)"""
        if self.stop_extraction:
            return set()
        
        # Extract
        self.extract_single(archive, extract_dir)
        
        with self.lock:
            self.processed_files.add(archive)
            self.extracted_count += 1
        
        # Find new archives
        return set(self.find_archives_fast(extract_dir))

# ==============================================================================
#                            COOKIE EXTRACTION
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
        self.progress = None
        self.task_manager = None
        self.user_id = None
        
        # Pre-compile patterns for each site
        self.site_patterns = {site: re.compile(re.escape(site).encode()) for site in self.target_sites}
    
    def set_progress(self, progress, task_manager=None, user_id=None):
        """Set progress tracker"""
        self.progress = progress
        self.task_manager = task_manager
        self.user_id = user_id
    
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
        
        # Scan in parallel using threads
        with ThreadPoolExecutor(max_workers=min(20, len(top_dirs) or 1)) as executor:
            futures = [executor.submit(scan_worker, d) for d in (top_dirs or [extract_dir])]
            for future in futures:
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
    
    async def process_all(self, extract_dir: str):
        """Process all files"""
        # Find all cookie files
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        if self.progress:
            await self.progress.set_total(len(cookie_files))
        
        # Process files in thread pool
        loop = asyncio.get_event_loop()
        tasks = []
        
        for file_path, orig_name in cookie_files:
            # Check cancellation
            if self.task_manager and self.user_id:
                if await self.task_manager.is_cancelled(self.user_id):
                    self.stop_processing = True
                    break
            
            if self.stop_processing:
                break
            
            task = loop.run_in_executor(
                None,
                self.process_file,
                file_path, orig_name, extract_dir
            )
            tasks.append(task)
        
        # Wait for all tasks
        if tasks:
            for i, task in enumerate(asyncio.as_completed(tasks)):
                await task
                if self.progress and not self.stop_processing:
                    await self.progress.update(1)
    
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
#                            BOT APPLICATION
# ==============================================================================

class CookieExtractorBot:
    """Main bot application"""
    
    def __init__(self):
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        self.task_manager = UserTaskManager()
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.downloads_dir = os.path.join(self.base_dir, 'downloads')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.logs_dir = os.path.join(self.base_dir, 'logs')
        
        # Create directories
        os.makedirs(self.downloads_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # User states
        self.user_states = {}
        self.user_data = {}
        self.state_lock = asyncio.Lock()
        
    async def start(self):
        """Start the bot"""
        print(f"{Fore.GREEN}Starting Cookie Extractor Bot...{Style.RESET_ALL}")
        await self.app.start()
        print(f"{Fore.GREEN}Bot started successfully!{Style.RESET_ALL}")
        
        # Start cleanup task
        asyncio.create_task(self.cleanup_old_files())
    
    async def stop(self):
        """Stop the bot"""
        print(f"{Fore.YELLOW}Stopping bot...{Style.RESET_ALL}")
        await self.app.stop()
        print(f"{Fore.GREEN}Bot stopped{Style.RESET_ALL}")
    
    async def cleanup_old_files(self):
        """Cleanup old files periodically"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Cleanup downloads older than 1 hour
                current_time = time.time()
                for folder in [self.downloads_dir, self.results_dir]:
                    if os.path.exists(folder):
                        for item in os.listdir(folder):
                            item_path = os.path.join(folder, item)
                            try:
                                if os.path.isfile(item_path):
                                    if current_time - os.path.getmtime(item_path) > 3600:
                                        os.remove(item_path)
                                elif os.path.isdir(item_path):
                                    if current_time - os.path.getmtime(item_path) > 3600:
                                        shutil.rmtree(item_path, ignore_errors=True)
                            except:
                                pass
                
                # Cleanup old tasks
                await self.task_manager.cleanup_old_tasks()
                
            except Exception as e:
                print(f"Cleanup error: {e}")
    
    async def log_to_channel(self, text: str):
        """Send log to channel"""
        if not SEND_LOGS:
            return
        
        try:
            await self.app.send_message(LOG_CHANNEL, text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass
    
    async def send_progress_message(self, user_id: int, text: str) -> Message:
        """Send progress message and return it"""
        msg = await self.app.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
        return msg
    
    async def download_file(self, url: str, file_path: str, progress_msg: Message, task_id: str) -> bool:
        """Download file with progress"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT), allow_redirects=True) as resp:
                    if resp.status != 200:
                        await progress_msg.edit_text(f"❌ Download failed: HTTP {resp.status}")
                        return False
                    
                    total_size = int(resp.headers.get('content-length', 0))
                    if total_size > MAX_FILE_SIZE:
                        await progress_msg.edit_text(f"❌ File too large: {format_size(total_size)} > {format_size(MAX_FILE_SIZE)}")
                        return False
                    
                    # Create progress tracker
                    user_id = progress_msg.chat.id
                    progress = ProgressTracker(progress_msg, total_size, "⬇️ Downloading", self.task_manager)
                    
                    downloaded = 0
                    chunk_size = 1024 * 1024  # 1MB
                    
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(chunk_size):
                            # Check cancellation
                            if await self.task_manager.is_cancelled(user_id):
                                return False
                            
                            await f.write(chunk)
                            downloaded += len(chunk)
                            await progress.update(len(chunk))
                    
                    return True
                    
        except asyncio.CancelledError:
            return False
        except Exception as e:
            await progress_msg.edit_text(f"❌ Download error: {str(e)}")
            return False
    
    async def download_telegram_file(self, message: Message, file_path: str, progress_msg: Message, task_id: str) -> bool:
        """Download file from Telegram with progress"""
        try:
            # Get file size
            file_size = 0
            if message.document:
                file_size = message.document.file_size
            elif message.photo:
                file_size = message.photo.file_size
            
            if file_size > MAX_FILE_SIZE:
                await progress_msg.edit_text(f"❌ File too large: {format_size(file_size)} > {format_size(MAX_FILE_SIZE)}")
                return False
            
            # Create progress tracker
            user_id = progress_msg.chat.id
            progress = ProgressTracker(progress_msg, file_size, "⬇️ Downloading", self.task_manager)
            
            # Download with progress callback
            async def progress_callback(current, total):
                # Check cancellation
                if await self.task_manager.is_cancelled(user_id):
                    raise asyncio.CancelledError()
                await progress.update(current - progress.current)
            
            await message.download(file_name=file_path, progress=progress_callback)
            
            return True
            
        except asyncio.CancelledError:
            return False
        except Exception as e:
            await progress_msg.edit_text(f"❌ Download error: {str(e)}")
            return False
    
    # ==========================================================================
    #                            HANDLERS
    # ==========================================================================
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        user = message.from_user
        welcome_text = (
            f"👋 **Welcome to Cookie Extractor Bot!**\n\n"
            f"📦 I can extract cookies from archives and filter them by domain.\n\n"
            f"**How to use:**\n"
            f"1️⃣ Send me an archive file (.zip/.rar/.7z) or any direct download link\n"
            f"2️⃣ Tell me if it's password protected\n"
            f"3️⃣ Provide the domains to filter (comma-separated)\n"
            f"4️⃣ I'll extract and filter cookies for you!\n\n"
            f"**Commands:**\n"
            f"/start - Show this message\n"
            f"/cancel - Cancel current task\n"
            f"/status - Check task status\n\n"
            f"⚡ **Speed:** Using {'✓ 7z' if TOOL_STATUS['7z'] else '✗ 7z'} | {'✓ UnRAR' if TOOL_STATUS['unrar'] else '✗ UnRAR'}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Guide", callback_data="guide"),
             InlineKeyboardButton("ℹ️ Info", callback_data="info")]
        ])
        
        await message.reply_text(welcome_text, reply_markup=keyboard)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Check if it's cancel with task ID
        if text.startswith('/cancel_'):
            task_id = text[8:].strip()
            task = await self.task_manager.get_task(user_id)
            
            if task and task.get('task_id') == task_id:
                await self.task_manager.cancel_task(user_id, task_id)
                await message.reply_text(f"✅ **Task {task_id} cancelled successfully!**")
                
                # Clean up user files
                if 'download_folder' in task['data']:
                    await delete_entire_folder(task['data']['download_folder'])
                if 'extract_folder' in task['data']:
                    await delete_entire_folder(task['data']['extract_folder'])
            else:
                await message.reply_text("❌ Invalid task ID or no active task.")
        else:
            # Regular cancel
            task = await self.task_manager.get_task(user_id)
            if task:
                await self.task_manager.cancel_task(user_id)
                await message.reply_text("✅ **Task cancelled successfully!**")
            else:
                await message.reply_text("❌ No active task found.")
    
    async def status_command(self, client: Client, message: Message):
        """Handle /status command"""
        user_id = message.from_user.id
        task = await self.task_manager.get_task(user_id)
        
        if task:
            elapsed = time.time() - task['start_time']
            status_text = (
                f"📊 **Task Status**\n\n"
                f"🆔 Task ID: `{task['task_id']}`\n"
                f"⏱️ Elapsed: {format_time(elapsed)}\n"
                f"📦 File: {task['data'].get('filename', 'Unknown')}\n"
                f"🔑 Password: {'Yes' if task['data'].get('password') else 'No'}\n"
                f"🎯 Domains: {', '.join(task['data'].get('domains', []))}\n\n"
                f"🔴 /cancel_{task['task_id']} to cancel"
            )
            await message.reply_text(status_text)
        else:
            await message.reply_text("❌ No active task.")
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document uploads"""
        user_id = message.from_user.id
        
        # Check if user has active task
        task = await self.task_manager.get_task(user_id)
        if task:
            await message.reply_text(
                "❌ You already have an active task.\n"
                f"Use /cancel_{task['task_id']} to cancel it first."
            )
            return
        
        # Check file extension
        if not message.document:
            return
        
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"❌ Unsupported file type: {ext}\n"
                f"Supported: {', '.join(SUPPORTED_ARCHIVES)}"
            )
            return
        
        # Store file info
        async with self.state_lock:
            self.user_data[user_id] = {
                'type': 'telegram',
                'message': message,
                'filename': file_name,
                'file_size': message.document.file_size
            }
            self.user_states[user_id] = 'awaiting_password'
        
        # Ask about password
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔐 Yes, it's protected", callback_data="password_yes"),
                InlineKeyboardButton("🔓 No password", callback_data="password_no")
            ],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        
        await message.reply_text(
            f"📦 **File received:** `{file_name}`\n"
            f"📊 Size: {format_size(message.document.file_size)}\n\n"
            f"🔒 Is this archive password protected?",
            reply_markup=keyboard
        )
    
    async def handle_text(self, client: Client, message: Message):
        """Handle text messages (URLs or passwords)"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Check if it's a URL (any URL)
        if text.startswith(('http://', 'https://', 'ftp://')):
            # URL handling
            task = await self.task_manager.get_task(user_id)
            if task:
                await message.reply_text(
                    f"❌ You already have an active task.\n"
                    f"Use /cancel_{task['task_id']} to cancel it first."
                )
                return
            
            # Store URL info
            filename = get_filename_from_url(text)
            async with self.state_lock:
                self.user_data[user_id] = {
                    'type': 'url',
                    'url': text,
                    'filename': filename
                }
                self.user_states[user_id] = 'awaiting_password'
            
            # Ask about password
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔐 Yes, it's protected", callback_data="password_yes"),
                    InlineKeyboardButton("🔓 No password", callback_data="password_no")
                ],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            
            await message.reply_text(
                f"📦 **URL received:** `{filename}`\n\n"
                f"🔒 Is this archive password protected?",
                reply_markup=keyboard
            )
            return
        
        # Handle password input
        async with self.state_lock:
            if user_id in self.user_states and self.user_states.get(user_id) == 'awaiting_password':
                self.user_data[user_id]['password'] = text
                self.user_states[user_id] = 'awaiting_domains'
                
                await message.reply_text(
                    "✅ Password saved!\n\n"
                    "🎯 Now send me the domains to filter (comma-separated)\n"
                    "Example: `example.com, google.com, facebook.com`"
                )
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        user_id = callback_query.from_user.id
        data = callback_query.data
        
        if data == "cancel":
            await self.task_manager.cancel_task(user_id)
            await callback_query.message.edit_text("❌ Operation cancelled.")
            
            # Clear user state
            async with self.state_lock:
                if user_id in self.user_data:
                    del self.user_data[user_id]
                if user_id in self.user_states:
                    del self.user_states[user_id]
            
            await callback_query.answer()
            return
        
        elif data == "password_yes":
            async with self.state_lock:
                self.user_states[user_id] = 'awaiting_password'
            await callback_query.message.edit_text(
                "🔐 Please send me the password for this archive."
            )
            await callback_query.answer()
            return
        
        elif data == "password_no":
            async with self.state_lock:
                if user_id in self.user_data:
                    self.user_data[user_id]['password'] = None
                    self.user_states[user_id] = 'awaiting_domains'
            
            await callback_query.message.edit_text(
                "🎯 Now send me the domains to filter (comma-separated)\n"
                "Example: `example.com, google.com, facebook.com`"
            )
            await callback_query.answer()
            return
        
        elif data == "guide":
            guide_text = (
                "📖 **User Guide**\n\n"
                "1️⃣ **Send Archive**\n"
                "   • Upload file directly or provide any direct download link\n"
                "   • Supported: .zip, .rar, .7z, .tar, .gz\n\n"
                "2️⃣ **Password (if needed)**\n"
                "   • Tell me if it's password protected\n"
                "   • Send the password if yes\n\n"
                "3️⃣ **Enter Domains**\n"
                "   • Comma-separated list (e.g., google.com, facebook.com)\n"
                "   • I'll filter cookies for these domains\n\n"
                "4️⃣ **Wait for Processing**\n"
                "   • Download progress shown\n"
                "   • Extraction progress shown\n"
                "   • Cookie filtering progress shown\n\n"
                "5️⃣ **Get Results**\n"
                "   • Separate ZIP files per domain\n"
                "   • Each contains filtered cookies\n\n"
                "6️⃣ **Cleanup**\n"
                "   • All files automatically deleted after sending\n\n"
                "7️⃣ **Cancel Task**\n"
                "   • Use /cancel_TASKID shown in progress bar\n"
                "   • Files will be cleaned up automatically"
            )
            await callback_query.message.edit_text(guide_text)
            await callback_query.answer()
            return
        
        elif data == "info":
            info_text = (
                "ℹ️ **Bot Information**\n\n"
                f"**Tools:**\n"
                f"• 7z: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}\n"
                f"• UnRAR: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}\n\n"
                f"**Supported Formats:**\n"
                f"{', '.join(SUPPORTED_ARCHIVES)}\n\n"
                f"**Max File Size:** {format_size(MAX_FILE_SIZE)}\n"
                f"**Max Workers:** {MAX_WORKERS}\n\n"
                f"**Developer:** @rute_dev"
            )
            await callback_query.message.edit_text(info_text)
            await callback_query.answer()
            return
    
    async def handle_domains(self, client: Client, message: Message):
        """Handle domain input"""
        user_id = message.from_user.id
        
        async with self.state_lock:
            if self.user_states.get(user_id) != 'awaiting_domains':
                return
        
        # Parse domains
        domains = [d.strip().lower() for d in message.text.split(',') if d.strip()]
        
        if not domains:
            await message.reply_text("❌ Please enter at least one domain.")
            return
        
        # Store domains
        async with self.state_lock:
            self.user_data[user_id]['domains'] = domains
        
        # Start processing
        await self.start_processing(user_id, message)
    
    async def start_processing(self, user_id: int, message: Message):
        """Start the main processing pipeline"""
        async with self.state_lock:
            data = self.user_data.get(user_id)
            if not data:
                await message.reply_text("❌ Error: No data found. Please start over.")
                return
        
        # Generate unique task ID
        task_id = generate_random_string(8)
        await self.task_manager.register_task(user_id, task_id, data)
        
        # Send initial progress message
        progress_msg = await self.send_progress_message(
            user_id,
            "🚀 **Starting process...**\n\n"
            f"📦 File: `{data['filename']}`\n"
            f"🔑 Password: {'Yes' if data['password'] else 'No'}\n"
            f"🎯 Domains: {', '.join(data['domains'])}\n\n"
            f"🔴 /cancel_{task_id} to cancel"
        )
        
        try:
            # Create unique folders
            unique_id = datetime.now().strftime('%H%M%S_') + generate_random_string(4)
            download_folder = os.path.join(self.downloads_dir, f"download_{unique_id}")
            extract_folder = os.path.join(self.downloads_dir, f"extract_{unique_id}")
            result_folder = os.path.join(self.results_dir, datetime.now().strftime('%Y-%m-%d'))
            
            os.makedirs(download_folder, exist_ok=True)
            os.makedirs(extract_folder, exist_ok=True)
            os.makedirs(result_folder, exist_ok=True)
            
            # Store folders in task data for cleanup
            data['download_folder'] = download_folder
            data['extract_folder'] = extract_folder
            
            # Step 1: Download file
            file_path = os.path.join(download_folder, sanitize_filename(data['filename']))
            
            if data['type'] == 'telegram':
                success = await self.download_telegram_file(data['message'], file_path, progress_msg, task_id)
            else:  # URL
                success = await self.download_file(data['url'], file_path, progress_msg, task_id)
            
            if not success or await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return
            
            # Step 2: Extract archives
            await progress_msg.edit_text(
                f"📦 **Extracting archives...**\n\n"
                f"🔴 /cancel_{task_id} to cancel"
            )
            
            extract_progress = ProgressTracker(progress_msg, 1, "📦 Extracting", self.task_manager)
            extractor = UltimateArchiveExtractor(data['password'])
            extractor.set_progress(extract_progress, self.task_manager, user_id)
            
            await extractor.extract_all_nested(file_path, extract_folder)
            
            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return
            
            # Step 3: Filter cookies
            await progress_msg.edit_text(
                f"🔍 **Filtering cookies...**\n\n"
                f"🔴 /cancel_{task_id} to cancel"
            )
            
            cookie_progress = ProgressTracker(progress_msg, 1, "🔍 Filtering", self.task_manager)
            cookie_extractor = UltimateCookieExtractor(data['domains'])
            cookie_extractor.set_progress(cookie_progress, self.task_manager, user_id)
            
            await cookie_extractor.process_all(extract_folder)
            
            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return
            
            # Step 4: Create ZIPs
            await progress_msg.edit_text(
                f"📦 **Creating ZIP archives...**\n\n"
                f"🔴 /cancel_{task_id} to cancel"
            )
            
            created_zips = cookie_extractor.create_site_zips(extract_folder, result_folder)
            
            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return
            
            # Step 5: Send results
            if created_zips:
                # Create summary message
                elapsed = time.time() - (await self.task_manager.get_task(user_id))['start_time']
                
                # Format stats
                files_processed_str = str(cookie_extractor.files_processed)
                entries_found_str = str(cookie_extractor.total_found)
                
                summary = (
                    f"✅ **Processing Complete!**\n\n"
                    f"⏱️ Time: {format_time(elapsed)}\n"
                    f"📁 Files processed: {files_processed_str}\n"
                    f"🔍 Entries found: {entries_found_str}\n"
                    f"📦 ZIP archives: {len(created_zips)}\n\n"
                    f"📤 **Sending files...**"
                )
                
                await progress_msg.edit_text(summary)
                
                # Send each ZIP
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        caption = f"🍪 Cookies for: `{site}`\n📊 Files: {len(cookie_extractor.site_files[site])}"
                        await self.app.send_document(
                            user_id,
                            zip_path,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(0.5)  # Small delay to avoid flood
                
                # Final message
                await self.app.send_message(
                    user_id,
                    "✅ **All files sent!**\nUse /start to process another archive."
                )
                
                # Log to channel
                log_text = (
                    f"✅ **Process Complete**\n"
                    f"👤 User: `{user_id}`\n"
                    f"📦 File: `{data['filename']}`\n"
                    f"⏱️ Time: {format_time(elapsed)}\n"
                    f"🔍 Entries: {cookie_extractor.total_found}\n"
                    f"📁 Zips: {len(created_zips)}"
                )
                await self.log_to_channel(log_text)
                
            else:
                await progress_msg.edit_text(
                    "❌ **No matching cookies found**\n"
                    "The archive was processed but no cookies matched your domains."
                )
            
            # Cleanup
            await self.cleanup_user_files(user_id, download_folder, extract_folder)
            
        except asyncio.CancelledError:
            await progress_msg.edit_text("❌ **Task cancelled by user**")
            await self.cleanup_user_files(user_id, download_folder, extract_folder)
        except Exception as e:
            await progress_msg.edit_text(f"❌ **Error:** {str(e)}")
            await self.log_to_channel(f"❌ Error for user {user_id}: {str(e)}")
            await self.cleanup_user_files(user_id, download_folder, extract_folder)
        finally:
            # Clear user data
            async with self.state_lock:
                if user_id in self.user_data:
                    del self.user_data[user_id]
                if user_id in self.user_states:
                    del self.user_states[user_id]
            await self.task_manager.clear_task(user_id)
    
    async def cleanup_user_files(self, user_id: int, *folders):
        """Clean up user files"""
        for folder in folders:
            if folder and os.path.exists(folder):
                await delete_entire_folder(folder)
    
    def run(self):
        """Run the bot"""
        # Register handlers
        @self.app.on_message(filters.command("start"))
        async def start_handler(client, message):
            await self.start_command(client, message)
        
        @self.app.on_message(filters.command("cancel"))
        async def cancel_handler(client, message):
            await self.cancel_command(client, message)
        
        @self.app.on_message(filters.command("status"))
        async def status_handler(client, message):
            await self.status_command(client, message)
        
        @self.app.on_message(filters.document)
        async def document_handler(client, message):
            await self.handle_document(client, message)
        
        @self.app.on_message(filters.text & filters.private)
        async def text_handler(client, message):
            # Check if awaiting domains
            user_id = message.from_user.id
            async with self.state_lock:
                is_awaiting_domains = self.user_states.get(user_id) == 'awaiting_domains'
            
            if is_awaiting_domains:
                await self.handle_domains(client, message)
            else:
                await self.handle_text(client, message)
        
        @self.app.on_callback_query()
        async def callback_handler(client, callback_query):
            await self.handle_callback(client, callback_query)
        
        # Run the bot
        self.app.run()

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    # Print banner
    tools_status = []
    if TOOL_STATUS['unrar']:
        tools_status.append(f"{Fore.GREEN}✓ UnRAR.exe{Style.RESET_ALL}")
    else:
        tools_status.append(f"{Fore.RED}✗ UnRAR.exe{Style.RESET_ALL}")
    
    if TOOL_STATUS['7z']:
        tools_status.append(f"{Fore.GREEN}✓ 7z.exe{Style.RESET_ALL}")
    else:
        tools_status.append(f"{Fore.RED}✗ 7z.exe{Style.RESET_ALL}")
    
    tools_str = ' · '.join(tools_status)
    
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════╗
║{Fore.YELLOW}     🚀 COOKIE EXTRACTOR BOT - TELEGRAM VERSION 🚀     {Fore.CYAN}║
║{Fore.WHITE}       External Tools: {tools_str}                      {Fore.CYAN}║
║{Fore.WHITE}       Multi-user · Progress Bars · Auto-Cleanup        {Fore.CYAN}║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}
    """
    print(banner)
    
    # Create and run bot
    bot = CookieExtractorBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
