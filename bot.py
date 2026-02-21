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
import threading
from concurrent.futures import ThreadPoolExecutor
import mimetypes
import functools
import queue

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

MAX_WORKERS = 100
DOWNLOAD_WORKERS = 20
BUFFER_SIZE = 64 * 1024 * 1024
CHUNK_SIZE = 4 * 1024 * 1024
MAX_FILE_SIZE = 4000 * 1024 * 1024
DOWNLOAD_TIMEOUT = 3600
PROGRESS_UPDATE_INTERVAL = 5  # Increased from 10 to 20 seconds
UPDATE_JITTER = 5  # Add random jitter to prevent synchronized updates
MAX_UPDATE_INTERVAL = 120  # Max 2 minutes between updates when rate limited

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}

SYSTEM = platform.system().lower()

thread_pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
download_pool = ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS)

# ==============================================================================
#                            TOOL DETECTION
# ==============================================================================

class ToolDetector:
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
                for path in ['C:\\Program Files\\WinRAR\\UnRAR.exe',
                              'C:\\Program Files (x86)\\WinRAR\\UnRAR.exe']:
                    if os.path.exists(path):
                        return path
                return 'unrar.exe'
            else:
                result = subprocess.run(['which', 'unrar'], capture_output=True, text=True)
                return result.stdout.strip() if result.returncode == 0 else 'unrar'
        elif tool_name == '7z':
            if SYSTEM == 'windows':
                for path in ['C:\\Program Files\\7-Zip\\7z.exe',
                              'C:\\Program Files (x86)\\7-Zip\\7z.exe']:
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

# ==============================================================================
#                            USER TASK MANAGER
# ==============================================================================

class UserTaskManager:
    def __init__(self):
        self.user_tasks: Dict[int, Dict] = {}
        self.user_cancelled: Set[int] = set()
        self.lock = asyncio.Lock()

    async def register_task(self, user_id: int, task_id: str, data: Dict):
        async with self.lock:
            self.user_tasks[user_id] = {
                'task_id': task_id, 'data': data,
                'start_time': time.time(), 'cancelled': False,
                'progress_messages': []
            }

    async def add_progress_message(self, user_id: int, message_id: int):
        async with self.lock:
            if user_id in self.user_tasks:
                self.user_tasks[user_id].setdefault('progress_messages', []).append(message_id)

    async def get_task(self, user_id: int) -> Optional[Dict]:
        async with self.lock:
            return self.user_tasks.get(user_id)

    async def get_task_id(self, user_id: int) -> Optional[str]:
        async with self.lock:
            task = self.user_tasks.get(user_id)
            return task.get('task_id') if task else None

    async def cancel_task(self, user_id: int, task_id: str = None) -> bool:
        async with self.lock:
            if user_id in self.user_tasks:
                if task_id and self.user_tasks[user_id].get('task_id') != task_id:
                    return False
                self.user_tasks[user_id]['cancelled'] = True
                self.user_cancelled.add(user_id)
                return True
            return False

    async def is_cancelled(self, user_id: int) -> bool:
        async with self.lock:
            if user_id in self.user_cancelled:
                return True
            if user_id in self.user_tasks:
                return self.user_tasks[user_id].get('cancelled', False)
            return False

    async def clear_task(self, user_id: int):
        async with self.lock:
            self.user_tasks.pop(user_id, None)
            self.user_cancelled.discard(user_id)

    async def cleanup_old_tasks(self, max_age: int = 3600):
        current_time = time.time()
        async with self.lock:
            to_remove = [uid for uid, t in self.user_tasks.items()
                         if current_time - t['start_time'] > max_age]
            for uid in to_remove:
                del self.user_tasks[uid]
                self.user_cancelled.discard(uid)

# ==============================================================================
#                            GLOBAL RATE LIMITER
# ==============================================================================

class GlobalRateLimiter:
    def __init__(self, max_edits_per_minute=20):  # Reduced from 30 to 20
        self.max_edits_per_minute = max_edits_per_minute
        self.edit_timestamps: List[float] = []
        self.lock = asyncio.Lock()
    
    async def can_edit(self) -> bool:
        async with self.lock:
            now = time.time()
            # Remove timestamps older than 1 minute
            self.edit_timestamps = [t for t in self.edit_timestamps if now - t < 60]
            
            if len(self.edit_timestamps) < self.max_edits_per_minute:
                self.edit_timestamps.append(now)
                return True
            return False

# ==============================================================================
#                            PROGRESS TRACKER
# ==============================================================================

