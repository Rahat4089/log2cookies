#!/usr/bin/env python3

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
import threading
import platform
import asyncio
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Set, Dict, Optional, Tuple
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message, Document
from pyrogram.errors import FloodWait
import aiohttp

# ============================================================================
#                            CONFIGURATION
# ============================================================================

API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAFzz3T1lU8KKQOyg2yHR5PsL5XkvQZCi54"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]

# Speed Settings
MAX_WORKERS = 50
BUFFER_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

# System detection
SYSTEM = platform.system().lower()

# Directories
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
EXTRACT_DIR = BASE_DIR / "extracted"
RESULTS_DIR = BASE_DIR / "results"
LOG_DIR = BASE_DIR / "logs"

for d in [DOWNLOAD_DIR, EXTRACT_DIR, RESULTS_DIR, LOG_DIR]:
    d.mkdir(exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# User tasks tracking
user_tasks: Dict[str, dict] = {}
task_lock = threading.Lock()

# ============================================================================
#                            TOOL DETECTION
# ============================================================================

class ToolDetector:
    """Detect available external tools"""
    
    @staticmethod
    def check_unrar() -> bool:
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
        if tool_name == 'unrar':
            if SYSTEM == 'windows':
                paths = ['C:\\Program Files\\WinRAR\\UnRAR.exe', 'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe']
                for path in paths:
                    if os.path.exists(path):
                        return path
                return 'unrar.exe'
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else 'unrar'
        
        elif tool_name == '7z':
            if SYSTEM == 'windows':
                paths = ['C:\\Program Files\\7-Zip\\7z.exe', 'C:\\Program Files (x86)\\7-Zip\\7z.exe']
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

TOOL_STATUS = {
    'unrar': ToolDetector.check_unrar(),
    '7z': ToolDetector.check_7z(),
}

TOOL_PATHS = {
    'unrar': ToolDetector.get_tool_path('unrar') if TOOL_STATUS['unrar'] else None,
    '7z': ToolDetector.get_tool_path('7z') if TOOL_STATUS['7z'] else None,
}

# ============================================================================
#                            UTILITY FUNCTIONS
# ============================================================================

def sanitize_filename(filename: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_unique_id() -> str:
    return datetime.now().strftime('%H%M%S') + ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

def get_file_hash_fast(filepath: str) -> str:
    try:
        with open(filepath, 'rb', buffering=BUFFER_SIZE) as f:
            first = f.read(1024)
            f.seek(-1024, 2)
            last = f.read(1024)
            return hashlib.md5(first + last).hexdigest()[:8]
    except:
        return str(os.path.getmtime(filepath))

def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"

def delete_folder(folder_path: str) -> bool:
    if not os.path.exists(folder_path):
        return True
    try:
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

# ============================================================================
#                            PASSWORD DETECTION
# ============================================================================

class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    def check_rar_protected(archive_path: str) -> bool:
        try:
            if TOOL_STATUS['unrar']:
                cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                return 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower()
        except:
            pass
        return True
    
    @staticmethod
    def check_7z_protected(archive_path: str) -> bool:
        try:
            if TOOL_STATUS['7z']:
                cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                return 'Encrypted' in result.stdout or 'Password' in result.stdout
        except:
            pass
        return True
    
    @staticmethod
    def check_zip_protected(archive_path: str) -> bool:
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
            return True

# ============================================================================
#                            ARCHIVE EXTRACTION
# ============================================================================

class ArchiveExtractor:
    """Archive extraction with optimal tool selection"""
    
    def __init__(self, password: Optional[str] = None, update_callback=None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.stop_extraction = False
        self.update_callback = update_callback
    
    async def _update_status(self, text: str):
        if self.update_callback:
            await self.update_callback(text)
    
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
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
        try:
            import tarfile
            with tarfile.open(archive_path, 'r:*') as tf:
                tf.extractall(extract_dir)
                return tf.getnames()
        except:
            return []
    
    def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        if self.stop_extraction:
            return []
        
        ext = os.path.splitext(archive_path)[1].lower()
        
        try:
            if ext == '.7z':
                if TOOL_STATUS['7z']:
                    return self.extract_7z_with_7z(archive_path, extract_dir)
            elif ext == '.rar':
                if TOOL_STATUS['unrar']:
                    return self.extract_rar_with_unrar(archive_path, extract_dir)
            elif ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            else:
                return self.extract_tar_fast(archive_path, extract_dir)
        except:
            pass
        
        return []
    
    def find_archives_fast(self, directory: str) -> List[str]:
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
        total_archives = 1
        extracted_count = 0
        
        while current_level and not self.stop_extraction:
            next_level = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {}
                for archive in current_level:
                    if archive in self.processed_files or self.stop_extraction:
                        continue
                    
                    archive_name = sanitize_filename(os.path.splitext(os.path.basename(archive))[0])[:50]
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
                            extracted_count += 1
                        
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                        
                        await self._update_status(f"📦 Extracted: {extracted_count} archives")
                    except:
                        pass
            
            current_level = next_level
            level += 1
        
        return base_dir

# ============================================================================
#                            COOKIE EXTRACTION
# ============================================================================

class CookieExtractor:
    """Cookie extraction with per-site filtering"""
    
    def __init__(self, target_sites: List[str], update_callback=None):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.stop_processing = False
        self.update_callback = update_callback
        self.site_patterns = {site: re.compile(site.encode()) for site in self.target_sites}
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
    
    async def _update_status(self, text: str):
        if self.update_callback:
            await self.update_callback(text)
    
    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
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
        
        except:
            pass
    
    async def process_all(self, extract_dir: str):
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
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
                completed += 1
                await self._update_status(f"🔍 Processing: {completed}/{len(cookie_files)} files | Found: {self.total_found}")
    
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

# ============================================================================
#                            PYROGRAM BOT
# ============================================================================

class CookieBot:
    def __init__(self):
        self.app = Client(
            "cookie_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            workers=4
        )
        
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.app.on_message(filters.command("start") & filters.private)
        async def start(client, message: Message):
            await message.reply(
                "🤖 **Cookie Extractor Bot**\n\n"
                "📌 **How to use:**\n"
                "1️⃣ Forward a .zip/.rar/.7z archive or send `/link <url>`\n"
                "2️⃣ Answer if it's password protected\n"
                "3️⃣ Provide domains to extract (comma-separated)\n"
                "4️⃣ Get filtered cookie files as ZIP\n\n"
                "⚙️ **Available commands:**\n"
                "/start - Show this menu\n"
                "/cancel_[ID] - Cancel current task\n\n"
                "🔧 **Tools:** 7z.exe=" + ("✓" if TOOL_STATUS['7z'] else "✗") + 
                " | UnRAR.exe=" + ("✓" if TOOL_STATUS['unrar'] else "✗"),
                quote=True
            )
        
        @self.app.on_message(filters.document & filters.private)
        async def handle_archive(client, message: Message):
            await self._process_archive(client, message)
        
        @self.app.on_message(filters.command("link") & filters.private)
        async def handle_link(client, message: Message):
            await self._process_link(client, message)
    
    async def _process_archive(self, client: Client, message: Message):
        """Handle archive file upload"""
        user_id = message.from_user.id
        task_id = generate_unique_id()
        
        with task_lock:
            if user_id in user_tasks:
                return await message.reply("⏳ You already have a running task. Use /cancel_[ID] to stop it.", quote=True)
            
            user_tasks[user_id] = {
                'id': task_id,
                'status': 'downloading',
                'message': message.id,
                'status_msg': None
            }
        
        try:
            status = await message.reply(f"⏳ Task ID: `{task_id}`\n⬇️ Downloading archive...")
            
            with task_lock:
                user_tasks[user_id]['status_msg'] = status.id
            
            # Download file
            user_dir = DOWNLOAD_DIR / str(user_id) / task_id
            user_dir.mkdir(parents=True, exist_ok=True)
            archive_path = await client.download_media(message.document, file_name=str(user_dir / message.document.file_name))
            
            if not archive_path:
                await status.edit("❌ Failed to download archive")
                with task_lock:
                    user_tasks.pop(user_id, None)
                return
            
            file_size = format_size(os.path.getsize(archive_path))
            await status.edit(f"✓ Downloaded: {file_size}\n\n🔍 Checking password protection...")
            
            # Check password
            ext = Path(archive_path).suffix.lower()
            is_protected = False
            
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(archive_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(archive_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(archive_path)
            
            if is_protected:
                await status.edit(f"✓ Downloaded: {file_size}\n\n🔐 Archive is password protected.\n🔑 Send password (or /skip to continue):")
                
                # Wait for password
                try:
                    pass_msg = await client.listen(filters.text & filters.user(user_id), timeout=300)
                    password = None if pass_msg.text.lower() == '/skip' else pass_msg.text
                except:
                    with task_lock:
                        user_tasks.pop(user_id, None)
                    return await status.edit("❌ Timeout. Task cancelled.")
            else:
                password = None
                await status.edit(f"✓ Downloaded: {file_size}\n\n✓ Not password protected\n🎯 Send domains (comma-separated):")
            
            # Get domains
            if is_protected:
                try:
                    domains_msg = await client.listen(filters.text & filters.user(user_id), timeout=300)
                    domains = domains_msg.text
                except:
                    with task_lock:
                        user_tasks.pop(user_id, None)
                    return await status.edit("❌ Timeout. Task cancelled.")
            else:
                try:
                    domains_msg = await client.listen(filters.text & filters.user(user_id), timeout=300)
                    domains = domains_msg.text
                except:
                    with task_lock:
                        user_tasks.pop(user_id, None)
                    return await status.edit("❌ Timeout. Task cancelled.")
            
            target_sites = [s.strip().lower() for s in domains.split(',') if s.strip()]
            if not target_sites:
                await status.edit("❌ No domains specified")
                with task_lock:
                    user_tasks.pop(user_id, None)
                return
            
            # Start processing
            await status.edit(f"🎯 Domains: {', '.join(target_sites)}\n\n📦 Extracting archives...")
            
            with task_lock:
                user_tasks[user_id]['status'] = 'extracting'
            
            extract_dir = EXTRACT_DIR / str(user_id) / task_id
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract
            async def update_extract(text):
                try:
                    await status.edit(f"📦 Extracting archives...\n{text}")
                except:
                    pass
            
            extractor = ArchiveExtractor(password, update_extract)
            extracted_path = await extractor.extract_all_nested(archive_path, str(extract_dir))
            
            if extractor.stop_extraction:
                with task_lock:
                    user_tasks.pop(user_id, None)
                return await status.edit("❌ Task cancelled by user")
            
            # Extract cookies
            await status.edit("🔍 Extracting cookies...")
            
            with task_lock:
                user_tasks[user_id]['status'] = 'filtering'
            
            async def update_cookies(text):
                try:
                    await status.edit(f"🔍 Extracting cookies...\n{text}")
                except:
                    pass
            
            cookie_extractor = CookieExtractor(target_sites, update_cookies)
            await cookie_extractor.process_all(extracted_path)
            
            if cookie_extractor.stop_processing:
                with task_lock:
                    user_tasks.pop(user_id, None)
                return await status.edit("❌ Task cancelled by user")
            
            # Create results
            if cookie_extractor.total_found > 0:
                result_folder = RESULTS_DIR / str(user_id) / task_id
                result_folder.mkdir(parents=True, exist_ok=True)
                
                created_zips = cookie_extractor.create_site_zips(extracted_path, str(result_folder))
                
                await status.edit(
                    f"✓ **Extraction Complete!**\n\n"
                    f"📊 **Stats:**\n"
                    f"• Files processed: {cookie_extractor.files_processed}\n"
                    f"• Entries found: {cookie_extractor.total_found}\n"
                    f"• ZIP archives: {len(created_zips)}\n\n"
                    f"📦 Uploading results..."
                )
                
                # Send ZIP files
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path):
                        try:
                            await client.send_document(
                                user_id,
                                zip_path,
                                caption=f"🍪 Cookies for `{site}`"
                            )
                        except Exception as e:
                            await message.reply(f"Error sending {site}: {str(e)}", quote=True)
                
                await status.edit("✓ Task completed! All files sent.")
            else:
                await status.edit("⚠️ No cookies found matching your domains.")
            
            # Cleanup
            with task_lock:
                user_tasks.pop(user_id, None)
            
            # Log
            if SEND_LOGS:
                try:
                    await client.send_message(
                        LOG_CHANNEL,
                        f"✓ Task completed\n\n"
                        f"👤 User: {user_id}\n"
                        f"📂 Task ID: {task_id}\n"
                        f"🎯 Domains: {', '.join(target_sites)}\n"
                        f"📊 Found: {cookie_extractor.total_found}"
                    )
                except:
                    pass
            
            # Cleanup files
            delete_folder(str(user_dir))
            delete_folder(str(extract_dir))
            delete_folder(str(result_folder))
        
        except Exception as e:
            logger.error(f"Error in _process_archive: {e}", exc_info=True)
            with task_lock:
                user_tasks.pop(user_id, None)
            await message.reply(f"❌ Error: {str(e)}", quote=True)
    
    async def _process_link(self, client: Client, message: Message):
        """Handle direct link"""
        user_id = message.from_user.id
        task_id = generate_unique_id()
        
        with task_lock:
            if user_id in user_tasks:
                return await message.reply("⏳ You already have a running task. Use /cancel_[ID] to stop it.", quote=True)
            
            user_tasks[user_id] = {
                'id': task_id,
                'status': 'downloading',
                'message': message.id,
                'status_msg': None
            }
        
        try:
            args = message.text.split(None, 1)
            if len(args) < 2:
                await message.reply("❌ Usage: /link <url>", quote=True)
                with task_lock:
                    user_tasks.pop(user_id, None)
                return
            
            url = args[1].strip()
            status = await message.reply(f"⏳ Task ID: `{task_id}`\n⬇️ Downloading from link...")
            
            with task_lock:
                user_tasks[user_id]['status_msg'] = status.id
            
            # Download file
            user_dir = DOWNLOAD_DIR / str(user_id) / task_id
            user_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            await status.edit(f"❌ Download failed (HTTP {resp.status})")
                            with task_lock:
                                user_tasks.pop(user_id, None)
                            return
                        
                        filename = url.split('/')[-1] or 'archive.zip'
                        archive_path = user_dir / filename
                        
                        with open(archive_path, 'wb') as f:
                            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                                f.write(chunk)
            except Exception as e:
                await status.edit(f"❌ Download failed: {str(e)}")
                with task_lock:
                    user_tasks.pop(user_id, None)
                return
            
            archive_path = str(archive_path)
            file_size = format_size(os.path.getsize(archive_path))
            await status.edit(f"✓ Downloaded: {file_size}\n\n🔍 Checking password protection...")
            
            # Check password
            ext = Path(archive_path).suffix.lower()
            is_protected = False
            
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(archive_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(archive_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(archive_path)
            
            if is_protected:
                await status.edit(f"✓ Downloaded: {file_size}\n\n🔐 Archive is password protected.\n🔑 Send password (or /skip):")
                
                try:
                    pass_msg = await client.listen(filters.text & filters.user(user_id), timeout=300)
                    password = None if pass_msg.text.lower() == '/skip' else pass_msg.text
                except:
                    with task_lock:
                        user_tasks.pop(user_id, None)
                    return await status.edit("❌ Timeout. Task cancelled.")
            else:
                password = None
                await status.edit(f"✓ Downloaded: {file_size}\n\n✓ Not password protected\n🎯 Send domains (comma-separated):")
            
            # Get domains
            try:
                domains_msg = await client.listen(filters.text & filters.user(user_id), timeout=300)
                domains = domains_msg.text
            except:
                with task_lock:
                    user_tasks.pop(user_id, None)
                return await status.edit("❌ Timeout. Task cancelled.")
            
            target_sites = [s.strip().lower() for s in domains.split(',') if s.strip()]
            if not target_sites:
                await status.edit("❌ No domains specified")
                with task_lock:
                    user_tasks.pop(user_id, None)
                return
            
            # Start processing
            await status.edit(f"🎯 Domains: {', '.join(target_sites)}\n\n📦 Extracting archives...")
            
            with task_lock:
                user_tasks[user_id]['status'] = 'extracting'
            
            extract_dir = EXTRACT_DIR / str(user_id) / task_id
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract
            async def update_extract(text):
                try:
                    await status.edit(f"📦 Extracting archives...\n{text}")
                except:
                    pass
            
            extractor = ArchiveExtractor(password, update_extract)
            extracted_path = await extractor.extract_all_nested(archive_path, str(extract_dir))
            
            if extractor.stop_extraction:
                with task_lock:
                    user_tasks.pop(user_id, None)
                return await status.edit("❌ Task cancelled by user")
            
            # Extract cookies
            await status.edit("🔍 Extracting cookies...")
            
            with task_lock:
                user_tasks[user_id]['status'] = 'filtering'
            
            async def update_cookies(text):
                try:
                    await status.edit(f"🔍 Extracting cookies...\n{text}")
                except:
                    pass
            
            cookie_extractor = CookieExtractor(target_sites, update_cookies)
            await cookie_extractor.process_all(extracted_path)
            
            if cookie_extractor.stop_processing:
                with task_lock:
                    user_tasks.pop(user_id, None)
                return await status.edit("❌ Task cancelled by user")
            
            # Create results
            if cookie_extractor.total_found > 0:
                result_folder = RESULTS_DIR / str(user_id) / task_id
                result_folder.mkdir(parents=True, exist_ok=True)
                
                created_zips = cookie_extractor.create_site_zips(extracted_path, str(result_folder))
                
                await status.edit(
                    f"✓ **Extraction Complete!**\n\n"
                    f"📊 **Stats:**\n"
                    f"• Files processed: {cookie_extractor.files_processed}\n"
                    f"• Entries found: {cookie_extractor.total_found}\n"
                    f"• ZIP archives: {len(created_zips)}\n\n"
                    f"📦 Uploading results..."
                )
                
                # Send ZIP files
                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path):
                        try:
                            await client.send_document(
                                user_id,
                                zip_path,
                                caption=f"🍪 Cookies for `{site}`"
                            )
                        except Exception as e:
                            await message.reply(f"Error sending {site}: {str(e)}", quote=True)
                
                await status.edit("✓ Task completed! All files sent.")
            else:
                await status.edit("⚠️ No cookies found matching your domains.")
            
            # Cleanup
            with task_lock:
                user_tasks.pop(user_id, None)
            
            # Log
            if SEND_LOGS:
                try:
                    await client.send_message(
                        LOG_CHANNEL,
                        f"✓ Task completed\n\n"
                        f"👤 User: {user_id}\n"
                        f"📂 Task ID: {task_id}\n"
                        f"🎯 Domains: {', '.join(target_sites)}\n"
                        f"📊 Found: {cookie_extractor.total_found}"
                    )
                except:
                    pass
            
            # Cleanup files
            delete_folder(str(user_dir))
            delete_folder(str(extract_dir))
            delete_folder(str(result_folder))
        
        except Exception as e:
            logger.error(f"Error in _process_link: {e}", exc_info=True)
            with task_lock:
                user_tasks.pop(user_id, None)
            await message.reply(f"❌ Error: {str(e)}", quote=True)
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Cookie Extractor Bot...")
        logger.info(f"7z.exe: {TOOL_STATUS['7z']} | UnRAR.exe: {TOOL_STATUS['unrar']}")
        self.app.run()

if __name__ == "__main__":
    bot = CookieBot()
    bot.run()
