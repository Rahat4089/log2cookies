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
import aiofiles
import aiohttp
import psutil
from datetime import datetime
from typing import List, Set, Dict, Optional, Tuple
import threading
import platform
import signal
import uuid
from pathlib import Path
import math

# Pyrofork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

# ==============================================================================
#                            CONFIGURATION
# ==============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAFzz3T1lU8KKQOyg2yHR5PsL5XkvQZCi54"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# Bot settings
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB (Telegram limit)
DOWNLOAD_PATH = "downloads"
EXTRACT_PATH = "extracted"
RESULTS_PATH = "results"
MAX_WORKERS = 50  # Threads for extraction
CHUNK_SIZE = 1024 * 1024  # 1MB chunks
BUFFER_SIZE = 20 * 1024 * 1024  # 20MB buffer

# Supported archives
SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# System detection
SYSTEM = platform.system().lower()

# Progress emojis
EMOJI = {
    'download': '📥',
    'extract': '📦',
    'filter': '🔍',
    'zip': '🗜️',
    'upload': '📤',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'info': 'ℹ️',
    'cancel': '🚫',
    'complete': '🎉'
}

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

def format_size(size_bytes: int) -> str:
    """Format size to human readable"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename"""
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_unique_id() -> str:
    """Generate unique ID for task"""
    return str(uuid.uuid4())[:8]

async def delete_folder_async(folder_path: str):
    """Delete folder asynchronously"""
    if not os.path.exists(folder_path):
        return
    
    def _delete():
        try:
            shutil.rmtree(folder_path, ignore_errors=True)
            time.sleep(0.5)
            if os.path.exists(folder_path):
                if SYSTEM == 'windows':
                    os.system(f'rmdir /s /q "{folder_path}"')
                else:
                    os.system(f'rm -rf "{folder_path}"')
        except:
            pass
    
    await asyncio.to_thread(_delete)

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

# ==============================================================================
#                            PASSWORD DETECTION
# ==============================================================================

class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    async def check_rar_protected(archive_path: str) -> bool:
        """Check RAR password protection"""
        if TOOL_STATUS['unrar']:
            try:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                output = stderr.decode().lower()
                return 'password' in output or 'encrypted' in output
            except:
                pass
        return True
    
    @staticmethod
    async def check_7z_protected(archive_path: str) -> bool:
        """Check 7z password protection"""
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                output = stdout.decode()
                return 'Encrypted' in output or 'Password' in output
            except:
                pass
        return True
    
    @staticmethod
    async def check_zip_protected(archive_path: str) -> bool:
        """Check ZIP password protection"""
        # Try with 7z first
        if TOOL_STATUS['7z']:
            try:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                output = stdout.decode()
                if 'Encrypted' in output or 'Password' in output:
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
#                            PROGRESS MANAGER
# ==============================================================================

class ProgressManager:
    """Manage progress messages for tasks"""
    
    def __init__(self, client: Client, message: Message, task_id: str):
        self.client = client
        self.message = message
        self.task_id = task_id
        self.last_update = 0
        self.update_interval = 1  # Update every second
    
    async def update_download(self, current: int, total: int, speed: str = ""):
        """Update download progress"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        percent = (current / total) * 100 if total else 0
        progress_bar = self._create_progress_bar(percent)
        downloaded = format_size(current)
        total_size = format_size(total)
        
        text = (
            f"{EMOJI['download']} **Downloading Archive**\n"
            f"Task ID: `{self.task_id}`\n\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"📊 {downloaded} / {total_size}\n"
        )
        if speed:
            text += f"⚡ Speed: {speed}\n"
        text += f"\n{EMOJI['cancel']} Send `/cancel_{self.task_id}` to cancel"
        
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def update_extract(self, current: int, total: int, status: str = "Extracting"):
        """Update extraction progress"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        percent = (current / total) * 100 if total else 0
        progress_bar = self._create_progress_bar(percent)
        
        text = (
            f"{EMOJI['extract']} **{status}**\n"
            f"Task ID: `{self.task_id}`\n\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"📊 Archives: {current}/{total}\n"
            f"\n{EMOJI['cancel']} Send `/cancel_{self.task_id}` to cancel"
        )
        
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def update_filter(self, files_processed: int, entries_found: Dict[str, int]):
        """Update filtering progress"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        
        text = f"{EMOJI['filter']} **Filtering Cookies**\nTask ID: `{self.task_id}`\n\n"
        text += f"📁 Files processed: {files_processed}\n"
        text += f"🔍 Total entries found: {sum(entries_found.values())}\n\n"
        
        for site, count in entries_found.items():
            if count > 0:
                text += f"• {site}: {count} entries\n"
        
        text += f"\n{EMOJI['cancel']} Send `/cancel_{self.task_id}` to cancel"
        
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def update_zip(self, current: int, total: int):
        """Update ZIP creation progress"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        percent = (current / total) * 100
        progress_bar = self._create_progress_bar(percent)
        
        text = (
            f"{EMOJI['zip']} **Creating Archives**\n"
            f"Task ID: `{self.task_id}`\n\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"📦 Zips: {current}/{total}\n"
        )
        
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def update_upload(self, current: int, total: int, filename: str):
        """Update upload progress"""
        now = time.time()
        if now - self.last_update < self.update_interval:
            return
        
        self.last_update = now
        percent = (current / total) * 100
        progress_bar = self._create_progress_bar(percent)
        uploaded = format_size(current)
        total_size = format_size(total)
        
        text = (
            f"{EMOJI['upload']} **Uploading**\n"
            f"Task ID: `{self.task_id}`\n\n"
            f"📄 File: `{filename}`\n"
            f"{progress_bar} {percent:.1f}%\n"
            f"📊 {uploaded} / {total_size}\n"
        )
        
        try:
            await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def complete(self, text: str):
        """Show completion message"""
        await self.message.edit_text(text, parse_mode=enums.ParseMode.MARKDOWN)
    
    def _create_progress_bar(self, percent: float, length: int = 20) -> str:
        """Create visual progress bar"""
        filled = int(length * percent / 100)
        bar = '█' * filled + '▒' * (length - filled)
        return f"`{bar}`"

