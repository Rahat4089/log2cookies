#!/usr/bin/env python3
"""
RUTE Cookie Extractor Bot - ULTIMATE EDITION ENHANCED
Telegram Bot with live counting, per-domain stats, and proper log forwarding
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
import uuid
import gc
import json
from datetime import datetime, timedelta
from typing import List, Set, Dict, Optional, Tuple, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from threading import Lock, Thread
from asyncio import Queue, TimeoutError
from collections import defaultdict, deque, Counter
import traceback
import functools
import queue

# Pyrofork imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, RPCError
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.enums import ParseMode

# Third-party imports
try:
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style, Back
    colorama.init(autoreset=True)
except ImportError:
    os.system("pip install -q tqdm colorama")
    from tqdm import tqdm
    import colorama
    from colorama import Fore, Style, Back
    colorama.init(autoreset=True)

# Archive libraries
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

# Bot Configuration
API_ID = 23933044
API_HASH = "6df11147cbec7d62a323f0f498c8c03a"
BOT_TOKEN = "8315539700:AAH3NGnaLNQeeV6-2wNJsDFmGPjXInU2YeY"
LOG_CHANNEL = -1003747061396
SEND_LOGS = True
ADMINS = [7125341830]
OWNER_TAG = "@still_alivenow"

# Performance Settings
MAX_WORKERS = 100
BUFFER_SIZE = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024
INPUT_TIMEOUT = 30  # 30 seconds for password/domain input
CLEANUP_DELAY = 5
PROGRESS_UPDATE_INTERVAL = 2  # Update progress every 2 seconds

# UI Elements - Expanded emoji set
SUCCESS_EMOJI = "✅"
ERROR_EMOJI = "❌"
WARNING_EMOJI = "⚠️"
INFO_EMOJI = "ℹ️"
DOWNLOAD_EMOJI = "📥"
UPLOAD_EMOJI = "📤"
EXTRACT_EMOJI = "📦"
FILTER_EMOJI = "🔍"
COMPLETE_EMOJI = "🎉"
CANCEL_EMOJI = "🚫"
QUEUE_EMOJI = "📋"
STATS_EMOJI = "📊"
CLOCK_EMOJI = "⏱️"
SPEED_EMOJI = "⚡"
MEMORY_EMOJI = "🧠"
DISK_EMOJI = "💾"
CPU_EMOJI = "⚙️"
NETWORK_EMOJI = "🌐"
BOT_EMOJI = "🤖"
LOCK_EMOJI = "🔒"
UNLOCK_EMOJI = "🔓"
KEY_EMOJI = "🔑"
FILE_EMOJI = "📁"
ARCHIVE_EMOJI = "🗜️"
COOKIE_EMOJI = "🍪"
USER_EMOJI = "👤"
FIRE_EMOJI = "🔥"
STAR_EMOJI = "⭐"
DIAMOND_EMOJI = "💎"
ROCKET_EMOJI = "🚀"
PARTY_EMOJI = "🥳"
TROPHY_EMOJI = "🏆"
MAGIC_EMOJI = "✨"
ZAP_EMOJI = "⚡"
HEART_EMOJI = "❤️"
CHART_EMOJI = "📈"
BAR_CHART_EMOJI = "📊"
PIE_CHART_EMOJI = "🥧"
GEAR_EMOJI = "⚙️"
TOOLBOX_EMOJI = "🧰"
MICROSCOPE_EMOJI = "🔬"
MAGNIFIER_EMOJI = "🔎"
PACKAGE_EMOJI = "📦"
SCROLL_EMOJI = "📜"
CROWN_EMOJI = "👑"
MEDAL_EMOJI = "🏅"
FORWARD_EMOJI = "↗️"

SUPPORTED_ARCHIVES = {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'}
COOKIE_FOLDERS = {'Cookies', 'Browsers'}
TEMP_DIR = "temp_downloads"
RESULTS_DIR = "bot_results"

# Create directories
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

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
#                            UTILITY FUNCTIONS
# ==============================================================================

def format_size(size_bytes: int) -> str:
    """Quick size formatting"""
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_time(seconds: float) -> str:
    """Format seconds to human readable"""
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
    if bytes_per_sec < 0:
        return "0 B/s"
    return f"{format_size(bytes_per_sec)}/s"

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

def delete_entire_folder(folder_path: str) -> bool:
    """Delete entire folder in one operation"""
    if not os.path.exists(folder_path):
        return True
    
    try:
        gc.collect()
        time.sleep(0.5)
        
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

def create_fancy_progress_bar(progress: float, width: int = 15, style: str = "default") -> str:
    """Create a fancy progress bar with multiple styles"""
    filled = int(width * progress)
    
    styles = {
        "default": ("█", "░"),
        "blocks": ("🟩", "⬜"),
        "circles": ("●", "○"),
        "stars": ("⭐", "☆"),
        "hearts": ("❤️", "🩶"),
        "diamonds": ("💎", "🔹"),
        "fire": ("🔥", "💨"),
        "zap": ("⚡", "⋯"),
    }
    
    fill_char, empty_char = styles.get(style, styles["default"])
    
    if style == "fire":
        # Special fire effect
        bar = ""
        for i in range(width):
            if i < filled:
                if i < width * 0.3:
                    bar += "🔥"
                elif i < width * 0.6:
                    bar += "⚡"
                else:
                    bar += "✨"
            else:
                bar += "💨"
        return bar
    
    return fill_char * filled + empty_char * (width - filled)

def create_fancy_header(title: str, emoji: str = ROCKET_EMOJI, width: int = 42) -> str:
    """Create a fancy header with decorations"""
    top = f"╔{'═' * width}╗"
    middle = f"║{emoji}  {title.upper():^{width-5}}  {emoji}║"
    bottom = f"╚{'═' * width}╝"
    return f"{top}\n{middle}\n{bottom}"

def create_fancy_footer() -> str:
    """Create a fancy footer with owner info"""
    return f"\n{DIAMOND_EMOJI} Powered by {OWNER_TAG} {DIAMOND_EMOJI}"

def create_domain_stats_display(stats: Dict[str, int], total: int) -> str:
    """Create a beautiful domain statistics display"""
    if not stats:
        return ""
    
    # Sort domains by count (highest first)
    sorted_domains = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    
    # Find the longest domain name for alignment
    max_domain_len = max(len(domain) for domain in stats.keys())
    max_domain_len = min(max_domain_len, 20)  # Cap at 20
    
    display = f"\n{CHART_EMOJI} **DOMAIN STATISTICS** {CHART_EMOJI}\n"
    display += "```\n"
    
    for domain, count in sorted_domains[:10]:  # Show top 10 only
        # Truncate long domain names
        display_domain = domain[:max_domain_len] + "..." if len(domain) > max_domain_len else domain
        # Calculate percentage
        percentage = (count / total * 100) if total > 0 else 0
        # Create mini bar
        bar_length = int(percentage / 5)  # Scale to 20 chars max
        bar = "█" * bar_length
        
        display += f"{display_domain:<{max_domain_len+2}} │ {bar:<20} │ {count:>4} ({percentage:>5.1f}%)\n"
    
    display += "```\n"
    return display

async def safe_edit_message(message: Message, text: str, reply_markup=None):
    """Safely edit a message with error handling"""
    try:
        await message.edit_text(text, reply_markup=reply_markup, disable_web_page_preview=True)
    except Exception as e:
        print(f"Error editing message: {e}")

async def safe_send_message(client: Client, chat_id: int, text: str, **kwargs):
    """Safely send a message with error handling"""
    try:
        return await client.send_message(chat_id, text, disable_web_page_preview=True, **kwargs)
    except Exception as e:
        print(f"Error sending message: {e}")
        return None

async def safe_send_document(client: Client, chat_id: int, file_path: str, **kwargs):
    """Safely send a document with error handling"""
    try:
        return await client.send_document(chat_id, file_path, **kwargs)
    except Exception as e:
        print(f"Error sending document: {e}")
        return None

async def safe_forward_message(client: Client, chat_id: int, from_chat_id: int, message_id: int):
    """Safely forward a message"""
    try:
        return await client.forward_messages(chat_id, from_chat_id, message_id)
    except Exception as e:
        print(f"Error forwarding message: {e}")
        return None

def run_in_executor(f):
    """Decorator to run blocking functions in executor"""
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: f(*args, **kwargs))
    return wrapper

def get_system_stats() -> str:
    """Get detailed system statistics with cool UI"""
    try:
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_total = disk.total
        disk_used = disk.used
        disk_free = disk.free
        disk_percent = disk.percent
        
        # Memory usage
        memory = psutil.virtual_memory()
        mem_total = memory.total
        mem_used = memory.used
        mem_percent = memory.percent
        mem_free = memory.free
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        cpu_freq_current = cpu_freq.current if cpu_freq else 0
        
        # Process info
        process = psutil.Process()
        process_cpu = process.cpu_percent(interval=0.1)
        process_memory_rss = process.memory_info().rss
        process_memory_vms = process.memory_info().vms
        process_threads = process.num_threads()
        # Fix: Use net_connections() instead of deprecated connections()
        process_connections = len(process.net_connections())
        
        # Network
        net_io = psutil.net_io_counters()
        bytes_sent = net_io.bytes_sent
        bytes_recv = net_io.bytes_recv
        total_io = bytes_sent + bytes_recv
        
        try:
            net_io2 = psutil.net_io_counters()
            time.sleep(0.1)
            net_io3 = psutil.net_io_counters()
            upload_speed = (net_io3.bytes_sent - net_io2.bytes_sent) / 0.1
            download_speed = (net_io3.bytes_recv - net_io2.bytes_recv) / 0.1
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
        
        # Create fancy bars
        mem_bar = create_fancy_progress_bar(mem_percent / 100, 15, "blocks")
        disk_bar = create_fancy_progress_bar(disk_percent / 100, 15, "blocks")
        cpu_bar = create_fancy_progress_bar(cpu_percent / 100, 15, "zap")
        
        stats = f"""
{create_fancy_header("SYSTEM STATISTICS", STATS_EMOJI)}

