#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - Pyrogram Version
Full-featured Telegram bot with queue system, stats, and robust error handling
"""

import os
import sys
import re
import zipfile
import shutil
import hashlib
import time
import asyncio
import random
import string
import subprocess
import psutil
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple
import threading
import platform
from pathlib import Path

# Pyrogram imports
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified

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

# Try to import rarfile for password detection only
try:
    import rarfile
    HAS_RARFILE = True
except ImportError:
    HAS_RARFILE = False

# Try to import py7zr for password detection only
try:
    import py7zr
    HAS_PY7ZR = True
except ImportError:
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

# Speed Settings
MAX_WORKERS = 100
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB
CHUNK_SIZE = 1024 * 1024  # 1MB
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4GB

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# Detect system
SYSTEM = platform.system().lower()

# Bot start time
BOT_START_TIME = datetime.now()

# ==============================================================================
#                            QUEUE SYSTEM
# ==============================================================================

class TaskQueue:
    """Queue system for managing user tasks"""
    
    def __init__(self):
        self.queue: List[Dict] = []
        self.active_tasks: Dict[int, Dict] = {}  # user_id -> task
        self.user_states: Dict[int, Dict] = {}  # user_id -> state
        self.lock = asyncio.Lock()
    
    async def add_task(self, user_id: int, task_data: Dict) -> int:
        """Add task to queue"""
        async with self.lock:
            # Check if user already has active task
            if user_id in self.active_tasks:
                return -1
            
            task_data['user_id'] = user_id
            task_data['added_time'] = datetime.now()
            task_data['status'] = 'queued'
            self.queue.append(task_data)
            
            return len(self.queue)
    
    async def get_next_task(self) -> Optional[Dict]:
        """Get next task from queue"""
        async with self.lock:
            if self.queue:
                task = self.queue.pop(0)
                task['status'] = 'processing'
                task['start_time'] = datetime.now()
                self.active_tasks[task['user_id']] = task
                return task
            return None
    
    async def complete_task(self, user_id: int):
        """Mark task as complete"""
        async with self.lock:
            if user_id in self.active_tasks:
                del self.active_tasks[user_id]
    
    async def cancel_task(self, user_id: int) -> bool:
        """Cancel user's task"""
        async with self.lock:
            # Cancel from queue
            for i, task in enumerate(self.queue):
                if task['user_id'] == user_id:
                    self.queue.pop(i)
                    return True
            
            # Cancel active task
            if user_id in self.active_tasks:
                self.active_tasks[user_id]['cancelled'] = True
                return True
            
            return False
    
    async def get_queue_info(self) -> str:
        """Get queue information"""
        async with self.lock:
            if not self.queue and not self.active_tasks:
                return "📭 Queue is empty"
            
            info = "📋 **Current Queue:**\n\n"
            
            # Active tasks
            if self.active_tasks:
                info += "🔄 **Processing:**\n"
                for user_id, task in self.active_tasks.items():
                    elapsed = (datetime.now() - task['start_time']).seconds
                    info += f"├ User: `{user_id}`\n"
                    info += f"├ File: `{task['filename']}`\n"
                    info += f"├ Size: `{self.format_size(task['file_size'])}`\n"
                    info += f"└ Time: `{elapsed}s`\n\n"
            
            # Queued tasks
            if self.queue:
                info += f"⏳ **Waiting ({len(self.queue)}):**\n"
                for i, task in enumerate(self.queue[:5], 1):
                    wait_time = (datetime.now() - task['added_time']).seconds
                    info += f"{i}. User: `{task['user_id']}`\n"
                    info += f"   File: `{task['filename']}`\n"
                    info += f"   Size: `{self.format_size(task['file_size'])}`\n"
                    info += f"   Wait: `{wait_time}s`\n\n"
                
                if len(self.queue) > 5:
                    info += f"... and {len(self.queue) - 5} more\n"
            
            return info
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f}TB"
    
    async def set_user_state(self, user_id: int, state: str, data: Dict = None):
        """Set user state"""
        async with self.lock:
            self.user_states[user_id] = {
                'state': state,
                'data': data or {},
                'time': datetime.now()
            }
    
    async def get_user_state(self, user_id: int) -> Optional[Dict]:
        """Get user state"""
        async with self.lock:
            return self.user_states.get(user_id)
    
    async def clear_user_state(self, user_id: int):
        """Clear user state"""
        async with self.lock:
            if user_id in self.user_states:
                del self.user_states[user_id]