class ProgressTracker:
    """
    mode='bytes'  → shows MB/GB + speed + ETA  (for downloads)
    mode='count'  → shows  X / Y archives       (for extraction / filtering)
                    percentage is always clamped 0–100
    """

    def __init__(self, message: Message, total: int, description: str = "Progress",
                 task_manager: UserTaskManager = None, filename: str = None,
                 mode: str = 'bytes', rate_limiter: GlobalRateLimiter = None):
        self.message = message
        self.total = max(total, 1)
        self.current = 0
        self.description = description
        self.last_update = 0
        self.lock = asyncio.Lock()
        self.start_time = time.time()
        self.cancelled = False
        self.task_manager = task_manager
        self.user_id = message.chat.id
        self.filename = filename
        self.mode = mode
        self.speed_samples: List[float] = []
        self.update_task: Optional[asyncio.Task] = None
        self.last_error_time = 0
        self.consecutive_errors = 0
        self.current_update_interval = PROGRESS_UPDATE_INTERVAL
        self.rate_limiter = rate_limiter
        self.last_successful_update = 0

        if task_manager:
            asyncio.create_task(task_manager.add_progress_message(self.user_id, message.id))

    async def start_periodic_updates(self):
        self.update_task = asyncio.create_task(self._periodic_update())

    async def stop_periodic_updates(self):
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except:
                pass

    async def _periodic_update(self):
        try:
            while not self.cancelled:
                # Add jitter to prevent synchronized updates
                jitter = random.uniform(0, UPDATE_JITTER)
                await asyncio.sleep(self.current_update_interval + jitter)
                
                # Check if enough time has passed since last successful update
                if time.time() - self.last_successful_update >= self.current_update_interval:
                    await self._send_update()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Periodic update error: {e}")

    async def update(self, amount: int = 1, force: bool = False):
        if self.cancelled:
            return
        async with self.lock:
            self.current += amount
            current_time = time.time()
            if self.mode == 'bytes' and self.last_update > 0:
                dt = current_time - self.last_update
                if dt > 0 and dt < 60:  # Ignore very large gaps
                    self.speed_samples.append(amount / dt)
                    if len(self.speed_samples) > 5:
                        self.speed_samples.pop(0)
            
            # Only update if enough time has passed since last successful update
            time_since_last = current_time - self.last_successful_update
            if force or time_since_last >= self.current_update_interval:
                await self._send_update()

    async def set_total(self, total: int):
        async with self.lock:
            self.total = max(total, 1)

    async def increment_total(self, amount: int = 1):
        async with self.lock:
            self.total += amount

    def _calc_speed(self) -> float:
        if not self.speed_samples:
            elapsed = time.time() - self.start_time
            if elapsed > 0 and self.current > 0:
                return self.current / elapsed
            return 0
        
        # Weighted average - newer samples have higher weight
        weights = [0.5, 0.3, 0.1, 0.07, 0.03][:len(self.speed_samples)]
        weights = weights[:len(self.speed_samples)]
        if not weights:
            return 0
            
        wsum = sum(s * w for s, w in zip(self.speed_samples, weights))
        tw = sum(weights)
        return wsum / tw if tw > 0 else 0

    async def _send_update(self):
        # Check global rate limiter
        if self.rate_limiter and not await self.rate_limiter.can_edit():
            # Skip this update if we're rate limited globally
            return
            
        try:
            pct = min(100.0, self.current / self.total * 100) if self.total > 0 else 0.0
            elapsed = time.time() - self.start_time
            filled = int(20 * pct / 100)
            bar = '█' * filled + '░' * (20 - filled)
            file_ext = os.path.splitext(self.filename)[1].upper() if self.filename else "UNKNOWN"

            parts = [
                f"**{self.description}**",
                f"📄 **File:** `{self.filename or 'Unknown'}`",
                f"📁 **Type:** `{file_ext}`",
                f"`{bar}` {pct:.1f}%",
            ]

            if self.mode == 'bytes':
                speed = self._calc_speed()
                if speed == 0 and self.current > 0 and elapsed > 0:
                    speed = self.current / elapsed
                parts.append(f"📊 {self._fmt_size(self.current)} / {self._fmt_size(self.total)}")
                parts.append(f"⚡ **Speed:** {self._fmt_speed(speed)}")
                if speed > 0 and self.total > self.current:
                    eta = (self.total - self.current) / speed
                    if eta < 3600:  # Less than 1 hour
                        parts.append(f"⏱️ **ETA:** {self._fmt_time(eta)}")
                    else:
                        hours = eta / 3600
                        parts.append(f"⏱️ **ETA:** {hours:.1f}h")
                else:
                    parts.append(f"⏱️ **ETA:** {'Almost done...' if pct >= 99 else 'Calculating...'}")
            else:
                parts.append(f"📊 {self.current} / {self.total} archives")

            parts.append(f"🕒 **Elapsed:** {self._fmt_time(elapsed)}")

            if self.task_manager:
                tid = await self.task_manager.get_task_id(self.user_id)
                if tid:
                    parts.append(f"🔴 /cancel_{tid} to cancel")

            # Try to edit the message with flood wait handling
            try:
                await self.message.edit_text("\n".join(parts), parse_mode=ParseMode.MARKDOWN)
                # Success - reset error tracking and update last successful time
                self.consecutive_errors = 0
                self.current_update_interval = PROGRESS_UPDATE_INTERVAL
                self.last_successful_update = time.time()
                
            except FloodWait as e:
                # Handle flood wait
                self.consecutive_errors += 1
                wait_time = e.value
                
                # Increase update interval exponentially based on error count
                self.current_update_interval = min(
                    MAX_UPDATE_INTERVAL,
                    PROGRESS_UPDATE_INTERVAL * (2 ** self.consecutive_errors)
                )
                
                print(f"Flood wait for user {self.user_id}: {wait_time}s. "
                      f"Adjusted interval to {self.current_update_interval:.1f}s")
                
                # Don't try to update again until the flood wait is over
                self.last_update = time.time()
                
                # Actually wait the required time
                await asyncio.sleep(wait_time)
                
            except MessageNotModified:
                # Content didn't change - that's fine, reduce error count
                self.consecutive_errors = max(0, self.consecutive_errors - 1)
                self.last_successful_update = time.time()
                pass
                
            except Exception as e:
                print(f"Progress update error: {e}")
                self.consecutive_errors += 1
                # Increase interval on other errors too
                self.current_update_interval = min(
                    MAX_UPDATE_INTERVAL,
                    PROGRESS_UPDATE_INTERVAL * (1.5 ** self.consecutive_errors)
                )
                
        except Exception as e:
            print(f"Progress update error: {e}")

    def _fmt_size(self, b: int) -> str:
        for u in ['B', 'KB', 'MB', 'GB']:
            if b < 1024.0:
                return f"{b:.1f}{u}"
            b /= 1024.0
        return f"{b:.1f}TB"

    def _fmt_speed(self, bps: float) -> str:
        if bps < 1024: return f"{bps:.1f} B/s"
        if bps < 1024**2: return f"{bps/1024:.1f} KB/s"
        if bps < 1024**3: return f"{bps/1024**2:.1f} MB/s"
        return f"{bps/1024**3:.1f} GB/s"

    def _fmt_time(self, s: float) -> str:
        if s < 60: return f"{s:.0f}s"
        if s < 3600: return f"{s/60:.1f}m"
        return f"{s/3600:.1f}h"

    async def cancel(self):
        self.cancelled = True
        await self.stop_periodic_updates()
        try:
            await self.message.edit_text("❌ **Task Cancelled**", parse_mode=ParseMode.MARKDOWN)
        except:
            pass

    async def complete(self, text: str):
        await self.stop_periodic_updates()
        try:
            await self.message.edit_text(text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass

# ==============================================================================
#                            DOWNLOAD MANAGER
# ==============================================================================

class DownloadManager:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if not self.session:
            connector = aiohttp.TCPConnector(
                limit=DOWNLOAD_WORKERS, limit_per_host=DOWNLOAD_WORKERS,
                ttl_dns_cache=300, force_close=True, enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT, connect=30, sock_read=30)
            self.session = aiohttp.ClientSession(
                connector=connector, timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
        return self.session

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def download_file(self, url: str, file_path: str,
                            progress: ProgressTracker, user_id: int) -> bool:
        try:
            session = await self.get_session()
            async with session.head(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return False
                total_size = int(resp.headers.get('content-length', 0))
                accept_ranges = resp.headers.get('accept-ranges', '').lower() == 'bytes'
                await progress.set_total(total_size)

            if accept_ranges and total_size > CHUNK_SIZE * 2:
                return await self._parallel_download(url, file_path, total_size, progress, user_id)
            return await self._single_download(url, file_path, progress, user_id)
        except Exception as e:
            print(f"Download error: {e}")
            return False

    async def _single_download(self, url: str, file_path: str,
                                progress: ProgressTracker, user_id: int) -> bool:
        try:
            session = await self.get_session()
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return False
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        if await progress.task_manager.is_cancelled(user_id):
                            return False
                        await f.write(chunk)
                        await progress.update(len(chunk))
            return True
        except Exception as e:
            print(f"Single download error: {e}")
            return False

    async def _parallel_download(self, url: str, file_path: str, total_size: int,
                                  progress: ProgressTracker, user_id: int) -> bool:
        try:
            n = min(DOWNLOAD_WORKERS, (total_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
            cs = total_size // n
            ranges = [(i * cs, (i * cs + cs - 1) if i < n - 1 else total_size - 1)
                      for i in range(n)]
            temp_files = [f"{file_path}.part{i}" for i in range(n)]
            tasks = [asyncio.create_task(
                self._download_chunk(url, temp_files[i], s, e, progress, user_id)
            ) for i, (s, e) in enumerate(ranges)]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            if any(isinstance(r, Exception) or r is False for r in results):
                return False

            async with aiofiles.open(file_path, 'wb') as out:
                for tf in temp_files:
                    async with aiofiles.open(tf, 'rb') as inp:
                        while True:
                            chunk = await inp.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            await out.write(chunk)
                    os.remove(tf)
            return True
        except Exception as e:
            print(f"Parallel download error: {e}")
            return False

    async def _download_chunk(self, url: str, temp_file: str, start: int, end: int,
                               progress: ProgressTracker, user_id: int) -> bool:
        try:
            session = await self.get_session()
            async with session.get(url, headers={'Range': f'bytes={start}-{end}'},
                                   allow_redirects=True) as resp:
                if resp.status not in (200, 206):
                    return False
                async with aiofiles.open(temp_file, 'wb') as f:
                    async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                        if await progress.task_manager.is_cancelled(user_id):
                            return False
                        await f.write(chunk)
                        await progress.update(len(chunk))
            return True
        except Exception as e:
            print(f"Chunk download error: {e}")
            return False

# ==============================================================================
#                            UTILITY FUNCTIONS
# ==============================================================================

def sanitize_filename(filename: str) -> str:
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in filename)

def generate_random_string(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def get_filename_from_url(url: str, content_disposition: str = None) -> str:
    if content_disposition:
        m = re.search(r'filename[^;=\n]*=(([\'"]).*?\2|[^;\n]*)', content_disposition, re.IGNORECASE)
        if m:
            fn = m.group(1).strip('"\'')
            if fn:
                return sanitize_filename(fn)
    try:
        fn = os.path.basename(urllib.parse.urlparse(url).path)
        if fn and fn != '/' and '.' in fn:
            return sanitize_filename(fn.split('?')[0])
    except:
        pass
    return f"download_{generate_random_string(8)}.bin"

def detect_archive_type(file_path: str) -> Optional[str]:
    try:
        with open(file_path, 'rb') as f:
            h = f.read(20)
        if h[:4] in (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'):
            return '.zip'
        if h[:7] in (b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01'):
            return '.rar'
        if h[:6] == b'7z\xbc\xaf\x27\x1c':
            return '.7z'
        if h[:8] in (b'ustar\x0000', b'ustar  \x00'):
            return '.tar'
        if h[:2] == b'\x1f\x8b':
            return '.gz'
        if h[:3] == b'BZh':
            return '.bz2'
        if h[:6] == b'\xfd7zXZ\x00':
            return '.xz'
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            for kw, ext in [('zip', '.zip'), ('rar', '.rar'), ('x-7z', '.7z'),
                             ('tar', '.tar'), ('gzip', '.gz'), ('bzip', '.bz2'), ('xz', '.xz')]:
                if kw in mime_type:
                    return ext
    except:
        pass
    return None

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
    for u in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{u}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"

def format_time(seconds: float) -> str:
    if seconds < 60: return f"{seconds:.1f}s"
    if seconds < 3600: return f"{seconds/60:.1f}m"
    return f"{seconds/3600:.1f}h"

async def delete_entire_folder(folder_path: str) -> bool:
    if not os.path.exists(folder_path):
        return True
    try:
        gc.collect()
        loop = asyncio.get_event_loop()
        if SYSTEM == 'windows':
            await loop.run_in_executor(thread_pool,
                lambda: os.system(f'rmdir /s /q "{folder_path}" 2>nul'))
        else:
            await loop.run_in_executor(thread_pool,
                lambda: os.system(f'rm -rf "{folder_path}"'))
        await asyncio.sleep(1)
        if os.path.exists(folder_path):
            await loop.run_in_executor(thread_pool,
                lambda: shutil.rmtree(folder_path, ignore_errors=True))
        return not os.path.exists(folder_path)
    except:
        return False

# ==============================================================================
#                            PASSWORD DETECTION
# ==============================================================================

class PasswordDetector:
    @staticmethod
    def check_rar_protected(archive_path: str) -> bool:
        if not HAS_RARFILE:
            if TOOL_STATUS['unrar']:
                try:
                    r = subprocess.run([TOOL_PATHS['unrar'], 'l', archive_path],
                                       capture_output=True, text=True, timeout=10)
                    return 'password' in r.stderr.lower() or 'encrypted' in r.stderr.lower()
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
        if not HAS_PY7ZR:
            if TOOL_STATUS['7z']:
                try:
                    r = subprocess.run([TOOL_PATHS['7z'], 'l', archive_path],
                                       capture_output=True, text=True, timeout=10)
                    return 'Encrypted' in r.stdout or 'Password' in r.stdout
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
        if TOOL_STATUS['7z']:
            try:
                r = subprocess.run([TOOL_PATHS['7z'], 'l', archive_path],
                                   capture_output=True, text=True, timeout=10)
                if 'Encrypted' in r.stdout or 'Password' in r.stdout:
                    return True
            except:
                pass
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                return any(info.flag_bits & 0x1 for info in zf.infolist())
        except:
            return True

# ==============================================================================
#                   THREAD-SAFE PROGRESS HELPERS
# ==============================================================================

def _schedule(coro, loop: asyncio.AbstractEventLoop):
    """Schedule a coroutine on the main event loop from any worker thread."""
    if loop and not loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            future.result(timeout=5)
        except Exception:
            pass

def run_progress_update(progress, amount: int, loop: asyncio.AbstractEventLoop):
    _schedule(progress.update(amount), loop)

def run_progress_set_total(progress, total: int, loop: asyncio.AbstractEventLoop):
    _schedule(progress.set_total(total), loop)

def run_progress_increment_total(progress, amount: int, loop: asyncio.AbstractEventLoop):
    _schedule(progress.increment_total(amount), loop)

# ==============================================================================
#                            ARCHIVE EXTRACTION
# ==============================================================================

class UltimateArchiveExtractor:
    def __init__(self, password: Optional[str] = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = threading.Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.total_archives = 0
        self.progress: Optional[ProgressTracker] = None
        self.task_manager: Optional[UserTaskManager] = None
        self.user_id: Optional[int] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_progress(self, progress, task_manager=None, user_id=None,
                     loop: asyncio.AbstractEventLoop = None):
        self.progress = progress
        self.task_manager = task_manager
        self.user_id = user_id
        self.loop = loop

    # ── extraction helpers ────────────────────────────────────────────────────

    def _walk_files(self, extract_dir: str) -> List[str]:
        return [os.path.relpath(os.path.join(r, f), extract_dir)
                for r, _, fs in os.walk(extract_dir) for f in fs]

    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        try:
            cmd = [TOOL_PATHS['7z'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd += [f'-o{extract_dir}', archive_path]
            if subprocess.run(cmd, capture_output=True, timeout=300).returncode == 0:
                return self._walk_files(extract_dir)
        except:
            pass
        return []

    def extract_rar_with_unrar(self, archive_path: str, extract_dir: str) -> List[str]:
        try:
            sep = '\\' if SYSTEM == 'windows' else '/'
            cmd = [TOOL_PATHS['unrar'], 'x', '-y',
                   f'-p{self.password}' if self.password else '-p-',
                   archive_path, extract_dir + sep]
            if subprocess.run(cmd, capture_output=True, timeout=300).returncode == 0:
                return self._walk_files(extract_dir)
        except:
            pass
        return []

    def extract_zip_fastest(self, archive_path: str, extract_dir: str) -> List[str]:
        if TOOL_STATUS['7z']:
            result = self.extract_7z_with_7z(archive_path, extract_dir)
            if result:
                return result
        if TOOL_STATUS['unrar']:
            result = self.extract_rar_with_unrar(archive_path, extract_dir)
            if result:
                return result
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

    def extract_rar_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        try:
            with rarfile.RarFile(archive_path) as rf:
                if self.password:
                    rf.setpassword(self.password)
                rf.extractall(extract_dir)
                return rf.namelist()
        except:
            return []

    def extract_7z_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        try:
            with py7zr.SevenZipFile(archive_path, mode='r', password=self.password) as sz:
                sz.extractall(extract_dir)
                return sz.getnames()
        except:
            return []

    def extract_single(self, archive_path: str, extract_dir: str) -> List[str]:
        if self.stop_extraction:
            return []
        ext = os.path.splitext(archive_path)[1].lower()
        try:
            if ext == '.7z':
                return (self.extract_7z_with_7z(archive_path, extract_dir) if TOOL_STATUS['7z']
                        else self.extract_7z_fallback(archive_path, extract_dir) if HAS_PY7ZR else [])
            elif ext == '.rar':
                return (self.extract_rar_with_unrar(archive_path, extract_dir) if TOOL_STATUS['unrar']
                        else self.extract_rar_fallback(archive_path, extract_dir) if HAS_RARFILE else [])
            elif ext == '.zip':
                return self.extract_zip_fastest(archive_path, extract_dir)
            else:
                return self.extract_tar_fast(archive_path, extract_dir)
        except:
            return []

    def find_archives_fast(self, directory: str) -> List[str]:
        found = []
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    if os.path.splitext(file)[1].lower() in SUPPORTED_ARCHIVES:
                        found.append(os.path.join(root, file))
        except:
            pass
        return found

    async def extract_all_nested(self, root_archive: str, base_dir: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            thread_pool,
            self._extract_all_nested_sync,
            root_archive, base_dir
        )

    def _extract_all_nested_sync(self, root_archive: str, base_dir: str) -> str:
        """
        Synchronous extraction that runs in the thread pool.
        Progress uses mode='count' (archive units) so percentage never exceeds 100%.
        total starts at 1 and grows dynamically as nested archives are discovered.
        """
        current_level = {root_archive}
        level = 0
        self.total_archives = 1

        if self.progress and self.loop:
            run_progress_set_total(self.progress, 1, self.loop)

        while current_level and not self.stop_extraction:
            next_level: Set[str] = set()
            level_dir = os.path.join(base_dir, f"L{level}")
            os.makedirs(level_dir, exist_ok=True)

            for archive in current_level:
                if archive in self.processed_files or self.stop_extraction:
                    continue

                archive_name = sanitize_filename(
                    os.path.splitext(os.path.basename(archive))[0])[:50]
                extract_subdir = os.path.join(level_dir, archive_name)
                os.makedirs(extract_subdir, exist_ok=True)

                self.extract_single(archive, extract_subdir)

                with self.lock:
                    self.processed_files.add(archive)
                    self.extracted_count += 1

                # Discover nested archives BEFORE advancing current
                new_archives = self.find_archives_fast(extract_subdir)
                if new_archives:
                    next_level.update(new_archives)
                    self.total_archives += len(new_archives)
                    if self.progress and self.loop:
                        run_progress_increment_total(self.progress, len(new_archives), self.loop)

                # Mark this archive as done
                if self.progress and self.loop:
                    run_progress_update(self.progress, 1, self.loop)

            current_level = next_level
            level += 1

        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    def __init__(self, target_sites: List[str]):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {s: {} for s in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {s: set() for s in self.target_sites}
        self.stop_processing = False
        self.progress: Optional[ProgressTracker] = None
        self.task_manager: Optional[UserTaskManager] = None
        self.user_id: Optional[int] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.site_patterns = {s: re.compile(re.escape(s).encode()) for s in self.target_sites}

    def set_progress(self, progress, task_manager=None, user_id=None,
                     loop: asyncio.AbstractEventLoop = None):
        self.progress = progress
        self.task_manager = task_manager
        self.user_id = user_id
        self.loop = loop

    def find_cookie_files(self, extract_dir: str) -> List[Tuple[str, str]]:
        def scan(start_dir):
            results = []
            try:
                for root, _, files in os.walk(start_dir):
                    if any(f in root for f in COOKIE_FOLDERS):
                        for file in files:
                            if file.endswith(('.txt', '.txt.bak')):
                                results.append((os.path.join(root, file), file))
            except:
                pass
            return results

        top_dirs = []
        try:
            for item in os.listdir(extract_dir):
                p = os.path.join(extract_dir, item)
                if os.path.isdir(p):
                    top_dirs.append(p)
        except:
            top_dirs = [extract_dir]

        cookie_files = []
        with ThreadPoolExecutor(max_workers=min(20, len(top_dirs) or 1)) as ex:
            for result in ex.map(scan, top_dirs or [extract_dir]):
                cookie_files.extend(result)
        return cookie_files

    def get_unique_filename(self, site: str, orig_name: str) -> str:
        base, ext = os.path.splitext(orig_name)
        with self.seen_lock:
            if orig_name not in self.used_filenames[site]:
                self.used_filenames[site].add(orig_name)
                return orig_name
            new_name = f"{base}_{generate_random_string(6)}{ext}"
            while new_name in self.used_filenames[site]:
                new_name = f"{base}_{generate_random_string(6)}{ext}"
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
            site_matches: Dict[str, List[Tuple[int, str]]] = {s: [] for s in self.target_sites}

            for line_num, line_bytes in enumerate(lines):
                if not line_bytes or line_bytes.startswith(b'#'):
                    continue
                line_lower = line_bytes.lower()
                line_str = line_bytes.decode('utf-8', errors='ignore').rstrip('\n\r')
                for site in self.target_sites:
                    if self.site_patterns[site].search(line_lower):
                        uid = f"{site}|{file_hash}|{line_num}"
                        with self.seen_lock:
                            if uid not in self.global_seen:
                                self.global_seen.add(uid)
                                site_matches[site].append((line_num, line_str))
                                with self.stats_lock:
                                    self.total_found += 1

            for site, matches in site_matches.items():
                if matches:
                    matches.sort(key=lambda x: x[0])
                    site_dir = os.path.join(extract_dir, "cookies", site)
                    os.makedirs(site_dir, exist_ok=True)
                    unique_name = self.get_unique_filename(site, orig_name)
                    out_path = os.path.join(site_dir, unique_name)
                    with open(out_path, 'w', encoding='utf-8', buffering=BUFFER_SIZE) as f:
                        f.write('\n'.join(line for _, line in matches))
                    with self.seen_lock:
                        self.site_files[site][out_path] = unique_name

            with self.stats_lock:
                self.files_processed += 1
        except Exception:
            pass

    async def process_all(self, extract_dir: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            thread_pool,
            self._process_all_sync,
            extract_dir
        )

    def _process_all_sync(self, extract_dir: str):
        cookie_files = self.find_cookie_files(extract_dir)
        if not cookie_files:
            return
        if self.progress and self.loop:
            run_progress_set_total(self.progress, len(cookie_files), self.loop)
        for file_path, orig_name in cookie_files:
            if self.stop_processing:
                break
            self.process_file(file_path, orig_name, extract_dir)
            if self.progress and self.loop:
                run_progress_update(self.progress, 1, self.loop)

    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        created_zips = {}
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            zip_name = f"{sanitize_filename(site)}_{datetime.now().strftime('%H%M%S')}.zip"
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
    def __init__(self):
        self.app = Client("cookie_extractor_bot",
                          api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
        self.task_manager = UserTaskManager()
        self.download_manager = DownloadManager()
        self.global_rate_limiter = GlobalRateLimiter(max_edits_per_minute=20)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.downloads_dir = os.path.join(self.base_dir, 'downloads')
        self.results_dir = os.path.join(self.base_dir, 'results')
        self.logs_dir = os.path.join(self.base_dir, 'logs')
        for d in (self.downloads_dir, self.results_dir, self.logs_dir):
            os.makedirs(d, exist_ok=True)

        self.user_states: Dict[int, str] = {}
        self.user_data: Dict[int, Dict] = {}
        self.state_lock = asyncio.Lock()
        self.active_tasks: Dict[int, asyncio.Task] = {}

    async def start(self):
        print(f"{Fore.GREEN}Starting Cookie Extractor Bot...{Style.RESET_ALL}")
        await self.app.start()
        print(f"{Fore.GREEN}Bot started!{Style.RESET_ALL}")
        asyncio.create_task(self.cleanup_old_files())

    async def stop(self):
        for task in self.active_tasks.values():
            task.cancel()
        await self.download_manager.close()
        await self.app.stop()

    async def cleanup_old_files(self):
        while True:
            try:
                await asyncio.sleep(3600)
                ct = time.time()
                for folder in (self.downloads_dir, self.results_dir):
                    if not os.path.exists(folder):
                        continue
                    for item in os.listdir(folder):
                        p = os.path.join(folder, item)
                        try:
                            if ct - os.path.getmtime(p) > 3600:
                                if os.path.isfile(p):
                                    os.remove(p)
                                else:
                                    await delete_entire_folder(p)
                        except:
                            pass
                await self.task_manager.cleanup_old_tasks()
            except Exception as e:
                print(f"Cleanup error: {e}")

    async def log_to_channel(self, text: str):
        if not SEND_LOGS:
            return
        try:
            await self.app.send_message(LOG_CHANNEL, text, parse_mode=ParseMode.MARKDOWN)
        except:
            pass

    async def send_progress_message(self, user_id: int, text: str) -> Message:
        return await self.app.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)

    # ── download helpers ──────────────────────────────────────────────────────

    async def _finish_download(self, file_path: str, filename: str,
                                progress_msg: Message) -> Tuple[bool, Optional[str]]:
        archive_type = await asyncio.get_event_loop().run_in_executor(
            thread_pool, detect_archive_type, file_path)
        if not archive_type:
            await progress_msg.edit_text("❌ Downloaded file is not a supported archive format.")
            return False, None
        if not filename.lower().endswith(archive_type):
            new_fn = os.path.splitext(filename)[0] + archive_type
            new_path = os.path.join(os.path.dirname(file_path), sanitize_filename(new_fn))
            await asyncio.get_event_loop().run_in_executor(thread_pool, os.rename, file_path, new_path)
        return True, archive_type

    async def download_file(self, url: str, file_path: str, progress_msg: Message,
                            task_id: str, filename: str) -> Tuple[bool, Optional[str]]:
        try:
            user_id = progress_msg.chat.id
            progress = ProgressTracker(progress_msg, 1, "⬇️ Downloading",
                                       self.task_manager, filename, mode='bytes',
                                       rate_limiter=self.global_rate_limiter)
            await progress.start_periodic_updates()
            success = await self.download_manager.download_file(url, file_path, progress, user_id)
            if not success or await self.task_manager.is_cancelled(user_id):
                await progress.cancel()
                return False, None
            await progress.stop_periodic_updates()
            return await self._finish_download(file_path, filename, progress_msg)
        except asyncio.CancelledError:
            return False, None
        except Exception as e:
            await progress_msg.edit_text(f"❌ Download error: {str(e)}")
            return False, None

    async def download_telegram_file(self, message: Message, file_path: str,
                                     progress_msg: Message, task_id: str,
                                     filename: str) -> Tuple[bool, Optional[str]]:
        try:
            file_size = 0
            if message.document:
                file_size = message.document.file_size
            elif message.photo:
                file_size = message.photo.file_size
            if file_size > MAX_FILE_SIZE:
                await progress_msg.edit_text(
                    f"❌ File too large: {format_size(file_size)} > {format_size(MAX_FILE_SIZE)}")
                return False, None

            user_id = progress_msg.chat.id
            progress = ProgressTracker(progress_msg, file_size, "⬇️ Downloading",
                                       self.task_manager, filename, mode='bytes',
                                       rate_limiter=self.global_rate_limiter)
            await progress.start_periodic_updates()

            async def cb(current, total):
                if await self.task_manager.is_cancelled(user_id):
                    raise asyncio.CancelledError()
                await progress.update(current - progress.current)

            await message.download(file_name=file_path, progress=cb)
            await progress.stop_periodic_updates()
            return await self._finish_download(file_path, filename, progress_msg)
        except asyncio.CancelledError:
            return False, None
        except Exception as e:
            await progress_msg.edit_text(f"❌ Download error: {str(e)}")
            return False, None

    # ── command handlers ──────────────────────────────────────────────────────

    async def start_command(self, client: Client, message: Message):
        welcome_text = (
            "👋 **Welcome to Cookie Extractor Bot!**\n\n"
            "📦 I can extract cookies from archives and filter them by domain.\n\n"
            "**How to use:**\n"
            "1️⃣ Send me an archive file (.zip/.rar/.7z) or any direct download link\n"
            "2️⃣ Tell me if it's password protected\n"
            "3️⃣ Provide the domains to filter (comma-separated)\n"
            "4️⃣ I'll extract and filter cookies for you!\n\n"
            "**Commands:**\n"
            "/start - Show this message\n"
            "/cancel - Cancel current task\n"
            "/status - Check task status\n\n"
            f"⚡ **Speed:** Using {'✓ 7z' if TOOL_STATUS['7z'] else '✗ 7z'} | "
            f"{'✓ UnRAR' if TOOL_STATUS['unrar'] else '✗ UnRAR'}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Guide", callback_data="guide"),
             InlineKeyboardButton("ℹ️ Info", callback_data="info")]
        ])
        await message.reply_text(welcome_text, reply_markup=keyboard)

    async def cancel_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        text = message.text.strip()
        task_id = text[8:].strip() if text.startswith('/cancel_') else None
        task = await self.task_manager.get_task(user_id)

        if task and (task_id is None or task.get('task_id') == task_id):
            await self.task_manager.cancel_task(user_id, task_id)
            await message.reply_text("✅ **Task cancelled successfully!**")
            for key in ('download_folder', 'extract_folder'):
                if key in task['data']:
                    await delete_entire_folder(task['data'][key])
            if user_id in self.active_tasks:
                self.active_tasks.pop(user_id).cancel()
        else:
            await message.reply_text("❌ Invalid task ID or no active task.")

    async def status_command(self, client: Client, message: Message):
        user_id = message.from_user.id
        task = await self.task_manager.get_task(user_id)
        if task:
            elapsed = time.time() - task['start_time']
            await message.reply_text(
                f"📊 **Task Status**\n\n"
                f"🆔 Task ID: `{task['task_id']}`\n"
                f"⏱️ Elapsed: {format_time(elapsed)}\n"
                f"📦 File: {task['data'].get('filename', 'Unknown')}\n"
                f"🔑 Password: {'Yes' if task['data'].get('password') else 'No'}\n"
                f"🎯 Domains: {', '.join(task['data'].get('domains', []))}\n\n"
                f"🔴 /cancel_{task['task_id']} to cancel"
            )
        else:
            await message.reply_text("❌ No active task.")

    async def handle_document(self, client: Client, message: Message):
        user_id = message.from_user.id
        task = await self.task_manager.get_task(user_id)
        if task:
            await message.reply_text(
                f"❌ You already have an active task.\n"
                f"Use /cancel_{task['task_id']} to cancel it first.")
            return
        if not message.document:
            return

        file_name = message.document.file_name
        async with self.state_lock:
            self.user_data[user_id] = {
                'type': 'telegram', 'message': message,
                'filename': file_name, 'file_size': message.document.file_size,
                'extension': os.path.splitext(file_name)[1].lower()
            }
            self.user_states[user_id] = 'awaiting_password'

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 Yes, it's protected", callback_data="password_yes"),
             InlineKeyboardButton("🔓 No password", callback_data="password_no")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        await message.reply_text(
            f"📦 **File received:** `{file_name}`\n"
            f"📊 Size: {format_size(message.document.file_size)}\n\n"
            f"🔒 Is this archive password protected?",
            reply_markup=keyboard
        )

    async def handle_text(self, client: Client, message: Message):
        user_id = message.from_user.id
        text = message.text.strip()

        if text.startswith(('http://', 'https://', 'ftp://')):
            task = await self.task_manager.get_task(user_id)
            if task:
                await message.reply_text(
                    f"❌ You already have an active task.\n"
                    f"Use /cancel_{task['task_id']} to cancel it first.")
                return
            filename = get_filename_from_url(text)
            async with self.state_lock:
                self.user_data[user_id] = {'type': 'url', 'url': text, 'filename': filename}
                self.user_states[user_id] = 'awaiting_password'
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔐 Yes, it's protected", callback_data="password_yes"),
                 InlineKeyboardButton("🔓 No password", callback_data="password_no")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
            await message.reply_text(
                f"📦 **URL received:** `{filename}`\n"
                f"🔍 Archive type will be detected after download\n\n"
                f"🔒 Is this archive password protected?",
                reply_markup=keyboard
            )
            return

        async with self.state_lock:
            if self.user_states.get(user_id) == 'awaiting_password':
                self.user_data[user_id]['password'] = text
                self.user_states[user_id] = 'awaiting_domains'
                await message.reply_text(
                    "✅ Password saved!\n\n"
                    "🎯 Now send me the domains to filter (comma-separated)\n"
                    "Example: `example.com, google.com, facebook.com`"
                )

    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        data = callback_query.data

        if data == "cancel":
            await self.task_manager.cancel_task(user_id)
            await callback_query.message.edit_text("❌ Operation cancelled.")
            async with self.state_lock:
                self.user_data.pop(user_id, None)
                self.user_states.pop(user_id, None)

        elif data == "password_yes":
            async with self.state_lock:
                self.user_states[user_id] = 'awaiting_password'
            await callback_query.message.edit_text("🔐 Please send me the password for this archive.")

        elif data == "password_no":
            async with self.state_lock:
                if user_id in self.user_data:
                    self.user_data[user_id]['password'] = None
                    self.user_states[user_id] = 'awaiting_domains'
            await callback_query.message.edit_text(
                "🎯 Now send me the domains to filter (comma-separated)\n"
                "Example: `example.com, google.com, facebook.com`"
            )

        elif data == "guide":
            await callback_query.message.edit_text(
                "📖 **User Guide**\n\n"
                "1️⃣ Upload archive or paste a direct download URL\n"
                "2️⃣ Choose if it's password-protected\n"
                "3️⃣ Send password (if needed)\n"
                "4️⃣ Enter comma-separated domains to filter\n"
                "5️⃣ Wait — progress bars keep you updated\n"
                "6️⃣ Receive a ZIP per domain with matching cookies\n"
                "7️⃣ Cancel anytime with /cancel_TASKID"
            )

        elif data == "info":
            await callback_query.message.edit_text(
                "ℹ️ **Bot Information**\n\n"
                f"• 7z: {'✅ Available' if TOOL_STATUS['7z'] else '❌ Not found'}\n"
                f"• UnRAR: {'✅ Available' if TOOL_STATUS['unrar'] else '❌ Not found'}\n\n"
                f"**Supported:** {', '.join(SUPPORTED_ARCHIVES)}\n"
                f"**Max file size:** {format_size(MAX_FILE_SIZE)}\n\n"
                "**Developer:** @rute_dev"
            )

        await callback_query.answer()

    async def handle_domains(self, client: Client, message: Message):
        user_id = message.from_user.id
        async with self.state_lock:
            if self.user_states.get(user_id) != 'awaiting_domains':
                return

        domains = [d.strip().lower() for d in message.text.split(',') if d.strip()]
        if not domains:
            await message.reply_text("❌ Please enter at least one domain.")
            return

        async with self.state_lock:
            self.user_data[user_id]['domains'] = domains

        await self.start_processing(user_id, message)

    async def start_processing(self, user_id: int, message: Message):
        async with self.state_lock:
            data = self.user_data.get(user_id)
        if not data:
            await message.reply_text("❌ Error: No data found. Please start over.")
            return

        task_id = generate_random_string(8)
        await self.task_manager.register_task(user_id, task_id, data)

        progress_msg = await self.send_progress_message(
            user_id,
            f"🚀 **Starting process...**\n\n"
            f"📦 File: `{data['filename']}`\n"
            f"🔑 Password: {'Yes' if data.get('password') else 'No'}\n"
            f"🎯 Domains: {', '.join(data['domains'])}\n\n"
            f"🔴 /cancel_{task_id} to cancel"
        )

        processing_task = asyncio.create_task(
            self._process_user_task(user_id, data, progress_msg, task_id)
        )
        self.active_tasks[user_id] = processing_task

        try:
            await processing_task
        except asyncio.CancelledError:
            await progress_msg.edit_text("❌ **Task cancelled by user**")
        finally:
            self.active_tasks.pop(user_id, None)
            await self.task_manager.clear_task(user_id)

    async def _process_user_task(self, user_id: int, data: Dict,
                                  progress_msg: Message, task_id: str):
        download_folder = extract_folder = None
        try:
            uid = datetime.now().strftime('%H%M%S_') + generate_random_string(4)
            download_folder = os.path.join(self.downloads_dir, f"download_{uid}")
            extract_folder = os.path.join(self.downloads_dir, f"extract_{uid}")
            result_folder = os.path.join(self.results_dir, datetime.now().strftime('%Y-%m-%d'))
            for d in (download_folder, extract_folder, result_folder):
                os.makedirs(d, exist_ok=True)

            data['download_folder'] = download_folder
            data['extract_folder'] = extract_folder

            # ── 1. Download ───────────────────────────────────────────────────
            file_path = os.path.join(download_folder, sanitize_filename(data['filename']))
            if data['type'] == 'telegram':
                success, archive_type = await self.download_telegram_file(
                    data['message'], file_path, progress_msg, task_id, data['filename'])
            else:
                success, archive_type = await self.download_file(
                    data['url'], file_path, progress_msg, task_id, data['filename'])

            if not success or await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return

            if archive_type:
                data['archive_type'] = archive_type
                if not data['filename'].lower().endswith(archive_type):
                    data['filename'] = os.path.splitext(data['filename'])[0] + archive_type

            # ── 2. Extract ────────────────────────────────────────────────────
            await progress_msg.edit_text(
                f"📦 **Extracting archives...**\n"
                f"📄 File: `{data['filename']}`\n"
                f"📁 Type: `{(archive_type or 'Unknown').upper()}`\n\n"
                f"🔴 /cancel_{task_id} to cancel"
            )

            extract_progress = ProgressTracker(
                progress_msg, 1, "📦 Extracting",
                self.task_manager, data['filename'], mode='count',
                rate_limiter=self.global_rate_limiter
            )
            await extract_progress.start_periodic_updates()

            extractor = UltimateArchiveExtractor(data.get('password'))
            loop = asyncio.get_event_loop()
            extractor.set_progress(extract_progress, self.task_manager, user_id, loop)

            await extractor.extract_all_nested(file_path, extract_folder)
            await extract_progress.stop_periodic_updates()

            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return

            # ── 3. Filter cookies ─────────────────────────────────────────────
            await progress_msg.edit_text(
                f"🔍 **Filtering cookies...**\n"
                f"🎯 Domains: {', '.join(data['domains'])}\n\n"
                f"🔴 /cancel_{task_id} to cancel"
            )

            cookie_progress = ProgressTracker(
                progress_msg, 1, "🔍 Filtering",
                self.task_manager, data['filename'], mode='count',
                rate_limiter=self.global_rate_limiter
            )
            await cookie_progress.start_periodic_updates()

            cookie_extractor = UltimateCookieExtractor(data['domains'])
            cookie_extractor.set_progress(cookie_progress, self.task_manager, user_id, loop)

            await cookie_extractor.process_all(extract_folder)
            await cookie_progress.stop_periodic_updates()

            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return

            # ── 4. Create ZIPs ────────────────────────────────────────────────
            await progress_msg.edit_text(
                f"📦 **Creating ZIP archives...**\n\n🔴 /cancel_{task_id} to cancel")

            created_zips = await loop.run_in_executor(
                thread_pool, cookie_extractor.create_site_zips,
                extract_folder, result_folder
            )

            if await self.task_manager.is_cancelled(user_id):
                await self.cleanup_user_files(user_id, download_folder, extract_folder)
                return

            # ── 5. Send results ───────────────────────────────────────────────
            if created_zips:
                task_info = await self.task_manager.get_task(user_id)
                elapsed = time.time() - task_info['start_time'] if task_info else 0

                await progress_msg.edit_text(
                    f"✅ **Processing Complete!**\n\n"
                    f"⏱️ Time: {format_time(elapsed)}\n"
                    f"📁 Files processed: {cookie_extractor.files_processed}\n"
                    f"🔍 Entries found: {cookie_extractor.total_found}\n"
                    f"📦 ZIP archives: {len(created_zips)}\n\n"
                    f"📤 **Sending files...**"
                )

                for site, zip_path in created_zips.items():
                    if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                        await self.app.send_document(
                            user_id, zip_path,
                            caption=(f"🍪 Cookies for: `{site}`\n"
                                     f"📊 Files: {len(cookie_extractor.site_files[site])}"),
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(1)  # Increased delay between file sends

                await self.app.send_message(
                    user_id,
                    "✅ **All files sent!**\nUse /start to process another archive."
                )
                await self.log_to_channel(
                    f"✅ **Process Complete**\n"
                    f"👤 User: `{user_id}`\n"
                    f"📦 File: `{data['filename']}`\n"
                    f"📁 Type: `{data.get('archive_type', 'Unknown')}`\n"
                    f"⏱️ Time: {format_time(elapsed)}\n"
                    f"🔍 Entries: {cookie_extractor.total_found}\n"
                    f"📦 Zips: {len(created_zips)}"
                )
            else:
                await progress_msg.edit_text(
                    "❌ **No matching cookies found**\n"
                    "The archive was processed but no cookies matched your domains."
                )

            await self.cleanup_user_files(user_id, download_folder, extract_folder)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            await progress_msg.edit_text(f"❌ **Error:** {str(e)}")
            await self.log_to_channel(f"❌ Error for user {user_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            await self.cleanup_user_files(user_id, download_folder, extract_folder)
        finally:
            async with self.state_lock:
                self.user_data.pop(user_id, None)
                self.user_states.pop(user_id, None)

    async def cleanup_user_files(self, user_id: int, *folders):
        for folder in folders:
            if folder and os.path.exists(folder):
                await delete_entire_folder(folder)

    def run(self):
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
            user_id = message.from_user.id
            async with self.state_lock:
                is_domains = self.user_states.get(user_id) == 'awaiting_domains'
            if is_domains:
                await self.handle_domains(client, message)
            else:
                await self.handle_text(client, message)

        @self.app.on_callback_query()
        async def callback_handler(client, callback_query):
            await self.handle_callback(client, callback_query)

        self.app.run()

# ==============================================================================
#                                MAIN
# ==============================================================================

if __name__ == "__main__":
    ts = []
    ts.append(f"{Fore.GREEN}✓ UnRAR{Style.RESET_ALL}" if TOOL_STATUS['unrar']
              else f"{Fore.RED}✗ UnRAR{Style.RESET_ALL}")
    ts.append(f"{Fore.GREEN}✓ 7z{Style.RESET_ALL}" if TOOL_STATUS['7z']
              else f"{Fore.RED}✗ 7z{Style.RESET_ALL}")

    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════╗
║{Fore.YELLOW}     🚀 COOKIE EXTRACTOR BOT - TELEGRAM VERSION 🚀     {Fore.CYAN}║
║{Fore.WHITE}  Tools: {' · '.join(ts):<50}{Fore.CYAN}║
║{Fore.WHITE}  Multi-user · Progress Bars · Auto-Cleanup             {Fore.CYAN}║
║{Fore.WHITE}  Rate Limited · Flood Wait Protected                   {Fore.CYAN}║
╚══════════════════════════════════════════════════════════╝{Style.RESET_ALL}""")

    bot = CookieExtractorBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Bot stopped by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