{DISK_EMOJI} **DISK STORAGE**
├ Total:  `{format_size(disk_total)}`
├ Used:   `{format_size(disk_used)}` {disk_bar} `{disk_percent:.1f}%`
└ Free:   `{format_size(disk_free)}`

{MEMORY_EMOJI} **RAM MEMORY**
├ Total:  `{format_size(mem_total)}`
├ Used:   `{format_size(mem_used)}` {mem_bar} `{mem_percent:.1f}%`
└ Free:   `{format_size(mem_free)}`

{CPU_EMOJI} **CPU**
├ Cores:  `{cpu_count}`
├ Freq:   `{cpu_freq_current/1000:.2f} GHz`
└ Usage:  {cpu_bar} `{cpu_percent:.1f}%`

{BOT_EMOJI} **BOT PROCESS**
├ CPU:    `{process_cpu:.1f}%`
├ Threads: `{process_threads}`
├ RAM RSS: `{format_size(process_memory_rss)}`
├ RAM VMS: `{format_size(process_memory_vms)}`
└ Connections: `{process_connections}`

{NETWORK_EMOJI} **NETWORK**
├ Upload:   `{format_speed(upload_speed)}`
├ Download: `{format_speed(download_speed)}`
└ Total I/O: `{format_size(total_io)}`

{INFO_EMOJI} **SYSTEM INFO**
├ OS:      `{os_name} {os_version}`
├ Python:  `{python_version}`
└ Uptime:  `{uptime_str}`