# ==============================================================================
#                            ARCHIVE EXTRACTION
# ==============================================================================

class ArchiveExtractor:
    """Extract archives with optimal tools"""
    
    def __init__(self, password: Optional[str] = None, progress: Optional[ProgressManager] = None):
        self.password = password
        self.progress = progress
        self.processed_files: Set[str] = set()
        self.extracted_count = 0
        self.total_archives = 1
        self.stop_extraction = False
        self.lock = threading.Lock()
    
    async def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .7z using 7z.exe"""
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
            await process.communicate()
            
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
    
    async def extract_rar_with_unrar(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .rar using UnRAR.exe"""
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
            await process.communicate()
            
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
    
    async def extract_zip_fastest(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .zip using fastest method"""
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
                await process.communicate()
                
                if process.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files
            except:
                pass
        
        # Try unrar
        if TOOL_STATUS['unrar']:
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
                await process.communicate()
                
                if process.returncode == 0:
                    files = []
                    for root, _, filenames in os.walk(extract_dir):
                        for f in filenames:
                            rel_path = os.path.relpath(os.path.join(root, f), extract_dir)
                            files.append(rel_path)
                    return files
            except:
                pass
        
        # Fallback to zipfile
        try:
            def _extract():
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    if self.password:
                        zf.extractall(extract_dir, pwd=self.password.encode())
                    else:
                        zf.extractall(extract_dir)
                    return zf.namelist()
            
            return await asyncio.to_thread(_extract)
        except:
            return []
    
    async def extract_tar_fast(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract TAR/GZ/BZ2"""
        try:
            import tarfile
            
            def _extract():
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(extract_dir)
                    return tf.getnames()
            
            return await asyncio.to_thread(_extract)
        except:
            return []
    
    async def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract a single archive"""
        if self.stop_extraction:
            return []
        
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            if ext == '.7z' and TOOL_STATUS['7z']:
                return await self.extract_7z_with_7z(archive_path, extract_dir)
            elif ext == '.rar' and TOOL_STATUS['unrar']:
                return await self.extract_rar_with_unrar(archive_path, extract_dir)
            elif ext == '.zip':
                return await self.extract_zip_fastest(archive_path, extract_dir)
            else:
                return await self.extract_tar_fast(archive_path, extract_dir)
        except:
            return []
    
    def find_archives_fast(self, directory: str) -> List[str]:
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
    
    async def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        """Extract all nested archives"""
        current_level = {root_archive}
        level = 0
        self.total_archives = 1
        
        if self.progress:
            await self.progress.update_extract(0, self.total_archives, "Starting extraction...")
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            # Process archives in parallel
            tasks = []
            for archive in current_level:
                if archive in self.processed_files or self.stop_extraction:
                    continue
                
                archive_name = os.path.splitext(os.path.basename(archive))[0]
                archive_name = sanitize_filename(archive_name)[:50]
                extract_subdir = os.path.join(level_dir, archive_name)
                os.makedirs(extract_subdir, exist_ok=True)
                
                tasks.append(self._extract_and_find(archive, extract_subdir))
            
            if tasks:
                results = await asyncio.gather(*tasks)
                for new_archives in results:
                    next_level.update(new_archives)
                    
                    with self.lock:
                        self.total_archiles += len(new_archives)
                    
                    if self.progress:
                        await self.progress.update_extract(
                            len(self.processed_files), 
                            self.total_archives,
                            f"Extracting level {level}"
                        )
            
            current_level = next_level
            level += 1
        
        return base_dir
    
    async def _extract_and_find(self, archive: str, extract_dir: str) -> Set[str]:
        """Extract and find new archives"""
        try:
            extracted = await self.extract_single(archive, extract_dir)
            with self.lock:
                self.processed_files.add(archive)
                self.extracted_count += 1
            
            # Find new archives in extracted content
            new_archives = set()
            for root, _, files in os.walk(extract_dir):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_ARCHIVES:
                        new_archives.add(os.path.join(root, file))
            
            return new_archives
        except:
            return set()

# ==============================================================================
#                            COOKIE EXTRACTOR
# ==============================================================================

class CookieExtractor:
    """Extract and filter cookies by domain"""
    
    def __init__(self, target_sites: List[str], progress: Optional[ProgressManager] = None):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.progress = progress
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.site_entries: Dict[str, int] = {site: 0 for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.files_processed = 0
        self.total_found = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.lock = threading.Lock()
        
        # Pre-compile patterns
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
    
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
        """Find all cookie files"""
        cookie_files = []
        
        for root, _, files in os.walk(extract_dir):
            if any(folder in root for folder in COOKIE_FOLDERS):
                for file in files:
                    if file.endswith(('.txt', '.txt.bak')):
                        cookie_files.append((os.path.join(root, file), file))
        
        return cookie_files
    
    def get_unique_filename(self, site: str, orig_name: str) -> str:
        """Generate unique filename"""
        base, ext = os.path.splitext(orig_name)
        
        with self.lock:
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
    
    async def process_file(self, file_path: str, orig_name: str, extract_dir: str):
        """Process a single file"""
        if self.stop_processing:
            return
        
        try:
            # Read file
            async with aiofiles.open(file_path, 'rb', buffering=BUFFER_SIZE) as f:
                content = await f.read()
                lines = content.split(b'\n')
            
            file_hash = get_file_hash_fast(file_path)
            
            # Collect matches per site
            site_matches: Dict[str, List[str]] = {site: [] for site in self.target_sites}
            
            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        unique_id = f"{site}|{file_hash}|{line_num}"
                        
                        with self.lock:
                            if unique_id not in self.global_seen:
                                self.global_seen.add(unique_id)
                                site_matches[site].append(line_str)
                                self.site_entries[site] += 1
                                self.total_found += 1
            
            # Save files for each site
            for site, matches in site_matches.items():
                if matches:
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    
                    async with aiofiles.open(out_path, 'w', encoding='utf-8') as f:
                        await f.write('\n'.join(matches))
                    
                    with self.lock:
                        self.site_files[site][out_path] = unique_name
            
            with self.lock:
                self.files_processed += 1
            
            # Update progress
            if self.progress:
                await self.progress.update_filter(self.files_processed, self.site_entries)
                
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    async def process_all(self, extract_dir: str):
        """Process all cookie files"""
        cookie_files = self.find_cookie_files(extract_dir)
        
        if not cookie_files:
            return
        
        # Process files in parallel
        tasks = []
        for file_path, orig_name in cookie_files[:100]:  # Limit to 100 files at a time
            if self.stop_processing:
                break
            tasks.append(self.process_file(file_path, orig_name, extract_dir))
            
            if len(tasks) >= 20:  # Process in batches of 20
                await asyncio.gather(*tasks)
                tasks = []
        
        if tasks:
            await asyncio.gather(*tasks)
    
    async def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        """Create ZIP archives per site"""
        created_zips = {}
        total_sites = len([s for s in self.site_files if self.site_files[s]])
        
        for idx, (site, files_dict) in enumerate(self.site_files.items(), 1):
            if not files_dict or self.stop_processing:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            # Create ZIP
            def _create_zip():
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                    for file_path, unique_name in files_dict.items():
                        if os.path.exists(file_path):
                            zf.write(file_path, unique_name)
            
            await asyncio.to_thread(_create_zip)
            created_zips[site] = zip_path
            
            if self.progress:
                await self.progress.update_zip(idx, total_sites)
        
        return created_zips

# ==============================================================================
#                            TASK MANAGER
# ==============================================================================

class TaskManager:
    """Manage user tasks"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self.user_tasks: Dict[int, str] = {}  # user_id -> task_id
    
    def create_task(self, user_id: int, message: Message) -> str:
        """Create new task"""
        # Cancel existing task for user
        if user_id in self.user_tasks:
            self.cancel_task(self.user_tasks[user_id])
        
        task_id = generate_unique_id()
        self.tasks[task_id] = {
            'user_id': user_id,
            'message': message,
            'created_at': time.time(),
            'status': 'created',
            'cancel': False,
            'data': {}
        }
        self.user_tasks[user_id] = task_id
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_user_task(self, user_id: int) -> Optional[str]:
        """Get active task ID for user"""
        return self.user_tasks.get(user_id)
    
    def cancel_task(self, task_id: str):
        """Cancel task"""
        if task_id in self.tasks:
            self.tasks[task_id]['cancel'] = True
            self.tasks[task_id]['status'] = 'cancelled'
            
            # Remove from user_tasks if matches
            user_id = self.tasks[task_id]['user_id']
            if user_id in self.user_tasks and self.user_tasks[user_id] == task_id:
                del self.user_tasks[user_id]
    
    def complete_task(self, task_id: str):
        """Mark task as completed"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = 'completed'
            
            # Remove from user_tasks
            user_id = self.tasks[task_id]['user_id']
            if user_id in self.user_tasks and self.user_tasks[user_id] == task_id:
                del self.user_tasks[user_id]
    
    def cleanup_old_tasks(self, max_age: int = 3600):
        """Clean up tasks older than max_age seconds"""
        now = time.time()
        to_delete = []
        
        for task_id, task in self.tasks.items():
            if now - task['created_at'] > max_age:
                to_delete.append(task_id)
                
                # Remove from user_tasks
                user_id = task['user_id']
                if user_id in self.user_tasks and self.user_tasks[user_id] == task_id:
                    del self.user_tasks[user_id]
        
        for task_id in to_delete:
            del self.tasks[task_id]

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
        self.task_manager = TaskManager()
        self.start_time = datetime.now()
        
        # Create directories
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        os.makedirs(EXTRACT_PATH, exist_ok=True)
        os.makedirs(RESULTS_PATH, exist_ok=True)
    
    async def log_message(self, text: str):
        """Send log to log channel"""
        if not SEND_LOGS or not LOG_CHANNEL:
            return
        
        try:
            await self.app.send_message(LOG_CHANNEL, text, parse_mode=enums.ParseMode.MARKDOWN)
        except:
            pass
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = (
            f"{EMOJI['info']} **Welcome to Cookie Extractor Bot!**\n\n"
            "I can extract cookies from archive files and filter them by domain.\n\n"
            "**How to use:**\n"
            "1️⃣ Send me an archive file (.zip, .rar, .7z)\n"
            "2️⃣ Or use `/link <direct_download_url>`\n"
            "3️⃣ I'll ask for password (if protected)\n"
            "4️⃣ Send domains separated by commas\n"
            "5️⃣ Wait for processing\n\n"
            "**Features:**\n"
            "• Supports ZIP, RAR, 7Z, TAR, GZ, BZ2\n"
            "• Nested archive extraction\n"
            "• Per-domain cookie filtering\n"
            "• Cancel with `/cancel_TASK_ID`\n\n"
            f"**Tools:**\n"
            f"• UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}\n"
            f"• 7-Zip: {'✅' if TOOL_STATUS['7z'] else '❌'}\n\n"
            "Send a file to get started!"
        )
        
        await message.reply_text(welcome_text, parse_mode=enums.ParseMode.MARKDOWN)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        parts = message.text.split()
        
        if len(parts) != 2:
            await message.reply_text(
                f"{EMOJI['warning']} Usage: `/cancel_TASK_ID`\n"
                "Example: `/cancel_a1b2c3d4`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        task_id = parts[0].replace('/cancel_', '').strip()
        task = self.task_manager.get_task(task_id)
        
        if not task:
            await message.reply_text(
                f"{EMOJI['error']} Task not found or already completed!",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        if task['user_id'] != message.from_user.id and message.from_user.id not in ADMINS:
            await message.reply_text(
                f"{EMOJI['error']} You don't have permission to cancel this task!",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        self.task_manager.cancel_task(task_id)
        
        # Update progress message
        try:
            await task['message'].edit_text(
                f"{EMOJI['cancel']} **Task Cancelled**\n"
                f"Task ID: `{task_id}`\n\n"
                "Processing has been stopped and files will be cleaned up.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        except:
            pass
        
        await message.reply_text(
            f"{EMOJI['success']} Task cancelled successfully!",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    async def link_command(self, client: Client, message: Message):
        """Handle /link command for direct downloads"""
        parts = message.text.split(maxsplit=1)
        
        if len(parts) != 2:
            await message.reply_text(
                f"{EMOJI['warning']} Usage: `/link <direct_download_url>`\n"
                "Example: `/link https://example.com/file.zip`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        url = parts[1].strip()
        
        # Check if user has active task
        user_id = message.from_user.id
        existing_task_id = self.task_manager.get_user_task(user_id)
        if existing_task_id:
            await message.reply_text(
                f"{EMOJI['warning']} You already have an active task!\n"
                f"Send `/cancel_{existing_task_id}` to cancel it first.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Create progress message
        progress_msg = await message.reply_text(
            f"{EMOJI['info']} Processing your request...",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Create task
        task_id = self.task_manager.create_task(user_id, progress_msg)
        
        # Start processing
        asyncio.create_task(self.process_download_url(task_id, user_id, url, progress_msg))
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document/file uploads"""
        if not message.document:
            return
        
        # Check file extension
        file_name = message.document.file_name or "unknown"
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"{EMOJI['error']} Unsupported file type!\n"
                f"Supported: {', '.join(SUPPORTED_ARCHIVES)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Check file size
        file_size = message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(
                f"{EMOJI['error']} File too large!\n"
                f"Max size: {format_size(MAX_FILE_SIZE)}",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Check if user has active task
        user_id = message.from_user.id
        existing_task_id = self.task_manager.get_user_task(user_id)
        if existing_task_id:
            await message.reply_text(
                f"{EMOJI['warning']} You already have an active task!\n"
                f"Send `/cancel_{existing_task_id}` to cancel it first.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Create progress message
        progress_msg = await message.reply_text(
            f"{EMOJI['info']} Processing your file...",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Create task
        task_id = self.task_manager.create_task(user_id, progress_msg)
        
        # Start processing
        asyncio.create_task(self.process_uploaded_file(task_id, user_id, message, progress_msg))
    
    async def process_download_url(self, task_id: str, user_id: int, url: str, progress_msg: Message):
        """Process direct download URL"""
        task = self.task_manager.get_task(task_id)
        if not task or task['cancel']:
            return
        
        progress = ProgressManager(self.app, progress_msg, task_id)
        
        try:
            # Download file
            file_path = await self.download_from_url(url, progress)
            if not file_path or task['cancel']:
                return
            
            # Continue with processing
            await self.process_archive(task_id, user_id, file_path, progress)
            
        except Exception as e:
            await progress.complete(f"{EMOJI['error']} **Error:** {str(e)}")
            await self.log_message(f"Error in task {task_id}: {str(e)}")
        finally:
            # Cleanup
            self.task_manager.complete_task(task_id)
    
    async def process_uploaded_file(self, task_id: str, user_id: int, message: Message, progress_msg: Message):
        """Process uploaded file"""
        task = self.task_manager.get_task(task_id)
        if not task or task['cancel']:
            return
        
        progress = ProgressManager(self.app, progress_msg, task_id)
        
        try:
            # Download file from Telegram
            file_path = await self.download_from_telegram(message, progress)
            if not file_path or task['cancel']:
                return
            
            # Continue with processing
            await self.process_archive(task_id, user_id, file_path, progress)
            
        except Exception as e:
            await progress.complete(f"{EMOJI['error']} **Error:** {str(e)}")
            await self.log_message(f"Error in task {task_id}: {str(e)}")
        finally:
            # Cleanup
            self.task_manager.complete_task(task_id)
    
    async def download_from_telegram(self, message: Message, progress: ProgressManager) -> Optional[str]:
        """Download file from Telegram"""
        task_id = progress.task_id
        task = self.task_manager.get_task(task_id)
        
        # Create download path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = message.document.file_name or f"archive_{timestamp}"
        safe_name = sanitize_filename(file_name)
        download_path = os.path.join(DOWNLOAD_PATH, f"{task_id}_{safe_name}")
        
        try:
            # Download with progress
            c_time = time.time()
            last_update = 0
            downloaded = 0
            
            async def progress_callback(current, total):
                nonlocal last_update, downloaded
                downloaded = current
                
                if task and task['cancel']:
                    raise Exception("Task cancelled")
                
                # Calculate speed
                now = time.time()
                elapsed = now - c_time
                speed = format_size(current / elapsed) + "/s" if elapsed > 0 else ""
                
                await progress.update_download(current, total, speed)
                last_update = now
            
            await message.download(file_name=download_path, progress=progress_callback)
            
            if task and task['cancel']:
                os.remove(download_path)
                await progress.complete(f"{EMOJI['cancel']} **Download Cancelled**")
                return None
            
            return download_path
            
        except Exception as e:
            if os.path.exists(download_path):
                os.remove(download_path)
            if "Task cancelled" not in str(e):
                raise
            return None
    
    async def download_from_url(self, url: str, progress: ProgressManager) -> Optional[str]:
        """Download file from URL"""
        task_id = progress.task_id
        task = self.task_manager.get_task(task_id)
        
        # Create download path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_name = url.split('/')[-1].split('?')[0] or f"archive_{timestamp}"
        safe_name = sanitize_filename(file_name)
        download_path = os.path.join(DOWNLOAD_PATH, f"{task_id}_{safe_name}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise Exception(f"HTTP {response.status}")
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    c_time = time.time()
                    
                    async with aiofiles.open(download_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                            if task and task['cancel']:
                                raise Exception("Task cancelled")
                            
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Update progress
                            elapsed = time.time() - c_time
                            speed = format_size(downloaded / elapsed) + "/s" if elapsed > 0 else ""
                            await progress.update_download(downloaded, total_size, speed)
            
            if task and task['cancel']:
                os.remove(download_path)
                await progress.complete(f"{EMOJI['cancel']} **Download Cancelled**")
                return None
            
            return download_path
            
        except Exception as e:
            if os.path.exists(download_path):
                os.remove(download_path)
            if "Task cancelled" not in str(e):
                raise
            return None
    
    async def process_archive(self, task_id: str, user_id: int, archive_path: str, progress: ProgressManager):
        """Process archive file"""
        task = self.task_manager.get_task(task_id)
        if not task or task['cancel']:
            return
        
        # Check if password protected
        ext = os.path.splitext(archive_path)[1].lower()
        is_protected = False
        
        if ext == '.rar':
            is_protected = await PasswordDetector.check_rar_protected(archive_path)
        elif ext == '.7z':
            is_protected = await PasswordDetector.check_7z_protected(archive_path)
        elif ext == '.zip':
            is_protected = await PasswordDetector.check_zip_protected(archive_path)
        
        password = None
        if is_protected:
            # Ask for password
            await progress.complete(
                f"{EMOJI['warning']} **Archive is password protected**\n\n"
                f"Please send the password as a message.\n"
                f"Task ID: `{task_id}`"
            )
            
            # Wait for password
            password = await self.wait_for_password(user_id, task_id)
            if not password or task['cancel']:
                return
            
            # Update progress message
            await progress.complete(
                f"{EMOJI['info']} Password received. Processing...\n"
                f"Task ID: `{task_id}`"
            )
        else:
            await progress.complete(
                f"{EMOJI['success']} Archive is not password protected.\n"
                f"Task ID: `{task_id}`"
            )
        
        # Ask for domains
        await progress.complete(
            f"{EMOJI['info']} **Enter domains to filter**\n\n"
            f"Send domains separated by commas\n"
            f"Example: `google.com, facebook.com, twitter.com`\n\n"
            f"Task ID: `{task_id}`"
        )
        
        # Wait for domains
        domains = await self.wait_for_domains(user_id, task_id)
        if not domains or task['cancel']:
            return
        
        target_sites = [d.strip().lower() for d in domains.split(',') if d.strip()]
        
        if not target_sites:
            await progress.complete(f"{EMOJI['error']} No valid domains provided!")
            return
        
        # Create unique folder for this task
        unique_folder = os.path.join(EXTRACT_PATH, task_id)
        os.makedirs(unique_folder, exist_ok=True)
        
        result_folder = os.path.join(RESULTS_PATH, datetime.now().strftime('%Y-%m-%d'))
        os.makedirs(result_folder, exist_ok=True)
        
        try:
            # STEP 1: Extract archives
            extractor = ArchiveExtractor(password, progress)
            await progress.update_extract(0, 1, "Starting extraction...")
            
            extract_dir = await extractor.extract_all_nested(archive_path, unique_folder)
            
            if task['cancel']:
                await progress.complete(f"{EMOJI['cancel']} **Extraction Cancelled**")
                return
            
            # STEP 2: Filter cookies
            cookie_extractor = CookieExtractor(target_sites, progress)
            await progress.update_filter(0, cookie_extractor.site_entries)
            
            await cookie_extractor.process_all(extract_dir)
            
            if task['cancel']:
                await progress.complete(f"{EMOJI['cancel']} **Filtering Cancelled**")
                return
            
            # STEP 3: Create ZIPs
            if cookie_extractor.total_found > 0:
                await progress.update_zip(0, len(target_sites))
                
                created_zips = await cookie_extractor.create_site_zips(extract_dir, result_folder)
                
                if task['cancel']:
                    await progress.complete(f"{EMOJI['cancel']} **ZIP Creation Cancelled**")
                    return
                
                # STEP 4: Upload files
                await self.upload_results(user_id, created_zips, cookie_extractor, progress, task_id)
                
            else:
                await progress.complete(
                    f"{EMOJI['warning']} **No cookies found**\n\n"
                    f"No matching cookies found for the specified domains."
                )
            
        finally:
            # Cleanup
            await delete_folder_async(unique_folder)
            if os.path.exists(archive_path):
                os.remove(archive_path)
    
    async def wait_for_password(self, user_id: int, task_id: str, timeout: int = 120) -> Optional[str]:
        """Wait for user to send password"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return None
        
        # Create future for password
        future = asyncio.Future()
        task['data']['password_future'] = future
        
        try:
            password = await asyncio.wait_for(future, timeout=timeout)
            return password
        except asyncio.TimeoutError:
            if task and not task['cancel']:
                task['cancel'] = True
                await task['message'].edit_text(
                    f"{EMOJI['error']} **Timeout**\n\n"
                    f"Password not received within {timeout} seconds.",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            return None
        finally:
            if 'password_future' in task['data']:
                del task['data']['password_future']
    
    async def wait_for_domains(self, user_id: int, task_id: str, timeout: int = 120) -> Optional[str]:
        """Wait for user to send domains"""
        task = self.task_manager.get_task(task_id)
        if not task:
            return None
        
        # Create future for domains
        future = asyncio.Future()
        task['data']['domains_future'] = future
        
        try:
            domains = await asyncio.wait_for(future, timeout=timeout)
            return domains
        except asyncio.TimeoutError:
            if task and not task['cancel']:
                task['cancel'] = True
                await task['message'].edit_text(
                    f"{EMOJI['error']} **Timeout**\n\n"
                    f"Domains not received within {timeout} seconds.",
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            return None
        finally:
            if 'domains_future' in task['data']:
                del task['data']['domains_future']
    
    async def handle_text_message(self, client: Client, message: Message):
        """Handle text messages (password or domains)"""
        user_id = message.from_user.id
        text = message.text.strip()
        
        # Check if user has active task
        task_id = self.task_manager.get_user_task(user_id)
        if not task_id:
            return
        
        task = self.task_manager.get_task(task_id)
        if not task or task['cancel']:
            return
        
        # Check if waiting for password
        if 'password_future' in task['data'] and not task['data']['password_future'].done():
            task['data']['password_future'].set_result(text)
            await message.reply_text(f"{EMOJI['success']} Password received! Processing...")
            return
        
        # Check if waiting for domains
        if 'domains_future' in task['data'] and not task['data']['domains_future'].done():
            task['data']['domains_future'].set_result(text)
            await message.reply_text(f"{EMOJI['success']} Domains received! Starting extraction...")
            return
    
    async def upload_results(self, user_id: int, created_zips: Dict[str, str], 
                           cookie_extractor: CookieExtractor, progress: ProgressManager, task_id: str):
        """Upload result files to user"""
        task = self.task_manager.get_task(task_id)
        if not task or task['cancel']:
            return
        
        # Show summary
        summary = (
            f"{EMOJI['complete']} **Processing Complete!**\n"
            f"Task ID: `{task_id}`\n\n"
            f"📁 Files processed: {cookie_extractor.files_processed}\n"
            f"🔍 Total entries: {cookie_extractor.total_found}\n"
            f"📦 ZIP archives: {len(created_zips)}\n\n"
            f"**Per-domain stats:**\n"
        )
        
        for site in cookie_extractor.target_sites:
            if site in cookie_extractor.site_files:
                count = len(cookie_extractor.site_files[site])
                entries = cookie_extractor.site_entries.get(site, 0)
                if count > 0:
                    summary += f"• {site}: {count} files ({entries} entries)\n"
        
        summary += f"\n{EMOJI['upload']} **Uploading files...**"
        
        await progress.complete(summary)
        
        # Upload each ZIP
        for site, zip_path in created_zips.items():
            if task['cancel']:
                break
            
            file_size = os.path.getsize(zip_path)
            
            # Update progress for upload
            await progress.update_upload(0, file_size, os.path.basename(zip_path))
            
            # Upload with progress
            c_time = time.time()
            
            async def progress_callback(current, total):
                if task['cancel']:
                    raise Exception("Task cancelled")
                
                await progress.update_upload(current, total, os.path.basename(zip_path))
            
            try:
                await client.send_document(
                    user_id,
                    zip_path,
                    caption=f"**{site}**\nFiles: {len(cookie_extractor.site_files[site])}\nEntries: {cookie_extractor.site_entries.get(site, 0)}",
                    parse_mode=enums.ParseMode.MARKDOWN,
                    progress=progress_callback
                )
            except Exception as e:
                await client.send_message(
                    user_id,
                    f"{EMOJI['error']} Error uploading {site}: {str(e)}"
                )
        
        # Send final message
        await client.send_message(
            user_id,
            f"{EMOJI['success']} **All files uploaded successfully!**\n\n"
            f"Task ID: `{task_id}` completed.\n"
            f"Total processing time: {format_time(time.time() - task['created_at'])}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        # Update progress message
        await progress.complete(
            f"{EMOJI['success']} **Task Completed!**\n"
            f"Task ID: `{task_id}`\n"
            f"Total time: {format_time(time.time() - task['created_at'])}"
        )
        
        # Log completion
        await self.log_message(
            f"✅ Task completed\n"
            f"User: {user_id}\n"
            f"Task: {task_id}\n"
            f"Files: {cookie_extractor.files_processed}\n"
            f"Entries: {cookie_extractor.total_found}\n"
            f"Zips: {len(created_zips)}"
        )
    
    async def status_command(self, client: Client, message: Message):
        """Show bot status"""
        # Get system info
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Count active tasks
        active_tasks = sum(1 for t in self.task_manager.tasks.values() 
                          if t['status'] in ['created', 'processing'])
        
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]
        
        status_text = (
            f"**Bot Status**\n\n"
            f"**System:**\n"
            f"• CPU: {cpu_percent}%\n"
            f"• RAM: {memory.percent}% ({format_size(memory.used)}/{format_size(memory.total)})\n"
            f"• Disk: {disk.percent}% ({format_size(disk.used)}/{format_size(disk.total)})\n\n"
            f"**Bot:**\n"
            f"• Uptime: {uptime_str}\n"
            f"• Active tasks: {active_tasks}\n"
            f"• Total tasks: {len(self.task_manager.tasks)}\n\n"
            f"**Tools:**\n"
            f"• UnRAR: {'✅' if TOOL_STATUS['unrar'] else '❌'}\n"
            f"• 7-Zip: {'✅' if TOOL_STATUS['7z'] else '❌'}"
        )
        
        await message.reply_text(status_text, parse_mode=enums.ParseMode.MARKDOWN)
    
    async def cleanup_command(self, client: Client, message: Message):
        """Manual cleanup (admin only)"""
        if message.from_user.id not in ADMINS:
            await message.reply_text(f"{EMOJI['error']} Admin only!")
            return
        
        # Clean old tasks
        self.task_manager.cleanup_old_tasks()
        
        # Clean old files
        cleaned = 0
        for folder in [DOWNLOAD_PATH, EXTRACT_PATH]:
            if os.path.exists(folder):
                for item in os.listdir(folder):
                    item_path = os.path.join(folder, item)
                    try:
                        if os.path.isfile(item_path):
                            # Delete files older than 1 hour
                            if time.time() - os.path.getmtime(item_path) > 3600:
                                os.remove(item_path)
                                cleaned += 1
                        elif os.path.isdir(item_path):
                            # Delete folders older than 1 hour
                            if time.time() - os.path.getmtime(item_path) > 3600:
                                shutil.rmtree(item_path, ignore_errors=True)
                                cleaned += 1
                    except:
                        pass
        
        await message.reply_text(
            f"{EMOJI['success']} Cleanup completed!\n"
            f"Removed {cleaned} items.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    def run(self):
        """Run the bot"""
        print(f"Starting Cookie Extractor Bot...")
        print(f"Tools: UnRAR={'✓' if TOOL_STATUS['unrar'] else '✗'} 7-Zip={'✓' if TOOL_STATUS['7z'] else '✗'}")
        
        # Register handlers
        self.app.on_message(filters.command("start"))(self.start_command)
        self.app.on_message(filters.command("link"))(self.link_command)
        self.app.on_message(filters.command("status"))(self.status_command)
        self.app.on_message(filters.command("cleanup"))(self.cleanup_command)
        self.app.on_message(filters.regex(r"^/cancel_"))(self.cancel_command)
        self.app.on_message(filters.document)(self.handle_document)
        self.app.on_message(filters.text & ~filters.command(["start", "link", "status", "cleanup"]))(self.handle_text_message)
        
        # Start bot
        self.app.run()

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    bot = CookieExtractorBot()
    bot.run()