# Global queue
task_queue = TaskQueue()

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    """Sanitize filename"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    """Generate random string"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

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

def format_size(size_bytes: int) -> str:
    """Format size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    """Format time"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

async def progress_callback(current, total, message: Message, start_time, action="Downloading"):
    """Progress callback for downloads/uploads"""
    try:
        now = time.time()
        elapsed = now - start_time
        
        if elapsed == 0:
            return
        
        percentage = (current / total) * 100
        speed = current / elapsed
        eta = (total - current) / speed if speed > 0 else 0
        
        progress_bar = "".join([
            "█" if i < int(percentage / 5) else "░"
            for i in range(20)
        ])
        
        text = (
            f"**{action}**\n\n"
            f"`{progress_bar}` {percentage:.1f}%\n\n"
            f"📦 **Size:** {format_size(current)} / {format_size(total)}\n"
            f"⚡ **Speed:** {format_size(speed)}/s\n"
            f"⏱️ **ETA:** {format_time(eta)}\n"
            f"🕐 **Elapsed:** {format_time(elapsed)}"
        )
        
        # Update every 2 seconds
        if not hasattr(progress_callback, 'last_update'):
            progress_callback.last_update = {}
        
        last = progress_callback.last_update.get(message.id, 0)
        if now - last >= 2:
            await message.edit_text(text)
            progress_callback.last_update[message.id] = now
            
    except MessageNotModified:
        pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

def delete_folder(folder_path: str) -> bool:
    """Delete folder"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        import gc
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

# Tool status
TOOL_STATUS = {
    'unrar': ToolDetector.check_unrar(),
    '7z': ToolDetector.check_7z(),
}

TOOL_PATHS = {
    'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None,
    '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None,
}

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

class ArchiveExtractor:
    """Archive extraction with progress updates"""
    
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
        if not HAS_RARFILE:
            return []
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
        if not HAS_PY7ZR:
            return []
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        """Extract all nested archives with progress"""
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
                        
                        with self.lock:
                            total_archives += len(new_archives)
                        
                        if self.progress_callback:
                            await self.progress_callback(self.extracted_count, total_archives)
                    except:
                        pass
            
            current_level = next_level
            level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class CookieExtractor:
    """Cookie extraction with filtering"""
    
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
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
                
        except Exception:
            pass
    
    async def process_all(self, extract_dir: str, progress_callback=None):
        """Process all files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        total = len(cookie_files)
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = []
            for file_path, orig_name in cookie_files:
                if self.stop_processing:
                    break
                future = executor.submit(self.process_file, file_path, orig_name, extract_dir)
                futures.append(future)
            
            for i, future in enumerate(as_completed(futures)):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
                
                if progress_callback and i % 10 == 0:
                    await progress_callback(i + 1, total)
    
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
#                            STATS COMMAND
# ==============================================================================