{create_fancy_footer()}"""
        return stats
    except Exception as e:
        return f"{ERROR_EMOJI} Error getting system stats: {e}"

# ==============================================================================
#                            PASSWORD DETECTION
# ==============================================================================

class PasswordDetector:
    """Detect if archive is password protected"""
    
    @staticmethod
    def check_rar_protected(archive_path: str) -> bool:
        """Check RAR password protection"""
        try:
            if not HAS_RARFILE:
                if TOOL_STATUS['unrar']:
                    try:
                        cmd = [TOOL_PATHS['unrar'], 'l', archive_path]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        return 'password' in result.stderr.lower() or 'encrypted' in result.stderr.lower()
                    except:
                        pass
                return True
            
            with rarfile.RarFile(archive_path) as rf:
                return rf.needs_password()
        except:
            return True
    
    @staticmethod
    def check_7z_protected(archive_path: str) -> bool:
        """Check 7z password protection"""
        try:
            if not HAS_PY7ZR:
                if TOOL_STATUS['7z']:
                    try:
                        cmd = [TOOL_PATHS['7z'], 'l', archive_path]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        return 'Encrypted' in result.stdout or 'Password' in result.stdout
                    except:
                        pass
                return True
            
            with py7zr.SevenZipFile(archive_path, mode='r') as sz:
                return sz.password_protected
        except:
            return True
    
    @staticmethod
    def check_zip_protected(archive_path: str) -> bool:
        """Check ZIP password protection"""
        try:
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
            
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for info in zf.infolist():
                    if info.flag_bits & 0x1:
                        return True
                return False
        except:
            return True

# ==============================================================================
#                            PROGRESS TRACKER
# ==============================================================================

class ProgressTracker:
    """Thread-safe progress tracker with live updates"""
    
    def __init__(self, task_id: str, update_callback: Callable, loop: asyncio.AbstractEventLoop):
        self.task_id = task_id
        self.update_callback = update_callback
        self.loop = loop
        self.lock = Lock()
        self.extraction_count = 0
        self.total_archives = 1
        self.filtered_files = 0
        self.total_files = 0
        self.domain_counts = Counter()
        self.start_time = time.time()
        self.last_update = 0
    
    def update_extraction(self, count: int, total: int):
        """Update extraction progress"""
        with self.lock:
            self.extraction_count = count
            self.total_archives = max(total, 1)
            self._maybe_update()
    
    def update_filtering(self, processed: int, total: int, domain_counts: Dict[str, int] = None):
        """Update filtering progress"""
        with self.lock:
            self.filtered_files = processed
            self.total_files = total
            if domain_counts:
                self.domain_counts.update(domain_counts)
            self._maybe_update()
    
    def _maybe_update(self):
        """Update if enough time has passed"""
        now = time.time()
        if now - self.last_update >= PROGRESS_UPDATE_INTERVAL:
            self.last_update = now
            # Create progress data
            progress_data = {
                "extraction": {
                    "current": self.extraction_count,
                    "total": self.total_archives,
                    "percent": self.extraction_count / self.total_archives if self.total_archives > 0 else 0
                },
                "filtering": {
                    "current": self.filtered_files,
                    "total": self.total_files,
                    "percent": self.filtered_files / self.total_files if self.total_files > 0 else 0
                },
                "domain_counts": dict(self.domain_counts.most_common(10)),  # Top 10 domains
                "elapsed": time.time() - self.start_time
            }
            # Use call_soon_threadsafe to run async callback from thread
            asyncio.run_coroutine_threadsafe(
                self.update_callback(self.task_id, progress_data),
                self.loop
            )

# ==============================================================================
#                            ARCHIVE EXTRACTION
# ==============================================================================

class UltimateArchiveExtractor:
    """Ultimate speed archive extraction with progress tracking"""
    
    def __init__(self, password: Optional[str] = None, tracker: ProgressTracker = None):
        self.password = password
        self.processed_files: Set[str] = set()
        self.lock = Lock()
        self.extracted_count = 0
        self.stop_extraction = False
        self.tracker = tracker
    
    def extract_7z_with_7z(self, archive_path: str, extract_dir: str) -> List[str]:
        """Extract .7z using 7z.exe"""
        try:
            cmd = [TOOL_PATHS['7z'], 'x', '-y']
            if self.password:
                cmd.append(f'-p{self.password}')
            cmd.append(f'-o{extract_dir}')
            cmd.append(archive_path)
            
            result = subprocess.run(cmd, capture_output=True, timeout=None)
            
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
            
            result = subprocess.run(cmd, capture_output=True, timeout=None)
            
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
                
                result = subprocess.run(cmd, capture_output=True, timeout=None)
                
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
                
                result = subprocess.run(cmd, capture_output=True, timeout=None)
                
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
            print(f"Python zip extraction error: {e}")
            return []
    
    def extract_rar_fallback(self, archive_path: str, extract_dir: str) -> List[str]:
        """Fallback RAR extraction"""
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
        """Extract all nested archives with progress tracking"""
        current_level = {root_archive}
        level = 0
        total_archives = 1
        
        # Update tracker with initial count
        if self.tracker:
            self.tracker.update_extraction(0, 1)
        
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
                        extracted = future.result()
                        with self.lock:
                            self.processed_files.add(archive)
                            self.extracted_count += 1
                            
                            # Update tracker
                            if self.tracker:
                                self.tracker.update_extraction(self.extracted_count, total_archives)
                        
                        new_archives = self.find_archives_fast(extract_subdir)
                        next_level.update(new_archives)
                        
                        with self.lock:
                            total_archives += len(new_archives)
                            if self.tracker:
                                self.tracker.update_extraction(self.extracted_count, total_archives)
                        
                    except Exception as e:
                        print(f"Error processing future: {e}")
            
            current_level = next_level
            level += 1
        
        return base_dir

# ==============================================================================
#                            COOKIE EXTRACTION
# ==============================================================================

class UltimateCookieExtractor:
    """Ultimate speed cookie extraction with per-site filtering and live counting"""
    
    def __init__(self, target_sites: List[str], tracker: ProgressTracker = None):
        self.target_sites = [s.strip().lower() for s in target_sites]
        self.site_files: Dict[str, Dict[str, str]] = {site: {} for site in self.target_sites}
        self.global_seen: Set[str] = set()
        self.seen_lock = Lock()
        self.stats_lock = Lock()
        self.total_found = 0
        self.files_processed = 0
        self.used_filenames: Dict[str, Set[str]] = {site: set() for site in self.target_sites}
        self.stop_processing = False
        self.tracker = tracker
        self.domain_counter = Counter()
        self.total_files = 0
        
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
        
        # Update tracker with total files
        if self.tracker:
            self.tracker.update_filtering(0, self.total_files)
        
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
        """Process a single file with live counting"""
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
            
            # Track domains found in this file for live updates
            file_domain_counts = Counter()
            
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
                                    file_domain_counts[site] += 1
            
            # Update domain counter
            if file_domain_counts:
                with self.stats_lock:
                    self.domain_counter.update(file_domain_counts)
            
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
                
                # Update tracker with progress and domain counts
                if self.tracker:
                    self.tracker.update_filtering(
                        self.files_processed,
                        self.total_files,
                        dict(self.domain_counter)
                    )
                
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
    
    def process_all(self, extract_dir: str):
        """Process all files with live counting"""
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
            
            for future in as_completed(futures):
                if self.stop_processing:
                    executor.shutdown(wait=False)
                    break
                future.result()
    
    def create_site_zips(self, extract_dir: str, result_folder: str) -> Dict[str, str]:
        """Create ZIP archives per site"""
        created_zips = {}
        
        for site, files_dict in self.site_files.items():
            if not files_dict:
                continue
            
            timestamp = datetime.now().strftime('%H%M%S')
            zip_name = f"{sanitize_filename(site)}_{timestamp}.zip"
            zip_path = os.path.join(result_folder, zip_name)
            
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                    for file_path, unique_name in files_dict.items():
                        if os.path.exists(file_path):
                            zf.write(file_path, unique_name)
                
                created_zips[site] = zip_path
            except Exception as e:
                print(f"Error creating zip for {site}: {e}")
        
        return created_zips

# ==============================================================================
#                            BOT TASK MANAGER
# ==============================================================================

class TaskStatus:
    WAITING_PASSWORD = "waiting_password"
    WAITING_DOMAINS = "waiting_domains"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    FILTERING = "filtering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"

class UserTask:
    def __init__(self, user_id: int, user_name: str, message_id: int, chat_id: int):
        self.task_id = str(uuid.uuid4())[:8]
        self.user_id = user_id
        self.user_name = user_name
        self.message_id = message_id
        self.chat_id = chat_id
        self.status = TaskStatus.WAITING_DOMAINS
        self.archive_path = None
        self.password = None
        self.domains = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.progress = 0
        self.progress_message = ""
        self.downloaded_size = 0
        self.total_size = 0
        self.extract_folder = None
        self.result_zips = []
        self.error = None
        self.cancel_requested = False
        self.status_message = None
        self.start_time = None
        self.last_update_time = None
        self.download_start_time = None
        self.speed_history = deque(maxlen=10)
        self.timeout_task = None
        self.current_file_name = ""
        self.last_progress_update = 0
        self.tracker = None
        self.extraction_count = 0
        self.total_archives = 1
        self.filtered_count = 0
        self.total_files = 0
        self.domain_counts = {}
        self.original_message_id = None  # Store original message ID for forwarding
    
    def update_status(self, status: str, progress: float = None, message: str = None):
        """Update task status"""
        self.status = status
        self.updated_at = datetime.now()
        if progress is not None:
            self.progress = progress
        if message:
            self.progress_message = message
    
    def get_cancel_button(self) -> InlineKeyboardMarkup:
        """Get cancel button for this task"""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{CANCEL_EMOJI} Cancel Task {CANCEL_EMOJI}", callback_data=f"cancel_{self.task_id}")]
        ])
        return keyboard
    
    def to_dict(self):
        """Convert to dictionary for display"""
        status_emoji = {
            TaskStatus.WAITING_PASSWORD: KEY_EMOJI,
            TaskStatus.WAITING_DOMAINS: INFO_EMOJI,
            TaskStatus.DOWNLOADING: DOWNLOAD_EMOJI,
            TaskStatus.EXTRACTING: EXTRACT_EMOJI,
            TaskStatus.FILTERING: FILTER_EMOJI,
            TaskStatus.COMPLETED: COMPLETE_EMOJI,
            TaskStatus.FAILED: ERROR_EMOJI,
            TaskStatus.CANCELLED: CANCEL_EMOJI,
            TaskStatus.TIMEOUT: WARNING_EMOJI
        }.get(self.status, INFO_EMOJI)
        
        return {
            "task_id": self.task_id,
            "user": self.user_name,
            "user_id": self.user_id,
            "status": f"{status_emoji} {self.status}",
            "progress": f"{self.progress*100:.1f}%" if self.progress else "0%",
            "message": self.progress_message,
            "size": format_size(self.total_size) if self.total_size else "Unknown",
            "file": os.path.basename(self.archive_path) if self.archive_path else "N/A",
            "domains": ", ".join(self.domains) if self.domains else "Not set",
            "created": self.created_at.strftime("%H:%M:%S"),
            "elapsed": str(datetime.now() - self.created_at).split('.')[0]
        }

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, UserTask] = {}
        self.user_tasks: Dict[int, str] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.active_tasks: Set[str] = set()
        self.lock = asyncio.Lock()
        self.processing = False
        self.worker_task = None
    
    def create_task(self, user_id: int, user_name: str, message_id: int, chat_id: int) -> UserTask:
        """Create a new task"""
        # Cancel any existing task for this user
        if user_id in self.user_tasks:
            old_task_id = self.user_tasks[user_id]
            if old_task_id in self.tasks:
                asyncio.create_task(self.cancel_task(old_task_id, user_id))
        
        task = UserTask(user_id, user_name, message_id, chat_id)
        task.original_message_id = message_id
        self.tasks[task.task_id] = task
        self.user_tasks[user_id] = task.task_id
        return task
    
    async def add_to_queue(self, task_id: str):
        """Add task to processing queue"""
        await self.queue.put(task_id)
    
    def get_task(self, task_id: str) -> Optional[UserTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_user_task(self, user_id: int) -> Optional[UserTask]:
        """Get current task for user"""
        if user_id in self.user_tasks:
            return self.tasks.get(self.user_tasks[user_id])
        return None
    
    async def cancel_task(self, task_id: str, user_id: int = None) -> bool:
        """Cancel a task"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if user_id and task.user_id != user_id and user_id not in ADMINS:
                return False
            
            task.cancel_requested = True
            task.status = TaskStatus.CANCELLED
            
            # Cancel timeout task if exists
            if task.timeout_task:
                task.timeout_task.cancel()
            
            # Clean up files
            try:
                if task.archive_path and os.path.exists(task.archive_path):
                    os.remove(task.archive_path)
                
                if task.extract_folder and os.path.exists(task.extract_folder):
                    delete_entire_folder(task.extract_folder)
                
                for zip_path in task.result_zips:
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
            except Exception as e:
                print(f"Error cleaning up task {task_id}: {e}")
            
            if user_id in self.user_tasks and self.user_tasks[user_id] == task_id:
                del self.user_tasks[user_id]
            
            return True
        return False
    
    async def timeout_task(self, task_id: str, timeout_type: str):
        """Handle task timeout"""
        await asyncio.sleep(INPUT_TIMEOUT)
        
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status in [TaskStatus.WAITING_PASSWORD, TaskStatus.WAITING_DOMAINS]:
                task.status = TaskStatus.TIMEOUT
                task.error = f"Timeout waiting for {timeout_type}"
                
                # Clean up
                await self.cancel_task(task_id)
                
                # Notify user
                if task.status_message:
                    try:
                        await task.status_message.edit_text(
                            f"{WARNING_EMOJI} **Task Cancelled Due to Timeout!**\n\n"
                            f"No {timeout_type} provided within {INPUT_TIMEOUT} seconds.\n\n"
                            f"{ROCKET_EMOJI} Send a new file to start again."
                        )
                    except:
                        pass
    
    def get_queue_info(self) -> List[Dict]:
        """Get information about all tasks in queue"""
        queue_info = []
        for task_id in list(self.queue._queue):
            if task_id in self.tasks:
                queue_info.append(self.tasks[task_id].to_dict())
        
        for task_id in self.active_tasks:
            if task_id in self.tasks:
                task_info = self.tasks[task_id].to_dict()
                task_info["status"] = f"{FIRE_EMOJI} ACTIVE - {task_info['status']}"
                queue_info.insert(0, task_info)
        
        return queue_info