def get_system_stats() -> str:
    """Get system statistics"""
    try:
        # Disk
        disk = psutil.disk_usage('/')
        disk_total = format_size(disk.total)
        disk_used = format_size(disk.used)
        disk_free = format_size(disk.free)
        disk_percent = disk.percent
        
        # RAM
        ram = psutil.virtual_memory()
        ram_total = format_size(ram.total)
        ram_used = format_size(ram.used)
        ram_free = format_size(ram.available)
        ram_percent = ram.percent
        
        # CPU
        cpu_count = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Bot process
        process = psutil.Process()
        bot_cpu = process.cpu_percent()
        bot_mem = process.memory_info()
        bot_rss = format_size(bot_mem.rss)
        bot_vms = format_size(bot_mem.vms)
        
        # Network
        net = psutil.net_io_counters()
        upload_speed = format_size(net.bytes_sent)
        download_speed = format_size(net.bytes_recv)
        total_io = format_size(net.bytes_sent + net.bytes_recv)
        
        # System info
        os_name = platform.system()
        os_version = platform.release()
        python_version = platform.python_version()
        
        # Uptime
        uptime = datetime.now() - BOT_START_TIME
        uptime_str = f"{uptime.seconds // 3600:02d}h {(uptime.seconds % 3600) // 60:02d}m {uptime.seconds % 60:02d}s"
        
        # Ping (simple approximation)
        import time
        start = time.time()
        psutil.cpu_percent()
        ping = (time.time() - start) * 1000
        
        stats = f"""🖥️ **System Statistics Dashboard**

💾 **Disk Storage**
├ Total: `{disk_total}`
├ Used: `{disk_used}` ({disk_percent}%)
└ Free: `{disk_free}`

🧠 **RAM (Memory)**
├ Total: `{ram_total}`
├ Used: `{ram_used}` ({ram_percent}%)
└ Free: `{ram_free}`

⚡ **CPU**
├ Cores: `{cpu_count}`
└ Usage: `{cpu_percent}%`

🔌 **Bot Process**
├ CPU: `{bot_cpu}%`
├ RAM (RSS): `{bot_rss}`
└ RAM (VMS): `{bot_vms}`

🌐 **Network**
├ Upload Total: `{upload_speed}`
├ Download Total: `{download_speed}`
└ Total I/O: `{total_io}`

📟 **System Info**
├ OS: `{os_name}`
├ OS Version: `{os_version}`
├ Python: `{python_version}`
└ Uptime: `{uptime_str}`

⏱️ **Performance**
└ Current Ping: `{ping:.3f} ms`

👤 **Owner Credits:** @still_alivenow"""
        
        return stats
    except Exception as e:
        return f"❌ Error getting stats: {str(e)}"

# ==============================================================================
#                            BOT INITIALIZATION
# ==============================================================================

app = Client(
    "cookie_extractor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==============================================================================
#                            BOT HANDLERS
# ==============================================================================

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Start command"""
    try:
        tools_status = []
        if TOOL_STATUS['unrar']:
            tools_status.append("✅ UnRAR")
        else:
            tools_status.append("❌ UnRAR")
        
        if TOOL_STATUS['7z']:
            tools_status.append("✅ 7z")
        else:
            tools_status.append("❌ 7z")
        
        tools_str = ' · '.join(tools_status)
        
        text = f"""🚀 **RUTE Cookie Extractor Bot**

**Features:**
✅ 100 Threads for maximum speed
✅ Supports .zip, .rar, .7z, and more
✅ Queue system for multiple users
✅ Per-site cookie filtering
✅ Auto-forwarding to logs

**Available Tools:**
{tools_str}

**Commands:**
/extract - Start cookie extraction
/queue - View current queue
/stats - View system statistics
/cancel - Cancel current operation

**Owner:** @still_alivenow"""
        
        await message.reply_text(text)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    """Stats command"""
    try:
        stats = get_system_stats()
        await message.reply_text(stats)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("queue"))
async def queue_command(client: Client, message: Message):
    """Queue command"""
    try:
        info = await task_queue.get_queue_info()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
        ])
        
        await message.reply_text(info, reply_markup=keyboard)
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("extract"))
async def extract_command(client: Client, message: Message):
    """Extract command"""
    try:
        user_id = message.from_user.id
        
        # Check if user already has task
        state = await task_queue.get_user_state(user_id)
        if state:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
            ])
            await message.reply_text(
                "⚠️ You already have an active operation. Please complete or cancel it first.",
                reply_markup=keyboard
            )
            return
        
        # Set state to waiting for archive
        await task_queue.set_user_state(user_id, 'waiting_archive')
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
        ])
        
        await message.reply_text(
            "📂 Please send me the archive file (.zip, .rar, .7z, etc.)\n"
            f"Maximum size: {format_size(MAX_FILE_SIZE)}",
            reply_markup=keyboard
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_message(filters.command("cancel"))
async def cancel_command(client: Client, message: Message):
    """Cancel command"""
    try:
        user_id = message.from_user.id
        
        # Try to cancel task
        cancelled = await task_queue.cancel_task(user_id)
        
        # Clear user state
        await task_queue.clear_user_state(user_id)
        
        if cancelled:
            await message.reply_text("✅ Operation cancelled successfully!")
        else:
            await message.reply_text("ℹ️ No active operation to cancel.")
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

@app.on_callback_query(filters.regex("^cancel_task$"))
async def cancel_callback(client: Client, callback_query):
    """Cancel callback"""
    try:
        user_id = callback_query.from_user.id
        
        cancelled = await task_queue.cancel_task(user_id)
        await task_queue.clear_user_state(user_id)
        
        if cancelled:
            await callback_query.answer("✅ Cancelled!", show_alert=True)
            await callback_query.message.edit_text("✅ Operation cancelled!")
        else:
            await callback_query.answer("ℹ️ Nothing to cancel", show_alert=True)
    except Exception as e:
        await callback_query.answer(f"❌ Error: {str(e)}", show_alert=True)

@app.on_message(filters.document | filters.video)
async def handle_file(client: Client, message: Message):
    """Handle file upload"""
    try:
        user_id = message.from_user.id
        
        # Check user state
        state = await task_queue.get_user_state(user_id)
        if not state or state['state'] != 'waiting_archive':
            return
        
        # Check file size
        file_size = message.document.file_size if message.document else message.video.file_size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(f"❌ File too large! Maximum: {format_size(MAX_FILE_SIZE)}")
            return
        
        # Check file extension
        file_name = message.document.file_name if message.document else message.video.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"❌ Unsupported format!\n"
                f"Supported: {', '.join(SUPPORTED_ARCHIVES)}"
            )
            return
        
        # Forward to logs
        if SEND_LOGS:
            try:
                await message.forward(LOG_CHANNEL)
            except:
                pass
        
        # Update state
        await task_queue.set_user_state(user_id, 'waiting_password', {
            'file_id': message.document.file_id if message.document else message.video.file_id,
            'file_name': file_name,
            'file_size': file_size
        })
        
        # Check if password protected
        msg = await message.reply_text("🔍 Checking if password protected...")
        
        # Download file temporarily to check
        temp_dir = f"temp_{user_id}"
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = os.path.join(temp_dir, file_name)
        
        try:
            start_time = time.time()
            await message.download(
                file_name=temp_file,
                progress=lambda c, t: asyncio.create_task(
                    progress_callback(c, t, msg, start_time, "Checking")
                )
            )
            
            # Check password
            is_protected = False
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(temp_file)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(temp_file)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(temp_file)
            
            # Cleanup temp file
            delete_folder(temp_dir)
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
            ])
            
            if is_protected:
                await msg.edit_text(
                    "🔐 Archive is password protected!\n"
                    "Please send the password (or /skip if not needed):",
                    reply_markup=keyboard
                )
            else:
                await msg.edit_text(
                    "✅ Archive is not password protected!\n"
                    "Please send target domains (comma-separated):\n"
                    "Example: `facebook.com, google.com`",
                    reply_markup=keyboard
                )
                await task_queue.set_user_state(user_id, 'waiting_domains', state['data'])
        
        except Exception as e:
            delete_folder(temp_dir)
            await msg.edit_text(f"❌ Error checking file: {str(e)}")
            await task_queue.clear_user_state(user_id)
    
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        await task_queue.clear_user_state(message.from_user.id)

@app.on_message(filters.text & ~filters.command(["start", "stats", "queue", "extract", "cancel", "skip"]))
async def handle_text(client: Client, message: Message):
    """Handle text messages"""
    try:
        user_id = message.from_user.id
        state = await task_queue.get_user_state(user_id)
        
        if not state:
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
        ])
        
        if state['state'] == 'waiting_password':
            # Store password
            state['data']['password'] = message.text.strip()
            await task_queue.set_user_state(user_id, 'waiting_domains', state['data'])
            
            await message.reply_text(
                "✅ Password saved!\n"
                "Please send target domains (comma-separated):\n"
                "Example: `facebook.com, google.com`",
                reply_markup=keyboard
            )
        
        elif state['state'] == 'waiting_domains':
            # Parse domains
            domains = [d.strip().lower() for d in message.text.split(',') if d.strip()]
            
            if not domains:
                await message.reply_text("❌ Please provide at least one domain!")
                return
            
            # Add to queue
            task_data = state['data']
            task_data['domains'] = domains
            task_data['filename'] = task_data['file_name']
            task_data['message'] = message
            
            position = await task_queue.add_task(user_id, task_data)
            
            if position == -1:
                await message.reply_text("⚠️ You already have an active task!")
                return
            
            await task_queue.clear_user_state(user_id)
            
            await message.reply_text(
                f"✅ Added to queue!\n"
                f"📍 Position: {position}\n"
                f"📦 File: `{task_data['file_name']}`\n"
                f"📏 Size: `{format_size(task_data['file_size'])}`\n"
                f"🎯 Domains: {len(domains)}\n\n"
                f"Processing will start soon...",
                reply_markup=keyboard
            )
            
            # Start processing if not already running
            asyncio.create_task(process_queue())
    
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")
        await task_queue.clear_user_state(message.from_user.id)

@app.on_message(filters.command("skip"))
async def skip_command(client: Client, message: Message):
    """Skip password"""
    try:
        user_id = message.from_user.id
        state = await task_queue.get_user_state(user_id)
        
        if not state or state['state'] != 'waiting_password':
            return
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]
        ])
        
        await task_queue.set_user_state(user_id, 'waiting_domains', state['data'])
        
        await message.reply_text(
            "✅ Skipped password!\n"
            "Please send target domains (comma-separated):\n"
            "Example: `facebook.com, google.com`",
            reply_markup=keyboard
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: {str(e)}")

# ==============================================================================
#                            QUEUE PROCESSOR
# ==============================================================================

processing_lock = asyncio.Lock()

async def process_queue():
    """Process queue"""
    async with processing_lock:
        while True:
            task = await task_queue.get_next_task()
            if not task:
                break
            
            try:
                await process_task(task)
            except Exception as e:
                try:
                    await task['message'].reply_text(f"❌ Error processing: {str(e)}")
                except:
                    pass
            finally:
                await task_queue.complete_task(task['user_id'])

async def process_task(task: Dict):
    """Process a single task"""
    user_id = task['user_id']
    message = task['message']
    file_id = task['file_id']
    file_name = task['file_name']
    file_size = task['file_size']
    password = task.get('password')
    domains = task['domains']
    
    # Create directories
    unique_id = datetime.now().strftime('%H%M%S_%f')
    work_dir = f"work_{user_id}_{unique_id}"
    extract_dir = os.path.join(work_dir, "extracted")
    result_dir = os.path.join(work_dir, "results")
    os.makedirs(extract_dir, exist_ok=True)
    os.makedirs(result_dir, exist_ok=True)
    
    archive_path = os.path.join(work_dir, file_name)
    
    status_msg = None
    
    try:
        # Download
        status_msg = await message.reply_text("📥 Downloading archive...")
        start_time = time.time()
        
        await message.download(
            file_name=archive_path,
            progress=lambda c, t: asyncio.create_task(
                progress_callback(c, t, status_msg, start_time, "Downloading")
            )
        )
        
        # Check if cancelled
        if task.get('cancelled'):
            raise Exception("Task cancelled by user")
        
        # Extract
        await status_msg.edit_text("📦 Extracting archives...")
        
        extractor = ArchiveExtractor(password)
        
        async def extraction_progress(current, total):
            try:
                text = (
                    f"📦 **Extracting Archives**\n\n"
                    f"Progress: {current}/{total} archives\n"
                    f"Percentage: {(current/total*100):.1f}%"
                )
                await status_msg.edit_text(text)
            except:
                pass
        
        extractor.progress_callback = extraction_progress
        await extractor.extract_all_nested(archive_path, extract_dir)
        
        # Check if cancelled
        if task.get('cancelled'):
            raise Exception("Task cancelled by user")
        
        # Filter cookies
        await status_msg.edit_text(f"🔍 Filtering cookies for {len(domains)} domains...")
        
        cookie_extractor = CookieExtractor(domains)
        
        async def cookie_progress(current, total):
            try:
                text = (
                    f"🔍 **Filtering Cookies**\n\n"
                    f"Progress: {current}/{total} files\n"
                    f"Percentage: {(current/total*100):.1f}%\n"
                    f"Found: {cookie_extractor.total_found} entries"
                )
                await status_msg.edit_text(text)
            except:
                pass
        
        await cookie_extractor.process_all(extract_dir, cookie_progress)
        
        # Check if cancelled
        if task.get('cancelled'):
            raise Exception("Task cancelled by user")
        
        # Create ZIPs
        if cookie_extractor.total_found > 0:
            await status_msg.edit_text("📦 Creating ZIP archives...")
            created_zips = cookie_extractor.create_site_zips(extract_dir, result_dir)
            
            # Send results
            await status_msg.edit_text("📤 Sending results...")
            
            for site, zip_path in created_zips.items():
                if os.path.exists(zip_path):
                    file_size_zip = os.path.getsize(zip_path)
                    caption = (
                        f"🍪 **Cookies for {site}**\n\n"
                        f"📊 Entries: {len(cookie_extractor.site_files[site])}\n"
                        f"📏 Size: {format_size(file_size_zip)}"
                    )
                    
                    # Send to user
                    sent_msg = await message.reply_document(
                        zip_path,
                        caption=caption
                    )
                    
                    # Forward to logs
                    if SEND_LOGS:
                        try:
                            await sent_msg.forward(LOG_CHANNEL)
                        except:
                            pass
                    
                    # Delete file
                    try:
                        os.remove(zip_path)
                    except:
                        pass
            
            # Summary
            elapsed = time.time() - start_time
            summary = (
                f"✅ **Extraction Complete!**\n\n"
                f"⏱️ Time: `{format_time(elapsed)}`\n"
                f"📁 Files processed: `{cookie_extractor.files_processed}`\n"
                f"🍪 Entries found: `{cookie_extractor.total_found}`\n"
                f"📦 ZIP archives: `{len(created_zips)}`\n\n"
            )
            
            for site in domains:
                if site in cookie_extractor.site_files:
                    count = len(cookie_extractor.site_files[site])
                    if count > 0:
                        summary += f"✓ {site}: {count} files\n"
            
            await status_msg.edit_text(summary)
        else:
            await status_msg.edit_text("⚠️ No matching cookies found!")
    
    except Exception as e:
        if status_msg:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        else:
            await message.reply_text(f"❌ Error: {str(e)}")
    
    finally:
        # Cleanup
        try:
            delete_folder(work_dir)
        except:
            pass

# ==============================================================================
#                            MAIN
# ==============================================================================

if __name__ == "__main__":
    print("🤖 Starting Cookie Extractor Bot...")
    print(f"📊 Tools: UnRAR={'✅' if TOOL_STATUS['unrar'] else '❌'} | 7z={'✅' if TOOL_STATUS['7z'] else '❌'}")
    print(f"👤 Owner: @still_alivenow")
    app.run()