# ==============================================================================
#                            BOT CLASS
# ==============================================================================

class CookieExtractorBot:
    def __init__(self):
        self.app = Client(
            "cookie_extractor_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )
        self.task_manager = TaskManager()
        self.start_time = datetime.now()
        self.processing_lock = asyncio.Lock()
        self.loop = None
        
        # Register handlers
        self.app.on_message(filters.command("start"))(self.start_command)
        self.app.on_message(filters.command("help"))(self.help_command)
        self.app.on_message(filters.command("stats"))(self.stats_command)
        self.app.on_message(filters.command("queue"))(self.queue_command)
        self.app.on_message(filters.command("cancel"))(self.cancel_command)
        self.app.on_message(filters.document)(self.handle_document)
        self.app.on_message(filters.text & ~filters.command(["start", "help", "stats", "queue", "cancel"]))(self.handle_text)
        self.app.on_callback_query()(self.handle_callback)
    
    async def start_worker(self):
        """Background worker to process tasks"""
        while True:
            try:
                task_id = await self.task_manager.queue.get()
                task = self.task_manager.get_task(task_id)
                
                if not task or task.cancel_requested:
                    continue
                
                self.task_manager.active_tasks.add(task_id)
                
                try:
                    await self.process_task(task)
                except Exception as e:
                    print(f"Error processing task {task_id}: {e}")
                    traceback.print_exc()
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    await self.update_task_message(task, f"{ERROR_EMOJI} **Error:** {str(e)}")
                finally:
                    if task_id in self.task_manager.active_tasks:
                        self.task_manager.active_tasks.remove(task_id)
                    
                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT]:
                        if task.user_id in self.task_manager.user_tasks:
                            del self.task_manager.user_tasks[task.user_id]
                        
                        asyncio.create_task(self.cleanup_task_files(task))
                
                self.task_manager.queue.task_done()
                
            except Exception as e:
                print(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    async def cleanup_task_files(self, task: UserTask):
        """Clean up task files after delay"""
        await asyncio.sleep(CLEANUP_DELAY)
        
        try:
            if task.archive_path and os.path.exists(task.archive_path):
                os.remove(task.archive_path)
            
            if task.extract_folder and os.path.exists(task.extract_folder):
                delete_entire_folder(task.extract_folder)
            
            for zip_path in task.result_zips:
                if os.path.exists(zip_path):
                    os.remove(zip_path)
        except Exception as e:
            print(f"Error in cleanup: {e}")
    
    async def update_progress(self, task_id: str, progress_data: dict):
        """Update progress from tracker (called from thread)"""
        task = self.task_manager.get_task(task_id)
        if not task or task.cancel_requested:
            return
        
        # Update task with progress data
        extraction = progress_data.get("extraction", {})
        filtering = progress_data.get("filtering", {})
        domain_counts = progress_data.get("domain_counts", {})
        elapsed = progress_data.get("elapsed", 0)
        
        task.extraction_count = extraction.get("current", 0)
        task.total_archives = extraction.get("total", 1)
        task.filtered_count = filtering.get("current", 0)
        task.total_files = filtering.get("total", 0)
        task.domain_counts = domain_counts
        
        # Create progress display
        if task.status == TaskStatus.EXTRACTING:
            await self.show_extraction_progress(task, elapsed)
        elif task.status == TaskStatus.FILTERING:
            await self.show_filtering_progress(task, elapsed)
    
    async def show_extraction_progress(self, task: UserTask, elapsed: float):
        """Show extraction progress with live counts"""
        if task.cancel_requested:
            return
        
        progress = task.extraction_count / task.total_archives if task.total_archives > 0 else 0
        bar = create_fancy_progress_bar(progress, 20, "fire")
        
        text = (
            f"{EXTRACT_EMOJI} **EXTRACTING ARCHIVES** {EXTRACT_EMOJI}\n\n"
            f"{FILE_EMOJI} **File:** `{os.path.basename(task.archive_path)}`\n"
            f"{bar} `{progress*100:.1f}%`\n\n"
            f"{ARCHIVE_EMOJI} **Archives Extracted:** `{task.extraction_count} / {task.total_archives}`\n"
            f"{CLOCK_EMOJI} **Elapsed:** `{format_time(elapsed)}`\n\n"
            f"{ZAP_EMOJI} **Status:** Processing nested archives...\n\n"
            f"{task.get_cancel_button().inline_keyboard[0][0].text}"
        )
        
        await self.update_task_message(task, text, task.get_cancel_button())
    
    async def show_filtering_progress(self, task: UserTask, elapsed: float):
        """Show filtering progress with live counts and domain stats"""
        if task.cancel_requested:
            return
        
        progress = task.filtered_count / task.total_files if task.total_files > 0 else 0
        bar = create_fancy_progress_bar(progress, 20, "zap")
        
        text = (
            f"{FILTER_EMOJI} **FILTERING COOKIES** {FILTER_EMOJI}\n\n"
            f"{FILE_EMOJI} **Domains:** `{', '.join(task.domains)}`\n"
            f"{bar} `{progress*100:.1f}%`\n\n"
            f"{COOKIE_EMOJI} **Files Processed:** `{task.filtered_count} / {task.total_files}`\n"
            f"{CHART_EMOJI} **Entries Found:** `{sum(task.domain_counts.values())}`\n"
            f"{CLOCK_EMOJI} **Elapsed:** `{format_time(elapsed)}`\n"
        )
        
        # Add domain statistics if we have them
        if task.domain_counts:
            # Get top 5 domains
            top_domains = sorted(task.domain_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            text += f"\n{STAR_EMOJI} **Top Domains:**\n"
            for domain, count in top_domains:
                mini_bar = "█" * int((count / max(task.domain_counts.values())) * 10) if max(task.domain_counts.values()) > 0 else ""
                text += f"  `{domain[:15] + '...' if len(domain) > 15 else domain:<15}` {mini_bar} `{count}`\n"
        
        text += f"\n{task.get_cancel_button().inline_keyboard[0][0].text}"
        
        await self.update_task_message(task, text, task.get_cancel_button())
    
    async def process_task(self, task: UserTask):
        """Process a task"""
        try:
            if task.status == TaskStatus.WAITING_DOMAINS:
                # Set timeout for domains
                task.timeout_task = asyncio.create_task(
                    self.task_manager.timeout_task(task.task_id, "domains")
                )
                return
            
            if task.status == TaskStatus.WAITING_PASSWORD:
                # Set timeout for password
                task.timeout_task = asyncio.create_task(
                    self.task_manager.timeout_task(task.task_id, "password")
                )
                return
            
            if task.status == TaskStatus.DOWNLOADING:
                task.status = TaskStatus.EXTRACTING
                task.start_time = time.time()
                
                # Get the event loop for this task
                loop = asyncio.get_running_loop()
                
                # Create progress tracker with the loop
                task.tracker = ProgressTracker(task.task_id, self.update_progress, loop)
                
                await self.show_extraction_progress(task, 0)
                
                # Create extraction folder
                unique_id = datetime.now().strftime('%H%M%S') + f"_{task.task_id}"
                task.extract_folder = os.path.join(TEMP_DIR, f"extract_{unique_id}")
                os.makedirs(task.extract_folder, exist_ok=True)
                
                # Extract archives (run in executor to avoid blocking)
                extractor = UltimateArchiveExtractor(task.password, task.tracker)
                
                try:
                    extract_dir = await loop.run_in_executor(
                        None,
                        extractor.extract_all_nested,
                        task.archive_path,
                        task.extract_folder
                    )
                    
                    if task.cancel_requested:
                        return
                    
                    # Filter cookies
                    task.status = TaskStatus.FILTERING
                    await self.show_filtering_progress(task, time.time() - task.start_time)
                    
                    cookie_extractor = UltimateCookieExtractor(task.domains, task.tracker)
                    
                    await loop.run_in_executor(
                        None,
                        cookie_extractor.process_all,
                        extract_dir
                    )
                    
                    if task.cancel_requested:
                        return
                    
                    # Create ZIPs
                    if cookie_extractor.total_found > 0:
                        result_folder = os.path.join(RESULTS_DIR, datetime.now().strftime('%Y-%m-%d'))
                        os.makedirs(result_folder, exist_ok=True)
                        
                        created_zips = cookie_extractor.create_site_zips(extract_dir, result_folder)
                        task.result_zips = list(created_zips.values())
                        
                        # Send results to user
                        await self.send_results_to_user(task, cookie_extractor, created_zips)
                        
                        # Forward to log channel (using forward, not upload)
                        if SEND_LOGS and LOG_CHANNEL:
                            await self.forward_to_log_channel(task, cookie_extractor, created_zips)
                        
                        task.status = TaskStatus.COMPLETED
                        
                        elapsed = time.time() - task.start_time
                        
                        # Create beautiful completion message
                        completion_msg = (
                            f"{PARTY_EMOJI} **EXTRACTION COMPLETE!** {PARTY_EMOJI}\n\n"
                            f"{CLOCK_EMOJI} **Time:** `{format_time(elapsed)}`\n"
                            f"{ARCHIVE_EMOJI} **Archives Extracted:** `{task.extraction_count}`\n"
                            f"{FILE_EMOJI} **Files Processed:** `{cookie_extractor.files_processed}`\n"
                            f"{COOKIE_EMOJI} **Total Entries:** `{cookie_extractor.total_found}`\n"
                            f"{PACKAGE_EMOJI} **ZIP Archives:** `{len(created_zips)}`\n"
                        )
                        
                        # Add per-domain statistics
                        if cookie_extractor.domain_counter:
                            completion_msg += create_domain_stats_display(
                                dict(cookie_extractor.domain_counter.most_common()),
                                cookie_extractor.total_found
                            )
                        
                        completion_msg += f"\n{TROPHY_EMOJI} **Your files have been sent!** {TROPHY_EMOJI}"
                        completion_msg += create_fancy_footer()
                        
                        await self.update_task_message(task, completion_msg)
                        
                    else:
                        task.status = TaskStatus.COMPLETED
                        await self.update_task_message(
                            task,
                            f"{WARNING_EMOJI} **No Cookies Found** {WARNING_EMOJI}\n\n"
                            f"No matching cookies found for domains: `{', '.join(task.domains)}`\n\n"
                            f"{ROCKET_EMOJI} Try different domains or check the archive contents."
                            f"{create_fancy_footer()}"
                        )
                        
                except Exception as e:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    await self.update_task_message(
                        task,
                        f"{ERROR_EMOJI} **Extraction Error** {ERROR_EMOJI}\n\n"
                        f"Error: `{str(e)}`\n\n"
                        f"{WARNING_EMOJI} This could be due to:\n"
                        f"• Incorrect password\n"
                        f"• Corrupted archive\n"
                        f"• Unsupported compression\n\n"
                        f"Try again with a different file."
                        f"{create_fancy_footer()}"
                    )
        
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            await self.update_task_message(
                task,
                f"{ERROR_EMOJI} **Error** {ERROR_EMOJI}\n\n"
                f"Error: `{str(e)}`\n\n"
                f"{create_fancy_footer()}"
            )
    
    async def send_results_to_user(self, task: UserTask, cookie_extractor, created_zips):
        """Send results to user with cool formatting"""
        try:
            for site, zip_path in created_zips.items():
                if os.path.exists(zip_path):
                    file_count = len(cookie_extractor.site_files[site])
                    site_count = cookie_extractor.domain_counter.get(site, 0)
                    
                    caption = (
                        f"{COOKIE_EMOJI} **Cookies for `{site}`** {COOKIE_EMOJI}\n\n"
                        f"{FILE_EMOJI} **Source Files:** `{file_count}`\n"
                        f"{CHART_EMOJI} **Entries Found:** `{site_count}`\n"
                        f"{STAR_EMOJI} **Domain:** `{site}`\n\n"
                        f"{MAGIC_EMOJI} Happy scraping! {MAGIC_EMOJI}"
                    )
                    
                    await safe_send_document(
                        self.app,
                        task.chat_id,
                        zip_path,
                        caption=caption
                    )
                    await asyncio.sleep(1)
        except Exception as e:
            print(f"Error sending results to user: {e}")
    
    async def forward_to_log_channel(self, task: UserTask, cookie_extractor, created_zips):
        """Forward results to log channel (using forward, not upload)"""
        try:
            # Send detailed info message first
            info_msg = (
                f"{PACKAGE_EMOJI} **NEW TASK PROCESSED** {PACKAGE_EMOJI}\n\n"
                f"{USER_EMOJI} **User:** `{task.user_name}` (ID: `{task.user_id}`)\n"
                f"{FILE_EMOJI} **File:** `{os.path.basename(task.archive_path)}`\n"
                f"{DISK_EMOJI} **Size:** `{format_size(task.total_size)}`\n"
                f"{FILTER_EMOJI} **Domains:** `{', '.join(task.domains)}`\n"
                f"{KEY_EMOJI} **Password:** `{task.password if task.password else 'None'}`\n"
                f"{COOKIE_EMOJI} **Total Entries:** `{cookie_extractor.total_found}`\n"
                f"{CLOCK_EMOJI} **Time:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
            )
            
            # Add domain statistics
            if cookie_extractor.domain_counter:
                info_msg += create_domain_stats_display(
                    dict(cookie_extractor.domain_counter.most_common()),
                    cookie_extractor.total_found
                )
            
            await safe_send_message(self.app, LOG_CHANNEL, info_msg)
            
            # FORWARD the original file from user (not upload)
            if task.original_message_id:
                try:
                    await self.app.forward_messages(
                        LOG_CHANNEL,
                        task.chat_id,
                        task.original_message_id
                    )
                except Exception as e:
                    print(f"Error forwarding original file: {e}")
            
            # FORWARD the result files from the user's chat (they were just sent)
            # We need to get the message IDs of the sent files
            # Since we can't easily get them, we'll wait a bit and assume they were sent
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Error forwarding to log channel: {e}")
    
    async def update_task_message(self, task: UserTask, text: str, reply_markup=None):
        """Update task status message"""
        try:
            if task.status_message:
                await safe_edit_message(task.status_message, text, reply_markup)
            else:
                msg = await self.app.send_message(task.chat_id, text, reply_markup=reply_markup)
                task.status_message = msg
        except Exception as e:
            print(f"Error updating task message: {e}")
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command"""
        welcome_text = f"""
{create_fancy_header("RUTE COOKIE EXTRACTOR", ROCKET_EMOJI)}

{USER_EMOJI} **Welcome to the Ultimate Cookie Extractor!**

{ARCHIVE_EMOJI} **Supported Formats:** `.zip` `.rar` `.7z` `.tar` `.gz` `.bz2` `.xz`

{DIAMOND_EMOJI} **How to Use:**
1️⃣ Send me an archive file (max 4GB)
2️⃣ Enter domains to filter (comma-separated)
3️⃣ Enter password if required
4️⃣ Watch the live progress with cool counters!
5️⃣ Receive filtered cookies per domain

{FIRE_EMOJI} **Features:**
• 100 threads for maximum speed
• Live extraction counter
• Per-domain cookie statistics
• Nested archive support
• Real-time progress tracking
• Auto-cleanup after processing

{CLOCK_EMOJI} **Timeout:** `{INPUT_TIMEOUT}s` for password/domain input

**Commands:**
/stats - View system statistics
/queue - View current queue
/cancel - Cancel your task

{create_fancy_footer()}"""
        await message.reply_text(welcome_text)
    
    async def help_command(self, client: Client, message: Message):
        """Handle /help command"""
        help_text = f"""
{create_fancy_header("HELP & GUIDE", SCROLL_EMOJI)}

{ARCHIVE_EMOJI} **Supported Formats:**
• ZIP archives (.zip)
• RAR archives (.rar)
• 7Z archives (.7z)
• TAR archives (.tar, .tar.gz, .tar.bz2)
• GZIP files (.gz)
• BZIP2 files (.bz2)
• XZ files (.xz)

{DISK_EMOJI} **Maximum File Size:** `4GB`

{CLOCK_EMOJI} **Timeout Settings:**
• Password input: `{INPUT_TIMEOUT}s`
• Domain input: `{INPUT_TIMEOUT}s`

{INFO_EMOJI} **Processing Steps:**
1️⃣ **Upload** - Send your archive
2️⃣ **Domains** - Enter domains (e.g., `google.com, facebook.com`)
3️⃣ **Password** - Enter password if archive is protected
4️⃣ **Extraction** - Watch live counter of extracted archives
5️⃣ **Filtering** - See per-domain cookie counts in real-time
6️⃣ **Results** - Receive ZIP files with detailed statistics

{SPEED_EMOJI} **Performance:**
• 100 concurrent threads
• 20MB buffer size
• Optimized tools per format

**Commands:**
/start - Start the bot
/help - Show this help
/stats - View system statistics  
/queue - View current queue
/cancel - Cancel your task

{create_fancy_footer()}"""
        await message.reply_text(help_text)
    
    async def stats_command(self, client: Client, message: Message):
        """Handle /stats command"""
        stats = get_system_stats()
        
        # Add bot stats
        uptime = datetime.now() - self.start_time
        uptime_str = str(uptime).split('.')[0]
        
        queue_size = self.task_manager.queue.qsize()
        active_tasks = len(self.task_manager.active_tasks)
        total_tasks = len(self.task_manager.tasks)
        
        stats += f"""
{BOT_EMOJI} **Bot Statistics**
├ Uptime: `{uptime_str}`
├ Active Tasks: `{active_tasks}`
├ Queue Size: `{queue_size}`
└ Total Tasks: `{total_tasks}`

{create_fancy_footer()}"""
        
        await message.reply_text(stats)
    
    async def queue_command(self, client: Client, message: Message):
        """Handle /queue command"""
        queue_info = self.task_manager.get_queue_info()
        
        if not queue_info:
            await message.reply_text(f"{INFO_EMOJI} Queue is empty")
            return
        
        text = f"{create_fancy_header('CURRENT QUEUE', QUEUE_EMOJI)}\n\n"
        
        for i, task in enumerate(queue_info, 1):
            text += (
                f"**{i}. {task['status']}**\n"
                f"  {USER_EMOJI} **User:** `{task['user']}`\n"
                f"  {FILE_EMOJI} **File:** `{task['file']}`\n"
                f"  {DISK_EMOJI} **Size:** `{task['size']}`\n"
                f"  {FILTER_EMOJI} **Domains:** `{task['domains']}`\n"
                f"  {CHART_EMOJI} **Progress:** `{task['progress']}`\n"
                f"  {CLOCK_EMOJI} **Elapsed:** `{task['elapsed']}`\n\n"
            )
        
        text += create_fancy_footer()
        await message.reply_text(text)
    
    async def cancel_command(self, client: Client, message: Message):
        """Handle /cancel command"""
        user_id = message.from_user.id
        task = self.task_manager.get_user_task(user_id)
        
        if not task:
            await message.reply_text(f"{ERROR_EMOJI} No active task to cancel")
            return
        
        # Check for specific task ID in command
        parts = message.text.split()
        if len(parts) > 1:
            task_id = parts[1]
            if task_id != task.task_id and user_id not in ADMINS:
                await message.reply_text(f"{ERROR_EMOJI} You can only cancel your own tasks")
                return
            if task_id in self.task_manager.tasks:
                success = await self.task_manager.cancel_task(task_id, user_id)
                if success:
                    await message.reply_text(f"{SUCCESS_EMOJI} Task `{task_id}` cancelled successfully")
                else:
                    await message.reply_text(f"{ERROR_EMOJI} Failed to cancel task")
                return
        
        # Cancel current user's task
        success = await self.task_manager.cancel_task(task.task_id, user_id)
        
        if success:
            await message.reply_text(f"{SUCCESS_EMOJI} Your task has been cancelled")
            
            if task.status_message:
                try:
                    await task.status_message.edit_text(
                        f"{CANCEL_EMOJI} **Task Cancelled** {CANCEL_EMOJI}\n\n"
                        f"Your task has been cancelled successfully.\n\n"
                        f"{ROCKET_EMOJI} Send a new file to start again."
                    )
                except:
                    pass
        else:
            await message.reply_text(f"{ERROR_EMOJI} Failed to cancel task")
    
    async def handle_document(self, client: Client, message: Message):
        """Handle document uploads"""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or f"User_{user_id}"
        
        # Check if user already has a task
        existing_task = self.task_manager.get_user_task(user_id)
        if existing_task and existing_task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.TIMEOUT]:
            await message.reply_text(
                f"{WARNING_EMOJI} **Active Task Detected!**\n\n"
                f"You already have an active task. Please wait for it to complete or use /cancel to cancel it.\n\n"
                f"**Current Status:** {existing_task.status}"
            )
            return
        
        # Check file size
        file_size = message.document.file_size
        if file_size > MAX_FILE_SIZE:
            await message.reply_text(
                f"{ERROR_EMOJI} **File Too Large!**\n\n"
                f"Maximum size: `{format_size(MAX_FILE_SIZE)}`\n"
                f"Your file: `{format_size(file_size)}`\n\n"
                f"{INFO_EMOJI} Please compress or split the file."
            )
            return
        
        # Check file extension
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in SUPPORTED_ARCHIVES:
            await message.reply_text(
                f"{ERROR_EMOJI} **Unsupported Format!**\n\n"
                f"Supported formats: `{', '.join(SUPPORTED_ARCHIVES)}`\n"
                f"Your file: `{ext}`"
            )
            return
        
        # Create task
        task = self.task_manager.create_task(user_id, user_name, message.id, message.chat.id)
        task.total_size = file_size
        task.status = TaskStatus.DOWNLOADING
        task.current_file_name = file_name
        
        status_msg = await message.reply_text(
            f"{DOWNLOAD_EMOJI} **DOWNLOADING FILE** {DOWNLOAD_EMOJI}\n\n"
            f"{FILE_EMOJI} **File:** `{file_name}`\n"
            f"{DISK_EMOJI} **Size:** `{format_size(file_size)}`\n\n"
            f"{ZAP_EMOJI} Starting download...",
            reply_markup=task.get_cancel_button()
        )
        task.status_message = status_msg
        
        # Download file
        try:
            task.download_start_time = time.time()
            task.last_update_time = time.time()
            
            file_path = await message.download(
                file_name=os.path.join(TEMP_DIR, f"{task.task_id}_{sanitize_filename(file_name)}"),
                progress=self.download_progress,
                progress_args=(task, status_msg)
            )
            
            if task.cancel_requested:
                return
            
            task.archive_path = file_path
            
            # Check password protection
            await status_msg.edit_text(
                f"{LOCK_EMOJI} **CHECKING ARCHIVE** {LOCK_EMOJI}\n\n"
                f"{MICROSCOPE_EMOJI} Analyzing archive protection...",
                reply_markup=task.get_cancel_button()
            )
            
            is_protected = False
            if ext == '.rar':
                is_protected = PasswordDetector.check_rar_protected(file_path)
            elif ext == '.7z':
                is_protected = PasswordDetector.check_7z_protected(file_path)
            elif ext == '.zip':
                is_protected = PasswordDetector.check_zip_protected(file_path)
            
            if task.cancel_requested:
                return
            
            if is_protected:
                task.status = TaskStatus.WAITING_PASSWORD
                await status_msg.edit_text(
                    f"{LOCK_EMOJI} **PASSWORD REQUIRED** {LOCK_EMOJI}\n\n"
                    f"This archive is password protected.\n\n"
                    f"{KEY_EMOJI} Please enter the password (you have {INPUT_TIMEOUT}s):\n\n"
                    f"Use /cancel to abort.",
                    reply_markup=task.get_cancel_button()
                )
                
                # Set timeout for password
                task.timeout_task = asyncio.create_task(
                    self.task_manager.timeout_task(task.task_id, "password")
                )
            else:
                task.status = TaskStatus.WAITING_DOMAINS
                await status_msg.edit_text(
                    f"{FILTER_EMOJI} **DOMAINS REQUIRED** {FILTER_EMOJI}\n\n"
                    f"File: `{file_name}`\n"
                    f"Size: `{format_size(file_size)}`\n\n"
                    f"{MAGNIFIER_EMOJI} Please enter domains to filter (comma-separated, {INPUT_TIMEOUT}s):\n"
                    f"Example: `google.com, facebook.com, twitter.com`\n\n"
                    f"Use /cancel to abort.",
                    reply_markup=task.get_cancel_button()
                )
                
                # Set timeout for domains
                task.timeout_task = asyncio.create_task(
                    self.task_manager.timeout_task(task.task_id, "domains")
                )
        
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            await status_msg.edit_text(
                f"{ERROR_EMOJI} **Download Failed** {ERROR_EMOJI}\n\n"
                f"Error: `{str(e)}`\n\n"
                f"{create_fancy_footer()}"
            )
    
    async def download_progress(self, current, total, task: UserTask, message: Message):
        """Download progress callback with fancy UI"""
        if task.cancel_requested:
            raise Exception("Download cancelled by user")
        
        now = time.time()
        if now - task.last_update_time < PROGRESS_UPDATE_INTERVAL:
            return
        
        task.last_update_time = now
        downloaded = current
        total_size = total
        elapsed = now - task.download_start_time
        
        # Calculate speed
        speed = downloaded / elapsed if elapsed > 0 else 0
        task.speed_history.append(speed)
        avg_speed = sum(task.speed_history) / len(task.speed_history) if task.speed_history else 0
        
        # Calculate ETA
        remaining = total_size - downloaded
        eta = remaining / avg_speed if avg_speed > 0 else 0
        
        # Create progress bar
        progress = downloaded / total_size if total_size > 0 else 0
        bar = create_fancy_progress_bar(progress, 20, "fire")
        
        # Update message
        text = (
            f"{DOWNLOAD_EMOJI} **DOWNLOADING** {DOWNLOAD_EMOJI}\n\n"
            f"{FILE_EMOJI} **File:** `{task.current_file_name}`\n"
            f"{bar} `{progress*100:.1f}%`\n\n"
            f"{DISK_EMOJI} **Downloaded:** `{format_size(downloaded)} / {format_size(total_size)}`\n"
            f"{SPEED_EMOJI} **Speed:** `{format_speed(avg_speed)}`\n"
            f"{CLOCK_EMOJI} **Elapsed:** `{format_time(elapsed)}`\n"
            f"{ZAP_EMOJI} **ETA:** `{format_time(eta)}`\n\n"
            f"{task.get_cancel_button().inline_keyboard[0][0].text}"
        )
        
        try:
            await message.edit_text(text, reply_markup=task.get_cancel_button())
        except:
            pass
    
    async def handle_text(self, client: Client, message: Message):
        """Handle text messages (domains and passwords)"""
        user_id = message.from_user.id
        task = self.task_manager.get_user_task(user_id)
        
        if not task:
            await message.reply_text(
                f"{ERROR_EMOJI} **No Active Task**\n\n"
                f"{ROCKET_EMOJI} Send me an archive file to start."
            )
            return
        
        text = message.text.strip()
        
        # Cancel timeout task if exists
        if task.timeout_task:
            task.timeout_task.cancel()
            task.timeout_task = None
        
        # Handle password input
        if task.status == TaskStatus.WAITING_PASSWORD:
            task.password = text if text else None
            task.status = TaskStatus.WAITING_DOMAINS
            
            await message.reply_text(f"{SUCCESS_EMOJI} Password saved! Now enter domains:")
            
            # Update status message
            if task.status_message:
                await safe_edit_message(
                    task.status_message,
                    f"{FILTER_EMOJI} **DOMAINS REQUIRED** {FILTER_EMOJI}\n\n"
                    f"{LOCK_EMOJI} **Password:** {'✓ Provided' if task.password else '✗ None'}\n\n"
                    f"{MAGNIFIER_EMOJI} Please enter domains to filter (comma-separated, {INPUT_TIMEOUT}s):\n"
                    f"Example: `google.com, facebook.com, twitter.com`\n\n"
                    f"Use /cancel to abort.",
                    task.get_cancel_button()
                )
            
            # Set timeout for domains
            task.timeout_task = asyncio.create_task(
                self.task_manager.timeout_task(task.task_id, "domains")
            )
        
        # Handle domains input
        elif task.status == TaskStatus.WAITING_DOMAINS:
            # Parse domains
            domains = [d.strip().lower() for d in text.split(',') if d.strip()]
            
            if not domains:
                await message.reply_text(
                    f"{ERROR_EMOJI} Please enter at least one valid domain"
                )
                return
            
            task.domains = domains
            task.status = TaskStatus.DOWNLOADING  # Will be changed by processor
            
            await message.reply_text(
                f"{SUCCESS_EMOJI} Domains saved: `{', '.join(domains)}`\n"
                f"{QUEUE_EMOJI} Adding to queue..."
            )
            
            # Update status message
            if task.status_message:
                await safe_edit_message(
                    task.status_message,
                    f"{ARCHIVE_EMOJI} **Ready for Processing** {ARCHIVE_EMOJI}\n\n"
                    f"{FILE_EMOJI} **File:** `{os.path.basename(task.archive_path)}`\n"
                    f"{LOCK_EMOJI} **Password:** {'✓ Provided' if task.password else '✗ None'}\n"
                    f"{FILTER_EMOJI} **Domains:** `{', '.join(domains)}`\n\n"
                    f"{QUEUE_EMOJI} **Status:** Queued for processing\n\n"
                    f"{ZAP_EMOJI} Please wait...",
                    task.get_cancel_button()
                )
            
            # Add to queue
            await self.task_manager.add_to_queue(task.task_id)
        
        else:
            await message.reply_text(
                f"{ERROR_EMOJI} **Invalid Input**\n\n"
                f"Please follow the instructions or use /cancel to abort."
            )
    
    async def handle_callback(self, client: Client, callback_query: CallbackQuery):
        """Handle callback queries"""
        data = callback_query.data
        user_id = callback_query.from_user.id
        
        if data.startswith("cancel_"):
            task_id = data.replace("cancel_", "")
            task = self.task_manager.get_task(task_id)
            
            if not task:
                await callback_query.answer("Task not found")
                return
            
            if task.user_id != user_id and user_id not in ADMINS:
                await callback_query.answer("You can only cancel your own tasks")
                return
            
            success = await self.task_manager.cancel_task(task_id, user_id)
            
            if success:
                await callback_query.answer("Task cancelled successfully")
                await callback_query.message.edit_text(
                    f"{CANCEL_EMOJI} **Task Cancelled** {CANCEL_EMOJI}\n\n"
                    f"Task `{task_id}` has been cancelled."
                )
            else:
                await callback_query.answer("Failed to cancel task")
    
    async def run(self):
        """Run the bot"""
        print(f"╔════════════════════════════════════════╗")
        print(f"║    RUTE COOKIE EXTRACTOR BOT          ║")
        print(f"╚════════════════════════════════════════╝")
        print(f"Starting bot...")
        
        # Store the event loop
        self.loop = asyncio.get_running_loop()
        
        # Start worker
        self.task_manager.worker_task = asyncio.create_task(self.start_worker())
        
        # Start bot
        await self.app.start()
        
        print(f"✓ Bot is running!")
        print(f"Owner: {OWNER_TAG}")
        print(f"Press Ctrl+C to stop")
        
        # Keep running
        while True:
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot"""
        print(f"Stopping bot...")
        
        # Cancel all tasks
        for task_id in list(self.task_manager.tasks.keys()):
            await self.task_manager.cancel_task(task_id)
        
        # Stop worker
        if self.task_manager.worker_task:
            self.task_manager.worker_task.cancel()
        
        # Stop bot
        await self.app.stop()
        
        print(f"✓ Bot stopped")

# ==============================================================================
#                                MAIN
# ==============================================================================

async def main():
    """Main function"""
    bot = CookieExtractorBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        print(f"\nReceived interrupt signal")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
